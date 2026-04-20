# Agentic Workflow Instructions

Use the `agentic-workflow-audit` skill for implementation requests that should be auditable, delegated, reviewed, and tested.

<!--
Copyable generic settings:

workflow_name: FEATURE_V1
task_root: .workflow/tasks
dod_root: .workflow/dod
audit_root: .workflow/audit
architecture_docs: []
decision_docs: []
project_context_docs: []
-->

## Workflow Rules

- Treat the main Codex session as `MainContext`.
- Initialize `.workflow/audit/<workflow_name>/` before the first workflow spawn.
- Keep `workflow_log.jsonl` plus `channels/*.jsonl` updated live.
- Spawn exactly one Architect workflow context.
- Have the Architect write task files under `.workflow/tasks/<workflow_name>/`.
- Delegate each task through SW Technical Engineer, Code Review, and Unit Tester gates.
- Write acceptance/DoD records under `.workflow/dod/<workflow_name>/`.
- Run Integration Test before closing the workflow.
