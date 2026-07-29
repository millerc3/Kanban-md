---
id: KMD-015
title: Warn when starting a ticket with unfinished blockers
status: inbox
category: Interface
intervention: low
priority: medium
type: feature
blocked_by: []
tags: [web-ui, dependencies, validation]
source: [docs/SCHEMA.md#status]
created: 2026-07-28
updated: 2026-07-29
---

## Goal

Say something when work starts on a ticket whose blockers are not finished, instead of allowing it
in silence.

## Context

The generator validates that every `blocked_by` entry names a ticket that exists. It does not look
at what state that ticket is in. So a ticket can be dragged from Ready straight into In Progress
while everything it depends on is still sitting in Inbox, and nothing anywhere mentions it.

The card shows "Blocked by KMD-002" as static text, which tells a reader the dependency exists but
not whether it is satisfied. Checking means finding the blocker on the board and reading its column.

This is the mistake an agent working from `board.md` is most likely to make. The summary lists
`blocked_by` IDs in a column with no state attached, so an agent scanning for available work has to
cross-reference every dependency by hand — and will eventually not bother.

## Acceptance criteria

- [ ] Moving a ticket to `in_progress` while any blocker is unfinished surfaces a warning.
- [ ] The warning names the specific blockers and their current statuses.
- [ ] The move is still allowed. This is advisory, not a lock.
- [ ] "Unfinished" is defined once, explicitly, and used everywhere — including whether an archived
      blocker counts as satisfied.
- [ ] The same signal reaches `board.md`, so an agent reading the summary sees it too.
- [ ] Tests cover: all blockers done, some unfinished, a blocker that is archived, a ticket with no
      blockers, and the generated output.

## Implementation notes

Advisory rather than blocking is the right call and should stay that way. People legitimately start
work early, and a tracker whose job is to stay out of the way should not be the thing that stops
them. A hard block would also need an override, and the override would become the habit.

An archived blocker is the interesting case. Archiving usually implies the work concluded, but it
can also mean abandoned. Whichever way it is decided, decide it once and write it down — this is
exactly the Done-versus-Archived conflation `AGENTS.md` warns about.

The card treatment matters more than the warning dialog. A warning appears once, at the moment of
the drag, when the decision is already made; a persistent "ready to start" affordance is what
actually changes which ticket gets picked up. That affordance now belongs to KMD-020, which fixes
the card reading as blocked when its blockers are finished. This ticket keeps the drag-time
advisory, and the two must share one definition of "unfinished" rather than each writing their own —
whichever lands first defines it.

## Human work

Decide whether an archived blocker counts as satisfied.
