# Folder Mover Pro v{VERSION}

## Downloads

| File | SHA256 |
|------|--------|
| `FolderMoverPro-v{VERSION}-win64.zip` | `{SHA256_ZIP}` |
| `FolderMoverPro.exe` (GUI) | `{SHA256_GUI}` |
| `FolderMoverPro-CLI.exe` (CLI) | `{SHA256_CLI}` |

**Download the ZIP file** — it contains both executables, a quick-start guide, and demo files.

## What's New

- {CHANGE_1}
- {CHANGE_2}
- {CHANGE_3}

## Known Limitations

- **EXEs are unsigned.** Windows SmartScreen will warn on first launch. Click "More info" then "Run anyway". This is normal for unsigned software.
- Aho-Corasick matcher (`--matcher aho`) is not bundled in the EXE. Use the default bucket matcher, which handles most use cases well.
- Long path support requires Windows 10 1607+ with long paths enabled in the registry.

## Verification

To verify your download has not been tampered with:

```powershell
# Verify the ZIP
(Get-FileHash .\FolderMoverPro-v{VERSION}-win64.zip -Algorithm SHA256).Hash
# Expected: {SHA256_ZIP}

# Or verify individual EXEs after extracting
(Get-FileHash .\FolderMoverPro.exe -Algorithm SHA256).Hash
# Expected: {SHA256_GUI}

(Get-FileHash .\FolderMoverPro-CLI.exe -Algorithm SHA256).Hash
# Expected: {SHA256_CLI}
```

## Quick Start

1. Extract the ZIP to a folder
2. Double-click `FolderMoverPro.exe` to launch the GUI
3. Or use the CLI: `FolderMoverPro-CLI.exe caselist.xlsx C:\Source C:\Dest --dry-run`
4. **Always run `--dry-run` first** to preview changes before moving files

See `README-QuickStart.txt` in the ZIP for detailed instructions.

## System Requirements

- Windows 10 or later (64-bit)
- No Python installation required
- No internet connection required
