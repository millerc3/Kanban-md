# AGENTS.md

## What this repository is

`kanban.md` is a small, local-first Kanban tracker for people and coding agents.
Its defining property is that project data remains ordinary, portable Markdown:
there is no ticket database, hosted service, account, or required Git
integration.

The browser UI is a convenience for viewing, creating, filtering, and moving
tickets. The files inside a project's `.kanban` directory are the product's
source of truth and must remain understandable without the UI.

The application is intentionally simple:

- Python 3 and Flask provide the local HTTP server and JSON API.
- Plain HTML, CSS, and JavaScript provide the browser UI.
- The server binds only to `127.0.0.1`.
- Project content stays on the local machine.
- There is no active Node, Vite, database, or frontend build step.

## Start here

Before changing behavior, read:

1. `README.md` for setup and basic use.
2. `docs/SCHEMA.md` for the portable `.kanban` format.
3. The relevant tests in `tests/`.

On Windows, run the application with:

```powershell
.\run.ps1
```

The UI is then available at <http://127.0.0.1:5000>.

Run the complete test suite with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The only runtime dependency is the pinned Flask version in
`requirements.txt`.

## Repository map

- `app.py` — Flask application, file parsing/writing, project selection, and API
  routes.
- `templates/index.html` — single-page application markup.
- `static/app.js` — client state, rendering, API calls, drag-and-drop, and
  ticket drawer behavior.
- `static/styles.css` — all UI styling.
- `tools/regenerate_board.py` — canonical board generator, validator, and ticket
  ID allocator.
- `tools/migrate_ticket_ids.py` — one-off migration that adopts project-assigned
  ticket IDs in an existing project.
- `tests/test_app.py` — Flask API and UI-contract tests.
- `tests/test_regenerate_board.py` — generator, validation, CLI, and atomic-write
  tests.
- `tests/test_migrate_ticket_ids.py` — migration planning, rewriting, and
  rollback tests.
- `docs/SCHEMA.md` — `.kanban` file-format documentation.
- `exports/` — generated portable project exports used as real-world examples.
- `imports/` — copied source material used by import tools. Instructions inside
  a nested `AGENTS.md` apply when working there.

## The `.kanban` data model

A project is initialized when it contains `.kanban/tickets/`. Its portable
layout is:

```text
.kanban/
├── board.yaml
├── board.md
├── tools/
│   └── regenerate_board.py
├── tickets/
└── archive/
    └── <year>/
```

- `board.yaml` defines the project name, valid status order, category order,
  intervention levels, and the ticket ID scheme.
- `tickets/*.md` contains active tickets.
- `archive/**/*.md` contains retained historical tickets.
- Ticket `id` frontmatter is immutable identity; the filename is descriptive
  and may change.
- Unknown frontmatter fields and body sections belong to the ticket owner and
  must be preserved.

The generator requires these frontmatter fields:

- `id`
- `title`
- `status`
- `category`
- `intervention`
- `type`
- `blocked_by`
- `tags`
- `source`

`blocked_by`, `tags`, and `source` are lists. Both inline and block-list syntax
are supported.

## Ticket IDs are assigned by the project

IDs are not chosen per ticket. `board.yaml` declares `id_prefix`, `id_padding`,
and `id_sequence`, and the next ID is one past the larger of the recorded
high-water mark and the highest number across active and archived tickets. A
deleted ticket therefore never releases its number.

Before hand-writing a ticket file, get its ID from the canonical tool:

```sh
python3 .kanban/tools/regenerate_board.py --next-id
```

Do not invent an ID, reuse one, or add a second allocator. The API rejects a
client-supplied ID, and allocation must stay reserve-by-create — the ID is only
ever handed out together with the file that claims it — so a concurrent agent
cannot be given the same number.

IDs that predate the scheme remain valid; `--strict-ids` reports them for
projects that want the format enforced. `tools/migrate_ticket_ids.py` adopts the
scheme in an existing project, in config-only (`--adopt`) or renumbering
(`--renumber`, `--renumber-all`) form. It is a dry run unless `--apply` is
given, and it backs `.kanban` up before writing.

## `board.md` is generated

`.kanban/board.md` is a deterministic, disposable agent-readable summary. It is
never authoritative and must never be manually edited.

After manually creating, editing, moving, or archiving ticket files, run from
the project root:

```sh
python3 .kanban/tools/regenerate_board.py
```

Validate ticket data and verify that the summary is current with:

```sh
python3 .kanban/tools/regenerate_board.py --check
```

Fix validation failures in ticket files, never in `board.md`.

`tools/regenerate_board.py` is the canonical implementation. Portable exports
contain an exact copy at `.kanban/tools/regenerate_board.py`; do not create a
second board-generation implementation. The generator must remain Python
standard-library-only, deterministic, and safe to run regardless of the
caller's working directory. Writes to `board.md` must remain atomic and must be
skipped when the generated bytes are unchanged.

The Flask API automatically invokes the canonical generator after successful
ticket creation and status changes. A failed validation rolls back the attempted
mutation. Any future API that edits, archives, restores, renames, or deletes a
ticket must provide the same regenerate-or-rollback guarantee.

## Current ticket and archive behavior

The statuses are:

`inbox`, `ready`, `in_progress`, `blocked`, `review`, and `done`.

The current UI loads only `.kanban/tickets/*.md`. Therefore:

- A ticket with `status: done` that remains under `tickets/` appears in the Done
  column.
- A ticket under `archive/` is validated by the generator and counted in the
  generated archive summary, but is not shown in the browser UI.
- The UI currently has no explicit archive, restore, or archive-history
  feature.

Do not silently conflate Done and Archived when extending this behavior. Done is
a workflow status; Archived is a filesystem lifecycle state. If archive UI is
added, define whether archived tickets are read-only and how restoration works,
then cover file moves and rollback behavior with tests.

## Editing and safety rules

- Treat Markdown ticket files as authoritative user data.
- Preserve unknown frontmatter and body content when updating a ticket.
- Never rewrite ticket files merely to validate or regenerate a board.
- Keep writes atomic and avoid changing modification times for byte-identical
  generated output.
- Validate dependencies across both active and archived ticket IDs.
- Reject duplicate IDs across active and archived files.
- Preserve natural ticket-ID ordering (`A9` before `A10`) and configured status
  and category ordering.
- Escape Markdown table content, especially pipe characters.
- Keep changes narrow; this repository deliberately avoids framework and build
  complexity.
- Do not add a Node/Vite toolchain for ordinary UI work. The current frontend is
  served directly by Flask.
- Preserve unrelated working-tree changes. This repository may contain
  developer work that is not part of the current task.

## Expectations for changes

For backend or file-format changes:

1. Add or update focused `unittest` coverage.
2. Run the complete test suite.
3. If generator behavior changed, regenerate relevant exported `board.md` files
   and run their portable tool with `--check`.
4. If the canonical generator changed, ensure exported portable copies are
   refreshed rather than edited independently.
5. Update `README.md` or `docs/SCHEMA.md` when user-facing commands, lifecycle
   semantics, or the portable format change.

At handoff, report the files changed, tests run, and any behavior or limitation
the next agent should know about.
