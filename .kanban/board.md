<!--
GENERATED FILE — DO NOT EDIT MANUALLY.
Run: python3 .kanban/tools/regenerate_board.py
Source: .kanban/tickets/*.md
-->

# kanban.md board

> Generated summary. Markdown ticket files are authoritative.

## Inbox

### Product

| ID | Ticket | Intervention | Blocked by |
|---|---|---|---|
| KMD-008 | Add a POSIX launcher and document non-Windows use | medium | — |
| KMD-009 | Write agent instructions into a project during initialization | low | KMD-017 |
| KMD-010 | Add an end-to-end walkthrough to the README | low | KMD-008, KMD-009 |

### Storage

| ID | Ticket | Intervention | Blocked by |
|---|---|---|---|
| KMD-005 | Add a ticket query CLI for agents | low | — |
| KMD-014 | Validate priority and show it in the board summary | low | — |
| KMD-017 | Create tickets through a tool instead of by hand | low | — |

### Interface

| ID | Ticket | Intervention | Blocked by |
|---|---|---|---|
| KMD-011 | Capture stub tickets for an agent to flesh out | medium | — |
| KMD-012 | Archive a ticket by dragging it out of the board | medium | — |
| KMD-013 | Edit ticket fields from the drawer | medium | — |
| KMD-015 | Warn when starting a ticket with unfinished blockers | low | — |
| KMD-016 | Choose a ticket type and get a matching body template | low | KMD-011 |

## Done

| ID | Ticket | Category | Intervention | Blocked by |
|---|---|---|---|---|
| KMD-001 | Define the portable Markdown schema | Product | medium | — |
| KMD-002 | Read and write a local `.kanban` directory | Storage | low | KMD-001 |
| KMD-003 | Generate the agent board summary | Storage | low | KMD-002 |
| KMD-004 | Add drag-and-drop movement | Interface | low | KMD-002 |
| KMD-006 | Sync portable tools into a target project | Storage | low | — |
| KMD-007 | Open a project from a startup path argument | Interface | low | — |

## Archive

0 archived tickets retained under `.kanban/archive/`.
