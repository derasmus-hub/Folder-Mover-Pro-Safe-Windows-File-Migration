"""
Folder Mover Pro - Offline Windows File Migration Utility

A Windows-focused CLI tool for moving folders based on Excel CaseID lists.

This package provides functionality to:
- Read CaseIDs from an Excel XLSX file (Column A)
- Index folders under a source root directory
- Match folders by checking if folder names contain the CaseID
- Move matched folders to a destination root
- Handle naming collisions with numeric suffixes
- Generate detailed CSV reports of operations
"""

# Product identity constants
PRODUCT_NAME = "Folder Mover Pro"
PRODUCT_VERSION = "1.0.0"
PRODUCT_DESCRIPTION = "Offline Windows File Migration Utility"

__version__ = PRODUCT_VERSION
__author__ = "Folder Mover Team"
