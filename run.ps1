#!/usr/bin/env -S powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File

param(
    [Parameter(Position = 0)]
    [string]$ProjectPath
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VirtualPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$AppUrl = "http://127.0.0.1:5000"
$ServerRunning = $false

if ($ProjectPath) {
    if (-not (Test-Path -LiteralPath $ProjectPath)) {
        Write-Error "Project path does not exist: $ProjectPath"
        exit 2
    }
    if (-not (Test-Path -LiteralPath $ProjectPath -PathType Container)) {
        Write-Error "Project path is not a directory: $ProjectPath"
        exit 2
    }
    $ProjectPath = (Resolve-Path -LiteralPath $ProjectPath).Path
}

try {
    $ExistingServer = Invoke-WebRequest -UseBasicParsing -Uri $AppUrl -TimeoutSec 1
    if ($ExistingServer.StatusCode -eq 200) {
        $ServerRunning = $true
    }
} catch {
    # No healthy server is listening yet; continue with normal startup.
}

if ($ServerRunning) {
    if ($ProjectPath) {
        $RequestBody = @{ path = $ProjectPath } | ConvertTo-Json
        $OpenResult = Invoke-RestMethod -Uri "$AppUrl/api/open" -Method Post -ContentType "application/json" -Body $RequestBody
        if ($OpenResult.tool_sync.Count -gt 0) {
            foreach ($Tool in $OpenResult.tool_sync) {
                $ToolPath = Join-Path $ProjectPath ".kanban\tools\$($Tool.name)"
                Write-Host ("{0}: {1}" -f $ToolPath, $Tool.status)
            }
        } elseif (-not $OpenResult.initialized) {
            Write-Host "$ProjectPath`: portable tool sync skipped (no .kanban directory)"
        }
        Write-Host "kanban.md is already running at $AppUrl"
        Write-Host "Re-pointed the server and any open browser tabs to $ProjectPath"
    } else {
        Write-Host "kanban.md is already running at $AppUrl"
    }
    exit 0
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
$StartupArguments = @((Join-Path $ProjectRoot "app.py"))
if ($ProjectPath) {
    $StartupArguments += $ProjectPath
}
& $VirtualPython @StartupArguments
