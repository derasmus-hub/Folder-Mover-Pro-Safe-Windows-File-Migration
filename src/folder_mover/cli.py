"""
Command-line interface for the folder mover application.

This module is responsible for:
- Parsing command-line arguments using argparse
- Configuring logging based on verbosity level
- Orchestrating the overall workflow
- Displaying progress and results to the user
"""

import argparse
import csv
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set

from . import __version__, PRODUCT_NAME, PRODUCT_DESCRIPTION
from .excel import load_case_ids
from .indexer import (
    FolderIndexer,
    HAS_AHOCORASICK,
    MatcherNotAvailableError,
    match_caseids,
    scan_folders,
)
from .mover import FolderMover
from .report import ReportWriter
from .types import FolderMatch, MoveStatus

logger = logging.getLogger(__name__)

# Status values in CSV reports that indicate a successful move
MOVED_STATUSES = {"MOVED", "MOVED_RENAMED"}


def load_moved_paths_from_report(report_path: Path) -> Set[str]:
    """
    Load source paths that were successfully moved in a previous run.

    This enables resume functionality - if a run is interrupted, the user
    can re-run with --resume-from-report to skip already-moved folders.

    Args:
        report_path: Path to a previous CSV report

    Returns:
        Set of source paths that had status MOVED or MOVED_RENAMED

    Raises:
        FileNotFoundError: If the report file doesn't exist
        ValueError: If the report is missing required columns
    """
    if not report_path.exists():
        raise FileNotFoundError(f"Resume report not found: {report_path}")

    moved_paths: Set[str] = set()

    logger.info(f"Loading moved paths from resume report: {report_path}")

    with open(report_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        # Validate required columns
        required_cols = {"status", "source_path"}
        if reader.fieldnames is None:
            raise ValueError(f"Resume report is empty or invalid: {report_path}")

        actual_cols = set(reader.fieldnames)
        missing = required_cols - actual_cols
        if missing:
            raise ValueError(
                f"Resume report missing required columns: {missing}. "
                f"Found: {reader.fieldnames}"
            )

        # Collect moved paths
        for row in reader:
            status = row.get("status", "").strip()
            source_path = row.get("source_path", "").strip()

            if status in MOVED_STATUSES and source_path:
                moved_paths.add(source_path)

    logger.info(f"Loaded {len(moved_paths)} already-moved paths from resume report")
    return moved_paths


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        prog="folder-mover",
        description=f"""
{PRODUCT_NAME} - {PRODUCT_DESCRIPTION}

Move folders based on CaseIDs from an Excel file.

Scans SourceRoot for folders whose names contain CaseIDs listed in
Column A of the Excel file. Matched folders are moved directly into
DestRoot (source directory structure is not preserved).
        """.strip(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  %(prog)s caselist.xlsx C:\\Data\\Source C:\\Data\\Dest

  # Preview with dry-run
  %(prog)s caselist.xlsx C:\\Data\\Source C:\\Data\\Dest --dry-run

  # Generate report
  %(prog)s caselist.xlsx C:\\Data\\Source C:\\Data\\Dest --report moves.csv

  # Safe test run (move only 1 folder)
  %(prog)s caselist.xlsx C:\\Data\\Source C:\\Data\\Dest --max-moves 1

  # Exclude temp and backup folders
  %(prog)s caselist.xlsx C:\\Data\\Source C:\\Data\\Dest --exclude-pattern "*.tmp" --exclude-pattern "*_backup"

  # Skip existing instead of renaming
  %(prog)s caselist.xlsx C:\\Data\\Source C:\\Data\\Dest --on-dest-exists skip

  # Resume from a previous interrupted run
  %(prog)s caselist.xlsx C:\\Data\\Source C:\\Data\\Dest --resume-from-report prev_report.csv

  # Verbose with all options
  %(prog)s caselist.xlsx C:\\Data\\Source C:\\Data\\Dest -v --dry-run --report out.csv

Notes:
  - CaseIDs are read as strings to preserve leading zeros
  - Name collisions are handled by appending _1, _2, etc. (use --on-dest-exists skip to skip instead)
  - Use --dry-run to preview operations without making changes
  - Use --max-moves for incremental/safe testing
  - Use --exclude-pattern to skip folders matching glob patterns or substrings
  - Use --resume-from-report to continue after an interrupted run
        """
    )

    # Positional arguments
    parser.add_argument(
        "excel_file",
        type=Path,
        help="Path to Excel XLSX file with CaseIDs in Column A"
    )
    parser.add_argument(
        "source_root",
        type=Path,
        help="Root directory to search for matching folders"
    )
    parser.add_argument(
        "dest_root",
        type=Path,
        help="Destination directory where matched folders will be moved"
    )

    # Dry run options
    parser.add_argument(
        "-n", "--dry-run", "--whatif",
        action="store_true",
        dest="dry_run",
        help="Preview operations without actually moving folders"
    )

    # Report options
    parser.add_argument(
        "-r", "--report",
        type=Path,
        default=None,
        metavar="CSV_FILE",
        help="Path for CSV report (default: report_YYYYMMDD_HHMMSS.csv)"
    )

    # Excel options
    parser.add_argument(
        "-s", "--sheet",
        type=str,
        default=None,
        metavar="NAME",
        help="Excel sheet name to read (default: active sheet)"
    )

    # Confirmation
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip confirmation prompt (use with caution)"
    )

    # Limiting options for testing
    parser.add_argument(
        "--max-folders",
        type=int,
        default=None,
        metavar="N",
        help="Limit folder scan to first N folders (for testing)"
    )
    parser.add_argument(
        "--max-moves",
        type=int,
        default=None,
        metavar="N",
        help="Limit to first N move operations (for safe testing)"
    )
    parser.add_argument(
        "--caseid-limit",
        type=int,
        default=None,
        metavar="N",
        help="Only process first N CaseIDs from Excel (for testing)"
    )

    # Matching algorithm
    parser.add_argument(
        "--matcher",
        type=str,
        choices=["bucket", "aho"],
        default="bucket",
        metavar="ALGO",
        help="Matching algorithm: 'bucket' (default) or 'aho' (requires pyahocorasick)"
    )

    # Safety features
    parser.add_argument(
        "--exclude-pattern",
        type=str,
        action="append",
        default=[],
        dest="exclude_patterns",
        metavar="PATTERN",
        help="Exclude folders matching pattern (glob or substring). Can be specified multiple times."
    )
    parser.add_argument(
        "--on-dest-exists",
        type=str,
        choices=["rename", "skip"],
        default="rename",
        dest="on_dest_exists",
        metavar="ACTION",
        help="Action when destination exists: 'rename' (add _1, _2, default) or 'skip'"
    )
    parser.add_argument(
        "--resume-from-report",
        type=Path,
        default=None,
        dest="resume_report",
        metavar="CSV",
        help="Resume from a previous report, skipping folders already moved (MOVED/MOVED_RENAMED status)"
    )

    # Verbosity
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase output verbosity (-v for INFO, -vv for DEBUG)"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=__version__
    )

    return parser


def setup_logging(verbosity: int) -> None:
    """Configure logging based on verbosity level."""
    if verbosity >= 2:
        level = logging.DEBUG
    elif verbosity >= 1:
        level = logging.INFO
    else:
        level = logging.WARNING

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )


def validate_paths(args: argparse.Namespace) -> bool:
    """Validate that required paths exist."""
    errors = []

    if not args.excel_file.exists():
        errors.append(f"Excel file not found: {args.excel_file}")

    if not args.source_root.exists():
        errors.append(f"Source root not found: {args.source_root}")
    elif not args.source_root.is_dir():
        errors.append(f"Source root is not a directory: {args.source_root}")

    if not args.dest_root.exists():
        errors.append(f"Destination root not found: {args.dest_root}")
    elif not args.dest_root.is_dir():
        errors.append(f"Destination root is not a directory: {args.dest_root}")

    for error in errors:
        logger.error(error)
        print(f"Error: {error}", file=sys.stderr)

    return len(errors) == 0


def get_default_report_path() -> Path:
    """Generate default report path with timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(f"report_{timestamp}.csv")


def get_run_parameters(args: argparse.Namespace) -> Dict[str, str]:
    """
    Get run parameters as a dictionary for traceability.

    Args:
        args: Parsed command-line arguments

    Returns:
        Dictionary of parameter names to values
    """
    params = {
        "version": __version__,
        "timestamp": datetime.now().isoformat(),
        "excel_file": str(args.excel_file.resolve()),
        "source_root": str(args.source_root.resolve()),
        "dest_root": str(args.dest_root.resolve()),
        "dry_run": str(args.dry_run),
        "report": str(args.report.resolve()) if args.report else "",
        "sheet": args.sheet or "(active)",
        "matcher": args.matcher,
        "max_folders": str(args.max_folders) if args.max_folders else "",
        "max_moves": str(args.max_moves) if args.max_moves else "",
        "caseid_limit": str(args.caseid_limit) if args.caseid_limit else "",
        "exclude_patterns": ",".join(args.exclude_patterns) if args.exclude_patterns else "",
        "on_dest_exists": args.on_dest_exists,
        "resume_report": str(args.resume_report.resolve()) if args.resume_report else "",
    }
    return params


def confirm_operation(total_matches: int, dest_root: Path) -> bool:
    """
    Prompt user to confirm the move operation.

    Args:
        total_matches: Number of folders to be moved
        dest_root: Destination directory

    Returns:
        True if user confirms, False otherwise
    """
    print(f"\n{'!'*60}")
    print("CONFIRMATION REQUIRED")
    print(f"{'!'*60}")
    print(f"\nYou are about to MOVE {total_matches} folder(s) to:")
    print(f"  {dest_root}")
    print("\nThis operation cannot be easily undone.")
    print("Use --dry-run to preview changes first.")
    print(f"{'!'*60}\n")

    try:
        response = input("Type 'yes' to proceed, or anything else to cancel: ")
        return response.strip().lower() == "yes"
    except EOFError:
        # Non-interactive environment
        return False


def print_banner(args: argparse.Namespace) -> None:
    """Print startup banner with configuration."""
    print(f"\n{'='*60}")
    print(f"{PRODUCT_NAME}")
    print(f"Version {__version__}")
    print(f"{PRODUCT_DESCRIPTION}")
    print(f"{'='*60}")
    print(f"Excel file:   {args.excel_file}")
    print(f"Source root:  {args.source_root}")
    print(f"Dest root:    {args.dest_root}")

    if args.dry_run:
        print(f"Mode:         DRY RUN (no changes will be made)")
    else:
        print(f"Mode:         LIVE (folders will be moved)")

    if args.report:
        print(f"Report:       {args.report}")

    # Show limits if set
    limits = []
    if args.caseid_limit:
        limits.append(f"CaseIDs: {args.caseid_limit}")
    if args.max_folders:
        limits.append(f"Folders: {args.max_folders}")
    if args.max_moves:
        limits.append(f"Moves: {args.max_moves}")
    if limits:
        print(f"Limits:       {', '.join(limits)}")

    # Show safety features
    if args.exclude_patterns:
        print(f"Exclusions:   {', '.join(args.exclude_patterns)}")
    if args.on_dest_exists != "rename":
        print(f"On exists:    {args.on_dest_exists}")
    if args.resume_report:
        print(f"Resume from:  {args.resume_report}")

    print(f"{'='*60}\n")


def print_summary(
    total_caseids: int,
    total_folders: int,
    match_counts: Dict[str, int],
    not_found: List[str],
    move_stats: Dict[str, int],
    dry_run: bool
) -> None:
    """Print final summary of operations."""
    total_matches = sum(match_counts.values())
    caseids_with_matches = sum(1 for count in match_counts.values() if count > 0)
    multi_match_count = sum(1 for count in match_counts.values() if count > 1)

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    print(f"\nInput:")
    print(f"  CaseIDs loaded:        {total_caseids}")
    print(f"  Folders scanned:       {total_folders}")

    print(f"\nMatching:")
    print(f"  CaseIDs with matches:  {caseids_with_matches}")
    print(f"  CaseIDs not found:     {len(not_found)}")
    print(f"  Total folder matches:  {total_matches}")
    if multi_match_count:
        print(f"  CaseIDs with multiple: {multi_match_count}")

    print(f"\nOperations:")
    if dry_run:
        dry_count = move_stats.get("dry_run", 0) + move_stats.get("dry_run_renamed", 0)
        print(f"  Would move:            {dry_count}")
        if move_stats.get("dry_run_renamed", 0):
            print(f"    (with rename:        {move_stats.get('dry_run_renamed', 0)})")
    else:
        moved = move_stats.get("success", 0) + move_stats.get("success_renamed", 0)
        print(f"  Moved:                 {moved}")
        if move_stats.get("success_renamed", 0):
            print(f"    (with rename:        {move_stats.get('success_renamed', 0)})")

    skipped = (
        move_stats.get("skipped_missing", 0) +
        move_stats.get("skipped_exists", 0) +
        move_stats.get("skipped_excluded", 0) +
        move_stats.get("skipped_resume", 0)
    )
    if skipped:
        print(f"  Skipped:               {skipped}")
        if move_stats.get("skipped_missing", 0):
            print(f"    (source missing:     {move_stats.get('skipped_missing', 0)})")
        if move_stats.get("skipped_exists", 0):
            print(f"    (already exists:     {move_stats.get('skipped_exists', 0)})")
        if move_stats.get("skipped_excluded", 0):
            print(f"    (excluded:           {move_stats.get('skipped_excluded', 0)})")
        if move_stats.get("skipped_resume", 0):
            print(f"    (resume skip:        {move_stats.get('skipped_resume', 0)})")

    errors = move_stats.get("error", 0)
    if errors:
        print(f"  Errors:                {errors}")

    print(f"{'='*60}\n")


def main(argv: list = None) -> int:
    """
    Main entry point for the CLI.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    parser = create_parser()
    args = parser.parse_args(argv)

    setup_logging(args.verbose)

    logger.info(f"{PRODUCT_NAME} v{__version__}")
    logger.debug(f"Arguments: {args}")

    # Validate paths before proceeding
    if not validate_paths(args):
        return 1

    # Set default report path if report is requested but no path given
    if args.report is None:
        args.report = get_default_report_path()

    # Get and log run parameters for traceability
    run_params = get_run_parameters(args)
    logger.info("Run parameters:")
    for key, value in run_params.items():
        if value:  # Only log non-empty values
            logger.info(f"  {key}: {value}")

    print_banner(args)

    try:
        # Step 1: Load CaseIDs from Excel
        print("Step 1: Loading CaseIDs from Excel...")
        case_ids = load_case_ids(args.excel_file, args.sheet)

        # Apply caseid limit if set
        if args.caseid_limit and len(case_ids) > args.caseid_limit:
            print(f"  Limiting to first {args.caseid_limit} CaseIDs")
            case_ids = case_ids[:args.caseid_limit]

        print(f"  Loaded {len(case_ids)} unique CaseIDs")

        # Step 2: Scan folders
        print("\nStep 2: Scanning source folders...")
        folders = scan_folders(args.source_root)

        # Apply max_folders limit if set
        if args.max_folders and len(folders) > args.max_folders:
            print(f"  Limiting to first {args.max_folders} folders")
            folders = folders[:args.max_folders]

        print(f"  Found {len(folders)} folders")

        # Step 3: Match CaseIDs to folders
        matcher_str = args.matcher
        if args.matcher == "aho" and HAS_AHOCORASICK:
            matcher_str = "aho (Aho-Corasick)"
        elif args.matcher == "bucket":
            matcher_str = "bucket (length-bucket)"
        print(f"\nStep 3: Matching CaseIDs to folders using {matcher_str} matcher...")
        matches_by_caseid = match_caseids(case_ids, folders, matcher=args.matcher)

        # Count matches per CaseID
        match_counts = {cid: len(matches) for cid, matches in matches_by_caseid.items()}
        total_matches = sum(match_counts.values())

        # Find CaseIDs with no matches
        not_found = [cid for cid, count in match_counts.items() if count == 0]

        print(f"  Total matches: {total_matches}")
        print(f"  CaseIDs with no matches: {len(not_found)}")

        # Build list of all matches as FolderMatch objects
        all_matches: List[FolderMatch] = []
        for case_id, folder_entries in matches_by_caseid.items():
            for folder in folder_entries:
                all_matches.append(FolderMatch(
                    case_id=case_id,
                    source_path=folder.path,
                    folder_name=folder.name
                ))

        # Confirmation prompt for live mode
        if not args.dry_run and len(all_matches) > 0:
            if not args.yes:
                if not confirm_operation(len(all_matches), args.dest_root):
                    print("\nOperation cancelled by user.")
                    logger.info("Operation cancelled by user at confirmation prompt")
                    return 0
            else:
                logger.info("Confirmation skipped (--yes flag)")

        # Load resume data if resuming from previous report
        already_moved: Set[str] = set()
        if args.resume_report:
            print(f"\nLoading resume data from {args.resume_report}...")
            already_moved = load_moved_paths_from_report(args.resume_report)
            print(f"  Found {len(already_moved)} already-moved folders to skip")

        # Step 4: Move folders (or dry-run)
        mode_str = "DRY RUN" if args.dry_run else "Moving"
        print(f"\nStep 4: {mode_str} {len(all_matches)} folders...")

        mover = FolderMover(
            dest_root=args.dest_root,
            dry_run=args.dry_run,
            max_moves=args.max_moves,
            exclude_patterns=args.exclude_patterns,
            on_dest_exists=args.on_dest_exists,
            already_moved_paths=already_moved
        )

        results = mover.move_all(all_matches)
        move_stats = mover.get_stats()

        if args.dry_run:
            dry_count = move_stats.get("dry_run", 0) + move_stats.get("dry_run_renamed", 0)
            print(f"  Would move: {dry_count} folders")
        else:
            moved = move_stats.get("success", 0) + move_stats.get("success_renamed", 0)
            print(f"  Moved: {moved} folders")

        # Step 5: Generate report
        print(f"\nStep 5: Writing report to {args.report}...")

        with ReportWriter(args.report) as writer:
            # Write run parameters for traceability
            writer.write_parameters(run_params)

            # Write move results
            for result in results:
                is_multiple = match_counts.get(result.case_id, 1) > 1
                writer.write_move_result(result, is_multiple)

            # Write NOT_FOUND entries
            for case_id in not_found:
                writer.write_not_found(case_id)

            print(f"  Wrote {writer.get_row_count()} entries")

        # Print final summary
        print_summary(
            total_caseids=len(case_ids),
            total_folders=len(folders),
            match_counts=match_counts,
            not_found=not_found,
            move_stats=move_stats,
            dry_run=args.dry_run
        )

        print(f"Report saved to: {args.report}")

        # Return error code if there were errors
        if move_stats.get("error", 0) > 0:
            return 2

        return 0

    except FileNotFoundError as e:
        print(f"\nError: {e}", file=sys.stderr)
        logger.error(f"File not found: {e}")
        return 1

    except ValueError as e:
        print(f"\nError: {e}", file=sys.stderr)
        logger.error(f"Value error: {e}")
        return 1

    except MatcherNotAvailableError as e:
        print(f"\nError: {e}", file=sys.stderr)
        logger.error(f"Matcher not available: {e}")
        return 1

    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.", file=sys.stderr)
        return 130

    except Exception as e:
        print(f"\nUnexpected error: {e}", file=sys.stderr)
        logger.exception("Unexpected error")
        return 1


if __name__ == "__main__":
    sys.exit(main())
