# kanban.md file format

The `.kanban` directory is the portable project boundary. The application reads
the board from Markdown and YAML files inside it; there is no separate ticket
database.

## Directory layout

```text
.kanban/
├── board.yaml
├── board.md
├── tools/
│   └── regenerate_board.py
├── tickets/
│   └── PROJ-123-descriptive-title.md
└── archive/
    └── 2026/
```

- `board.yaml` contains project-level configuration.
- `board.md` is a generated, disposable summary for agents. It is never
  authoritative and must never be manually edited.
- `tools/regenerate_board.py` is the portable, standard-library-only board
  generator.
- `tickets/` contains every active ticket in one flat directory.
- `archive/` contains completed tickets retained by the developer.

## Regenerating and validating the board

After creating, editing, moving, or archiving any ticket, agents must run this
from the project root:

```sh
python3 .kanban/tools/regenerate_board.py
```

Validate all active and archived ticket data and confirm that `board.md` is
current with:

```sh
python3 .kanban/tools/regenerate_board.py --check
```

Validation failures must be fixed in the authoritative ticket files, never in
`board.md`. The generated summary can be deleted and recreated at any time.

## Ticket identity

The `id` field is the immutable identity. Filenames are descriptive and may
change without changing ticket identity.

## Core frontmatter

```yaml
---
id: PROJ-123
title: Replicate the sacrifice wallet
status: ready
category: Networking
intervention: low
priority: high
type: feature
blocked_by: [PROJ-100]
tags: [fishnet, economy]
created: 2026-07-26
updated: 2026-07-26
---
```

### Status

The initial workflow is:

`inbox` → `ready` → `in_progress` → `review` → `done`

`blocked` is an explicit status and may be entered from any active state.

### Category

`category` is a first-class planning dimension such as `Networking`, `Enemies`,
or `Abilities`. Ready tickets are grouped by category. Once work begins, the
workflow state is more important and the board shows those tickets in flat
columns.

### Human intervention

Every ticket has exactly one structured `intervention` level:

- `low`: an agent can deliver the work; a person reviews and validates it.
- `medium`: delivery needs editor work, coordination, or a bounded decision.
- `high`: the work is human-led because it is creative, directional, or
  hands-on.

This field is separate from arbitrary tags and from priority.

## Markdown body

The recommended sections are:

```md
## Goal

## Context

## Acceptance criteria

## Implementation notes

## Human work
```

Only the sections useful to a ticket are required. Unknown frontmatter fields
and body sections must be preserved by the application.

## Compatibility rules

- The schema is additive and forgiving.
- Unknown fields are retained.
- Missing status defaults to `inbox`.
- Missing category defaults to `Uncategorized`.
- Missing or invalid intervention currently defaults to `medium` and should be
  surfaced by future validation.
- The application does not require Git.
