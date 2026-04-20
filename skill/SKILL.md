---
name: agentic-workflow-audit
description: Run a reusable multi-agent software delivery workflow with live audit logging, delegated Architect/Engineer/Review/Test/Integration/Documenting roles, private channel transcripts, policy validation, Mermaid diagrams, and HTML/live audit viewers. Use when a repository should implement work through an auditable agentic workflow, when the user asks to use the workflow/audit system, or when porting the workflow to another codebase.
---

# Agentic Workflow Audit

Use this skill to run the full audited workflow in any repository. The target repository must provide or accept a `workflow.config.yaml` adapter.

## Required First Steps

1. Read the target repo's `workflow.config.yaml`; if it does not exist, copy one from `assets/templates/` or `examples/`.
2. Read `references/runtime_protocol.md`.
3. Load only the role files needed for the current phase from `references/roles/`.
4. Initialize audit logging before spawning any workflow agent:

```powershell
python <skill>/scripts/workflow-audit/init_workflow_audit.py --config workflow.config.yaml
```

## Workflow

- Treat the current Codex session as `MainContext`.
- Spawn exactly one Architect for the workflow run.
- Have the Architect create task files under `task_root/<workflow_name>/`.
- Delegate each task through SW Technical Engineer.
- Require Engineer -> Code Review -> Engineer -> Unit Tester -> Engineer gates before Architect acceptance.
- Write acceptance/DoD records under `dod_root/<workflow_name>/`.
- Run Integration Test after all known tasks are accepted.
- Run Documenting if configured architecture, decision, or project docs need updates.

## Audit Discipline

- Append events live with `append_workflow_event.py`.
- Append pair-channel transcript entries live with `append_channel_message.py`.
- Use `delegation_id` as the primary trace key.
- Do not reconstruct new workflow logs after the fact.
- Generate artifacts at the end:

```powershell
python <skill>/scripts/workflow-audit/check_policy.py --policy <skill>/scripts/workflow-audit/workflow_policy.yaml --log <audit_root>/<workflow_name>/workflow_log.jsonl
python <skill>/scripts/workflow-audit/generate_runtime_mermaid.py --log <audit_root>/<workflow_name>/workflow_log.jsonl --out <audit_root>/<workflow_name>/runtime_sequence.mmd
python <skill>/scripts/workflow-audit/generate_logical_mermaid.py --log <audit_root>/<workflow_name>/workflow_log.jsonl --out <audit_root>/<workflow_name>/logical_sequence.mmd
python <skill>/scripts/workflow-audit/generate_delegation_report.py --log <audit_root>/<workflow_name>/workflow_log.jsonl --out <audit_root>/<workflow_name>/delegation_report.txt
python <skill>/scripts/workflow-audit/render_workflow_html.py --config workflow.config.yaml
```

## References

- `references/configuration.md`: config schema, profiles, and examples.
- `references/runtime_protocol.md`: event model, channels, roles, and canonical flow.
- `references/roles/architect.md`: Architect behavior.
- `references/roles/sw_technical_engineer.md`: implementation behavior.
- `references/roles/code_review.md`: review gate.
- `references/roles/unit_tester.md`: unit-test gate.
- `references/roles/integration_test.md`: integration gate.
- `references/roles/documenting.md`: documentation updates.
