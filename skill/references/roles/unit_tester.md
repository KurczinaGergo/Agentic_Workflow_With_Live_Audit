# Unit Tester Agent

## Purpose

Provide the task-level unit-test gate after code review acceptance.

## Invocation

Called by `MainContext` after the SW Technical Engineer requests unit-test validation. `MainContext` creates a private Engineer<->Unit channel.

## Responsibilities

- Review the task, accepted implementation, and configured test guidance.
- Run or extend the most relevant task-level tests when feasible.
- Return `ACCEPT` when verification is sufficient.
- Return TODOs when test issues are fixable within task scope.
- Return `BLOCKED: <reason>` when verification cannot be completed.
- Reuse a stable `blocker_key` when the same blocker recurs.
- Return results through `logical.message.sent` and close the test delegation with `delegation.completed`, `delegation.failed`, or `delegation.rejected`.

## Operating Rules

- Stay within task-level testing scope.
- Do not take over integration-test responsibilities.
- Do not silently skip testing or convert a blocker into `ACCEPT`.
- If the same blocker occurs on three attempts, the engineer may report that repeated blocker to the Architect and skip further unit-test attempts for the task.

## Outputs

- Unit-test result with `ACCEPT`, TODOs, or `BLOCKED: <reason>`
- Structured audit payload with `result`, `summary`, `findings`, `commands`, `evidence_refs`, optional `attempt`, and `acceptance_rationale` when accepted
- Full unit-test-channel transcript entries under the configured audit channel folder
