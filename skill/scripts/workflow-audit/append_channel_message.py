import argparse
import json
from pathlib import Path

from audit_model import ensure_timestamp
from workflow_config import resolve_audit_dir


REQUIRED_KEYS = {
    "message_id",
    "run_id",
    "delegation_id",
    "channel_id",
    "channel_kind",
    "workflow_label",
    "source_agent_id",
    "target_agent_id",
    "role",
    "message_type",
    "body",
    "artifact_refs",
    "related_event_id",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Append one live workflow channel transcript entry.")
    parser.add_argument("--workflow-name", help="Workflow folder name under the configured audit root.")
    parser.add_argument("--config", help="Path to workflow.config.yaml for the target repository.")
    parser.add_argument("--audit-root", help="Override the audit root path from config.")
    parser.add_argument("--message-json", help="Single JSON object matching the channel transcript envelope.")
    parser.add_argument("--message-file", help="Path to a JSON file containing one channel transcript object.")
    args = parser.parse_args()

    if bool(args.message_json) == bool(args.message_file):
        raise SystemExit("Provide exactly one of --message-json or --message-file")

    message_text = args.message_json
    if args.message_file:
        message_text = Path(args.message_file).read_text(encoding="utf-8")

    message = json.loads(message_text)
    message = ensure_timestamp(message)
    missing = sorted(REQUIRED_KEYS - set(message.keys()))
    if missing:
        raise SystemExit(f"Missing required channel message keys: {', '.join(missing)}")

    if not isinstance(message["artifact_refs"], list):
        raise SystemExit("artifact_refs must be a JSON array")

    audit_dir, _, _ = resolve_audit_dir(args.workflow_name, args.config, args.audit_root)
    transcript_path = audit_dir / "channels" / f"{message['channel_id']}.jsonl"
    transcript_path.parent.mkdir(parents=True, exist_ok=True)

    with transcript_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(message, separators=(",", ":")) + "\n")

    print(transcript_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
