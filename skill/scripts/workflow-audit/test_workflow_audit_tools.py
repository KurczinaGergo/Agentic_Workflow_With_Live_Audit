import subprocess
import sys
import tempfile
import unittest
import shutil
import json
import socket
import time
import urllib.request
from pathlib import Path

from audit_model import derive_graph_state, sorted_timeline_items


ROOT = Path(__file__).resolve().parent
POLICY = ROOT / "workflow_policy.yaml"
SAMPLE = ROOT / "sample_log.jsonl"
CHECK_POLICY = ROOT / "check_policy.py"
RUNTIME_MERMAID = ROOT / "generate_runtime_mermaid.py"
LOGICAL_MERMAID = ROOT / "generate_logical_mermaid.py"
DELEGATION_REPORT = ROOT / "generate_delegation_report.py"
RENDER_HTML = ROOT / "render_workflow_html.py"
APPEND_EVENT = ROOT / "append_workflow_event.py"
APPEND_CHANNEL = ROOT / "append_channel_message.py"
INIT_AUDIT = ROOT / "init_workflow_audit.py"
LIVE_SERVER = ROOT / "serve_live_audit.py"
REPO_ROOT = ROOT.parents[2]
AUDIT_ROOT = REPO_ROOT / ".workflow" / "audit"


def run_python(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def write_log(lines: list[str]) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="workflow-audit-"))
    log_path = temp_dir / "workflow_log.jsonl"
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log_path


def sample_events() -> list[dict]:
    return [json.loads(line) for line in SAMPLE.read_text(encoding="utf-8").splitlines() if line.strip()]


def protection_override_event(source_agent_id: str = "codex_main", scope: str = "skill") -> dict:
    return {
        "event_id": f"evt_override_{scope}_{source_agent_id}",
        "run_id": "run_demo_001",
        "timestamp": "2026-04-10T15:00:30Z",
        "event_type": "audit.protection.override",
        "source_agent_id": source_agent_id,
        "target_agent_id": None,
        "runtime_parent_agent_id": "codex_main",
        "logical_parent_agent_id": "codex_main",
        "requested_by_agent_id": "codex_main",
        "delegation_id": None,
        "channel_id": None,
        "workflow_step": None,
        "message_type": None,
        "payload": {
            "authorized_by": "developer",
            "scope": scope,
            "reason": "Developer explicitly instructed this workflow to update protected audit assets.",
        },
    }


def write_events(events: list[dict]) -> Path:
    return write_log([json.dumps(event) for event in events])


def architect_lifecycle_events(include_termination: bool = False, include_close: bool = False) -> list[dict]:
    events = [
        {
            "event_id": "evt_arch_created",
            "run_id": "run_arch",
            "timestamp": "2026-04-17T10:00:00Z",
            "event_type": "delegation.created",
            "source_agent_id": "MainContext",
            "target_agent_id": "architect_1",
            "runtime_parent_agent_id": "MainContext",
            "logical_parent_agent_id": "MainContext",
            "requested_by_agent_id": "MainContext",
            "delegation_id": "del_arch",
            "channel_id": None,
            "workflow_step": "architecture",
            "message_type": "task_request",
            "payload": {
                "requested_by_role": "main_context",
                "target_role": "architect",
                "role": "architect",
                "status": "created",
            },
        },
        {
            "event_id": "evt_arch_spawned",
            "run_id": "run_arch",
            "timestamp": "2026-04-17T10:00:01Z",
            "event_type": "runtime.agent.spawned",
            "source_agent_id": "MainContext",
            "target_agent_id": "architect_1",
            "runtime_parent_agent_id": "MainContext",
            "logical_parent_agent_id": "MainContext",
            "requested_by_agent_id": "MainContext",
            "delegation_id": "del_arch",
            "channel_id": None,
            "workflow_step": "architecture",
            "message_type": None,
            "payload": {"role": "architect"},
        },
        {
            "event_id": "evt_arch_bound",
            "run_id": "run_arch",
            "timestamp": "2026-04-17T10:00:02Z",
            "event_type": "binding.delegation_runtime_agent",
            "source_agent_id": "MainContext",
            "target_agent_id": "architect_1",
            "runtime_parent_agent_id": "MainContext",
            "logical_parent_agent_id": "MainContext",
            "requested_by_agent_id": "MainContext",
            "delegation_id": "del_arch",
            "channel_id": None,
            "workflow_step": "architecture",
            "message_type": None,
            "payload": {"role": "architect"},
        },
        {
            "event_id": "evt_arch_channel",
            "run_id": "run_arch",
            "timestamp": "2026-04-17T10:00:03Z",
            "event_type": "runtime.channel.created",
            "source_agent_id": "MainContext",
            "target_agent_id": "architect_1",
            "runtime_parent_agent_id": "MainContext",
            "logical_parent_agent_id": "MainContext",
            "requested_by_agent_id": "MainContext",
            "delegation_id": "del_arch",
            "channel_id": "ch_main_arch",
            "workflow_step": "architecture",
            "message_type": None,
            "payload": {"owners": ["MainContext", "architect_1"]},
        },
        {
            "event_id": "evt_arch_channel_bound",
            "run_id": "run_arch",
            "timestamp": "2026-04-17T10:00:04Z",
            "event_type": "binding.delegation_channel",
            "source_agent_id": "MainContext",
            "target_agent_id": "architect_1",
            "runtime_parent_agent_id": "MainContext",
            "logical_parent_agent_id": "MainContext",
            "requested_by_agent_id": "MainContext",
            "delegation_id": "del_arch",
            "channel_id": "ch_main_arch",
            "workflow_step": "architecture",
            "message_type": None,
            "payload": {},
        },
        {
            "event_id": "evt_arch_completed",
            "run_id": "run_arch",
            "timestamp": "2026-04-17T10:00:05Z",
            "event_type": "delegation.completed",
            "source_agent_id": "architect_1",
            "target_agent_id": "MainContext",
            "runtime_parent_agent_id": "MainContext",
            "logical_parent_agent_id": "MainContext",
            "requested_by_agent_id": "MainContext",
            "delegation_id": "del_arch",
            "channel_id": "ch_main_arch",
            "workflow_step": "architecture",
            "message_type": "verdict",
            "payload": {"status": "completed"},
        },
        {
            "event_id": "evt_arch_channel_closed",
            "run_id": "run_arch",
            "timestamp": "2026-04-17T10:00:05.500000Z",
            "event_type": "runtime.channel.closed",
            "source_agent_id": "MainContext",
            "target_agent_id": "architect_1",
            "runtime_parent_agent_id": "MainContext",
            "logical_parent_agent_id": "MainContext",
            "requested_by_agent_id": "MainContext",
            "delegation_id": "del_arch",
            "channel_id": "ch_main_arch",
            "workflow_step": "architecture",
            "message_type": None,
            "payload": {"ended_reason": "architecture delegation completed"},
        },
    ]
    if include_termination:
        events.append(
            {
                "event_id": "evt_arch_terminated",
                "run_id": "run_arch",
                "timestamp": "2026-04-17T10:00:06Z",
                "event_type": "runtime.agent.terminated",
                "source_agent_id": "MainContext",
                "target_agent_id": "architect_1",
                "runtime_parent_agent_id": "MainContext",
                "logical_parent_agent_id": "MainContext",
                "requested_by_agent_id": "MainContext",
                "delegation_id": "del_arch",
                "channel_id": None,
                "workflow_step": "architecture",
                "message_type": None,
                "payload": {"ended_reason": "workflow shutdown"},
            }
        )
    if include_close:
        events.append(
            {
                "event_id": "evt_workflow_closed",
                "run_id": "run_arch",
                "timestamp": "2026-04-17T10:00:07Z",
                "event_type": "workflow.closed",
                "source_agent_id": "MainContext",
                "target_agent_id": None,
                "runtime_parent_agent_id": "MainContext",
                "logical_parent_agent_id": "MainContext",
                "requested_by_agent_id": "MainContext",
                "delegation_id": None,
                "channel_id": None,
                "workflow_step": "workflow_close",
                "message_type": None,
                "payload": {"status": "closed"},
            }
        )
    return events


def write_audit_workflow(name: str, lines: list[str], transcript_lines: list[str] | None = None) -> Path:
    audit_dir = AUDIT_ROOT / name
    if audit_dir.exists():
        shutil.rmtree(audit_dir)
    (audit_dir / "channels").mkdir(parents=True)
    (audit_dir / "workflow_log.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if transcript_lines:
        (audit_dir / "channels" / "sample-channel.jsonl").write_text(
            "\n".join(transcript_lines) + "\n",
            encoding="utf-8",
        )
    return audit_dir


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_json(url: str, timeout_seconds: float = 5.0) -> dict:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover - diagnostic carried in assertion
            last_error = exc
            time.sleep(0.1)
    raise AssertionError(f"Timed out waiting for {url}: {last_error}")


class WorkflowAuditToolsTests(unittest.TestCase):
    def test_golden_path_policy_passes(self) -> None:
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(SAMPLE))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Violations: none", result.stdout)

    def test_missing_review_result_fails(self) -> None:
        lines = SAMPLE.read_text(encoding="utf-8").splitlines()
        filtered = [line for line in lines if '"event_id": "evt_013"' not in line and '"event_id": "evt_014"' not in line]
        log_path = write_log(filtered)
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("review", result.stdout.lower())

    def test_missing_test_result_fails(self) -> None:
        lines = SAMPLE.read_text(encoding="utf-8").splitlines()
        filtered = [line for line in lines if '"event_id": "evt_021"' not in line and '"event_id": "evt_022"' not in line]
        log_path = write_log(filtered)
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("test", result.stdout.lower())

    def test_invalid_delegation_fails(self) -> None:
        lines = SAMPLE.read_text(encoding="utf-8").splitlines()
        invalid_line = lines[6].replace('"target_role": "code_reviewer"', '"target_role": "worker_programmer"')
        lines[6] = invalid_line
        log_path = write_log(lines)
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("forbidden logical delegation", result.stdout)

    def test_prebind_delegation_requires_target_role(self) -> None:
        events = sample_events()
        del events[6]["payload"]["target_role"]
        log_path = write_events(events)
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing payload.target_role", result.stdout)

    def test_prebind_delegation_requires_requested_by_role(self) -> None:
        events = sample_events()
        del events[6]["payload"]["requested_by_role"]
        log_path = write_events(events)
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing payload.requested_by_role", result.stdout)

    def test_prebind_delegation_requires_later_runtime_binding(self) -> None:
        events = [
            event
            for event in sample_events()
            if not (event["delegation_id"] == "del_review_001" and event["event_type"] == "binding.delegation_runtime_agent")
        ]
        log_path = write_events(events)
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pre-bind delegation missing runtime agent binding", result.stdout)

    def test_prebind_delegation_requires_matching_bound_role(self) -> None:
        events = sample_events()
        binding = next(
            event
            for event in events
            if event["delegation_id"] == "del_review_001"
            and event["event_type"] == "binding.delegation_runtime_agent"
        )
        binding["payload"]["role"] = "unit_test_agent"
        log_path = write_events(events)
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("runtime binding role mismatch", result.stdout)

    def test_runtime_target_required_event_cannot_have_null_target_agent(self) -> None:
        events = sample_events()
        spawned = next(
            event
            for event in events
            if event["delegation_id"] == "del_review_001"
            and event["event_type"] == "runtime.agent.spawned"
        )
        spawned["target_agent_id"] = None
        log_path = write_events(events)
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("runtime.agent.spawned requires target_agent_id", result.stdout)

    def test_protected_skill_artifact_ref_fails_without_override(self) -> None:
        events = sample_events()
        events[5]["payload"]["artifact_refs"] = ["skill/SKILL.md"]
        log_path = write_events(events)
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("protected skill path changed without developer override", result.stdout)

    def test_protected_audit_log_artifact_ref_fails_without_override(self) -> None:
        events = sample_events()
        events[5]["payload"]["artifact_refs"] = [".workflow/audit/FEATURE_V1/workflow_log.jsonl"]
        log_path = write_events(events)
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("canonical audit log rewrite attempted without developer override", result.stdout)

    def test_protected_channel_artifact_ref_fails_without_override(self) -> None:
        events = sample_events()
        events[5]["payload"]["artifact_refs"] = [".workflow/audit/FEATURE_V1/channels/ch-worker.jsonl"]
        log_path = write_events(events)
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("canonical audit log rewrite attempted without developer override", result.stdout)

    def test_protected_artifact_refs_pass_with_main_context_developer_override(self) -> None:
        events = [protection_override_event(scope="skill"), *sample_events()]
        events[6]["payload"]["artifact_refs"] = ["skill/SKILL.md"]
        log_path = write_events(events)
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_protection_override_from_non_main_context_fails(self) -> None:
        events = [protection_override_event(source_agent_id="worker_1", scope="skill"), *sample_events()]
        events[6]["payload"]["artifact_refs"] = ["skill/SKILL.md"]
        log_path = write_events(events)
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("protection override must be emitted by MainContext", result.stdout)

    def test_derived_audit_artifact_ref_is_allowed_without_override(self) -> None:
        events = sample_events()
        events[5]["payload"]["artifact_refs"] = [".workflow/audit/FEATURE_V1/workflow_log.visualization.html"]
        log_path = write_events(events)
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_protected_transcript_artifact_ref_fails_without_override(self) -> None:
        workflow_name = "_TEST_PROTECTED_TRANSCRIPT_REF"
        transcript = (
            '{"message_id": "msg_protected", "run_id": "run_demo_001", "timestamp": "2026-04-10T15:01:05Z", '
            '"delegation_id": "del_impl_001", "channel_id": "ch_architect_worker_1", '
            '"channel_kind": "architect_engineer", "workflow_label": "Task01", '
            '"source_agent_id": "worker_1", "target_agent_id": "architect_1", "role": "worker_programmer", '
            '"message_type": "implementation_result", "body": "Implementation completed.", '
            '"artifact_refs": ["skill/SKILL.md"], "related_event_id": "evt_006"}'
        )
        audit_dir = write_audit_workflow(workflow_name, SAMPLE.read_text(encoding="utf-8").splitlines(), [transcript])
        try:
            result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(audit_dir / "workflow_log.jsonl"))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("protected skill path changed without developer override", result.stdout)
        finally:
            shutil.rmtree(audit_dir, ignore_errors=True)

    def test_architect_bootstrap_from_main_context_passes(self) -> None:
        events = [
            {
                "event_id": "evt_boot_001",
                "run_id": "run_bootstrap",
                "timestamp": "2026-04-21T10:00:00Z",
                "event_type": "delegation.created",
                "source_agent_id": "codex_main",
                "target_agent_id": None,
                "runtime_parent_agent_id": "codex_main",
                "logical_parent_agent_id": "codex_main",
                "requested_by_agent_id": "codex_main",
                "delegation_id": "del_architect_001",
                "channel_id": None,
                "workflow_step": "architecture",
                "message_type": "task_request",
                "payload": {
                    "requested_by_role": "main_context",
                    "target_role": "architect",
                    "role": "architect",
                    "purpose": "Bootstrap the workflow architect",
                    "status": "pending_runtime_binding",
                },
            },
            {
                "event_id": "evt_boot_002",
                "run_id": "run_bootstrap",
                "timestamp": "2026-04-21T10:00:01Z",
                "event_type": "runtime.agent.spawned",
                "source_agent_id": "codex_main",
                "target_agent_id": "architect_1",
                "runtime_parent_agent_id": "codex_main",
                "logical_parent_agent_id": "codex_main",
                "requested_by_agent_id": "codex_main",
                "delegation_id": "del_architect_001",
                "channel_id": None,
                "workflow_step": "architecture",
                "message_type": None,
                "payload": {"role": "architect"},
            },
            {
                "event_id": "evt_boot_003",
                "run_id": "run_bootstrap",
                "timestamp": "2026-04-21T10:00:02Z",
                "event_type": "binding.delegation_runtime_agent",
                "source_agent_id": "codex_main",
                "target_agent_id": "architect_1",
                "runtime_parent_agent_id": "codex_main",
                "logical_parent_agent_id": "codex_main",
                "requested_by_agent_id": "codex_main",
                "delegation_id": "del_architect_001",
                "channel_id": None,
                "workflow_step": "architecture",
                "message_type": None,
                "payload": {"role": "architect"},
            },
            {
                "event_id": "evt_boot_004",
                "run_id": "run_bootstrap",
                "timestamp": "2026-04-21T10:00:03Z",
                "event_type": "runtime.channel.created",
                "source_agent_id": "codex_main",
                "target_agent_id": "architect_1",
                "runtime_parent_agent_id": "codex_main",
                "logical_parent_agent_id": "codex_main",
                "requested_by_agent_id": "codex_main",
                "delegation_id": "del_architect_001",
                "channel_id": "ch_main_architect_1",
                "workflow_step": "architecture",
                "message_type": None,
                "payload": {"owners": ["codex_main", "architect_1"]},
            },
            {
                "event_id": "evt_boot_005",
                "run_id": "run_bootstrap",
                "timestamp": "2026-04-21T10:00:04Z",
                "event_type": "binding.delegation_channel",
                "source_agent_id": "codex_main",
                "target_agent_id": "architect_1",
                "runtime_parent_agent_id": "codex_main",
                "logical_parent_agent_id": "codex_main",
                "requested_by_agent_id": "codex_main",
                "delegation_id": "del_architect_001",
                "channel_id": "ch_main_architect_1",
                "workflow_step": "architecture",
                "message_type": None,
                "payload": {},
            },
            {
                "event_id": "evt_boot_006",
                "run_id": "run_bootstrap",
                "timestamp": "2026-04-21T10:00:05Z",
                "event_type": "delegation.completed",
                "source_agent_id": "architect_1",
                "target_agent_id": "codex_main",
                "runtime_parent_agent_id": "codex_main",
                "logical_parent_agent_id": "codex_main",
                "requested_by_agent_id": "codex_main",
                "delegation_id": "del_architect_001",
                "channel_id": "ch_main_architect_1",
                "workflow_step": "architecture",
                "message_type": "verdict",
                "payload": {"status": "completed"},
            },
            {
                "event_id": "evt_boot_007",
                "run_id": "run_bootstrap",
                "timestamp": "2026-04-21T10:00:06Z",
                "event_type": "runtime.channel.closed",
                "source_agent_id": "codex_main",
                "target_agent_id": "architect_1",
                "runtime_parent_agent_id": "codex_main",
                "logical_parent_agent_id": "codex_main",
                "requested_by_agent_id": "codex_main",
                "delegation_id": "del_architect_001",
                "channel_id": "ch_main_architect_1",
                "workflow_step": "architecture",
                "message_type": None,
                "payload": {"ended_reason": "architecture delegation completed"},
            },
        ]
        log_path = write_events(events)
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_terminal_status_fails(self) -> None:
        lines = SAMPLE.read_text(encoding="utf-8").splitlines()
        filtered = [line for line in lines if '"event_id": "evt_023"' not in line]
        log_path = write_log(filtered)
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no terminal delegation event found", result.stdout)

    def test_missing_runtime_agent_termination_fails(self) -> None:
        events = [event for event in sample_events() if event["event_id"] != "evt_026"]
        log_path = write_events(events)
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing runtime.agent.terminated for bound agent 'worker_1'", result.stdout)

    def test_runtime_agent_termination_must_target_bound_agent(self) -> None:
        events = sample_events()
        termination = next(event for event in events if event["event_id"] == "evt_026")
        termination["target_agent_id"] = "reviewer_1"
        log_path = write_events(events)
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing runtime.agent.terminated for bound agent 'worker_1'", result.stdout)

    def test_runtime_agent_termination_must_follow_terminal_event(self) -> None:
        events = sample_events()
        termination_index = next(index for index, event in enumerate(events) if event["event_id"] == "evt_026")
        termination = events.pop(termination_index)
        terminal_index = next(index for index, event in enumerate(events) if event["event_id"] == "evt_023")
        events.insert(terminal_index, termination)
        log_path = write_events(events)
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing runtime.agent.terminated for bound agent 'worker_1'", result.stdout)

    def test_missing_channel_close_fails(self) -> None:
        events = [event for event in sample_events() if event["event_id"] != "evt_029"]
        log_path = write_events(events)
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing runtime.channel.closed for bound channel 'ch_architect_worker_1'", result.stdout)

    def test_terminal_only_delegation_id_fails(self) -> None:
        events = sample_events()
        events.append(
            {
                "event_id": "evt_terminal_only",
                "run_id": "run_demo_001",
                "timestamp": "2026-04-10T15:03:00Z",
                "event_type": "delegation.completed",
                "source_agent_id": "reviewer_orphan",
                "target_agent_id": "worker_1",
                "runtime_parent_agent_id": "codex_main",
                "logical_parent_agent_id": "worker_1",
                "requested_by_agent_id": "worker_1",
                "delegation_id": "del_orphan_review",
                "channel_id": "ch_orphan_review",
                "workflow_step": "review",
                "message_type": "review_result",
                "payload": {"status": "completed", "role": "code_reviewer"},
            }
        )
        log_path = write_events(events)
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("terminal delegation event without delegation.created", result.stdout)

    def test_terminal_source_must_match_bound_runtime_agent(self) -> None:
        events = sample_events()
        terminal = next(event for event in events if event["event_id"] == "evt_014")
        terminal["source_agent_id"] = "wrong_reviewer"
        log_path = write_events(events)
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match bound runtime agent 'reviewer_1'", result.stdout)

    def test_lifecycle_event_after_terminal_fails(self) -> None:
        events = sample_events()
        spawn_index = next(index for index, event in enumerate(events) if event["event_id"] == "evt_008")
        spawned = events.pop(spawn_index)
        terminal_index = next(index for index, event in enumerate(events) if event["event_id"] == "evt_014")
        events.insert(terminal_index + 1, spawned)
        log_path = write_events(events)
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("runtime.agent.spawned appears after terminal delegation event", result.stdout)

    def test_architect_may_remain_active_after_planning_completion(self) -> None:
        log_path = write_events(architect_lifecycle_events())
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_workflow_close_requires_architect_termination(self) -> None:
        log_path = write_events(architect_lifecycle_events(include_close=True))
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("workflow close requires runtime.agent.terminated for architect", result.stdout)

    def test_architect_termination_satisfies_workflow_close(self) -> None:
        log_path = write_events(architect_lifecycle_events(include_termination=True, include_close=True))
        result = run_python(str(CHECK_POLICY), "--policy", str(POLICY), "--log", str(log_path))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_generators_create_outputs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workflow-audit-out-") as temp_dir:
            temp_path = Path(temp_dir)
            runtime_out = temp_path / "runtime_sequence.mmd"
            logical_out = temp_path / "logical_sequence.mmd"
            report_out = temp_path / "delegation_report.txt"

            runtime_result = run_python(str(RUNTIME_MERMAID), "--log", str(SAMPLE), "--out", str(runtime_out))
            logical_result = run_python(str(LOGICAL_MERMAID), "--log", str(SAMPLE), "--out", str(logical_out))
            report_result = run_python(str(DELEGATION_REPORT), "--log", str(SAMPLE), "--out", str(report_out))

            self.assertEqual(runtime_result.returncode, 0, runtime_result.stdout + runtime_result.stderr)
            self.assertEqual(logical_result.returncode, 0, logical_result.stdout + logical_result.stderr)
            self.assertEqual(report_result.returncode, 0, report_result.stdout + report_result.stderr)

            self.assertTrue(runtime_out.exists())
            self.assertTrue(logical_out.exists())
            self.assertTrue(report_out.exists())
            self.assertIn("sequenceDiagram", runtime_out.read_text(encoding="utf-8"))
            self.assertIn("sequenceDiagram", logical_out.read_text(encoding="utf-8"))
            self.assertIn("WORKFLOW DELEGATION REPORT", report_out.read_text(encoding="utf-8"))

    def test_init_uses_worktrace_style_config_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workflow-config-") as temp_dir:
            repo = Path(temp_dir)
            config = repo / "workflow.config.yaml"
            config.write_text(
                "\n".join(
                    [
                        "workflow_name: SAMPLE_WORK",
                        "task_root: docs/tasks",
                        "dod_root: docs/dod",
                        "audit_root: docs/Audit",
                        "architecture_docs: [docs/architecture.md]",
                        "decision_docs: [docs/decisions]",
                        "project_context_docs: [docs/project-documents]",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_python(str(INIT_AUDIT), "--config", str(config))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((repo / "docs" / "Audit" / "SAMPLE_WORK" / "workflow_log.jsonl").exists())
            self.assertTrue((repo / "docs" / "Audit" / "SAMPLE_WORK" / "channels").exists())

    def test_append_and_render_use_configured_audit_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workflow-config-") as temp_dir:
            repo = Path(temp_dir)
            config = repo / "workflow.config.yaml"
            config.write_text("workflow_name: GENERIC_WORK\naudit_root: .workflow/audit\n", encoding="utf-8")
            event_file = repo / "event.json"
            event_file.write_text(
                json.dumps(
                    {
                        "event_id": "evt_config_001",
                        "run_id": "run_config",
                        "event_type": "runtime.agent.spawned",
                        "source_agent_id": "MainContext",
                        "target_agent_id": "worker_1",
                        "runtime_parent_agent_id": "MainContext",
                        "logical_parent_agent_id": "MainContext",
                        "requested_by_agent_id": "MainContext",
                        "delegation_id": "del_config_001",
                        "channel_id": None,
                        "workflow_step": "implementation",
                        "message_type": None,
                        "payload": {"role": "worker_programmer"},
                    }
                ),
                encoding="utf-8",
            )

            result = run_python(str(APPEND_EVENT), "--config", str(config), "--event-file", str(event_file))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            log_path = repo / ".workflow" / "audit" / "GENERIC_WORK" / "workflow_log.jsonl"
            self.assertTrue(log_path.exists())

            result = run_python(str(RENDER_HTML), "--config", str(config))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            html_path = repo / ".workflow" / "audit" / "GENERIC_WORK" / "workflow_log.visualization.html"
            self.assertTrue(html_path.exists())

    def test_render_html_creates_audit_first_event_viewer(self) -> None:
        workflow_name = "_TEST_RENDER_EVENT_VIEWER"
        transcript = (
            '{"message_id": "msg_evt_006", "run_id": "run_demo_001", "timestamp": "2026-04-10T15:01:05Z", '
            '"delegation_id": "del_impl_001", "channel_id": "ch_architect_worker_1", '
            '"channel_kind": "architect_engineer", "workflow_label": "Task01", '
            '"source_agent_id": "worker_1", "target_agent_id": "architect_1", "role": "worker_programmer", '
            '"message_type": "implementation_result", "body": "Implementation completed with audit evidence.", '
            '"artifact_refs": ["patch_001"], "related_event_id": "evt_006"}'
        )
        audit_dir = write_audit_workflow(workflow_name, SAMPLE.read_text(encoding="utf-8").splitlines(), [transcript])
        try:
            result = run_python(str(RENDER_HTML), "--workflow-name", workflow_name)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            html_text = (audit_dir / "workflow_log.visualization.html").read_text(encoding="utf-8")
            self.assertIn("Audit Status", html_text)
            self.assertIn("Delegation Evidence", html_text)
            self.assertIn("Gate Timeline", html_text)
            self.assertIn("Transcript Evidence", html_text)
            self.assertIn("Raw Ledger", html_text)
            self.assertIn("Mermaid Diagrams", html_text)
            self.assertIn("Implementation completed with audit evidence.", html_text)
            self.assertIn("data-filter-key=\"eventType\"", html_text)
        finally:
            shutil.rmtree(audit_dir, ignore_errors=True)

    def test_render_html_surfaces_attention_for_broken_runs(self) -> None:
        workflow_name = "_TEST_RENDER_ATTENTION"
        lines = SAMPLE.read_text(encoding="utf-8").splitlines()
        broken_lines = [
            line
            for line in lines
            if '"event_id": "evt_003"' not in line
            and '"event_id": "evt_005"' not in line
            and '"event_id": "evt_023"' not in line
        ]
        audit_dir = write_audit_workflow(workflow_name, broken_lines)
        try:
            result = run_python(str(RENDER_HTML), "--workflow-name", workflow_name)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            html_text = (audit_dir / "workflow_log.visualization.html").read_text(encoding="utf-8")
            self.assertIn("Needs Attention", html_text)
            self.assertIn("no terminal event", html_text)
            self.assertIn("no runtime agent binding", html_text)
            self.assertIn("no channel binding", html_text)
        finally:
            shutil.rmtree(audit_dir, ignore_errors=True)

    def test_append_workflow_event_fills_missing_timestamp_and_preserves_explicit_timestamp(self) -> None:
        workflow_name = "_TEST_APPEND_EVENT_TIMESTAMP"
        audit_dir = write_audit_workflow(workflow_name, [])
        try:
            base_event = {
                "event_id": "evt-no-timestamp",
                "run_id": "run_timestamp",
                "event_type": "runtime.agent.spawned",
                "source_agent_id": "MainContext",
                "target_agent_id": "agent_1",
                "runtime_parent_agent_id": "MainContext",
                "logical_parent_agent_id": None,
                "requested_by_agent_id": "MainContext",
                "delegation_id": "del_1",
                "channel_id": None,
                "workflow_step": "implementation",
                "message_type": None,
                "payload": {"role": "worker_programmer"},
            }
            with tempfile.TemporaryDirectory(prefix="workflow-audit-event-") as temp_dir:
                event_file = Path(temp_dir) / "event.json"
                event_file.write_text(json.dumps(base_event), encoding="utf-8")
                result = run_python(str(APPEND_EVENT), "--workflow-name", workflow_name, "--event-file", str(event_file))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

                explicit_event = dict(base_event)
                explicit_event["event_id"] = "evt-explicit-timestamp"
                explicit_event["timestamp"] = "2026-04-17T10:00:00Z"
                event_file.write_text(json.dumps(explicit_event), encoding="utf-8")
                result = run_python(str(APPEND_EVENT), "--workflow-name", workflow_name, "--event-file", str(event_file))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            events = [
                json.loads(line)
                for line in (audit_dir / "workflow_log.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertTrue(events[0]["timestamp"].endswith("Z"))
            self.assertEqual(events[1]["timestamp"], "2026-04-17T10:00:00Z")
        finally:
            shutil.rmtree(audit_dir, ignore_errors=True)

    def test_append_channel_message_fills_missing_timestamp_and_preserves_explicit_timestamp(self) -> None:
        workflow_name = "_TEST_APPEND_CHANNEL_TIMESTAMP"
        audit_dir = write_audit_workflow(workflow_name, [])
        try:
            base_message = {
                "message_id": "msg-no-timestamp",
                "run_id": "run_timestamp",
                "delegation_id": "del_1",
                "channel_id": "ch_1",
                "channel_kind": "engineer_unit",
                "workflow_label": "Task01Unit",
                "source_agent_id": "tester_1",
                "target_agent_id": "worker_1",
                "role": "unit_test_agent",
                "message_type": "test_result",
                "body": "PASS",
                "artifact_refs": [],
                "related_event_id": "evt_1",
            }
            with tempfile.TemporaryDirectory(prefix="workflow-audit-message-") as temp_dir:
                message_file = Path(temp_dir) / "message.json"
                message_file.write_text(json.dumps(base_message), encoding="utf-8")
                result = run_python(str(APPEND_CHANNEL), "--workflow-name", workflow_name, "--message-file", str(message_file))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

                explicit_message = dict(base_message)
                explicit_message["message_id"] = "msg-explicit-timestamp"
                explicit_message["timestamp"] = "2026-04-17T10:01:00Z"
                message_file.write_text(json.dumps(explicit_message), encoding="utf-8")
                result = run_python(str(APPEND_CHANNEL), "--workflow-name", workflow_name, "--message-file", str(message_file))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            messages = [
                json.loads(line)
                for line in (audit_dir / "channels" / "ch_1.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertTrue(messages[0]["timestamp"].endswith("Z"))
            self.assertEqual(messages[1]["timestamp"], "2026-04-17T10:01:00Z")
        finally:
            shutil.rmtree(audit_dir, ignore_errors=True)

    def test_live_model_derives_graph_state_and_replay_order(self) -> None:
        events = [
            {
                "event_id": "evt_2",
                "run_id": "run_live",
                "timestamp": "2026-04-17T10:00:02Z",
                "event_type": "runtime.agent.spawned",
                "source_agent_id": "MainContext",
                "target_agent_id": "worker_1",
                "delegation_id": "del_1",
                "channel_id": None,
                "workflow_step": "implementation",
                "message_type": None,
                "payload": {"role": "worker_programmer"},
            },
            {
                "event_id": "evt_1",
                "run_id": "run_live",
                "timestamp": "2026-04-17T10:00:01Z",
                "event_type": "delegation.created",
                "source_agent_id": "architect_1",
                "target_agent_id": None,
                "delegation_id": "del_1",
                "channel_id": None,
                "workflow_step": "implementation",
                "message_type": None,
                "payload": {"target_role": "worker_programmer", "status": "created"},
            },
            {
                "event_id": "evt_3",
                "run_id": "run_live",
                "timestamp": "2026-04-17T10:00:03Z",
                "event_type": "binding.delegation_runtime_agent",
                "source_agent_id": "MainContext",
                "target_agent_id": "worker_1",
                "delegation_id": "del_1",
                "channel_id": None,
                "workflow_step": "implementation",
                "message_type": None,
                "payload": {"role": "worker_programmer"},
            },
            {
                "event_id": "evt_4",
                "run_id": "run_live",
                "timestamp": "2026-04-17T10:00:04Z",
                "event_type": "runtime.channel.created",
                "source_agent_id": "MainContext",
                "target_agent_id": None,
                "delegation_id": "del_1",
                "channel_id": "ch_1",
                "workflow_step": "implementation",
                "message_type": None,
                "payload": {"owners": ["architect_1", "worker_1"]},
            },
            {
                "event_id": "evt_5",
                "run_id": "run_live",
                "timestamp": "2026-04-17T10:00:05Z",
                "event_type": "binding.delegation_channel",
                "source_agent_id": "MainContext",
                "target_agent_id": None,
                "delegation_id": "del_1",
                "channel_id": "ch_1",
                "workflow_step": "implementation",
                "message_type": None,
                "payload": {},
            },
            {
                "event_id": "evt_6",
                "run_id": "run_live",
                "timestamp": "2026-04-17T10:00:06Z",
                "event_type": "logical.message.sent",
                "source_agent_id": "worker_1",
                "target_agent_id": "architect_1",
                "delegation_id": "del_1",
                "channel_id": "ch_1",
                "workflow_step": "implementation",
                "message_type": "implementation_result",
                "payload": {"summary": "Done"},
            },
            {
                "event_id": "evt_7",
                "run_id": "run_live",
                "timestamp": "2026-04-17T10:00:07Z",
                "event_type": "delegation.completed",
                "source_agent_id": "worker_1",
                "target_agent_id": "architect_1",
                "delegation_id": "del_1",
                "channel_id": "ch_1",
                "workflow_step": "implementation",
                "message_type": "implementation_result",
                "payload": {"status": "completed"},
            },
            {
                "event_id": "evt_8",
                "run_id": "run_live",
                "timestamp": "2026-04-17T10:00:08Z",
                "event_type": "runtime.agent.terminated",
                "source_agent_id": "MainContext",
                "target_agent_id": "worker_1",
                "delegation_id": "del_1",
                "channel_id": None,
                "workflow_step": "implementation",
                "message_type": None,
                "payload": {"ended_reason": "work complete"},
            },
            {
                "event_id": "evt_9",
                "run_id": "run_live",
                "timestamp": "2026-04-17T10:00:09Z",
                "event_type": "runtime.channel.closed",
                "source_agent_id": "MainContext",
                "target_agent_id": "worker_1",
                "delegation_id": "del_1",
                "channel_id": "ch_1",
                "workflow_step": "implementation",
                "message_type": None,
                "payload": {"ended_reason": "work complete"},
            },
        ]
        transcripts = [
            {
                "message_id": "msg_1",
                "timestamp": "2026-04-17T10:00:06.500000Z",
                "source_agent_id": "worker_1",
                "target_agent_id": "architect_1",
                "delegation_id": "del_1",
                "channel_id": "ch_1",
                "message_type": "implementation_result",
                "body": "Done",
            }
        ]

        active_graph = derive_graph_state(events[:-2], transcripts)
        active_worker = next(agent for agent in active_graph["agents"] if agent["id"] == "worker_1")
        self.assertEqual(active_worker["status"], "active")
        self.assertTrue(
            any(
                item["kind"] == "lifecycle"
                and "worker_1 has no runtime.agent.terminated event" in item["summary"]
                for item in active_graph["attention"]
            )
        )

        graph = derive_graph_state(events, transcripts)
        worker = next(agent for agent in graph["agents"] if agent["id"] == "worker_1")
        delegation = next(item for item in graph["delegations"] if item["id"] == "del_1")
        channel = next(item for item in graph["channels"] if item["id"] == "ch_1")

        self.assertEqual(worker["status"], "terminated")
        self.assertFalse(any(item["kind"] == "lifecycle" for item in graph["attention"]))
        self.assertEqual(delegation["status"], "completed")
        self.assertEqual(delegation["runtime_agent_id"], "worker_1")
        self.assertEqual(delegation["channel_id"], "ch_1")
        self.assertEqual(channel["owners"], ["architect_1", "worker_1"])
        self.assertEqual(channel["status"], "closed")
        self.assertTrue(any(message["message_type"] == "implementation_result" for message in graph["messages"]))
        self.assertEqual(sorted_timeline_items(events, transcripts)[0]["entry"]["event_id"], "evt_1")

    def test_live_model_keeps_persistent_architect_active_without_warning(self) -> None:
        events = [
            {
                "event_id": "evt_arch_0",
                "run_id": "run_live",
                "timestamp": "2026-04-17T10:00:00Z",
                "event_type": "delegation.created",
                "source_agent_id": "MainContext",
                "target_agent_id": "architect_1",
                "delegation_id": "del_arch",
                "channel_id": None,
                "workflow_step": "architecture",
                "message_type": "task_request",
                "payload": {
                    "requested_by_role": "main_context",
                    "target_role": "architect",
                    "role": "architect",
                    "status": "created",
                },
            },
            {
                "event_id": "evt_arch_1",
                "run_id": "run_live",
                "timestamp": "2026-04-17T10:00:01Z",
                "event_type": "runtime.agent.spawned",
                "source_agent_id": "MainContext",
                "target_agent_id": "architect_1",
                "delegation_id": "del_arch",
                "channel_id": None,
                "workflow_step": "architecture",
                "message_type": None,
                "payload": {"role": "architect"},
            },
            {
                "event_id": "evt_arch_2",
                "run_id": "run_live",
                "timestamp": "2026-04-17T10:00:02Z",
                "event_type": "binding.delegation_runtime_agent",
                "source_agent_id": "MainContext",
                "target_agent_id": "architect_1",
                "delegation_id": "del_arch",
                "channel_id": None,
                "workflow_step": "architecture",
                "message_type": None,
                "payload": {"role": "architect"},
            },
            {
                "event_id": "evt_arch_2b",
                "run_id": "run_live",
                "timestamp": "2026-04-17T10:00:02.500000Z",
                "event_type": "runtime.channel.created",
                "source_agent_id": "MainContext",
                "target_agent_id": "architect_1",
                "delegation_id": "del_arch",
                "channel_id": "ch_main_arch",
                "workflow_step": "architecture",
                "message_type": None,
                "payload": {"owners": ["MainContext", "architect_1"]},
            },
            {
                "event_id": "evt_arch_2c",
                "run_id": "run_live",
                "timestamp": "2026-04-17T10:00:02.750000Z",
                "event_type": "binding.delegation_channel",
                "source_agent_id": "MainContext",
                "target_agent_id": "architect_1",
                "delegation_id": "del_arch",
                "channel_id": "ch_main_arch",
                "workflow_step": "architecture",
                "message_type": None,
                "payload": {},
            },
            {
                "event_id": "evt_arch_3",
                "run_id": "run_live",
                "timestamp": "2026-04-17T10:00:03Z",
                "event_type": "delegation.completed",
                "source_agent_id": "architect_1",
                "target_agent_id": "MainContext",
                "delegation_id": "del_arch",
                "channel_id": "ch_main_arch",
                "workflow_step": "architecture",
                "message_type": "verdict",
                "payload": {"status": "completed"},
            },
            {
                "event_id": "evt_arch_3b",
                "run_id": "run_live",
                "timestamp": "2026-04-17T10:00:03.500000Z",
                "event_type": "runtime.channel.closed",
                "source_agent_id": "MainContext",
                "target_agent_id": "architect_1",
                "delegation_id": "del_arch",
                "channel_id": "ch_main_arch",
                "workflow_step": "architecture",
                "message_type": None,
                "payload": {"ended_reason": "architecture delegation completed"},
            },
        ]

        graph = derive_graph_state(events, [])
        architect = next(agent for agent in graph["agents"] if agent["id"] == "architect_1")

        self.assertEqual(architect["status"], "active")
        self.assertFalse(any(item["kind"] == "lifecycle" for item in graph["attention"]))

        terminated_graph = derive_graph_state(
            [
                *events,
                {
                    "event_id": "evt_arch_4",
                    "run_id": "run_live",
                    "timestamp": "2026-04-17T10:00:04Z",
                    "event_type": "runtime.agent.terminated",
                    "source_agent_id": "MainContext",
                    "target_agent_id": "architect_1",
                    "delegation_id": "del_arch",
                    "channel_id": None,
                    "workflow_step": "architecture",
                    "message_type": None,
                    "payload": {"ended_reason": "workflow shutdown"},
                },
            ],
            [],
        )
        terminated_architect = next(agent for agent in terminated_graph["agents"] if agent["id"] == "architect_1")
        self.assertEqual(terminated_architect["status"], "terminated")

    def test_live_server_snapshot_returns_graph_and_replay_metadata(self) -> None:
        workflow_name = "_TEST_LIVE_SERVER"
        audit_dir = write_audit_workflow(workflow_name, SAMPLE.read_text(encoding="utf-8").splitlines())
        port = free_port()
        process = subprocess.Popen(
            [sys.executable, str(LIVE_SERVER), "--workflow-name", workflow_name, "--port", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            snapshot = wait_for_json(f"http://127.0.0.1:{port}/api/snapshot")
            self.assertEqual(snapshot["workflow_name"], workflow_name)
            self.assertGreater(len(snapshot["events"]), 0)
            self.assertIn("graph", snapshot)
            self.assertIn("agents", snapshot["graph"])
            self.assertIn("replay", snapshot["graph"])
        finally:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
            shutil.rmtree(audit_dir, ignore_errors=True)

    def test_live_server_streams_appended_workflow_events(self) -> None:
        workflow_name = "_TEST_LIVE_SERVER_SSE"
        audit_dir = write_audit_workflow(workflow_name, [])
        port = free_port()
        process = subprocess.Popen(
            [sys.executable, str(LIVE_SERVER), "--workflow-name", workflow_name, "--port", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        response = None
        try:
            wait_for_json(f"http://127.0.0.1:{port}/api/snapshot")
            response = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/events", timeout=5)
            event = {
                "event_id": "evt-streamed",
                "run_id": "run_streamed",
                "event_type": "runtime.agent.spawned",
                "source_agent_id": "MainContext",
                "target_agent_id": "agent_streamed",
                "runtime_parent_agent_id": "MainContext",
                "logical_parent_agent_id": None,
                "requested_by_agent_id": "MainContext",
                "delegation_id": "del_streamed",
                "channel_id": None,
                "workflow_step": "implementation",
                "message_type": None,
                "payload": {"role": "worker_programmer"},
            }
            with tempfile.TemporaryDirectory(prefix="workflow-audit-sse-") as temp_dir:
                event_file = Path(temp_dir) / "event.json"
                event_file.write_text(json.dumps(event), encoding="utf-8")
                result = run_python(str(APPEND_EVENT), "--workflow-name", workflow_name, "--event-file", str(event_file))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            lines: list[str] = []
            deadline = time.time() + 5
            while time.time() < deadline and not any("evt-streamed" in line for line in lines):
                line = response.readline().decode("utf-8").strip()
                if line:
                    lines.append(line)

            self.assertTrue(any(line == "event: workflow_event" for line in lines))
            self.assertTrue(any("evt-streamed" in line for line in lines))
        finally:
            if response is not None:
                response.close()
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
            shutil.rmtree(audit_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
