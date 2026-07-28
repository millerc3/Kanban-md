---
id: KMD-002
title: Read and write a local `.kanban` directory
status: done
category: Storage
intervention: low
priority: high
type: feature
blocked_by: [KMD-001]
tags: [filesystem, markdown]
source: []
created: 2026-07-26
updated: 2026-07-26
---

## Goal

Allow a developer to open any project directory containing `.kanban` and use
its Markdown tickets as the board.

## Acceptance criteria

- [x] A project directory can be selected.
- [x] Markdown tickets are parsed from `.kanban/tickets`.
- [x] A folder without `.kanban` can be initialized.
- [x] Status changes update the ticket frontmatter.
- [x] A new ticket can be created as Markdown.

## Implementation notes

The Flask server owns filesystem access. The interface works in Firefox and
other browsers because the browser never receives direct directory handles.
