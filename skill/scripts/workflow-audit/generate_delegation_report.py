import argparse
import json
from collections import defaultdict
from pathlib import Path


def load_events(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


parser = argparse.ArgumentParser()
parser.add_argument("--log", required=True)
parser.add_argument("--out", required=True)
args = parser.parse_args()

events = load_events(Path(args.log))

grouped = defaultdict(list)
created = {}
for event in events:
    delegation_id = event.get("delegation_id")
    if delegation_id:
        grouped[delegation_id].append(event)
        if event["event_type"] == "delegation.created":
            created[delegation_id] = event

lines = ["=== WORKFLOW DELEGATION REPORT ===", ""]

for delegation_id, created_event in created.items():
    delegation_events = grouped[delegation_id]
    runtime_agents = [
        event.get("target_agent_id")
        for event in delegation_events
        if event["event_type"] == "binding.delegation_runtime_agent"
    ]
    channels = [
        event.get("channel_id")
        for event in delegation_events
        if event["event_type"] == "binding.delegation_channel"
    ]
    terminal_events = [
        event.get("payload", {}).get("status")
        for event in delegation_events
        if event["event_type"] in {"delegation.completed", "delegation.failed", "delegation.rejected"}
    ]

    lines.append(f"- {delegation_id}")
    lines.append(f"  requester: {created_event.get('requested_by_agent_id')}")
    lines.append(f"  target_role: {created_event.get('payload', {}).get('target_role')}")
    lines.append(f"  workflow_step: {created_event.get('workflow_step')}")
    lines.append(f"  purpose: {created_event.get('payload', {}).get('purpose')}")
    lines.append(f"  runtime_agents: {runtime_agents}")
    lines.append(f"  channels: {channels}")
    lines.append(f"  terminal_status: {terminal_events[-1] if terminal_events else 'none'}")
    lines.append("")

Path(args.out).write_text("\n".join(lines), encoding="utf-8")
