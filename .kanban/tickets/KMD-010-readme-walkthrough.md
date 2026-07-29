---
id: KMD-010
title: Add an end-to-end walkthrough to the README
status: inbox
category: Product
intervention: low
priority: medium
type: docs
blocked_by: [KMD-008, KMD-009]
tags: [docs, onboarding]
source: [README.md#use]
created: 2026-07-28
updated: 2026-07-28
---

## Goal

Take a reader from an ordinary project directory to a working board with an agent that knows how to
use it, in one continuous sequence they can follow without guessing.

## Context

The README explains each part of kanban.md correctly and never joins them up. "Use" is three lines
and assumes the reader already knows what a `.kanban` directory is for. Initialization is mentioned
but never described: nothing says what it creates, so nothing tells the reader whether it is safe
to run on a real project or what to expect afterwards.

Two questions a new user has are unanswered anywhere in the repository:

- **What do I commit?** `.kanban/` should be committed — the ticket files are the product and
  belong in history next to the code they describe. `board.md` is generated, but it should be
  committed too: it is the file agents read first, and an agent that has to regenerate before it can
  orient has to be told to, which defeats the purpose. It is deterministic, so it does not produce
  spurious diffs when nothing changed. Note that this is a recommendation, not a requirement — a
  project that prefers to ignore the generated summary can.
- **How does my agent learn any of this?** Answered by KMD-009, which this section links to rather
  than duplicating.

This is blocked on KMD-008 and KMD-009 deliberately. Written first, the walkthrough would be
Windows-only prose that describes an initialization step that does not yet produce the file the
walkthrough needs to mention, and both halves would be rewritten immediately.

## Acceptance criteria

- [ ] A "How to use" section walks through: open or create a project directory; start kanban.md
      pointed at it; initialize `.kanban`; see what initialization created; create a first ticket;
      move it; and hand the board to an agent.
- [ ] Each step shows both launchers, or shows a launcher-neutral command.
- [ ] The section states what initialization writes, file by file, and which of those files are
      generated and disposable.
- [ ] Version-control guidance says `.kanban/` should be committed, explains why `board.md` is
      included despite being generated, and marks it as a recommendation.
- [ ] The agent hand-off step points at the instructions KMD-009 installs rather than restating
      them.
- [ ] The existing three-line "Use" section is replaced, not left beside the new one.
- [ ] The walkthrough has been followed verbatim, on a directory that has never held a board, and
      every command in it worked as written.

## Implementation notes

Write it against a scratch directory and follow it while writing. A walkthrough that was composed
from knowledge of the code rather than executed will contain a step that is obvious to the author
and missing for the reader — most likely the one where the folder picker and the path field are
alternatives rather than a sequence.

Keep the reference sections that already exist. Ticket IDs, portable-tool syncing, and the
generated board summary are correct and are what a returning reader wants; the walkthrough is for
the first hour, not a replacement for them.

Resist documenting behaviour that does not exist yet. The app cannot edit a ticket beyond its
status (KMD-013) and cannot archive one (KMD-012). If the walkthrough would read better with those,
that is a signal about build order, not licence to describe them early.

## Human work

Confirm the commit recommendation matches how you actually intend to use this, since it is the
first opinionated claim the README will make.
