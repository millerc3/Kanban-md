---
id: KMD-005
title: Add a ticket query CLI for agents
status: inbox
category: Storage
intervention: low
priority: medium
type: feature
blocked_by: []
tags: [cli, agents, tokens]
source: [AGENTS.md#ticket-ids-are-assigned-by-the-project]
created: 2026-07-28
updated: 2026-07-28
---

## Goal

Give agents a read-only way to answer "which tickets match X?" in one command, without globbing
`.kanban/tickets/*.md` and reading every file to find out.

## Context

Agents currently locate tickets by grepping the ticket directory, then opening each hit to learn
its title and status. `board.md` already removes much of that cost — it is a generated index of
ID, title, category, intervention, and `blocked_by` grouped by status — but it has two gaps:

- It does not surface `tags` at all, so tag-based lookup still forces a grep.
- It can be stale between regenerations, whereas a query reads the ticket files live.

This must be a CLI, not an HTTP endpoint. `ACTIVE_PROJECT` in `app.py` is a process-global set by
`POST /api/open`, so an agent calling the API would repoint the server and hijack whichever board
the developer has open in the browser. It would also require a server to be listening, which is
usually false when an agent is working in a terminal. A CLI has no server, no port, and no shared
mutable state, and the portable copy already sits in `.kanban/tools/` where `AGENTS.md` sends
agents.

Real-world motivation: VaultKnights retired its `MP#` ID prefix when it adopted project-assigned
IDs. That prefix had doubled as a search handle for networking tickets. Filtering by
`category` and `tags` is the intended replacement.

## Acceptance criteria

- [ ] A new `tools/query_tickets.py` prints tickets matching the supplied filters.
- [ ] Filters: `--tag`, `--category`, `--status`, `--type`, `--intervention`. Repeating a flag
      matches any of the supplied values; different flags combine with AND.
- [ ] `--archived` includes `archive/**`; active tickets only by default.
- [ ] Default output is one compact line per ticket (ID, status, category, title) and never
      includes ticket bodies — the point is choosing what to open before paying to read it.
- [ ] `--format json` emits structured output for programmatic use.
- [ ] Results are ordered by `natural_key` on the ID, matching the generator.
- [ ] Exits 0 with no output when nothing matches; exits with the generator's validation status
      when ticket data is invalid.
- [ ] Runs correctly from any working directory via `discover_kanban`, and accepts `--kanban PATH`.
- [ ] `tests/test_query_tickets.py` covers each filter, filter combination, the archived toggle,
      both output formats, empty results, and invalid ticket data.
- [ ] `README.md` and `docs/SCHEMA.md` document the command.
- [ ] `AGENTS.md` tells agents to use it instead of globbing the ticket directory.

## Implementation notes

Write it as a sibling script that imports the loader from `tools/regenerate_board.py`, exactly as
`tools/migrate_ticket_ids.py` does — including the `try: from regenerate_board import ...` /
`except ImportError: from tools.regenerate_board import ...` shim that lets the same file work
both as a portable copy in `.kanban/tools/` and as part of the `tools` package.

Do not add query behaviour to `regenerate_board.py`; that file's name is a promise about what it
does.

Reuse `load_and_validate`, `Ticket`, and `natural_key` rather than reparsing frontmatter. The tool
must stay Python standard-library-only, deterministic, and strictly read-only — it must never
write `board.md` or touch a ticket file.

Consider whether `tags` should also appear in `board.md`. It is the cheaper fix for the same gap
and needs no new tool, but it widens every generated table and still makes a reader take the whole
board to see one slice. This ticket assumes the query tool is the better answer; revisit if the
generated table proves sufficient.

## Human work

Confirm the filter set is the right one before the tests are written to it, and decide the
`board.md` tags question noted above.
