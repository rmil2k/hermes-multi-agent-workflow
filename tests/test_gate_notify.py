from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli.triage import gate_send_command, parse_gate_reply  # noqa: E402
from engine.config import TriageConfig  # noqa: E402
from tests.test_engine_core import make_config  # noqa: E402


def cfg_with_gate(root: Path, gate: dict) -> TriageConfig:
    data = make_config().raw
    data["workspace_root"] = str(root / "work")
    data["gate"] = gate
    config_path = root / "triage.yaml"
    config_path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return TriageConfig.load(config_path)


class TestGateNotifications(unittest.TestCase):
    def test_discord_gate_target_builds_hermes_send_dm_command(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = cfg_with_gate(
                Path(td),
                {
                    "channel": "discord",
                    "target": "discord:1507343296979140781",
                    "approve": ["approve"],
                    "shelve": ["shelve"],
                    "modify": ["modify"],
                },
            )

            with patch.dict("os.environ", {"HERMES_BIN": "hermes"}):
                cmd = gate_send_command(cfg, Path(td) / "proposal.md", subject="[gate] test item")

            self.assertEqual(cmd[:4], ["hermes", "send", "--to", "discord:1507343296979140781"])
            self.assertIn("--file", cmd)
            self.assertIn(str(Path(td) / "proposal.md"), cmd)
            self.assertIn("--subject", cmd)
            self.assertIn("[gate] test item", cmd)

    def test_gate_target_defaults_to_channel_home_when_target_omitted(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = cfg_with_gate(Path(td), {"channel": "discord"})

            with patch.dict("os.environ", {"HERMES_BIN": "hermes"}):
                cmd = gate_send_command(cfg, Path(td) / "proposal.md")

            self.assertEqual(cmd[:4], ["hermes", "send", "--to", "discord"])
    def test_plain_reply_parser_maps_configured_gate_verbs(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = cfg_with_gate(
                Path(td),
                {
                    "channel": "discord",
                    "approve": ["approve", "ship it"],
                    "shelve": ["shelve", "reject the rest"],
                    "modify": ["modify"],
                },
            )

            self.assertEqual(parse_gate_reply(cfg, "approve silent-agent-workflow-failures"), ("approve", "silent-agent-workflow-failures", None))
            self.assertEqual(parse_gate_reply(cfg, "ship it silent-agent-workflow-failures"), ("approve", "silent-agent-workflow-failures", None))
            self.assertEqual(parse_gate_reply(cfg, "shelve silent-agent-workflow-failures: too broad"), ("shelve", "silent-agent-workflow-failures", "too broad"))
            self.assertEqual(parse_gate_reply(cfg, "modify silent-agent-workflow-failures: narrow to Hermes"), ("modify", "silent-agent-workflow-failures", "narrow to Hermes"))
            self.assertEqual(parse_gate_reply(cfg, "reject the rest"), ("shelve-all", "", None))


if __name__ == "__main__":
    unittest.main()
