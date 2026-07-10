from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import yaml

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli.triage import cmd_item_list, cmd_item_show, cmd_smoke_test  # noqa: E402
from engine.item_vault import ItemVault  # noqa: E402
from tests.test_engine_core import make_config  # noqa: E402


def write_config(root: Path) -> Path:
    cfg = make_config().raw
    cfg["workspace_root"] = str(root / "work")
    path = root / "triage.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


class TestItemEventsAndCli(unittest.TestCase):
    def test_item_vault_append_event_persists_chronological_events(self):
        with tempfile.TemporaryDirectory() as td:
            vault = ItemVault(Path(td) / "items")
            vault.create_item(slug="event-test", title="Event Test", sources=[], body="body")

            vault.append_event("event-test", "created", detail="item created")
            vault.append_event("event-test", "scored", score=75)
            item = vault.load("event-test")

            self.assertEqual([e["event"] for e in item.frontmatter["events"]], ["created", "scored"])
            self.assertEqual(item.frontmatter["events"][0]["detail"], "item created")
            self.assertEqual(item.frontmatter["events"][1]["score"], 75)
            self.assertIn("at", item.frontmatter["events"][0])

    def test_item_cli_lists_and_shows_smoke_test_item_with_events(self):
        with tempfile.TemporaryDirectory() as td:
            config = write_config(Path(td))
            smoke_output = StringIO()
            with redirect_stdout(smoke_output):
                self.assertEqual(cmd_smoke_test(config), 0)

            default_listing = StringIO()
            with redirect_stdout(default_listing):
                rc = cmd_item_list(config)
            self.assertEqual(rc, 0)
            self.assertNotIn("smoke-agent-workflow-pain", default_listing.getvalue())

            listing = StringIO()
            with redirect_stdout(listing):
                rc = cmd_item_list(config, smoke=True)
            self.assertEqual(rc, 0)
            list_text = listing.getvalue()
            self.assertIn("smoke-agent-workflow-pain", list_text)
            self.assertIn("approved", list_text)
            self.assertIn("build", list_text)

            detail = StringIO()
            with redirect_stdout(detail):
                rc = cmd_item_show(config, "smoke-agent-workflow-pain", smoke=True)
            self.assertEqual(rc, 0)
            detail_text = detail.getvalue()
            self.assertIn("Agent users lose hours", detail_text)
            self.assertIn("Events", detail_text)
            self.assertIn("scored", detail_text)
            self.assertIn("approved", detail_text)


if __name__ == "__main__":
    unittest.main()
