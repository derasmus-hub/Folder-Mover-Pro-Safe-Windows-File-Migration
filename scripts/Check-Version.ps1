<#
.SYNOPSIS
    Check version consistency across all sources.

.DESCRIPTION
    Verifies that pyproject.toml, Python source, and exe all report
    the same version. Also checks that the application icon exists.
    Exits non-zero if any mismatch is detected.

.EXAMPLE
    .\Check-Version.ps1

.NOTES
    Author: Erasmus Labs
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

# Get project root (parent of scripts directory)
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "  Version Consistency Check" -ForegroundColor Cyan
Write-Host "  =========================" -ForegroundColor Cyan
Write-Host ""

$Versions = @{}
$Errors = @()

# 1. Extract version from pyproject.toml
$PyProjectPath = Join-Path $ProjectRoot "pyproject.toml"
if (Test-Path $PyProjectPath) {
    $PyProjectContent = Get-Content $PyProjectPath -Raw
    if ($PyProjectContent -match 'version\s*=\s*"([^"]+)"') {
        $Versions["pyproject.toml"] = $Matches[1]
        Write-Host "  pyproject.toml:  $($Versions["pyproject.toml"])" -ForegroundColor White
    } else {
        $Errors += "Could not extract version from pyproject.toml"
        Write-Host "  pyproject.toml:  ERROR - could not extract" -ForegroundColor Red
    }
} else {
    $Errors += "pyproject.toml not found"
    Write-Host "  pyproject.toml:  ERROR - file not found" -ForegroundColor Red
}

# 2. Get version from Python source
$SrcDir = Join-Path $ProjectRoot "src"
try {
    $PythonVersion = python -c "import sys; sys.path.insert(0, '$($SrcDir.Replace('\', '\\'))'); from folder_mover import __version__; print(__version__)" 2>&1
    if ($LASTEXITCODE -eq 0) {
        $Versions["python src"] = $PythonVersion.Trim()
        Write-Host "  python src:      $($Versions["python src"])" -ForegroundColor White
    } else {
        $Errors += "Python import failed: $PythonVersion"
        Write-Host "  python src:      ERROR - import failed" -ForegroundColor Red
    }
} catch {
    $Errors += "Python not available: $_"
    Write-Host "  python src:      ERROR - python not available" -ForegroundColor Red
}

# 3. Get version from CLI exe (can verify via --version)
$CliExePath = Join-Path $ProjectRoot "dist\FolderMoverPro-CLI.exe"
if (Test-Path $CliExePath) {
    try {
        $ExeVersion = (& $CliExePath --version 2>&1) | Out-String
        $ExeVersion = $ExeVersion.Trim()
        if ($LASTEXITCODE -eq 0 -and $ExeVersion) {
            $Versions["cli exe"] = $ExeVersion
            Write-Host "  cli exe:         $($Versions["cli exe"])" -ForegroundColor White
        } else {
            $Errors += "CLI exe returned error or empty version"
            Write-Host "  cli exe:         ERROR - returned error" -ForegroundColor Red
        }
    } catch {
        $Errors += "CLI exe execution failed: $_"
        Write-Host "  cli exe:         ERROR - execution failed" -ForegroundColor Red
    }
} else {
    Write-Host "  cli exe:         (not built)" -ForegroundColor DarkGray
}

# 4. Check GUI exe exists (windowed - cannot verify version via CLI)
$GuiExePath = Join-Path $ProjectRoot "dist\FolderMoverPro.exe"
if (Test-Path $GuiExePath) {
    $GuiFileInfo = Get-Item $GuiExePath
    Write-Host "  gui exe:         (exists, $([math]::Round($GuiFileInfo.Length / 1MB, 2)) MB)" -ForegroundColor DarkGray
} else {
    Write-Host "  gui exe:         (not built)" -ForegroundColor DarkGray
}

Write-Host ""

# 5. Check application icon
Write-Host "  Asset Checks" -ForegroundColor Cyan
Write-Host "  -------------" -ForegroundColor Cyan
$IcoPath = Join-Path $ProjectRoot "logo\ErasmusLabs.ico"
if (Test-Path $IcoPath) {
    $IcoInfo = Get-Item $IcoPath
    Write-Host "  icon (ICO):      OK ($([math]::Round($IcoInfo.Length / 1KB, 1)) KB)" -ForegroundColor Green
} else {
    Write-Host "  icon (ICO):      MISSING - run scripts\Make-Icon.ps1" -ForegroundColor Yellow
}

$PngPath = Join-Path $ProjectRoot "logo\1.png"
if (Test-Path $PngPath) {
    Write-Host "  logo (PNG):      OK (logo\1.png)" -ForegroundColor Green
} else {
    $Errors += "Source logo PNG not found (logo\1.png)"
    Write-Host "  logo (PNG):      MISSING (logo\1.png)" -ForegroundColor Red
}

Write-Host ""

# Check for mismatches
$UniqueVersions = $Versions.Values | Sort-Object -Unique
$HasMismatch = $false

if ($Versions.Count -gt 1 -and $UniqueVersions.Count -gt 1) {
    $HasMismatch = $true
    Write-Host "  STATUS: VERSION MISMATCH DETECTED" -ForegroundColor Red
    Write-Host ""
    Write-Host "  The following versions were found:" -ForegroundColor Yellow
    foreach ($Source in $Versions.Keys) {
        Write-Host "    $Source = $($Versions[$Source])"
    }
    Write-Host ""
    Write-Host "  All versions must match pyproject.toml" -ForegroundColor Yellow
} elseif ($Errors.Count -gt 0) {
    Write-Host "  STATUS: ERRORS OCCURRED" -ForegroundColor Red
    foreach ($Err in $Errors) {
        Write-Host "    - $Err" -ForegroundColor Red
    }
} else {
    Write-Host "  STATUS: OK - All versions match" -ForegroundColor Green
}

Write-Host ""

if ($HasMismatch -or $Errors.Count -gt 0) {
    exit 1
}
exit 0
