from __future__ import annotations

import os
import re
import tempfile
import threading
from datetime import date
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

from tools.regenerate_board import ValidationError, regenerate_board


app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

PROJECT_LOCK = threading.RLock()
ACTIVE_PROJECT: Path | None = None

STATUSES = ("inbox", "ready", "in_progress", "blocked", "review", "done")
INTERVENTION_LEVELS = ("low", "medium", "high")
FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?(.*)\Z", re.DOTALL)


def strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_inline_list(value: str) -> list[str]:
    value = value.strip()
    if not value:
        return []
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    return [strip_quotes(item) for item in value.split(",") if item.strip()]


def parse_frontmatter(source: str) -> tuple[dict[str, Any], str] | None:
    match = FRONTMATTER.match(source)
    if not match:
        return None

    values: dict[str, Any] = {}
    current_key: str | None = None
    for line in match.group(1).splitlines():
        property_match = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if property_match:
            current_key = property_match.group(1)
            raw_value = property_match.group(2).strip()
            values[current_key] = (
                parse_inline_list(raw_value)
                if raw_value.startswith("[") and raw_value.endswith("]")
                else strip_quotes(raw_value)
            )
            continue

        list_match = re.match(r"^\s+-\s+(.+)$", line)
        if list_match and current_key:
            if not isinstance(values.get(current_key), list):
                values[current_key] = []
            values[current_key].append(strip_quotes(list_match.group(1)))

    return values, match.group(2).strip()


def normalize_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return parse_inline_list(value)
    return []


def ticket_from_file(path: Path) -> dict[str, Any] | None:
    source = path.read_text(encoding="utf-8")
    parsed = parse_frontmatter(source)
    if not parsed:
        return None
    values, body = parsed
    status = str(values.get("status", "inbox"))
    intervention = str(values.get("intervention", "medium"))
    return {
        "file_name": path.name,
        "id": str(values.get("id") or path.stem),
        "title": str(values.get("title") or path.stem.replace("-", " ")),
        "status": status if status in STATUSES else "inbox",
        "category": str(values.get("category") or "Uncategorized"),
        "intervention": (
            intervention if intervention in INTERVENTION_LEVELS else "medium"
        ),
        "priority": str(values.get("priority") or ""),
        "type": str(values.get("type") or ""),
        "blocked_by": normalize_list(values.get("blocked_by")),
        "tags": normalize_list(values.get("tags")),
        "body": body,
        "modified_ns": str(path.stat().st_mtime_ns),
    }


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", text=True
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def update_frontmatter(source: str, updates: dict[str, str]) -> str:
    match = FRONTMATTER.match(source)
    if not match:
        raise ValueError("Ticket has no YAML frontmatter")

    frontmatter = match.group(1)
    for key, value in updates.items():
        pattern = re.compile(rf"^{re.escape(key)}:.*$", re.MULTILINE)
        replacement = f"{key}: {value}"
        if pattern.search(frontmatter):
            frontmatter = pattern.sub(replacement, frontmatter, count=1)
        else:
            frontmatter = f"{frontmatter}\n{replacement}"
    return f"---\n{frontmatter}\n---\n\n{match.group(2).lstrip()}"


def project_payload(project: Path) -> dict[str, Any]:
    tickets_directory = project / ".kanban" / "tickets"
    tickets: list[dict[str, Any]] = []
    invalid_files: list[str] = []

    if tickets_directory.is_dir():
        for path in sorted(tickets_directory.glob("*.md")):
            try:
                ticket = ticket_from_file(path)
            except (OSError, UnicodeError):
                ticket = None
            if ticket:
                tickets.append(ticket)
            else:
                invalid_files.append(path.name)

    return {
        "project": str(project),
        "name": project.name,
        "initialized": tickets_directory.is_dir(),
        "tickets": tickets,
        "invalid_files": invalid_files,
    }


def selected_project() -> Path:
    with PROJECT_LOCK:
        if ACTIVE_PROJECT is None:
            raise RuntimeError("No project is open")
        return ACTIVE_PROJECT


def ticket_path_by_id(project: Path, ticket_id: str) -> Path:
    tickets_directory = project / ".kanban" / "tickets"
    for path in tickets_directory.glob("*.md"):
        ticket = ticket_from_file(path)
        if ticket and ticket["id"] == ticket_id:
            return path
    raise FileNotFoundError(ticket_id)


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "ticket"


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/directories")
def directories():
    supplied = request.args.get("path", "").strip()

    if supplied == "::drives":
        if os.name == "nt":
            import ctypes

            mask = ctypes.windll.kernel32.GetLogicalDrives()
            roots = [
                f"{letter}:\\"
                for index, letter in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
                if mask & (1 << index)
            ]
        else:
            roots = ["/"]
        return jsonify(
            {
                "current": "Computer",
                "parent": None,
                "directories": [{"name": root, "path": root} for root in roots],
                "drives": True,
            }
        )

    current = Path(supplied).expanduser() if supplied else Path.home()
    try:
        current = current.resolve()
        if not current.is_dir():
            return jsonify({"error": "That directory does not exist"}), 404
        children = sorted(
            (
                {"name": child.name, "path": str(child)}
                for child in current.iterdir()
                if child.is_dir() and not child.name.startswith(".")
            ),
            key=lambda item: item["name"].lower(),
        )
    except (OSError, PermissionError) as error:
        return jsonify({"error": f"That directory cannot be read: {error}"}), 403

    parent = str(current.parent) if current.parent != current else None
    return jsonify(
        {
            "current": str(current),
            "parent": parent,
            "directories": children,
            "drives": False,
        }
    )


@app.post("/api/open")
def open_project():
    global ACTIVE_PROJECT
    supplied = str((request.get_json(silent=True) or {}).get("path", "")).strip()
    if not supplied:
        return jsonify({"error": "Enter a project directory"}), 400

    project = Path(supplied).expanduser().resolve()
    if not project.is_dir():
        return jsonify({"error": "That directory does not exist"}), 404

    with PROJECT_LOCK:
        ACTIVE_PROJECT = project
        return jsonify(project_payload(project))


@app.post("/api/initialize")
def initialize_project():
    project = selected_project()
    kanban = project / ".kanban"
    tickets = kanban / "tickets"
    archive = kanban / "archive"
    tickets.mkdir(parents=True, exist_ok=True)
    archive.mkdir(parents=True, exist_ok=True)
    board_config = kanban / "board.yaml"
    if not board_config.exists():
        atomic_write(
            board_config,
            "\n".join(
                (
                    "version: 1",
                    f"name: {project.name}",
                    f"statuses: [{', '.join(STATUSES)}]",
                    "categories: []",
                    f"intervention_levels: [{', '.join(INTERVENTION_LEVELS)}]",
                    "",
                )
            ),
        )
    return jsonify(project_payload(project))


@app.get("/api/tickets")
def list_tickets():
    try:
        return jsonify(project_payload(selected_project()))
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 409


@app.post("/api/tickets")
def create_ticket():
    project = selected_project()
    payload = request.get_json(silent=True) or {}
    ticket_id = str(payload.get("id", "")).strip()
    title = str(payload.get("title", "")).strip()
    category = str(payload.get("category", "")).strip() or "General"
    intervention = str(payload.get("intervention", "low"))

    if not ticket_id or not title:
        return jsonify({"error": "Ticket ID and title are required"}), 400
    if intervention not in INTERVENTION_LEVELS:
        return jsonify({"error": "Invalid intervention level"}), 400

    with PROJECT_LOCK:
        tickets_directory = project / ".kanban" / "tickets"
        try:
            ticket_path_by_id(project, ticket_id)
            return jsonify({"error": f"Ticket {ticket_id} already exists"}), 409
        except FileNotFoundError:
            pass

        file_path = tickets_directory / f"{ticket_id}-{safe_slug(title)}.md"
        today = date.today().isoformat()
        source = f"""---
id: {ticket_id}
title: {title}
status: inbox
category: {category}
intervention: {intervention}
priority: medium
type: feature
blocked_by: []
tags: []
source: [web-ui]
created: {today}
updated: {today}
---

## Goal

Describe the outcome this ticket should produce.

## Context

Add the project knowledge an agent needs before starting.

## Acceptance criteria

- [ ] Define a concrete, verifiable result.

## Human work

State any decisions, editor wiring, art, review, or testing needed from a person.
"""
        atomic_write(file_path, source)
        try:
            regenerate_board(project / ".kanban")
        except ValidationError as error:
            file_path.unlink()
            return jsonify(
                {
                    "error": "Board validation failed; the ticket was not created.",
                    "details": error.messages,
                }
            ), 422
        return jsonify(ticket_from_file(file_path)), 201


@app.patch("/api/tickets/<ticket_id>")
def update_ticket(ticket_id: str):
    project = selected_project()
    payload = request.get_json(silent=True) or {}
    status = str(payload.get("status", ""))
    expected_modified = payload.get("modified_ns")

    if status not in STATUSES:
        return jsonify({"error": "Invalid status"}), 400

    with PROJECT_LOCK:
        try:
            path = ticket_path_by_id(project, ticket_id)
        except FileNotFoundError:
            return jsonify({"error": "Ticket not found"}), 404

        if expected_modified and path.stat().st_mtime_ns != int(expected_modified):
            return jsonify(
                {"error": "This ticket changed on disk. The board has been refreshed."}
            ), 409

        source = path.read_text(encoding="utf-8")
        updated = update_frontmatter(
            source, {"status": status, "updated": date.today().isoformat()}
        )
        atomic_write(path, updated)
        try:
            regenerate_board(project / ".kanban")
        except ValidationError as error:
            atomic_write(path, source)
            return jsonify(
                {
                    "error": "Board validation failed; the ticket was not moved.",
                    "details": error.messages,
                }
            ), 422
        return jsonify(ticket_from_file(path))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
