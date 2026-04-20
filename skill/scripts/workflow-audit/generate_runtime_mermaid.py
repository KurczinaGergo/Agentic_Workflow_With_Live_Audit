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

participants = {"codex_main"}
for event in events:
    for key in ("source_agent_id", "target_agent_id", "runtime_parent_agent_id"):
        value = event.get(key)
        if value:
            participants.add(value)

lines = ["sequenceDiagram"]
for participant in sorted(participants):
    lines.append(f"participant {participant}")

for event in events:
    event_type = event["event_type"]
    source = event.get("source_agent_id") or "codex_main"
    target = event.get("target_agent_id")
    delegation_id = event.get("delegation_id")
    channel_id = event.get("channel_id")

    if event_type == "runtime.agent.spawned" and target:
        lines.append(f"{source}->>{target}: runtime spawn ({delegation_id})")
    elif event_type == "runtime.agent.terminated" and target:
        lines.append(f"{source}->>{target}: runtime terminate ({delegation_id})")
    elif event_type == "runtime.channel.created":
        lines.append(f"Note over {source}: create channel {channel_id} for {delegation_id}")
    elif event_type == "runtime.channel.closed":
        lines.append(f"Note over {source}: close channel {channel_id} for {delegation_id}")

Path(args.out).write_text("\n".join(lines), encoding="utf-8")
