import argparse
import json
from pathlib import Path

from audit_model import ensure_timestamp
from workflow_config import resolve_audit_dir


REQUIRED_KEYS = {
    "event_id",
    "run_id",
    "event_type",
    "source_agent_id",
    "target_agent_id",
    "runtime_parent_agent_id",
    "logical_parent_agent_id",
    "requested_by_agent_id",
    "delegation_id",
    "channel_id",
    "workflow_step",
    "message_type",
    "payload",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Append one live workflow audit event.")
    parser.add_argument("--workflow-name", help="Workflow folder name under the configured audit root.")
    parser.add_argument("--config", help="Path to workflow.config.yaml for the target repository.")
    parser.add_argument("--audit-root", help="Override the audit root path from config.")
    parser.add_argument("--event-json", help="Single JSON object matching the workflow event envelope.")
    parser.add_argument("--event-file", help="Path to a JSON file containing one workflow event object.")
    args = parser.parse_args()

    if bool(args.event_json) == bool(args.event_file):
        raise SystemExit("Provide exactly one of --event-json or --event-file")

    event_text = args.event_json
    if args.event_file:
        event_text = Path(args.event_file).read_text(encoding="utf-8")

    event = json.loads(event_text)
    event = ensure_timestamp(event)
    missing = sorted(REQUIRED_KEYS - set(event.keys()))
    if missing:
        raise SystemExit(f"Missing required event keys: {', '.join(missing)}")

    if not isinstance(event["payload"], dict):
        raise SystemExit("payload must be a JSON object")

    audit_dir, _, _ = resolve_audit_dir(args.workflow_name, args.config, args.audit_root)
    log_path = audit_dir / "workflow_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, separators=(",", ":")) + "\n")

    print(log_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
