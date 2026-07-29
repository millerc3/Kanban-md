import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from tools import create_ticket as tool
from tools.regenerate_board import ValidationError, main as regenerate_main


REPOSITORY = Path(__file__).resolve().parent.parent

BOARD_CONFIG = """version: 1
name: Test Project
statuses: [inbox, ready, in_progress, blocked, review, done]
categories: [Product, Storage]
intervention_levels: [low, medium, high]
id_prefix: TST
id_padding: 3
id_sequence: 0
"""


class CreateTicketTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.project = Path(self.directory.name)
        self.kanban = self.project / ".kanban"
        (self.kanban / "tickets").mkdir(parents=True)
        (self.kanban / "archive").mkdir(parents=True)
        (self.kanban / "board.yaml").write_text(BOARD_CONFIG, encoding="utf-8")

    def tickets(self):
        return sorted(path.name for path in (self.kanban / "tickets").glob("*.md"))

    def board_yaml(self):
        return (self.kanban / "board.yaml").read_text(encoding="utf-8")

    def run_cli(self, *arguments, stdin=None):
        """Run the tool in-process, returning its exit code and streams."""

        out, err = StringIO(), StringIO()
        with mock.patch.object(sys, "stdin", StringIO(stdin or "")):
            with redirect_stdout(out), redirect_stderr(err):
                code = tool.main(
                    ["--kanban", str(self.kanban), *[str(item) for item in arguments]]
                )
        return code, out.getvalue(), err.getvalue()

    def test_creates_a_complete_ticket_and_regenerates_the_board(self):
        code, out, _ = self.run_cli(
            "--title",
            "Validate that foobar is called",
            "--category",
            "Storage",
            "--priority",
            "high",
            "--type",
            "test",
            "--tags",
            "tests,foobar",
        )

        self.assertEqual(code, 0)
        self.assertEqual(self.tickets(), ["TST-001-validate-that-foobar-is-called.md"])
        source = (
            self.kanban / "tickets" / "TST-001-validate-that-foobar-is-called.md"
        ).read_text(encoding="utf-8")
        self.assertIn("id: TST-001", source)
        self.assertIn("title: Validate that foobar is called", source)
        self.assertIn("status: inbox", source)
        self.assertIn("category: Storage", source)
        self.assertIn("priority: high", source)
        self.assertIn("type: test", source)
        self.assertIn("tags: [tests, foobar]", source)
        self.assertIn("source: [cli]", source)
        self.assertIn("blocked_by: []", source)
        self.assertIn("id_sequence: 1", self.board_yaml())
        self.assertIn("TST-001", (self.kanban / "board.md").read_text(encoding="utf-8"))
        self.assertIn("TST-001", out)

    def test_ids_are_assigned_in_sequence(self):
        self.run_cli("--title", "First")
        self.run_cli("--title", "Second")

        self.assertEqual(self.tickets(), ["TST-001-first.md", "TST-002-second.md"])
        self.assertIn("id_sequence: 2", self.board_yaml())

    def test_caller_supplied_id_is_refused(self):
        code, _, err = self.run_cli("--title", "Chosen id", "--id", "TST-999")

        self.assertEqual(code, tool.VALIDATION_ERROR)
        self.assertIn("cannot be chosen", err)
        self.assertEqual(self.tickets(), [])
        self.assertIn("id_sequence: 0", self.board_yaml())

    def test_body_is_read_from_a_file(self):
        body = self.project / "body.md"
        body.write_text("## Goal\n\nProve the body survives.\n", encoding="utf-8")

        code, _, _ = self.run_cli("--title", "From file", "--body-file", body)

        self.assertEqual(code, 0)
        source = (self.kanban / "tickets" / "TST-001-from-file.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Prove the body survives.", source)
        self.assertNotIn("Describe the outcome this ticket should produce.", source)

    def test_body_is_read_from_stdin(self):
        code, _, _ = self.run_cli(
            "--title", "From stdin", "--body-stdin", stdin="## Goal\n\nPiped body.\n"
        )

        self.assertEqual(code, 0)
        source = (self.kanban / "tickets" / "TST-001-from-stdin.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Piped body.", source)

    def test_body_file_dash_also_reads_stdin(self):
        code, _, _ = self.run_cli(
            "--title", "Dash stdin", "--body-file", "-", stdin="## Goal\n\nDashed.\n"
        )

        self.assertEqual(code, 0)
        source = (self.kanban / "tickets" / "TST-001-dash-stdin.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Dashed.", source)

    def test_a_byte_order_mark_is_stripped_from_a_piped_body(self):
        """Windows shells prepend a BOM when piping UTF-8."""

        code, _, _ = self.run_cli(
            "--title", "Bom body", "--body-stdin", stdin="﻿## Goal\n\nClean.\n"
        )

        self.assertEqual(code, 0)
        source = (self.kanban / "tickets" / "TST-001-bom-body.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("﻿", source)
        self.assertIn("---\n\n## Goal", source)

    def test_a_byte_order_mark_is_stripped_from_a_body_file(self):
        body = self.project / "body.md"
        body.write_text("## Goal\n\nFrom a BOM file.\n", encoding="utf-8-sig")

        code, _, _ = self.run_cli("--title", "Bom file", "--body-file", body)

        self.assertEqual(code, 0)
        source = (self.kanban / "tickets" / "TST-001-bom-file.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("﻿", source)
        self.assertIn("---\n\n## Goal", source)

    def test_missing_body_falls_back_to_the_type_template(self):
        code, _, _ = self.run_cli("--title", "Template fallback")

        self.assertEqual(code, 0)
        source = (self.kanban / "tickets" / "TST-001-template-fallback.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Describe the outcome this ticket should produce.", source)

    def test_unreadable_body_file_creates_nothing(self):
        code, _, err = self.run_cli(
            "--title", "Missing body", "--body-file", self.project / "absent.md"
        )

        self.assertEqual(code, tool.VALIDATION_ERROR)
        self.assertIn("cannot read ticket body", err)
        self.assertEqual(self.tickets(), [])

    def test_json_output_reports_the_id_and_path(self):
        code, out, _ = self.run_cli("--title", "Machine readable", "--json")

        payload = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(payload["id"], "TST-001")
        self.assertTrue(Path(payload["path"]).is_file())

    def test_invalid_status_is_refused_before_anything_is_written(self):
        code, _, err = self.run_cli("--title", "Bad status", "--status", "shipped")

        self.assertEqual(code, tool.VALIDATION_ERROR)
        self.assertIn("invalid status", err)
        self.assertEqual(self.tickets(), [])
        self.assertIn("id_sequence: 0", self.board_yaml())

    def test_unknown_dependency_rolls_the_creation_back(self):
        before = self.board_yaml()

        code, _, err = self.run_cli(
            "--title", "Depends on nothing", "--blocked-by", "TST-404"
        )

        self.assertEqual(code, tool.VALIDATION_ERROR)
        self.assertIn("does not match an active or archived ticket", err)
        self.assertEqual(self.tickets(), [])
        self.assertEqual(self.board_yaml(), before)

    def test_rollback_restores_the_previous_high_water_mark(self):
        self.run_cli("--title", "Existing work")
        before = self.board_yaml()

        code, _, _ = self.run_cli("--title", "Doomed", "--blocked-by", "TST-404")

        self.assertEqual(code, tool.VALIDATION_ERROR)
        self.assertEqual(self.board_yaml(), before)
        self.assertEqual(self.tickets(), ["TST-001-existing-work.md"])

    def test_an_already_invalid_board_assigns_no_id(self):
        (self.kanban / "tickets" / "BROKEN.md").write_text(
            "---\nid: BROKEN\n---\n", encoding="utf-8"
        )

        code, _, err = self.run_cli("--title", "Must not survive")

        self.assertEqual(code, tool.VALIDATION_ERROR)
        self.assertIn("missing required field", err)
        self.assertEqual(self.tickets(), ["BROKEN.md"])
        self.assertIn("id_sequence: 0", self.board_yaml())

    def test_a_lost_reservation_retries_onto_the_next_id(self):
        """A number already held by another file is given up, not duplicated."""

        self.run_cli("--title", "Existing work")
        real_allocate = tool.allocate_ticket_id
        attempts = []

        def stale_allocation(kanban):
            assigned = real_allocate(kanban)
            attempts.append(assigned)
            # Hand out the id that is already taken exactly once, as a racing
            # process would after reading the board a moment too early.
            return "TST-001" if len(attempts) == 1 else assigned

        with mock.patch.object(tool, "allocate_ticket_id", stale_allocation):
            code, out, _ = self.run_cli("--title", "Racing writer", "--json")

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["id"], "TST-002")
        self.assertEqual(
            self.tickets(), ["TST-001-existing-work.md", "TST-002-racing-writer.md"]
        )

    def test_a_held_claim_is_waited_out_and_a_stale_one_is_cleared(self):
        claim = self.kanban / "tickets" / ".TST-001.claim"
        claim.write_text("TST-001\n", encoding="utf-8")
        stale = time.time() - (tool.CLAIM_TIMEOUT_SECONDS + 60)
        os.utime(claim, (stale, stale))

        code, out, _ = self.run_cli("--title", "After a crash", "--json")

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["id"], "TST-001")
        self.assertFalse(claim.exists())

    def test_a_live_claim_blocks_the_number_it_holds(self):
        claim = self.kanban / "tickets" / ".TST-001.claim"
        claim.write_text("TST-001\n", encoding="utf-8")

        code, _, err = self.run_cli("--title", "Blocked by a live claim")

        self.assertEqual(code, tool.VALIDATION_ERROR)
        self.assertIn("could not reserve a ticket id", err)
        self.assertEqual(self.tickets(), [])
        self.assertTrue(claim.exists())

    def test_claim_markers_are_invisible_to_the_board(self):
        self.run_cli("--title", "Only ticket")

        self.assertEqual(
            [path.name for path in (self.kanban / "tickets").iterdir()],
            ["TST-001-only-ticket.md"],
        )

    def test_runs_from_an_unrelated_working_directory(self):
        elsewhere = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: elsewhere.rmdir())
        previous = Path.cwd()
        os.chdir(elsewhere)
        try:
            code, _, _ = self.run_cli("--title", "Anywhere")
        finally:
            os.chdir(previous)

        self.assertEqual(code, 0)
        self.assertEqual(self.tickets(), ["TST-001-anywhere.md"])

    def test_concurrent_processes_receive_distinct_ids(self):
        script = REPOSITORY / "tools" / "create_ticket.py"
        processes = [
            subprocess.Popen(
                [
                    sys.executable,
                    str(script),
                    "--kanban",
                    str(self.kanban),
                    "--title",
                    f"Concurrent writer {index}",
                    "--json",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(REPOSITORY),
            )
            for index in range(6)
        ]
        results = [process.communicate() for process in processes]

        for process, (_, err) in zip(processes, results):
            self.assertEqual(process.returncode, 0, err)
        assigned = [json.loads(out)["id"] for out, _ in results]
        self.assertEqual(len(set(assigned)), len(assigned), assigned)
        self.assertEqual(len(self.tickets()), 6)

        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            check = regenerate_main(["--kanban", str(self.kanban), "--check"])
        self.assertEqual(check, 0, err.getvalue())


class SharedModuleTests(unittest.TestCase):
    """The library surface the Flask endpoint depends on."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.kanban = Path(self.directory.name) / ".kanban"
        (self.kanban / "tickets").mkdir(parents=True)
        (self.kanban / "archive").mkdir(parents=True)
        (self.kanban / "board.yaml").write_text(BOARD_CONFIG, encoding="utf-8")

    def test_create_ticket_returns_the_id_and_path(self):
        ticket_id, path = tool.create_ticket(
            self.kanban, tool.TicketFields(title="Library call")
        )

        self.assertEqual(ticket_id, "TST-001")
        self.assertEqual(path.name, "TST-001-library-call.md")
        self.assertTrue(path.is_file())

    def test_rollback_raises_a_distinguishable_error(self):
        with self.assertRaises(tool.CreationRolledBack):
            tool.create_ticket(
                self.kanban,
                tool.TicketFields(title="Doomed", blocked_by=["TST-404"]),
            )

    def test_a_prior_invalid_board_raises_a_plain_validation_error(self):
        (self.kanban / "tickets" / "BROKEN.md").write_text(
            "---\nid: BROKEN\n---\n", encoding="utf-8"
        )

        with self.assertRaises(ValidationError) as caught:
            tool.create_ticket(self.kanban, tool.TicketFields(title="No id for me"))
        self.assertNotIsInstance(caught.exception, tool.CreationRolledBack)

    def test_a_taken_descriptive_name_falls_back_without_overwriting(self):
        """The id is identity; an occupied slug never overwrites another file."""

        tickets = self.kanban / "tickets"
        occupied = tickets / "TST-001-taken.md"
        occupied.write_text("someone else's file", encoding="utf-8")

        path = tool._write_ticket_file(tickets, "TST-001", "Taken", "new content")

        self.assertEqual(path, tickets / "TST-001.md")
        self.assertEqual(occupied.read_text(encoding="utf-8"), "someone else's file")

    def test_titles_with_a_line_break_are_refused(self):
        with self.assertRaises(ValidationError):
            tool.create_ticket(
                self.kanban, tool.TicketFields(title="Broken\nframatter: yes")
            )


if __name__ == "__main__":
    unittest.main()
