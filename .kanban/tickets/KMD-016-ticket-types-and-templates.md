---
id: KMD-016
title: Choose a ticket type and get a matching body template
status: inbox
category: Interface
intervention: low
priority: low
type: feature
blocked_by: [KMD-011]
tags: [web-ui, templates, schema]
source: [docs/SCHEMA.md#markdown-body]
created: 2026-07-28
updated: 2026-07-28
---

## Goal

Stop starting every ticket from the feature template, so a bug or a spike opens with the sections
it actually needs.

## Context

`new_ticket_source` hardcodes `type: feature` and one fixed body: Goal, Context, Acceptance
criteria, Human work. Those are the right sections for a feature and the wrong ones for everything
else. A bug wants what happened, what was expected, and how to reproduce it. A spike is a question
with a time box, and writing acceptance criteria for one is a category error — the whole point is
that the answer is not known yet.

The field already varies in practice: KMD-001 is `type: decision`, written by hand. So the
vocabulary is real, the app just cannot express it.

This depends on KMD-011 because both change how a new ticket's body is produced, and because they
interact: a spike is *expected* to be under-specified, so it should not be flagged as needing
refinement merely for being a spike.

## Acceptance criteria

- [ ] The New Ticket dialog offers a type, defaulting to `feature` so current behaviour is the
      default.
- [ ] Each type produces its own body template with sections appropriate to it.
- [ ] The chosen type is written to `type` frontmatter.
- [ ] Templates are declared in one place, not spread through the create path.
- [ ] The type list can be declared in `board.yaml` and falls back to a built-in set when absent, so
      a project can use its own vocabulary.
- [ ] A ticket whose `type` is not in the list still validates — this field has never been enforced
      and hand-written tickets rely on that.
- [ ] The refinement flag from KMD-011 interacts sensibly with types that are under-specified by
      nature.
- [ ] Tests cover each built-in type's generated body, the default, a project-declared list, and an
      unrecognized type on an existing ticket.
- [ ] `docs/SCHEMA.md` documents the types and their templates.

## Implementation notes

Start with `feature`, `bug`, `chore`, `spike`, and `decision` — the last is already in use in this
project's own tickets.

Keep templates as data rather than branching inside `new_ticket_source`. A dict of type to section
list stays readable at five types and at fifteen; a chain of conditionals does not.

Resist validating `type` against the list. Every ticket in this repository was hand-written before
the app could set the field, and turning a descriptive field into an enforced one breaks files that
are correct. Declaring the list is for populating a dropdown, not for policing what exists.

The templates are the deliverable here, not the dropdown. A bug template that does not prompt for
reproduction steps is the same blank page with different headings.

## Human work

Review the section list for each type. This is editorial work — it decides what every future ticket
in every project using kanban.md is prompted to write down.
