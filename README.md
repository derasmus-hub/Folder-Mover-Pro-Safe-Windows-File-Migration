# Folder Mover Pro

**Offline Windows File Migration Utility**

A Windows-focused CLI tool for moving folders based on CaseIDs from an Excel file.

---

## Download

**[Download FolderMoverPro.exe from GitHub Releases](../../releases/latest)**

> Download the `.exe` file directly — **not** the source code zip.
> No installation or Python required. Just download and run.

### Quick Start (EXE)

```cmd
:: Preview what would happen (dry run)
FolderMoverPro.exe caselist.xlsx C:\Source C:\Dest --dry-run

:: Run the migration
FolderMoverPro.exe caselist.xlsx C:\Source C:\Dest --report migration.csv
```

---

## Quick Start (Python)

```powershell
# 1. Install
pip install -e .

# 2. Preview what would happen (dry run)
folder-mover caselist.xlsx C:\Source C:\Dest --dry-run --report preview.csv

# 3. Test with one folder
folder-mover caselist.xlsx C:\Source C:\Dest --max-moves 1 --report test.csv

# 4. Run full migration
folder-mover caselist.xlsx C:\Source C:\Dest --report migration.csv
```

See [Safe Test Plan](#safe-test-plan) before running on production data.

---

## Overview

This tool scans a source directory tree for folders whose names contain CaseIDs listed in an Excel file (Column A). Matched folders are moved directly into a destination directory. The tool handles naming collisions, supports dry-run mode for previewing operations, and generates detailed CSV reports.

### Features

- **Excel-driven**: Reads CaseIDs from Column A of an XLSX file
- **Leading zero preservation**: CaseIDs are treated as strings to preserve leading zeros
- **Substring matching**: A folder matches if its name contains the CaseID
- **Flat destination**: Folders are moved directly into DestRoot (no source structure preserved)
- **Collision handling**: Name conflicts resolved with `_1`, `_2`, etc. suffixes
- **Dry-run mode**: Preview operations without making changes
- **Idempotent**: Skip folders already at destination
- **Resume support**: Continue interrupted runs without re-processing
- **Exclusion patterns**: Skip folders matching glob/substring patterns
- **Detailed reporting**: CSV report of all operations with timestamps

## Installation

### Option 1: Install as Package (Recommended)

```powershell
# Install in development mode
pip install -e .

# Now you can run from anywhere:
folder-mover --help
```

### Option 2: Install Dependencies Only

```powershell
pip install -r requirements.txt

# Run as module:
python -m folder_mover --help
```

### Optional: Faster Matching

For large datasets (thousands of CaseIDs), install the Aho-Corasick matcher:

```powershell
pip install -r requirements-extra.txt
# Then use: folder-mover ... --matcher aho
```

## Usage

```bash
python -m folder_mover <excel_file> <source_root> <dest_root> [options]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `excel_file` | Path to Excel XLSX file with CaseIDs in Column A |
| `source_root` | Root directory to search for matching folders |
| `dest_root` | Destination directory where matched folders will be moved |

### Options

| Option | Description |
|--------|-------------|
| `-n, --dry-run, --whatif` | Preview operations without actually moving folders |
| `-y, --yes` | Skip confirmation prompt (use with caution) |
| `-r, --report FILE` | Path for CSV report (default: `report_YYYYMMDD_HHMMSS.csv`) |
| `-s, --sheet NAME` | Excel sheet name to read (default: active sheet) |
| `--max-moves N` | Limit to first N move operations (for safe testing) |
| `--max-folders N` | Limit folder scan to first N folders (for testing) |
| `--caseid-limit N` | Only process first N CaseIDs from Excel (for testing) |
| `--matcher ALGO` | Matching algorithm: `bucket` (default) or `aho` (faster, requires pyahocorasick) |
| `--exclude-pattern PAT` | Exclude folders matching pattern (can be specified multiple times) |
| `--on-dest-exists ACTION` | Action when destination exists: `rename` (default) or `skip` |
| `--duplicates-action ACTION` | How to handle CaseIDs with multiple matches: `quarantine` (default), `skip`, or `move-all` |
| `--list-duplicates` | List quarantined duplicates with age information (does not move any folders) |
| `--resume-from-report CSV` | Resume from previous report, skipping already-moved folders |
| `-v, --verbose` | Increase verbosity (-v for INFO, -vv for DEBUG) |
| `--version` | Show version and exit |
| `-h, --help` | Show help message and exit |

**Note:** In live mode (without `--dry-run`), you will be prompted to confirm before any folders are moved. Use `--yes` to skip this prompt for automated/scripted runs.

### Examples

Basic usage:
```bash
python -m folder_mover caselist.xlsx C:\Data\Source C:\Data\Dest
```

Preview changes without moving:
```bash
python -m folder_mover caselist.xlsx C:\Data\Source C:\Data\Dest --dry-run
```

Verbose output with report:
```bash
python -m folder_mover caselist.xlsx C:\Data\Source C:\Data\Dest -v --report moves.csv
```

Safe test run (move only 1 folder):
```bash
python -m folder_mover caselist.xlsx C:\Data\Source C:\Data\Dest --max-moves 1
```

Exclude temp and backup folders:
```bash
python -m folder_mover caselist.xlsx C:\Data\Source C:\Data\Dest --exclude-pattern "*.tmp" --exclude-pattern "*_backup"
```

Skip folders that already exist at destination (instead of renaming):
```bash
python -m folder_mover caselist.xlsx C:\Data\Source C:\Data\Dest --on-dest-exists skip
```

Resume after an interrupted run:
```bash
python -m folder_mover caselist.xlsx C:\Data\Source C:\Data\Dest --resume-from-report previous_run.csv
```

## Excel File Format

The Excel file (.xlsx) should have CaseIDs in **Column A**:

| Column A |
|----------|
| 00123    |
| 00456    |
| CASE-789 |
| 00123    |

### Important Notes

- **Leading zeros**: CaseIDs are read as strings, so leading zeros like `00123` are preserved exactly
- **Empty cells**: Empty rows are automatically skipped
- **Duplicates**: Duplicate CaseIDs are removed (first occurrence kept)
- **Whitespace**: Leading/trailing whitespace is trimmed
- **Data types**: Numeric values are converted to strings (e.g., `123` becomes `"123"`)
- **Sheet selection**: By default reads the active sheet; use `-s` to specify a sheet name

### Example Excel Structure

```
A1: 00123      <- Preserved as "00123"
A2: CASE-456   <- String with special characters
A3:            <- Empty, skipped
A4: 00123      <- Duplicate, skipped
A5: 789        <- Numeric, becomes "789"
```

Result: `["00123", "CASE-456", "789"]`

## CSV Report Format

When using `--report`, a detailed CSV file is generated with the following columns:

| Column | Description |
|--------|-------------|
| `timestamp` | When the operation occurred (YYYY-MM-DD HH:MM:SS) |
| `case_id` | The CaseID from the Excel file |
| `status` | Operation result (see Status Values below) |
| `source_path` | Original folder location |
| `dest_path` | Destination folder location (if moved) |
| `message` | Details about the operation |

### Status Values

| Status | Description |
|--------|-------------|
| `MOVED` | Folder moved successfully |
| `MOVED_RENAMED` | Moved with suffix (`_1`, `_2`) due to name collision |
| `FOUND_DRYRUN` | Would move (dry-run mode) |
| `FOUND_DRYRUN_RENAMED` | Would move with rename (dry-run mode) |
| `NOT_FOUND` | No folders matched this CaseID |
| `MULTIPLE_MATCHES` | CaseID matched multiple folders (all moved) |
| `SKIPPED_MISSING` | Source folder no longer exists |
| `SKIPPED_EXISTS` | Destination already exists |
| `SKIPPED_EXCLUDED` | Folder matched an exclusion pattern |
| `SKIPPED_RESUME` | Already moved in previous run (resume mode) |
| `SKIPPED_DUPLICATE` | Duplicate CaseID skipped (`--duplicates-action skip`) |
| `QUARANTINED` | Moved to `_DUPLICATES/<CaseID>/` folder |
| `QUARANTINED_RENAMED` | Quarantined with rename due to collision |
| `FOUND_DRYRUN_QUARANTINE` | Would quarantine (dry-run mode) |
| `ERROR` | Operation failed (see message for details) |

### Sample Report Output

See [`examples/sample_report.csv`](examples/sample_report.csv) for a complete example.

```csv
timestamp,case_id,status,source_path,dest_path,message
2024-01-15 10:30:00,00123,MOVED,C:\Source\Case_00123_Smith,C:\Dest\Case_00123_Smith,Moved successfully
2024-01-15 10:30:01,00456,MOVED_RENAMED,C:\Source\Case_00456,C:\Dest\Case_00456_1,Moved successfully (renamed from Case_00456 to Case_00456_1)
2024-01-15 10:30:02,00789,MULTIPLE_MATCHES,C:\Source\2023\Case_00789,C:\Dest\Case_00789,[Multiple matches] Moved successfully
2024-01-15 10:30:02,00789,MULTIPLE_MATCHES,C:\Source\2024\Case_00789,C:\Dest\Case_00789_1,[Multiple matches] Moved successfully
2024-01-15 10:30:03,99999,NOT_FOUND,,,No matching folders found for this CaseID
2024-01-15 10:30:04,00111,ERROR,C:\Source\Case_00111,,PermissionError: Access denied
```

## Safe Test Plan

**Always follow this 4-step protocol before running on production data.**

### Step 1: Dry Run (Preview Only)

See what WOULD happen without making any changes:

```powershell
folder-mover caselist.xlsx C:\Source C:\Dest --dry-run --report dryrun.csv -v
```

**Review the report for:**
- `FOUND_DRYRUN` - Folders that would be moved
- `NOT_FOUND` - CaseIDs with no matches (expected or data issue?)
- `FOUND_DRYRUN_RENAMED` - Folders that would be renamed due to collision

### Step 2: Single Folder Test

Move exactly ONE folder to verify the mechanism works:

```powershell
folder-mover caselist.xlsx C:\Source C:\Dest --max-moves 1 --report move1.csv -v
```

**Verify:**
- [ ] Folder was moved to destination
- [ ] Source folder no longer exists
- [ ] All contents transferred correctly
- [ ] Report shows `MOVED` status

### Step 3: Small Batch Test

Test with a larger sample (10-100 folders):

```powershell
folder-mover caselist.xlsx C:\Source C:\Dest --max-moves 10 --report move10.csv -v
```

**Verify:**
- [ ] All moves completed as expected
- [ ] Name collisions handled correctly (`_1`, `_2` suffixes)
- [ ] No permission errors

### Step 4: Full Migration

Once confident, run the complete migration:

```powershell
folder-mover caselist.xlsx C:\Source C:\Dest --report migration.csv -v
```

**Post-migration checklist:**
- [ ] Review report for any `ERROR` entries
- [ ] Verify destination folder count
- [ ] Archive the report for audit purposes

### Matching Algorithms

The tool supports two algorithms for matching CaseIDs to folder names:

| Algorithm | Flag | Description |
|-----------|------|-------------|
| **bucket** (default) | `--matcher bucket` | Length-bucket optimization. No extra dependencies. Good for most use cases. |
| **aho** | `--matcher aho` | Aho-Corasick automaton. Faster for large datasets with many CaseIDs. Requires `pyahocorasick`. |

**When to use Aho-Corasick:**
- You have thousands of CaseIDs AND hundreds of thousands of folders
- The bucket matcher is too slow for your dataset
- You're running repeated operations and want maximum throughput

**Installing the optional dependency:**
```bash
pip install -r requirements-extra.txt
# or directly:
pip install pyahocorasick
```

**Note:** `pyahocorasick` requires a C compiler. On Windows, you may need [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/). On Linux, `gcc` is typically sufficient.

**Example with Aho-Corasick:**
```bash
python -m folder_mover cases.xlsx C:\Data\Source C:\Data\Dest --matcher aho --dry-run
```

### Safety Features for Production

The tool includes several safety features for running on production file servers:

**Exclusion Patterns** (`--exclude-pattern`):
Skip folders matching specific patterns. Patterns support:
- Glob wildcards: `*.tmp`, `*_backup`, `Case_*_Old`
- Substring matching: `temp` matches `my_temp_folder`

```bash
python -m folder_mover cases.xlsx Source Dest --exclude-pattern "*.tmp" --exclude-pattern "_OLD"
```

**Destination Exists Behavior** (`--on-dest-exists`):
- `rename` (default): Add `_1`, `_2`, etc. suffix if destination exists
- `skip`: Skip the folder if destination already exists

```bash
python -m folder_mover cases.xlsx Source Dest --on-dest-exists skip
```

**Duplicate CaseID Handling** (`--duplicates-action`):
When a CaseID matches multiple folders, you can choose how to handle them:
- `quarantine` (default): Move all matching folders to `Dest\_DUPLICATES\<CaseID>\` for manual review
- `skip`: Do not move duplicates, only report them
- `move-all`: Move all to main destination (previous behavior)

```bash
# Quarantine duplicates for review (default)
python -m folder_mover cases.xlsx Source Dest --duplicates-action quarantine

# Skip duplicates entirely
python -m folder_mover cases.xlsx Source Dest --duplicates-action skip

# Move all (old behavior)
python -m folder_mover cases.xlsx Source Dest --duplicates-action move-all
```

Quarantine structure example:
```
Dest\
├── Case_00001\              <- Single match: moved normally
├── Case_00002\              <- Single match: moved normally
└── _DUPLICATES\
    └── 00123\               <- CaseID with multiple matches
        ├── Case_00123_A\    <- First match
        └── Case_00123_B\    <- Second match
```

**Reviewing Quarantined Duplicates** (`--list-duplicates`):
After migration, review quarantined folders with age information:

```bash
# List quarantined duplicates to console
python -m folder_mover --list-duplicates C:\Dest

# Export to CSV for review
python -m folder_mover --list-duplicates C:\Dest --report duplicates_review.csv
```

Example output:
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

**Cleanup Old Duplicates** (`scripts/Cleanup-Duplicates.ps1`):
After reviewing and resolving duplicates, clean up old quarantined folders:

```powershell
# Preview what would be deleted (default - safe, no changes)
.\scripts\Cleanup-Duplicates.ps1 -DestRoot C:\Dest

# Preview folders older than 60 days
.\scripts\Cleanup-Duplicates.ps1 -DestRoot C:\Dest -OlderThanDays 60

# Actually delete (requires typing DELETE to confirm)
.\scripts\Cleanup-Duplicates.ps1 -DestRoot C:\Dest -WhatIf:$false -ConfirmDelete
```

Safety features: Preview mode by default, requires explicit `-ConfirmDelete` switch, requires typing `DELETE` to confirm, only operates on `_DUPLICATES` folder.

**Resume from Previous Run** (`--resume-from-report`):
If a run is interrupted, resume by passing the previous report. Folders with status `MOVED` or `MOVED_RENAMED` will be skipped:

```bash
# If interrupted, resume with:
python -m folder_mover cases.xlsx Source Dest --resume-from-report previous_report.csv
```

### Tips for Large Runs

- Use `--max-folders 1000` to test scanning performance first
- Use `--caseid-limit 10` to test with a subset of CaseIDs
- Use `--matcher aho` for faster matching with many CaseIDs (requires pyahocorasick)
- Use `-v` for detailed logging during troubleshooting
- Always generate a report for audit trail
- Use `--exclude-pattern` to skip temp/backup folders
- Use `--resume-from-report` to continue after interruptions

## Project Structure

```
folder-mover/
├── src/folder_mover/       # Main package
│   ├── __init__.py         # Package metadata
│   ├── __main__.py         # Module entry point
│   ├── cli.py              # Command-line interface
│   ├── excel.py            # Excel file reading
│   ├── indexer.py          # Folder scanning and indexing
│   ├── mover.py            # Folder move operations
│   ├── report.py           # CSV report generation
│   ├── types.py            # Data classes and enums
│   └── utils.py            # Windows path utilities
├── tests/                  # Unit tests
├── docs/
│   └── CLIENT_HANDOFF.md   # Client deployment guide
├── scripts/                # PowerShell utility scripts
│   ├── Cleanup-Duplicates.ps1  # Quarantine cleanup script
│   ├── Run-FolderMoverPro.ps1  # Wrapper for exe
│   └── Run-FromSource.ps1      # Run from Python source
├── release/scripts/        # Example scripts
│   ├── run_dryrun_example.ps1
│   ├── run_live_example.ps1
│   └── create_test_tree.ps1
├── examples/               # Example files
├── pyproject.toml          # Package configuration
├── requirements.txt        # Dependencies
└── requirements-extra.txt  # Optional dependencies
```

## Troubleshooting

### Locked Files / Access Denied

**Symptom:** `PermissionError: Access denied` or `The process cannot access the file`

**Causes:**
- File is open in another application (Word, Excel, etc.)
- Antivirus is scanning the folder
- Windows Search indexer has a lock

**Solutions:**
1. Close all applications that might have files open in the source folder
2. Temporarily disable real-time antivirus scanning for the source/dest folders
3. Wait a few seconds and retry (Windows may release locks)
4. Use `--exclude-pattern` to skip problematic folders and handle them manually

```powershell
# Skip folders with known issues
folder-mover data.xlsx Source Dest --exclude-pattern "ProblemFolder" --report partial.csv
```

### Long Path Errors (Path Too Long)

**Symptom:** `FileNotFoundError` or `The filename or extension is too long`

**Cause:** Windows has a default 260-character path limit.

**Solutions:**

The tool automatically handles long paths using the `\\?\` prefix. If you still encounter issues:

1. **Enable long paths in Windows (recommended):**
   ```powershell
   # Run as Administrator
   Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1
   # Restart your computer
   ```

2. **Shorten folder names** at the source or destination

3. **Move to a shorter base path** (e.g., `C:\D` instead of `C:\Users\Username\Documents\Projects\...`)

### Permission Denied on Network Shares (UNC Paths)

**Symptom:** Cannot access `\\server\share` paths

**Solutions:**
1. Ensure you have read access to source and write access to destination
2. Map the network drive and use the drive letter instead:
   ```powershell
   net use Z: \\server\share
   folder-mover data.xlsx Z:\Source Z:\Dest --report out.csv
   ```
3. Run PowerShell/Command Prompt as Administrator
4. Check if the share requires specific credentials

### "No module named 'openpyxl'" Error

**Solution:**
```powershell
pip install openpyxl
# Or install all dependencies:
pip install -r requirements.txt
```

### Slow Performance with Many CaseIDs

**Symptom:** Matching phase takes very long with thousands of CaseIDs

**Solution:** Use the Aho-Corasick matcher:
```powershell
pip install pyahocorasick
folder-mover data.xlsx Source Dest --matcher aho --report out.csv
```

### Resume After Crash or Interruption

If the tool is interrupted mid-run:

```powershell
# Resume using the report from the interrupted run
folder-mover data.xlsx Source Dest --resume-from-report interrupted_report.csv --report resume.csv
```

The tool will skip any folders already marked as `MOVED` or `MOVED_RENAMED`.

### Report Shows Unexpected NOT_FOUND

**Possible causes:**
1. CaseID in Excel doesn't match folder naming convention
2. Leading zeros were lost (ensure Excel column is formatted as Text)
3. Folder is in a subdirectory not being scanned

**Debug steps:**
```powershell
# Run with debug verbosity
folder-mover data.xlsx Source Dest --dry-run -vv 2>&1 | Out-File debug.log

# Search for a specific CaseID in folder names
Get-ChildItem -Path "C:\Source" -Recurse -Directory | Where-Object { $_.Name -like "*00123*" }
```

---

## Additional Documentation

- **[Client Handoff Guide](docs/CLIENT_HANDOFF.md)** - Detailed test protocol, report interpretation, and resume instructions
- **[Release Scripts](release/scripts/)** - PowerShell wrappers for common operations

## Windows Security & Trust

### SmartScreen Warnings

Folder Mover Pro executables are **not digitally signed** with a code-signing certificate. When you first run an EXE, Windows SmartScreen will display a warning:

> "Windows protected your PC — Microsoft Defender SmartScreen prevented an unrecognized app from starting."

**This is expected behavior for unsigned software.** To proceed:
1. Click **"More info"**
2. Click **"Run anyway"**

SmartScreen warnings cannot be removed without purchasing a code-signing certificate (typically $200-400/year) and building reputation through Microsoft's telemetry system. This is a cost-benefit decision, not a sign that the software is unsafe.

### SHA256 Verification

Every release includes SHA256 hashes for both EXE files and the release ZIP. To verify file integrity:

```powershell
# Check hash of a downloaded file
Get-FileHash .\FolderMoverPro.exe -Algorithm SHA256

# Compare the output against the hash published in the release notes
```

If the hash does not match the published value, **do not run the file** — it may have been modified in transit.

### Why Not Email EXEs

Do not distribute EXE files via email:
- Most email providers strip or quarantine `.exe` attachments
- Recipients have no way to verify the file wasn't tampered with
- Email is not a reliable delivery mechanism for executables

Use GitHub Releases or a shared ZIP download link instead.

## Distribution

### Recommended: GitHub Releases

The preferred distribution method is **GitHub Releases**:
- Download the `.zip` file (not the source code archive)
- ZIP contains both EXEs, a quick-start guide, and demo files
- Release notes include SHA256 hashes for verification

### Release ZIP Contents

```
FolderMoverPro-v1.0.3-win64.zip
├── FolderMoverPro.exe          # GUI - double-click to launch
├── FolderMoverPro-CLI.exe      # CLI - for command-line use
├── README-QuickStart.txt       # Getting started guide
└── demo/
    ├── demo_cases.xlsx         # Sample Excel file
    ├── demo_source/            # Sample source tree
    └── demo_dest/              # Empty destination for testing
```

### Building From Source

If you prefer to build the EXEs yourself:

```powershell
# 1. Generate the icon (first time only)
.\scripts\Make-Icon.ps1

# 2. Build both EXEs with icon and version metadata
.\build\build_exe.ps1 -Clean

# 3. Package the release ZIP
.\build\package_release.ps1

# 4. Verify versions match
.\scripts\Check-Version.ps1
```

## Running Tests

```powershell
pip install pytest
$env:PYTHONPATH = "src"
pytest tests/ -v
```

## License

MIT License
