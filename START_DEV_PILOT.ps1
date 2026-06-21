$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[DevPilot] Creating isolated Python environment for first run..."
    py -m venv .venv
}
& ".venv\Scripts\python.exe" .\run.py
