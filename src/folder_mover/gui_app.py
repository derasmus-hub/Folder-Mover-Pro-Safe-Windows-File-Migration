"""
Folder Mover Pro - GUI Application Entry Point

This module provides the entry point for the windowed GUI executable.
It handles PyInstaller frozen app detection and launches the GUI.
"""

import sys


def main() -> int:
    """
    Main entry point for the GUI application.

    Returns:
        int: Exit code (0 for success)
    """
    # Handle PyInstaller frozen app - set up paths if needed
    if getattr(sys, 'frozen', False):
        # Running as compiled exe
        import os
        # Ensure working directory is sensible for file dialogs
        if hasattr(sys, '_MEIPASS'):
            # PyInstaller extracts to temp dir, but we want user's dir for dialogs
            pass  # File dialogs will use last-used or user home by default

    # Import and run the GUI
    from .gui import main as gui_main
    gui_main()

    return 0


if __name__ == "__main__":
    sys.exit(main())
