============================================================
  Folder Mover Pro - Quick Start Guide
  Offline Windows File Migration Utility
  by Erasmus Labs
============================================================

WHAT IT DOES
- Reads CaseIDs from an Excel file (Column A)
- Scans a source folder tree
- Finds folders whose names contain CaseIDs
- Moves matching folders into a destination root
- Writes a CSV report of everything it did (or would do)

RECOMMENDED SAFE WORKFLOW
1) DRY RUN first (no changes) to generate a report
2) Review the CSV report
3) LIVE run with --max-moves 1 for a safe test
4) LIVE run without limits when confident

GUI (FolderMoverPro.exe)
1) Excel File: pick your .xlsx (CaseIDs in Column A)
2) Source Root: pick the folder tree to scan
3) Dest Root: pick the destination folder
4) Report CSV: choose where to save the report
5) Click "Preview (Dry Run)" first
6) When ready: uncheck Dry Run and click "Run"

CLI (FolderMoverPro-CLI.exe)
Dry run:
  FolderMoverPro-CLI.exe "cases.xlsx" "source_root" "dest_root" --dry-run --report "report.csv" -v

Live move with safety limit:
  FolderMoverPro-CLI.exe "cases.xlsx" "source_root" "dest_root" --max-moves 1 --report "report.csv" -v

WINDOWS SECURITY NOTE
This tool is not code-signed. SmartScreen may warn on first run.
Download only from GitHub Releases. Verify hashes if provided.

============================================================
