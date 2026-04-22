# Agentic Workflow Instructions

<!--
Copyable WorkTrace-style setup:

- Use the `agentic-workflow-audit` skill for project-development implementation requests that name a workflow, SRS, issue, ticket, or feature package.
- Use `workflow.config.yaml` for `workflow_name`, `task_root`, `dod_root`, `audit_root`, and repo context docs.
- Initialize audit logging before spawning the first workflow agent:
  `python <skill>/scripts/workflow-audit/init_workflow_audit.py --config workflow.config.yaml`
-->

## Required Workflow

- Treat the main Codex session as `MainContext`.
- `MainContext` is the only runtime control plane allowed to spawn agents, create private pair channels, observe private channels, retire stale workflow state, and surface outcomes.
- Spawn exactly one Architect workflow context for a workflow run.
- Have the Architect create task files under `task_root/<workflow_name>/` before implementation starts.
- Implementation must be traceable to task files, not informal prompt text.
- Each SW Technical Engineer task must follow: Engineer -> Code Review -> Engineer -> Unit Tester -> Engineer.
- Review and unit-test gates use direct private Engineer<->Reviewer and Engineer<->Unit channels created by `MainContext`.
- After task acceptance, write an acceptance/DoD record under `dod_root/<workflow_name>/`.
- When all known tasks are complete, the Architect requests Integration Test through `MainContext`.
- Keep `workflow_log.jsonl` and `channels/*.jsonl` updated live in `audit_root/<workflow_name>/`.
- Treat `workflow_log.jsonl` and `channels/*.jsonl` as append-only source-of-truth evidence.
- Do not edit prior audit records or `skill/` during a normal agentic workflow.
- Protected skill or canonical audit edits require an explicit developer instruction and a prior `MainContext` `audit.protection.override` event.
