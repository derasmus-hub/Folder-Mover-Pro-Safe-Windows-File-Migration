# Show-Version.ps1
# Display Folder Mover Pro version information

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ExePath = Join-Path $ProjectRoot "dist\FolderMoverPro.exe"
$SrcDir = Join-Path $ProjectRoot "src"

Write-Host ""
Write-Host "  Folder Mover Pro" -ForegroundColor Cyan
Write-Host "  =================" -ForegroundColor Cyan
Write-Host ""

if (Test-Path $ExePath) {
    $Version = & $ExePath --version 2>&1
    $FileInfo = Get-Item $ExePath

    Write-Host "  Version:    $Version" -ForegroundColor Green
    Write-Host "  Executable: $ExePath"
    Write-Host "  Size:       $([math]::Round($FileInfo.Length / 1MB, 2)) MB"
    Write-Host "  Modified:   $($FileInfo.LastWriteTime)"
} else {
    Write-Host "  Executable not built yet." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  To build:" -ForegroundColor Gray
    Write-Host "    .\build\build_exe.ps1" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  To run from source:" -ForegroundColor Gray
    $env:PYTHONPATH = $SrcDir
    $Version = python -c "from folder_mover import PRODUCT_VERSION; print(PRODUCT_VERSION)" 2>&1
    Write-Host "  Version (source): $Version" -ForegroundColor Green
}

Write-Host ""
