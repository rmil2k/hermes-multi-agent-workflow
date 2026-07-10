from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import yaml

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli.triage import cmd_smoke_test  # noqa: E402
from tests.test_engine_core import make_config  # noqa: E402


def write_smoke_config(root: Path) -> Path:
    cfg = make_config().raw
    cfg["workspace_root"] = str(root / "work")
    cfg["route"] = {"classifier": "audit.quality", "map": {"missing": "build", "good": "shelve"}}
    cfg["paths"]["build"]["scope_rails"] = "paths/rails/build.md"
    rails = root / "paths" / "rails"
    rails.mkdir(parents=True)
    (rails / "build.md").write_text("Smoke build rails", encoding="utf-8")
    path = root / "triage.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


class TestSmokeTest(unittest.TestCase):
    def test_smoke_test_simulates_full_build_path_without_live_hermes(self):
        with tempfile.TemporaryDirectory() as td:
            config = write_smoke_config(Path(td))

            out = StringIO()
            with redirect_stdout(out):
                rc = cmd_smoke_test(config)

            self.assertEqual(rc, 0)
            text = out.getvalue()
            self.assertIn("[OK] config", text)
            self.assertIn("[OK] dedup", text)
            self.assertIn("[OK] score", text)
            self.assertIn("[OK] research", text)
            self.assertIn("[OK] route", text)
            self.assertIn("[OK] prep", text)
            self.assertIn("[OK] approval", text)
            self.assertIn("[OK] fulfillment", text)
            self.assertIn("Smoke test passed", text)

            item_files = list((Path(td) / "work" / "smoke" / "vault" / "items").glob("*.md"))
            self.assertEqual(len(item_files), 1)
            content = item_files[0].read_text(encoding="utf-8")
            self.assertIn("status: approved", content)
            self.assertIn("path: build", content)
            self.assertIn("score:", content)


if __name__ == "__main__":
    unittest.main()
