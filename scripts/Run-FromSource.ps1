# Run-FromSource.ps1
# Run Folder Mover Pro directly from Python source

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"

# Get project root
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SrcDir = Join-Path $ProjectRoot "src"

# Set PYTHONPATH
$env:PYTHONPATH = $SrcDir

# Change to project root
Push-Location $ProjectRoot

try {
    python -m folder_mover.cli @Arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
