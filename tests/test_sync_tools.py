import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import sync_tools as synchronizer


class SyncToolsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name)
        self.kanban = self.project / ".kanban"
        self.kanban.mkdir()
        self.canonical = Path(synchronizer.__file__).resolve().parent

    def tearDown(self):
        self.temporary.cleanup()

    def run_main(self, *arguments):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = synchronizer.main([*arguments, str(self.project)])
        return code, stdout.getvalue(), stderr.getvalue()

    def assert_portable_tools_match(self):
        for name in synchronizer.PORTABLE_TOOLS:
            self.assertEqual(
                (self.kanban / "tools" / name).read_bytes(),
                (self.canonical / name).read_bytes(),
            )

    def test_fresh_copy_adds_every_manifest_tool(self):
        code, stdout, stderr = self.run_main()

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assert_portable_tools_match()
        self.assertEqual(stdout.count(": added"), len(synchronizer.PORTABLE_TOOLS))
        self.assertFalse((self.kanban / "tools" / "sync_tools.py").exists())

    def test_up_to_date_copy_is_a_no_op(self):
        synchronizer.sync_tools(self.project)
        paths = [
            self.kanban / "tools" / name for name in synchronizer.PORTABLE_TOOLS
        ]
        mtimes = {path: path.stat().st_mtime_ns for path in paths}

        code, stdout, _ = self.run_main()

        self.assertEqual(code, 0)
        self.assertEqual(stdout.count(": already current"), len(paths))
        self.assertEqual({path: path.stat().st_mtime_ns for path in paths}, mtimes)

    def test_stale_file_is_refreshed(self):
        synchronizer.sync_tools(self.project)
        stale = self.kanban / "tools" / synchronizer.PORTABLE_TOOLS[0]
        stale.write_bytes(b"stale")

        code, stdout, _ = self.run_main()

        self.assertEqual(code, 0)
        self.assertIn(f"{stale}: updated", stdout)
        self.assertEqual(
            stale.read_bytes(),
            (self.canonical / synchronizer.PORTABLE_TOOLS[0]).read_bytes(),
        )

    def test_missing_file_is_added_to_an_existing_tools_directory(self):
        synchronizer.sync_tools(self.project)
        missing = self.kanban / "tools" / synchronizer.PORTABLE_TOOLS[1]
        missing.unlink()

        code, stdout, _ = self.run_main()

        self.assertEqual(code, 0)
        self.assertIn(f"{missing}: added", stdout)
        self.assert_portable_tools_match()

    def test_check_passes_when_every_tool_is_current(self):
        synchronizer.sync_tools(self.project)

        code, stdout, stderr = self.run_main("--check")

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(
            stdout.count(": already current"), len(synchronizer.PORTABLE_TOOLS)
        )

    def test_check_reports_drift_without_writing(self):
        tools = self.kanban / "tools"
        tools.mkdir()
        stale = tools / synchronizer.PORTABLE_TOOLS[0]
        stale.write_bytes(b"stale")

        code, stdout, stderr = self.run_main("--check")

        self.assertEqual(code, synchronizer.DRIFT_FOUND)
        self.assertEqual(stderr, "")
        self.assertIn(f"{stale}: differs (would be updated)", stdout)
        self.assertIn("missing (would be added)", stdout)
        self.assertEqual(stale.read_bytes(), b"stale")
        self.assertFalse((tools / synchronizer.PORTABLE_TOOLS[1]).exists())

    def test_check_does_not_create_a_missing_tools_directory(self):
        code, stdout, stderr = self.run_main("--check")

        self.assertEqual(code, synchronizer.DRIFT_FOUND)
        self.assertEqual(stderr, "")
        self.assertEqual(
            stdout.count("missing (would be added)"),
            len(synchronizer.PORTABLE_TOOLS),
        )
        self.assertFalse((self.kanban / "tools").exists())

    def test_missing_kanban_is_an_error_and_creates_nothing(self):
        self.kanban.rmdir()

        code, _, stderr = self.run_main()

        self.assertEqual(code, synchronizer.SYNC_ERROR)
        self.assertIn("no .kanban directory", stderr)
        self.assertFalse(self.kanban.exists())

    def test_target_is_the_project_root_not_the_kanban_directory(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = synchronizer.main([str(self.kanban)])

        self.assertEqual(code, synchronizer.SYNC_ERROR)
        self.assertIn("no .kanban directory", stderr.getvalue())

    def test_failed_second_write_rolls_back_the_first(self):
        destinations = [
            self.kanban / "tools" / name for name in synchronizer.PORTABLE_TOOLS
        ]
        real_replace = os.replace
        failed = False

        def fail_second_replace(source, destination):
            nonlocal failed
            if Path(destination) == destinations[1] and not failed:
                failed = True
                raise OSError("simulated failure")
            return real_replace(source, destination)

        with mock.patch.object(synchronizer.os, "replace", fail_second_replace):
            with self.assertRaises(synchronizer.SyncError):
                synchronizer.sync_tools(self.project)

        self.assertFalse((self.kanban / "tools").exists())


if __name__ == "__main__":
    unittest.main()
