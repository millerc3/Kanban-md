# kanban.md

A local-first Kanban ticket tracker where every ticket is an ordinary Markdown
file that remains easy for both people and agents to read.

## Run on Windows

```powershell
.\run.ps1
```

Then open <http://127.0.0.1:5000> in Firefox or any other browser.

To open a project immediately, pass its directory to either launcher:

```powershell
.\run.ps1 D:\Development\my-project
.\.venv\Scripts\python.exe app.py D:\Development\my-project
```

If kanban.md is already running, `run.ps1 <path>` re-points that server (and
any browser tabs using it) to the supplied project.

The first run creates a local Python environment and installs Flask. Later runs
start immediately.

If PowerShell script execution is disabled, use:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

## Use

1. Open a project directory using the native folder picker or path field.
2. If necessary, initialize its `.kanban` directory.
3. Create, inspect, filter, and move tickets on the board.

The server binds only to `127.0.0.1`. Project content is read and written
locally and is never uploaded.

See [docs/SCHEMA.md](docs/SCHEMA.md) for the portable file format.

## Creating tickets from the command line

The browser UI is one way to create a ticket. From a terminal — or from a
coding agent working in one — use the portable tool instead:

```sh
python3 .kanban/tools/create_ticket.py --title "Short imperative title" --category Storage --body-file body.md
```

That single command assigns the ID, writes the frontmatter, and regenerates
`board.md`, then prints the ID and path it created. Add `--json` to get
`{"id": ..., "path": ...}` for scripting. If anything fails validation, nothing
is written at all and the command exits nonzero.

The body is yours: `--body-file PATH`, or `--body-stdin` to read from a pipe.
Leave both off and the ticket starts from the template for its type. Everything
else is a flag — `--status`, `--intervention`, `--priority`, `--type`, `--tags`,
`--blocked-by`, `--source` — and `--kanban PATH` points at a project other than
the one containing your working directory.

Writing a ticket file by hand in an editor still works and always will. The
tool exists so that nobody has to remember the mechanical parts.

## Ticket IDs

Ticket IDs are assigned by the project, not typed in by hand. `board.yaml`
declares a prefix and a high-water mark, and each new ticket takes the next
number. Deleting a ticket never releases its number for reuse.

To read the next ID without creating anything:

```sh
python3 .kanban/tools/regenerate_board.py --next-id
```

That is a query, not a reservation. Two people running it at the same moment
get the same answer, so create tickets with `create_ticket.py`, which claims
the number and writes the file as one step.

### Converting an existing project

A project that used its own numbering can adopt the scheme without rewriting
anything. This records the prefix and starts numbering above every ID already
in use, leaving existing tickets exactly as they are:

```sh
python3 .kanban/tools/migrate_ticket_ids.py --adopt --prefix PROJ --apply
```

To also renumber the IDs that do not match the scheme — remapping `blocked_by`
references and renaming files — use `--renumber`, or `--renumber-all` for a
clean sequence across every ticket. Run any of these without `--apply` first to
preview the plan; nothing is written until you pass it, and a timestamped
backup of `.kanban` is kept when you do.

## Syncing portable tools

From a kanban.md checkout, refresh the portable tools carried by another
initialized project:

```sh
python3 tools/sync_tools.py /path/to/project
```

The argument is the project root, not its `.kanban` directory. The command
copies only the explicit portable-tool manifest and leaves matching files
untouched. It refuses to create a missing `.kanban`; initialize the project in
the app first.

To detect missing or stale copies without changing the target:

```sh
python3 tools/sync_tools.py --check /path/to/project
```

The app performs the same compare-and-repair operation automatically whenever
an existing project is opened, including through `run.ps1 <path>`. Newly
initialized projects receive the portable tools immediately. Opening a folder
without `.kanban` still works and leaves it untouched until initialization.

## Generated board summary

`.kanban/board.md` is generated and disposable. It must never be manually
edited; the Markdown files under `.kanban/tickets/` and `.kanban/archive/` are
authoritative.

`create_ticket.py` and the browser UI regenerate the summary themselves. After
editing, moving, or archiving ticket files by hand, run:

```sh
python3 .kanban/tools/regenerate_board.py
```

Use `python3 .kanban/tools/regenerate_board.py --check` to validate ticket data
and confirm the summary is current. Fix validation failures in ticket files,
never in `board.md`.
