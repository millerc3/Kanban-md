---
id: KMD-001
title: Define the portable Markdown schema
status: done
category: Product
intervention: medium
priority: high
type: decision
blocked_by: []
tags: [schema, local-first]
source: []
created: 2026-07-26
updated: 2026-07-26
---

## Goal

Define an agent-readable ticket format that remains useful without the visual
application.

## Acceptance criteria

- [x] Ticket identity is independent of its filename.
- [x] Category and human intervention are first-class fields.
- [x] Unknown fields are preserved.
- [x] Git is optional.
