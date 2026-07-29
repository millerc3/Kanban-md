---
id: KMD-019
title: Keep apostrophes from splitting words in ticket filenames
status: inbox
category: Storage
intervention: low
priority: low
type: chore
blocked_by: [KMD-017]
tags: [cli, polish]
source: [tools/create_ticket.py]
created: 2026-07-29
updated: 2026-07-29
---

## Goal

Stop apostrophes from turning into stray hyphens in generated ticket filenames, so a title with a
possessive reads as one word rather than two.

## Context

`safe_slug()` in `tools/create_ticket.py` replaces every run of non-alphanumeric characters with a
hyphen. An apostrophe sits inside a word rather than between two, so `ticket's` becomes `ticket-s`
and the reader sees a word that was cut in half. KMD-018 carries the first real example:
`KMD-018-validate-a-new-ticket-s-body-has-the-sections-it-needs.md`.

This is cosmetic and nothing depends on it. The id is identity, the filename is descriptive, and
`docs/SCHEMA.md` already says a filename may change. The reason to fix it anyway is that the slug is
the part of a ticket a person reads most often outside the app — in a file listing, a diff, a branch
name — and a fix costs one line.

Straight and curly apostrophes both occur in practice. A title pasted from a document or written on
a phone will carry `’` rather than `'`, and handling only the ASCII form would leave the same
artefact for anyone who does not type in a code editor.

Existing files are not affected and must not be renamed. Renaming ticket files to match a new slug
rule would rewrite user data for a cosmetic gain, and the id is what anything else refers to.

## Acceptance criteria

- [ ] An apostrophe inside a word is dropped rather than replaced, so `ticket's` slugs as
      `tickets`.
- [ ] Both the ASCII apostrophe and the typographic right single quotation mark are handled.
- [ ] Every other separator keeps its current behaviour, and a title of only punctuation still
      falls back to `ticket`.
- [ ] No existing ticket file is renamed by this change.
- [ ] Tests cover a possessive title, a curly apostrophe, and the existing fallback.

## Implementation notes

The change belongs in `safe_slug()` alone: strip the apostrophe characters, then run the existing
substitution. Doing it in that order is what merges the word; substituting first has already
inserted the hyphen.

Leave the rest of the character handling as it is. This is a one-character fix, not an invitation to
add transliteration or unicode normalisation, which would change slugs for existing projects that
sync the tool.

## Human work

None expected beyond confirming the resulting filenames look right.
