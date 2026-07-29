---
id: KMD-008
title: Add a POSIX launcher and document non-Windows use
status: inbox
category: Product
intervention: medium
priority: medium
type: feature
blocked_by: []
tags: [cli, startup, posix, portability]
source: [README.md#run-on-windows]
created: 2026-07-28
updated: 2026-07-28
---

## Goal

Give Linux and macOS the same one-command start Windows has, so the documented workflow is not
"translate `run.ps1` in your head".

## Context

Nothing in the application is Windows-bound. `atomic_write` already forces `\n`, and
`/api/directories` already answers `::drives` with `["/"]` on non-Windows hosts. The gap is the
launcher and every document that spells a path as `.\.venv\Scripts\python.exe`.

This is speculative. There is no Linux or macOS machine that needs this today, so the support is
best-effort until someone runs it in anger. Say so in the README rather than implying a tested
platform matrix.

Validation should happen in WSL, but **not** from a `/mnt/<drive>` path. That mount is DrvFs:
case-insensitive by default, with different metadata and rename semantics. A run there would pass
while proving nothing about Linux. Clone into the WSL filesystem — `~/kanban-md` — so the test
exercises case-sensitive filenames and a real `os.replace` on ext4.

## Acceptance criteria

- [ ] `run.sh` starts the app and reaches parity with `run.ps1`: venv bootstrap, dependency
      install, startup banner, and `Ctrl+C` to stop.
- [ ] `run.sh <path>` opens that project, matching `run.ps1 <path>` exactly — including rejecting a
      nonexistent path or a file with a clear message and a nonzero exit.
- [ ] When a server is already listening, `run.sh <path>` re-points it through `POST /api/open` and
      prints the tool-sync result, rather than exiting early.
- [ ] The venv interpreter is resolved per-platform (`.venv/bin/python` vs
      `.venv\Scripts\python.exe`) wherever a document or script names it.
- [ ] `run.sh` is committed with its executable bit set.
- [ ] The full test suite passes when run from WSL against a checkout inside the WSL filesystem.
- [ ] `README.md`, `AGENTS.md`, and `docs/SCHEMA.md` show both launchers wherever they currently
      show only the PowerShell one.
- [ ] The README states plainly that POSIX support is validated on WSL only and that macOS is
      expected to work but is untested.

## Implementation notes

Write it as `#!/usr/bin/env bash` with `set -euo pipefail`. Prefer `python3`; fall back to `python`
only after confirming it reports major version 3, mirroring the check `run.ps1` already performs.

For the "is a server already up" probe, `run.ps1` uses `Invoke-WebRequest` with a one-second
timeout. `curl -fsS --max-time 1` is the direct equivalent; do not add a dependency on `jq` to read
the response — printing the raw sync result is enough, or parse it with the venv Python once it
exists.

Do not restructure `run.ps1` to share logic with `run.sh`. Two small readable scripts beat one
clever cross-platform launcher in a repository whose stated goal is to avoid toolchain complexity.

Check the test suite for hardcoded backslashes or drive letters before assuming it is portable.

## Human work

Run the WSL validation and confirm the launcher behaves as described — this cannot be verified from
the Windows host. Decide whether macOS should be claimed as supported or only as expected-to-work.
