import argparse
import html
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from check_policy import load_policy, validate
from workflow_config import resolve_audit_dir


TERMINAL_EVENT_TYPES = {"delegation.completed", "delegation.failed", "delegation.rejected"}
NON_ACCEPTING_RESULTS = {"changes_requested", "blocked", "fail", "failed", "rejected", "skipped"}


def load_events(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_transcripts(channels_dir: Path) -> list[dict]:
    entries: list[dict] = []
    if not channels_dir.exists():
        return entries

    for transcript_path in sorted(channels_dir.glob("*.jsonl")):
        with transcript_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                payload = json.loads(line)
                payload["_file_name"] = transcript_path.name
                entries.append(payload)
    return entries


def esc(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False)
    return html.escape(str(value), quote=True)


def short(value: str | None, length: int = 12) -> str:
    if not value:
        return "-"
    return value if len(value) <= length else value[:length]


def alias(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value)


def payload_value(event: dict, key: str) -> Any:
    return event.get("payload", {}).get(key)


def first_payload_value(events: list[dict], *keys: str) -> Any:
    for event in events:
        payload = event.get("payload", {})
        for key in keys:
            value = payload.get(key)
            if value not in (None, "", []):
                return value
    return None


def collect_payload_list(events: list[dict], key: str) -> list[Any]:
    values: list[Any] = []
    for event in events:
        value = payload_value(event, key)
        if value is None:
            continue
        if isinstance(value, list):
            values.extend(value)
        else:
            values.append(value)
    return values


def unique(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        marker = json.dumps(value, sort_keys=True, default=str) if isinstance(value, (dict, list)) else str(value)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(value)
    return result


def clean_mermaid(value: Any) -> str:
    return str(value or "-").replace("\n", " ").replace("\r", " ").replace('"', "'")


def is_role_placeholder_target(event: dict) -> bool:
    if event.get("event_type") != "delegation.created":
        return False

    target_agent_id = event.get("target_agent_id")
    target_role = event.get("payload", {}).get("target_role")
    return bool(target_agent_id and target_role and target_agent_id == target_role)


def build_participants(events: list[dict]) -> list[str]:
    participants = {"codex_main"}
    for event in events:
        for key in ("source_agent_id", "target_agent_id", "runtime_parent_agent_id", "logical_parent_agent_id"):
            if key == "target_agent_id" and is_role_placeholder_target(event):
                continue
            value = event.get(key)
            if value:
                participants.add(value)
    return sorted(participants)


def build_runtime_mermaid(events: list[dict]) -> str:
    lines = ["sequenceDiagram", "autonumber"]
    for participant in build_participants(events):
        lines.append(f'participant {alias(participant)} as "{clean_mermaid(participant)}"')

    for event in events:
        event_type = event["event_type"]
        source = event.get("source_agent_id") or "codex_main"
        target = None if is_role_placeholder_target(event) else event.get("target_agent_id")
        channel_id = event.get("channel_id") or "-"
        delegation_id = event.get("delegation_id") or "-"
        summary = payload_value(event, "summary") or event.get("message_type") or event_type
        label = f"{event_type}\\n{clean_mermaid(summary)}\\n{clean_mermaid(delegation_id)}"

        if event_type == "runtime.channel.created":
            owners = payload_value(event, "owners") or []
            if len(owners) == 2:
                lines.append(
                    f"Note over {alias(owners[0])},{alias(owners[1])}: {event_type}\\n{clean_mermaid(channel_id)}\\n{clean_mermaid(delegation_id)}"
                )
                continue

        if event_type == "runtime.channel.closed":
            lines.append(f"Note over {alias(source)}: {event_type}\\n{clean_mermaid(channel_id)}")
            continue

        if target:
            lines.append(f"{alias(source)}->>{alias(target)}: {label}")
        else:
            lines.append(f"Note over {alias(source)}: {label}")

    return "\n".join(lines) + "\n"


def build_logical_mermaid(events: list[dict]) -> str:
    participants = sorted(
        {
            value
            for event in events
            for key in ("source_agent_id", "target_agent_id", "logical_parent_agent_id", "requested_by_agent_id")
            if not (key == "target_agent_id" and is_role_placeholder_target(event))
            if (value := event.get(key)) and value != "codex_main"
        }
    )
    lines = ["sequenceDiagram", "autonumber"]
    for participant in participants:
        lines.append(f'participant {alias(participant)} as "{clean_mermaid(participant)}"')

    for event in events:
        event_type = event["event_type"]
        source = event.get("source_agent_id")
        target = event.get("target_agent_id")
        delegation_id = event.get("delegation_id")

        if event_type == "delegation.created":
            requester = event.get("requested_by_agent_id") or source or "codex_main"
            target_role = payload_value(event, "target_role") or "unknown_role"
            purpose = payload_value(event, "purpose") or event.get("message_type") or "delegation"
            lines.append(
                f"Note over {alias(requester)}: create {clean_mermaid(delegation_id)} -> {clean_mermaid(target_role)}\\n{clean_mermaid(purpose)}"
            )
        elif event_type == "logical.message.sent" and source and target:
            lines.append(
                f"{alias(source)}->>{alias(target)}: {clean_mermaid(event.get('message_type'))} ({clean_mermaid(delegation_id)})"
            )
        elif event_type in TERMINAL_EVENT_TYPES and source and target:
            status = payload_value(event, "status") or payload_value(event, "result") or event_type
            lines.append(f"{alias(source)}->>{alias(target)}: {clean_mermaid(status)} ({clean_mermaid(delegation_id)})")

    return "\n".join(lines) + "\n"


def build_connection_mermaid(delegations: list[dict]) -> str:
    lines = [
        "flowchart LR",
        "classDef agent fill:#f8fafc,stroke:#64748b,color:#0f172a;",
        "classDef ok fill:#ecfdf5,stroke:#15803d,color:#14532d;",
        "classDef warn fill:#fffbeb,stroke:#b45309,color:#78350f;",
        "classDef bad fill:#fef2f2,stroke:#b91c1c,color:#7f1d1d;",
    ]
    agents: set[str] = {"codex_main"}
    for delegation in delegations:
        for key in ("requester", "runtime_agent"):
            value = delegation.get(key)
            if value:
                agents.add(value)

    for agent in sorted(agents):
        lines.append(f'{alias("agent_" + agent)}["{clean_mermaid(agent)}"]:::agent')

    for delegation in delegations:
        node = alias("delegation_" + delegation["delegation_id"])
        status = delegation.get("status") or "open"
        css = "ok" if status == "completed" else "bad" if status in {"failed", "rejected"} else "warn"
        label = f"{delegation['delegation_id']}\\n{delegation.get('target_role') or '-'}\\n{status}"
        lines.append(f'{node}["{clean_mermaid(label)}"]:::{css}')
        requester = delegation.get("requester") or "codex_main"
        lines.append(f"{alias('agent_' + requester)} --> {node}")
        if delegation.get("runtime_agent"):
            lines.append(f"{node} --> {alias('agent_' + delegation['runtime_agent'])}")

    return "\n".join(lines) + "\n"


def group_by_delegation(events: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        delegation_id = event.get("delegation_id")
        if delegation_id:
            grouped[delegation_id].append(event)
    return dict(grouped)


def index_transcripts(
    transcripts: list[dict],
) -> tuple[dict[str, list[dict]], dict[tuple[str, str], list[dict]], dict[str, list[dict]]]:
    by_related: dict[str, list[dict]] = defaultdict(list)
    by_pair: dict[tuple[str, str], list[dict]] = defaultdict(list)
    by_channel: dict[str, list[dict]] = defaultdict(list)
    for entry in transcripts:
        if entry.get("related_event_id"):
            by_related[entry["related_event_id"]].append(entry)
        if entry.get("delegation_id") and entry.get("channel_id"):
            by_pair[(entry["delegation_id"], entry["channel_id"])].append(entry)
        if entry.get("channel_id"):
            by_channel[entry["channel_id"]].append(entry)
    return dict(by_related), dict(by_pair), dict(by_channel)


def build_delegation_rows(events: list[dict], transcripts: list[dict]) -> list[dict]:
    grouped = group_by_delegation(events)
    _, transcripts_by_pair, _ = index_transcripts(transcripts)
    rows: list[dict] = []

    for delegation_id, delegation_events in sorted(grouped.items()):
        created = next((event for event in delegation_events if event["event_type"] == "delegation.created"), None)
        terminal = next((event for event in reversed(delegation_events) if event["event_type"] in TERMINAL_EVENT_TYPES), None)
        runtime_binding = next(
            (event for event in delegation_events if event["event_type"] == "binding.delegation_runtime_agent"), None
        )
        channel_binding = next(
            (event for event in delegation_events if event["event_type"] == "binding.delegation_channel"), None
        )
        channel_id = (channel_binding or {}).get("channel_id") or next(
            (event.get("channel_id") for event in delegation_events if event.get("channel_id")), None
        )
        transcript_count = len(transcripts_by_pair.get((delegation_id, channel_id), [])) if channel_id else 0
        status = payload_value(terminal or {}, "status") or payload_value(terminal or {}, "result") or "open"
        result = payload_value(terminal or {}, "result") or payload_value(terminal or {}, "status") or "-"
        rows.append(
            {
                "delegation_id": delegation_id,
                "requester": (created or {}).get("requested_by_agent_id") or (created or {}).get("source_agent_id"),
                "requested_by_role": first_payload_value(delegation_events, "requested_by_role", "role"),
                "target_role": first_payload_value(delegation_events, "target_role", "role"),
                "runtime_agent": (runtime_binding or {}).get("target_agent_id"),
                "channel_id": channel_id,
                "workflow_label": first_payload_value(delegation_events, "workflow_label") or "-",
                "workflow_step": (created or delegation_events[0]).get("workflow_step") or "-",
                "status": status,
                "result": result,
                "summary": payload_value(terminal or {}, "summary")
                or first_payload_value(list(reversed(delegation_events)), "summary", "purpose")
                or "-",
                "artifact_refs": unique(
                    collect_payload_list(delegation_events, "artifact_refs")
                    + collect_payload_list(delegation_events, "artifact_ref")
                ),
                "commands": unique(collect_payload_list(delegation_events, "commands")),
                "findings": unique(collect_payload_list(delegation_events, "findings")),
                "acceptance_rationale": first_payload_value(list(reversed(delegation_events)), "acceptance_rationale"),
                "transcript_count": transcript_count,
                "has_terminal": terminal is not None,
                "has_runtime_binding": runtime_binding is not None,
                "has_channel_binding": channel_binding is not None,
                "events": delegation_events,
            }
        )

    return rows


def build_gate_rows(delegations: list[dict]) -> list[dict]:
    implementations = [row for row in delegations if row["workflow_step"] == "implementation"]
    reviews = [row for row in delegations if row["workflow_step"] == "review"]
    tests = [row for row in delegations if row["workflow_step"] == "test"]
    rows: list[dict] = []

    for implementation in implementations:
        worker = implementation.get("runtime_agent")
        review = next((row for row in reviews if row.get("requester") == worker), None)
        test = next((row for row in tests if row.get("requester") == worker), None)
        rows.append(
            {
                "task": implementation.get("workflow_label")
                if implementation.get("workflow_label") != "-"
                else implementation["delegation_id"],
                "implementation": implementation,
                "review": review,
                "test": test,
                "architect_handoff": implementation.get("status"),
            }
        )

    return rows


def state_class(value: Any) -> str:
    normalized = str(value or "").lower()
    if normalized in {"completed", "accept", "accepted", "pass", "passed", "ok", "success"}:
        return "success"
    if normalized in {"failed", "fail", "rejected", "changes_requested", "danger"}:
        return "danger"
    if normalized in {"blocked", "skipped", "open", "created", "requested", "warning"}:
        return "warning"
    return "neutral"


def badge(value: Any) -> str:
    return f'<span class="badge {state_class(value)}">{esc(value)}</span>'


def json_details(summary: str, value: Any) -> str:
    text = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)
    return (
        f'<details class="json-details"><summary>{esc(summary)}</summary>'
        f'<button class="copy-btn" type="button" data-copy="{esc(text)}">Copy</button>'
        f"<pre>{esc(text)}</pre></details>"
    )


def list_cell(values: list[Any]) -> str:
    if not values:
        return "-"
    items: list[str] = []
    for value in values:
        if isinstance(value, dict):
            label = value.get("code") or value.get("summary") or json.dumps(value, ensure_ascii=False)
        else:
            label = value
        items.append(f'<span class="token">{esc(label)}</span>')
    return " ".join(items)


def text_index(*values: Any) -> str:
    parts: list[str] = []
    for value in values:
        if value in (None, "", []):
            continue
        parts.append(json.dumps(value, ensure_ascii=False, default=str) if isinstance(value, (dict, list)) else str(value))
    return esc(" ".join(parts).lower())


def find_attention_items(
    events: list[dict],
    delegations: list[dict],
    transcripts: list[dict],
    policy_path: Path,
) -> tuple[list[dict], list[str]]:
    violations = validate(events, load_policy(policy_path), transcripts) if policy_path.exists() else []
    related_transcripts, transcript_pairs, _ = index_transcripts(transcripts)
    has_any_transcripts = bool(transcripts)
    items: list[dict] = [{"kind": "Policy", "severity": "danger", "summary": violation} for violation in violations]

    for row in delegations:
        if row["status"] in {"failed", "rejected"}:
            items.append({"kind": "Delegation", "severity": "danger", "summary": f"{row['delegation_id']} ended as {row['status']}"})
        if not row["has_terminal"]:
            items.append({"kind": "Delegation", "severity": "warning", "summary": f"{row['delegation_id']} has no terminal event"})
        if not row["has_runtime_binding"]:
            items.append({"kind": "Binding", "severity": "warning", "summary": f"{row['delegation_id']} has no runtime agent binding"})
        if not row["has_channel_binding"]:
            items.append({"kind": "Binding", "severity": "warning", "summary": f"{row['delegation_id']} has no channel binding"})
        if row["workflow_step"] in {"review", "test"} and str(row["result"]).lower() in NON_ACCEPTING_RESULTS:
            items.append({"kind": "Gate", "severity": "danger", "summary": f"{row['delegation_id']} {row['workflow_step']} result is {row['result']}"})

    for event in events:
        if event["event_type"] == "logical.message.sent" and has_any_transcripts:
            event_id = event["event_id"]
            pair_key = (event.get("delegation_id"), event.get("channel_id"))
            if event_id not in related_transcripts and pair_key not in transcript_pairs:
                items.append({"kind": "Transcript", "severity": "warning", "summary": f"{event_id} has no matching transcript evidence"})

        if event.get("message_type") == "blocker_report":
            items.append({"kind": "Blocker", "severity": "warning", "summary": payload_value(event, "summary") or f"{event['event_id']} reported a blocker"})
        if payload_value(event, "result") == "skipped":
            items.append({"kind": "Skipped", "severity": "warning", "summary": payload_value(event, "summary") or f"{event['event_id']} was skipped"})

    return items, violations


def build_summary(events: list[dict], delegations: list[dict], transcripts: list[dict], attention: list[dict]) -> dict:
    agents = {
        value
        for event in events
        for key in ("source_agent_id", "target_agent_id", "runtime_parent_agent_id", "logical_parent_agent_id")
        if not (key == "target_agent_id" and is_role_placeholder_target(event))
        if (value := event.get(key))
    }
    channels = {event.get("channel_id") for event in events if event.get("channel_id")}
    channels.update({entry.get("channel_id") for entry in transcripts if entry.get("channel_id")})
    return {
        "run_id": events[0]["run_id"] if events else "-",
        "first": events[0]["timestamp"] if events else "-",
        "last": events[-1]["timestamp"] if events else "-",
        "events": len(events),
        "delegations": len(delegations),
        "agents": len(agents),
        "channels": len([channel for channel in channels if channel]),
        "transcripts": len(transcripts),
        "attention": len(attention),
        "status_counts": dict(Counter(row["status"] for row in delegations)),
        "event_counts": dict(Counter(event["event_type"] for event in events)),
    }


def render_attention(items: list[dict]) -> str:
    if not items:
        return '<div class="empty-state">No audit findings need attention.</div>'
    rows = []
    for item in items:
        rows.append(
            f'<tr class="filter-row" data-search="{text_index(item)}" data-severity="{esc(item["severity"])}">'
            f"<td>{badge(item['severity'])}</td><td>{esc(item['kind'])}</td><td>{esc(item['summary'])}</td></tr>"
        )
    return f"<table><thead><tr><th>Severity</th><th>Kind</th><th>Finding</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"


def render_delegations(rows: list[dict]) -> str:
    rendered = []
    for row in rows:
        details = {
            key: row[key]
            for key in (
                "delegation_id",
                "requester",
                "requested_by_role",
                "target_role",
                "runtime_agent",
                "channel_id",
                "workflow_label",
                "workflow_step",
                "status",
                "result",
                "summary",
                "artifact_refs",
                "commands",
                "findings",
                "acceptance_rationale",
                "transcript_count",
            )
        }
        rendered.append(
            "<tr class=\"filter-row\" "
            f'data-search="{text_index(details)}" data-event-type="delegation" data-role="{esc(row.get("target_role"))}" '
            f'data-step="{esc(row["workflow_step"])}" data-result="{esc(row["result"])}" '
            f'data-channel="{esc(row.get("channel_id"))}" data-delegation="{esc(row["delegation_id"])}">'
            f'<td><button class="copy-btn" type="button" data-copy="{esc(row["delegation_id"])}">Copy</button> {esc(row["delegation_id"])}</td>'
            f"<td>{esc(row.get('requester'))}<br><small>{esc(row.get('requested_by_role'))}</small></td>"
            f"<td>{esc(row.get('target_role'))}<br><small>{esc(row.get('runtime_agent'))}</small></td>"
            f"<td>{esc(row.get('channel_id'))}</td>"
            f"<td>{esc(row.get('workflow_label'))}<br><small>{esc(row.get('workflow_step'))}</small></td>"
            f"<td>{badge(row.get('status'))}<br><small>{esc(row.get('result'))}</small></td>"
            f"<td>{esc(row.get('summary'))}</td>"
            f"<td>{list_cell(row.get('artifact_refs', []))}</td>"
            f"<td>{list_cell(row.get('commands', []))}</td>"
            f"<td>{list_cell(row.get('findings', []))}</td>"
            f"<td>{esc(row.get('transcript_count'))}</td>"
            f"<td>{json_details('Details', details)}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Delegation</th><th>Requester</th><th>Target</th><th>Channel</th>"
        "<th>Workflow</th><th>Status</th><th>Summary</th><th>Artifacts</th><th>Commands</th><th>Findings</th>"
        f"<th>Transcript</th><th>Inspect</th></tr></thead><tbody>{''.join(rendered)}</tbody></table>"
    )


def render_gate_timeline(rows: list[dict]) -> str:
    if not rows:
        return '<div class="empty-state">No implementation delegations were found.</div>'
    rendered = []
    for row in rows:
        implementation = row["implementation"]
        review = row.get("review") or {}
        test = row.get("test") or {}
        rendered.append(
            f'<tr class="filter-row" data-search="{text_index(row)}" data-step="implementation" data-result="{esc(implementation.get("result"))}" data-delegation="{esc(implementation["delegation_id"])}">'
            f"<td>{esc(row['task'])}</td>"
            f"<td>{badge(implementation.get('status'))}<br><small>{esc(implementation['delegation_id'])}</small></td>"
            f"<td>{badge(review.get('result', 'missing'))}<br><small>{esc(review.get('delegation_id'))}</small></td>"
            f"<td>{badge(test.get('result', 'missing'))}<br><small>{esc(test.get('delegation_id'))}</small></td>"
            f"<td>{badge(row.get('architect_handoff'))}</td>"
            f"<td>{esc(implementation.get('summary'))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Task</th><th>Implementation</th><th>Review Gate</th><th>Unit Gate</th>"
        f"<th>Architect Handoff</th><th>Evidence Summary</th></tr></thead><tbody>{''.join(rendered)}</tbody></table>"
    )


def render_transcripts(transcripts: list[dict]) -> str:
    if not transcripts:
        return '<div class="empty-state">No channel transcript entries were found.</div>'
    rows = []
    for entry in transcripts:
        body = entry.get("body", "")
        preview = body.replace("\n", " ")
        if len(preview) > 180:
            preview = preview[:177] + "..."
        rows.append(
            "<tr class=\"filter-row\" "
            f'data-search="{text_index(entry)}" data-role="{esc(entry.get("role"))}" data-step="{esc(entry.get("workflow_label"))}" '
            f'data-channel="{esc(entry.get("channel_id"))}" data-delegation="{esc(entry.get("delegation_id"))}" data-result="{esc(entry.get("message_type"))}">'
            f"<td>{esc(entry.get('_file_name'))}<br><small>{esc(entry.get('channel_id'))}</small></td>"
            f"<td>{esc(entry.get('timestamp'))}</td>"
            f"<td>{esc(entry.get('source_agent_id'))}<br><small>{esc(entry.get('target_agent_id'))}</small></td>"
            f"<td>{esc(entry.get('workflow_label'))}<br><small>{esc(entry.get('message_type'))}</small></td>"
            f"<td>{esc(preview)}<details><summary>Full body</summary><pre>{esc(body)}</pre></details></td>"
            f"<td>{list_cell(entry.get('artifact_refs') or [])}</td>"
            f"<td>{esc(entry.get('related_event_id'))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Channel File</th><th>Timestamp</th><th>Owners</th><th>Message</th>"
        f"<th>Body</th><th>Artifacts</th><th>Event</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def render_raw_ledger(events: list[dict]) -> str:
    rows = []
    for event in events:
        payload = event.get("payload", {})
        rows.append(
            "<tr class=\"filter-row\" "
            f'data-search="{text_index(event)}" data-event-type="{esc(event["event_type"])}" data-role="{esc(payload.get("role") or payload.get("target_role") or payload.get("requested_by_role"))}" '
            f'data-step="{esc(event.get("workflow_step"))}" data-result="{esc(payload.get("result") or payload.get("status"))}" '
            f'data-channel="{esc(event.get("channel_id"))}" data-delegation="{esc(event.get("delegation_id"))}">'
            f"<td>{esc(event['timestamp'])}</td>"
            f"<td>{badge(event['event_type'])}<br><small>{esc(event.get('message_type'))}</small></td>"
            f"<td>{esc(short(event.get('source_agent_id')))}<br><small>{esc(short(event.get('target_agent_id')))}</small></td>"
            f"<td>{esc(event.get('workflow_step'))}<br><small>{esc(event.get('delegation_id'))}</small></td>"
            f"<td>{esc(event.get('channel_id'))}</td>"
            f"<td>{esc(payload.get('summary') or payload.get('purpose') or payload.get('status') or payload.get('result'))}</td>"
            f"<td>{json_details('Payload', payload)}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Timestamp</th><th>Event</th><th>Source/Target</th><th>Step/Delegation</th>"
        f"<th>Channel</th><th>Summary</th><th>Payload</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def render_filter_options(events: list[dict], delegations: list[dict], transcripts: list[dict]) -> str:
    filters = {
        "eventType": sorted({event["event_type"] for event in events}),
        "role": sorted(
            {
                value
                for event in events
                for value in (
                    payload_value(event, "role"),
                    payload_value(event, "target_role"),
                    payload_value(event, "requested_by_role"),
                )
                if value
            }
            | {entry.get("role") for entry in transcripts if entry.get("role")}
        ),
        "step": sorted({event.get("workflow_step") for event in events if event.get("workflow_step")}),
        "result": sorted(
            {
                value
                for event in events
                for value in (payload_value(event, "result"), payload_value(event, "status"))
                if value
            }
        ),
        "channel": sorted(
            {event.get("channel_id") for event in events if event.get("channel_id")}
            | {entry.get("channel_id") for entry in transcripts if entry.get("channel_id")}
        ),
        "delegation": sorted({row["delegation_id"] for row in delegations}),
    }
    labels = {
        "eventType": "Event",
        "role": "Role",
        "step": "Step",
        "result": "Result",
        "channel": "Channel",
        "delegation": "Delegation",
    }
    rendered = ['<button class="chip active" type="button" data-filter-key="all" data-filter-value="">All</button>']
    for key, values in filters.items():
        for value in values:
            rendered.append(
                f'<button class="chip" type="button" data-filter-key="{key}" data-filter-value="{esc(value)}">{labels[key]}: {esc(value)}</button>'
            )
    return "".join(rendered)


def render_stats(summary: dict, violations: list[str]) -> str:
    stats = [
        ("Run", summary["run_id"]),
        ("Events", summary["events"]),
        ("Delegations", summary["delegations"]),
        ("Agents", summary["agents"]),
        ("Channels", summary["channels"]),
        ("Transcripts", summary["transcripts"]),
        ("Needs Attention", summary["attention"]),
        ("Policy Violations", len(violations)),
    ]
    return "".join(f'<div class="stat"><span>{esc(label)}</span><strong>{esc(value)}</strong></div>' for label, value in stats)


def build_html(
    title: str,
    log_path: Path,
    policy_path: Path,
    events: list[dict],
    transcripts: list[dict],
    delegations: list[dict],
    attention: list[dict],
    violations: list[str],
) -> str:
    runtime_mermaid = build_runtime_mermaid(events)
    logical_mermaid = build_logical_mermaid(events)
    connection_mermaid = build_connection_mermaid(delegations)
    summary = build_summary(events, delegations, transcripts, attention)
    gate_rows = build_gate_rows(delegations)
    event_counts = " ".join(
        f'<span class="token">{esc(event_type)}: {esc(count)}</span>'
        for event_type, count in sorted(summary["event_counts"].items())
    )
    status_counts = " ".join(
        f'<span class="token">{esc(status)}: {esc(count)}</span>'
        for status, count in sorted(summary["status_counts"].items())
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <style>
    :root {{
      --bg: #f8fafc;
      --surface: #ffffff;
      --surface-2: #f1f5f9;
      --ink: #0f172a;
      --muted: #475569;
      --line: #cbd5e1;
      --blue: #2563eb;
      --green: #15803d;
      --amber: #b45309;
      --red: #b91c1c;
      --radius: 8px;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Segoe UI", Arial, sans-serif; background: var(--bg); color: var(--ink); }}
    header {{ background: var(--surface); border-bottom: 1px solid var(--line); padding: 18px 24px; }}
    main {{ max-width: 1680px; margin: 0 auto; padding: 18px 18px 44px; }}
    h1 {{ margin: 0 0 6px; font-size: 1.65rem; line-height: 1.2; }}
    h2 {{ margin: 0 0 12px; font-size: 1.05rem; }}
    p {{ margin: 0; color: var(--muted); line-height: 1.5; }}
    code {{ background: var(--surface-2); border: 1px solid var(--line); border-radius: 6px; padding: 1px 5px; }}
    .topbar {{ position: sticky; top: 0; z-index: 20; background: rgba(248, 250, 252, 0.96); backdrop-filter: blur(10px); border-bottom: 1px solid var(--line); padding: 10px 18px; }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(145px, 1fr)); gap: 8px; max-width: 1680px; margin: 0 auto; }}
    .stat {{ background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 9px 10px; min-width: 0; }}
    .stat span {{ display: block; color: var(--muted); font-size: 0.74rem; text-transform: uppercase; }}
    .stat strong {{ display: block; margin-top: 3px; font-size: 0.95rem; overflow-wrap: anywhere; }}
    .toolbar {{ display: grid; gap: 10px; margin: 14px 0; }}
    .search {{ width: 100%; border: 1px solid var(--line); border-radius: var(--radius); padding: 11px 12px; font-size: 1rem; color: var(--ink); background: var(--surface); }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 7px; }}
    .chip, .copy-btn {{ border: 1px solid var(--line); background: var(--surface); color: var(--ink); border-radius: var(--radius); padding: 5px 8px; cursor: pointer; font-size: 0.82rem; }}
    .chip.active {{ background: var(--blue); border-color: var(--blue); color: white; }}
    section {{ background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); margin: 14px 0; padding: 14px; }}
    .section-meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }}
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--line); border-radius: var(--radius); }}
    table {{ width: 100%; border-collapse: collapse; min-width: 980px; }}
    th, td {{ text-align: left; vertical-align: top; border-bottom: 1px solid var(--line); padding: 8px; font-size: 0.88rem; }}
    th {{ background: var(--surface-2); color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; }}
    tr:last-child td {{ border-bottom: 0; }}
    small {{ color: var(--muted); }}
    pre {{ white-space: pre-wrap; overflow-x: auto; background: #0f172a; color: #e2e8f0; border-radius: var(--radius); padding: 10px; }}
    details summary {{ cursor: pointer; color: var(--blue); font-weight: 600; }}
    .json-details pre {{ max-width: 42rem; max-height: 28rem; }}
    .badge {{ display: inline-flex; align-items: center; border-radius: 999px; padding: 2px 7px; font-weight: 700; font-size: 0.76rem; border: 1px solid currentColor; }}
    .success {{ color: var(--green); background: #ecfdf5; }}
    .warning {{ color: var(--amber); background: #fffbeb; }}
    .danger {{ color: var(--red); background: #fef2f2; }}
    .neutral {{ color: #334155; background: #f1f5f9; }}
    .token {{ display: inline-flex; margin: 1px 3px 3px 0; padding: 2px 6px; border: 1px solid var(--line); border-radius: 999px; background: var(--surface-2); font-size: 0.78rem; }}
    .empty-state {{ color: var(--muted); background: var(--surface-2); border: 1px dashed var(--line); border-radius: var(--radius); padding: 14px; }}
    .diagram-grid {{ display: grid; grid-template-columns: 1fr; gap: 12px; }}
    .mermaid {{ background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 10px; min-width: 900px; }}
    .hidden-by-filter {{ display: none; }}
    @media (max-width: 720px) {{
      header {{ padding: 14px; }}
      main {{ padding: 12px; }}
      .topbar {{ padding: 8px 12px; }}
      h1 {{ font-size: 1.25rem; }}
      section {{ padding: 10px; }}
      table {{ min-width: 860px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{esc(title)}</h1>
    <p>Generated from <code>{esc(log_path)}</code>. Window: {esc(summary["first"])} to {esc(summary["last"])}. Policy: <code>{esc(policy_path)}</code>.</p>
  </header>
  <div class="topbar"><div class="stats">{render_stats(summary, violations)}</div></div>
  <main>
    <div class="toolbar">
      <input class="search" id="auditSearch" type="search" placeholder="Search events, agents, summaries, findings, artifacts, commands, transcripts...">
      <div class="chips" id="filterChips">{render_filter_options(events, delegations, transcripts)}</div>
    </div>
    <section>
      <h2>Audit Status</h2>
      <div class="section-meta">{status_counts or '<span class="token">No delegation statuses</span>'}</div>
      <div class="section-meta">{event_counts}</div>
      <div class="table-wrap">{render_attention(attention)}</div>
    </section>
    <section><h2>Delegation Evidence</h2><div class="table-wrap">{render_delegations(delegations)}</div></section>
    <section><h2>Gate Timeline</h2><div class="table-wrap">{render_gate_timeline(gate_rows)}</div></section>
    <section><h2>Transcript Evidence</h2><div class="table-wrap">{render_transcripts(transcripts)}</div></section>
    <section>
      <h2>Mermaid Diagrams</h2>
      <div class="diagram-grid">
        <details open><summary>Runtime Sequence</summary><div class="table-wrap"><pre class="mermaid">{esc(runtime_mermaid)}</pre></div>{json_details('Runtime source', runtime_mermaid)}</details>
        <details><summary>Logical Sequence</summary><div class="table-wrap"><pre class="mermaid">{esc(logical_mermaid)}</pre></div>{json_details('Logical source', logical_mermaid)}</details>
        <details><summary>Delegation Connections</summary><div class="table-wrap"><pre class="mermaid">{esc(connection_mermaid)}</pre></div>{json_details('Connection source', connection_mermaid)}</details>
      </div>
    </section>
    <section><h2>Raw Ledger</h2><div class="table-wrap">{render_raw_ledger(events)}</div></section>
  </main>
  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
    mermaid.initialize({{
      startOnLoad: true,
      theme: "base",
      securityLevel: "loose",
      themeVariables: {{
        primaryColor: "#ffffff",
        primaryTextColor: "#0f172a",
        primaryBorderColor: "#2563eb",
        lineColor: "#475569",
        actorBorder: "#2563eb",
        actorBkg: "#eff6ff",
        actorTextColor: "#0f172a",
        noteBkgColor: "#fffbeb",
        noteBorderColor: "#b45309"
      }}
    }});
  </script>
  <script>
    const search = document.querySelector("#auditSearch");
    const chips = document.querySelectorAll(".chip");
    const rows = () => Array.from(document.querySelectorAll(".filter-row"));
    let activeFilter = {{ key: "all", value: "" }};
    function normalize(value) {{ return (value || "").toString().toLowerCase(); }}
    function applyFilters() {{
      const query = normalize(search.value);
      rows().forEach((row) => {{
        const textMatch = normalize(row.dataset.search).includes(query);
        const filterMatch = activeFilter.key === "all" || normalize(row.dataset[activeFilter.key]).includes(normalize(activeFilter.value));
        row.classList.toggle("hidden-by-filter", !(textMatch && filterMatch));
      }});
    }}
    search.addEventListener("input", applyFilters);
    chips.forEach((chip) => {{
      chip.addEventListener("click", () => {{
        chips.forEach((item) => item.classList.remove("active"));
        chip.classList.add("active");
        activeFilter = {{ key: chip.dataset.filterKey, value: chip.dataset.filterValue }};
        applyFilters();
      }});
    }});
    document.addEventListener("click", async (event) => {{
      const button = event.target.closest("[data-copy]");
      if (!button) return;
      await navigator.clipboard.writeText(button.dataset.copy || "");
      const original = button.textContent;
      button.textContent = "Copied";
      setTimeout(() => {{ button.textContent = original; }}, 900);
    }});
  </script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Render an audit-first HTML Event Viewer from a workflow audit log.")
    parser.add_argument("--workflow-name", help="Workflow folder name under the configured audit root.")
    parser.add_argument("--config", help="Path to workflow.config.yaml for the target repository.")
    parser.add_argument("--audit-root", help="Override the audit root path from config.")
    parser.add_argument("--policy", help="Override workflow policy path.")
    parser.add_argument("--title", help="Optional HTML title.")
    args = parser.parse_args()

    audit_dir, workflow_name, _ = resolve_audit_dir(args.workflow_name, args.config, args.audit_root)
    log_path = audit_dir / "workflow_log.jsonl"
    channels_dir = audit_dir / "channels"
    html_path = audit_dir / "workflow_log.visualization.html"
    policy_path = Path(args.policy).resolve() if args.policy else Path(__file__).resolve().parent / "workflow_policy.yaml"

    events = load_events(log_path)
    transcripts = load_transcripts(channels_dir)
    delegations = build_delegation_rows(events, transcripts)
    attention, violations = find_attention_items(events, delegations, transcripts, policy_path)
    html_text = build_html(
        args.title or f"{workflow_name} Workflow Audit",
        log_path,
        policy_path,
        events,
        transcripts,
        delegations,
        attention,
        violations,
    )
    html_path.write_text(html_text, encoding="utf-8")

    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
