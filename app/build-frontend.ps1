$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'node-runtime.ps1')
$jevNodeDirectory = Resolve-ReceiptNode
$env:PATH = $jevNodeDirectory + ';' + $env:PATH
Push-Location (Join-Path $PSScriptRoot 'frontend')
try {
    & (Join-Path $jevNodeDirectory 'npm.cmd') run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally { Pop-Location }
