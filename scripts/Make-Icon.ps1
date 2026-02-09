<#
.SYNOPSIS
    Convert the project logo PNG to a Windows ICO file.

.DESCRIPTION
    Converts logo\ErasmusLabs_Logo_Reversed.png into logo\ErasmusLabs.ico
    containing standard icon sizes: 16, 24, 32, 48, 64, 128, 256 px.

    Tries ImageMagick first (magick convert). If not available, falls back
    to Python Pillow (pip install Pillow).

    This script is deterministic and re-runnable.

.EXAMPLE
    .\scripts\Make-Icon.ps1

.EXAMPLE
    .\scripts\Make-Icon.ps1 -Force

.NOTES
    Author: Erasmus Labs
#>

[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# Get project root (parent of scripts directory)
$ProjectRoot = Split-Path -Parent $PSScriptRoot

$SourcePng = Join-Path $ProjectRoot "logo\ErasmusLabs_Logo_Reversed.png"
$OutputIco = Join-Path $ProjectRoot "logo\ErasmusLabs.ico"

$Sizes = @(16, 24, 32, 48, 64, 128, 256)
$SizesStr = ($Sizes | ForEach-Object { "${_}x${_}" }) -join ", "

Write-Host ""
Write-Host "  Make-Icon: PNG to ICO Converter" -ForegroundColor Cyan
Write-Host "  ================================" -ForegroundColor Cyan
Write-Host "  Source:  $SourcePng"
Write-Host "  Output:  $OutputIco"
Write-Host "  Sizes:   $SizesStr"
Write-Host ""

# Verify source exists
if (-not (Test-Path $SourcePng)) {
    Write-Host "ERROR: Source PNG not found: $SourcePng" -ForegroundColor Red
    exit 1
}

# Skip if output already exists (unless -Force)
if ((Test-Path $OutputIco) -and -not $Force) {
    Write-Host "  ICO already exists. Use -Force to regenerate." -ForegroundColor DarkGray
    Write-Host "  $OutputIco" -ForegroundColor DarkGray
    Write-Host ""
    exit 0
}

# --- Strategy 1: ImageMagick ---
$UsedTool = $null

$MagickCmd = Get-Command "magick" -ErrorAction SilentlyContinue
if ($MagickCmd) {
    Write-Host "  Using ImageMagick..." -ForegroundColor Yellow

    # Build resize arguments for each size
    $MagickArgs = @($SourcePng)
    foreach ($sz in $Sizes) {
        $MagickArgs += "-resize"
        $MagickArgs += "${sz}x${sz}"
        $MagickArgs += "-write"
        $MagickArgs += (Join-Path $ProjectRoot "logo\icon_${sz}.png")
    }
    # Remove last -write and replace with actual conversion
    # Simpler approach: use magick to create ICO directly
    $SizeArgs = ($Sizes | ForEach-Object { "${_}x${_}" }) -join ","

    # ImageMagick can create multi-size ICO directly
    $TempFiles = @()
    foreach ($sz in $Sizes) {
        $TempFile = Join-Path $ProjectRoot "logo\icon_temp_${sz}.png"
        & magick $SourcePng -resize "${sz}x${sz}" -background none -gravity center -extent "${sz}x${sz}" $TempFile
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: ImageMagick resize failed for ${sz}x${sz}" -ForegroundColor Red
            # Clean up temp files
            foreach ($tf in $TempFiles) { Remove-Item -Force $tf -ErrorAction SilentlyContinue }
            break
        }
        $TempFiles += $TempFile
    }

    if ($TempFiles.Count -eq $Sizes.Count) {
        & magick @TempFiles $OutputIco
        if ($LASTEXITCODE -eq 0) {
            $UsedTool = "ImageMagick"
        } else {
            Write-Host "  ImageMagick ICO creation failed, trying Pillow..." -ForegroundColor Yellow
        }
        # Clean up temp files
        foreach ($tf in $TempFiles) { Remove-Item -Force $tf -ErrorAction SilentlyContinue }
    }
}

# --- Strategy 2: Python Pillow ---
if (-not $UsedTool) {
    Write-Host "  Using Python Pillow..." -ForegroundColor Yellow

    # Check if Pillow is installed
    $PillowCheck = python -c "import PIL; print(PIL.__version__)" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Installing Pillow..." -ForegroundColor Yellow
        python -m pip install Pillow --quiet
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: Failed to install Pillow" -ForegroundColor Red
            exit 1
        }
    }

    $PythonScript = @"
import sys
from PIL import Image

source = sys.argv[1]
output = sys.argv[2]
sizes = [16, 24, 32, 48, 64, 128, 256]

img = Image.open(source)

# Convert to RGBA if not already
if img.mode != 'RGBA':
    img = img.convert('RGBA')

# Create resized versions
icon_images = []
for sz in sizes:
    resized = img.copy()
    resized.thumbnail((sz, sz), Image.LANCZOS)
    # Create exact-size canvas with transparency
    canvas = Image.new('RGBA', (sz, sz), (0, 0, 0, 0))
    # Center the resized image
    offset_x = (sz - resized.width) // 2
    offset_y = (sz - resized.height) // 2
    canvas.paste(resized, (offset_x, offset_y))
    icon_images.append(canvas)

# Save as ICO with all sizes
icon_images[0].save(
    output,
    format='ICO',
    sizes=[(sz, sz) for sz in sizes],
    append_images=icon_images[1:]
)

print(f"Created ICO with {len(sizes)} sizes: {', '.join(f'{s}x{s}' for s in sizes)}")
"@

    $PythonScript | python - $SourcePng $OutputIco
    if ($LASTEXITCODE -eq 0) {
        $UsedTool = "Pillow"
    } else {
        Write-Host "ERROR: Pillow ICO creation failed" -ForegroundColor Red
        exit 1
    }
}

# Verify output
if (Test-Path $OutputIco) {
    $FileInfo = Get-Item $OutputIco
    Write-Host ""
    Write-Host "  ICO created successfully ($UsedTool)" -ForegroundColor Green
    Write-Host "  Path: $OutputIco" -ForegroundColor Green
    Write-Host "  Size: $([math]::Round($FileInfo.Length / 1KB, 1)) KB" -ForegroundColor Green
    Write-Host ""
} else {
    Write-Host "ERROR: Output ICO not found after generation" -ForegroundColor Red
    exit 1
}
