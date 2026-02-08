# Run-FolderMoverPro.ps1
# Wrapper script to run Folder Mover Pro executable

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"

# Locate executable
$ScriptDir = Split-Path -Parent $PSScriptRoot
$ExePath = Join-Path $ScriptDir "dist\FolderMoverPro.exe"

if (-not (Test-Path $ExePath)) {
    Write-Host "ERROR: FolderMoverPro.exe not found at $ExePath" -ForegroundColor Red
    Write-Host ""
    Write-Host "Run the build script first:" -ForegroundColor Yellow
    Write-Host "  .\build\build_exe.ps1" -ForegroundColor Cyan
    Write-Host ""
    exit 1
}

# Run the executable with all passed arguments
& $ExePath @Arguments
exit $LASTEXITCODE
