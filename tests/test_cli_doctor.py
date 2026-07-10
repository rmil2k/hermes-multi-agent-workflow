from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402
from cli.triage import cmd_doctor  # noqa: E402
from tests.test_engine_core import make_config  # noqa: E402


class FakeRunner:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(tuple(cmd))
        key = tuple(cmd)
        response = self.responses.get(key)
        if response is None:
            return subprocess.CompletedProcess(cmd, 127, "", "missing command")
        if isinstance(response, subprocess.CompletedProcess):
            return response
        return subprocess.CompletedProcess(cmd, 0, response, "")


def write_config(root: Path) -> Path:
    cfg = make_config().raw
    cfg["board"] = "test-board"
    cfg["roles"] = {
        "orchestrator": "orchestrator",
        "researcher": "researcher",
        "analyst": "analyst",
        "builder": "builder",
    }
    cfg["sources"] = [
        {"id": "web", "profile": "webresearch", "skill": "triage-scout-web", "schedule": "0 * * * *", "query": "find things"}
    ]
    path = root / "triage.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


class TestDoctor(unittest.TestCase):
    def test_doctor_passes_when_hermes_board_and_profiles_are_present(self):
        with tempfile.TemporaryDirectory() as td:
            config = write_config(Path(td))
            runner = FakeRunner({
                ("hermes", "--version"): "hermes 0.15.0\n",
                ("hermes", "profile", "list"): "orchestrator\nresearcher\nanalyst\nbuilder\nwebresearch\n",
                ("hermes", "kanban", "boards", "list"): "default\ntest-board\n",
            })

            out = StringIO()
            with redirect_stdout(out):
                rc = cmd_doctor(config, runner=runner)

            self.assertEqual(rc, 0)
            text = out.getvalue()
            self.assertIn("[OK] triage.yaml", text)
            self.assertIn("[OK] Hermes CLI", text)
            self.assertIn("[OK] board", text)
            self.assertIn("[OK] profiles", text)

    def test_doctor_fails_when_required_profiles_are_missing(self):
        with tempfile.TemporaryDirectory() as td:
            config = write_config(Path(td))
            runner = FakeRunner({
                ("hermes", "--version"): "hermes 0.15.0\n",
                ("hermes", "profile", "list"): "orchestrator\nresearcher\n",
                ("hermes", "kanban", "boards", "list"): "test-board\n",
            })

            out = StringIO()
            with redirect_stdout(out):
                rc = cmd_doctor(config, runner=runner)

            self.assertEqual(rc, 1)
            text = out.getvalue()
            self.assertIn("[FAIL] profiles", text)
            self.assertIn("analyst", text)
            self.assertIn("webresearch", text)

    def test_doctor_fails_cleanly_when_hermes_cli_is_missing(self):
        with tempfile.TemporaryDirectory() as td:
            config = write_config(Path(td))
            runner = FakeRunner({})

            out = StringIO()
            with redirect_stdout(out):
                rc = cmd_doctor(config, runner=runner)

            self.assertEqual(rc, 1)
            text = out.getvalue()
            self.assertIn("[FAIL] Hermes CLI", text)
            self.assertIn("Summary: 1 failure", text)


if __name__ == "__main__":
    unittest.main()
