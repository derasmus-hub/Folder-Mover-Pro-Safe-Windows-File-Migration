# Folder Mover Pro v1.0.4

## Downloads

| File | SHA256 |
|------|--------|
| `FolderMoverPro-v1.0.4-win64.zip` | `FF4A230BD2D2F2FC0A8FD48D26FB0D6DD9FBF41905713D91E9D1A352E8317F3D` |
| `FolderMoverPro.exe` (GUI) | `075D60A2B8C4504FABDC7EB7393C7FB25F01FA159C88EBE447222BD88A522A75` |
| `FolderMoverPro-CLI.exe` (CLI) | `2D7D80040A5CD1C7848F9E2A69F3AEF6B2E21FCF6D28D4BC70DE92964F618A50` |

**Download the ZIP file** — it contains both executables, a quick-start guide, and demo files.

## What's New

- **Fix: Aho-Corasick matcher no longer crashes when pyahocorasick is missing.** The CLI and GUI now fall back to the built-in bucket matcher automatically with a WARNING log, instead of raising an error or producing zero matches.
- **Fix: GUI no longer offers the "aho" matcher option when pyahocorasick is unavailable.** The combobox only shows available matchers, with a "(aho unavailable)" hint when the optional dependency is not installed.
- **Build: PyInstaller now includes `--hidden-import ahocorasick`** so the C extension is bundled automatically when present at build time.

## Known Limitations

- **EXEs are unsigned.** Windows SmartScreen will warn on first launch. Click "More info" then "Run anyway". This is normal for unsigned software.
- Aho-Corasick matcher (`--matcher aho`) requires optional `pyahocorasick` package. If unavailable, the app falls back to the built-in bucket matcher automatically.
- Long path support requires Windows 10 1607+ with long paths enabled in the registry.

## Verification

To verify your download has not been tampered with:

```powershell
# Verify the ZIP
(Get-FileHash .\FolderMoverPro-v1.0.4-win64.zip -Algorithm SHA256).Hash
# Expected: FF4A230BD2D2F2FC0A8FD48D26FB0D6DD9FBF41905713D91E9D1A352E8317F3D

# Or verify individual EXEs after extracting
(Get-FileHash .\FolderMoverPro.exe -Algorithm SHA256).Hash
# Expected: 075D60A2B8C4504FABDC7EB7393C7FB25F01FA159C88EBE447222BD88A522A75

(Get-FileHash .\FolderMoverPro-CLI.exe -Algorithm SHA256).Hash
# Expected: 2D7D80040A5CD1C7848F9E2A69F3AEF6B2E21FCF6D28D4BC70DE92964F618A50
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
