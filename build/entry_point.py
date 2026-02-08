#!/usr/bin/env python3
"""
PyInstaller entry point for Folder Mover Pro.

This script uses absolute imports to work correctly when bundled.
"""

import sys

# Add src to path for PyInstaller to find the package
import os
if getattr(sys, 'frozen', False):
    # Running as compiled exe
    pass
else:
    # Running as script - add src to path
    src_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src')
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

from folder_mover.cli import main

if __name__ == "__main__":
    sys.exit(main())
