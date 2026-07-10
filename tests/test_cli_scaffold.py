from __future__ import annotations

import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import yaml

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli.triage import cmd_scaffold_plan, scaffold_commands  # noqa: E402
from tests.test_engine_core import make_config  # noqa: E402


def write_config(root: Path) -> Path:
    cfg = make_config().raw
    cfg["board"] = "test-board"
    cfg["sources"] = [
        {"id": "web", "profile": "webresearch", "skill": "triage-scout-web", "schedule": "0 * * * *", "query": "find things"}
    ]
    path = root / "triage.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


class FakeRunner:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    def __call__(self, cmd, **kwargs):
        self.calls.append(tuple(cmd))
        response = self.responses.get(tuple(cmd))
        if response is None:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 0, response, "")


class TestScaffold(unittest.TestCase):
    def test_scaffold_commands_are_structured_and_do_not_contain_todo_markers(self):
        cfg = make_config(board="test-board")
        commands = scaffold_commands(cfg, base_profile="base", paused=True)
        rendered = [" ".join(cmd) for cmd in commands]

        self.assertIn("hermes kanban boards create test-board", rendered)
        self.assertIn("hermes profile create orchestrator --from base", rendered)
        self.assertIn("hermes cron pause all", rendered)
        self.assertFalse(any("TODO" in line for line in rendered))

    def test_scaffold_plan_dry_run_prints_without_executing(self):
        with tempfile.TemporaryDirectory() as td:
            config = write_config(Path(td))
            runner = FakeRunner()

            out = StringIO()
            with redirect_stdout(out):
                rc = cmd_scaffold_plan(config, base_profile="base", apply=False, paused=True, runner=runner)

            self.assertEqual(rc, 0)
            self.assertEqual(runner.calls, [])
            text = out.getvalue()
            self.assertIn("Dry run", text)
            self.assertIn("hermes kanban boards create test-board", text)
            self.assertIn("hermes cron pause all", text)

    def test_scaffold_plan_apply_executes_commands(self):
        with tempfile.TemporaryDirectory() as td:
            config = write_config(Path(td))
            runner = FakeRunner()

            out = StringIO()
            with redirect_stdout(out):
                rc = cmd_scaffold_plan(config, base_profile="base", apply=True, paused=True, runner=runner)

            self.assertEqual(rc, 0)
            self.assertGreater(len(runner.calls), 3)
            self.assertEqual(runner.calls[0], ("hermes", "kanban", "boards", "create", "test-board"))
            self.assertIn(("hermes", "cron", "pause", "all"), runner.calls)
            self.assertIn("Applied", out.getvalue())

    def test_scaffold_skip_existing_filters_board_and_profiles_before_apply(self):
        with tempfile.TemporaryDirectory() as td:
            config = write_config(Path(td))
            runner = FakeRunner({
                ("hermes", "kanban", "boards", "list"): "test-board\n",
                ("hermes", "profile", "list"): "orchestrator\nresearcher\nanalyst\nbuilder\nwebresearch\n",
            })

            out = StringIO()
            with redirect_stdout(out):
                rc = cmd_scaffold_plan(
                    config,
                    base_profile="base",
                    apply=True,
                    paused=True,
                    skip_existing=True,
                    runner=runner,
                )

            self.assertEqual(rc, 0)
            self.assertIn(("hermes", "kanban", "boards", "list"), runner.calls)
            self.assertIn(("hermes", "profile", "list"), runner.calls)
            self.assertNotIn(("hermes", "kanban", "boards", "create", "test-board"), runner.calls)
            self.assertNotIn(("hermes", "profile", "create", "orchestrator", "--from", "base"), runner.calls)
            self.assertIn(("hermes", "cron", "pause", "all"), runner.calls)
            self.assertIn("Skipping existing board", out.getvalue())


if __name__ == "__main__":
    unittest.main()
