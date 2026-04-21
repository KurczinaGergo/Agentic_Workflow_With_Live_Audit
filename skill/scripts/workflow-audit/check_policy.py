import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml


TERMINAL_EVENT_TYPES = {"delegation.completed", "delegation.failed", "delegation.rejected"}
CREATED_STATUSES = {"created", "pending_runtime_binding"}
TARGET_REQUIRED_EVENT_TYPES = {
    "runtime.agent.spawned",
    "runtime.agent.terminated",
    "runtime.channel.created",
    "runtime.channel.closed",
    "binding.delegation_runtime_agent",
    "binding.delegation_channel",
    "logical.message.sent",
    *TERMINAL_EVENT_TYPES,
}


def load_events(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_policy(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def roles_from_events(events: list[dict]) -> dict[str, str]:
    roles: dict[str, str] = {}

    for event in events:
        if event["event_type"] in {"runtime.agent.spawned", "binding.delegation_runtime_agent"}:
            target_agent = event.get("target_agent_id")
            role = event.get("payload", {}).get("role")
            if target_agent and role:
                roles[target_agent] = role

    for event in events:
        if event["event_type"] == "delegation.created":
            source_agent = event.get("source_agent_id")
            role = event.get("payload", {}).get("requested_by_role")
            if source_agent and role:
                roles.setdefault(source_agent, role)

    return roles


def event_index(events: list[dict], key: str) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        value = event.get(key)
        if value:
            grouped[value].append(event)
    return grouped


def runtime_agent_for_delegation(events: list[dict]) -> str | None:
    for event in events:
        if event["event_type"] == "binding.delegation_runtime_agent":
            return event.get("target_agent_id")
    return None


def runtime_binding_for_delegation(events: list[dict]) -> dict | None:
    for event in events:
        if event["event_type"] == "binding.delegation_runtime_agent":
            return event
    return None


def terminal_status(events: list[dict]) -> str | None:
    terminal_events = [event for event in events if event["event_type"] in TERMINAL_EVENT_TYPES]
    if not terminal_events:
        return None
    return terminal_events[-1].get("payload", {}).get("status")


def has_message(events: list[dict], message_type: str) -> bool:
    return any(
        event["event_type"] == "logical.message.sent" and event.get("message_type") == message_type
        for event in events
    )


def child_delegations_for_requester(
    delegations: dict[str, dict],
    grouped: dict[str, list[dict]],
    requester_agent_id: str,
    workflow_step: str,
) -> list[tuple[str, list[dict]]]:
    matches: list[tuple[str, list[dict]]] = []
    for delegation_id, event in delegations.items():
        if (
            event.get("requested_by_agent_id") == requester_agent_id
            and event.get("workflow_step") == workflow_step
        ):
            matches.append((delegation_id, grouped[delegation_id]))
    return matches


def validate(events: list[dict], policy: dict) -> list[str]:
    roles = roles_from_events(events)
    grouped_by_delegation = event_index(events, "delegation_id")
    delegations = {
        event["delegation_id"]: event
        for event in events
        if event["event_type"] == "delegation.created" and event.get("delegation_id")
    }
    violations: list[str] = []

    role_policy = policy.get("roles", {})

    for event in events:
        if event["event_type"] in TARGET_REQUIRED_EVENT_TYPES and not event.get("target_agent_id"):
            delegation_id = event.get("delegation_id")
            violations.append(
                f"[{delegation_id}] {event['event_type']} requires target_agent_id"
            )

    for delegation_id, event in delegations.items():
        payload = event.get("payload", {})
        requester_role = payload.get("requested_by_role")
        target_role = payload.get("target_role")
        compatibility_role = payload.get("role")
        status = payload.get("status")

        if not requester_role:
            violations.append(f"[{delegation_id}] delegation.created missing payload.requested_by_role")
        if not target_role:
            violations.append(f"[{delegation_id}] delegation.created missing payload.target_role")
        if compatibility_role != target_role:
            violations.append(
                f"[{delegation_id}] delegation.created payload.role must match target_role: {compatibility_role} -> {target_role}"
            )
        if status not in CREATED_STATUSES:
            violations.append(
                f"[{delegation_id}] delegation.created invalid status: {status}"
            )

        allowed = set(role_policy.get(requester_role, {}).get("can_delegate_to", []))
        if target_role not in allowed:
            violations.append(
                f"[{delegation_id}] forbidden logical delegation: {requester_role} -> {target_role}"
            )

        delegation_events = grouped_by_delegation[delegation_id]
        binding = runtime_binding_for_delegation(delegation_events)
        if event.get("target_agent_id") is None and not binding:
            violations.append(f"[{delegation_id}] pre-bind delegation missing runtime agent binding")
        if binding:
            bound_role = binding.get("payload", {}).get("role")
            if bound_role != target_role:
                violations.append(
                    f"[{delegation_id}] runtime binding role mismatch: {target_role} -> {bound_role}"
                )

    for rule in policy.get("rules", []):
        for edge in rule.get("forbid_delegation", []):
            source_role, target_role = edge.split("->", 1)
            for delegation_id, event in delegations.items():
                requester_role = event.get("payload", {}).get("requested_by_role") or roles.get(
                    event.get("source_agent_id")
                )
                actual_target_role = event.get("payload", {}).get("target_role")
                if requester_role == source_role and actual_target_role == target_role:
                    violations.append(f"[{delegation_id}] violates rule {rule['id']}: {edge}")

    for rule in policy.get("rules", []):
        required_events = rule.get("requires_for_each_delegation")
        if not required_events:
            continue

        for delegation_id in delegations:
            delegation_events = grouped_by_delegation[delegation_id]
            present = {event["event_type"] for event in delegation_events}
            for required_event in required_events:
                if required_event not in present:
                    violations.append(f"[{delegation_id}] missing required event: {required_event}")

    for event in events:
        if event["event_type"] != "logical.message.sent":
            continue

        delegation_id = event.get("delegation_id")
        source_agent = event.get("source_agent_id")
        message_type = event.get("message_type")
        source_role = roles.get(source_agent)
        allowed_message_types = set(role_policy.get(source_role, {}).get("allowed_message_types", []))

        if delegation_id not in delegations:
            violations.append(f"[{delegation_id}] logical message without delegation")

        if message_type not in allowed_message_types:
            violations.append(
                f"[{delegation_id}] message_type '{message_type}' is not allowed for role '{source_role}'"
            )

    allowed_final_statuses: set[str] = set()
    for rule in policy.get("rules", []):
        if "final_status_must_be_one_of" in rule:
            allowed_final_statuses.update(rule["final_status_must_be_one_of"])

    for delegation_id in delegations:
        delegation_events = grouped_by_delegation[delegation_id]
        status = terminal_status(delegation_events)
        if status is None:
            violations.append(f"[{delegation_id}] no terminal delegation event found")
        elif allowed_final_statuses and status not in allowed_final_statuses:
            violations.append(f"[{delegation_id}] invalid final status: {status}")

    for rule in policy.get("rules", []):
        required_child_steps = rule.get("requires_child_steps")
        if not required_child_steps:
            continue

        parent_step = rule.get("when_workflow_step")
        for delegation_id, event in delegations.items():
            if event.get("workflow_step") != parent_step:
                continue

            worker_agent_id = runtime_agent_for_delegation(grouped_by_delegation[delegation_id])
            if not worker_agent_id:
                violations.append(f"[{delegation_id}] missing runtime agent binding for implementation")
                continue

            for child_step in required_child_steps:
                children = child_delegations_for_requester(
                    delegations,
                    grouped_by_delegation,
                    worker_agent_id,
                    child_step,
                )
                if not children:
                    violations.append(f"[{delegation_id}] missing child delegation for workflow_step '{child_step}'")
                    continue

                matched_child = False
                for child_delegation_id, child_events in children:
                    request_message = f"{child_step}_request"
                    result_message = f"{child_step}_result"
                    if child_step == "test":
                        request_message = "test_request"
                        result_message = "test_result"
                    elif child_step == "review":
                        request_message = "review_request"
                        result_message = "review_result"

                    if has_message(child_events, request_message) and has_message(child_events, result_message):
                        status = terminal_status(child_events)
                        if status == "completed":
                            matched_child = True
                            break
                        violations.append(
                            f"[{child_delegation_id}] child delegation for '{child_step}' did not complete successfully"
                        )

                if not matched_child:
                    violations.append(
                        f"[{delegation_id}] no successful '{child_step}' delegation was linked to requester '{worker_agent_id}'"
                    )

    return violations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", required=True)
    parser.add_argument("--log", required=True)
    args = parser.parse_args()

    events = load_events(Path(args.log))
    policy = load_policy(Path(args.policy))
    roles = roles_from_events(events)
    delegations = [event for event in events if event["event_type"] == "delegation.created"]
    violations = validate(events, policy)

    print("=== WORKFLOW AUDIT POLICY CHECK ===")
    print(f"Total events: {len(events)}")
    print(f"Total delegations: {len(delegations)}")
    print(f"Known agents: {len(roles)}")
    print()

    if violations:
        print("Violations:")
        for violation in violations:
            print(f"- {violation}")
        return 1

    print("Violations: none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
