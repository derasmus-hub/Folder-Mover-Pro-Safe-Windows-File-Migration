# Folder Mover Pro - Runbook

## Overview

This runbook provides operational procedures for Folder Mover Pro.

---

## Pre-Flight Checklist

Before running any file migration:

- [ ] Verify Excel file exists and has CaseIDs in Column A
- [ ] Verify source folder exists and is accessible
- [ ] Verify destination drive has sufficient space
- [ ] Close any applications using files in the source folder
- [ ] Ensure you have write permissions on destination
- [ ] Consider creating a backup of critical data
- [ ] Run with `--dry-run` first to preview operations

---

## Common Operations

### Verify Installation

```cmd
FolderMoverPro.exe --version
```

Expected: `1.0.0`

### Display Help

```cmd
FolderMoverPro.exe --help
```

### Dry Run (Preview)

Always run a dry-run first:

```cmd
FolderMoverPro.exe cases.xlsx C:\Source C:\Dest --dry-run --report preview.csv
```

### Production Run

After verifying the dry-run report:

```cmd
FolderMoverPro.exe cases.xlsx C:\Source C:\Dest --report migration.csv --yes
```

### Resume After Interruption

If a run is interrupted, resume using the previous report:

```cmd
FolderMoverPro.exe cases.xlsx C:\Source C:\Dest --resume-from-report migration.csv --report migration2.csv
```

---

## Troubleshooting

### Issue: "Access Denied" Error

**Cause:** Insufficient permissions or files in use.

**Resolution:**
1. Run Command Prompt as Administrator
2. Close applications that may have files open
3. Retry the operation

### Issue: Executable Won't Start

**Cause:** Windows SmartScreen or antivirus blocking.

**Resolution:**
1. Right-click `FolderMoverPro.exe`
2. Select "Properties"
3. Check "Unblock" at the bottom
4. Click "Apply"

### Issue: "Path Too Long" Error

**Cause:** Windows path exceeds 260 characters.

**Resolution:**
1. Move files to a shorter base path first
2. Or enable long paths in Windows:
   ```
   Computer Configuration > Administrative Templates >
   System > Filesystem > Enable Win32 long paths
   ```

### Issue: Excel File Not Found

**Cause:** Path is incorrect or file is open in Excel.

**Resolution:**
1. Use full absolute path to Excel file
2. Close Excel if the file is open
3. Verify the file extension is `.xlsx`

### Issue: CaseID Not Found

**Cause:** Folder name doesn't contain the CaseID string.

**Resolution:**
1. Check the CSV report for NOT_FOUND entries
2. Verify CaseID format matches folder naming convention
3. CaseIDs are matched as substrings (case-sensitive)

---

## Safety Guidelines

1. **Always dry-run first** - Use `--dry-run` before any production move
2. **Never interrupt** a move operation in progress
3. **Verify results** after each operation completes
4. **Keep backups** of irreplaceable data
5. **Use --max-moves** for incremental testing with new datasets

---

## Environment Requirements

| Requirement | Minimum |
|-------------|---------|
| OS | Windows 10/11 |
| RAM | 512 MB available |
| Disk | Space for temporary operations |
| Network | Not required (offline utility) |

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Input/configuration error |
| 2 | Completed with some errors |
| 130 | Cancelled by user (Ctrl+C) |

---

## Report Format

The CSV report contains:

| Column | Description |
|--------|-------------|
| case_id | The matched CaseID |
| source_path | Original folder path |
| dest_path | Destination path (or intended path for dry-run) |
| status | MOVED, MOVED_RENAMED, SKIPPED, ERROR, NOT_FOUND |
| message | Additional details |
| is_multiple | Whether CaseID matched multiple folders |

---

## Logging

Console output displays operation status in real-time.

For verbose logging:
```cmd
FolderMoverPro.exe cases.xlsx C:\Source C:\Dest -v
```

For debug logging:
```cmd
FolderMoverPro.exe cases.xlsx C:\Source C:\Dest -vv
```

For persistent logs, redirect output:
```cmd
FolderMoverPro.exe cases.xlsx C:\Source C:\Dest > migration.log 2>&1
```

---

## Emergency Procedures

### If Operation Hangs

1. Wait at least 5 minutes (large files take time)
2. Check Task Manager for disk activity
3. If no activity, press `Ctrl+C` to cancel
4. Check source and destination for partial files

### If System Crashes During Move

1. Reboot system
2. Check destination for completed files
3. Check source for remaining files
4. Use `--resume-from-report` to continue from where it left off

---

## Maintenance

No maintenance required. Standalone executable with no dependencies.

To update: Replace `FolderMoverPro.exe` with newer version.
