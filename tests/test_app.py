import tempfile
import unittest
from pathlib import Path

import app as kanban_app
from tools.regenerate_board import generate_board


class KanbanApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name)
        self.client = kanban_app.app.test_client()
        kanban_app.ACTIVE_PROJECT = None

    def tearDown(self):
        kanban_app.ACTIVE_PROJECT = None
        self.temporary.cleanup()

    def post_json(self, path, payload=None):
        return self.client.post(path, json=payload or {})

    def test_project_lifecycle(self):
        opened = self.post_json("/api/open", {"path": str(self.project)})
        self.assertEqual(opened.status_code, 200)
        self.assertFalse(opened.get_json()["initialized"])

        initialized = self.post_json("/api/initialize")
        self.assertEqual(initialized.status_code, 200)
        self.assertTrue(initialized.get_json()["initialized"])
        self.assertTrue((self.project / ".kanban" / "board.yaml").is_file())

        created = self.post_json(
            "/api/tickets",
            {
                "id": "TEST-1",
                "title": "Verify the Flask board",
                "category": "Testing",
                "intervention": "low",
            },
        )
        self.assertEqual(created.status_code, 201)
        ticket = created.get_json()
        self.assertEqual(ticket["status"], "inbox")
        kanban = self.project / ".kanban"
        ticket_path = next((kanban / "tickets").glob("*.md"))
        self.assertIsInstance(ticket["modified_ns"], str)
        self.assertEqual(ticket["modified_ns"], str(ticket_path.stat().st_mtime_ns))
        board_path = kanban / "board.md"
        self.assertEqual(board_path.read_text(encoding="utf-8"), generate_board(kanban))
        self.assertIn("## Inbox", board_path.read_text(encoding="utf-8"))

        moved = self.client.patch(
            "/api/tickets/TEST-1",
            json={"status": "ready", "modified_ns": ticket["modified_ns"]},
        )
        self.assertEqual(moved.status_code, 200)
        self.assertEqual(moved.get_json()["status"], "ready")
        self.assertEqual(board_path.read_text(encoding="utf-8"), generate_board(kanban))
        self.assertIn("## Ready", board_path.read_text(encoding="utf-8"))
        self.assertNotIn("## Inbox", board_path.read_text(encoding="utf-8"))

        source = next((self.project / ".kanban" / "tickets").glob("*.md")).read_text(
            encoding="utf-8"
        )
        self.assertIn("status: ready", source)
        self.assertIn("category: Testing", source)
        self.assertIn("source: [web-ui]", source)

    def test_board_validation_failure_rolls_back_created_ticket(self):
        self.post_json("/api/open", {"path": str(self.project)})
        self.post_json("/api/initialize")
        invalid = self.project / ".kanban" / "tickets" / "BROKEN.md"
        invalid.write_text("---\nid: BROKEN\n---\n", encoding="utf-8")

        response = self.post_json(
            "/api/tickets",
            {
                "id": "TEST-ROLLBACK",
                "title": "Must not survive failed validation",
                "category": "Testing",
                "intervention": "low",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("Board validation failed", response.get_json()["error"])
        self.assertFalse(
            any(
                path.name.startswith("TEST-ROLLBACK-")
                for path in (self.project / ".kanban" / "tickets").glob("*.md")
            )
        )

    def test_rejects_stale_ticket_update(self):
        self.post_json("/api/open", {"path": str(self.project)})
        self.post_json("/api/initialize")
        created = self.post_json(
            "/api/tickets",
            {
                "id": "TEST-2",
                "title": "Protect external changes",
                "category": "Storage",
                "intervention": "medium",
            },
        ).get_json()

        ticket_path = next((self.project / ".kanban" / "tickets").glob("*.md"))
        ticket_path.write_text(
            ticket_path.read_text(encoding="utf-8") + "\nExternal edit.\n",
            encoding="utf-8",
        )

        response = self.client.patch(
            "/api/tickets/TEST-2",
            json={"status": "done", "modified_ns": created["modified_ns"]},
        )
        self.assertEqual(response.status_code, 409)

    def test_directory_browser_lists_folders_without_native_ui(self):
        (self.project / "Alpha").mkdir()
        (self.project / "Beta").mkdir()

        response = self.client.get(
            "/api/directories", query_string={"path": str(self.project)}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["current"], str(self.project.resolve()))
        self.assertEqual(
            [directory["name"] for directory in payload["directories"]],
            ["Alpha", "Beta"],
        )

    def test_index_includes_theme_control(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="theme-toggle"', response.data)
        self.assertIn(b"prefers-color-scheme: dark", response.data)


if __name__ == "__main__":
    unittest.main()
