# build_exe.ps1
# Builds Folder Mover Pro as a single Windows executable
# Requires: Python 3.8+ installed and in PATH

param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

# Get project root (parent of build directory)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DistDir = Join-Path $ProjectRoot "dist"
$BuildDir = Join-Path $ProjectRoot "build\pyinstaller"
$SrcDir = Join-Path $ProjectRoot "src"

Write-Host ""
Write-Host "  Folder Mover Pro - Build Script" -ForegroundColor Cyan
Write-Host "  ================================" -ForegroundColor Cyan
Write-Host ""

# Clean previous builds if requested
if ($Clean) {
    Write-Host "[1/4] Cleaning previous builds..." -ForegroundColor Yellow
    if (Test-Path $DistDir) { Remove-Item -Recurse -Force $DistDir }
    if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }
} else {
    Write-Host "[1/4] Skipping clean (use -Clean to remove previous builds)" -ForegroundColor Gray
}

# Install PyInstaller using python -m pip (works reliably in venv)
Write-Host "[2/4] Installing PyInstaller..." -ForegroundColor Yellow
python -m pip install pyinstaller --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to install PyInstaller" -ForegroundColor Red
    exit 1
}

# Change to project root
Push-Location $ProjectRoot

try {
    # Build the executable
    Write-Host "[3/4] Building executable..." -ForegroundColor Yellow

    # Set PYTHONPATH to include src directory
    $env:PYTHONPATH = $SrcDir

    # Use python -m PyInstaller (works reliably in venv)
    # Use build/entry_point.py which has absolute imports
    $EntryPoint = Join-Path $PSScriptRoot "entry_point.py"

    python -m PyInstaller `
        --onefile `
        --console `
        --name "FolderMoverPro" `
        --distpath "$DistDir" `
        --workpath "$BuildDir" `
        --specpath "$BuildDir" `
        --noconfirm `
        --clean `
        --paths "$SrcDir" `
        --hidden-import "folder_mover" `
        --hidden-import "folder_mover.cli" `
        --hidden-import "folder_mover.excel" `
        --hidden-import "folder_mover.indexer" `
        --hidden-import "folder_mover.mover" `
        --hidden-import "folder_mover.report" `
        --hidden-import "folder_mover.types" `
        --hidden-import "folder_mover.utils" `
        "$EntryPoint"

    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: PyInstaller build failed" -ForegroundColor Red
        exit 1
    }

    # Verify output
    Write-Host "[4/4] Verifying build..." -ForegroundColor Yellow
    $ExePath = Join-Path $DistDir "FolderMoverPro.exe"

    if (Test-Path $ExePath) {
        $FileInfo = Get-Item $ExePath
        Write-Host ""
        Write-Host "  BUILD SUCCESSFUL" -ForegroundColor Green
        Write-Host "  Output: $ExePath" -ForegroundColor Green
        Write-Host "  Size:   $([math]::Round($FileInfo.Length / 1MB, 2)) MB" -ForegroundColor Green
        Write-Host ""

        # Quick verification
        Write-Host "  Verification:" -ForegroundColor Cyan
        & $ExePath --version
    } else {
        Write-Host "ERROR: Expected output not found at $ExePath" -ForegroundColor Red
        exit 1
    }
}
finally {
    Pop-Location
}
