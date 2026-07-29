---
id: KMD-018
title: Validate a new ticket's body has the sections it needs
status: inbox
category: Storage
intervention: medium
priority: medium
type: feature
blocked_by: [KMD-011, KMD-017]
tags: [agents, cli, quality]
source: [AGENTS.md#creating-a-ticket]
created: 2026-07-29
updated: 2026-07-29
---

## Goal

Require a new ticket to arrive with the sections that make it actionable — what it is for, why, and
how anyone will know it is finished — so the emptiness is caught by the process that created the
ticket rather than by the person who opens it a week later.

## Context

`create_ticket.py` validates that a body exists, not that it says anything. An agent can omit
`--body-file` entirely and the tool writes the type template, reports success, and exits zero. The
ticket then looks real on the board — it has an id, a title, a category, a row in `board.md` — and
nothing distinguishes it from a ticket someone actually thought about until it is opened.

That failure is quiet and it lands on a person, which is the combination worth spending code on.

The check has to be positive rather than negative. Looking only for leftover template prose passes a
body that reads `## Goal` followed by one line, with no context and no statement of done: no
template text, no placeholder, nothing to flag, and nearly as useless as the template itself. So the
rule is that the required sections are present and carry content of their own. A section left
holding the template's sentence is then just one case of a section with nothing in it, rather than a
separate rule.

What is checkable here stays mechanical, not editorial. No tool can judge whether "Prove foobar is
called when baz happens" is a good goal, and nothing in this ticket should try. It can see that a
section is absent, empty, or untouched. That is the difference between a ticket that was written and
one that was not, and it is the only difference worth enforcing.

An opt-in strictness flag would not catch any of it. The caller who would have to pass the flag is
the same agent that just shipped the template, and an agent careless enough to do that will not
volunteer the argument that refuses it. This is why the `--strict-ids` precedent does not transfer:
that flag is opt-in because projects carry legacy ids they never chose, so enforcement has to be
their decision. At creation time there is no legacy corpus. Every ticket the tool makes is new, so
the check can simply always run.

The exemption already exists as a schema field. KMD-011 introduces `refinement: needed | done`, and
`needed` means precisely "this body is deliberately thin, an agent will flesh it out." A ticket that
declares `refinement: done` while its Goal is still template prose is asserting something untrue,
and the tool can refuse it on that basis alone. A ticket that declares `needed` has opted out
honestly, in the file, where a person can see the claim — unlike a command-line flag, which
evaporates with the shell history.

This also settles what the web UI should do. The New Ticket dialog collects a title, a category, and
an intervention level, and writes placeholder prose: it is a stub maker. It should create with
`refinement: needed` and be exempt, which is what KMD-011 already plans, since its control defaults
to *not* well-defined.

One tension to keep straight, because getting it backwards would be expensive. `docs/SCHEMA.md`
states that only the sections useful to a ticket are required, and that stays true. This is a policy
about what the creation tool will produce, not a change to the portable format. The generator must
go on accepting a ticket with no sections at all, or every project carrying a terse old ticket fails
validation the moment it syncs a new tool.

## Acceptance criteria

- [ ] Creating a ticket is refused unless its body carries the required sections, each with content
      of its own: nothing is written, and the exit is nonzero.
- [ ] A section that is present but still holds the template's prose counts as empty.
- [ ] The refusal names the sections at fault, so the caller learns what to write rather than what
      flag to add.
- [ ] The required set is a declared list in the shared module, not a rule scattered through the
      code, so KMD-016 can vary it per ticket type.
- [ ] Content is required, but its shape is not: an Acceptance criteria section need not use
      checkbox syntax.
- [ ] A ticket created with `refinement: needed` is exempt and is never checked.
- [ ] `refinement` is settable through the creation tool, and `POST /api/tickets` sets `needed`
      until the dialog can collect a real description.
- [ ] Absent `refinement` follows whatever KMD-011 defined; this ticket does not redefine it.
- [ ] There is no strictness flag. The field is the only opt-out.
- [ ] The check is one function in the shared creation module, so the CLI and the endpoint agree on
      what an unwritten body is.
- [ ] Nothing is added to `regenerate_board.py`. Existing tickets are not audited, no currently
      valid board becomes noisy, and a hand-written ticket with no sections stays valid.
- [ ] Tests cover: a missing section refused, an empty section refused, a section left as template
      prose refused, a complete body accepted, an exempt stub accepted with a template body, the
      refusal leaving no file and no consumed id, and the endpoint still creating tickets.
- [ ] `AGENTS.md` states that the refusal means write the body, and that marking a ticket
      `refinement: needed` is the honest response when the body genuinely is not ready.
- [ ] `docs/SCHEMA.md` records that the required sections are a creation-time policy and not a
      format requirement.

## Implementation notes

Require `## Goal`, `## Context`, and `## Acceptance criteria`. Leave `## Implementation notes` and
`## Human work` optional: plenty of good tickets have neither, and a rule that fires on them is a
rule people learn to satisfy with a line of filler.

The checks belong beside the templates in `tools/create_ticket.py`. That module already owns what a
new ticket contains, and splitting "what we write" from "what we require" across two files would put
them out of step on the first change to either.

Compare against the template per section, not the whole body and not a word count. Whole-body
equality misses the common case of an agent filling in `## Goal` and leaving `## Context` untouched.
Length is the wrong axis in both directions: a short section written by a person is fine, and a long
one made of placeholder prose is not.

Keep the required set short. Without a flag, every entry becomes project policy, and the cost of a
false positive is a refused ticket.

Do not call a language model, score prose, or gate on length. The value here is that the rule is
mechanical enough that a person can predict it, and predictable enough that satisfying it means
writing the body rather than gaming the checker.

Auditing every existing ticket is a different feature with a much larger blast radius and belongs in
its own ticket if it is wanted at all.

## Human work

Confirm the trade this makes: someone writing a genuinely complete two-line ticket must either fill
in three sections or label it `refinement: needed`. Also confirm the refusal wording, since it is
the thing an agent will read most often.
