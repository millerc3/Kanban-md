---
id: KMD-013
title: Edit ticket fields from the drawer
status: inbox
category: Interface
intervention: medium
priority: high
type: feature
blocked_by: []
tags: [web-ui, api, editing]
source: [AGENTS.md#board-md-is-generated]
created: 2026-07-28
updated: 2026-07-28
---

## Goal

Let a ticket's fields be corrected where the ticket is being looked at, instead of sending the
reader to a text editor for a one-word change.

## Context

The API can create a ticket and change its status. That is the whole of what the app can do to a
ticket. Fixing a typo in a title, moving something to the right category, raising a priority,
adding a tag, or recording a dependency all mean leaving the app, finding the file, editing
frontmatter by hand, and remembering to regenerate the board.

The board is a viewer with one write path. That is a much smaller product than the files can
support, and it is the gap most likely to send someone back to an editor and keep them there.

`AGENTS.md` already sets the terms: any API that edits a ticket must provide the same
regenerate-or-rollback guarantee as create and status-change, and must preserve unknown frontmatter
and body content. `update_frontmatter` exists and is used by the status endpoint, so the mechanism
is proven — this is mostly about scope and the drawer.

## Acceptance criteria

- [ ] The drawer can edit: title, category, intervention, priority, tags, and `blocked_by`.
- [ ] Editing goes through the existing PATCH endpoint, extended rather than duplicated.
- [ ] `id` cannot be changed through the API, matching the create endpoint's refusal of a supplied
      ID.
- [ ] Unknown frontmatter fields and the entire Markdown body survive an edit byte-for-byte.
- [ ] `updated` is set on a successful edit and left alone when nothing changed.
- [ ] The board regenerates after a successful edit; a validation failure restores the previous file
      contents and reports what failed.
- [ ] Invalid values are rejected: an unknown intervention level, and a `blocked_by` entry naming a
      ticket that does not exist in either active or archived files.
- [ ] A ticket cannot be made to block itself.
- [ ] Renaming a ticket does not rename its file — the filename is descriptive and identity lives in
      `id`.
- [ ] Tests cover each editable field, unknown-field preservation, body preservation, rollback on
      validation failure, a rejected `id` change, and an invalid dependency.

## Implementation notes

Body editing is deliberately excluded. A Markdown editor is a different feature with different
failure modes, and the frontmatter fields are where the friction actually is. Say so in the drawer
so the omission reads as a decision rather than a missing button.

Leaving the filename alone on a title change is the correct behaviour and will look like a bug to
someone watching the directory. It matches what the schema says about identity, and renaming a file
under a concurrent agent's feet is a worse problem than a stale-looking name.

`blocked_by` validation must consult archived tickets as well as active ones, or archiving a
blocker will start breaking edits to the tickets it blocks.

Do not add a second write path in `app.js`. The status mover already patches and refreshes; the
field editors should reuse it.

## Human work

Confirm the editable field list. Adding fields later is easy; removing one after people have used
it is not.
