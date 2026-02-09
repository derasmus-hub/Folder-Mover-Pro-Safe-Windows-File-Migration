"""
Folder mover for relocating matched folders to the destination.

This module is responsible for:
- Moving folders from source to destination root
- Handling name collisions with _1, _2, etc. suffixes
- Supporting dry-run mode (no actual moves)
- Ensuring idempotency (skip if already moved or source missing)
- Exclusion patterns to skip certain folders
- Resume from previous run to avoid reprocessing
- Catching and recording errors (permissions, locked files, etc.)
- Logging all operations
- Returning detailed results for reporting
"""

import fnmatch
import logging
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Literal, Optional, Set, Union

from .types import FolderMatch, MoveResult, MoveStatus
from .utils import (
    normalize_path,
    safe_move,
    to_extended_length_path,
)

# Type for on_dest_exists behavior
DestExistsBehavior = Literal["rename", "skip"]

# Type for duplicates action
DuplicatesAction = Literal["quarantine", "skip", "move-all"]

# Quarantine folder name
DUPLICATES_FOLDER = "_DUPLICATES"

logger = logging.getLogger(__name__)


@dataclass
class QuarantinedDuplicate:
    """Information about a quarantined duplicate folder."""
    case_id: str
    folder_path: str
    folder_name: str
    last_modified: datetime
    age_days: int


def scan_quarantined_duplicates(
    dest_root: Union[str, Path],
    reference_time: Optional[datetime] = None
) -> List[QuarantinedDuplicate]:
    """
    Scan the _DUPLICATES folder and return information about quarantined folders.

    Args:
        dest_root: The destination root directory containing _DUPLICATES
        reference_time: Reference time for age calculation (default: now)

    Returns:
        List of QuarantinedDuplicate objects sorted by age (oldest first)
    """
    dest_root = Path(dest_root)
    duplicates_dir = dest_root / DUPLICATES_FOLDER

    if not duplicates_dir.exists():
        logger.info(f"No duplicates folder found at {duplicates_dir}")
        return []

    if reference_time is None:
        reference_time = datetime.now()

    results: List[QuarantinedDuplicate] = []

    # Iterate over case_id subdirectories
    for case_id_dir in duplicates_dir.iterdir():
        if not case_id_dir.is_dir():
            continue

        case_id = case_id_dir.name

        # Iterate over folder entries within each case_id
        for folder_entry in case_id_dir.iterdir():
            if not folder_entry.is_dir():
                continue

            try:
                # Get modification time
                stat_info = folder_entry.stat()
                mtime = datetime.fromtimestamp(stat_info.st_mtime)

                # Calculate age in days
                age_delta = reference_time - mtime
                age_days = age_delta.days

                results.append(QuarantinedDuplicate(
                    case_id=case_id,
                    folder_path=str(folder_entry),
                    folder_name=folder_entry.name,
                    last_modified=mtime,
                    age_days=age_days
                ))
            except OSError as e:
                logger.warning(f"Could not stat {folder_entry}: {e}")
                continue

    # Sort by age (oldest first)
    results.sort(key=lambda x: x.age_days, reverse=True)

    logger.info(f"Found {len(results)} quarantined duplicates")
    return results


def matches_exclusion_pattern(folder_name: str, patterns: List[str]) -> Optional[str]:
    """
    Check if a folder name matches any exclusion pattern.

    Patterns can be:
    - Simple substrings: "temp" matches "my_temp_folder"
    - Glob patterns: "*.bak" matches "file.bak", "Case_*_Old" matches "Case_123_Old"

    Args:
        folder_name: The folder name to check
        patterns: List of exclusion patterns

    Returns:
        The matching pattern if found, None otherwise
    """
    if not patterns:
        return None

    folder_lower = folder_name.lower()

    for pattern in patterns:
        pattern_lower = pattern.lower()

        # Try fnmatch first (handles *, ?, [seq])
        if fnmatch.fnmatch(folder_lower, pattern_lower):
            return pattern

        # Also try simple substring match
        if pattern_lower in folder_lower:
            return pattern

    return None


def resolve_destination(
    dest_root: Union[str, Path],
    folder_name: str,
    existing_names: Optional[Set[str]] = None
) -> str:
    """
    Resolve a unique destination path for a folder.

    If the target path already exists (or is in existing_names), appends
    _1, _2, etc. until a unique name is found.

    Args:
        dest_root: The destination root directory
        folder_name: The original folder name to place in dest_root
        existing_names: Optional set of names already claimed in this session
                        (for tracking pending moves in dry-run or batch)

    Returns:
        The full destination path (unique, may have suffix)
    """
    dest_root_str = normalize_path(dest_root)
    dest_root_path = Path(dest_root_str)
    existing_names = existing_names or set()

    def _path_exists(path: Path) -> bool:
        """Check if path exists, using extended-length path on Windows."""
        path_str = str(path)
        if sys.platform == "win32":
            path_str = to_extended_length_path(path_str)
        return os.path.exists(path_str)

    # Try the original name first
    candidate = dest_root_path / folder_name
    if not _path_exists(candidate) and folder_name not in existing_names:
        return str(candidate)

    # Find a unique suffix
    counter = 1
    while True:
        suffixed_name = f"{folder_name}_{counter}"
        candidate = dest_root_path / suffixed_name
        if not _path_exists(candidate) and suffixed_name not in existing_names:
            return str(candidate)
        counter += 1

        # Safety limit to prevent infinite loops
        if counter > 10000:
            raise RuntimeError(
                f"Could not find unique name for '{folder_name}' "
                f"after 10000 attempts"
            )


def move_folder(
    src_path: Union[str, Path],
    dest_path: Union[str, Path],
    dry_run: bool = False,
    action: str = "Moving"
) -> MoveResult:
    """
    Move a single folder from source to destination.

    Handles:
    - Missing source (skips with SKIPPED_MISSING status)
    - Permission errors
    - Cross-volume moves (via shutil.move copy+delete)
    - Long paths on Windows (using \\\\?\\ prefix)
    - UNC paths (\\\\server\\share)

    Args:
        src_path: Source folder path
        dest_path: Destination folder path
        dry_run: If True, simulate the move without performing it

    Returns:
        MoveResult with status and details
    """
    # Normalize paths for consistent handling
    src_str = normalize_path(src_path)
    dest_str = normalize_path(dest_path)

    src_path_obj = Path(src_str)
    dest_path_obj = Path(dest_str)

    # For filesystem checks, use extended-length paths on Windows
    src_check = to_extended_length_path(src_str) if sys.platform == "win32" else src_str
    dest_check = to_extended_length_path(dest_str) if sys.platform == "win32" else dest_str

    # Check if source exists
    if not os.path.exists(src_check):
        logger.info(f"Source missing (already moved?): {src_str}")
        return MoveResult(
            case_id="",  # Will be set by caller
            source_path=src_str,
            dest_path=None,
            status=MoveStatus.SKIPPED_MISSING,
            message="Source folder no longer exists (may have been moved already)"
        )

    # Check if source is a directory
    if not os.path.isdir(src_check):
        logger.error(f"Source is not a directory: {src_str}")
        return MoveResult(
            case_id="",
            source_path=src_str,
            dest_path=None,
            status=MoveStatus.ERROR,
            message="Source path is not a directory"
        )

    # Check if destination already exists
    if os.path.exists(dest_check):
        logger.warning(f"Destination already exists: {dest_str}")
        return MoveResult(
            case_id="",
            source_path=src_str,
            dest_path=dest_str,
            status=MoveStatus.SKIPPED_EXISTS,
            message="Destination already exists"
        )

    # Dry run - just report what would happen
    if dry_run:
        logger.info(f"[DRY RUN] {action}: {src_str} -> {dest_str}")
        return MoveResult(
            case_id="",
            source_path=src_str,
            dest_path=dest_str,
            status=MoveStatus.DRY_RUN,
            message=f"Would move to {dest_str}"
        )

    # Ensure destination parent exists
    dest_parent = dest_path_obj.parent
    dest_parent_check = to_extended_length_path(str(dest_parent)) if sys.platform == "win32" else str(dest_parent)
    try:
        os.makedirs(dest_parent_check, exist_ok=True)
    except OSError as e:
        logger.error(f"Cannot create destination parent {dest_parent}: {e}")
        return MoveResult(
            case_id="",
            source_path=src_str,
            dest_path=dest_str,
            status=MoveStatus.ERROR,
            message=f"Cannot create destination directory: {e}"
        )

    # Perform the actual move using safe_move (handles long paths, cross-volume, etc.)
    logger.info(f"{action}: {src_str} -> {dest_str}")
    success, message = safe_move(src_str, dest_str, use_extended_paths=True)

    if success:
        return MoveResult(
            case_id="",
            source_path=src_str,
            dest_path=dest_str,
            status=MoveStatus.SUCCESS,
            message=message
        )
    else:
        logger.error(f"Move failed: {src_str} -> {dest_str}: {message}")
        return MoveResult(
            case_id="",
            source_path=src_str,
            dest_path=dest_str,
            status=MoveStatus.ERROR,
            message=message
        )


class FolderMover:
    """
    Handles moving folders from source locations to destination root.

    Supports dry-run mode for previewing operations and handles
    naming collisions by appending numeric suffixes.
    """

    def __init__(
        self,
        dest_root: Union[str, Path],
        dry_run: bool = False,
        max_moves: Optional[int] = None,
        exclude_patterns: Optional[List[str]] = None,
        on_dest_exists: DestExistsBehavior = "rename",
        already_moved_paths: Optional[Set[str]] = None,
        duplicates_action: DuplicatesAction = "quarantine",
        duplicate_case_ids: Optional[Set[str]] = None
    ):
        """
        Initialize the mover with destination settings.

        Args:
            dest_root: The destination root directory
            dry_run: If True, simulate moves without actually performing them
            max_moves: Optional limit on number of moves (for safety testing)
            exclude_patterns: List of patterns to exclude (substring or fnmatch)
            on_dest_exists: Behavior when destination exists: "rename" (add suffix)
                           or "skip" (skip the move)
            already_moved_paths: Set of source paths already moved in a previous run
                                (for resume functionality)
            duplicates_action: How to handle CaseIDs with multiple matches:
                              "quarantine" (move to _DUPLICATES/<case_id>/),
                              "skip" (don't move, just report),
                              "move-all" (move all to main dest, old behavior)
            duplicate_case_ids: Set of CaseIDs that have multiple folder matches
        """
        self.dest_root = Path(dest_root)
        self.dry_run = dry_run
        self.max_moves = max_moves
        self.exclude_patterns = exclude_patterns or []
        self.on_dest_exists = on_dest_exists
        self.already_moved_paths = already_moved_paths or set()
        self.duplicates_action = duplicates_action
        self.duplicate_case_ids = duplicate_case_ids or set()

        # Normalize already_moved_paths for consistent comparison
        self._normalized_moved_paths: Set[str] = set()
        for path in self.already_moved_paths:
            try:
                self._normalized_moved_paths.add(normalize_path(path))
            except (OSError, ValueError):
                # Path may no longer exist, keep original
                self._normalized_moved_paths.add(path)

        # Track names we've claimed during this session
        # (prevents collisions between moves in the same batch)
        self._claimed_names: Set[str] = set()

        # Track names claimed per quarantine case_id folder
        self._quarantine_claimed: Dict[str, Set[str]] = {}

        # Statistics
        self._stats: Dict[MoveStatus, int] = {status: 0 for status in MoveStatus}

    def _resolve_quarantine_destination(
        self,
        case_id: str,
        folder_name: str
    ) -> str:
        """
        Resolve destination path for a duplicate folder in quarantine.

        Quarantine path: dest_root/_DUPLICATES/<case_id>/<folder_name>

        Args:
            case_id: The CaseID for grouping
            folder_name: The original folder name

        Returns:
            Full path to quarantine destination (unique, may have suffix)
        """
        quarantine_root = self.dest_root / DUPLICATES_FOLDER / case_id

        # Get or create claimed names set for this case_id
        if case_id not in self._quarantine_claimed:
            self._quarantine_claimed[case_id] = set()

        claimed = self._quarantine_claimed[case_id]

        dest_path = resolve_destination(quarantine_root, folder_name, claimed)

        # Claim the name
        dest_name = Path(dest_path).name
        claimed.add(dest_name)

        return dest_path

    def move_folder(self, match: FolderMatch) -> MoveResult:
        """
        Move a matched folder to the destination root.

        Handles:
        - Exclusion patterns (SKIPPED_EXCLUDED)
        - Resume from previous run (SKIPPED_RESUME)
        - Duplicate CaseIDs based on duplicates_action setting
        - Collisions by appending _1, _2, etc. or skipping based on on_dest_exists
        - Tracks claimed names to prevent collisions within a batch

        Args:
            match: The FolderMatch describing the folder to move

        Returns:
            MoveResult describing the outcome of the operation
        """
        src_path = Path(match.source_path)
        folder_name = match.folder_name
        is_duplicate = match.case_id in self.duplicate_case_ids

        # Check exclusion patterns first
        if self.exclude_patterns:
            matched_pattern = matches_exclusion_pattern(folder_name, self.exclude_patterns)
            if matched_pattern:
                logger.info(f"Excluded by pattern '{matched_pattern}': {folder_name}")
                result = MoveResult(
                    case_id=match.case_id,
                    source_path=match.source_path,
                    dest_path=None,
                    status=MoveStatus.SKIPPED_EXCLUDED,
                    message=f"Excluded by pattern: {matched_pattern}"
                )
                self._stats[result.status] += 1
                return result

        # Check if already processed in a previous run (resume)
        try:
            normalized_src = normalize_path(match.source_path)
        except (OSError, ValueError):
            normalized_src = match.source_path

        if normalized_src in self._normalized_moved_paths or match.source_path in self._normalized_moved_paths:
            logger.info(f"Already processed in previous run: {match.source_path}")
            result = MoveResult(
                case_id=match.case_id,
                source_path=match.source_path,
                dest_path=None,
                status=MoveStatus.SKIPPED_RESUME,
                message="Already processed in previous run (resumed)"
            )
            self._stats[result.status] += 1
            return result

        # Check if source exists before resolving destination
        if not src_path.exists():
            result = MoveResult(
                case_id=match.case_id,
                source_path=match.source_path,
                dest_path=None,
                status=MoveStatus.SKIPPED_MISSING,
                message="Source folder no longer exists (may have been moved already)"
            )
            self._stats[result.status] += 1
            return result

        # Handle duplicates based on duplicates_action
        if is_duplicate and self.duplicates_action == "skip":
            logger.info(f"Skipping duplicate (--duplicates-action=skip): {folder_name} (CaseID: {match.case_id})")
            result = MoveResult(
                case_id=match.case_id,
                source_path=match.source_path,
                dest_path=None,
                status=MoveStatus.SKIPPED_DUPLICATE,
                message=f"Duplicate CaseID skipped (--duplicates-action=skip)"
            )
            self._stats[result.status] += 1
            return result

        if is_duplicate and self.duplicates_action == "quarantine":
            # Move to quarantine folder: dest_root/_DUPLICATES/<case_id>/<folder_name>
            return self._move_to_quarantine(match)

        # Default behavior (move-all) or single match: move to main destination
        # Check if destination with original name already exists
        original_dest = self.dest_root / folder_name
        original_dest_check = to_extended_length_path(str(original_dest)) if sys.platform == "win32" else str(original_dest)
        dest_exists = os.path.exists(original_dest_check) or folder_name in self._claimed_names

        # Handle on_dest_exists behavior
        if dest_exists and self.on_dest_exists == "skip":
            logger.info(f"Destination exists, skipping (--on-dest-exists=skip): {folder_name}")
            result = MoveResult(
                case_id=match.case_id,
                source_path=match.source_path,
                dest_path=str(original_dest),
                status=MoveStatus.SKIPPED_EXISTS,
                message="Destination exists (skipped due to --on-dest-exists=skip)"
            )
            self._stats[result.status] += 1
            return result

        # Resolve unique destination path (will add suffix if needed when on_dest_exists=rename)
        dest_path = resolve_destination(
            self.dest_root,
            folder_name,
            self._claimed_names
        )

        # Claim this name for the session
        dest_name = Path(dest_path).name
        self._claimed_names.add(dest_name)

        # Perform the move
        result = move_folder(src_path, dest_path, self.dry_run)

        # Determine if this was a rename (dest name differs from original folder name)
        was_renamed = dest_name != folder_name

        # Adjust status based on rename
        if result.status == MoveStatus.SUCCESS and was_renamed:
            status = MoveStatus.SUCCESS_RENAMED
            message = f"Moved successfully (renamed from {folder_name} to {dest_name})"
        elif result.status == MoveStatus.DRY_RUN and was_renamed:
            status = MoveStatus.DRY_RUN_RENAMED
            message = f"Would move to {dest_path} (renamed from {folder_name} to {dest_name})"
        else:
            status = result.status
            message = result.message

        # Create final result with case_id
        final_result = MoveResult(
            case_id=match.case_id,
            source_path=result.source_path,
            dest_path=result.dest_path,
            status=status,
            message=message
        )

        self._stats[final_result.status] += 1
        return final_result

    def _move_to_quarantine(self, match: FolderMatch) -> MoveResult:
        """
        Move a duplicate folder to the quarantine directory.

        Quarantine path: dest_root/_DUPLICATES/<case_id>/<folder_name>

        Args:
            match: The FolderMatch describing the folder to move

        Returns:
            MoveResult with quarantine-specific status
        """
        src_path = Path(match.source_path)
        folder_name = match.folder_name

        # Resolve quarantine destination
        dest_path = self._resolve_quarantine_destination(match.case_id, folder_name)
        dest_name = Path(dest_path).name

        # Perform the move (with quarantine-specific logging)
        result = move_folder(src_path, dest_path, self.dry_run, action="Quarantining")

        # Determine if this was a rename
        was_renamed = dest_name != folder_name

        # Map to quarantine-specific statuses
        if result.status == MoveStatus.SUCCESS:
            if was_renamed:
                status = MoveStatus.QUARANTINED_RENAMED
                message = f"Quarantined duplicate (renamed from {folder_name} to {dest_name})"
            else:
                status = MoveStatus.QUARANTINED
                message = f"Quarantined duplicate to {dest_path}"
        elif result.status == MoveStatus.DRY_RUN:
            if was_renamed:
                status = MoveStatus.DRY_RUN_QUARANTINE_RENAMED
                message = f"Would quarantine to {dest_path} (renamed from {folder_name} to {dest_name})"
            else:
                status = MoveStatus.DRY_RUN_QUARANTINE
                message = f"Would quarantine duplicate to {dest_path}"
        else:
            # Pass through other statuses (error, skipped, etc.)
            status = result.status
            message = result.message

        final_result = MoveResult(
            case_id=match.case_id,
            source_path=result.source_path,
            dest_path=result.dest_path,
            status=status,
            message=message
        )

        self._stats[final_result.status] += 1
        return final_result

    def move_all(
        self,
        matches: List[FolderMatch],
        progress_callback=None
    ) -> List[MoveResult]:
        """
        Move all matched folders to the destination root.

        Args:
            matches: List of FolderMatch objects to process
            progress_callback: Optional callable(current, total, match) for progress

        Returns:
            List of MoveResult objects describing each operation
        """
        results: List[MoveResult] = []
        total = len(matches)
        ops_count = 0  # Count actual operations (moves + quarantines)

        # Statuses that count as an operation (actual file system move)
        OP_STATUSES = {
            MoveStatus.SUCCESS,
            MoveStatus.SUCCESS_RENAMED,
            MoveStatus.QUARANTINED,
            MoveStatus.QUARANTINED_RENAMED,
            MoveStatus.DRY_RUN,
            MoveStatus.DRY_RUN_RENAMED,
            MoveStatus.DRY_RUN_QUARANTINE,
            MoveStatus.DRY_RUN_QUARANTINE_RENAMED,
        }

        if self.max_moves is not None:
            logger.info(
                f"Processing up to {self.max_moves} operations from {total} matches "
                f"(--max-moves safety limit)"
            )
        else:
            logger.info(f"Processing {total} folder matches...")

        for i, match in enumerate(matches):
            # Check if we've hit the operation limit
            if self.max_moves is not None and ops_count >= self.max_moves:
                logger.info(
                    f"Reached --max-moves limit ({self.max_moves} ops). "
                    f"Stopping with {total - i} matches remaining."
                )
                break

            if progress_callback:
                progress_callback(i + 1, total, match)

            result = self.move_folder(match)
            results.append(result)

            # Count actual operations (not skips)
            if result.status in OP_STATUSES:
                ops_count += 1

            # Log progress every 100 processed
            if (i + 1) % 100 == 0:
                logger.info(f"Processed {i + 1}/{total} folders ({ops_count} ops)...")

        logger.info(f"Completed: {len(results)} processed, {ops_count} operations performed")
        return results

    def get_stats(self) -> Dict[str, int]:
        """
        Get statistics about move operations.

        Returns:
            Dictionary mapping status names to counts
        """
        return {status.value: count for status, count in self._stats.items()}

    def get_summary(self) -> str:
        """
        Get a human-readable summary of move operations.

        Returns:
            Formatted summary string
        """
        stats = self.get_stats()
        total = sum(stats.values())

        lines = [f"Move Summary ({total} total):"]

        # Group by success/skip/error
        success_count = stats.get("success", 0) + stats.get("success_renamed", 0)
        dry_run_count = stats.get("dry_run", 0) + stats.get("dry_run_renamed", 0)
        quarantine_count = stats.get("quarantined", 0) + stats.get("quarantined_renamed", 0)
        dry_run_quarantine_count = stats.get("dry_run_quarantine", 0) + stats.get("dry_run_quarantine_renamed", 0)
        skipped_count = (
            stats.get("skipped_missing", 0) +
            stats.get("skipped_exists", 0) +
            stats.get("skipped_excluded", 0) +
            stats.get("skipped_resume", 0) +
            stats.get("skipped_duplicate", 0)
        )
        error_count = stats.get("error", 0)

        if self.dry_run:
            lines.append(f"  Would move: {dry_run_count}")
            if stats.get("dry_run_renamed", 0):
                lines.append(
                    f"    (with rename: {stats.get('dry_run_renamed', 0)})"
                )
            if dry_run_quarantine_count:
                lines.append(f"  Would quarantine: {dry_run_quarantine_count}")
                if stats.get("dry_run_quarantine_renamed", 0):
                    lines.append(
                        f"    (with rename: {stats.get('dry_run_quarantine_renamed', 0)})"
                    )
        else:
            lines.append(f"  Moved: {success_count}")
            if stats.get("success_renamed", 0):
                lines.append(
                    f"    (with rename: {stats.get('success_renamed', 0)})"
                )
            if quarantine_count:
                lines.append(f"  Quarantined: {quarantine_count}")
                if stats.get("quarantined_renamed", 0):
                    lines.append(
                        f"    (with rename: {stats.get('quarantined_renamed', 0)})"
                    )

        if skipped_count:
            lines.append(f"  Skipped: {skipped_count}")
            if stats.get("skipped_missing", 0):
                lines.append(
                    f"    (source missing: {stats.get('skipped_missing', 0)})"
                )
            if stats.get("skipped_exists", 0):
                lines.append(
                    f"    (already exists: {stats.get('skipped_exists', 0)})"
                )
            if stats.get("skipped_excluded", 0):
                lines.append(
                    f"    (excluded: {stats.get('skipped_excluded', 0)})"
                )
            if stats.get("skipped_resume", 0):
                lines.append(
                    f"    (resume skip: {stats.get('skipped_resume', 0)})"
                )
            if stats.get("skipped_duplicate", 0):
                lines.append(
                    f"    (duplicate skip: {stats.get('skipped_duplicate', 0)})"
                )

        if error_count:
            lines.append(f"  Errors: {error_count}")

        return "\n".join(lines)

    def reset_stats(self) -> None:
        """Reset statistics and claimed names for a new batch."""
        self._stats = {status: 0 for status in MoveStatus}
        self._claimed_names.clear()
        self._quarantine_claimed.clear()
