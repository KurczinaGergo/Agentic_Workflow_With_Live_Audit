import argparse

from workflow_config import resolve_audit_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize a live workflow audit folder.")
    parser.add_argument("--workflow-name", help="Workflow folder name under the configured audit root.")
    parser.add_argument("--config", help="Path to workflow.config.yaml for the target repository.")
    parser.add_argument("--audit-root", help="Override the audit root path from config.")
    args = parser.parse_args()

    audit_dir, _, _ = resolve_audit_dir(args.workflow_name, args.config, args.audit_root)
    channels_dir = audit_dir / "channels"

    channels_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "workflow_log.jsonl").touch(exist_ok=True)

    print(audit_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
