#!/usr/bin/env python3
"""
Generate PyInstaller version-info files from pyproject.toml.

Reads the version from pyproject.toml (single source of truth) and writes
Windows VERSIONINFO resource files for the GUI and CLI executables.

Output:
    build/version_info_gui.txt
    build/version_info_cli.txt

Usage:
    python build/make_version_info.py
"""

import re
import sys
from datetime import datetime
from pathlib import Path

# Resolve paths relative to this script
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"


def read_version_from_pyproject() -> str:
    """Read version string from pyproject.toml."""
    content = PYPROJECT_PATH.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        print("ERROR: Could not find version in pyproject.toml", file=sys.stderr)
        sys.exit(1)
    return match.group(1)


def version_to_tuple(version_str: str) -> tuple:
    """Convert '1.0.3' to (1, 0, 3, 0) for Windows VERSIONINFO."""
    parts = version_str.split(".")
    # Pad to 4 parts with zeros
    while len(parts) < 4:
        parts.append("0")
    return tuple(int(p) for p in parts[:4])


def generate_version_info(
    version_str: str,
    file_description: str,
    internal_name: str,
    original_filename: str,
) -> str:
    """Generate PyInstaller version-info text content."""
    vt = version_to_tuple(version_str)
    year = datetime.now().year

    return f"""# UTF-8
#
# For more details about fixed file info 'ffi' see:
# http://msdn.microsoft.com/en-us/library/ms646997.aspx
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={vt},
    prodvers={vt},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'040904B0',
          [
            StringStruct(u'CompanyName', u'Erasmus Labs'),
            StringStruct(u'FileDescription', u'{file_description}'),
            StringStruct(u'FileVersion', u'{version_str}'),
            StringStruct(u'InternalName', u'{internal_name}'),
            StringStruct(u'LegalCopyright', u'Copyright (c) {year} Erasmus Labs. All rights reserved.'),
            StringStruct(u'OriginalFilename', u'{original_filename}'),
            StringStruct(u'ProductName', u'Folder Mover Pro'),
            StringStruct(u'ProductVersion', u'{version_str}'),
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""


def main():
    version = read_version_from_pyproject()
    print(f"  Version from pyproject.toml: {version}")

    # GUI version info
    gui_info = generate_version_info(
        version_str=version,
        file_description="Folder Mover Pro - Offline Windows File Migration Utility",
        internal_name="FolderMoverPro",
        original_filename="FolderMoverPro.exe",
    )
    gui_path = SCRIPT_DIR / "version_info_gui.txt"
    gui_path.write_text(gui_info, encoding="utf-8")
    print(f"  Wrote: {gui_path}")

    # CLI version info
    cli_info = generate_version_info(
        version_str=version,
        file_description="Folder Mover Pro CLI - Offline Windows File Migration Utility",
        internal_name="FolderMoverPro-CLI",
        original_filename="FolderMoverPro-CLI.exe",
    )
    cli_path = SCRIPT_DIR / "version_info_cli.txt"
    cli_path.write_text(cli_info, encoding="utf-8")
    print(f"  Wrote: {cli_path}")


if __name__ == "__main__":
    main()
