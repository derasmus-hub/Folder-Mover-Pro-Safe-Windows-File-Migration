# Folder Mover Pro

**Offline Windows File Migration Utility**

## Quick Start

### Option 1: Run the Executable (Recommended)

1. Download `FolderMoverPro.exe` from the `dist/` folder
2. Place it anywhere on your Windows machine
3. Open Command Prompt or PowerShell:

```cmd
FolderMoverPro.exe --help
```

No installation required. No Python needed.

### Option 2: Run from Source

Requires Python 3.8+

```powershell
$env:PYTHONPATH = "src"
python -m folder_mover.cli --help
```

Or install in development mode:

```powershell
pip install -e .
folder-mover --help
```

---

## What This Tool Does

Folder Mover Pro moves folders based on CaseIDs from an Excel file:

- Reads CaseIDs from Column A of an Excel XLSX file
- Scans a source directory for folders containing those CaseIDs
- Moves matched folders to a destination directory
- Handles naming collisions with numeric suffixes
- Generates detailed CSV reports of all operations

---

## Basic Usage

```cmd
FolderMoverPro.exe <excel_file> <source_root> <dest_root> [options]
```

### Examples

Preview operations (dry run):
```cmd
FolderMoverPro.exe caselist.xlsx C:\Data\Source C:\Data\Dest --dry-run
```

Move folders with report:
```cmd
FolderMoverPro.exe caselist.xlsx C:\Data\Source C:\Data\Dest --report moves.csv
```

Safe test (move only 1 folder):
```cmd
FolderMoverPro.exe caselist.xlsx C:\Data\Source C:\Data\Dest --max-moves 1
```

---

## Key Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview without moving |
| `--report FILE` | Save CSV report |
| `--max-moves N` | Limit number of moves |
| `--yes` | Skip confirmation prompt |
| `--verbose` | Show detailed output |
| `--version` | Show version |
| `--help` | Show all options |

---

## File Locations

| File | Purpose |
|------|---------|
| `dist/FolderMoverPro.exe` | Standalone executable |
| `src/folder_mover/` | Python source code |
| `tests/` | Test suite |
| `BUILD.md` | Build instructions |
| `RUNBOOK.md` | Operations guide |

---

## Support

This is an offline utility. All operations are performed locally on your machine.

- For build instructions, see `BUILD.md`
- For operational procedures, see `RUNBOOK.md`
- For detailed documentation, see `README.md`
