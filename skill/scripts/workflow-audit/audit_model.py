import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


TERMINAL_EVENT_TYPES = {"delegation.completed", "delegation.failed", "delegation.rejected"}


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
