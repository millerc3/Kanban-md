---
id: KMD-006
title: Sync portable tools into a target project
status: done
category: Storage
intervention: low
priority: high
type: feature
blocked_by: []
tags: [cli, distribution, drift]
source: [AGENTS.md#board-md-is-generated]
created: 2026-07-28
updated: 2026-07-28
---

## Goal

One command that copies this repository's portable tools into a target project's
`.kanban/tools/`, and a `--check` mode that fails when a target's copies have fallen behind.

## Context

`tools/regenerate_board.py` is canonical; every project carries a copy at
`.kanban/tools/regenerate_board.py`. `AGENTS.md` requires exported copies to be refreshed rather
than edited independently, but nothing enforces or automates it, so refreshing is a manual `cp`
that is easy to forget.

This has already failed in practice. A real target project (VaultKnights) was found carrying a
copy that predated the ticket-ID work: `--next-id` failed there with `unrecognized arguments`, and
`migrate_ticket_ids.py` was absent entirely. Nothing surfaced the drift — it was found only by
diffing by hand. The `--check` mode is the more important half of this ticket for that reason.

The command is deliberately **not** called `init`. Initialization already means something else in
this product: creating `tickets/`, `archive/`, and `board.yaml` for a project that has no board
yet, which the app does through `POST /api/initialize`. This command only refreshes tooling in a
project that already has a board. Creating a board from the CLI is separate work and is not in
scope here.

## Acceptance criteria

- [x] `tools/sync_tools.py <target_project>` copies the portable tools into
      `<target_project>/.kanban/tools/`, creating the directory if needed.
- [x] The target path is the project root, not the `.kanban` directory, and is resolved the same
      way `POST /api/open` resolves a project path.
- [x] The command exits nonzero with a clear message when the target has no `.kanban` directory.
      It must not create a board; that is the app's initialize flow.
- [x] `--check` reports drift and exits nonzero when any copy differs or is missing, without
      writing anything.
- [x] Copying is the default action; there is no dry-run default.
- [x] Per-file reporting distinguishes `added`, `updated`, and `already current`, matching the
      generator's existing "regenerated / already current" phrasing.
- [x] A file whose bytes already match is not rewritten, so modification times are left alone.
- [x] Writes are atomic.
- [x] `tests/test_sync_tools.py` covers a fresh copy, an up-to-date no-op, a stale file being
      refreshed, a missing file being added, `--check` passing and failing, and the missing
      `.kanban` error.
- [x] `README.md` and `docs/SCHEMA.md` document the command.
- [x] `AGENTS.md` points to it as the supported way to refresh exported copies.

## Implementation notes

The set of portable tools is an explicit manifest constant in the module, not a glob of `tools/`.
A glob would be wrong: **`sync_tools.py` must never copy itself.** Every other tool is meaningful
inside a target project, but this one only works from a kanban-md checkout, because only there
does the canonical source exist. A copy sitting in a target project would have nothing to sync
from.

Current manifest: `regenerate_board.py`, `migrate_ticket_ids.py`. KMD-005 adds a query tool; that
ticket must add its script to this manifest when it lands.

Apply-by-default is a deliberate difference from `migrate_ticket_ids.py`, which defaults to a dry
run. That tool rewrites authored ticket data, where a wrong guess costs real work. This one
overwrites files that are declared disposable copies of a canonical source, where the recovery is
to run it again. Keep the divergence, and keep this paragraph's reasoning near the argument
parser so it does not read as an inconsistency.

Reuse the atomic-write approach already used by `write_board`. The tool must stay Python
standard-library-only and must never read or modify ticket files.

Consider whether `--check` should be run against a project as part of that project's own
validation step. It cannot be — the check needs canonical bytes, which only exist in this
repository. Drift detection therefore belongs to whoever has the kanban-md checkout, and the
ticket should not promise otherwise.

## Human work

Confirm the manifest is the right set of files to distribute, and decide whether refreshing a
target's tools should be part of a routine you run deliberately or something wired into a hook.

Confirmed on 2026-07-28: keep the explicit two-file manifest and automatically compare and repair
portable tools when the app opens or initializes a project. Retain the deliberate CLI command for
manual synchronization and CI-style drift checks.
