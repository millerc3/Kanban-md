---
id: KMD-007
title: Open a project from a startup path argument
status: inbox
category: Interface
intervention: low
priority: medium
type: feature
blocked_by: []
tags: [cli, startup, ergonomics]
source: [README.md#use]
created: 2026-07-28
updated: 2026-07-28
---

## Goal

Start the app pointed at a project directly, so the board is on screen without pasting or browsing
to a path every session.

## Context

Today every start lands on "No project open" and the developer re-selects the same directory
through the path field or the folder picker. Anyone who works in one project for a stretch pays
that cost on every launch.

The intended behaviour when the supplied directory has no `.kanban` is deliberately *not* a hard
error. The UI already has a first-class path for that case: the "No .kanban directory found —
initialize this project" button in `static/app.js`. Refusing to start would block the one flow
that exists to fix the situation. A path that does not exist at all is a different thing — that is
a typo, it is unambiguous, and it should fail loudly.

## Acceptance criteria

- [ ] `python app.py <path>` sets the active project before the server starts.
- [ ] `run.ps1 <path>` forwards the argument.
- [ ] A path that does not exist, or is not a directory, prints a clear message and exits nonzero
      without starting the server.
- [ ] A directory that exists but has no `.kanban` starts normally with that project selected, so
      the existing initialize button is one click away.
- [ ] With no argument, startup behaviour is unchanged.
- [ ] The browser shows the board on first load instead of "No project open".
- [ ] `run.ps1` re-points an already-running server at the supplied path rather than exiting early.
- [ ] The server still binds only to `127.0.0.1`.
- [ ] Tests cover: a valid initialized path, a valid uninitialized path, a nonexistent path, a
      path that is a file, and no argument at all.

## Implementation notes

Put argument parsing in a function that sets `ACTIVE_PROJECT` and returns, rather than inline
under `if __name__ == "__main__"`. The current entry point cannot be tested without starting a
server; a separate function can be called directly from `tests/test_app.py`.

Resolve the path exactly as `POST /api/open` does, including `expanduser`, so a path behaves the
same whether it arrives from the command line or the UI.

For the frontend: no new route is needed. `GET /api/tickets` already returns the project payload
or a 409 when nothing is open, so `app.js` can call it once on load and run the existing
`applyProject` when it succeeds. Reuse that path rather than adding a `/api/project` endpoint or
injecting state into the template.

`run.ps1` currently probes `http://127.0.0.1:5000` and exits early when a server answers, which
would make a supplied path silently do nothing in exactly the case where someone is most likely to
use it. When a server is already up and a path was given, `POST /api/open` to it instead of
exiting. Note that this repoints the board for any browser tab already viewing that server; that
is the intended outcome of asking for a specific project, but call it out in the message printed
to the console so it is not a surprise.

## Human work

Confirm the re-point behaviour on an already-running server is wanted, since it changes what an
open browser tab is showing.
