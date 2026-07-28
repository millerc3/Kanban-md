"""Synchronize canonical portable tools into an existing .kanban project."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import Sequence


PORTABLE_TOOLS = ("regenerate_board.py", "migrate_ticket_ids.py")
DRIFT_FOUND = 1
SYNC_ERROR = 2


class SyncError(Exception):
    """A failure that should be reported cleanly by the command-line tool."""


def resolve_target(supplied: str | Path) -> Path:
    """Resolve a project root using the same rules as POST /api/open."""

    try:
        target = Path(supplied).expanduser().resolve()
    except (OSError, RuntimeError) as error:
        raise SyncError(f"cannot resolve target project: {error}") from error
    if not target.is_dir():
        raise SyncError(f"target project directory does not exist: {target}")
    if not (target / ".kanban").is_dir():
        raise SyncError(
            f"{target}: no .kanban directory; initialize the project in the app first"
        )
    return target


def _atomic_write(destination: Path, content: bytes) -> None:
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, destination)
        temporary_name = ""
    except OSError as error:
        raise SyncError(
            f"{destination}: cannot atomically write tool: {error}"
        ) from error
    finally:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def _tool_states(
    target: Path,
) -> list[tuple[Path, bytes, bytes | None, str]]:
    source_directory = Path(__file__).resolve().parent
    destination_directory = target / ".kanban" / "tools"
    states = []
    for name in PORTABLE_TOOLS:
        source = source_directory / name
        destination = destination_directory / name
        try:
            canonical = source.read_bytes()
        except OSError as error:
            raise SyncError(f"{source}: cannot read canonical tool: {error}") from error
        try:
            existing = destination.read_bytes()
        except FileNotFoundError:
            existing = None
        except OSError as error:
            raise SyncError(
                f"{destination}: cannot read portable tool: {error}"
            ) from error
        status = (
            "added"
            if existing is None
            else "already current"
            if existing == canonical
            else "updated"
        )
        states.append((destination, canonical, existing, status))
    return states


def sync_tools(
    supplied_target: str | Path, *, check: bool = False
) -> list[tuple[Path, str]]:
    """Check or synchronize the portable tools for one project."""

    target = resolve_target(supplied_target)
    states = _tool_states(target)
    results = [(destination, status) for destination, _, _, status in states]
    if check or all(status == "already current" for _, status in results):
        return results

    destination_directory = target / ".kanban" / "tools"
    directory_existed = destination_directory.exists()
    try:
        destination_directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise SyncError(
            f"{destination_directory}: cannot create tools directory: {error}"
        ) from error

    committed: list[tuple[Path, bytes | None]] = []
    try:
        for destination, canonical, existing, status in states:
            if status == "already current":
                continue
            _atomic_write(destination, canonical)
            committed.append((destination, existing))
    except SyncError as write_error:
        rollback_errors = []
        for destination, existing in reversed(committed):
            try:
                if existing is None:
                    destination.unlink()
                else:
                    _atomic_write(destination, existing)
            except (OSError, SyncError) as rollback_error:
                rollback_errors.append(f"{destination}: {rollback_error}")
        if not directory_existed:
            try:
                destination_directory.rmdir()
            except OSError as rollback_error:
                rollback_errors.append(
                    f"{destination_directory}: cannot remove directory: {rollback_error}"
                )
        if rollback_errors:
            raise SyncError(
                f"{write_error}; rollback also failed: {'; '.join(rollback_errors)}"
            ) from write_error
        raise
    return results


def _argument_parser() -> argparse.ArgumentParser:
    # Unlike ticket migration, synchronization applies by default: these files
    # are disposable copies of canonical sources, not authored project data.
    parser = argparse.ArgumentParser(
        description="Sync canonical portable tools into an existing project."
    )
    parser.add_argument("target_project", help="project root containing .kanban")
    parser.add_argument(
        "--check",
        action="store_true",
        help="report missing or stale tools without writing anything",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    arguments = _argument_parser().parse_args(argv)
    try:
        results = sync_tools(arguments.target_project, check=arguments.check)
    except SyncError as error:
        print(f"error: {error}", file=sys.stderr)
        return SYNC_ERROR

    drift = False
    for destination, status in results:
        if arguments.check and status == "added":
            print(f"{destination}: missing (would be added)")
            drift = True
        elif arguments.check and status == "updated":
            print(f"{destination}: differs (would be updated)")
            drift = True
        else:
            print(f"{destination}: {status}")
    return DRIFT_FOUND if arguments.check and drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
