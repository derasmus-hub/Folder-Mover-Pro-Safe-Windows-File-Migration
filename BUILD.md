# Building Folder Mover Pro

## Prerequisites

- Windows 10/11
- Python 3.8 or higher (with pip)
- Virtual environment (venv) created and activated

## Build Steps

### 1. Open PowerShell and Activate venv

Navigate to the project root and activate the virtual environment:

```powershell
cd C:\Users\erasm\OneDrive\Documents\Folder-Mover-Pro-Safe-Windows-File-Migration
.\.venv\Scripts\Activate.ps1
```

### 2. Run the Build Script

```powershell
.\build\build_exe.ps1
```

To clean previous builds first:

```powershell
.\build\build_exe.ps1 -Clean
```

### 3. Locate Output

The executable will be created at:

```
dist\FolderMoverPro.exe
```

## What the Build Script Does

1. Installs PyInstaller (if not already installed)
2. Runs PyInstaller with the following options:
   - `--onefile`: Single executable (no additional files needed)
   - `--console`: Console application (shows terminal window)
   - `--name FolderMoverPro`: Output filename
   - `--paths src`: Includes the src directory for imports
3. Outputs to `dist\FolderMoverPro.exe`

## Output Details

| Property | Value |
|----------|-------|
| Type | Console application |
| Format | Single .exe file |
| Python required on target | No |
| Entry point | `folder_mover.cli:main` |

## Manual Build (Alternative)

If you prefer to run PyInstaller directly (with venv activated):

```powershell
$env:PYTHONPATH = "src"
python -m pip install pyinstaller
python -m PyInstaller --onefile --console --name FolderMoverPro --paths src src\folder_mover\cli.py
```

## Verification

Test the built executable:

```powershell
.\dist\FolderMoverPro.exe --version
```

Expected output:

```
1.0.0
```

Test help:

```powershell
.\dist\FolderMoverPro.exe --help
```

## Running Tests Before Building

```powershell
$env:PYTHONPATH = "src"
pytest -q
```

All tests should pass before building a release.
