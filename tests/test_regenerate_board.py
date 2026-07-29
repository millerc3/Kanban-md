import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import regenerate_board as board_generator


BOARD_YAML = """\
version: 1
name: Test Board
statuses: [inbox, ready, in_progress, blocked, review, done]
categories:
  - Core
  - "User Experience"
intervention_levels: [low, medium, high]
"""


class BoardGeneratorTests(unittest.TestCase):
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
        title=None,
        status="ready",
        category="Core",
        intervention="low",
        blocked_by="[]",
        tags="[]",
        source="[test]",
        archive=False,
        extra="",
    ):
        directory = (
            self.kanban / "archive" / "2025"
            if archive
            else self.kanban / "tickets"
        )
        path = directory / f"{ticket_id}.md"
        path.write_text(
            f"""\
---
id: {ticket_id}
title: {title or ticket_id}
status: {status}
category: {category}
intervention: {intervention}
type: feature
blocked_by: {blocked_by}
tags: {tags}
source: {source}
{extra}---

Ticket body.
""",
            encoding="utf-8",
        )
        return path

    def run_cli(self, *arguments):
        script = Path(board_generator.__file__)
        return subprocess.run(
            [sys.executable, str(script), "--kanban", str(self.kanban), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def test_generation_groups_planning_states_and_keeps_work_flat(self):
        self.write_ticket("A1", status="inbox", category="User Experience")
        self.write_ticket("A2", status="ready")
        self.write_ticket("A3", status="blocked", blocked_by="[A2]")
        self.write_ticket("A4", status="in_progress")
        self.write_ticket("A5", status="review")
        self.write_ticket("A6", status="done")
        self.write_ticket("OLD1", status="done", archive=True)

        content = board_generator.generate_board(self.kanban)

        self.assertTrue(content.startswith("<!--\nGENERATED FILE — DO NOT EDIT"))
        self.assertIn("## Inbox\n\n### User Experience", content)
        self.assertIn("## Ready\n\n### Core", content)
        self.assertIn("## Blocked\n\n### Core", content)
        self.assertIn("## In Progress\n\n| ID | Ticket | Category |", content)
        self.assertIn("## Review\n\n| ID | Ticket | Category |", content)
        self.assertIn("## Done\n\n| ID | Ticket | Category |", content)
        self.assertIn("1 archived ticket retained", content)
        self.assertNotIn("| OLD1 |", content)

    def test_natural_id_order_is_deterministic(self):
        self.write_ticket("A10")
        self.write_ticket("A9")
        first = board_generator.generate_board(self.kanban)
        second = board_generator.generate_board(self.kanban)
        self.assertEqual(first, second)
        self.assertLess(first.index("| A9 |"), first.index("| A10 |"))

    def test_escapes_markdown_table_pipes(self):
        self.write_ticket("A1", title='"Render | safely"')
        content = board_generator.generate_board(self.kanban)
        self.assertIn("Render \\| safely", content)
        self.assertNotIn("| Render | safely |", content)

    def test_inline_and_block_lists_and_unknown_fields(self):
        self.write_ticket(
            "DONE1",
            status="done",
            archive=True,
            tags="",
            source="",
            extra="""\
  - alpha
  - "beta value"
source:
  - docs/example.md
unknown_future_field: preserved-by-ticket-owner
""",
        )
        self.write_ticket(
            "A1",
            blocked_by="[DONE1]",
            tags="['one', \"two\"]",
            source='["docs/source.md"]',
            extra="unknown_inline: ignored\n",
        )
        content = board_generator.generate_board(self.kanban)
        self.assertIn("| A1 |", content)
        self.assertIn("DONE1", content)

    def test_source_preserves_markdown_heading_fragment(self):
        self.write_ticket(
            "A1",
            source="[docs/design.md#sacrifice-wallet]",
        )

        _, active, _ = board_generator.load_and_validate(self.kanban)

        self.assertEqual(
            active[0].source,
            ("docs/design.md#sacrifice-wallet",),
        )

    def test_archived_id_satisfies_dependency_validation(self):
        self.write_ticket("OLD1", status="done", archive=True)
        self.write_ticket("A1", blocked_by="[OLD1]")
        board_generator.generate_board(self.kanban)

    def test_duplicate_active_archive_id_is_rejected(self):
        self.write_ticket("A1")
        archived = self.write_ticket("A1-copy", archive=True)
        archived.write_text(
            archived.read_text(encoding="utf-8").replace("id: A1-copy", "id: A1"),
            encoding="utf-8",
        )
        with self.assertRaises(board_generator.ValidationError) as caught:
            board_generator.generate_board(self.kanban)
        self.assertIn("duplicate ticket id 'A1'", str(caught.exception))
        self.assertIn("A1.md", str(caught.exception))
        self.assertIn("A1-copy.md", str(caught.exception))

    def test_board_reports_the_state_of_each_blocker(self):
        self.write_ticket("OLD1", status="done", archive=True)
        self.write_ticket("A1", status="done")
        self.write_ticket("A2", status="ready")
        self.write_ticket("A3", blocked_by="[A1, A2, OLD1]")

        content = board_generator.generate_board(self.kanban)

        self.assertIn("A1 (done), A2 (ready), OLD1 (done)", content)

    def test_blocker_state_treats_only_done_as_satisfied(self):
        self.assertEqual(board_generator.blocker_state("done"), "satisfied")
        self.assertEqual(board_generator.blocker_state("ready"), "unfinished")
        self.assertEqual(board_generator.blocker_state("review"), "unfinished")
        self.assertEqual(board_generator.blocker_state(None), "unknown")

    def test_blocker_states_keep_ticket_order_and_carry_ids(self):
        states = board_generator.blocker_states(
            ["A2", "A1", "GONE"], {"A1": "done", "A2": "ready"}
        )
        self.assertEqual(
            states,
            [
                {"id": "A2", "status": "ready", "state": "unfinished"},
                {"id": "A1", "status": "done", "state": "satisfied"},
                {"id": "GONE", "status": "", "state": "unknown"},
            ],
        )

    def test_collected_statuses_span_active_and_archive(self):
        self.write_ticket("A1", status="ready")
        self.write_ticket("OLD1", status="done", archive=True)
        self.write_ticket("OLD2", status="inbox", archive=True)

        statuses = board_generator.collect_ticket_statuses(self.kanban)

        self.assertEqual(
            statuses, {"A1": "ready", "OLD1": "done", "OLD2": "inbox"}
        )
        self.assertEqual(
            board_generator.blocker_state(statuses["OLD1"]), "satisfied"
        )
        self.assertEqual(
            board_generator.blocker_state(statuses["OLD2"]), "unfinished"
        )

    def test_collected_statuses_skip_malformed_files_without_raising(self):
        self.write_ticket("A1", status="done")
        (self.kanban / "tickets" / "BROKEN.md").write_text(
            "no frontmatter here\n", encoding="utf-8"
        )

        statuses = board_generator.collect_ticket_statuses(self.kanban)

        self.assertEqual(statuses, {"A1": "done"})
        self.assertEqual(board_generator.blocker_state(statuses.get("B1")), "unknown")

    def test_missing_dependency_is_rejected(self):
        path = self.write_ticket("A1", blocked_by="[MISSING]")
        with self.assertRaises(board_generator.ValidationError) as caught:
            board_generator.generate_board(self.kanban)
        self.assertIn(str(path), str(caught.exception))
        self.assertIn("dependency 'MISSING'", str(caught.exception))

    def test_self_dependency_is_rejected(self):
        self.write_ticket("A1", blocked_by="[A1]")
        with self.assertRaises(board_generator.ValidationError) as caught:
            board_generator.generate_board(self.kanban)
        self.assertIn("cannot depend on itself", str(caught.exception))

    def test_invalid_status_and_intervention_are_rejected(self):
        self.write_ticket("A1", status="invented", intervention="automatic")
        with self.assertRaises(board_generator.ValidationError) as caught:
            board_generator.generate_board(self.kanban)
        message = str(caught.exception)
        self.assertIn("invalid status 'invented'", message)
        self.assertIn("invalid intervention 'automatic'", message)

    def set_id_scheme(self, *lines):
        path = self.kanban / "board.yaml"
        path.write_text(
            path.read_text(encoding="utf-8") + "".join(f"{line}\n" for line in lines),
            encoding="utf-8",
        )

    def test_next_id_uses_the_highest_number_in_use(self):
        self.set_id_scheme("id_prefix: TB", "id_padding: 3")
        self.write_ticket("TB-001")
        self.write_ticket("TB-009", archive=True)
        self.write_ticket("legacy-thing")

        self.assertEqual(board_generator.allocate_ticket_id(self.kanban), "TB-010")

    def test_next_id_respects_the_recorded_high_water_mark(self):
        self.set_id_scheme("id_prefix: TB", "id_sequence: 42")
        self.write_ticket("TB-002")

        self.assertEqual(board_generator.allocate_ticket_id(self.kanban), "TB-043")

    def test_next_id_widens_past_the_configured_padding(self):
        self.set_id_scheme("id_prefix: TB", "id_padding: 2", "id_sequence: 99")

        self.assertEqual(board_generator.allocate_ticket_id(self.kanban), "TB-100")

    def test_next_id_requires_an_adopted_scheme(self):
        self.write_ticket("A1")

        with self.assertRaises(board_generator.ValidationError) as raised:
            board_generator.allocate_ticket_id(self.kanban)
        self.assertIn("id_prefix", raised.exception.messages[0])

    def test_mixed_padding_keeps_natural_order(self):
        self.set_id_scheme("id_prefix: TB")
        self.write_ticket("TB-009")
        self.write_ticket("TB-010")
        self.write_ticket("TB-0002")

        board = board_generator.generate_board(self.kanban)
        self.assertLess(board.index("TB-0002"), board.index("TB-009"))
        self.assertLess(board.index("TB-009"), board.index("TB-010"))

    def test_invalid_id_prefix_is_rejected(self):
        self.set_id_scheme("id_prefix: 9bad")

        with self.assertRaises(board_generator.ValidationError) as raised:
            board_generator.load_board_config(self.kanban)
        self.assertIn("id_prefix", raised.exception.messages[0])

    def test_non_numeric_id_sequence_is_rejected(self):
        self.set_id_scheme("id_sequence: soon")

        with self.assertRaises(board_generator.ValidationError) as raised:
            board_generator.load_board_config(self.kanban)
        self.assertIn("whole number", raised.exception.messages[0])

    def test_strict_ids_reports_only_nonconforming_tickets(self):
        self.set_id_scheme("id_prefix: TB")
        self.write_ticket("TB-001")
        self.write_ticket("OLD-7")

        problems = board_generator.nonconforming_ids(self.kanban)

        self.assertEqual(len(problems), 1)
        self.assertIn("OLD-7", problems[0])

    def test_cli_next_id_and_strict_ids(self):
        self.set_id_scheme("id_prefix: TB")
        self.write_ticket("TB-004")
        self.write_ticket("OLD-7")

        printed = self.run_cli("--next-id")
        self.assertEqual(printed.returncode, 0)
        self.assertEqual(printed.stdout.strip(), "TB-005")
        self.assertFalse((self.kanban / "board.md").exists())

        strict = self.run_cli("--strict-ids")
        self.assertEqual(strict.returncode, 2)
        self.assertIn("OLD-7", strict.stderr)

        lenient = self.run_cli()
        self.assertEqual(lenient.returncode, 0)

    def test_check_success_and_stale_board_failure(self):
        self.write_ticket("A1")
        board_generator.regenerate_board(self.kanban)
        current = self.run_cli("--check")
        self.assertEqual(current.returncode, 0, current.stderr)

        (self.kanban / "board.md").write_text("stale\n", encoding="utf-8")
        stale = self.run_cli("--check")
        self.assertEqual(stale.returncode, board_generator.STALE_BOARD)
        self.assertIn("stale", stale.stderr)

    def test_validation_error_has_distinct_cli_status(self):
        self.write_ticket("A1", status="invalid")
        result = self.run_cli("--check")
        self.assertEqual(result.returncode, board_generator.VALIDATION_ERROR)

    def test_stdout_does_not_write(self):
        self.write_ticket("A1")
        result = self.run_cli("--stdout")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("# Test Board board", result.stdout)
        self.assertFalse((self.kanban / "board.md").exists())

    def test_atomic_regeneration_and_identical_content_noop(self):
        self.write_ticket("A1")
        with mock.patch.object(
            board_generator.os, "replace", wraps=board_generator.os.replace
        ) as replace:
            self.assertTrue(board_generator.regenerate_board(self.kanban))
            replace.assert_called_once()
            temporary_path, destination = replace.call_args.args
            self.assertEqual(Path(temporary_path).parent, self.kanban)
            self.assertEqual(Path(destination), self.kanban / "board.md")

        original_mtime = (self.kanban / "board.md").stat().st_mtime_ns
        with mock.patch.object(board_generator.os, "replace") as replace:
            self.assertFalse(board_generator.regenerate_board(self.kanban))
            replace.assert_not_called()
        self.assertEqual(
            (self.kanban / "board.md").stat().st_mtime_ns, original_mtime
        )


if __name__ == "__main__":
    unittest.main()
