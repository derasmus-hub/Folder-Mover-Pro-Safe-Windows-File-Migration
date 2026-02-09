# build_exe.ps1
# Builds Folder Mover Pro as Windows executables
# Requires: Python 3.8+ installed and in PATH
#
# By default, builds BOTH:
#   - FolderMoverPro.exe     (GUI, windowed, double-click friendly)
#   - FolderMoverPro-CLI.exe (CLI, console, for command-line use)
#
# Both executables embed:
#   - Application icon (logo\ErasmusLabs.ico)
#   - Windows version metadata (CompanyName, ProductName, etc.)
#
# Use -GuiOnly or -CliOnly to build just one.

param(
    [switch]$Clean,
    [switch]$GuiOnly,
    [switch]$CliOnly
)

$ErrorActionPreference = "Stop"

# Get project root (parent of build directory)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DistDir = Join-Path $ProjectRoot "dist"
$BuildDir = Join-Path $ProjectRoot "build\pyinstaller"
$SrcDir = Join-Path $ProjectRoot "src"
$IconPath = Join-Path $ProjectRoot "logo\ErasmusLabs.ico"

# Determine what to build
$BuildGui = -not $CliOnly
$BuildCli = -not $GuiOnly

if ($GuiOnly -and $CliOnly) {
    Write-Host "ERROR: Cannot specify both -GuiOnly and -CliOnly" -ForegroundColor Red
    exit 1
}

$BuildTypes = @()
if ($BuildGui) { $BuildTypes += "GUI" }
if ($BuildCli) { $BuildTypes += "CLI" }

Write-Host ""
Write-Host "  Folder Mover Pro - Build Script" -ForegroundColor Cyan
Write-Host "  ================================" -ForegroundColor Cyan
Write-Host "  Building: $($BuildTypes -join ', ')" -ForegroundColor Cyan
Write-Host ""

# Clean previous builds if requested
if ($Clean) {
    Write-Host "[1/5] Cleaning previous builds..." -ForegroundColor Yellow
    if (Test-Path $DistDir) { Remove-Item -Recurse -Force $DistDir }
    if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }
} else {
    Write-Host "[1/5] Skipping clean (use -Clean to remove previous builds)" -ForegroundColor Gray
}

# Install PyInstaller using python -m pip (works reliably in venv)
Write-Host "[2/5] Installing PyInstaller..." -ForegroundColor Yellow
python -m pip install pyinstaller --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to install PyInstaller" -ForegroundColor Red
    exit 1
}

# Generate ICO if missing
Write-Host "[3/5] Checking icon..." -ForegroundColor Yellow
if (-not (Test-Path $IconPath)) {
    Write-Host "  ICO not found, generating..." -ForegroundColor Yellow
    $MakeIconScript = Join-Path $ProjectRoot "scripts\Make-Icon.ps1"
    if (Test-Path $MakeIconScript) {
        & $MakeIconScript
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: Icon generation failed" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "WARNING: Make-Icon.ps1 not found and ICO missing. Building without icon." -ForegroundColor Yellow
        $IconPath = $null
    }
} else {
    Write-Host "  ICO found: $IconPath" -ForegroundColor DarkGray
}

# Generate Windows version info files
Write-Host "[4/5] Generating version info..." -ForegroundColor Yellow
$VersionInfoScript = Join-Path $PSScriptRoot "make_version_info.py"
python $VersionInfoScript
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Version info generation failed" -ForegroundColor Red
    exit 1
}

$VersionInfoGui = Join-Path $PSScriptRoot "version_info_gui.txt"
$VersionInfoCli = Join-Path $PSScriptRoot "version_info_cli.txt"

# Change to project root
Push-Location $ProjectRoot

function Build-Executable {
    param(
        [string]$Type,
        [string]$ExeName,
        [string]$EntryPointName,
        [string]$ConsoleFlag,
        [string]$VersionInfoFile,
        [string[]]$ExtraImports
    )

    Write-Host ""
    Write-Host "  Building $Type executable..." -ForegroundColor Yellow

    # Set PYTHONPATH to include src directory
    $env:PYTHONPATH = $SrcDir

    $EntryPoint = Join-Path $PSScriptRoot $EntryPointName

    $PyInstallerArgs = @(
        "--onefile",
        $ConsoleFlag,
        "--name", $ExeName,
        "--distpath", $DistDir,
        "--workpath", $BuildDir,
        "--specpath", $BuildDir,
        "--noconfirm",
        "--clean",
        "--paths", $SrcDir,
        "--hidden-import", "folder_mover",
        "--hidden-import", "folder_mover.cli",
        "--hidden-import", "folder_mover.excel",
        "--hidden-import", "folder_mover.indexer",
        "--hidden-import", "folder_mover.mover",
        "--hidden-import", "folder_mover.report",
        "--hidden-import", "folder_mover.types",
        "--hidden-import", "folder_mover.utils"
    )

    # Add icon if available
    if ($IconPath -and (Test-Path $IconPath)) {
        $PyInstallerArgs += "--icon"
        $PyInstallerArgs += $IconPath
    }

    # Add version info if available
    if ($VersionInfoFile -and (Test-Path $VersionInfoFile)) {
        $PyInstallerArgs += "--version-file"
        $PyInstallerArgs += $VersionInfoFile
    }

    foreach ($import in $ExtraImports) {
        $PyInstallerArgs += "--hidden-import"
        $PyInstallerArgs += $import
    }

    $PyInstallerArgs += $EntryPoint

    python -m PyInstaller @PyInstallerArgs

    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: PyInstaller build failed for $Type" -ForegroundColor Red
        return $false
    }

    $ExePath = Join-Path $DistDir "$ExeName.exe"
    if (Test-Path $ExePath) {
        $FileInfo = Get-Item $ExePath
        Write-Host "  $Type build successful: $ExePath ($([math]::Round($FileInfo.Length / 1MB, 2)) MB)" -ForegroundColor Green
        return $true
    } else {
        Write-Host "ERROR: Expected output not found at $ExePath" -ForegroundColor Red
        return $false
    }
}

try {
    Write-Host "[5/5] Building executables..." -ForegroundColor Yellow

    $Success = $true

    # Build GUI executable (windowed, no console)
    if ($BuildGui) {
        $result = Build-Executable `
            -Type "GUI" `
            -ExeName "FolderMoverPro" `
            -EntryPointName "entry_point_gui.py" `
            -ConsoleFlag "--noconsole" `
            -VersionInfoFile $VersionInfoGui `
            -ExtraImports @("folder_mover.gui", "folder_mover.gui_app")
        if (-not $result) { $Success = $false }
    }

    # Build CLI executable (console)
    if ($BuildCli) {
        $result = Build-Executable `
            -Type "CLI" `
            -ExeName "FolderMoverPro-CLI" `
            -EntryPointName "entry_point.py" `
            -ConsoleFlag "--console" `
            -VersionInfoFile $VersionInfoCli `
            -ExtraImports @()
        if (-not $result) { $Success = $false }
    }

    if (-not $Success) {
        Write-Host ""
        Write-Host "ERROR: One or more builds failed" -ForegroundColor Red
        exit 1
    }

    # Verify outputs
    Write-Host ""
    Write-Host "  Verifying builds..." -ForegroundColor Yellow

    if ($BuildCli) {
        $CliExe = Join-Path $DistDir "FolderMoverPro-CLI.exe"
        if (Test-Path $CliExe) {
            Write-Host "  CLI version check:" -ForegroundColor Cyan
            & $CliExe --version
        }
    }

    if ($BuildGui) {
        $GuiExe = Join-Path $DistDir "FolderMoverPro.exe"
        if (Test-Path $GuiExe) {
            Write-Host "  GUI exe exists (windowed - no console verification)" -ForegroundColor DarkGray
        }
    }

    Write-Host ""
    Write-Host "  BUILD COMPLETE" -ForegroundColor Green
    Write-Host "  Output directory: $DistDir" -ForegroundColor Green
    Write-Host ""

    if ($BuildGui) {
        Write-Host "  FolderMoverPro.exe     - Double-click to launch GUI (with icon + version metadata)" -ForegroundColor White
    }
    if ($BuildCli) {
        Write-Host "  FolderMoverPro-CLI.exe - Command-line interface (with icon + version metadata)" -ForegroundColor White
    }
    Write-Host ""
}
finally {
    Pop-Location
}
