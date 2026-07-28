import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import migrate_ticket_ids as migrate
from tools import regenerate_board as board_generator


BOARD_YAML = """\
version: 1
name: Test Board
statuses: [inbox, ready, in_progress, blocked, review, done]
categories: [Core]
intervention_levels: [low, medium, high]
"""


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.kanban = self.root / ".kanban"
        (self.kanban / "tickets").mkdir(parents=True)
        (self.kanban / "archive" / "2025").mkdir(parents=True)
        (self.kanban / "board.yaml").write_text(BOARD_YAML, encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def write_ticket(
        self,
        ticket_id,
        *,
        blocked_by="[]",
        created=None,
        archive=False,
        extra="",
        body="Ticket body.",
        file_name=None,
    ):
        directory = (
            self.kanban / "archive" / "2025" if archive else self.kanban / "tickets"
        )
        path = directory / (file_name or f"{ticket_id}.md")
        created_line = f"created: {created}\n" if created else ""
        # newline="" keeps fixtures LF on every platform; write_text would
        # translate to CRLF on Windows and hide line-ending regressions.
        path.write_text(
            f"""\
---
id: {ticket_id}
title: Ticket {ticket_id}
status: ready
category: Core
intervention: low
type: feature
blocked_by: {blocked_by}
tags: []
source: [test]
{created_line}{extra}---

{body}
""",
            encoding="utf-8",
            newline="",
        )
        return path

    def board_yaml(self):
        return (self.kanban / "board.yaml").read_text(encoding="utf-8")

    def ticket_files(self):
        return sorted(path.name for path in (self.kanban / "tickets").glob("*.md"))

    def run_migration(self, *arguments):
        with contextlib.redirect_stdout(io.StringIO()):
            return migrate.main(["--kanban", str(self.kanban), *arguments])

    def run_cli(self, *arguments):
        return subprocess.run(
            [
                sys.executable,
                str(Path(migrate.__file__)),
                "--kanban",
                str(self.kanban),
                *arguments,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    # Adoption

    def test_adopt_records_the_scheme_without_touching_tickets(self):
        self.write_ticket("weird-id-1")
        self.write_ticket("another")
        before = {
            path: path.read_text(encoding="utf-8")
            for path in (self.kanban / "tickets").glob("*.md")
        }

        self.assertEqual(self.run_migration("--adopt", "--apply", "--prefix", "TB"), 0)

        self.assertIn("id_prefix: TB", self.board_yaml())
        self.assertIn("id_sequence: 0", self.board_yaml())
        for path, text in before.items():
            self.assertEqual(path.read_text(encoding="utf-8"), text)
        self.assertEqual(board_generator.allocate_ticket_id(self.kanban), "TB-001")

    def test_adopt_seeds_the_sequence_above_existing_matching_ids(self):
        self.write_ticket("TB-007")
        self.write_ticket("TB-0012", archive=True)

        self.run_migration("--adopt", "--apply", "--prefix", "TB")

        self.assertIn("id_sequence: 12", self.board_yaml())
        self.assertEqual(board_generator.allocate_ticket_id(self.kanban), "TB-013")

    def test_adopt_derives_a_prefix_from_the_project_directory(self):
        self.write_ticket("A1")

        self.run_migration("--adopt", "--apply")

        config = board_generator.load_board_config(self.kanban)
        self.assertTrue(config.id_prefix)
        self.assertTrue(config.id_prefix[0].isalpha())

    def test_dry_run_is_the_default_and_writes_nothing(self):
        self.write_ticket("legacy-1")

        self.assertEqual(self.run_migration("--renumber", "--prefix", "TB"), 0)

        self.assertNotIn("id_prefix", self.board_yaml())
        self.assertEqual(self.ticket_files(), ["legacy-1.md"])
        self.assertEqual(list(self.root.glob(".kanban.backup-*")), [])

    # Renumbering

    def test_renumber_preserves_conforming_ids_and_remaps_dependencies(self):
        self.write_ticket("TB-001", created="2026-01-01")
        self.write_ticket(
            "legacy-a",
            blocked_by="[TB-001]",
            created="2026-01-02",
            file_name="legacy-a-first-task.md",
        )
        self.write_ticket(
            "legacy-b",
            blocked_by="[legacy-a]",
            created="2026-01-03",
            file_name="legacy-b-second-task.md",
        )

        self.assertEqual(self.run_migration("--renumber", "--apply", "--prefix", "TB"), 0)

        self.assertEqual(
            self.ticket_files(),
            ["TB-001.md", "TB-002-first-task.md", "TB-003-second-task.md"],
        )
        second = (self.kanban / "tickets" / "TB-002-first-task.md").read_text(
            encoding="utf-8"
        )
        third = (self.kanban / "tickets" / "TB-003-second-task.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("id: TB-002", second)
        self.assertIn("legacy_id: legacy-a", second)
        self.assertIn("blocked_by: [TB-001]", second)
        self.assertIn("blocked_by: [TB-002]", third)
        self.assertIn("id_sequence: 3", self.board_yaml())

    def test_renumber_rewrites_block_list_dependencies(self):
        self.write_ticket("old-one", created="2026-01-01")
        self.write_ticket("old-two", created="2026-01-02")
        self.write_ticket(
            "old-three",
            blocked_by="\n  - old-one\n  - old-two",
            created="2026-01-03",
        )

        self.run_migration("--renumber", "--apply", "--prefix", "TB")

        text = (self.kanban / "tickets" / "TB-003.md").read_text(encoding="utf-8")
        self.assertIn("  - TB-001\n", text)
        self.assertIn("  - TB-002\n", text)

    def test_renumber_preserves_unknown_fields_and_body(self):
        self.write_ticket(
            "old-one",
            extra="owner: chris\nestimate: 3\n",
            body="## Goal\n\nKeep | this ~ exactly.\n",
            file_name="old-one-descriptive-name.md",
        )

        self.run_migration("--renumber", "--apply", "--prefix", "TB")

        text = (self.kanban / "tickets" / "TB-001-descriptive-name.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("owner: chris", text)
        self.assertIn("estimate: 3", text)
        self.assertIn("Keep | this ~ exactly.", text)

    def test_renumber_covers_archived_tickets(self):
        self.write_ticket("old-active", created="2026-01-02")
        self.write_ticket("old-archived", archive=True, created="2026-01-01")

        self.run_migration("--renumber", "--apply", "--prefix", "TB")

        self.assertEqual(
            sorted(path.name for path in (self.kanban / "archive").rglob("*.md")),
            ["TB-001.md"],
        )
        self.assertEqual(self.ticket_files(), ["TB-002.md"])

    def test_renumber_all_handles_swapped_ids(self):
        self.write_ticket("TB-002", created="2026-01-01")
        self.write_ticket("TB-001", created="2026-01-02")

        self.assertEqual(self.run_migration("--renumber-all", "--apply", "--prefix", "TB"), 0)

        first = (self.kanban / "tickets" / "TB-001.md").read_text(encoding="utf-8")
        second = (self.kanban / "tickets" / "TB-002.md").read_text(encoding="utf-8")
        self.assertIn("legacy_id: TB-002", first)
        self.assertIn("legacy_id: TB-001", second)
        self.assertEqual(self.ticket_files(), ["TB-001.md", "TB-002.md"])

    def test_stray_body_references_are_reported_not_rewritten(self):
        self.write_ticket("old-one", body="Follows on from old-two.")
        self.write_ticket("old-two")

        plan = migrate.build_plan(self.kanban, "TB", None, "created", True, False)

        self.assertTrue(
            any("old-two" in reference for reference in plan.stray_references)
        )
        rewritten = next(
            rename.content
            for rename in plan.renames
            if rename.ticket.id == "old-one"
        )
        self.assertIn("Follows on from old-two.", rewritten)

    def test_second_run_is_a_no_op(self):
        self.write_ticket("old-one", created="2026-01-01")
        self.run_migration("--renumber", "--apply", "--prefix", "TB")
        after = (self.kanban / "tickets" / "TB-001.md").read_text(encoding="utf-8")

        plan = migrate.build_plan(self.kanban, None, None, "created", True, False)

        self.assertEqual(plan.renames, ())
        self.assertEqual(
            (self.kanban / "tickets" / "TB-001.md").read_text(encoding="utf-8"), after
        )

    def test_failed_migration_restores_the_backup(self):
        original = self.write_ticket("old-one").read_text(encoding="utf-8")
        plan = migrate.build_plan(self.kanban, "TB", None, "created", True, False)

        with mock.patch.object(
            migrate,
            "regenerate_board",
            side_effect=board_generator.ValidationError(["forced failure"]),
        ):
            with self.assertRaises(board_generator.ValidationError):
                migrate.apply_plan(plan)

        self.assertEqual(self.ticket_files(), ["old-one.md"])
        self.assertEqual(
            (self.kanban / "tickets" / "old-one.md").read_text(encoding="utf-8"),
            original,
        )
        self.assertNotIn("id_prefix", self.board_yaml())
        self.assertEqual(list(self.root.glob(".kanban.backup-*")), [])

    def test_invalid_board_stops_the_migration(self):
        (self.kanban / "tickets" / "BROKEN.md").write_text(
            "---\nid: BROKEN\n---\n", encoding="utf-8"
        )

        self.assertEqual(self.run_migration("--adopt", "--apply", "--prefix", "TB"), 2)
        self.assertNotIn("id_prefix", self.board_yaml())

    def test_invalid_prefix_is_rejected(self):
        self.write_ticket("A1")

        self.assertEqual(self.run_migration("--adopt", "--apply", "--prefix", "9x"), 2)

    def test_cli_reports_the_plan(self):
        self.write_ticket("old-one")

        result = self.run_cli("--renumber", "--prefix", "TB")

        self.assertEqual(result.returncode, 0)
        self.assertIn("old-one -> TB-001", result.stdout)
        self.assertIn("dry run", result.stdout)
        self.assertEqual(self.ticket_files(), ["old-one.md"])


if __name__ == "__main__":
    unittest.main()
