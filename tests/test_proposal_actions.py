from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import proposal_actions  # noqa: E402
from engine.item_vault import ItemVault  # noqa: E402
from proposal_actions import board_db  # noqa: E402
from tests.test_engine_core import make_config  # noqa: E402


def create_kanban_schema(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                body TEXT,
                assignee TEXT,
                status TEXT NOT NULL,
                priority INTEGER DEFAULT 0,
                created_by TEXT,
                created_at INTEGER NOT NULL,
                started_at INTEGER,
                completed_at INTEGER,
                workspace_kind TEXT NOT NULL DEFAULT 'scratch',
                workspace_path TEXT,
                branch_name TEXT,
                claim_lock TEXT,
                claim_expires INTEGER,
                tenant TEXT,
                result TEXT,
                idempotency_key TEXT,
                consecutive_failures INTEGER NOT NULL DEFAULT 0,
                worker_pid INTEGER,
                last_failure_error TEXT,
                max_runtime_seconds INTEGER,
                last_heartbeat_at INTEGER,
                current_run_id INTEGER,
                workflow_template_id TEXT,
                current_step_key TEXT,
                skills TEXT,
                model_override TEXT,
                max_retries INTEGER,
                goal_mode INTEGER NOT NULL DEFAULT 0,
                goal_max_turns INTEGER,
                session_id TEXT
            );
            CREATE TABLE task_links (
                parent_id TEXT NOT NULL,
                child_id TEXT NOT NULL,
                PRIMARY KEY (parent_id, child_id)
            );
            CREATE TABLE task_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                author TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE task_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                run_id INTEGER,
                kind TEXT NOT NULL,
                payload TEXT,
                created_at INTEGER NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO tasks (id, title, body, assignee, status, created_by, created_at, workspace_kind, consecutive_failures) "
            "VALUES ('root-task', 'triage root', '', 'orchestrator', 'done', 'test', 1, 'scratch', 0)"
        )
        conn.commit()
    finally:
        conn.close()


class TestProposalApprove(unittest.TestCase):
    def test_named_board_db_respects_hermes_home(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = make_config()
            cfg.raw["board"] = "pain-point"
            cfg.board = "pain-point"
            with patch.dict("os.environ", {"HERMES_HOME": str(Path(td) / "hermes-home")}, clear=False):
                self.assertEqual(
                    board_db(cfg),
                    Path(td) / "hermes-home" / "kanban" / "boards" / "pain-point" / "kanban.db",
                )

    def test_approve_spawns_ready_fulfillment_chain_and_records_item_event(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = make_config().raw
            data["workspace_root"] = str(root / "work")
            config_path = root / "triage.yaml"
            config_path.write_text(yaml.safe_dump(data), encoding="utf-8")

            vault_dir = root / "work" / "vault" / "items"
            vault = ItemVault(vault_dir)
            item = vault.create_item(slug="approved-item", title="Approved item", sources=[], body="Body")
            item.frontmatter["status"] = "awaiting_approval"
            item.frontmatter["path"] = "build"
            item.frontmatter["linked_kanban_tasks"] = ["root-task"]
            vault.save(item)

            db_path = root / "kanban.db"
            create_kanban_schema(db_path)

            with patch.object(proposal_actions, "CONFIG_PATH", config_path), patch.dict(
                "os.environ",
                {"TRIAGE_VAULT_DIR": str(vault_dir), "HERMES_KANBAN_DB": str(db_path)},
            ):
                result = proposal_actions.action_approve("approved-item")

            self.assertTrue(result["ok"])
            self.assertEqual(result["next_assignee"], "builder")
            self.assertEqual([task["title"] for task in result["chain"]], ["do_build: approved-item", "report: approved-item"])

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    "SELECT id, title, assignee, status, workspace_kind, workspace_path FROM tasks WHERE id != 'root-task' ORDER BY created_at, title"
                ).fetchall()
                self.assertEqual(len(rows), 2)
                first, second = rows
                self.assertEqual(first["status"], "ready")
                self.assertEqual(second["status"], "todo")
                self.assertEqual(first["workspace_kind"], "dir")
                self.assertEqual(second["workspace_kind"], "dir")
                self.assertEqual(first["workspace_path"], str(root / "work" / "builds" / "approved-item"))
                links = conn.execute("SELECT parent_id, child_id FROM task_links").fetchall()
                self.assertEqual([(row["parent_id"], row["child_id"]) for row in links], [(first["id"], second["id"])])
                comments = conn.execute("SELECT body FROM task_comments WHERE task_id = 'root-task'").fetchall()
                self.assertEqual(len(comments), 1)
                self.assertIn("Approved", comments[0]["body"])
            finally:
                conn.close()

            item = vault.load("approved-item")
            self.assertEqual(item.frontmatter["status"], "approved")
            self.assertEqual(item.frontmatter["linked_kanban_tasks"][0], "root-task")
            self.assertEqual(len(item.frontmatter["linked_kanban_tasks"]), 3)
            events = item.frontmatter.get("events", [])
            self.assertTrue(any(event.get("event") == "approved" and event.get("fulfillment_tasks") == 2 for event in events))
            self.assertIn("Approved by human", item.body)


if __name__ == "__main__":
    unittest.main()
