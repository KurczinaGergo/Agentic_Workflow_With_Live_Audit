import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


TERMINAL_EVENT_TYPES = {"delegation.completed", "delegation.failed", "delegation.rejected"}
REQUIRED_DELEGATION_EVENT_TYPES = {
    "delegation.created",
    "runtime.agent.spawned",
    "binding.delegation_runtime_agent",
    "runtime.channel.created",
    "binding.delegation_channel",
}
RUN_PERSISTENT_ROLES = {"main_context"}
WORKFLOW_PERSISTENT_ROLES = {"architect"}
WORKFLOW_CLOSE_EVENT_TYPES = {"workflow.closed", "workflow.completed"}


def role_requires_runtime_termination(role: str | None) -> bool:
    return role not in RUN_PERSISTENT_ROLES | WORKFLOW_PERSISTENT_ROLES


def role_requires_termination_on_close(role: str | None) -> bool:
    return role in WORKFLOW_PERSISTENT_ROLES


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def ensure_timestamp(envelope: dict) -> dict:
    if not envelope.get("timestamp"):
        envelope["timestamp"] = utc_timestamp()
    return envelope


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            entry["_source_file"] = str(path)
            entry["_append_index"] = index
            entries.append(entry)
    return entries


def load_events(path: Path) -> list[dict]:
    return read_jsonl(path)


def load_transcripts(channels_dir: Path) -> list[dict]:
    entries: list[dict] = []
    if not channels_dir.exists():
        return entries

    for transcript_path in sorted(channels_dir.glob("*.jsonl")):
        for entry in read_jsonl(transcript_path):
            entry["_file_name"] = transcript_path.name
            entries.append(entry)
    return entries


def sorted_timeline_items(events: list[dict], transcripts: list[dict]) -> list[dict]:
    items: list[dict] = []
    sequence = 0
    for event in events:
        event_time = parse_timestamp(event.get("timestamp"))
        items.append(
            {
                "kind": "event",
                "timestamp": event.get("timestamp"),
                "timestamp_valid": event_time is not None,
                "sort_timestamp": event_time.isoformat() if event_time else None,
                "sequence": sequence,
                "entry": event,
            }
        )
        sequence += 1

    for transcript in transcripts:
        transcript_time = parse_timestamp(transcript.get("timestamp"))
        items.append(
            {
                "kind": "transcript",
                "timestamp": transcript.get("timestamp"),
                "timestamp_valid": transcript_time is not None,
                "sort_timestamp": transcript_time.isoformat() if transcript_time else None,
                "sequence": sequence,
                "entry": transcript,
            }
        )
        sequence += 1

    return sorted(
        items,
        key=lambda item: (
            not item["timestamp_valid"],
            item["sort_timestamp"] or "",
            item["sequence"],
        ),
    )


def group_by_delegation(events: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        delegation_id = event.get("delegation_id")
        if delegation_id:
            grouped[delegation_id].append(event)
    return dict(grouped)


def first_event(events: list[dict], event_type: str) -> dict | None:
    return next((event for event in events if event.get("event_type") == event_type), None)


def terminal_events(events: list[dict]) -> list[tuple[int, dict]]:
    return [
        (index, event)
        for index, event in enumerate(events)
        if event.get("event_type") in TERMINAL_EVENT_TYPES
    ]


def append_attention_once(attention: list[dict], kind: str, severity: str, summary: str) -> None:
    item = {"kind": kind, "severity": severity, "summary": summary}
    if item not in attention:
        attention.append(item)


def derive_graph_state(events: list[dict], transcripts: list[dict]) -> dict:
    agents: dict[str, dict] = {}
    delegations: dict[str, dict] = {}
    channels: dict[str, dict] = {}
    messages: list[dict] = []
    attention: list[dict] = []

    def ensure_agent(agent_id: str | None) -> dict | None:
        if not agent_id:
            return None
        return agents.setdefault(
            agent_id,
            {
                "id": agent_id,
                "role": None,
                "status": "active",
                "spawned_at": None,
                "terminated_at": None,
                "last_seen_at": None,
            },
        )

    def is_role_placeholder_target(event: dict) -> bool:
        if event.get("event_type") != "delegation.created":
            return False

        target_agent_id = event.get("target_agent_id")
        target_role = event.get("payload", {}).get("target_role")
        return bool(target_agent_id and target_role and target_agent_id == target_role)

    for event in events:
        event_type = event.get("event_type")
        payload = event.get("payload", {})
        timestamp = event.get("timestamp")
        source_agent = ensure_agent(event.get("source_agent_id"))
        target_agent = None if is_role_placeholder_target(event) else ensure_agent(event.get("target_agent_id"))
        if source_agent:
            source_agent["last_seen_at"] = timestamp
        if target_agent:
            target_agent["last_seen_at"] = timestamp

        if parse_timestamp(timestamp) is None:
            attention.append(
                {
                    "kind": "timestamp",
                    "severity": "warning",
                    "summary": f"{event.get('event_id', 'event')} has an invalid or missing timestamp",
                }
            )

        if event_type == "runtime.agent.spawned" and target_agent:
            target_agent["role"] = payload.get("role") or target_agent.get("role")
            target_agent["status"] = "active"
            target_agent["spawned_at"] = timestamp

        if event_type == "runtime.agent.terminated" and target_agent:
            target_agent["status"] = "terminated"
            target_agent["terminated_at"] = timestamp
            target_agent["ended_reason"] = payload.get("ended_reason") or payload.get("summary")

        delegation_id = event.get("delegation_id")
        if delegation_id:
            delegation = delegations.setdefault(
                delegation_id,
                {
                    "id": delegation_id,
                    "status": "open",
                    "source_agent_id": event.get("source_agent_id"),
                    "target_agent_id": event.get("target_agent_id"),
                    "runtime_agent_id": None,
                    "channel_id": None,
                    "workflow_step": event.get("workflow_step"),
                    "target_role": payload.get("target_role") or payload.get("role"),
                    "created_at": None,
                    "ended_at": None,
                    "summary": payload.get("summary") or payload.get("purpose"),
                },
            )
            delegation["workflow_step"] = delegation.get("workflow_step") or event.get("workflow_step")
            delegation["summary"] = payload.get("summary") or delegation.get("summary")

            if event_type == "delegation.created":
                delegation["status"] = payload.get("status") or "created"
                delegation["created_at"] = timestamp
                delegation["source_agent_id"] = event.get("source_agent_id")
                delegation["target_role"] = payload.get("target_role") or delegation.get("target_role")

            if event_type == "binding.delegation_runtime_agent":
                delegation["runtime_agent_id"] = event.get("target_agent_id")
                delegation["target_role"] = payload.get("role") or delegation.get("target_role")

            if event_type == "binding.delegation_channel":
                delegation["channel_id"] = event.get("channel_id")

            if event_type in TERMINAL_EVENT_TYPES:
                delegation["status"] = payload.get("status") or event_type.split(".")[-1]
                delegation["result"] = payload.get("result")
                delegation["ended_at"] = timestamp

        channel_id = event.get("channel_id")
        if channel_id:
            channel = channels.setdefault(
                channel_id,
                {
                    "id": channel_id,
                    "status": "open",
                    "owners": [],
                    "delegation_id": delegation_id,
                    "created_at": None,
                    "closed_at": None,
                },
            )
            channel["delegation_id"] = channel.get("delegation_id") or delegation_id

            if event_type == "runtime.channel.created":
                channel["status"] = "open"
                channel["owners"] = payload.get("owners") or [
                    value
                    for value in (event.get("source_agent_id"), event.get("target_agent_id"))
                    if value
                ]
                channel["created_at"] = timestamp

            if event_type == "runtime.channel.closed":
                channel["status"] = "closed"
                channel["closed_at"] = timestamp

        if event_type == "logical.message.sent":
            messages.append(
                {
                    "id": event.get("event_id"),
                    "kind": "event",
                    "timestamp": timestamp,
                    "source_agent_id": event.get("source_agent_id"),
                    "target_agent_id": event.get("target_agent_id"),
                    "delegation_id": delegation_id,
                    "channel_id": channel_id,
                    "message_type": event.get("message_type"),
                    "summary": payload.get("summary") or event.get("message_type"),
                }
            )

    for transcript in transcripts:
        if parse_timestamp(transcript.get("timestamp")) is None:
            attention.append(
                {
                    "kind": "timestamp",
                    "severity": "warning",
                    "summary": f"{transcript.get('message_id', 'message')} has an invalid or missing timestamp",
                }
            )
        messages.append(
            {
                "id": transcript.get("message_id"),
                "kind": "transcript",
                "timestamp": transcript.get("timestamp"),
                "source_agent_id": transcript.get("source_agent_id"),
                "target_agent_id": transcript.get("target_agent_id"),
                "delegation_id": transcript.get("delegation_id"),
                "channel_id": transcript.get("channel_id"),
                "message_type": transcript.get("message_type"),
                "summary": transcript.get("body"),
            }
        )

    grouped = group_by_delegation(events)
    for delegation_id, delegation_events in grouped.items():
        created = first_event(delegation_events, "delegation.created")
        terminals = terminal_events(delegation_events)
        if created is None and terminals:
            append_attention_once(
                attention,
                "lifecycle",
                "danger",
                f"{delegation_id} has a terminal delegation event without delegation.created",
            )

        present = {event.get("event_type") for event in delegation_events}
        for required_event in sorted(REQUIRED_DELEGATION_EVENT_TYPES):
            if required_event not in present:
                append_attention_once(
                    attention,
                    "lifecycle",
                    "warning",
                    f"{delegation_id} missing required event: {required_event}",
                )

        delegation = delegations.get(delegation_id, {})
        runtime_agent_id = delegation.get("runtime_agent_id")
        runtime_agent = agents.get(runtime_agent_id) if runtime_agent_id else None
        if runtime_agent_id:
            for _, terminal_event in terminals:
                if terminal_event.get("source_agent_id") != runtime_agent_id:
                    append_attention_once(
                        attention,
                        "lifecycle",
                        "danger",
                        (
                            f"{delegation_id} terminal event source_agent_id "
                            f"{terminal_event.get('source_agent_id')} does not match bound runtime agent "
                            f"{runtime_agent_id}"
                        ),
                    )

        if terminals:
            terminal_index = terminals[-1][0]
            for index, event in enumerate(delegation_events):
                if index <= terminal_index:
                    continue
                if event.get("event_type") in REQUIRED_DELEGATION_EVENT_TYPES - {"delegation.created"}:
                    append_attention_once(
                        attention,
                        "lifecycle",
                        "danger",
                        f"{delegation_id} {event.get('event_type')} appears after terminal delegation event",
                    )

        if (
            delegation.get("status") in {"completed", "failed", "rejected"}
            and runtime_agent
            and role_requires_runtime_termination(delegation.get("target_role") or runtime_agent.get("role"))
            and runtime_agent.get("status") != "terminated"
        ):
            append_attention_once(
                attention,
                "lifecycle",
                "warning",
                (
                    f"{delegation_id} ended as {delegation.get('status')} but runtime agent "
                    f"{runtime_agent_id} has no runtime.agent.terminated event"
                ),
            )
        channel_id = delegation.get("channel_id")
        channel = channels.get(channel_id) if channel_id else None
        if delegation.get("status") in {"completed", "failed", "rejected"} and channel and channel.get("status") != "closed":
            append_attention_once(
                attention,
                "lifecycle",
                "warning",
                (
                    f"{delegation_id} ended as {delegation.get('status')} but channel "
                    f"{channel_id} has no runtime.channel.closed event"
                ),
            )

    for _, terminal_event in [
        item
        for delegation_events in grouped.values()
        for item in terminal_events(delegation_events)
    ]:
        source_agent_id = terminal_event.get("source_agent_id")
        source_agent = agents.get(source_agent_id) if source_agent_id else None
        if source_agent_id in {"codex_main", "MainContext"}:
            continue
        if source_agent and not source_agent.get("spawned_at") and not source_agent.get("role"):
            append_attention_once(
                attention,
                "lifecycle",
                "warning",
                f"{source_agent_id} produced a terminal event without runtime.agent.spawned evidence",
            )

    if any(event.get("event_type") in WORKFLOW_CLOSE_EVENT_TYPES for event in events):
        for agent in agents.values():
            if role_requires_termination_on_close(agent.get("role")) and agent.get("status") != "terminated":
                append_attention_once(
                    attention,
                    "lifecycle",
                    "warning",
                    f"workflow close requires runtime.agent.terminated for {agent.get('role')} {agent['id']}",
                )

    timeline = sorted_timeline_items(events, transcripts)
    return {
        "agents": sorted(agents.values(), key=lambda item: item["id"]),
        "delegations": sorted(delegations.values(), key=lambda item: item["id"]),
        "channels": sorted(channels.values(), key=lambda item: item["id"]),
        "messages": sorted(
            messages,
            key=lambda item: (
                parse_timestamp(item.get("timestamp")) is None,
                parse_timestamp(item.get("timestamp")) or datetime.max.replace(tzinfo=UTC),
                item.get("id") or "",
            ),
        ),
        "attention": attention,
        "replay": {
            "first_timestamp": timeline[0]["timestamp"] if timeline else None,
            "last_timestamp": timeline[-1]["timestamp"] if timeline else None,
            "item_count": len(timeline),
            "invalid_timestamp_count": sum(1 for item in timeline if not item["timestamp_valid"]),
        },
        "timeline": timeline,
    }


def load_audit_snapshot(audit_dir: Path) -> dict:
    log_path = audit_dir / "workflow_log.jsonl"
    channels_dir = audit_dir / "channels"
    events = load_events(log_path)
    transcripts = load_transcripts(channels_dir)
    graph = derive_graph_state(events, transcripts)
    return {
        "workflow_name": audit_dir.name,
        "log_path": str(log_path),
        "channels_dir": str(channels_dir),
        "events": events,
        "transcripts": transcripts,
        "graph": graph,
    }
