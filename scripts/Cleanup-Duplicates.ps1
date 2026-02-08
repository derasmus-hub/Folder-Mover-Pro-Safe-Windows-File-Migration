<#
.SYNOPSIS
    Cleanup old quarantined duplicate folders.

.DESCRIPTION
    This script removes folders from the _DUPLICATES quarantine directory
    that are older than a specified number of days.

    SAFETY FEATURES:
    - Only operates on _DUPLICATES folder (cannot delete main destination)
    - WhatIf mode is ON by default (preview only)
    - Requires explicit -ConfirmDelete switch to enable deletion
    - Requires typing "DELETE" to confirm actual deletion
    - Shows full preview before any deletion

.PARAMETER DestRoot
    The destination root directory containing _DUPLICATES folder.
    Required.

.PARAMETER OlderThanDays
    Only delete folders older than this many days.
    Default: 30

.PARAMETER WhatIf
    Preview mode - show what would be deleted without actually deleting.
    Default: $true (always preview by default)

.PARAMETER ConfirmDelete
    Must be explicitly set to $true to enable actual deletion.
    Even with this set, user must still type "DELETE" to confirm.

.EXAMPLE
    # Preview what would be deleted (30+ days old)
    .\Cleanup-Duplicates.ps1 -DestRoot C:\Dest

.EXAMPLE
    # Preview folders older than 60 days
    .\Cleanup-Duplicates.ps1 -DestRoot C:\Dest -OlderThanDays 60

.EXAMPLE
    # Actually delete (requires typing DELETE to confirm)
    .\Cleanup-Duplicates.ps1 -DestRoot C:\Dest -OlderThanDays 30 -WhatIf:$false -ConfirmDelete

.NOTES
    Author: Folder Mover Pro
    Version: 1.0.0
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory = $true, Position = 0, HelpMessage = "Destination root containing _DUPLICATES folder")]
    [ValidateNotNullOrEmpty()]
    [string]$DestRoot,

    [Parameter(HelpMessage = "Delete folders older than this many days (default: 30)")]
    [ValidateRange(1, 3650)]
    [int]$OlderThanDays = 30,

    [Parameter(HelpMessage = "Preview mode - show what would be deleted (default: true)")]
    [switch]$WhatIf = $true,

    [Parameter(HelpMessage = "Must be set to enable actual deletion")]
    [switch]$ConfirmDelete = $false
)

$ErrorActionPreference = "Stop"

# Constants
$DUPLICATES_FOLDER = "_DUPLICATES"

# Banner
Write-Host ""
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "  Folder Mover Pro - Quarantine Cleanup" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host ""

# Validate DestRoot
if (-not (Test-Path $DestRoot -PathType Container)) {
    Write-Host "ERROR: Destination root not found: $DestRoot" -ForegroundColor Red
    exit 1
}

$DuplicatesPath = Join-Path $DestRoot $DUPLICATES_FOLDER

if (-not (Test-Path $DuplicatesPath -PathType Container)) {
    Write-Host "No quarantine folder found at: $DuplicatesPath" -ForegroundColor Yellow
    Write-Host "No duplicates have been quarantined." -ForegroundColor Yellow
    exit 0
}

Write-Host "Destination Root:    $DestRoot"
Write-Host "Quarantine Folder:   $DuplicatesPath"
Write-Host "Age Threshold:       $OlderThanDays days"
Write-Host "Mode:                $(if ($WhatIf) { 'PREVIEW (WhatIf)' } else { 'DELETE' })"
Write-Host ""

# Calculate cutoff date
$CutoffDate = (Get-Date).AddDays(-$OlderThanDays)
Write-Host "Cutoff Date:         $($CutoffDate.ToString('yyyy-MM-dd HH:mm:ss'))"
Write-Host "  (Folders last modified before this date will be selected)"
Write-Host ""

# Find folders to delete
$FoldersToDelete = @()
$TotalSize = 0

# Iterate through CaseID directories
$CaseIdDirs = Get-ChildItem -Path $DuplicatesPath -Directory -ErrorAction SilentlyContinue

foreach ($CaseIdDir in $CaseIdDirs) {
    # Iterate through folder entries within each CaseID
    $FolderEntries = Get-ChildItem -Path $CaseIdDir.FullName -Directory -ErrorAction SilentlyContinue

    foreach ($Folder in $FolderEntries) {
        $LastModified = $Folder.LastWriteTime
        $AgeDays = ((Get-Date) - $LastModified).Days

        if ($LastModified -lt $CutoffDate) {
            # Calculate folder size
            $FolderSize = (Get-ChildItem -Path $Folder.FullName -Recurse -File -ErrorAction SilentlyContinue |
                          Measure-Object -Property Length -Sum).Sum
            if ($null -eq $FolderSize) { $FolderSize = 0 }

            $FoldersToDelete += [PSCustomObject]@{
                CaseId       = $CaseIdDir.Name
                FolderName   = $Folder.Name
                FullPath     = $Folder.FullName
                LastModified = $LastModified
                AgeDays      = $AgeDays
                SizeBytes    = $FolderSize
            }

            $TotalSize += $FolderSize
        }
    }
}

# Display results
if ($FoldersToDelete.Count -eq 0) {
    Write-Host "No folders found older than $OlderThanDays days." -ForegroundColor Green
    Write-Host ""
    exit 0
}

Write-Host "================================================================================" -ForegroundColor Yellow
Write-Host "  FOLDERS TO BE DELETED" -ForegroundColor Yellow
Write-Host "================================================================================" -ForegroundColor Yellow
Write-Host ""

# Sort by age (oldest first) and display
$FoldersToDelete | Sort-Object -Property AgeDays -Descending | ForEach-Object {
    $SizeMB = [math]::Round($_.SizeBytes / 1MB, 2)
    Write-Host "  CaseID:        $($_.CaseId)" -ForegroundColor White
    Write-Host "  Folder:        $($_.FolderName)"
    Write-Host "  Age:           $($_.AgeDays) days"
    Write-Host "  Last Modified: $($_.LastModified.ToString('yyyy-MM-dd HH:mm:ss'))"
    Write-Host "  Size:          $SizeMB MB"
    Write-Host "  Path:          $($_.FullPath)" -ForegroundColor DarkGray
    Write-Host ""
}

# Summary
$TotalSizeMB = [math]::Round($TotalSize / 1MB, 2)
$TotalSizeGB = [math]::Round($TotalSize / 1GB, 2)
$UniqueCaseIds = ($FoldersToDelete | Select-Object -Property CaseId -Unique).Count

Write-Host "================================================================================" -ForegroundColor Yellow
Write-Host "  SUMMARY" -ForegroundColor Yellow
Write-Host "================================================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Total folders to delete:  $($FoldersToDelete.Count)"
Write-Host "  Unique CaseIDs affected:  $UniqueCaseIds"
Write-Host "  Total size:               $TotalSizeMB MB ($TotalSizeGB GB)"
Write-Host ""

# WhatIf mode - just preview
if ($WhatIf) {
    Write-Host "================================================================================" -ForegroundColor Cyan
    Write-Host "  PREVIEW MODE - NO CHANGES MADE" -ForegroundColor Cyan
    Write-Host "================================================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "To actually delete these folders, run with:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  .\Cleanup-Duplicates.ps1 -DestRoot `"$DestRoot`" -OlderThanDays $OlderThanDays -WhatIf:`$false -ConfirmDelete" -ForegroundColor White
    Write-Host ""
    exit 0
}

# Deletion mode - require ConfirmDelete switch
if (-not $ConfirmDelete) {
    Write-Host "================================================================================" -ForegroundColor Red
    Write-Host "  DELETION NOT ENABLED" -ForegroundColor Red
    Write-Host "================================================================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "The -ConfirmDelete switch must be set to enable deletion." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To actually delete these folders, run with:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  .\Cleanup-Duplicates.ps1 -DestRoot `"$DestRoot`" -OlderThanDays $OlderThanDays -WhatIf:`$false -ConfirmDelete" -ForegroundColor White
    Write-Host ""
    exit 0
}

# Final confirmation - require typing DELETE
Write-Host "================================================================================" -ForegroundColor Red
Write-Host "  WARNING: PERMANENT DELETION" -ForegroundColor Red
Write-Host "================================================================================" -ForegroundColor Red
Write-Host ""
Write-Host "You are about to PERMANENTLY DELETE $($FoldersToDelete.Count) folder(s)." -ForegroundColor Red
Write-Host "This action CANNOT be undone." -ForegroundColor Red
Write-Host ""
Write-Host "To confirm deletion, type DELETE (all caps) and press Enter:" -ForegroundColor Yellow
Write-Host ""

$Confirmation = Read-Host "Confirmation"

if ($Confirmation -ne "DELETE") {
    Write-Host ""
    Write-Host "Confirmation failed. No folders were deleted." -ForegroundColor Yellow
    Write-Host "You entered: '$Confirmation' (expected: 'DELETE')" -ForegroundColor DarkGray
    Write-Host ""
    exit 0
}

# Perform deletion
Write-Host ""
Write-Host "================================================================================" -ForegroundColor Green
Write-Host "  DELETING FOLDERS" -ForegroundColor Green
Write-Host "================================================================================" -ForegroundColor Green
Write-Host ""

$DeletedCount = 0
$ErrorCount = 0
$DeletedSize = 0

foreach ($Folder in $FoldersToDelete) {
    Write-Host "Deleting: $($Folder.FullPath)..." -NoNewline

    try {
        Remove-Item -Path $Folder.FullPath -Recurse -Force -ErrorAction Stop
        Write-Host " OK" -ForegroundColor Green
        $DeletedCount++
        $DeletedSize += $Folder.SizeBytes
    }
    catch {
        Write-Host " FAILED" -ForegroundColor Red
        Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
        $ErrorCount++
    }
}

# Cleanup empty CaseID directories
Write-Host ""
Write-Host "Cleaning up empty CaseID directories..." -ForegroundColor DarkGray

$CaseIdDirs = Get-ChildItem -Path $DuplicatesPath -Directory -ErrorAction SilentlyContinue
foreach ($CaseIdDir in $CaseIdDirs) {
    $ChildCount = (Get-ChildItem -Path $CaseIdDir.FullName -ErrorAction SilentlyContinue).Count
    if ($ChildCount -eq 0) {
        try {
            Remove-Item -Path $CaseIdDir.FullName -Force -ErrorAction Stop
            Write-Host "  Removed empty: $($CaseIdDir.Name)" -ForegroundColor DarkGray
        }
        catch {
            # Ignore errors on cleanup
        }
    }
}

# Check if _DUPLICATES folder is now empty
$RemainingCount = (Get-ChildItem -Path $DuplicatesPath -ErrorAction SilentlyContinue).Count
if ($RemainingCount -eq 0) {
    try {
        Remove-Item -Path $DuplicatesPath -Force -ErrorAction Stop
        Write-Host "  Removed empty: $DUPLICATES_FOLDER" -ForegroundColor DarkGray
    }
    catch {
        # Ignore errors on cleanup
    }
}

# Final summary
$DeletedSizeMB = [math]::Round($DeletedSize / 1MB, 2)
Write-Host ""
Write-Host "================================================================================" -ForegroundColor Green
Write-Host "  CLEANUP COMPLETE" -ForegroundColor Green
Write-Host "================================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Folders deleted:  $DeletedCount"
Write-Host "  Space freed:      $DeletedSizeMB MB"
if ($ErrorCount -gt 0) {
    Write-Host "  Errors:           $ErrorCount" -ForegroundColor Red
}
Write-Host ""

if ($ErrorCount -gt 0) {
    exit 2
}
exit 0
