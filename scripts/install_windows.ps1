param(
  [string]$InstallDir = "$env:USERPROFILE\Judicex",
  [int]$Port = 5050
)

$ErrorActionPreference = "Stop"

Write-Host "Installing Judicex in $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

$RepoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $RepoRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python 3.11+ is required. Install it from https://www.python.org/downloads/windows/"
}

python -m venv "$InstallDir\.venv"
& "$InstallDir\.venv\Scripts\python.exe" -m pip install --upgrade pip
& "$InstallDir\.venv\Scripts\python.exe" -m pip install -e ".[crypto]"

$Launcher = Join-Path $InstallDir "run_judicex.bat"
@"
@echo off
set JUDICEX_DB=%USERPROFILE%\Judicex\memory.db
"$InstallDir\.venv\Scripts\python.exe" -m judicex_memory_os.web_app --db "%JUDICEX_DB%" --area civile --bind 127.0.0.1 --port $Port
"@ | Set-Content -Encoding ASCII $Launcher

Pop-Location

Write-Host ""
Write-Host "Done. Start Judicex with:"
Write-Host "  $Launcher"
Write-Host "Then open http://127.0.0.1:$Port"
