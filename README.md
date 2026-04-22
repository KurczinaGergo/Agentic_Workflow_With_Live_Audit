# Agentic Workflow With Live Audit

Reusable Codex workflow package for running implementation work through delegated agents with live, replayable audit evidence.

The workflow keeps the structure proven in WorkTrace2, but the package is language-neutral. A target repository can be .NET, JavaScript, Python, documentation-only, infrastructure, or anything else as long as it provides a small `workflow.config.yaml`.

## What This Gives You

- A full agentic workflow:
  - `MainContext`
  - Architect
  - SW Technical Engineer
  - Code Review
  - Unit Tester
  - Integration Test
  - Documenting
- Live audit logging with:
  - `workflow_log.jsonl`
  - pair-channel transcripts in `channels/*.jsonl`
  - runtime Mermaid diagram
  - logical Mermaid diagram
  - delegation report
  - static HTML audit viewer
  - optional live browser viewer
- Ready-to-use profiles:
  - `examples/generic-repo`
  - `examples/worktrace-style`
- A Codex skill under `skill/`.

## Install As A Codex Skill

Copy or link the `skill` folder into your Codex skills directory.

Example:

```powershell
Copy-Item -Recurse D:\Live_Audit_Log\skill $env:USERPROFILE\.codex\skills\agentic-workflow-audit
```

After that, ask Codex to use `agentic-workflow-audit` in a target repository.

## Add To A Repository

Choose a profile and copy it into the target repository:

```powershell
Copy-Item D:\Live_Audit_Log\examples\generic-repo\workflow.config.yaml .\workflow.config.yaml
```

For WorkTrace-style paths:

```powershell
Copy-Item D:\Live_Audit_Log\examples\worktrace-style\workflow.config.yaml .\workflow.config.yaml
```

Optional: copy the matching `AGENTS.example.md` content into the target repo's `AGENTS.md`.

## Configuration

Generic profile:

```yaml
workflow_name: FEATURE_V1
task_root: .workflow/tasks
dod_root: .workflow/dod
audit_root: .workflow/audit
architecture_docs: []
decision_docs: []
project_context_docs: []
test_commands: []
```

WorkTrace-style profile:

```yaml
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

All relative paths are resolved from the folder containing `workflow.config.yaml`.

## Start A Workflow Run

Initialize audit logging before spawning any workflow agents:

```powershell
python D:\Live_Audit_Log\skill\scripts\workflow-audit\init_workflow_audit.py --config workflow.config.yaml
```

Then ask Codex to run the workflow with the skill:

```text
Use agentic-workflow-audit for workflow FEATURE_V1. Implement the feature described in ...
```

The active Codex session is `MainContext`. It creates the Architect, creates private pair channels, observes all channels, and appends runtime/binding audit events.

## How The Workflow Works

The workflow separates runtime control from logical ownership.

`MainContext` owns runtime execution:

- spawns agents
- creates private pair channels
- writes `runtime.*` and `binding.*` events
- observes workflow state
- handles recovery
- bootstraps the Architect through a `main_context -> architect` delegation

The Architect owns logical delivery:

- reads repo context
- creates task files
- requests implementation delegations
- accepts task handoffs
- requests integration testing
- requests documentation updates

The SW Technical Engineer owns one implementation task:

- implements from a task file
- requests Code Review
- addresses review feedback
- requests Unit Tester validation
- writes the DoD/acceptance record

Reviewer and tester gates communicate directly with the engineer through private pair channels. The main session observes but does not speak as either agent inside those channels.

## Audit Model

The canonical audit stream is:

```text
<audit_root>/<workflow_name>/workflow_log.jsonl
```

Private channel transcripts live here:

```text
<audit_root>/<workflow_name>/channels/<channel_id>.jsonl
```

Important event families:

- `delegation.*`: logical work contracts
- `runtime.*`: spawned agents and private channels
- `binding.*`: links between delegations, runtime agents, and channels
- `logical.message.sent`: meaningful agent-to-agent communication
- `audit.protection.override`: developer-authorized protected skill or canonical audit maintenance

`delegation_id` is the primary trace key across events, channels, reports, and acceptance records.

Pre-bind `delegation.created` events are valid logical records, not placeholders. They may use `target_agent_id: null` only when `payload.requested_by_role`, `payload.target_role`, compatibility `payload.role`, and a created/pending status are present, and a later runtime binding resolves the same `delegation_id`. Later runtime, binding, logical message, and terminal events must set `target_agent_id`.

## Audit Source Of Truth

`workflow_log.jsonl` and `channels/*.jsonl` are append-only source-of-truth evidence. Workflow agents must not rewrite prior audit records or edit the `skill/` package during normal implementation work.

Generated artifacts such as Mermaid diagrams, delegation reports, and `workflow_log.visualization.html` are derived from the canonical JSONL ledger and may be regenerated.

Protected skill or canonical audit edits require explicit developer instruction and a prior `MainContext` `audit.protection.override` event with `payload.authorized_by: "developer"`, `payload.scope`, and a non-empty `payload.reason`.

## Generate Audit Artifacts

```powershell
$audit = ".workflow/audit/FEATURE_V1"
$tools = "D:\Live_Audit_Log\skill\scripts\workflow-audit"

python $tools\check_policy.py --policy $tools\workflow_policy.yaml --log $audit\workflow_log.jsonl
python $tools\generate_runtime_mermaid.py --log $audit\workflow_log.jsonl --out $audit\runtime_sequence.mmd
python $tools\generate_logical_mermaid.py --log $audit\workflow_log.jsonl --out $audit\logical_sequence.mmd
python $tools\generate_delegation_report.py --log $audit\workflow_log.jsonl --out $audit\delegation_report.txt
python $tools\render_workflow_html.py --config workflow.config.yaml
```

Open:

```text
<audit_root>/<workflow_name>/workflow_log.visualization.html
```

## Live Viewer

Run:

```powershell
python D:\Live_Audit_Log\skill\scripts\workflow-audit\serve_live_audit.py --config workflow.config.yaml --port 8765
```

Open:

```text
http://127.0.0.1:8765/
```

The live viewer streams appended workflow events and channel transcript messages.

## Validate This Repository

Run the audit tool tests:

```powershell
python -m unittest discover -s skill\scripts\workflow-audit -p "test_*.py"
```

## Important Rules

- Start audit logging before the first workflow spawn.
- Do not reconstruct new workflow logs after the run.
- Do not rewrite `workflow_log.jsonl` or `channels/*.jsonl` to fit an audit result.
- Do not edit `skill/` from a normal agentic workflow task.
- Implement from task files, not informal prompt text.
- Keep role-specific communication in private pair channels.
- Do not let non-main agents spawn other agents unless a role file explicitly allows it.
- Keep target-repo language, framework, and domain rules in `workflow.config.yaml`, repo docs, and task files.
