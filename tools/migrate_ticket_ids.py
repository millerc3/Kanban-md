#!/usr/bin/env python3
"""Adopt project-assigned ticket ids in an existing .kanban project.

Two migrations are possible:

``--adopt``
    Record the id scheme in ``board.yaml`` and seed the high-water mark above
    every existing id. No ticket file is touched, so ids already in use stay
    exactly as they are and only new tickets follow the scheme.

``--renumber``
    Additionally rewrite ids that do not match the scheme, remapping every
    ``blocked_by`` reference and renaming the affected files. Ids that already
    conform keep their number. ``--renumber-all`` instead assigns a clean
    sequence to every ticket.

Both modes report their plan and change nothing unless ``--apply`` is given.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

try:  # Portable copies live beside the generator inside .kanban/tools/.
    from regenerate_board import (
        DEFAULT_ID_PADDING,
        ID_PREFIX_PATTERN,
        BoardConfig,
        Ticket,
        ValidationError,
        _frontmatter,
        _split_inline_list,
        discover_kanban,
        format_ticket_id,
        highest_ticket_number,
        load_and_validate,
        natural_key,
        regenerate_board,
        ticket_number,
    )
except ImportError:  # Imported as part of the tools package instead.
    from tools.regenerate_board import (  # type: ignore[no-redef]
        DEFAULT_ID_PADDING,
        ID_PREFIX_PATTERN,
        BoardConfig,
        Ticket,
        ValidationError,
        _frontmatter,
        _split_inline_list,
        discover_kanban,
        format_ticket_id,
        highest_ticket_number,
        load_and_validate,
        natural_key,
        regenerate_board,
        ticket_number,
    )


MIGRATION_ERROR = 2
BACKUP_STAMP = "%Y%m%d-%H%M%S"


@dataclass(frozen=True)
class Rename:
    ticket: Ticket
    new_id: str
    new_path: Path
    content: str


@dataclass(frozen=True)
class Plan:
    kanban: Path
    prefix: str
    padding: int
    sequence: int
    renames: tuple[Rename, ...]
    stray_references: tuple[str, ...]


def derive_prefix(name: str) -> str:
    """Derive a short prefix from a project directory name."""

    words = re.sub(r"[^A-Za-z0-9]+", " ", name).split()
    if not words:
        return "TASK"
    candidate = (
        words[0][:4] if len(words) == 1 else "".join(word[0] for word in words)[:4]
    )
    candidate = candidate.upper()
    return candidate if candidate[0].isalpha() else f"T{candidate}"


def resolve_prefix(kanban: Path, config: BoardConfig, requested: str | None) -> str:
    if requested:
        if not ID_PREFIX_PATTERN.match(requested):
            raise ValidationError(
                [
                    f"--prefix '{requested}' must start with a letter and contain "
                    "only letters, digits, or underscores"
                ]
            )
        return requested
    return config.id_prefix or derive_prefix(kanban.parent.name)


def created_date(ticket: Ticket) -> str:
    """Return the ticket's created date, or an empty string when absent."""

    value = _frontmatter(ticket.path).get("created")
    return value if isinstance(value, str) else ""


def ordered_tickets(tickets: Sequence[Ticket], order: str) -> list[Ticket]:
    """Sort tickets into the deterministic order new numbers are handed out in."""

    if order == "created":
        return sorted(
            tickets, key=lambda item: (created_date(item), natural_key(item.id))
        )
    return sorted(tickets, key=lambda item: natural_key(item.id))


def build_mapping(
    tickets: Sequence[Ticket], prefix: str, padding: int, floor: int, renumber_all: bool
) -> tuple[dict[str, str], int]:
    """Map old ids to new ids, returning the mapping and high-water mark."""

    if renumber_all:
        mapping = {
            ticket.id: format_ticket_id(prefix, number, padding)
            for number, ticket in enumerate(tickets, start=1)
        }
        return mapping, len(tickets)

    highest = max(highest_ticket_number(tickets, prefix), floor)
    mapping: dict[str, str] = {}
    for ticket in tickets:
        if ticket_number(ticket.id, prefix) is not None:
            continue
        highest += 1
        mapping[ticket.id] = format_ticket_id(prefix, highest, padding)
    return mapping, highest


def _line_ending(line: str) -> str:
    return line[len(line.rstrip("\r\n")) :]


def _replace_scalar(line: str, field: str, value: str) -> str:
    """Replace a scalar value while keeping indentation and line ending."""

    body = line.rstrip("\r\n")
    replaced = re.sub(
        rf"^({re.escape(field)}:\s*).*$", lambda match: match.group(1) + value, body
    )
    return replaced + _line_ending(line)


def frontmatter_bounds(lines: Sequence[str]) -> int:
    """Return the index of the closing delimiter, or the end of the file."""

    return next(
        (
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.strip() == "---"
        ),
        len(lines),
    )


def rewrite_frontmatter(
    text: str, ticket_id: str, new_id: str, mapping: dict[str, str]
) -> str:
    """Rewrite the id and dependencies a line at a time.

    Everything else — unknown fields, comments, blank lines, and the whole
    Markdown body — is copied through untouched.
    """

    lines = text.splitlines(keepends=True)
    closing = frontmatter_bounds(lines)
    has_legacy = any(
        line.strip().startswith("legacy_id:") for line in lines[1:closing]
    )

    output: list[str] = []
    in_blocked_by = False
    for index, line in enumerate(lines):
        if index == 0 or index >= closing:
            output.append(line)
            continue

        stripped = line.strip()
        if in_blocked_by:
            item = re.match(r"^(\s+-\s*)(.*?)(\s*)$", line.rstrip("\r\n"))
            if item:
                dependency = item.group(2).strip()
                output.append(
                    f"{item.group(1)}{mapping.get(dependency, dependency)}"
                    f"{item.group(3)}{_line_ending(line)}"
                )
                continue
            in_blocked_by = False

        if stripped.startswith("id:"):
            output.append(_replace_scalar(line, "id", new_id))
            if new_id != ticket_id and not has_legacy:
                output.append(f"legacy_id: {ticket_id}{_line_ending(line) or chr(10)}")
            continue

        if stripped.startswith("blocked_by:"):
            value = stripped[len("blocked_by:") :].strip()
            if value.startswith("[") and value.endswith("]"):
                items = [mapping.get(item, item) for item in _split_inline_list(value)]
                output.append(
                    _replace_scalar(line, "blocked_by", f"[{', '.join(items)}]")
                )
            else:
                output.append(line)
                in_blocked_by = not value
            continue

        output.append(line)
    return "".join(output)


def read_verbatim(path: Path) -> str:
    """Read a ticket without translating its line endings.

    A migration must not silently convert a project's CRLF files to LF, so
    universal-newline mode is disabled and the endings are carried through the
    rewrite untouched.
    """

    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def write_verbatim(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(content)


def set_config_field(text: str, field: str, value: str) -> str:
    """Set one board.yaml field, keeping the file's existing line endings.

    The pattern stops at the newline rather than at ``$`` so that a CRLF file
    does not lose the carriage return on the single line being rewritten.
    """

    pattern = re.compile(rf"^{re.escape(field)}:[^\n]*", re.MULTILINE)
    match = pattern.search(text)
    if match:
        carriage = "\r" if match.group(0).endswith("\r") else ""
        return (
            text[: match.start()] + f"{field}: {value}{carriage}" + text[match.end() :]
        )
    ending = "\r\n" if "\r\n" in text else "\n"
    separator = "" if not text or text.endswith(("\n", "\r")) else ending
    return f"{text}{separator}{field}: {value}{ending}"


def target_path(ticket: Ticket, new_id: str) -> Path:
    """Rename the descriptive filename to lead with the new id."""

    stem = ticket.path.stem
    lowered = stem.lower()
    for candidate in (f"{ticket.id.lower()}-", f"{ticket.id.lower()}_"):
        if lowered.startswith(candidate):
            stem = stem[len(candidate) :]
            break
    else:
        if lowered == ticket.id.lower():
            stem = ""
    suffix = f"-{stem}" if stem else ""
    return ticket.path.with_name(f"{new_id}{suffix}{ticket.path.suffix}")


def find_stray_references(
    tickets: Sequence[Ticket], mapping: dict[str, str]
) -> list[str]:
    """Report old ids mentioned in prose, which are never rewritten silently."""

    if not mapping:
        return []
    pattern = re.compile(
        r"(?<![A-Za-z0-9_-])(" + "|".join(re.escape(key) for key in mapping) + r")"
        r"(?![A-Za-z0-9_-])"
    )
    findings: list[str] = []
    for ticket in tickets:
        lines = ticket.path.read_text(encoding="utf-8").splitlines()
        closing = frontmatter_bounds(lines)
        for number, line in enumerate(lines, start=1):
            stripped = line.strip()
            managed = stripped.startswith(("id:", "legacy_id:", "blocked_by:")) or (
                number <= closing and stripped.startswith("-")
            )
            if managed:
                continue
            for match in pattern.finditer(line):
                findings.append(
                    f"{ticket.path}:{number}: mentions '{match.group(1)}' "
                    f"(now {mapping[match.group(1)]})"
                )
    return findings


def build_plan(
    kanban: Path,
    prefix: str | None,
    padding: int | None,
    order: str,
    renumber: bool,
    renumber_all: bool,
) -> Plan:
    config, active, archived = load_and_validate(kanban)
    tickets = ordered_tickets([*active, *archived], order)
    resolved_prefix = resolve_prefix(kanban, config, prefix)
    resolved_padding = padding or config.id_padding or DEFAULT_ID_PADDING

    if not (renumber or renumber_all):
        sequence = max(
            highest_ticket_number(tickets, resolved_prefix), config.id_sequence
        )
        return Plan(kanban, resolved_prefix, resolved_padding, sequence, (), ())

    mapping, sequence = build_mapping(
        tickets, resolved_prefix, resolved_padding, config.id_sequence, renumber_all
    )
    mapping = {old: new for old, new in mapping.items() if old != new}

    claimed = set(mapping.values())
    kept = {ticket.id for ticket in tickets if ticket.id not in mapping}
    collisions = sorted(claimed & kept)
    if collisions:
        raise ValidationError(
            [f"new id '{value}' collides with an existing ticket" for value in collisions]
        )
    if len(claimed) != len(mapping):
        raise ValidationError(["the generated id mapping is not one-to-one"])

    renames: list[Rename] = []
    planned_paths: dict[Path, str] = {}
    for ticket in tickets:
        new_id = mapping.get(ticket.id, ticket.id)
        text = read_verbatim(ticket.path)
        content = rewrite_frontmatter(text, ticket.id, new_id, mapping)
        new_path = target_path(ticket, new_id) if new_id != ticket.id else ticket.path
        if new_path in planned_paths:
            raise ValidationError(
                [f"{new_path}: two tickets would claim the same filename"]
            )
        planned_paths[new_path] = ticket.id
        if content != text or new_path != ticket.path:
            renames.append(Rename(ticket, new_id, new_path, content))

    strays = find_stray_references(tickets, mapping)
    return Plan(
        kanban,
        resolved_prefix,
        resolved_padding,
        sequence,
        tuple(renames),
        tuple(strays),
    )


def update_board_config(kanban: Path, plan: Plan) -> None:
    """Write the id scheme into board.yaml without reserialising the file."""

    path = kanban / "board.yaml"
    text = read_verbatim(path)
    for field, value in (
        ("id_prefix", plan.prefix),
        ("id_padding", str(plan.padding)),
        ("id_sequence", str(plan.sequence)),
    ):
        text = set_config_field(text, field, value)
    write_verbatim(path, text)


def apply_plan(plan: Plan) -> Path:
    """Apply the plan, restoring the backup if the result does not validate."""

    backup = plan.kanban.with_name(
        f"{plan.kanban.name}.backup-{datetime.now().strftime(BACKUP_STAMP)}"
    )
    shutil.copytree(plan.kanban, backup)
    try:
        staged: list[tuple[Path, Path]] = []
        for index, rename in enumerate(plan.renames):
            temporary = rename.new_path.with_name(f".migrate-{index}.tmp")
            write_verbatim(temporary, rename.content)
            staged.append((temporary, rename.new_path))

        # Old files are removed before any temporary file takes its final name,
        # so a renumbering that swaps two ids cannot collide mid-flight.
        for rename in plan.renames:
            rename.ticket.path.unlink()
        for temporary, destination in staged:
            temporary.replace(destination)

        update_board_config(plan.kanban, plan)
        regenerate_board(plan.kanban)
    except BaseException:
        shutil.rmtree(plan.kanban)
        shutil.copytree(backup, plan.kanban)
        shutil.rmtree(backup, ignore_errors=True)
        raise
    return backup


def describe(plan: Plan, applied: bool, backup: Path | None) -> str:
    lines = [
        f"project: {plan.kanban}",
        f"id scheme: {format_ticket_id(plan.prefix, plan.sequence + 1, plan.padding)}"
        f" is next (prefix {plan.prefix}, padding {plan.padding}, "
        f"sequence {plan.sequence})",
        "",
    ]
    if plan.renames:
        lines.append(f"{len(plan.renames)} ticket file(s) rewritten:")
        for rename in plan.renames:
            arrow = (
                f"{rename.ticket.id} -> {rename.new_id}"
                if rename.ticket.id != rename.new_id
                else f"{rename.ticket.id} (dependencies only)"
            )
            lines.append(f"  {arrow}")
            if rename.new_path != rename.ticket.path:
                lines.append(
                    f"    {rename.ticket.path.name} -> {rename.new_path.name}"
                )
    else:
        lines.append("no ticket file needs to change")
    if plan.stray_references:
        lines.extend(
            ["", "old ids still mentioned in ticket text (left for you to review):"]
        )
        lines.extend(f"  {reference}" for reference in plan.stray_references)
    lines.append("")
    if applied:
        lines.append(f"applied; a backup was kept at {backup}")
    else:
        lines.append("dry run; nothing was written. Re-run with --apply to commit.")
    return "\n".join(lines)


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Adopt project-assigned ticket ids in a .kanban project."
    )
    parser.add_argument("--kanban", type=Path, help="explicit path to .kanban")
    parser.add_argument("--prefix", help="ticket id prefix, such as PROJ")
    parser.add_argument("--padding", type=int, help="zero-padded width of the number")
    parser.add_argument(
        "--order",
        choices=("id", "created"),
        default="created",
        help="order new numbers are handed out in (default: created)",
    )
    parser.add_argument(
        "--apply", action="store_true", help="write the changes instead of previewing"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--adopt",
        action="store_true",
        help="record the scheme only; keep every existing id (default)",
    )
    mode.add_argument(
        "--renumber",
        action="store_true",
        help="also renumber ids that do not match the scheme",
    )
    mode.add_argument(
        "--renumber-all",
        action="store_true",
        help="assign a clean sequence to every ticket",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    arguments = _argument_parser().parse_args(argv)
    if arguments.padding is not None and arguments.padding < 1:
        print("error: --padding must be 1 or greater", file=sys.stderr)
        return MIGRATION_ERROR
    try:
        kanban = (
            arguments.kanban.resolve()
            if arguments.kanban is not None
            else discover_kanban()
        )
        plan = build_plan(
            kanban,
            arguments.prefix,
            arguments.padding,
            arguments.order,
            arguments.renumber,
            arguments.renumber_all,
        )
        backup = apply_plan(plan) if arguments.apply else None
        print(describe(plan, arguments.apply, backup))
        return 0
    except ValidationError as error:
        for message in error.messages:
            print(f"error: {message}", file=sys.stderr)
        return MIGRATION_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
