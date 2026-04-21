# Runtime Protocol

This document defines the reusable runtime communication and logical audit contract for agentic workflow runs in any repository.

## Scope

- This is a documentation and audit contract, not a runtime ACL implementation.
- The main Codex session acts as `MainContext`, with logical role `main_context`.
- `MainContext` is the only entity allowed to spawn agents, create private channels, close private channels, and observe all workflow traffic.
- The default workflow roles are Architect, SW Technical Engineer, Code Review, Unit Tester, Integration Test, and Documenting.
- New audit artifacts live under the configured `audit_root/<workflow_name>/`.
- New workflow runs use `workflow_log.jsonl` as the canonical event stream.
- Task files live under `task_root/<workflow_name>/`.
- Acceptance or Definition of Done records live under `dod_root/<workflow_name>/`.
- Audit logging must begin before the first spawned workflow agent or private channel is created.
- `workflow_log.jsonl` and `channels/*.jsonl` must be written live as the workflow executes. Post-run reconstruction is not acceptable for new runs.
- Use the bundled `scripts/workflow-audit/` helpers when native runtime hooks are not available.

## Configuration

The target repository supplies `workflow.config.yaml`. Relative paths are resolved from the config file directory.

```yaml
# WorkTrace-style usable example:
# workflow_name: FEATURE_V1
# task_root: docs/tasks
# dod_root: docs/dod
# audit_root: docs/Audit
# architecture_docs: [docs/architecture.md]
# decision_docs: [docs/decisions]
# project_context_docs: [docs/project-documents]

workflow_name: FEATURE_V1
task_root: .workflow/tasks
dod_root: .workflow/dod
audit_root: .workflow/audit
architecture_docs: []
decision_docs: []
project_context_docs: []
test_commands: []
```

## Canonical Contracts

Use the bundled audit contracts:

- `scripts/workflow-audit/event_schema.json`
- `scripts/workflow-audit/delegation_contract.json`
- `scripts/workflow-audit/channel_contract.json`
- `scripts/workflow-audit/workflow_policy.yaml`

## Event Envelope

Each event in `workflow_log.jsonl` uses this envelope:

```json
{
  "event_id": "string",
  "run_id": "string",
  "timestamp": "string",
  "event_type": "string",
  "source_agent_id": "string|null",
  "target_agent_id": "string|null",
  "runtime_parent_agent_id": "string|null",
  "logical_parent_agent_id": "string|null",
  "requested_by_agent_id": "string|null",
  "delegation_id": "string|null",
  "channel_id": "string|null",
  "workflow_step": "string|null",
  "message_type": "string|null",
  "payload": {}
}
```

## Logical Identity Rules

- `runtime_parent_agent_id` tracks who owns the runtime spawn tree. In the default workflow this is `MainContext`.
- `logical_parent_agent_id` tracks the logical caller that owns the delegation branch.
- `requested_by_agent_id` identifies the agent that requested the delegation or gate.
- `delegation_id` is the primary traceability key across runtime events, logical messages, channel bindings, and reports.
- `workflow_label` remains human-facing metadata, but it is not the primary join key.

## Event Families

- `delegation.created`
- `delegation.completed`
- `delegation.failed`
- `delegation.rejected`
- `runtime.agent.spawned`
- `runtime.agent.terminated`
- `runtime.channel.created`
- `runtime.channel.closed`
- `binding.delegation_runtime_agent`
- `binding.delegation_channel`
- `logical.message.sent`

## Payload Conventions

Expected payload fields when applicable:

- `role`: runtime role, such as `architect`, `worker_programmer`, `code_reviewer`, `unit_test_agent`, `integration_test_agent`, or `documenting_agent`
- `workflow_label`: stable visible label such as `Task02`
- `channel_kind`: one of `architect_engineer`, `engineer_review`, `engineer_unit`, `architect_integration`, or `architect_documenting`
- `owners`: the two runtime agent ids that own the private channel
- `status`: lifecycle status such as `created`, `requested`, `completed`, `failed`, `rejected`, `blocked`, or `closed`
- `artifact_ref` or `artifact_refs`: task file, patch, report, DoD record, log, screenshot, or other evidence
- `result`: normalized outcome such as `accept`, `changes_requested`, `blocked`, `pass`, `fail`, or `skipped`
- `summary`: short human-readable summary
- `findings`: structured review or test findings
- `commands`: verification commands used for a gate
- `evidence_refs`: supporting reports, screenshots, logs, patches, or artifacts
- `attempt`: 1-based attempt count
- `blocker_key`: stable key for repeated unit-test blockers
- `acceptance_rationale`: required when a review, test, or handoff is accepted

## Channel Transcript Envelope

Each line in `channels/<channel_id>.jsonl` uses this envelope:

```json
{
  "message_id": "string",
  "run_id": "string",
  "timestamp": "string",
  "delegation_id": "string",
  "channel_id": "string",
  "channel_kind": "string",
  "workflow_label": "string",
  "source_agent_id": "string",
  "target_agent_id": "string|null",
  "role": "string",
  "message_type": "string",
  "body": "string",
  "artifact_refs": [],
  "related_event_id": "string|null"
}
```

## Default Policy Rules

- Only `MainContext` may emit `runtime.*` and `binding.*` events.
- `main_context` may delegate only to `architect`.
- Each `delegation.created` must include `requested_by_role`, `target_role`, `role` matching `target_role`, and `status` set to `created` or `pending_runtime_binding`.
- A pre-bind `delegation.created` may use `target_agent_id: null` only when it later receives a matching `binding.delegation_runtime_agent`.
- All later runtime, binding, logical message, and terminal events for that delegation must set `target_agent_id`; channel creation and channel binding events target the bound runtime agent.
- Each `delegation.created` must have `runtime.agent.spawned`, `binding.delegation_runtime_agent`, `runtime.channel.created`, and `binding.delegation_channel`.
- No valid logical message may exist without its parent delegation.
- Architect may delegate only to `worker_programmer`, `integration_test_agent`, and `documenting_agent`.
- SW Technical Engineer may delegate only to `code_reviewer` and `unit_test_agent`.
- Review and test child delegations must include workflow-level `logical.message.sent` request and result events, then complete before an implementation delegation completes successfully.
- Every delegation must end in `completed`, `failed`, or `rejected`.

## Canonical Flow

1. `MainContext` initializes the audit folder.
2. `MainContext` emits the Architect delegation when a workflow run is requested, using `requested_by_role: "main_context"` and `target_role: "architect"`.
3. The Architect creates task files under `task_root/<workflow_name>/`.
4. The Architect emits `delegation.created` for each implementation task.
5. `MainContext` spawns the engineer and binds the Architect<->Engineer channel.
6. The engineer implements the task and emits `implementation_result`.
7. The engineer requests Code Review, then Unit Tester, through direct pair channels.
8. The engineer returns to the Architect only after accepted review and accepted unit testing, or after the configured repeated-blocker path.
9. The engineer writes the acceptance/DoD record under `dod_root/<workflow_name>/`.
10. The Architect requests Integration Test after all known tasks are accepted.
11. The Architect requests Documenting if architecture or decision docs need updates.

## Derived Artifacts

For each run, generate:

- `runtime_sequence.mmd`
- `logical_sequence.mmd`
- `delegation_report.txt`
- `workflow_log.visualization.html`
- `channels/*.jsonl`
