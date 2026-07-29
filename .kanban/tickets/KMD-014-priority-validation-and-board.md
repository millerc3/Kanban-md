---
id: KMD-014
title: Validate priority and show it in the board summary
status: inbox
category: Storage
intervention: low
priority: medium
type: chore
blocked_by: []
tags: [generator, schema, validation]
source: [docs/SCHEMA.md#core-frontmatter]
created: 2026-07-28
updated: 2026-07-28
---

## Goal

Finish `priority`. It is currently written, displayed, and documented, but declared nowhere and
checked by nothing.

## Context

Every ticket the app creates gets `priority: medium`. The card renders it as a styled badge.
`docs/SCHEMA.md` lists it in the core frontmatter example. And yet:

- `board.yaml` declares `intervention_levels` and no equivalent for priority.
- `regenerate_board.py` never mentions the field, so `priority: banana` validates cleanly and
  reaches the UI as a badge with a class nobody styled.
- `board.md` omits it, so the file agents read to decide what to work on carries no signal about
  what matters.

`intervention` is the model to copy: declared in `board.yaml`, validated by the generator, rendered
in the summary. `priority` should either follow it or be documented as deliberately free-form. The
current half-state is the worst of both — strict enough that people rely on it, loose enough that
nothing holds.

Showing it in `board.md` is the half that changes behaviour. An agent picking up work reads the
generated summary; without priority there, everything looks equally urgent.

## Acceptance criteria

- [ ] `board.yaml` declares `priority_levels`, defaulting to `[low, medium, high]` when absent.
- [ ] The generator validates `priority` against that list and reports an unrecognized value the
      same way it reports a bad intervention.
- [ ] A missing `priority` has one documented default and is not a validation failure — existing
      tickets must keep validating.
- [ ] `board.md` shows priority in the ticket tables.
- [ ] Ordering within a group is stable and documented — either unchanged, or by priority with
      natural ID order as the tiebreak.
- [ ] Tests cover: a valid value, an invalid value, an absent value, a project with custom
      `priority_levels`, a project with none declared, and the generated output.
- [ ] `docs/SCHEMA.md` documents the levels, the default, and the config key.
- [ ] The exported `board.md` files under `exports/` are regenerated and pass `--check` with their
      portable tool.

## Implementation notes

Adding a column widens every table, which KMD-005 flags as a real cost. Priority earns it in a way
a two-state flag does not: it is what a reader is looking for when they open the summary. If the
tables get unwieldy, drop `intervention` from the Done section rather than dropping priority —
nobody triages finished work by how much human involvement it needed.

If ordering changes, it changes for every project, and any test asserting current row order will
need updating. Decide before writing, and prefer leaving order alone unless priority ordering is
actually wanted.

Follow how `intervention_levels` is read from `board.yaml` so a project with an unusual scheme —
four levels, or numeric ones — works without a special case.

## Human work

Decide whether `board.md` ordering should change, since that affects every project's generated
output, not just this one's.
