"""
CSV report generator for documenting move operations.

This module is responsible for:
- Creating detailed CSV reports of all operations
- Streaming writes to keep memory low
- Recording timestamps, paths, and status for each operation
- Tracking NOT_FOUND CaseIDs and MULTIPLE_MATCHES
- Generating summary statistics
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, TextIO, Union

from .types import MoveResult, MoveStatus, ReportEntry, ReportStatus

logger = logging.getLogger(__name__)

# CSV column headers in order
REPORT_COLUMNS = [
    "timestamp",
    "case_id",
    "status",
    "source_path",
    "dest_path",
    "message",
]


class ReportWriter:
    """
    Streaming CSV report writer for move operations.

    Writes entries incrementally to keep memory usage low,
    suitable for processing hundreds of thousands of folders.
    """

    def __init__(
        self,
        report_path: Union[str, Path],
        include_header: bool = True
    ):
        """
        Initialize the report writer.

        Args:
            report_path: Path where the CSV report will be written
            include_header: Whether to write header row (default: True)
        """
        self.report_path = Path(report_path)
        self.include_header = include_header

        self._file: Optional[TextIO] = None
        self._writer: Optional[csv.writer] = None
        self._row_count = 0
        self._stats: Dict[str, int] = {}
        self._started = False

    def __enter__(self):
        """Context manager entry - opens the file."""
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - closes the file."""
        self.close()
        return False

    def open(self) -> None:
        """Open the report file for writing."""
        if self._file is not None:
            return  # Already open

        # Ensure parent directory exists
        self.report_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Opening report file: {self.report_path}")
        self._file = open(self.report_path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file, quoting=csv.QUOTE_MINIMAL)

        if self.include_header:
            self._writer.writerow(REPORT_COLUMNS)

        self._started = True

    def close(self) -> None:
        """Close the report file."""
        if self._file is not None:
            self._file.close()
            self._file = None
            self._writer = None
            logger.info(
                f"Report closed: {self._row_count} rows written to {self.report_path}"
            )

    def write_parameters(self, params: Dict[str, str]) -> None:
        """
        Write run parameters as comment rows at the start of the report.

        This provides traceability by recording the exact parameters used.
        Parameters are written as rows with status "PARAMETER".

        Args:
            params: Dictionary of parameter names to values
        """
        self._ensure_open()

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for key, value in params.items():
            if value:  # Only write non-empty values
                row = [
                    timestamp,
                    "",  # case_id
                    "PARAMETER",
                    "",  # source_path
                    "",  # dest_path
                    f"{key}={value}",
                ]
                self._writer.writerow(row)
                self._row_count += 1

        # Add separator row
        row = [
            timestamp,
            "",
            "PARAMETER",
            "",
            "",
            "--- END PARAMETERS ---",
        ]
        self._writer.writerow(row)
        self._row_count += 1
        self._file.flush()

    def _ensure_open(self) -> None:
        """Ensure file is open, open if not."""
        if self._file is None:
            self.open()

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _update_stats(self, status: str) -> None:
        """Update statistics counter for a status."""
        self._stats[status] = self._stats.get(status, 0) + 1

    def write_entry(self, entry: ReportEntry) -> None:
        """
        Write a single report entry to the CSV.

        Args:
            entry: The ReportEntry to write
        """
        self._ensure_open()

        row = [
            entry.timestamp,
            entry.case_id,
            entry.status,
            entry.source_path,
            entry.dest_path,
            entry.message,
        ]
        self._writer.writerow(row)
        self._row_count += 1
        self._update_stats(entry.status)

        # Flush periodically for safety
        if self._row_count % 100 == 0:
            self._file.flush()

    def write_move_result(
        self,
        result: MoveResult,
        is_multiple_match: bool = False,
        timestamp: Optional[str] = None
    ) -> None:
        """
        Write a MoveResult to the report.

        Args:
            result: The MoveResult to record
            is_multiple_match: Whether this CaseID matched multiple folders
            timestamp: Optional timestamp (defaults to current time)
        """
        # Determine report status
        # Quarantine statuses are action-based and should not be overridden
        quarantine_statuses = {
            MoveStatus.QUARANTINED,
            MoveStatus.QUARANTINED_RENAMED,
            MoveStatus.DRY_RUN_QUARANTINE,
            MoveStatus.DRY_RUN_QUARANTINE_RENAMED,
        }

        if result.status in quarantine_statuses:
            # Quarantine actions get their true status; note multiple match in message
            report_status = ReportStatus.from_move_status(result.status)
            if is_multiple_match:
                message = f"[Multiple matches] {result.message}"
            else:
                message = result.message
        elif is_multiple_match:
            # For non-quarantine multiple matches (move-all mode), use MULTIPLE_MATCHES
            report_status = ReportStatus.MULTIPLE_MATCHES
            message = f"[Multiple matches] {result.message}"
        else:
            report_status = ReportStatus.from_move_status(result.status)
            message = result.message

        entry = ReportEntry(
            timestamp=timestamp or self._get_timestamp(),
            case_id=result.case_id,
            status=report_status.value,
            source_path=result.source_path,
            dest_path=result.dest_path or "",
            message=message,
        )
        self.write_entry(entry)

    def write_not_found(
        self,
        case_id: str,
        timestamp: Optional[str] = None
    ) -> None:
        """
        Write a NOT_FOUND entry for a CaseID with no matches.

        Args:
            case_id: The CaseID that had no folder matches
            timestamp: Optional timestamp (defaults to current time)
        """
        entry = ReportEntry(
            timestamp=timestamp or self._get_timestamp(),
            case_id=case_id,
            status=ReportStatus.NOT_FOUND.value,
            source_path="",
            dest_path="",
            message="No matching folders found for this CaseID",
        )
        self.write_entry(entry)

    def write_error(
        self,
        case_id: str,
        error: Exception,
        source_path: str = "",
        timestamp: Optional[str] = None
    ) -> None:
        """
        Write an ERROR entry for an exception.

        Args:
            case_id: The CaseID being processed when error occurred
            error: The exception that was raised
            source_path: Optional source path if known
            timestamp: Optional timestamp (defaults to current time)
        """
        error_type = type(error).__name__
        error_msg = str(error)

        entry = ReportEntry(
            timestamp=timestamp or self._get_timestamp(),
            case_id=case_id,
            status=ReportStatus.ERROR.value,
            source_path=source_path,
            dest_path="",
            message=f"{error_type}: {error_msg}",
        )
        self.write_entry(entry)

    def get_stats(self) -> Dict[str, int]:
        """
        Get statistics about written entries.

        Returns:
            Dictionary mapping status to count
        """
        return dict(self._stats)

    def get_row_count(self) -> int:
        """Get total number of rows written."""
        return self._row_count

    def get_summary(self) -> str:
        """
        Get a human-readable summary of the report.

        Returns:
            Formatted summary string
        """
        lines = [f"Report Summary ({self._row_count} total entries):"]

        # Success counts
        moved = self._stats.get("MOVED", 0) + self._stats.get("MOVED_RENAMED", 0)
        dry_run = (
            self._stats.get("FOUND_DRYRUN", 0) +
            self._stats.get("FOUND_DRYRUN_RENAMED", 0)
        )

        if moved > 0:
            lines.append(f"  Moved: {moved}")
            if self._stats.get("MOVED_RENAMED", 0):
                lines.append(f"    (renamed: {self._stats.get('MOVED_RENAMED', 0)})")

        if dry_run > 0:
            lines.append(f"  Would move (dry run): {dry_run}")
            if self._stats.get("FOUND_DRYRUN_RENAMED", 0):
                lines.append(
                    f"    (would rename: {self._stats.get('FOUND_DRYRUN_RENAMED', 0)})"
                )

        # Multiple matches
        if self._stats.get("MULTIPLE_MATCHES", 0):
            lines.append(f"  Multiple matches: {self._stats.get('MULTIPLE_MATCHES', 0)}")

        # Skipped
        skipped = (
            self._stats.get("SKIPPED_MISSING", 0) +
            self._stats.get("SKIPPED_EXISTS", 0)
        )
        if skipped > 0:
            lines.append(f"  Skipped: {skipped}")
            if self._stats.get("SKIPPED_MISSING", 0):
                lines.append(
                    f"    (source missing: {self._stats.get('SKIPPED_MISSING', 0)})"
                )
            if self._stats.get("SKIPPED_EXISTS", 0):
                lines.append(
                    f"    (already exists: {self._stats.get('SKIPPED_EXISTS', 0)})"
                )

        # Not found
        if self._stats.get("NOT_FOUND", 0):
            lines.append(f"  Not found: {self._stats.get('NOT_FOUND', 0)}")

        # Errors
        if self._stats.get("ERROR", 0):
            lines.append(f"  Errors: {self._stats.get('ERROR', 0)}")

        return "\n".join(lines)


def generate_report(
    results: List[MoveResult],
    not_found_case_ids: List[str],
    report_path: Union[str, Path],
    match_counts: Optional[Dict[str, int]] = None
) -> ReportWriter:
    """
    Generate a complete report from results.

    This is a convenience function for generating a report from
    in-memory results. For streaming, use ReportWriter directly.

    Args:
        results: List of MoveResult objects
        not_found_case_ids: List of CaseIDs with no matches
        report_path: Path for the CSV report
        match_counts: Optional dict of CaseID -> match count for detecting multiples

    Returns:
        The ReportWriter used (for accessing stats)
    """
    match_counts = match_counts or {}

    with ReportWriter(report_path) as writer:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Write move results
        for result in results:
            is_multiple = match_counts.get(result.case_id, 1) > 1
            writer.write_move_result(result, is_multiple, timestamp)

        # Write not found entries
        for case_id in not_found_case_ids:
            writer.write_not_found(case_id, timestamp)

        logger.info(writer.get_summary())
        return writer


# Keep old class name for backwards compatibility
class ReportGenerator(ReportWriter):
    """Alias for ReportWriter (backwards compatibility)."""

    def add_result(self, result: MoveResult) -> None:
        """Add a move result to the report."""
        self.write_move_result(result)

    def write_report(self) -> None:
        """Write is handled automatically; this ensures file is flushed."""
        if self._file:
            self._file.flush()
