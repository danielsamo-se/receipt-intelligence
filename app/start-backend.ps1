param([int]$Port = 8000, [string]$DatabasePath = '')
$ErrorActionPreference = 'Stop'
$jevProjectRoot = Split-Path -Parent $PSScriptRoot
$jevPython = Join-Path $jevProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $jevPython)) { throw 'Create .venv and install app/backend/requirements.txt first. See app/README.md.' }
if ($DatabasePath) { $env:RECEIPT_DB_PATH = $DatabasePath }
Push-Location $jevProjectRoot
try {
    & $jevPython -B -m uvicorn receipt_intelligence.api:app --app-dir app/backend --host 127.0.0.1 --port $Port
} finally { Pop-Location }
