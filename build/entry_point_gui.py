#!/usr/bin/env python3
"""
PyInstaller entry point for Folder Mover Pro GUI.

This file uses absolute imports to ensure PyInstaller
properly bundles the folder_mover package.
"""

import sys
from pathlib import Path

# Ensure src is in path for development
src_path = Path(__file__).parent.parent / "src"
if src_path.exists() and str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from folder_mover.gui_app import main

if __name__ == "__main__":
    sys.exit(main())
