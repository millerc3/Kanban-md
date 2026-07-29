---
id: KMD-011
title: Capture stub tickets for an agent to flesh out
status: inbox
category: Interface
intervention: medium
priority: high
type: feature
blocked_by: []
tags: [agents, web-ui, schema, workflow]
source: [docs/SCHEMA.md#core-frontmatter]
created: 2026-07-28
updated: 2026-07-28
---

## Goal

Let a person drop a half-formed idea onto the board in ten seconds, then tell an agent "go flesh
out the stubs" and have that instruction be executable without further explanation.

## Context

The workflow this serves is: catch the thought before it evaporates, and let an agent do the work
of turning it into a real ticket later. The New Ticket dialog does not support the first half — it
collects a title, a category, and an intervention level, and writes a body of placeholder prose. The
one sentence the person actually had in mind has nowhere to go.

The second half is the part that makes the feature work, and it is easy to under-build. A flag that
only exists in frontmatter means "refine my stubs" still forces an agent to open every ticket file
to discover which ones qualify. The flag has to reach `board.md`, because that is the file agents
read first and the only place a scan is cheap. Build the marker and the input together or the
feature does not pay off.

A note on the control: a lone radio button cannot express this. Once pressed it cannot be
unpressed, so "not yet marked well-defined" becomes unreachable after the first click. A checkbox,
a toggle, or an honest two-option group all work.

## Acceptance criteria

- [ ] The New Ticket dialog has a multi-line description field.
- [ ] Its content becomes the `## Goal` body of the new ticket, replacing the placeholder text.
      Leaving it empty keeps the current placeholder behaviour.
- [ ] The dialog has a control marking whether the description is well-defined, defaulting to *not*
      well-defined.
- [ ] Every ticket created through the UI records the resulting state in frontmatter explicitly, so
      the value is never ambiguous for a ticket the app made.
- [ ] A ticket with the field absent is treated as well-defined.
- [ ] `board.md` marks tickets needing refinement so an agent can find them without opening files.
- [ ] The card shows the state, so the board is scannable by eye too.
- [ ] The generator validates the field's value and rejects an unrecognized one.
- [ ] Tests cover: description written into the body, empty description, both flag states, an older
      ticket with the field absent, the generated marker, and validation of a bad value.
- [ ] `docs/SCHEMA.md` documents the field, and the instructions from KMD-009 tell an agent what to
      do when it sees one.

## Implementation notes

Do not add a `description:` frontmatter field. The body already opens with `## Goal`, and a
frontmatter copy would create two homes for the same sentence and contradict the schema's rule that
the Markdown body carries ticket content.

Name the flag as an enum rather than a boolean — `refinement: needed | done` fits the existing
`intervention` and `priority` vocabularies, and leaves room for a third state later. A bare
`well_defined: true` does not.

Absent must mean done. Absent meaning "needed" would silently flag every ticket written before this
landed, and a signal that fires on everything is not a signal.

For the `board.md` marker, prefer a compact per-row indicator or a short trailing list of the IDs
needing refinement. KMD-005 already warns against widening the generated tables, and a whole extra
column for a two-state field is exactly the widening it warns about.

`--refinement` is a natural filter for the query CLI in KMD-005 if that ticket is built after this
one.

## Human work

Pick the control — checkbox, toggle, or two-option group — and decide whether the flag can be
cleared from the UI at all. Today the app can only create a ticket and change its status, so a stub
marked here can only be un-marked by editing the file or by KMD-013 landing first. Leaving it to
the file is defensible; it should be a decision rather than an accident.
