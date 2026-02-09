"""
Folder indexer for building a searchable index of folders under SourceRoot.

This module is responsible for:
- Recursively scanning a source directory tree using os.scandir (fast)
- Building an index of folder names to their full paths
- Matching folders where the folder name contains a given CaseID
- Supporting efficient lookups for large directory trees (~300k folders)
- Optional Aho-Corasick acceleration for batch substring matching
"""

import logging
import os
import sys
from collections import defaultdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Literal, Optional, Union

from .types import FolderEntry, FolderMatch
from .utils import (
    from_extended_length_path,
    normalize_path,
    to_extended_length_path,
)

logger = logging.getLogger(__name__)

# Try to import pyahocorasick for faster multi-pattern matching
try:
    import ahocorasick
    HAS_AHOCORASICK = True
except ImportError:
    ahocorasick = None  # type: ignore
    HAS_AHOCORASICK = False


# Matcher type literal for type hints
MatcherType = Literal["bucket", "aho"]


class MatcherNotAvailableError(Exception):
    """Raised when requested matcher is not available."""
    pass


def scan_folders(
    source_root: Union[str, Path],
    follow_symlinks: bool = False
) -> List[FolderEntry]:
    """
    Recursively scan a directory tree and collect all folder entries.

    Uses os.scandir for efficient directory traversal. Handles permission
    errors gracefully by logging and skipping inaccessible directories.

    Args:
        source_root: The root directory to scan
        follow_symlinks: Whether to follow symbolic links (default: False)

    Returns:
        List of FolderEntry objects for all discovered folders

    Raises:
        FileNotFoundError: If source_root doesn't exist
        NotADirectoryError: If source_root is not a directory
    """
    root_path = Path(source_root)

    if not root_path.exists():
        raise FileNotFoundError(f"Source root not found: {root_path}")

    if not root_path.is_dir():
        raise NotADirectoryError(f"Source root is not a directory: {root_path}")

    # Normalize path for consistent handling
    # On Windows, use extended-length path prefix for long path support
    root_normalized = normalize_path(root_path)
    root_str = to_extended_length_path(root_normalized)

    logger.info(f"Scanning folders under: {root_normalized}")

    folders: List[FolderEntry] = []
    dirs_scanned = 0
    errors_count = 0

    def _scan_recursive(dir_path: str) -> None:
        """Recursively scan directory using os.scandir."""
        nonlocal dirs_scanned, errors_count

        try:
            with os.scandir(dir_path) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=follow_symlinks):
                            # Add this folder to results
                            # Convert back to normal form for human-readable output
                            folder_path = from_extended_length_path(entry.path)

                            folders.append(FolderEntry(
                                name=entry.name,
                                path=folder_path
                            ))
                            dirs_scanned += 1

                            if dirs_scanned % 10000 == 0:
                                logger.info(f"Scanned {dirs_scanned} folders...")

                            # Recurse into subdirectory
                            _scan_recursive(entry.path)

                    except OSError as e:
                        errors_count += 1
                        logger.warning(f"Cannot access {entry.path}: {e}")

        except OSError as e:
            errors_count += 1
            logger.warning(f"Cannot scan directory {dir_path}: {e}")

    _scan_recursive(root_str)

    logger.info(
        f"Scan complete: {len(folders)} folders found "
        f"({errors_count} access errors skipped)"
    )

    return folders


def match_caseids(
    case_ids: List[str],
    folders: List[FolderEntry],
    case_sensitive: bool = False,
    matcher: MatcherType = "bucket"
) -> Dict[str, List[FolderEntry]]:
    """
    Find folders whose names contain any of the given CaseIDs.

    Supports two matching algorithms:
    - "bucket": Length-bucket optimization (default, no dependencies)
    - "aho": Aho-Corasick automaton (requires pyahocorasick, faster for large datasets)

    Args:
        case_ids: List of CaseID strings to search for
        folders: List of FolderEntry objects to search in
        case_sensitive: Whether matching is case-sensitive (default: False)
        matcher: Matching algorithm to use ("bucket" or "aho", default: "bucket")

    Returns:
        Dictionary mapping each CaseID to list of matching FolderEntry objects.
        CaseIDs with no matches will have empty lists.

    Note:
        If matcher="aho" but pyahocorasick is not installed, logs a WARNING
        and automatically falls back to the bucket matcher.
    """
    if not case_ids or not folders:
        return {cid: [] for cid in case_ids}

    logger.info(
        f"Matching {len(case_ids)} CaseIDs against {len(folders)} folders "
        f"using {matcher} matcher"
    )

    if matcher == "aho":
        if not HAS_AHOCORASICK:
            logger.warning(
                "Aho-Corasick matcher requested but pyahocorasick is not installed. "
                "Falling back to bucket matcher."
            )
            return _match_with_length_buckets(case_ids, folders, case_sensitive)
        return _match_with_ahocorasick(case_ids, folders, case_sensitive)
    else:
        # Default to bucket matcher
        return _match_with_length_buckets(case_ids, folders, case_sensitive)


def _match_with_ahocorasick(
    case_ids: List[str],
    folders: List[FolderEntry],
    case_sensitive: bool
) -> Dict[str, List[FolderEntry]]:
    """
    Match using Aho-Corasick automaton for efficient multi-pattern matching.

    This is optimal for matching many patterns against many texts.
    Time complexity: O(total_folder_name_length + total_pattern_length + matches)
    """
    logger.debug("Using Aho-Corasick matching algorithm")

    # Build automaton with all CaseIDs
    automaton = ahocorasick.Automaton()

    # Map normalized patterns back to original CaseIDs
    pattern_to_caseids: Dict[str, List[str]] = defaultdict(list)

    for case_id in case_ids:
        pattern = case_id if case_sensitive else case_id.lower()
        pattern_to_caseids[pattern].append(case_id)
        automaton.add_word(pattern, pattern)

    automaton.make_automaton()

    # Initialize results
    results: Dict[str, List[FolderEntry]] = {cid: [] for cid in case_ids}

    # Match each folder name
    match_count = 0
    for folder in folders:
        folder_name = folder.name if case_sensitive else folder.name.lower()

        # Find all patterns that match in this folder name
        matched_patterns = set()
        for _, pattern in automaton.iter(folder_name):
            matched_patterns.add(pattern)

        # Map patterns back to original CaseIDs
        for pattern in matched_patterns:
            for case_id in pattern_to_caseids[pattern]:
                results[case_id].append(folder)
                match_count += 1

    logger.info(f"Aho-Corasick matching found {match_count} total matches")
    return results


def _match_with_length_buckets(
    case_ids: List[str],
    folders: List[FolderEntry],
    case_sensitive: bool
) -> Dict[str, List[FolderEntry]]:
    """
    Match using length-bucket optimization.

    Optimization: A CaseID can only be a substring of a folder name if
    len(CaseID) <= len(folder_name). We bucket CaseIDs by length and only
    check CaseIDs that could possibly match.

    Time complexity: O(folders * avg_applicable_caseids * avg_name_length)
    This is much better than O(folders * all_caseids) when CaseIDs vary in length.
    """
    logger.debug("Using length-bucket matching algorithm")

    # Prepare CaseIDs for matching
    if case_sensitive:
        prepared_caseids = [(cid, cid) for cid in case_ids]
    else:
        prepared_caseids = [(cid, cid.lower()) for cid in case_ids]

    # Bucket CaseIDs by length
    # bucket[length] = [(original_caseid, normalized_caseid), ...]
    max_length = max(len(cid) for cid in case_ids) if case_ids else 0
    buckets: List[List[tuple]] = [[] for _ in range(max_length + 1)]

    for original, normalized in prepared_caseids:
        buckets[len(normalized)].append((original, normalized))

    # Build cumulative buckets: all CaseIDs of length <= N
    # This lets us quickly get all applicable CaseIDs for a given folder name length
    cumulative: List[List[tuple]] = []
    running = []
    for bucket in buckets:
        running = running + bucket
        cumulative.append(running.copy())

    # Initialize results
    results: Dict[str, List[FolderEntry]] = {cid: [] for cid in case_ids}

    # Match each folder
    match_count = 0
    for folder in folders:
        folder_name = folder.name if case_sensitive else folder.name.lower()
        name_len = len(folder_name)

        # Only check CaseIDs that could fit in this folder name
        # A CaseID of length L can match if L <= name_len
        if name_len == 0:
            applicable = []
        elif name_len > max_length:
            applicable = cumulative[max_length] if max_length < len(cumulative) else []
        else:
            applicable = cumulative[name_len] if name_len < len(cumulative) else []

        # Check each applicable CaseID
        for original, normalized in applicable:
            if normalized in folder_name:
                results[original].append(folder)
                match_count += 1

    logger.info(f"Length-bucket matching found {match_count} total matches")
    return results


class FolderIndexer:
    """
    High-level interface for folder scanning and CaseID matching.

    This class provides a convenient wrapper around scan_folders() and
    match_caseids() for use in the CLI and other modules.
    """

    def __init__(
        self,
        source_root: Union[str, Path],
        case_sensitive: bool = False,
        matcher: MatcherType = "bucket"
    ):
        """
        Initialize the indexer with a source root directory.

        Args:
            source_root: The root directory to scan for folders
            case_sensitive: Whether CaseID matching is case-sensitive
            matcher: Matching algorithm to use ("bucket" or "aho")
        """
        self.source_root = Path(source_root)
        self.case_sensitive = case_sensitive
        self.matcher = matcher
        self._folders: Optional[List[FolderEntry]] = None

    def build_index(self) -> int:
        """
        Scan the source root and build the folder index.

        Returns:
            Number of folders indexed
        """
        self._folders = scan_folders(self.source_root)
        return len(self._folders)

    @property
    def folders(self) -> List[FolderEntry]:
        """Get the list of indexed folders. Builds index if not already done."""
        if self._folders is None:
            self.build_index()
        return self._folders

    def find_matches(self, case_id: str) -> List[FolderMatch]:
        """
        Find all folders whose names contain the given CaseID.

        Args:
            case_id: The CaseID to search for

        Returns:
            List of FolderMatch objects for matching folders
        """
        results = match_caseids(
            [case_id],
            self.folders,
            self.case_sensitive,
            self.matcher
        )

        return [
            FolderMatch(
                case_id=case_id,
                source_path=folder.path,
                folder_name=folder.name
            )
            for folder in results.get(case_id, [])
        ]

    def find_all_matches(
        self,
        case_ids: List[str]
    ) -> Dict[str, List[FolderMatch]]:
        """
        Find matches for multiple CaseIDs efficiently.

        Args:
            case_ids: List of CaseIDs to search for

        Returns:
            Dictionary mapping CaseID to list of FolderMatch objects
        """
        results = match_caseids(
            case_ids,
            self.folders,
            self.case_sensitive,
            self.matcher
        )

        return {
            case_id: [
                FolderMatch(
                    case_id=case_id,
                    source_path=folder.path,
                    folder_name=folder.name
                )
                for folder in folders
            ]
            for case_id, folders in results.items()
        }
