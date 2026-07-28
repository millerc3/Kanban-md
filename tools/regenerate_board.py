#!/usr/bin/env python3
"""Validate Markdown tickets and regenerate the disposable board summary."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


VALIDATION_ERROR = 2
STALE_BOARD = 1
REQUIRED_FIELDS = (
    "id",
    "title",
    "status",
    "category",
    "intervention",
    "type",
    "blocked_by",
    "tags",
    "source",
)
PLANNING_STATUSES = {"inbox", "ready", "blocked"}
GENERATED_WARNING = """<!--
GENERATED FILE — DO NOT EDIT MANUALLY.
Run: python3 .kanban/tools/regenerate_board.py
Source: .kanban/tickets/*.md
-->"""


class ValidationError(Exception):
    """Raised when board configuration or ticket data is invalid."""

    def __init__(self, messages: Sequence[str]):
        self.messages = list(messages)
        super().__init__("\n".join(self.messages))


@dataclass(frozen=True)
class Ticket:
    path: Path
    archived: bool
    id: str
    title: str
    status: str
    category: str
    intervention: str
    ticket_type: str
    blocked_by: tuple[str, ...]
    tags: tuple[str, ...]
    source: tuple[str, ...]


@dataclass(frozen=True)
class BoardConfig:
    name: str
    statuses: tuple[str, ...]
    categories: tuple[str, ...]
    intervention_levels: tuple[str, ...]


def _split_inline_list(value: str) -> list[str]:
    inner = value[1:-1].strip()
    if not inner:
        return []
    items: list[str] = []
    start = 0
    quote = ""
    escaped = False
    for index, character in enumerate(inner):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote == '"':
            escaped = True
            continue
        if quote:
            if character == quote:
                quote = ""
            continue
        if character in {"'", '"'}:
            quote = character
        elif character == ",":
            items.append(inner[start:index].strip())
            start = index + 1
    if quote:
        raise ValueError("unterminated quoted string in inline list")
    items.append(inner[start:].strip())
    return [_parse_scalar(item) for item in items]


def _parse_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid quoted string: {error.msg}") from error
        if not isinstance(parsed, str):
            raise ValueError("expected a string")
        return parsed
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def parse_yaml_like(text: str, filename: str) -> dict[str, Any]:
    """Parse the small, forgiving YAML subset used by kanban.md files."""

    values: dict[str, Any] = {}
    current_list: str | None = None
    errors: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        list_match = re.match(r"^\s+-\s*(.*?)\s*$", line)
        if list_match and current_list:
            try:
                values[current_list].append(_parse_scalar(list_match.group(1)))
            except ValueError as error:
                errors.append(f"{filename}:{line_number}: {error}")
            continue
        field_match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:\s*(.*))?$", line)
        if not field_match:
            current_list = None
            continue
        key, raw_value = field_match.groups()
        raw_value = (raw_value or "").strip()
        try:
            if not raw_value:
                values[key] = []
                current_list = key
            elif raw_value.startswith("[") and raw_value.endswith("]"):
                values[key] = _split_inline_list(raw_value)
                current_list = None
            else:
                values[key] = _parse_scalar(raw_value)
                current_list = None
        except ValueError as error:
            errors.append(f"{filename}:{line_number}: {error}")
            current_list = None
    if errors:
        raise ValidationError(errors)
    return values


def _frontmatter(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ValidationError([f"{path}: cannot read UTF-8 ticket: {error}"]) from error
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValidationError([f"{path}: missing opening frontmatter delimiter"])
    try:
        end = next(
            index for index, line in enumerate(lines[1:], start=1)
            if line.strip() == "---"
        )
    except StopIteration as error:
        raise ValidationError([f"{path}: missing closing frontmatter delimiter"]) from error
    return parse_yaml_like("\n".join(lines[1:end]), str(path))


def _string_field(
    values: dict[str, Any], field: str, path: Path, errors: list[str]
) -> str:
    value = values.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}: field '{field}' must be a non-empty string")
        return ""
    return value.strip()


def _list_field(
    values: dict[str, Any], field: str, path: Path, errors: list[str]
) -> tuple[str, ...]:
    value = values.get(field)
    if not isinstance(value, list):
        errors.append(f"{path}: field '{field}' must be an inline or block list")
        return ()
    if any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"{path}: field '{field}' must contain only non-empty strings")
        return ()
    return tuple(item.strip() for item in value)


def _ticket_from_path(path: Path, archived: bool) -> Ticket:
    values = _frontmatter(path)
    errors = [
        f"{path}: missing required field '{field}'"
        for field in REQUIRED_FIELDS
        if field not in values
    ]
    ticket_id = _string_field(values, "id", path, errors)
    title = _string_field(values, "title", path, errors)
    status = _string_field(values, "status", path, errors)
    category = _string_field(values, "category", path, errors)
    intervention = _string_field(values, "intervention", path, errors)
    ticket_type = _string_field(values, "type", path, errors)
    blocked_by = _list_field(values, "blocked_by", path, errors)
    tags = _list_field(values, "tags", path, errors)
    source = _list_field(values, "source", path, errors)
    if errors:
        raise ValidationError(errors)
    return Ticket(
        path=path,
        archived=archived,
        id=ticket_id,
        title=title,
        status=status,
        category=category,
        intervention=intervention,
        ticket_type=ticket_type,
        blocked_by=blocked_by,
        tags=tags,
        source=source,
    )


def load_board_config(kanban: Path) -> BoardConfig:
    path = kanban / "board.yaml"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ValidationError([f"{path}: cannot read board configuration: {error}"]) from error
    values = parse_yaml_like(text, str(path))
    errors: list[str] = []
    name_value = values.get("name", kanban.parent.name or "Kanban")
    name = name_value.strip() if isinstance(name_value, str) else "Kanban"
    statuses = _list_field(values, "statuses", path, errors)
    categories = _list_field(values, "categories", path, errors)
    interventions = _list_field(values, "intervention_levels", path, errors)
    if not statuses:
        errors.append(f"{path}: 'statuses' must contain at least one status")
    if not interventions:
        errors.append(
            f"{path}: 'intervention_levels' must contain at least one level"
        )
    if len(set(statuses)) != len(statuses):
        errors.append(f"{path}: 'statuses' contains duplicate values")
    if len(set(interventions)) != len(interventions):
        errors.append(f"{path}: 'intervention_levels' contains duplicate values")
    if errors:
        raise ValidationError(errors)
    return BoardConfig(name, statuses, categories, interventions)


def load_and_validate(kanban: Path) -> tuple[BoardConfig, list[Ticket], list[Ticket]]:
    config = load_board_config(kanban)
    active_directory = kanban / "tickets"
    archive_directory = kanban / "archive"
    errors: list[str] = []
    if not active_directory.is_dir():
        errors.append(f"{active_directory}: active ticket directory does not exist")
    paths = (
        [(path, False) for path in sorted(active_directory.glob("*.md"))]
        if active_directory.is_dir()
        else []
    )
    if archive_directory.is_dir():
        paths.extend(
            (path, True) for path in sorted(archive_directory.rglob("*.md"))
        )

    tickets: list[Ticket] = []
    for path, archived in paths:
        try:
            tickets.append(_ticket_from_path(path, archived))
        except ValidationError as error:
            errors.extend(error.messages)

    by_id: dict[str, Ticket] = {}
    for ticket in tickets:
        previous = by_id.get(ticket.id)
        if previous:
            errors.append(
                f"{ticket.path}: duplicate ticket id '{ticket.id}' "
                f"(also in {previous.path})"
            )
        else:
            by_id[ticket.id] = ticket
        if ticket.status not in config.statuses:
            errors.append(
                f"{ticket.path}: invalid status '{ticket.status}'; "
                f"expected one of {', '.join(config.statuses)}"
            )
        if ticket.intervention not in config.intervention_levels:
            errors.append(
                f"{ticket.path}: invalid intervention '{ticket.intervention}'; "
                f"expected one of {', '.join(config.intervention_levels)}"
            )

    known_ids = set(by_id)
    for ticket in tickets:
        for dependency in ticket.blocked_by:
            if dependency == ticket.id:
                errors.append(
                    f"{ticket.path}: ticket '{ticket.id}' cannot depend on itself"
                )
            elif dependency not in known_ids:
                errors.append(
                    f"{ticket.path}: dependency '{dependency}' does not match "
                    "an active or archived ticket"
                )
    if errors:
        raise ValidationError(errors)
    return (
        config,
        [ticket for ticket in tickets if not ticket.archived],
        [ticket for ticket in tickets if ticket.archived],
    )


def natural_key(value: str) -> tuple[tuple[int, object], ...]:
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in re.split(r"(\d+)", value)
        if part
    )


def _escape_table(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>").replace("|", "\\|")


def _heading(value: str) -> str:
    return value.replace("_", " ").title()


def _ticket_rows(tickets: Sequence[Ticket], include_category: bool) -> list[str]:
    headers = ["ID", "Ticket"]
    if include_category:
        headers.append("Category")
    headers.extend(["Intervention", "Blocked by"])
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for ticket in sorted(tickets, key=lambda item: natural_key(item.id)):
        cells = [ticket.id, ticket.title]
        if include_category:
            cells.append(ticket.category)
        cells.extend(
            [ticket.intervention, ", ".join(ticket.blocked_by) or "—"]
        )
        lines.append("| " + " | ".join(_escape_table(cell) for cell in cells) + " |")
    return lines


def generate_board(kanban: Path) -> str:
    config, active, archived = load_and_validate(kanban)
    lines = [
        GENERATED_WARNING,
        "",
        f"# {config.name} board",
        "",
        "> Generated summary. Markdown ticket files are authoritative.",
        "",
    ]
    category_positions = {
        category: index for index, category in enumerate(config.categories)
    }

    for status in config.statuses:
        status_tickets = [ticket for ticket in active if ticket.status == status]
        if not status_tickets:
            continue
        lines.extend((f"## {_heading(status)}", ""))
        if status in PLANNING_STATUSES:
            categories = sorted(
                {ticket.category for ticket in status_tickets},
                key=lambda category: (
                    category_positions.get(category, len(category_positions)),
                    category.casefold(),
                    category,
                ),
            )
            for category in categories:
                lines.extend((f"### {category}", ""))
                lines.extend(
                    _ticket_rows(
                        [
                            ticket
                            for ticket in status_tickets
                            if ticket.category == category
                        ],
                        include_category=False,
                    )
                )
                lines.append("")
        else:
            lines.extend(_ticket_rows(status_tickets, include_category=True))
            lines.append("")

    lines.extend(
        (
            "## Archive",
            "",
            f"{len(archived)} archived ticket"
            f"{'' if len(archived) == 1 else 's'} retained under `.kanban/archive/`.",
            "",
        )
    )
    return "\n".join(lines)


def write_board(kanban: Path, content: str) -> bool:
    """Atomically write board.md, returning True only when bytes changed."""

    destination = kanban / "board.md"
    encoded = content.encode("utf-8")
    try:
        if destination.read_bytes() == encoded:
            return False
    except FileNotFoundError:
        pass
    except OSError as error:
        raise ValidationError([f"{destination}: cannot read existing board: {error}"])

    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=kanban,
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(encoded)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, destination)
    except OSError as error:
        raise ValidationError([f"{destination}: cannot atomically write board: {error}"])
    finally:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
    return True


def regenerate_board(kanban: Path) -> bool:
    kanban = kanban.resolve()
    return write_board(kanban, generate_board(kanban))


def discover_kanban(script_path: Path | None = None, cwd: Path | None = None) -> Path:
    script = (script_path or Path(__file__)).resolve()
    if script.parent.name == "tools" and script.parent.parent.name == ".kanban":
        return script.parent.parent
    current = (cwd or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        if directory.name == ".kanban" and (directory / "board.yaml").is_file():
            return directory
        candidate = directory / ".kanban"
        if (candidate / "board.yaml").is_file():
            return candidate
    raise ValidationError(
        [
            "could not find .kanban from the current directory; "
            "pass --kanban PATH"
        ]
    )


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate tickets and regenerate .kanban/board.md."
    )
    parser.add_argument(
        "--kanban",
        type=Path,
        help="explicit path to the .kanban directory",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="validate tickets and fail if board.md is stale",
    )
    mode.add_argument(
        "--stdout",
        action="store_true",
        help="print generated Markdown without writing board.md",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    arguments = _argument_parser().parse_args(argv)
    try:
        kanban = (
            arguments.kanban.resolve()
            if arguments.kanban is not None
            else discover_kanban()
        )
        content = generate_board(kanban)
        if arguments.stdout:
            sys.stdout.write(content)
            return 0
        if arguments.check:
            board_path = kanban / "board.md"
            try:
                current = board_path.read_bytes()
            except FileNotFoundError:
                current = b""
            if current != content.encode("utf-8"):
                print(
                    f"{board_path}: generated board is stale; run "
                    "python3 .kanban/tools/regenerate_board.py",
                    file=sys.stderr,
                )
                return STALE_BOARD
            return 0
        changed = write_board(kanban, content)
        print(f"{kanban / 'board.md'}: {'regenerated' if changed else 'already current'}")
        return 0
    except ValidationError as error:
        for message in error.messages:
            print(f"error: {message}", file=sys.stderr)
        return VALIDATION_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
