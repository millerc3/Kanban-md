---
id: KMD-003
title: Generate the agent board summary
status: ready
category: Storage
intervention: low
priority: medium
type: feature
blocked_by: [KMD-002]
tags: [agents, markdown]
created: 2026-07-26
updated: 2026-07-26
---

## Goal

Regenerate `.kanban/board.md` from ticket files so an agent can cheaply inspect
the current project state.

## Acceptance criteria

- [ ] The summary clearly states that it is generated.
- [ ] Active tickets are grouped by workflow state.
- [ ] Ready tickets retain their category grouping.
- [ ] Regeneration is deterministic.
