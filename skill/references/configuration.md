# Configuration

The target repository controls paths and repo-specific context with `workflow.config.yaml`. Relative paths are resolved from the directory containing the config file.

## Minimal Generic Config

```yaml
# Copyable generic example:
# workflow_name: FEATURE_V1
# task_root: .workflow/tasks
# dod_root: .workflow/dod
# audit_root: .workflow/audit
# architecture_docs: []
# decision_docs: []
# project_context_docs: []
# test_commands: []

workflow_name: FEATURE_V1
task_root: .workflow/tasks
dod_root: .workflow/dod
audit_root: .workflow/audit
architecture_docs: []
decision_docs: []
project_context_docs: []
test_commands: []
```

## WorkTrace-Style Config

This profile mirrors the WorkTrace2 folder layout and is directly usable in repos that want that convention.

```yaml
# Copyable WorkTrace-style example:
# workflow_name: FEATURE_V1
# task_root: docs/tasks
# dod_root: docs/dod
# audit_root: docs/Audit
# architecture_docs: [docs/architecture.md]
# decision_docs: [docs/decisions]
# project_context_docs: [docs/project-documents]
# test_commands:
#   - dotnet test

workflow_name: FEATURE_V1
task_root: docs/tasks
dod_root: docs/dod
audit_root: docs/Audit
architecture_docs:
  - docs/architecture.md
decision_docs:
  - docs/decisions
project_context_docs:
  - docs/project-documents
test_commands: []
```

## Fields

- `workflow_name`: folder name and trace label for one workflow run.
- `task_root`: parent folder for task files.
- `dod_root`: parent folder for acceptance/DoD records.
- `audit_root`: parent folder for live audit logs and generated audit artifacts.
- `architecture_docs`: repo-specific architecture files or folders to read when work changes structure.
- `decision_docs`: repo-specific decision records.
- `project_context_docs`: domain, product, stack, or business-rule documents.
- `test_commands`: suggested verification commands for Engineer, Unit Tester, and Integration Test roles.
- `role_policy`: optional policy override path if the repo customizes role delegation rules.
- `artifact_naming`: optional naming conventions for task and DoD files.

## Script Path Resolution

The audit scripts accept:

```powershell
python <skill>/scripts/workflow-audit/init_workflow_audit.py --config workflow.config.yaml
python <skill>/scripts/workflow-audit/init_workflow_audit.py --workflow-name FEATURE_V1 --audit-root docs/Audit
```

Use `--config` for normal operation. Use direct flags for one-off tests or migration work.
