---
id: KMD-012
title: Archive a ticket by dragging it out of the board
status: inbox
category: Interface
intervention: medium
priority: medium
type: feature
blocked_by: []
tags: [web-ui, archive, drag-and-drop, lifecycle]
source: [AGENTS.md#current-ticket-and-archive-behavior]
created: 2026-07-28
updated: 2026-07-28
---

## Goal

Give finished work a way off the board that matches what `archive/` already means on disk, without
turning archiving into a seventh column.

## Context

`.kanban/archive/<year>/` exists, the generator validates what is in it, and `board.md` counts it.
The UI cannot put anything there. Done tickets therefore accumulate in the Done column forever, and
the only way to archive is to move a file by hand and regenerate.

An Archive column would be the wrong fix, and `AGENTS.md` already says why: Done is a workflow
status and Archived is a filesystem lifecycle state. Putting them side by side as peers teaches
exactly the conflation the repository warns against, and it re-adds to the board the very tickets
archiving is meant to remove from it.

The intended interaction is a drop target rather than a destination column — drag a card to it and
the card leaves the board. The gesture already exists for status moves, so this reuses a motion the
user knows, and "it disappears" is the honest representation of what archiving does.

## Acceptance criteria

- [ ] A drop target appears during a card drag and is not part of the board's column layout.
- [ ] Dropping a card on it moves the file to `.kanban/archive/<year>/` and removes the card from
      the board.
- [ ] The year is the one the archive action happens in, chosen from a single documented rule.
- [ ] The board regenerates after the move; a validation failure moves the file back and leaves the
      card in place, matching the create and status-change guarantee.
- [ ] A name collision in the destination directory fails without overwriting anything.
- [ ] Archiving is confirmed before it happens, or is undoable — a drag is easy to make by accident
      and this one makes work vanish.
- [ ] Ticket content is byte-identical after the move except for fields the move legitimately
      changes.
- [ ] Tests cover: a successful archive, rollback on validation failure, a destination collision,
      year directory creation, and that the archived ticket is absent from `GET /api/tickets` but
      still counted by the generator.
- [ ] `docs/SCHEMA.md` and `README.md` describe archiving and state whether it can be reversed from
      the UI.

## Implementation notes

Decide the two questions `AGENTS.md` insists on before writing code: whether archived tickets are
read-only, and how restoration works. Restoration does not have to ship here, but the answer
determines whether the move may touch frontmatter. If a ticket can come back, the file must carry
enough to come back correctly.

Any status may be archived, or only `done` — pick one and enforce it. Allowing any status is more
honest about what people do with abandoned work; restricting to `done` makes the board's meaning
tighter. Either is defensible; ambiguity is not.

Use `os.replace` for the move, and treat the case where the destination exists as a hard error
rather than a silent overwrite. IDs are never reused, so a collision means something is already
wrong.

The rollback path is the part most likely to be wrong. Write its test first.

## Human work

Decide read-only-ness and restoration, whether non-`done` tickets can be archived, and whether the
guard against accidental archiving is a confirmation or an undo. The interaction is the point of
this ticket, so it should be designed rather than discovered during implementation.
