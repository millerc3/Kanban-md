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
│   ├── regenerate_board.py
│   └── migrate_ticket_ids.py
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
- `tools/migrate_ticket_ids.py` adopts project-assigned ticket ids in a project
  that used its own numbering.
- `tickets/` contains every active ticket in one flat directory.
- `archive/` contains completed tickets retained by the developer.

## Refreshing portable tools

The files under `.kanban/tools/` are disposable copies maintained from a
kanban.md source checkout. Refresh them by passing the project root:

```sh
python3 tools/sync_tools.py /path/to/project
```

This copies the explicit portable-tool manifest, creates `.kanban/tools/` when
needed, and does not rewrite byte-identical files. It does not create a board:
the target must already contain `.kanban`.

Check for missing or stale copies without writing anything:

```sh
python3 tools/sync_tools.py --check /path/to/project
```

The check requires a kanban.md checkout because the canonical source files are
not available inside a portable project.

When a project is opened by the app, the running kanban.md checkout
automatically compares and repairs these portable copies. Initialization also
populates them. A selected directory without `.kanban` is left untouched so it
can use the app's normal initialization flow.

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

Ids are assigned by the project rather than chosen per ticket. `board.yaml`
declares the scheme:

```yaml
id_prefix: KMD
id_padding: 3
id_sequence: 12
```

- `id_prefix` is the project-wide prefix. Ids take the form `PREFIX-<number>`.
- `id_padding` is the zero-padded width of the number. Numbers wider than the
  padding are written in full, and `KMD-9` still sorts before `KMD-10`.
- `id_sequence` is the high-water mark. The next id is one more than the larger
  of this value and the highest number found across active and archived
  tickets, so deleting a ticket never hands its number to a new one.

All three fields are optional. A project without `id_prefix` keeps whatever ids
its tickets already use, and the application refuses to assign new ones until
the scheme is adopted.

To read the next id without writing anything:

```sh
python3 .kanban/tools/regenerate_board.py --next-id
```

Ids that predate the scheme stay valid. `--strict-ids` reports them when you
want that enforced:

```sh
python3 .kanban/tools/regenerate_board.py --check --strict-ids
```

### Adopting the scheme in an existing project

`tools/migrate_ticket_ids.py` migrates a project that used its own numbering.
It previews the change and writes nothing until `--apply` is given, and it
keeps a timestamped backup of `.kanban` when it does.

```sh
python3 .kanban/tools/migrate_ticket_ids.py --adopt --prefix KMD
```

`--adopt` is the default and the least disruptive option: it records the scheme
in `board.yaml` and seeds `id_sequence` above every existing id. No ticket file
is touched, existing ids keep working, and only new tickets follow the scheme.

`--renumber` additionally rewrites ids that do not match the scheme, remapping
every `blocked_by` reference and renaming the affected files. Ids that already
match keep their number. `--renumber-all` instead assigns a clean sequence to
every ticket. Both record the previous id as `legacy_id` and report — without
rewriting — any old id still mentioned in ticket prose.

## Core frontmatter

```yaml
---
id: PROJ-123
legacy_id: NET-7
title: Replicate the sacrifice wallet
status: ready
category: Networking
intervention: low
priority: high
type: feature
blocked_by: [PROJ-100]
tags: [fishnet, economy]
source: [docs/design.md#sacrifice-wallet]
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

### Source

`source` is a list of provenance references. When a reference points into a
Markdown file, use a project-relative path followed by the target heading's
fragment identifier:

```yaml
source: [docs/design.md#sacrifice-wallet]
```

The `#sacrifice-wallet` suffix is commonly called a heading anchor or fragment.
Use the lowercase, hyphen-separated form of the heading text. For a reference
that must remain stable when the heading is renamed, place an explicit anchor
immediately before the heading in the source document:

```md
<a id="sacrifice-wallet"></a>

## Sacrifice wallet
```

Then use `docs/design.md#sacrifice-wallet` in the ticket. Provenance that does
not refer to a Markdown section, such as `web-ui`, may remain a plain label.

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
- `legacy_id` is optional and records the id a ticket carried before migration.
  It is never used for lookup or dependency resolution.
- Missing category defaults to `Uncategorized`.
- Missing or invalid intervention currently defaults to `medium` and should be
  surfaced by future validation.
- The application does not require Git.
