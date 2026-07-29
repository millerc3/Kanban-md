---
id: KMD-020
title: Only flag a card as blocked when a blocker is unfinished
status: done
category: Interface
intervention: low
priority: high
type: bug
blocked_by: []
tags: [web-ui, dependencies, ux]
source: [static/app.js]
created: 2026-07-29
updated: 2026-07-29
---

## Goal

Make a card say whether its dependencies are actually outstanding, so glancing at the board answers
"what can I hand to an agent right now?" without opening tickets or cross-referencing columns.

## Context

The dependency label carries no state. `static/app.js` appends "Blocked by …" whenever `blocked_by`
is non-empty, and `.dependency` in `static/styles.css` is painted red unconditionally. The UI never
asks whether the blocker is finished, so the marker means "a dependency was once recorded," while it
reads as "do not start this."

KMD-018 and KMD-019 both list KMD-017, which is done. Both currently read as red-flagged work, and
the flag was wrong at the moment it mattered — while deciding what to hand to an agent.

The cost is trust rather than inconvenience. A red marker that is wrong teaches a reader to stop
reading it, and a marker nobody reads is worse than no marker, because the next correct warning
lands on someone already trained to ignore it. That is why this should not wait behind KMD-015: that
ticket adds an advisory at the moment of a drag, and an advisory inherits the credibility of the
indicator beside it.

Nothing new has to be built to know the answer. `project_payload()` in `app.py` globs
`.kanban/tickets/*.md` and stops, so the browser has no record of an archived ticket and cannot tell
a finished blocker from one that does not exist. The server has both directories on disk. This is
not a missing capability; it is state the payload does not carry, and the fix is to stop making the
client guess.

The same answer is wanted in more than one place — the card, the generated summary, and eventually a
terminal query — so "satisfied" must be one predicate with several callers rather than a rule
rewritten per surface. A subprocess is the wrong shape for that sharing: the browser cannot execute
anything, and having Flask shell out per request would re-read files it already has.

Two cases the implementation cannot skip. A blocker id matching no ticket at all must render as
unknown rather than quietly counting as satisfied — the generator rejects such an id, but the UI
deliberately renders invalid boards through `invalid_files`, so it will meet one. And a single
malformed ticket file must not break the computation or blank the board, for the same reason.

This is about what a card says, not about which cards appear. Nothing is hidden, filtered, or
reordered. A blocked ticket is still work that needs to be visible, and removing it from its column
would trade one lie for a worse one.

## Acceptance criteria

- [x] A card whose blockers are all satisfied is not flagged as blocked. The dependency stays
      visible and de-emphasized, because the ordering is still useful context.
- [x] A card with at least one unfinished blocker keeps the flagged treatment and names which
      blockers are outstanding, not merely that something is.
- [x] Blocker state is computed on the server and carried in the ticket payload. The client never
      infers it from the ids alone.
- [x] The computation reads both active and archived tickets.
- [x] A blocker id that matches no ticket renders as unknown, visually distinct from both satisfied
      and unfinished.
- [x] "Satisfied" is defined once and shared by the payload and `board.md`, so the card and the
      summary cannot disagree.
- [x] A malformed ticket file does not raise, blank the board, or silently mark blockers satisfied.
- [x] No ticket is hidden, filtered, or reordered by this change.
- [x] Tests cover: all blockers done, one unfinished, an archived blocker, an unknown id, a ticket
      with no blockers, a malformed file present, and the shape of the payload field.

## Implementation notes

`project_payload()` is the place to add this. It already builds the per-ticket dictionary the client
renders from, and it is the only thing standing between the browser and the archive directory.

`load_and_validate()` in the generator already gathers active and archived tickets together, which
is exactly the set this needs, but it raises on an invalid board and this path must not. Collect ids
and statuses tolerantly, skipping files that do not parse, and keep the strict loader for
validation.

Send the blocker's id and status, not a boolean. A bit says something is outstanding; the reader
wants to know which one so they can go look at it, and a boolean throws that away. Let the client
decide how to render from the state it is given.

Do not filter, hide, or sort by blocked state, and do not add a "hide blocked" control here. A
user-driven filter is a reasonable thing to want, but it belongs with the query work and is opt-in
by nature.

KMD-015 covers the drag-time advisory and owns the question of what counts as unfinished. Whichever
of the two lands first defines "satisfied"; the other consumes that definition rather than writing a
second one. KMD-005's query CLI is a later third caller.

## Human work

Decided: a blocker is satisfied only when its own `status` is `done`. Living under `archive/` does
not make it satisfied, because archiving records a filesystem lifecycle, not a claim that the work
concluded — an archived ticket abandoned at `inbox` still reads as outstanding. Written down in
`docs/SCHEMA.md` under "Dependencies", implemented once as `blocker_state()`, and inherited by
KMD-015 and KMD-005 rather than restated.

Remaining: the `unknown` treatment has not been seen on screen. A valid board cannot produce one —
the generator rejects a dependency naming no ticket — so it only appears on a board rendered through
`invalid_files`. It is currently a dashed orange outline, and tests cover the state, not the look.
