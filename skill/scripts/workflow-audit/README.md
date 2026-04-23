# Workflow Audit Tools

Canonical workflow-audit contracts and generators for reusable agentic workflow runs.

## Scope

- These tools apply to new workflow runs only.
- The canonical event stream is `<audit_root>/<workflow_name>/workflow_log.jsonl`.
- Pair-channel transcripts are stored under `<audit_root>/<workflow_name>/channels/`.
- Canonical audit JSONL is append-only source-of-truth evidence.
- Generated Mermaid, report, and HTML files are derived artifacts that may be regenerated from the JSONL ledger.
- Relative paths in `workflow.config.yaml` are resolved from the config file directory.

## Files

- `event_schema.json`: top-level workflow event envelope.
- `delegation_contract.json`: logical delegation contract.
- `channel_contract.json`: pair-channel contract.
- `workflow_policy.yaml`: default delegation graph and policy rules.
- `workflow_config.py`: shared config and path resolver.
- `init_workflow_audit.py`: initializes audit folders.
- `append_workflow_event.py`: appends one live workflow event.
- `append_channel_message.py`: appends one live pair-channel transcript message.
- `check_policy.py`: validates a workflow log against the policy.
- `generate_runtime_mermaid.py`: renders a runtime-oriented Mermaid sequence diagram.
- `generate_logical_mermaid.py`: renders a logical delegation/message Mermaid sequence diagram.
- `generate_delegation_report.py`: writes a text summary grouped by `delegation_id`.
- `render_workflow_html.py`: renders the static audit-first Event Viewer.
- `serve_live_audit.py`: serves the live graph and replay viewer.
- `sample_log.jsonl`: golden-path sample log for reference and tests.

## Live Workflow Usage

Initialize the audit folder before spawning workflow agents:

```powershell
python skill/scripts/workflow-audit/init_workflow_audit.py --config workflow.config.yaml
```

Append events as they happen:

```powershell
python skill/scripts/workflow-audit/append_workflow_event.py --config workflow.config.yaml --event-json "{...}"
python skill/scripts/workflow-audit/append_channel_message.py --config workflow.config.yaml --message-json "{...}"
```

Direct path overrides are available for one-off runs:

```powershell
python skill/scripts/workflow-audit/init_workflow_audit.py --workflow-name FEATURE_V1 --audit-root docs/Audit
```

If an appended workflow event or channel message omits `timestamp`, the append helper fills the current UTC timestamp. Supplying explicit timestamps is preferred for deterministic replay tests.

Reconstruction is not acceptable for new runs. `workflow_log.jsonl` and `channels/*.jsonl` are expected to be append-only live artifacts written during execution.

Pre-bind `delegation.created` events are allowed only as complete logical records. Include `payload.requested_by_role`, `payload.target_role`, compatibility `payload.role` matching `target_role`, and `payload.status` set to `created` or `pending_runtime_binding`; the same `delegation_id` must later receive matching runtime-agent and channel bindings. Later runtime, binding, logical message, and terminal events must set `target_agent_id`.

Lifecycle classes follow `workflow_policy.yaml`: `main_context` is `run_persistent`, `architect` is `workflow_persistent`, and implementation, review, test, integration, and documentation roles are `ephemeral`.

After a terminal `delegation.completed`, `delegation.failed`, or `delegation.rejected`, append `runtime.channel.closed` for the delegation's bound channel. If the delegated role is `ephemeral`, append `runtime.agent.terminated` for the bound runtime agent after that terminal outcome as well. `workflow_persistent` Architect may stay active after delegation completion and is terminated only during final workflow shutdown; `run_persistent` `MainContext` stays active for the full run.

Do not rewrite prior `workflow_log.jsonl` or `channels/*.jsonl` records to fit an audit result. Failed audits must be fixed through implementation changes, follow-up tasks, or an explicit developer-authorized audit-maintenance task. Protected edits to `skill/` or canonical audit JSONL require a prior `audit.protection.override` event emitted by `MainContext` with `payload.authorized_by: "developer"`, `payload.scope`, and a non-empty `payload.reason`.

## Validation And Derived Artifacts

```powershell
python skill/scripts/workflow-audit/check_policy.py --policy skill/scripts/workflow-audit/workflow_policy.yaml --log <audit_root>/<workflow_name>/workflow_log.jsonl
python skill/scripts/workflow-audit/generate_runtime_mermaid.py --log <audit_root>/<workflow_name>/workflow_log.jsonl --out <audit_root>/<workflow_name>/runtime_sequence.mmd
python skill/scripts/workflow-audit/generate_logical_mermaid.py --log <audit_root>/<workflow_name>/workflow_log.jsonl --out <audit_root>/<workflow_name>/logical_sequence.mmd
python skill/scripts/workflow-audit/generate_delegation_report.py --log <audit_root>/<workflow_name>/workflow_log.jsonl --out <audit_root>/<workflow_name>/delegation_report.txt
python skill/scripts/workflow-audit/render_workflow_html.py --config workflow.config.yaml
```

## Event Viewer

`render_workflow_html.py` creates `workflow_log.visualization.html` from the canonical live event stream and pair-channel transcripts. The viewer includes run summary, policy attention items, delegation evidence, gate timeline, transcript evidence, Mermaid diagrams, and raw ledger details.

`check_policy.py` and the live viewer both surface lifecycle attention items when required follow-up events are missing or out of order, such as a terminal delegation without later `runtime.channel.closed`, an `ephemeral` delegated agent without later `runtime.agent.terminated`, or lifecycle binding events that appear after a terminal delegation record.

## Live Graph And Replay Viewer

Run a local live viewer while a workflow is active:

```powershell
python skill/scripts/workflow-audit/serve_live_audit.py --config workflow.config.yaml --port 8765
```

Open `http://127.0.0.1:8765/`. The server reads from `workflow_log.jsonl` and `channels/*.jsonl`, serves `/api/snapshot`, and streams appended records from `/api/events` with Server-Sent Events.

## Expected Outputs

Each audit folder should contain:

- `workflow_log.jsonl`
- `runtime_sequence.mmd`
- `logical_sequence.mmd`
- `delegation_report.txt`
- `workflow_log.visualization.html`
- `channels/`
