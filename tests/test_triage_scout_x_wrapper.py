from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WRAPPER = ROOT / "scripts" / "triage_scout_x.sh"


class TestTriageScoutXWrapper(unittest.TestCase):
    def _run(self, mode: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            intake = root / "intake"
            intake.mkdir()
            state = root / "state"
            fake_hermes = root / "hermes"
            fake_hermes.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    import json
                    import os
                    import pathlib
                    import sys

                    args = sys.argv[1:]
                    root = pathlib.Path(os.environ["FIXTURE_ROOT"])
                    intake = pathlib.Path(os.environ["TRIAGE_X_INTAKE_DIR"])
                    state = root / "state"
                    mode = os.environ["FIXTURE_MODE"]
                    if "list" in args and "--json" in args:
                        if state.exists():
                            report = next(intake.glob("*-x.md"))
                            print(json.dumps([{
                                "id": "task-new",
                                "title": "intake: x 2026-11-16",
                                "body": str(report),
                                "assignee": "orchestrator",
                                "created_by": "triage-scout-x",
                            }]))
                        else:
                            print("[]")
                        raise SystemExit(0)
                    if "chat" in args:
                        if mode == "provider-failure":
                            print("API call failed: HTTP 400 model_not_found")
                            print("Error: provider/model failure")
                            raise SystemExit(0)  # reproduces Hermes false-green exit
                        if mode == "provider-nonzero":
                            print("provider process failed", file=sys.stderr)
                            raise SystemExit(42)
                        if mode in {"report-only", "complete", "blocked"}:
                            report = intake / "2026-11-16T220000Z-x.md"
                            status = "blocked" if mode == "blocked" else "completed"
                            report.write_text(
                                f"source: x\\ncaptured_at: 2026-11-16T22:00:00Z\\nstatus: {status}\\n\\n"
                                "## Candidate: fixture\\nClaim: fixture\\nSources: []\\n",
                                encoding="utf-8",
                            )
                        if mode in {"complete", "blocked"}:
                            state.write_text("created", encoding="utf-8")
                        print("agent finished")
                        raise SystemExit(0)
                    raise SystemExit(2)
                    """
                ),
                encoding="utf-8",
            )
            fake_hermes.chmod(fake_hermes.stat().st_mode | stat.S_IXUSR)
            env = {
                **os.environ,
                "FIXTURE_ROOT": str(root),
                "FIXTURE_MODE": mode,
                "HERMES_BIN": str(fake_hermes),
                "TRIAGE_X_INTAKE_DIR": str(intake),
                "TRIAGE_X_WORKDIR": str(ROOT),
                "HERMES_HOME": str(root / "hermes-home"),
            }
            return subprocess.run(
                ["bash", str(WRAPPER)],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )

    def test_provider_failure_is_nonzero_even_when_hermes_exits_zero(self):
        result = self._run("provider-failure")
        self.assertEqual(result.returncode, 70, result.stdout + result.stderr)
        self.assertIn("failure detected despite zero Hermes exit", result.stderr)

    def test_nonzero_provider_exit_is_propagated(self):
        result = self._run("provider-nonzero")
        self.assertEqual(result.returncode, 42, result.stdout + result.stderr)
        self.assertIn("Hermes agent failed with exit 42", result.stderr)

    def test_success_without_required_artifacts_is_nonzero(self):
        result = self._run("no-artifacts")
        self.assertEqual(result.returncode, 71, result.stdout + result.stderr)
        self.assertIn("no new X intake report", result.stderr)

    def test_report_without_required_task_is_nonzero(self):
        result = self._run("report-only")
        self.assertEqual(result.returncode, 74, result.stdout + result.stderr)
        self.assertIn("no matching new intake Kanban task", result.stderr)

    def test_fixture_report_and_task_pass_without_live_x(self):
        result = self._run("complete")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("verified new intake report and Kanban task", result.stdout)

    def test_blocked_report_and_task_are_nonzero(self):
        result = self._run("blocked")
        self.assertEqual(result.returncode, 75, result.stdout + result.stderr)
        self.assertIn("X search did not complete", result.stderr)


if __name__ == "__main__":
    unittest.main()
