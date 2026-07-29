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
- `tools/create_ticket.py` — canonical ticket creation, shared by the CLI and
  `POST /api/tickets`.
- `tools/migrate_ticket_ids.py` — one-off migration that adopts project-assigned
  ticket IDs in an existing project.
- `tools/sync_tools.py` — refreshes canonical portable tools in a target project.
- `tests/test_app.py` — Flask API and UI-contract tests.
- `tests/test_regenerate_board.py` — generator, validation, CLI, and atomic-write
  tests.
- `tests/test_create_ticket.py` — creation, rollback, and concurrent-allocation
  tests.
- `tests/test_migrate_ticket_ids.py` — migration planning, rewriting, and
  rollback tests.
- `tests/test_sync_tools.py` — portable-tool sync, drift, and rollback tests.
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
│   ├── regenerate_board.py
│   └── create_ticket.py
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

## Creating a ticket

Create tickets with the canonical tool, never by hand:

```sh
python3 .kanban/tools/create_ticket.py --title "Short imperative title" \
  --category Storage --type feature --tags cli,agents --body-file body.md
```

One invocation allocates the ID, writes complete frontmatter, records the
high-water mark, and regenerates the board. It prints the assigned ID and path;
`--json` prints them as `{"id": ..., "path": ...}` for chaining. Any failure
leaves nothing behind — no file, no consumed ID, no half-updated `board.yaml` —
and exits nonzero.

Supply the body and nothing else. `--body-file PATH` is the usual form;
`--body-stdin` reads the body from a pipe. Prefer the file form: ticket bodies
contain backticks, `$`, and quotes, and piping puts all of them through the
shell. Without a body, the tool falls back to the type template.

Never pass `--id`. Never assemble frontmatter by hand. Never add a second
allocator: `tools/create_ticket.py` is the one implementation, and
`POST /api/tickets` is a caller of it.

A person may still write a ticket file in an editor — that is what portable
Markdown means, and the generator keeps accepting such files. What the tool
replaces is agents performing allocation.

## Ticket IDs are assigned by the project

IDs are not chosen per ticket. `board.yaml` declares `id_prefix`, `id_padding`,
and `id_sequence`, and the next ID is one past the larger of the recorded
high-water mark and the highest number across active and archived tickets. A
deleted ticket therefore never releases its number.

Allocation must stay reserve-by-create — the ID is only ever handed out
together with the file that claims it — so a concurrent agent cannot be given
the same number. The reservation is a claim marker keyed on the ID alone, so
two callers choosing different titles cannot both win one number, and it is
deliberately not a `.md` file: an abandoned reservation visible to a board scan
would make an unrelated process roll back its own valid ticket.

`--next-id` still reports the next ID as a query, but the value is advisory and
is not reserved. Do not read it and then write a file; that is the read-then-
write race the tool exists to remove.

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

Refresh every portable tool in a target project from this checkout with:

```sh
python3 tools/sync_tools.py /path/to/project
```

Use `python3 tools/sync_tools.py --check /path/to/project` to detect missing or
stale copies without writing. The argument is the project root, and the target
must already contain `.kanban`. The app performs the same compare-and-repair
automatically when it opens an initialized project and after initialization.

The Flask API automatically invokes the canonical generator after successful
ticket creation and status changes. A failed validation rolls back the attempted
mutation. Any future API that edits, archives, restores, renames, or deletes a
ticket must provide the same regenerate-or-rollback guarantee.

Ticket creation itself lives in `tools/create_ticket.py`, which regenerates and
rolls back on the caller's behalf. A change to what a new ticket contains
belongs in that module, not in the Flask endpoint, or the CLI and the web UI
will drift apart.

## Working a ticket

The board is how a person sees what an agent is doing, so keep it truthful as
you go rather than at the end.

When you start work on a ticket, set its `status` to `in_progress` before
writing any code. When you stop being able to make progress — a decision you
need from a person, an unlanded dependency — set it to `blocked` and say in the
ticket what would unblock it.

When the work is finished and needs a person to look at it, set `status` to
`review`. That is where an agent's work ends. Do not set `done` yourself: `done`
is the client's judgement that the work is acceptable, not the agent's claim
that the code compiles. Do not archive a ticket unless asked.

Also tick the acceptance criteria you actually satisfied, and leave the rest
unticked. An unticked box in a `review` ticket is a useful signal; a ticked box
that is not true is worse than no ticket at all.

Status lives in the ticket file, so a status change is an ordinary ticket edit:
update `status`, update `updated` to today, then regenerate the board.

```sh
python3 .kanban/tools/regenerate_board.py
```

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
