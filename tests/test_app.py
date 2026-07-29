import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

import app as kanban_app
from tools.regenerate_board import generate_board
from tools.sync_tools import PORTABLE_TOOLS, SyncError


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

    def open_and_initialize(self):
        self.post_json("/api/open", {"path": str(self.project)})
        self.post_json("/api/initialize")

    def create(self, title="A ticket", **overrides):
        payload = {"title": title, "category": "Testing", "intervention": "low"}
        payload.update(overrides)
        return self.post_json("/api/tickets", payload)

    def board_yaml(self):
        return (self.project / ".kanban" / "board.yaml").read_text(encoding="utf-8")

    def assert_portable_tools_match(self):
        canonical = Path(kanban_app.__file__).parent / "tools"
        portable = self.project / ".kanban" / "tools"
        for name in PORTABLE_TOOLS:
            self.assertEqual(
                (portable / name).read_bytes(),
                (canonical / name).read_bytes(),
            )

    def test_project_lifecycle(self):
        opened = self.post_json("/api/open", {"path": str(self.project)})
        self.assertEqual(opened.status_code, 200)
        self.assertFalse(opened.get_json()["initialized"])

        initialized = self.post_json("/api/initialize")
        self.assertEqual(initialized.status_code, 200)
        self.assertTrue(initialized.get_json()["initialized"])
        self.assertTrue((self.project / ".kanban" / "board.yaml").is_file())
        self.assertIn("id_prefix: ", self.board_yaml())
        self.assert_portable_tools_match()
        self.assertEqual(
            {item["status"] for item in initialized.get_json()["tool_sync"]},
            {"added"},
        )

        created = self.create("Verify the Flask board")
        self.assertEqual(created.status_code, 201)
        ticket = created.get_json()
        self.assertEqual(ticket["status"], "inbox")
        self.assertTrue(ticket["id"].endswith("-001"), ticket["id"])
        kanban = self.project / ".kanban"
        ticket_path = next((kanban / "tickets").glob("*.md"))
        self.assertIsInstance(ticket["modified_ns"], str)
        self.assertEqual(ticket["modified_ns"], str(ticket_path.stat().st_mtime_ns))
        board_path = kanban / "board.md"
        self.assertEqual(board_path.read_text(encoding="utf-8"), generate_board(kanban))
        self.assertIn("## Inbox", board_path.read_text(encoding="utf-8"))

        moved = self.client.patch(
            f"/api/tickets/{ticket['id']}",
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

    def write_ticket(self, ticket_id, *, status="ready", blocked_by="[]", archive=False):
        directory = self.project / ".kanban" / (
            "archive/2025" if archive else "tickets"
        )
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{ticket_id}.md"
        path.write_text(
            f"""\
---
id: {ticket_id}
title: {ticket_id}
status: {status}
category: Testing
intervention: low
type: feature
blocked_by: {blocked_by}
tags: []
source: [test]
---

Body.
""",
            encoding="utf-8",
        )
        return path

    def tickets_by_id(self):
        response = self.client.get("/api/tickets")
        self.assertEqual(response.status_code, 200)
        return {
            ticket["id"]: ticket for ticket in response.get_json()["tickets"]
        }

    def test_payload_carries_blocker_state_for_each_dependency(self):
        self.open_and_initialize()
        self.write_ticket("T1", status="done")
        self.write_ticket("T2", status="ready")
        self.write_ticket("T3", blocked_by="[T1, T2]")
        self.write_ticket("T4", blocked_by="[T1]")
        self.write_ticket("T5")

        tickets = self.tickets_by_id()

        self.assertEqual(
            tickets["T3"]["blockers"],
            [
                {"id": "T1", "status": "done", "state": "satisfied"},
                {"id": "T2", "status": "ready", "state": "unfinished"},
            ],
        )
        self.assertEqual(
            tickets["T4"]["blockers"],
            [{"id": "T1", "status": "done", "state": "satisfied"}],
        )
        self.assertEqual(tickets["T5"]["blockers"], [])

    def test_payload_resolves_an_archived_blocker_the_client_cannot_see(self):
        self.open_and_initialize()
        self.write_ticket("OLD1", status="done", archive=True)
        self.write_ticket("OLD2", status="inbox", archive=True)
        self.write_ticket("T1", blocked_by="[OLD1, OLD2]")

        tickets = self.tickets_by_id()

        self.assertEqual(
            tickets["T1"]["blockers"],
            [
                {"id": "OLD1", "status": "done", "state": "satisfied"},
                {"id": "OLD2", "status": "inbox", "state": "unfinished"},
            ],
        )
        self.assertNotIn("OLD1", tickets)

    def test_unknown_blocker_id_is_never_reported_as_satisfied(self):
        self.open_and_initialize()
        self.write_ticket("T1", blocked_by="[GONE]")

        tickets = self.tickets_by_id()

        self.assertEqual(
            tickets["T1"]["blockers"],
            [{"id": "GONE", "status": "", "state": "unknown"}],
        )

    def test_malformed_file_does_not_blank_the_board_or_satisfy_blockers(self):
        self.open_and_initialize()
        self.write_ticket("T1", status="done")
        self.write_ticket("T2", blocked_by="[T1, BROKEN]")
        (self.project / ".kanban" / "tickets" / "BROKEN.md").write_text(
            "not a ticket at all\n", encoding="utf-8"
        )

        response = self.client.get("/api/tickets")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertEqual(payload["invalid_files"], ["BROKEN.md"])
        tickets = {ticket["id"]: ticket for ticket in payload["tickets"]}
        self.assertEqual({"T1", "T2"}, set(tickets))
        self.assertEqual(
            tickets["T2"]["blockers"],
            [
                {"id": "T1", "status": "done", "state": "satisfied"},
                {"id": "BROKEN", "status": "", "state": "unknown"},
            ],
        )

    def test_blocker_state_does_not_hide_or_reorder_tickets(self):
        self.open_and_initialize()
        self.write_ticket("T1", status="ready")
        self.write_ticket("T2", blocked_by="[T1]")
        self.write_ticket("T3", status="done")

        payload = self.client.get("/api/tickets").get_json()

        self.assertEqual(
            [ticket["id"] for ticket in payload["tickets"]], ["T1", "T2", "T3"]
        )

    def test_ticket_ids_are_assigned_in_sequence(self):
        self.open_and_initialize()

        first = self.create("First").get_json()["id"]
        second = self.create("Second").get_json()["id"]
        third = self.create("Third").get_json()["id"]

        prefix = first.rpartition("-")[0]
        self.assertEqual(
            [first, second, third],
            [f"{prefix}-001", f"{prefix}-002", f"{prefix}-003"],
        )
        self.assertIn("id_sequence: 3", self.board_yaml())

    def test_client_supplied_id_is_refused(self):
        self.open_and_initialize()

        response = self.create("Pick my own id", id="CHOSEN-1")

        self.assertEqual(response.status_code, 400)
        self.assertIn("assigned by the project", response.get_json()["error"])
        self.assertEqual(
            list((self.project / ".kanban" / "tickets").glob("*.md")), []
        )

    def test_next_id_endpoint_previews_without_writing(self):
        self.open_and_initialize()
        created = self.create("First").get_json()["id"]

        preview = self.client.get("/api/next-id")

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.get_json()["id"], f"{created.rpartition('-')[0]}-002")
        self.assertEqual(
            len(list((self.project / ".kanban" / "tickets").glob("*.md"))), 1
        )

    def test_deleted_ticket_number_is_never_reissued(self):
        self.open_and_initialize()
        first = self.create("Doomed").get_json()["id"]
        next((self.project / ".kanban" / "tickets").glob("*.md")).unlink()

        reissued = self.create("Replacement").get_json()["id"]

        self.assertNotEqual(reissued, first)
        self.assertTrue(reissued.endswith("-002"), reissued)

    def test_board_validation_failure_rolls_back_created_ticket(self):
        self.open_and_initialize()
        self.create("Existing work")
        before = self.board_yaml()

        # An unterminated quoted string inside an inline list parses as a
        # ticket but fails board validation, exercising the rollback path.
        response = self.create('[a, "b]')

        self.assertEqual(response.status_code, 422)
        self.assertIn("the ticket was not created", response.get_json()["error"])
        self.assertEqual(
            len(list((self.project / ".kanban" / "tickets").glob("*.md"))), 1
        )
        self.assertEqual(self.board_yaml(), before)

    def test_no_id_is_assigned_when_the_board_is_already_invalid(self):
        self.open_and_initialize()
        invalid = self.project / ".kanban" / "tickets" / "BROKEN.md"
        invalid.write_text("---\nid: BROKEN\n---\n", encoding="utf-8")

        response = self.create("Must not survive failed validation")

        self.assertEqual(response.status_code, 422)
        self.assertIn("no ticket ID was assigned", response.get_json()["error"])
        self.assertEqual(
            [path.name for path in (self.project / ".kanban" / "tickets").glob("*.md")],
            ["BROKEN.md"],
        )

    def test_rejects_stale_ticket_update(self):
        self.open_and_initialize()
        created = self.create("Protect external changes").get_json()

        ticket_path = next((self.project / ".kanban" / "tickets").glob("*.md"))
        ticket_path.write_text(
            ticket_path.read_text(encoding="utf-8") + "\nExternal edit.\n",
            encoding="utf-8",
        )

        response = self.client.patch(
            f"/api/tickets/{created['id']}",
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

    def test_create_dialog_shows_the_assigned_id_instead_of_an_input(self):
        response = self.client.get("/")

        self.assertIn(b'<strong id="create-id">', response.data)
        self.assertNotIn(b'<input id="create-id"', response.data)

    def test_startup_path_selects_an_initialized_project(self):
        (self.project / ".kanban" / "tickets").mkdir(parents=True)

        with redirect_stdout(StringIO()) as stdout:
            kanban_app.configure_startup_project([str(self.project)])

        self.assertEqual(kanban_app.ACTIVE_PROJECT, self.project.resolve())
        self.assert_portable_tools_match()
        self.assertEqual(stdout.getvalue().count(": added"), len(PORTABLE_TOOLS))
        response = self.client.get("/api/tickets")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["initialized"])

    def test_startup_path_selects_an_uninitialized_project(self):
        with redirect_stdout(StringIO()) as stdout:
            kanban_app.configure_startup_project([str(self.project)])

        self.assertEqual(kanban_app.ACTIVE_PROJECT, self.project.resolve())
        self.assertFalse((self.project / ".kanban").exists())
        self.assertIn("portable tool sync skipped", stdout.getvalue())
        response = self.client.get("/api/tickets")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["initialized"])

    def test_nonexistent_startup_path_exits_nonzero(self):
        missing = self.project / "missing"

        with redirect_stderr(StringIO()) as stderr:
            with self.assertRaises(SystemExit) as raised:
                kanban_app.configure_startup_project([str(missing)])

        self.assertNotEqual(raised.exception.code, 0)
        self.assertIn("project path does not exist", stderr.getvalue())
        self.assertIsNone(kanban_app.ACTIVE_PROJECT)

    def test_file_startup_path_exits_nonzero(self):
        file_path = self.project / "not-a-directory.txt"
        file_path.write_text("not a project", encoding="utf-8")

        with redirect_stderr(StringIO()) as stderr:
            with self.assertRaises(SystemExit) as raised:
                kanban_app.configure_startup_project([str(file_path)])

        self.assertNotEqual(raised.exception.code, 0)
        self.assertIn("project path is not a directory", stderr.getvalue())
        self.assertIsNone(kanban_app.ACTIVE_PROJECT)

    def test_no_startup_path_leaves_project_selection_unchanged(self):
        kanban_app.ACTIVE_PROJECT = self.project.resolve()

        kanban_app.configure_startup_project([])

        self.assertEqual(kanban_app.ACTIVE_PROJECT, self.project.resolve())

    def test_open_project_refreshes_stale_portable_tools(self):
        tools = self.project / ".kanban" / "tools"
        tools.mkdir(parents=True)
        stale = tools / PORTABLE_TOOLS[0]
        stale.write_bytes(b"stale")

        response = self.post_json("/api/open", {"path": str(self.project)})

        self.assertEqual(response.status_code, 200)
        self.assert_portable_tools_match()
        statuses = {
            item["name"]: item["status"] for item in response.get_json()["tool_sync"]
        }
        self.assertEqual(statuses[PORTABLE_TOOLS[0]], "updated")
        self.assertEqual(statuses[PORTABLE_TOOLS[1]], "added")

    def test_sync_failure_does_not_switch_the_active_project(self):
        previous = self.project / "previous"
        previous.mkdir()
        (self.project / ".kanban").mkdir()
        kanban_app.ACTIVE_PROJECT = previous

        with mock.patch.object(
            kanban_app,
            "sync_portable_tools",
            side_effect=SyncError("simulated failure"),
        ):
            response = self.post_json("/api/open", {"path": str(self.project)})

        self.assertEqual(response.status_code, 500)
        self.assertIn("Could not synchronize", response.get_json()["error"])
        self.assertEqual(kanban_app.ACTIVE_PROJECT, previous)

    def test_initialize_rolls_back_when_tool_sync_fails(self):
        opened = self.post_json("/api/open", {"path": str(self.project)})
        self.assertEqual(opened.status_code, 200)

        with mock.patch.object(
            kanban_app,
            "sync_portable_tools",
            side_effect=SyncError("simulated failure"),
        ):
            response = self.post_json("/api/initialize")

        self.assertEqual(response.status_code, 500)
        self.assertIn("initialization was rolled back", response.get_json()["error"])
        self.assertFalse((self.project / ".kanban").exists())

    def test_frontend_loads_the_startup_project(self):
        script = (Path(__file__).parents[1] / "static" / "app.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('applyProject(await api("/api/tickets"))', script)
        self.assertIn("loadStartupProject();", script)
        self.assertIn("data.project,", script)
        self.assertIn("state.refreshTimer = setInterval(refreshTickets, 2000)", script)

    def test_windows_launcher_forwards_and_repoints_startup_path(self):
        launcher = (Path(__file__).parents[1] / "run.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("Project path does not exist:", launcher)
        self.assertIn("Project path is not a directory:", launcher)
        self.assertIn("(Resolve-Path -LiteralPath $ProjectPath).Path", launcher)
        self.assertIn("$StartupArguments += $ProjectPath", launcher)
        self.assertIn('Invoke-RestMethod -Uri "$AppUrl/api/open"', launcher)
        self.assertIn("foreach ($Tool in $OpenResult.tool_sync)", launcher)
        self.assertIn("$Tool.status", launcher)


if __name__ == "__main__":
    unittest.main()
