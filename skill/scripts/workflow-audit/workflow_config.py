from pathlib import Path
from typing import Any

import yaml


DEFAULT_AUDIT_ROOT = ".workflow/audit"
DEFAULT_TASK_ROOT = ".workflow/tasks"
DEFAULT_DOD_ROOT = ".workflow/dod"


def load_config(config_path: str | None) -> tuple[dict[str, Any], Path]:
    if not config_path:
        return {}, Path.cwd()

    path = Path(config_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Workflow config not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Workflow config must be a mapping: {path}")

    return data, path.parent


def resolve_path(value: str | None, base_dir: Path) -> Path:
    if not value:
        raise ValueError("Cannot resolve an empty path")

    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def workflow_name_from_args(explicit: str | None, config: dict[str, Any]) -> str:
    workflow_name = explicit or config.get("workflow_name")
    if not workflow_name:
        raise ValueError("Provide --workflow-name or set workflow_name in the config file")
    return str(workflow_name)


def audit_root_from_args(explicit: str | None, config: dict[str, Any]) -> str:
    return str(explicit or config.get("audit_root") or DEFAULT_AUDIT_ROOT)


def resolve_audit_dir(
    workflow_name: str | None,
    config_path: str | None = None,
    audit_root: str | None = None,
) -> tuple[Path, str, dict[str, Any]]:
    config, base_dir = load_config(config_path)
    resolved_workflow_name = workflow_name_from_args(workflow_name, config)
    root = resolve_path(audit_root_from_args(audit_root, config), base_dir)
    return root / resolved_workflow_name, resolved_workflow_name, config


def resolve_artifact_roots(config_path: str | None) -> dict[str, Path]:
    config, base_dir = load_config(config_path)
    return {
        "task_root": resolve_path(str(config.get("task_root") or DEFAULT_TASK_ROOT), base_dir),
        "dod_root": resolve_path(str(config.get("dod_root") or DEFAULT_DOD_ROOT), base_dir),
        "audit_root": resolve_path(str(config.get("audit_root") or DEFAULT_AUDIT_ROOT), base_dir),
    }
