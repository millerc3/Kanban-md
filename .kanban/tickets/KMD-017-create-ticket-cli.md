---
id: KMD-017
title: Create tickets through a tool instead of by hand
status: inbox
category: Storage
intervention: low
priority: high
type: feature
blocked_by: []
tags: [cli, agents, ids, correctness]
source: [AGENTS.md#ticket-ids-are-assigned-by-the-project]
created: 2026-07-28
updated: 2026-07-28
---

## Goal

Give agents one command that creates a valid ticket, so no agent ever allocates an ID, assembles
frontmatter, or remembers to regenerate the board.

## Context

`AGENTS.md` states the rule that governs ID allocation:

> allocation must stay reserve-by-create — the ID is only ever handed out together with the file
> that claims it — so a concurrent agent cannot be given the same number

Six lines earlier, the same document tells agents to run `--next-id` and then hand-write the ticket
file. That is read-then-write: the number is read, and nothing holds it until the file appears.
`POST /api/tickets` obeys the rule through `reserve_ticket_id`; the documented agent path does not.
The workflow contradicts the constraint the project already set for itself.

Not every part of hand-writing is dangerous. A stale `id_sequence` is harmless — the next ID is one
past the larger of the recorded high-water mark and the highest ID found in the files, so forgetting
to update `board.yaml` is conservative rather than colliding. The real exposures are narrower:

- Two agents read the same next ID and both write files. `--check` catches the duplicate afterwards,
  once both tickets exist and one has to be renumbered.
- Frontmatter is malformed or missing a required field, which is caught only if someone runs
  `--check`.
- The board is not regenerated, leaving a stale `board.md` that the next agent reads and trusts.
- An ID is invented outright, which no amount of care in the reading step prevents.

Everything in that list is metadata. None of it benefits from an agent's judgement. The ticket body
is the opposite — writing it is the entire reason an agent is involved. The tool should own the
first and never touch the second.

## Acceptance criteria

- [ ] A portable tool creates a ticket from supplied parameters in one invocation.
- [ ] It allocates the ID, writes complete frontmatter, records the high-water mark, and regenerates
      the board.
- [ ] The ticket body is supplied by the caller — via a file or stdin — and falls back to the type
      template when absent. The caller never writes frontmatter.
- [ ] Accepting a caller-supplied ID is refused, matching the HTTP endpoint.
- [ ] Any failure leaves nothing behind: no orphan file, no consumed ID, no half-updated
      `board.yaml`, and a nonzero exit.
- [ ] It prints the assigned ID and path, with a machine-readable form for chaining.
- [ ] Creation logic lives in one module shared by this tool and `POST /api/tickets`; the endpoint
      becomes a caller rather than a parallel implementation.
- [ ] The shared module is standard-library-only and runs from any working directory, so it works as
      a portable copy under `.kanban/tools/`.
- [ ] `tools/sync_tools.py` carries it, and it reaches existing projects through the automatic
      compare-and-repair.
- [ ] Exclusive creation is keyed on the ID alone, so two processes cannot claim one number by
      writing different filenames.
- [ ] Tests cover: a successful create, a rejected caller-supplied ID, a body from file and from
      stdin, the template fallback, rollback on validation failure, and concurrent allocation from
      two processes yielding two distinct IDs.
- [ ] `AGENTS.md`, `README.md`, and `docs/SCHEMA.md` document the command and stop presenting
      `--next-id` as a step toward hand-writing a ticket.

## Implementation notes

Do not write a second allocator. `create_ticket()` in `app.py` already implements every part of this
correctly — reserve-by-create, `record_id_sequence`, regenerate, unlink-and-restore on
`ValidationError`. The work is lifting that into a portable module and pointing Flask at it, not
reproducing it. A CLI that reimplements allocation is exactly the duplication `AGENTS.md` forbids,
and the two copies will diverge on the rollback path first.

Make it a CLI rather than an HTTP endpoint, for the reasons KMD-005 already records: `ACTIVE_PROJECT`
is a process-global set by `POST /api/open`, so an agent calling the API would repoint whichever
board the developer has open, and an agent working in a terminal usually has no server running.

Use the `try: from regenerate_board import ...` / `except ImportError: from tools.regenerate_board
import ...` shim that `migrate_ticket_ids.py` and `sync_tools.py` already use, so one file works both
as a portable copy and as part of the `tools` package.

The exclusive-create key is a real defect worth fixing here rather than inheriting. `reserve_ticket_id`
creates `{id}-{slug}.md` with `O_EXCL`, which only collides when two callers choose the same title.
Inside Flask that is masked by `PROJECT_LOCK`, but a CLI running beside the app shares no lock, and
two different titles allocating the same number produce two different filenames and two tickets with
one ID. Reserve on a path derived from the ID alone, then rename to the descriptive filename.

Keep `--next-id`. Removing it breaks portable copies already sitting in other projects, and it is
still meaningful as a query. Stop documenting it as part of creating a ticket, and say in its help
text that the value is advisory and not reserved.

This does not make hand-written tickets illegal. A person must still be able to create a ticket in
an editor — that is what portable Markdown means, and the generator must keep accepting such files.
What changes is that agents are no longer asked to perform allocation, not that files stop being
authoritative.

KMD-011 and KMD-016 both extend what a new ticket contains. Whichever lands last should add its
fields to the shared module rather than to the Flask endpoint.

## Human work

Confirm the parameter surface once, since agents will be told to depend on it.
