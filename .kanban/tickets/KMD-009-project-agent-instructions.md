---
id: KMD-009
title: Write agent instructions into a project during initialization
status: inbox
category: Product
intervention: low
priority: high
type: feature
blocked_by: [KMD-017]
tags: [agents, initialization, onboarding, docs]
source: [AGENTS.md#ticket-ids-are-assigned-by-the-project]
created: 2026-07-28
updated: 2026-07-28
---

## Goal

Make a freshly initialized project agent-ready on its own, so a coding agent opening it can learn
the rules from the project instead of from a paragraph the developer had to remember and retype.

## Context

Initialization currently produces `board.yaml`, `board.md`, `tickets/`, `archive/`, and the
portable tools. It produces no instructions. An agent dropped into such a project sees a directory
of Markdown and a Python script, with nothing telling it that ticket IDs are allocated rather than
invented, that `board.md` is generated and must never be hand-edited, or that the board must be
regenerated after every ticket change.

That knowledge lives in this repository's `AGENTS.md`, which is about *developing kanban.md*. A
project using kanban.md needs a much smaller document about *using* it. Every adopter currently
reconstructs it from memory or does without, and doing without is how a board acquires a
hand-invented `PROJ-42` or a manually edited `board.md`.

This is the cheapest large win available: it removes the same paragraph from every future adopter's
setup, and it shortens the README walkthrough that depends on it.

## Acceptance criteria

- [ ] Initialization writes agent instructions inside `.kanban`.
- [ ] The document covers, at minimum: ticket files are authoritative; `board.md` is generated and
      must never be edited; create tickets with the tool from KMD-017 rather than by hand; run the
      generator after any ticket change; fix validation failures in ticket files.
- [ ] It does not instruct an agent to allocate an ID or assemble frontmatter itself.
- [ ] It documents the frontmatter fields the generator requires, and the status and intervention
      vocabularies, reading them from the project's own `board.yaml` rather than hardcoding this
      repository's values.
- [ ] It is written for the project's agent, not for a kanban.md developer, and does not reference
      this repository's layout, tests, or `run.ps1`.
- [ ] The file is treated as a portable tool: `tools/sync_tools.py` carries it, refreshes a stale
      copy, and reports it under `--check`.
- [ ] Opening an already-initialized project that predates this change adds the file through the
      existing automatic compare-and-repair.
- [ ] Tests cover initialization, the sync manifest, drift detection, and the byte-identical
      no-write case.
- [ ] `README.md` and `docs/SCHEMA.md` describe the file and where it lands.

## Implementation notes

Put it at `.kanban/AGENTS.md`. Inside `.kanban` it is unambiguously about the board, it travels
with the portable boundary, and it cannot collide with a root `AGENTS.md` or `CLAUDE.md` the
project already maintains for its own code.

Do not append to or rewrite a root-level `AGENTS.md`. That file is the developer's, it may be under
review or version control conventions we know nothing about, and silently editing it violates the
rule that user files are authoritative. If a pointer from the root file is wanted, print the
suggested one-line reference to the console and let a person add it.

Deriving the vocabularies from `board.yaml` is what makes this correct in a project whose
categories and statuses differ from this one's. Generate the document rather than copying a static
blob, or the first project with a custom status list gets instructions that are wrong.

Since sync overwrites drift, the file must be disposable by design. State that in the document
itself so nobody edits it expecting the change to survive.

## Human work

Review the wording once. This is the first thing another team's agent reads about kanban.md, and it
is the one document that has to be right without a person present to correct it.
