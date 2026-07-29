#!/usr/bin/env python3
"""Create a valid ticket in one invocation.

This module owns ticket creation for the whole project. The command-line tool
and ``POST /api/tickets`` both call :func:`create_ticket`, so allocation,
frontmatter, the high-water mark, and board regeneration have exactly one
implementation and cannot drift apart on the rollback path.

The caller supplies the ticket body and never the frontmatter, and never the
id: ids are assigned by the project. Allocation stays reserve-by-create, and
the reservation is keyed on the id alone so two processes writing different
titles cannot claim the same number.
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Sequence

try:  # Portable copies live beside the generator inside .kanban/tools/.
    from regenerate_board import (
        ValidationError,
        _frontmatter,
        allocate_ticket_id,
        discover_kanban,
        load_board_config,
        regenerate_board,
        ticket_number,
    )
except ImportError:  # Running from the canonical checkout as tools.create_ticket.
    from tools.regenerate_board import (
        ValidationError,
        _frontmatter,
        allocate_ticket_id,
        discover_kanban,
        load_board_config,
        regenerate_board,
        ticket_number,
    )


VALIDATION_ERROR = 2
ID_ALLOCATION_ATTEMPTS = 5
CLAIM_TIMEOUT_SECONDS = 30


class CreationRolledBack(ValidationError):
    """The ticket was written, then removed because the board failed to validate.

    Distinct from a plain ValidationError, which means the board was already
    invalid and no id was ever assigned. Callers report the two differently:
    only this one means a write happened and was undone.
    """

DEFAULT_STATUS = "inbox"
DEFAULT_CATEGORY = "General"
DEFAULT_INTERVENTION = "low"
DEFAULT_PRIORITY = "medium"
DEFAULT_TYPE = "feature"
DEFAULT_SOURCE = ("cli",)

DEFAULT_TEMPLATE = """## Goal

Describe the outcome this ticket should produce.

## Context

Add the project knowledge an agent needs before starting.

## Acceptance criteria

- [ ] Define a concrete, verifiable result.

## Human work

State any decisions, editor wiring, art, review, or testing needed from a person.
"""

# Keyed by ticket type. Only the shared default exists today; per-type bodies
# belong here rather than in any caller.
BODY_TEMPLATES: dict[str, str] = {}


@dataclass
class TicketFields:
    """Everything the caller chooses about a new ticket except its id."""

    title: str
    status: str = DEFAULT_STATUS
    category: str = DEFAULT_CATEGORY
    intervention: str = DEFAULT_INTERVENTION
    priority: str = DEFAULT_PRIORITY
    type: str = DEFAULT_TYPE
    blocked_by: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    source: list[str] = field(default_factory=lambda: list(DEFAULT_SOURCE))


REPLACE_ATTEMPTS = 10


def replace_with_retry(source: str | Path, destination: Path) -> None:
    """Rename over a destination, tolerating brief Windows sharing conflicts.

    On Windows a replace fails outright when another process momentarily holds
    the destination open, which two agents creating tickets at the same time
    will do to board.yaml. Elsewhere the first attempt always wins.
    """

    for attempt in range(REPLACE_ATTEMPTS):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(0.01 * (attempt + 1))


def atomic_write(path: Path, content: str, newline: str = "\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", text=True
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline=newline) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        replace_with_retry(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def exclusive_write(path: Path, content: str) -> None:
    """Create a file with its full contents, or fail if the name is taken.

    Ticket ids are reserved by winning this create, so a concurrent agent
    cannot be handed the same id between the scan and the write.

    The content is written to a temporary file and linked into place, so the
    ticket never exists on disk half-written. That matters because another
    process may be scanning the ticket directory to regenerate the board at
    the same moment, and a partial read there would fail validation and roll
    back that process's own, perfectly valid, ticket.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", text=True
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        try:
            os.link(temporary_name, path)
        except (AttributeError, NotImplementedError, OSError) as error:
            # Filesystems without hard links fall back to an exclusive create.
            # The reservation stays correct; only the partial-read window
            # returns.
            if isinstance(error, OSError) and error.errno == errno.EEXIST:
                raise FileExistsError(str(path)) from error
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as fallback:
                fallback.write(content)
                fallback.flush()
                os.fsync(fallback.fileno())
    finally:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "ticket"


def record_id_sequence(kanban: Path, number: int) -> str | None:
    """Raise the recorded high-water mark, returning the replaced file text.

    board.yaml is edited a line at a time because the parser is deliberately
    lossy: rewriting it would discard comments and unknown configuration.
    """

    path = kanban / "board.yaml"
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            original = handle.read()
    except OSError:
        return None

    # Stop at the newline rather than at '$' so a CRLF file does not lose the
    # carriage return on the one line being rewritten.
    pattern = re.compile(r"^id_sequence:[^\n]*", re.MULTILINE)
    match = pattern.search(original)
    if match:
        carriage = "\r" if match.group(0).endswith("\r") else ""
        updated = (
            original[: match.start()]
            + f"id_sequence: {number}{carriage}"
            + original[match.end() :]
        )
    else:
        ending = "\r\n" if "\r\n" in original else "\n"
        separator = "" if not original or original.endswith(("\n", "\r")) else ending
        updated = f"{original}{separator}id_sequence: {number}{ending}"
    if updated == original:
        return None
    atomic_write(path, updated, newline="")
    return original


def default_body(ticket_type: str) -> str:
    """Return the body template for a ticket type."""

    return BODY_TEMPLATES.get(ticket_type, DEFAULT_TEMPLATE)


def _inline_list(values: Sequence[str]) -> str:
    quoted = [
        f'"{value}"' if value != value.strip() or "," in value else value
        for value in values
    ]
    return f"[{', '.join(quoted)}]"


def render_ticket(ticket_id: str, fields: TicketFields, body: str) -> str:
    """Render the complete ticket file, frontmatter included."""

    today = date.today().isoformat()
    frontmatter = "\n".join(
        (
            f"id: {ticket_id}",
            f"title: {fields.title}",
            f"status: {fields.status}",
            f"category: {fields.category}",
            f"intervention: {fields.intervention}",
            f"priority: {fields.priority}",
            f"type: {fields.type}",
            f"blocked_by: {_inline_list(fields.blocked_by)}",
            f"tags: {_inline_list(fields.tags)}",
            f"source: {_inline_list(fields.source)}",
            f"created: {today}",
            f"updated: {today}",
        )
    )
    return f"---\n{frontmatter}\n---\n\n{body.strip()}\n"


def validate_fields(kanban: Path, fields: TicketFields) -> None:
    """Check the values this module owns against the project configuration.

    Only what the generator itself enforces is checked here. Everything else —
    unknown dependencies, duplicate ids — is caught by the regenerate step,
    which rolls the creation back, so there is no second set of rules to keep
    in step with the generator.
    """

    config = load_board_config(kanban)
    errors: list[str] = []
    if not fields.title.strip():
        errors.append("a ticket title is required")
    for name, value in (
        ("title", fields.title),
        ("category", fields.category),
        ("priority", fields.priority),
        ("type", fields.type),
    ):
        if "\n" in value or "\r" in value:
            errors.append(f"'{name}' cannot contain a line break")
    if fields.status not in config.statuses:
        errors.append(
            f"invalid status '{fields.status}'; "
            f"expected one of {', '.join(config.statuses)}"
        )
    if fields.intervention not in config.intervention_levels:
        errors.append(
            f"invalid intervention '{fields.intervention}'; "
            f"expected one of {', '.join(config.intervention_levels)}"
        )
    if errors:
        raise ValidationError(errors)


def _id_is_held_elsewhere(kanban: Path, ticket_id: str, reserved: Path) -> bool:
    """Report whether any file other than our reservation carries this id."""

    paths = [*(kanban / "tickets").glob("*.md")]
    archive = kanban / "archive"
    if archive.is_dir():
        paths.extend(archive.rglob("*.md"))
    for path in paths:
        if path == reserved:
            continue
        try:
            if str(_frontmatter(path).get("id", "")).strip() == ticket_id:
                return True
        except ValidationError:
            continue
    return False


def _write_ticket_file(
    tickets_directory: Path, ticket_id: str, title: str, content: str
) -> Path:
    """Write the ticket exactly once, at the best name that is free.

    The id is identity and the slug is only readability, so an unrelated file
    already holding the descriptive name costs the ticket its slug, never its
    contents, and never overwrites a file this tool did not create.
    """

    descriptive = tickets_directory / f"{ticket_id}-{safe_slug(title)}.md"
    try:
        exclusive_write(descriptive, content)
        return descriptive
    except FileExistsError:
        plain = tickets_directory / f"{ticket_id}.md"
        exclusive_write(plain, content)
        return plain


def reserve_ticket_id(
    kanban: Path, title: str, build_source: Callable[[str], str]
) -> tuple[str, Path]:
    """Claim the next project id, then write the ticket that holds it.

    The claim is an exclusive create keyed on the id alone, so two callers
    choosing different titles cannot both win the same number — the defect in
    keying the reservation on the descriptive filename.

    The marker is deliberately not a ``.md`` file. A reservation that turns out
    to have lost the race is abandoned, and if that abandoned file were visible
    to a board scan, an unrelated process regenerating at that instant would
    see a duplicate id and roll back its own perfectly valid ticket. Nothing
    enters the ticket directory until the number is certain, and then it enters
    complete and named once.

    The marker is released on every path. One left behind by a killed process
    burns nothing: it is invisible to allocation, and the next caller clears it
    once it is older than a live claim could be.
    """

    tickets_directory = kanban / "tickets"
    for attempt in range(ID_ALLOCATION_ATTEMPTS):
        ticket_id = allocate_ticket_id(kanban)
        claim = tickets_directory / f".{ticket_id}.claim"
        try:
            exclusive_write(claim, f"{ticket_id}\n")
        except FileExistsError:
            # Another process is mid-claim on this number. Its ticket is not
            # visible yet, so re-allocating immediately would return the same
            # id; wait for it to land, or clear the marker if it never will.
            if _claim_is_stale(claim):
                claim.unlink(missing_ok=True)
            else:
                time.sleep(0.02 * (attempt + 1))
            continue
        try:
            if _id_is_held_elsewhere(kanban, ticket_id, claim):
                continue
            return ticket_id, _write_ticket_file(
                tickets_directory, ticket_id, title, build_source(ticket_id)
            )
        finally:
            claim.unlink(missing_ok=True)
    raise FileExistsError("could not reserve a ticket id")


def _claim_is_stale(claim: Path) -> bool:
    """Report whether a claim marker was abandoned by a crashed process.

    A claim is held for milliseconds, so anything older than the timeout is
    debris rather than a live reservation.
    """

    try:
        return (time.time() - claim.stat().st_mtime) > CLAIM_TIMEOUT_SECONDS
    except OSError:
        return False


def create_ticket(
    kanban: Path, fields: TicketFields, body: str | None = None
) -> tuple[str, Path]:
    """Create one ticket, returning its assigned id and path.

    On any validation failure nothing is left behind: no ticket file, no
    consumed id, and no raised high-water mark.
    """

    kanban = Path(kanban).resolve()
    validate_fields(kanban, fields)
    content = body if body and body.strip() else default_body(fields.type)

    ticket_id, path = reserve_ticket_id(
        kanban,
        fields.title,
        lambda assigned: render_ticket(assigned, fields, content),
    )

    config = load_board_config(kanban)
    number = ticket_number(ticket_id, config.id_prefix)
    previous_config = record_id_sequence(kanban, number) if number else None
    try:
        regenerate_board(kanban)
    except ValidationError as error:
        path.unlink(missing_ok=True)
        if previous_config is not None:
            atomic_write(kanban / "board.yaml", previous_config, newline="")
        raise CreationRolledBack(error.messages) from error
    return ticket_id, path


def _split_options(values: Sequence[str] | None) -> list[str]:
    """Accept both repeated flags and comma-separated values."""

    items: list[str] = []
    for value in values or ():
        items.extend(part.strip() for part in value.split(",") if part.strip())
    return items


def _read_body(arguments: argparse.Namespace) -> str | None:
    # Windows shells prepend a byte-order mark when piping or writing UTF-8,
    # and it would otherwise land in the first line of the ticket body.
    if arguments.body_stdin or arguments.body_file == "-":
        return sys.stdin.read().lstrip("﻿")
    if arguments.body_file:
        path = Path(arguments.body_file)
        try:
            return path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as error:
            raise ValidationError([f"{path}: cannot read ticket body: {error}"])
    return None


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a ticket, assigning its id and regenerating the board."
    )
    parser.add_argument("--title", required=True, help="ticket title")
    parser.add_argument(
        "--kanban", type=Path, help="explicit path to the .kanban directory"
    )
    parser.add_argument(
        "--status", default=DEFAULT_STATUS, help="initial status (default: inbox)"
    )
    parser.add_argument(
        "--category", default=DEFAULT_CATEGORY, help="category (default: General)"
    )
    parser.add_argument(
        "--intervention",
        default=DEFAULT_INTERVENTION,
        help="intervention level (default: low)",
    )
    parser.add_argument(
        "--priority", default=DEFAULT_PRIORITY, help="priority (default: medium)"
    )
    parser.add_argument(
        "--type", default=DEFAULT_TYPE, help="ticket type (default: feature)"
    )
    parser.add_argument(
        "--tags", action="append", help="comma-separated tags; may be repeated"
    )
    parser.add_argument(
        "--blocked-by",
        action="append",
        help="comma-separated blocking ticket ids; may be repeated",
    )
    parser.add_argument(
        "--source",
        action="append",
        help="comma-separated source references; may be repeated",
    )
    body = parser.add_mutually_exclusive_group()
    body.add_argument(
        "--body-file",
        help="read the ticket body from a file, or from '-' for standard input",
    )
    body.add_argument(
        "--body-stdin",
        action="store_true",
        help="read the ticket body from standard input",
    )
    parser.add_argument(
        "--id",
        help=argparse.SUPPRESS,  # Accepted only so it can be refused explicitly.
    )
    parser.add_argument(
        "--json", action="store_true", help="print the result as JSON for chaining"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    arguments = _argument_parser().parse_args(argv)

    try:
        if arguments.id:
            raise ValidationError(
                [
                    "ticket ids are assigned by the project and cannot be chosen; "
                    "omit --id"
                ]
            )
        kanban = (
            arguments.kanban.resolve()
            if arguments.kanban is not None
            else discover_kanban()
        )
        body = _read_body(arguments)
        fields = TicketFields(
            title=arguments.title.strip(),
            status=arguments.status,
            category=arguments.category,
            intervention=arguments.intervention,
            priority=arguments.priority,
            type=arguments.type,
            blocked_by=_split_options(arguments.blocked_by),
            tags=_split_options(arguments.tags),
            source=_split_options(arguments.source) or list(DEFAULT_SOURCE),
        )
        ticket_id, path = create_ticket(kanban, fields, body)
    except ValidationError as error:
        for message in error.messages:
            print(f"error: {message}", file=sys.stderr)
        return VALIDATION_ERROR
    except FileExistsError as error:
        print(f"error: {error}", file=sys.stderr)
        return VALIDATION_ERROR

    if arguments.json:
        print(json.dumps({"id": ticket_id, "path": str(path)}))
    else:
        print(f"{ticket_id}  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
