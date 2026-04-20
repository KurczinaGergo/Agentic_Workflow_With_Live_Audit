# Agentic Workflow Instructions

Use the `agentic-workflow-audit` skill for implementation requests that name a workflow, SRS, issue, ticket, or feature package.

<!--
Copyable WorkTrace-style settings:

workflow_name: FEATURE_V1
task_root: docs/tasks
dod_root: docs/dod
audit_root: docs/Audit
architecture_docs: [docs/architecture.md]
decision_docs: [docs/decisions]
project_context_docs: [docs/project-documents]
-->

## Workflow Rules

- Treat the main Codex session as `MainContext`.
- Initialize `docs/Audit/<workflow_name>/` before the first workflow spawn.
- Keep `workflow_log.jsonl` plus `channels/*.jsonl` updated live.
- Spawn exactly one Architect workflow context.
- Have the Architect write task files under `docs/tasks/<workflow_name>/`.
- Delegate each task through SW Technical Engineer, Code Review, and Unit Tester gates.
- Write DoD records under `docs/dod/<workflow_name>/`.
- Run Integration Test before closing the workflow.
