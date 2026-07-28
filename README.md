# kanban.md

A local-first Kanban ticket tracker where every ticket is an ordinary Markdown
file that remains easy for both people and agents to read.

## Run on Windows

```powershell
.\run.ps1
```

Then open <http://127.0.0.1:5000> in Firefox or any other browser.

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

## Generated board summary

`.kanban/board.md` is generated and disposable. It must never be manually
edited; the Markdown files under `.kanban/tickets/` and `.kanban/archive/` are
authoritative.

After creating, editing, moving, or archiving tickets, agents must run:

```sh
python3 .kanban/tools/regenerate_board.py
```

Use `python3 .kanban/tools/regenerate_board.py --check` to validate ticket data
and confirm the summary is current. Fix validation failures in ticket files,
never in `board.md`.
