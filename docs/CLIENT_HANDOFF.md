# Client Handoff Guide

This document provides the recommended test protocol, report interpretation guide, and instructions for safe rerunning after interruptions.

## Table of Contents

1. [Recommended Test Protocol](#recommended-test-protocol)
2. [Understanding Report Statuses](#understanding-report-statuses)
3. [Resuming After Interruption](#resuming-after-interruption)
4. [Common Scenarios](#common-scenarios)
5. [Checklist Before Production Run](#checklist-before-production-run)

---

## Recommended Test Protocol

Follow this 4-step protocol before running on production data:

### Step 1: Dry Run (Preview Only)

**Purpose:** See what WOULD happen without making any changes.

```powershell
python -m folder_mover caselist.xlsx C:\Source C:\Dest --dry-run --report dryrun_report.csv -v
```

**Review the report for:**
- ✅ `FOUND_DRYRUN` - Folders that would be moved
- ⚠️ `NOT_FOUND` - CaseIDs with no matching folders (expected or data issue?)
- ⚠️ `FOUND_DRYRUN_RENAMED` - Folders that would be renamed due to collision

**Expected outcome:** No files moved, report generated showing planned actions.

### Step 2: Single Folder Test

**Purpose:** Verify the move mechanism works correctly with ONE folder.

```powershell
python -m folder_mover caselist.xlsx C:\Source C:\Dest --max-moves 1 --report move1_report.csv -v
```

**Verify:**
- ✅ One folder was moved to destination
- ✅ Source folder no longer exists
- ✅ All contents transferred correctly
- ✅ Report shows `MOVED` status

### Step 3: Small Batch Test

**Purpose:** Test with a larger sample before full migration.

```powershell
# Move 10 folders
python -m folder_mover caselist.xlsx C:\Source C:\Dest --max-moves 10 --report move10_report.csv -v

# Or limit by CaseIDs
python -m folder_mover caselist.xlsx C:\Source C:\Dest --caseid-limit 10 --report subset_report.csv -v
```

**Verify:**
- ✅ All moves completed as expected
- ✅ Name collisions handled correctly (`_1`, `_2` suffixes)
- ✅ No permission errors

### Step 4: Full Migration

**Purpose:** Complete the migration with all safety features.

```powershell
python -m folder_mover caselist.xlsx C:\Source C:\Dest --report full_migration.csv -v
```

**Post-migration:**
- Review the report for any `ERROR` entries
- Verify destination folder count matches expectations
- Keep the report for audit purposes

---

## Understanding Report Statuses

The CSV report contains a `status` column with the following values:

### Success Statuses

| Status | Meaning | Action Required |
|--------|---------|-----------------|
| `MOVED` | Folder successfully moved | None |
| `MOVED_RENAMED` | Moved with `_1`, `_2` suffix due to name collision | Verify this was expected |

### Dry Run Statuses

| Status | Meaning | Action Required |
|--------|---------|-----------------|
| `FOUND_DRYRUN` | Would be moved (dry run) | Review before live run |
| `FOUND_DRYRUN_RENAMED` | Would be moved with rename | Check for naming conflicts |

### Skip Statuses

| Status | Meaning | Action Required |
|--------|---------|-----------------|
| `NOT_FOUND` | No folders matched this CaseID | Verify CaseID is correct |
| `SKIPPED_MISSING` | Source folder no longer exists | Already moved or deleted |
| `SKIPPED_EXISTS` | Destination already exists | May already be migrated |
| `SKIPPED_EXCLUDED` | Matched exclusion pattern | Expected if using `--exclude-pattern` |
| `SKIPPED_RESUME` | Already processed in previous run | Expected when using `--resume-from-report` |
| `SKIPPED_DUPLICATE` | Duplicate CaseID skipped | Expected when using `--duplicates-action skip` |
| `MULTIPLE_MATCHES` | CaseID matched multiple folders | Legacy status for `--duplicates-action move-all` |

### Quarantine Statuses (for duplicate handling)

| Status | Meaning | Action Required |
|--------|---------|-----------------|
| `QUARANTINED` | Moved to `_DUPLICATES/<CaseID>/` folder | Review quarantine folder |
| `QUARANTINED_RENAMED` | Quarantined with rename | Check for same-name duplicates |
| `FOUND_DRYRUN_QUARANTINE` | Would quarantine (dry run) | Review before live run |

### Error Status

| Status | Meaning | Action Required |
|--------|---------|-----------------|
| `ERROR` | Operation failed | Check `message` column for details |

### Common Error Messages

| Message | Cause | Solution |
|---------|-------|----------|
| `PermissionError: Access denied` | File is locked or no permissions | Close applications using the folder, check permissions |
| `Cannot create destination directory` | No write access to destination | Check destination folder permissions |
| `Source path is not a directory` | Matched item is a file, not folder | Review matching logic |

---

## Resuming After Interruption

If a migration is interrupted (network issue, system restart, etc.), you can safely resume:

### Using the Resume Feature

```powershell
# Continue from where you left off
python -m folder_mover caselist.xlsx C:\Source C:\Dest --resume-from-report previous_report.csv --report resume_report.csv -v
```

**How it works:**
1. The tool reads the previous report
2. Any folder with status `MOVED` or `MOVED_RENAMED` is skipped
3. Only unprocessed folders are attempted

### Manual Verification

Before resuming, you can check the previous report:

```powershell
# Count successful moves
Import-Csv previous_report.csv | Where-Object { $_.status -eq "MOVED" -or $_.status -eq "MOVED_RENAMED" } | Measure-Object

# List failed entries
Import-Csv previous_report.csv | Where-Object { $_.status -eq "ERROR" } | Format-Table
```

### Combining Reports

After resuming, you'll have two reports. To combine them:

```powershell
# Combine reports (skip header from second file)
Get-Content first_report.csv | Out-File combined_report.csv
Get-Content resume_report.csv | Select-Object -Skip 1 | Out-File combined_report.csv -Append
```

---

## Common Scenarios

### Scenario 1: CaseID Matches Multiple Folders (Duplicates)

**Situation:** CaseID `00123` matches both `Case_00123_2023` and `Case_00123_2024`.

**Default Behavior (`--duplicates-action quarantine`):**
Both folders are moved to a quarantine folder for manual review.

```powershell
python -m folder_mover cases.xlsx C:\Source C:\Dest --report out.csv
```

**Example output:**
```csv
case_id,status,source_path,dest_path,message
00123,QUARANTINED,C:\Source\Case_00123_2023,C:\Dest\_DUPLICATES\00123\Case_00123_2023,Quarantined duplicate
00123,QUARANTINED,C:\Source\Case_00123_2024,C:\Dest\_DUPLICATES\00123\Case_00123_2024,Quarantined duplicate
```

**Result folder structure:**
```
C:\Dest\
└── _DUPLICATES\
    └── 00123\
        ├── Case_00123_2023\
        └── Case_00123_2024\
```

**Alternative: Skip duplicates entirely:**
```powershell
python -m folder_mover cases.xlsx C:\Source C:\Dest --duplicates-action skip
```

**Alternative: Move all to main dest (legacy behavior):**
```powershell
python -m folder_mover cases.xlsx C:\Source C:\Dest --duplicates-action move-all
```

### Scenario 2: Destination Already Has a Folder with Same Name

**Situation:** `C:\Dest\Case_00123` already exists.

**With `--on-dest-exists rename` (default):**
- New folder becomes `Case_00123_1`
- Status: `MOVED_RENAMED`

**With `--on-dest-exists skip`:**
- Folder is not moved
- Status: `SKIPPED_EXISTS`

### Scenario 3: Excluding Temporary Folders

**Situation:** You want to skip folders matching certain patterns.

```powershell
python -m folder_mover caselist.xlsx C:\Source C:\Dest `
    --exclude-pattern "*.tmp" `
    --exclude-pattern "*_backup" `
    --exclude-pattern "Archive_*" `
    --dry-run
```

**Result:** Matching folders show `SKIPPED_EXCLUDED` in report.

### Scenario 4: Long File Paths (>260 characters)

**Situation:** Windows path limit errors.

**Solution:** The tool automatically handles long paths using the `\\?\` prefix on Windows. No action required.

If you still encounter issues:
1. Enable long paths in Windows (requires admin):
   ```powershell
   Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1
   ```
2. Restart the system

### Scenario 5: Reviewing Quarantined Duplicates

**Situation:** After migration, you need to review and process quarantined duplicates.

**Step 1: List quarantined duplicates with age information:**
```powershell
python -m folder_mover --list-duplicates C:\Dest
```

**Example output:**
```
Quarantined Duplicates Report
=============================
Destination: C:\Dest

CaseID      Folder Name         Age (days)  Last Modified
-----------------------------------------------------------------
00123       Case_00123_A              45    2024-11-25 14:30:00
00123       Case_00123_B              45    2024-11-25 14:32:00
00456       Case_00456_2023           30    2024-12-10 09:15:00
00456       Case_00456_2024           30    2024-12-10 09:16:00

Total: 4 quarantined folders from 2 CaseIDs
```

**Step 2: Export to CSV for detailed analysis:**
```powershell
python -m folder_mover --list-duplicates C:\Dest --report duplicates_review.csv
```

**Step 3: Manual resolution:**
- Review each CaseID's duplicates
- Keep the correct folder (move to main destination)
- Delete or archive the duplicates
- The `_DUPLICATES` folder can be deleted when empty

**Step 4: Automated cleanup (after 30+ days):**
```powershell
# Preview what would be deleted (safe - no changes)
.\scripts\Cleanup-Duplicates.ps1 -DestRoot C:\Dest

# Actually delete old duplicates (requires typing DELETE)
.\scripts\Cleanup-Duplicates.ps1 -DestRoot C:\Dest -WhatIf:$false -ConfirmDelete
```

See [RUNBOOK.md](../RUNBOOK.md#quarantine-cleanup) for full cleanup documentation.

---

## Checklist Before Production Run

Use this checklist before running on production data:

### Pre-Migration

- [ ] **Backup verified** - Confirm backup exists for source data
- [ ] **Dry run completed** - Reviewed dry run report, all expected
- [ ] **Single folder test** - One folder moved and verified
- [ ] **Small batch test** - 10+ folders moved successfully
- [ ] **Exclusions configured** - Added patterns for temp/backup folders
- [ ] **Permissions checked** - Tool can read source and write to dest
- [ ] **Disk space verified** - Destination has sufficient space
- [ ] **Users notified** - Users know not to access folders during migration

### During Migration

- [ ] **Report path set** - Using `--report` to capture all actions
- [ ] **Verbosity enabled** - Using `-v` for logging
- [ ] **Monitor progress** - Watch for errors in real-time

### Post-Migration

- [ ] **Report reviewed** - All entries checked for errors
- [ ] **Destination verified** - Folder count matches expectations
- [ ] **NOT_FOUND reviewed** - Understood why some CaseIDs had no matches
- [ ] **Duplicates reviewed** - Used `--list-duplicates` to check quarantine folder
- [ ] **Report archived** - Saved for audit trail

---

## Quick Reference

### Essential Commands

```powershell
# Dry run
python -m folder_mover data.xlsx Source Dest --dry-run --report dryrun.csv

# Safe first test
python -m folder_mover data.xlsx Source Dest --max-moves 1 --report test.csv

# With exclusions
python -m folder_mover data.xlsx Source Dest --exclude-pattern "*.tmp" --report out.csv

# Skip existing destinations
python -m folder_mover data.xlsx Source Dest --on-dest-exists skip --report out.csv

# Resume after interruption
python -m folder_mover data.xlsx Source Dest --resume-from-report prev.csv --report resume.csv

# Quarantine duplicates (default behavior)
python -m folder_mover data.xlsx Source Dest --report out.csv

# Skip duplicates entirely
python -m folder_mover data.xlsx Source Dest --duplicates-action skip --report out.csv

# List quarantined duplicates with age info
python -m folder_mover --list-duplicates Dest

# Export quarantine report to CSV
python -m folder_mover --list-duplicates Dest --report duplicates.csv

# Preview cleanup of old duplicates (30+ days)
.\scripts\Cleanup-Duplicates.ps1 -DestRoot Dest

# Actually cleanup old duplicates
.\scripts\Cleanup-Duplicates.ps1 -DestRoot Dest -WhatIf:$false -ConfirmDelete

# Full run with all safety features
python -m folder_mover data.xlsx Source Dest `
    --exclude-pattern "*.tmp" `
    --exclude-pattern "*_backup" `
    --on-dest-exists rename `
    --report migration_$(Get-Date -Format 'yyyyMMdd').csv `
    -v
```

### Getting Help

```powershell
# Show all options
python -m folder_mover --help

# Show version
python -m folder_mover --version
```

---

## Support

If you encounter issues:

1. **Check the report** - The `message` column often explains the problem
2. **Increase verbosity** - Run with `-vv` for debug logging
3. **Test with dry run** - Reproduce the issue without making changes
4. **Review permissions** - Ensure the running user has read/write access
