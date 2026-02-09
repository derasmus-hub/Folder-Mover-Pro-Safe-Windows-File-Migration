<#
.SYNOPSIS
    Package a release ZIP for distribution.

.DESCRIPTION
    Creates dist\release\FolderMoverPro-v<version>-win64.zip containing:
      - FolderMoverPro.exe          (GUI)
      - FolderMoverPro-CLI.exe      (CLI)
      - README-QuickStart.txt
      - demo\demo_cases.xlsx
      - demo\demo_source\
      - demo\demo_dest\

    Also computes SHA256 hashes for both EXEs and the ZIP.

.EXAMPLE
    .\build\package_release.ps1

.NOTES
    Author: Erasmus Labs
    Requires: Both EXEs must be built first (run build\build_exe.ps1).
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

# Get project root (parent of build directory)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DistDir = Join-Path $ProjectRoot "dist"
$ReleaseDir = Join-Path $DistDir "release"

Write-Host ""
Write-Host "  Folder Mover Pro - Release Packager" -ForegroundColor Cyan
Write-Host "  ====================================" -ForegroundColor Cyan
Write-Host ""

# Read version from pyproject.toml
$PyProjectPath = Join-Path $ProjectRoot "pyproject.toml"
$PyProjectContent = Get-Content $PyProjectPath -Raw
if ($PyProjectContent -match 'version\s*=\s*"([^"]+)"') {
    $Version = $Matches[1]
} else {
    Write-Host "ERROR: Could not read version from pyproject.toml" -ForegroundColor Red
    exit 1
}

Write-Host "  Version: $Version" -ForegroundColor White

# Verify required files exist
$GuiExe = Join-Path $DistDir "FolderMoverPro.exe"
$CliExe = Join-Path $DistDir "FolderMoverPro-CLI.exe"
$QuickStart = Join-Path $DistDir "README-QuickStart.txt"
$DemoCases = Join-Path $ProjectRoot "demo_cases.xlsx"
$DemoSource = Join-Path $ProjectRoot "demo_source"
$DemoDest = Join-Path $ProjectRoot "demo_dest"

$Missing = @()
if (-not (Test-Path $GuiExe))     { $Missing += "dist\FolderMoverPro.exe (run build\build_exe.ps1)" }
if (-not (Test-Path $CliExe))     { $Missing += "dist\FolderMoverPro-CLI.exe (run build\build_exe.ps1)" }
if (-not (Test-Path $QuickStart)) { $Missing += "dist\README-QuickStart.txt" }
if (-not (Test-Path $DemoCases))  { $Missing += "demo_cases.xlsx" }
if (-not (Test-Path $DemoSource)) { $Missing += "demo_source\" }
if (-not (Test-Path $DemoDest))   { $Missing += "demo_dest\" }

if ($Missing.Count -gt 0) {
    Write-Host ""
    Write-Host "ERROR: Missing required files:" -ForegroundColor Red
    foreach ($m in $Missing) {
        Write-Host "  - $m" -ForegroundColor Red
    }
    exit 1
}

# Create staging directory
$ZipName = "FolderMoverPro-v$Version-win64"
$StagingDir = Join-Path $ReleaseDir $ZipName
$ZipPath = Join-Path $ReleaseDir "$ZipName.zip"

Write-Host ""
Write-Host "  [1/4] Preparing staging directory..." -ForegroundColor Yellow

# Clean previous staging
if (Test-Path $StagingDir) { Remove-Item -Recurse -Force $StagingDir }
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }

New-Item -ItemType Directory -Path $StagingDir -Force | Out-Null

# Copy files to staging
Write-Host "  [2/4] Copying files..." -ForegroundColor Yellow

Copy-Item $GuiExe     (Join-Path $StagingDir "FolderMoverPro.exe")
Copy-Item $CliExe     (Join-Path $StagingDir "FolderMoverPro-CLI.exe")
Copy-Item $QuickStart (Join-Path $StagingDir "README-QuickStart.txt")

# Copy demo files
$DemoStaging = Join-Path $StagingDir "demo"
New-Item -ItemType Directory -Path $DemoStaging -Force | Out-Null

Copy-Item $DemoCases (Join-Path $DemoStaging "demo_cases.xlsx")

# Copy demo_source (exclude any files that were moved during testing)
Copy-Item -Recurse $DemoSource (Join-Path $DemoStaging "demo_source")

# Create clean demo_dest (empty directory for user to test with)
New-Item -ItemType Directory -Path (Join-Path $DemoStaging "demo_dest") -Force | Out-Null

Write-Host "  Staged files:" -ForegroundColor DarkGray
Get-ChildItem -Recurse $StagingDir | ForEach-Object {
    $RelPath = $_.FullName.Substring($StagingDir.Length + 1)
    if ($_.PSIsContainer) {
        Write-Host "    $RelPath\" -ForegroundColor DarkGray
    } else {
        Write-Host "    $RelPath ($([math]::Round($_.Length / 1KB, 1)) KB)" -ForegroundColor DarkGray
    }
}

# Create ZIP
Write-Host ""
Write-Host "  [3/4] Creating ZIP..." -ForegroundColor Yellow

Compress-Archive -Path "$StagingDir\*" -DestinationPath $ZipPath -CompressionLevel Optimal
$ZipInfo = Get-Item $ZipPath
Write-Host "  ZIP created: $ZipPath ($([math]::Round($ZipInfo.Length / 1MB, 2)) MB)" -ForegroundColor Green

# Clean up staging directory
Remove-Item -Recurse -Force $StagingDir

# Compute SHA256 hashes
Write-Host ""
Write-Host "  [4/4] Computing SHA256 hashes..." -ForegroundColor Yellow

$HashGui = (Get-FileHash $GuiExe -Algorithm SHA256).Hash
$HashCli = (Get-FileHash $CliExe -Algorithm SHA256).Hash
$HashZip = (Get-FileHash $ZipPath -Algorithm SHA256).Hash

Write-Host ""
Write-Host "  SHA256 Hashes:" -ForegroundColor Cyan
Write-Host "  FolderMoverPro.exe:      $HashGui" -ForegroundColor White
Write-Host "  FolderMoverPro-CLI.exe:  $HashCli" -ForegroundColor White
Write-Host "  $ZipName.zip:  $HashZip" -ForegroundColor White

# Write hashes to file
$HashFile = Join-Path $ReleaseDir "$ZipName.sha256"
@(
    "SHA256 Hashes for Folder Mover Pro v$Version",
    "============================================",
    "",
    "FolderMoverPro.exe:      $HashGui",
    "FolderMoverPro-CLI.exe:  $HashCli",
    "$ZipName.zip:  $HashZip",
    "",
    "To verify (PowerShell):",
    "  Get-FileHash .\FolderMoverPro.exe -Algorithm SHA256",
    "  Get-FileHash .\FolderMoverPro-CLI.exe -Algorithm SHA256"
) | Set-Content -Path $HashFile -Encoding UTF8

Write-Host ""
Write-Host "  RELEASE PACKAGING COMPLETE" -ForegroundColor Green
Write-Host "  ==========================" -ForegroundColor Green
Write-Host ""
Write-Host "  Outputs:" -ForegroundColor White
Write-Host "    $ZipPath" -ForegroundColor White
Write-Host "    $HashFile" -ForegroundColor White
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Yellow
Write-Host "    1. Upload ZIP to GitHub Releases" -ForegroundColor Yellow
Write-Host "    2. Include SHA256 hashes in release notes" -ForegroundColor Yellow
Write-Host "    3. Do NOT email the EXE files directly" -ForegroundColor Yellow
Write-Host ""
