import argparse
import json
from pathlib import Path


def load_events(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


parser = argparse.ArgumentParser()
parser.add_argument("--log", required=True)
parser.add_argument("--out", required=True)
args = parser.parse_args()

events = load_events(Path(args.log))

participants = set()
for event in events:
    for key in ("source_agent_id", "target_agent_id", "logical_parent_agent_id", "requested_by_agent_id"):
        value = event.get(key)
        if value and value != "codex_main":
            participants.add(value)

lines = ["sequenceDiagram"]
for participant in sorted(participants):
    lines.append(f"participant {participant}")

for event in events:
    event_type = event["event_type"]
    source = event.get("source_agent_id")
    target = event.get("target_agent_id")
    delegation_id = event.get("delegation_id")
    message_type = event.get("message_type")

    if event_type == "delegation.created":
        requester = event.get("requested_by_agent_id") or source
        target_role = event.get("payload", {}).get("target_role", "unknown_role")
        lines.append(f"Note over {requester}: create delegation {delegation_id} -> {target_role}")
    elif event_type == "logical.message.sent" and source and target:
        lines.append(f"{source}->>{target}: {message_type or event_type} ({delegation_id})")
    elif event_type in {"delegation.completed", "delegation.failed", "delegation.rejected"} and source and target:
        status = event.get("payload", {}).get("status", event_type)
        lines.append(f"{source}->>{target}: {status} ({delegation_id})")

Path(args.out).write_text("\n".join(lines), encoding="utf-8")
