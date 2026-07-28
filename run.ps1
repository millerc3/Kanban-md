#!/usr/bin/env -S powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VirtualPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$AppUrl = "http://127.0.0.1:5000"

try {
    $ExistingServer = Invoke-WebRequest -UseBasicParsing -Uri $AppUrl -TimeoutSec 1
    if ($ExistingServer.StatusCode -eq 200) {
        Write-Host "kanban.md is already running at $AppUrl"
        exit 0
    }
} catch {
    # No healthy server is listening yet; continue with normal startup.
}

if (-not (Test-Path -LiteralPath $VirtualPython)) {
    Write-Host "Setting up kanban.md for first use..."
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($PythonCommand) {
        $PythonMajor = & $PythonCommand.Source -c "import sys; print(sys.version_info.major)" 2>$null
    }

    if ($PythonMajor -eq "3") {
        & $PythonCommand.Source -m venv (Join-Path $ProjectRoot ".venv")
    } else {
        $PythonLauncher = Get-Command py -ErrorAction SilentlyContinue
        if (-not $PythonLauncher) {
            throw "Python 3 is required. Install it from python.org, then run this script again."
        }
        & $PythonLauncher.Source -3 -m venv (Join-Path $ProjectRoot ".venv")
        if ($LASTEXITCODE -ne 0) {
            throw "Python 3 could not start. Install or repair Python 3, then run this script again."
        }
    }
    & $VirtualPython -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
}

Set-Location -LiteralPath $ProjectRoot
Write-Host "kanban.md is available at $AppUrl"
Write-Host "Press Ctrl+C to stop the server."
& $VirtualPython (Join-Path $ProjectRoot "app.py")
