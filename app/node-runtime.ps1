function Resolve-ReceiptNode {
    $jevNodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($jevNodeCommand) { return Split-Path -Parent $jevNodeCommand.Source }
    $jevPortablePointer = Join-Path $PSScriptRoot '.tools\node-path.txt'
    if (Test-Path -LiteralPath $jevPortablePointer) {
        $jevPortableDirectory = [System.IO.File]::ReadAllText($jevPortablePointer).Trim()
        if (Test-Path -LiteralPath (Join-Path $jevPortableDirectory 'node.exe')) { return $jevPortableDirectory }
    }
    throw 'Node.js is not available. Install a current Node.js LTS release, reopen PowerShell, and run this command again.'
}
