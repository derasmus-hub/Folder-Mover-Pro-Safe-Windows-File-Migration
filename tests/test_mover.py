"""
Unit tests for the folder mover.
"""

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from folder_mover.mover import (
    DUPLICATES_FOLDER,
    FolderMover,
    QuarantinedDuplicate,
    matches_exclusion_pattern,
    move_folder,
    resolve_destination,
    scan_quarantined_duplicates,
)
from folder_mover.types import FolderMatch, MoveStatus


class TestResolveDestination:
    """Tests for resolve_destination function."""

    def test_no_collision(self):
        """Returns original path when no collision."""
        with tempfile.TemporaryDirectory() as tmp:
            result = resolve_destination(tmp, "MyFolder")
            assert result == str(Path(tmp) / "MyFolder")

    def test_collision_with_existing_folder(self):
        """Adds suffix when folder already exists."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create existing folder
            (Path(tmp) / "MyFolder").mkdir()

            result = resolve_destination(tmp, "MyFolder")
            assert result == str(Path(tmp) / "MyFolder_1")

    def test_multiple_collisions(self):
        """Increments suffix for multiple collisions."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create existing folders
            (Path(tmp) / "MyFolder").mkdir()
            (Path(tmp) / "MyFolder_1").mkdir()
            (Path(tmp) / "MyFolder_2").mkdir()

            result = resolve_destination(tmp, "MyFolder")
            assert result == str(Path(tmp) / "MyFolder_3")

    def test_collision_with_claimed_names(self):
        """Respects claimed names set."""
        with tempfile.TemporaryDirectory() as tmp:
            claimed = {"MyFolder", "MyFolder_1"}

            result = resolve_destination(tmp, "MyFolder", claimed)
            assert result == str(Path(tmp) / "MyFolder_2")

    def test_mixed_disk_and_claimed_collision(self):
        """Handles both disk and claimed name collisions."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "MyFolder").mkdir()
            (Path(tmp) / "MyFolder_1").mkdir()  # On disk
            claimed = {"MyFolder_2"}  # Claimed in session

            result = resolve_destination(tmp, "MyFolder", claimed)
            assert result == str(Path(tmp) / "MyFolder_3")


class TestMoveFolder:
    """Tests for move_folder function."""

    def test_successful_move(self):
        """Successfully moves folder."""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "source"
            dest = Path(tmp) / "dest"
            src.mkdir()
            (src / "file.txt").write_text("content")

            result = move_folder(src, dest)

            assert result.status == MoveStatus.SUCCESS
            assert not src.exists()
            assert dest.exists()
            assert (dest / "file.txt").read_text() == "content"

    def test_source_missing(self):
        """Reports missing source."""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "nonexistent"
            dest = Path(tmp) / "dest"

            result = move_folder(src, dest)

            assert result.status == MoveStatus.SKIPPED_MISSING
            assert "no longer exists" in result.message

    def test_destination_exists(self):
        """Reports existing destination."""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "source"
            dest = Path(tmp) / "dest"
            src.mkdir()
            dest.mkdir()

            result = move_folder(src, dest)

            assert result.status == MoveStatus.SKIPPED_EXISTS
            assert src.exists()  # Source untouched

    def test_dry_run_no_move(self):
        """Dry run doesn't actually move."""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "source"
            dest = Path(tmp) / "dest"
            src.mkdir()

            result = move_folder(src, dest, dry_run=True)

            assert result.status == MoveStatus.DRY_RUN
            assert src.exists()  # Still there
            assert not dest.exists()  # Not created

    def test_dry_run_different_dest_name(self):
        """Dry run works with different dest name (rename detection in FolderMover)."""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "source"
            dest = Path(tmp) / "dest_different"
            src.mkdir()

            # Low-level move_folder doesn't detect renames - just reports DRY_RUN
            result = move_folder(src, dest, dry_run=True)

            assert result.status == MoveStatus.DRY_RUN
            assert src.exists()  # Still there

    def test_move_with_contents(self):
        """Moves folder with all contents."""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "source"
            src.mkdir()
            (src / "subdir").mkdir()
            (src / "file1.txt").write_text("content1")
            (src / "subdir" / "file2.txt").write_text("content2")

            dest = Path(tmp) / "dest"
            result = move_folder(src, dest)

            assert result.status == MoveStatus.SUCCESS
            assert (dest / "file1.txt").read_text() == "content1"
            assert (dest / "subdir" / "file2.txt").read_text() == "content2"

    def test_source_is_file_error(self):
        """Reports error when source is a file."""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "file.txt"
            src.write_text("content")
            dest = Path(tmp) / "dest"

            result = move_folder(src, dest)

            assert result.status == MoveStatus.ERROR
            assert "not a directory" in result.message


class TestFolderMover:
    """Tests for FolderMover class."""

    def test_move_single_folder(self):
        """Moves a single matched folder."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            src = base / "source" / "Case_00123"
            dest_root = base / "dest"
            src.mkdir(parents=True)
            dest_root.mkdir()

            match = FolderMatch(
                case_id="00123",
                source_path=str(src),
                folder_name="Case_00123"
            )

            mover = FolderMover(dest_root)
            result = mover.move_folder(match)

            assert result.status == MoveStatus.SUCCESS
            assert result.case_id == "00123"
            assert (dest_root / "Case_00123").exists()

    def test_move_with_collision(self):
        """Handles collision by adding suffix."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            src = base / "source" / "Case_00123"
            dest_root = base / "dest"
            src.mkdir(parents=True)
            dest_root.mkdir()
            (dest_root / "Case_00123").mkdir()  # Create collision

            match = FolderMatch(
                case_id="00123",
                source_path=str(src),
                folder_name="Case_00123"
            )

            mover = FolderMover(dest_root)
            result = mover.move_folder(match)

            assert result.status == MoveStatus.SUCCESS_RENAMED
            assert (dest_root / "Case_00123_1").exists()

    def test_move_all_basic(self):
        """Moves multiple folders."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            src_root = base / "source"
            dest_root = base / "dest"
            src_root.mkdir()
            dest_root.mkdir()

            # Create source folders
            (src_root / "Case_001").mkdir()
            (src_root / "Case_002").mkdir()

            matches = [
                FolderMatch("001", str(src_root / "Case_001"), "Case_001"),
                FolderMatch("002", str(src_root / "Case_002"), "Case_002"),
            ]

            mover = FolderMover(dest_root)
            results = mover.move_all(matches)

            assert len(results) == 2
            assert all(r.status == MoveStatus.SUCCESS for r in results)
            assert (dest_root / "Case_001").exists()
            assert (dest_root / "Case_002").exists()

    def test_move_all_with_batch_collision(self):
        """Handles collisions between items in same batch."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            # Create two source folders with same name in different locations
            src1 = base / "loc1" / "SameName"
            src2 = base / "loc2" / "SameName"
            src1.mkdir(parents=True)
            src2.mkdir(parents=True)

            matches = [
                FolderMatch("001", str(src1), "SameName"),
                FolderMatch("002", str(src2), "SameName"),
            ]

            mover = FolderMover(dest_root)
            results = mover.move_all(matches)

            assert len(results) == 2
            assert results[0].status == MoveStatus.SUCCESS
            assert results[1].status == MoveStatus.SUCCESS_RENAMED
            assert (dest_root / "SameName").exists()
            assert (dest_root / "SameName_1").exists()

    def test_dry_run_mode(self):
        """Dry run doesn't move anything."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            src = base / "source" / "Case_00123"
            dest_root = base / "dest"
            src.mkdir(parents=True)
            dest_root.mkdir()

            match = FolderMatch("00123", str(src), "Case_00123")

            mover = FolderMover(dest_root, dry_run=True)
            result = mover.move_folder(match)

            assert result.status == MoveStatus.DRY_RUN
            assert src.exists()
            assert not (dest_root / "Case_00123").exists()

    def test_max_moves_limit(self):
        """Respects max_moves limit."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            # Create 5 source folders
            matches = []
            for i in range(5):
                src = base / f"src_{i}" / f"Folder_{i}"
                src.mkdir(parents=True)
                matches.append(FolderMatch(f"{i}", str(src), f"Folder_{i}"))

            mover = FolderMover(dest_root, max_moves=3)
            results = mover.move_all(matches)

            assert len(results) == 3
            assert (dest_root / "Folder_0").exists()
            assert (dest_root / "Folder_1").exists()
            assert (dest_root / "Folder_2").exists()
            assert not (dest_root / "Folder_3").exists()
            assert not (dest_root / "Folder_4").exists()

    def test_get_stats(self):
        """Tracks statistics correctly."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            # One existing (will succeed)
            src1 = base / "src1"
            src1.mkdir()

            # One missing (will skip)
            src2 = base / "src2"  # Don't create

            matches = [
                FolderMatch("001", str(src1), "Folder1"),
                FolderMatch("002", str(src2), "Folder2"),
            ]

            mover = FolderMover(dest_root)
            mover.move_all(matches)

            stats = mover.get_stats()
            assert stats["success"] == 1
            assert stats["skipped_missing"] == 1

    def test_get_summary(self):
        """Generates readable summary."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            src = base / "src"
            src.mkdir()

            match = FolderMatch("001", str(src), "Folder")
            mover = FolderMover(dest_root)
            mover.move_folder(match)

            summary = mover.get_summary()
            assert "Move Summary" in summary
            assert "Moved: 1" in summary

    def test_reset_stats(self):
        """Reset clears stats and claimed names."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            src = base / "src"
            src.mkdir()

            match = FolderMatch("001", str(src), "Folder")
            mover = FolderMover(dest_root)
            mover.move_folder(match)

            assert sum(mover.get_stats().values()) > 0
            assert len(mover._claimed_names) > 0

            mover.reset_stats()

            assert sum(mover.get_stats().values()) == 0
            assert len(mover._claimed_names) == 0


class TestIdempotency:
    """Tests for idempotent behavior."""

    def test_already_moved_skipped(self):
        """Source that no longer exists is skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            dest_root = Path(tmp) / "dest"
            dest_root.mkdir()

            match = FolderMatch(
                case_id="00123",
                source_path="/nonexistent/source/path",
                folder_name="Case_00123"
            )

            mover = FolderMover(dest_root)
            result = mover.move_folder(match)

            assert result.status == MoveStatus.SKIPPED_MISSING

    def test_run_twice_idempotent(self):
        """Running twice on same data is safe."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            src = base / "source" / "Case_00123"
            dest_root = base / "dest"
            src.mkdir(parents=True)
            dest_root.mkdir()

            match = FolderMatch("00123", str(src), "Case_00123")

            # First run - moves the folder
            mover1 = FolderMover(dest_root)
            result1 = mover1.move_folder(match)
            assert result1.status == MoveStatus.SUCCESS

            # Second run - source is gone
            mover2 = FolderMover(dest_root)
            result2 = mover2.move_folder(match)
            assert result2.status == MoveStatus.SKIPPED_MISSING


class TestEdgeCases:
    """Tests for edge cases."""

    def test_special_characters_in_name(self):
        """Handles special characters in folder names."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            # Note: some characters aren't allowed on Windows
            src = base / "Case #123 (2023)"
            dest_root = base / "dest"
            src.mkdir()
            dest_root.mkdir()

            match = FolderMatch("123", str(src), "Case #123 (2023)")
            mover = FolderMover(dest_root)
            result = mover.move_folder(match)

            assert result.status == MoveStatus.SUCCESS

    def test_deeply_nested_source(self):
        """Handles deeply nested source folders."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            # Create deep path
            src = base / "a" / "b" / "c" / "d" / "e" / "Case_001"
            src.mkdir(parents=True)
            dest_root = base / "dest"
            dest_root.mkdir()

            match = FolderMatch("001", str(src), "Case_001")
            mover = FolderMover(dest_root)
            result = mover.move_folder(match)

            assert result.status == MoveStatus.SUCCESS
            assert (dest_root / "Case_001").exists()

    def test_empty_source_folder(self):
        """Handles empty source folder."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            src = base / "EmptyFolder"
            src.mkdir()
            dest_root = base / "dest"
            dest_root.mkdir()

            match = FolderMatch("001", str(src), "EmptyFolder")
            mover = FolderMover(dest_root)
            result = mover.move_folder(match)

            assert result.status == MoveStatus.SUCCESS
            assert (dest_root / "EmptyFolder").exists()

    def test_progress_callback(self):
        """Progress callback is called correctly."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            # Create source folders
            matches = []
            for i in range(3):
                src = base / f"src_{i}"
                src.mkdir()
                matches.append(FolderMatch(f"{i}", str(src), f"Folder_{i}"))

            progress_calls = []

            def callback(current, total, match):
                progress_calls.append((current, total, match.case_id))

            mover = FolderMover(dest_root)
            mover.move_all(matches, progress_callback=callback)

            assert len(progress_calls) == 3
            assert progress_calls[0] == (1, 3, "0")
            assert progress_calls[1] == (2, 3, "1")
            assert progress_calls[2] == (3, 3, "2")


class TestMatchesExclusionPattern:
    """Tests for matches_exclusion_pattern function."""

    def test_no_patterns(self):
        """Returns None when no patterns."""
        assert matches_exclusion_pattern("Folder", []) is None

    def test_exact_match(self):
        """Matches exact folder name."""
        result = matches_exclusion_pattern("temp", ["temp"])
        assert result == "temp"

    def test_substring_match(self):
        """Matches substring."""
        result = matches_exclusion_pattern("my_temp_folder", ["temp"])
        assert result == "temp"

    def test_glob_asterisk(self):
        """Matches glob with asterisk."""
        assert matches_exclusion_pattern("file.bak", ["*.bak"]) == "*.bak"
        assert matches_exclusion_pattern("Case_123_Old", ["*_Old"]) == "*_Old"

    def test_glob_question_mark(self):
        """Matches glob with question mark."""
        assert matches_exclusion_pattern("test1", ["test?"]) == "test?"
        assert matches_exclusion_pattern("test12", ["test?"]) is None  # Too long

    def test_case_insensitive(self):
        """Matching is case-insensitive."""
        assert matches_exclusion_pattern("TEMP", ["temp"]) == "temp"
        assert matches_exclusion_pattern("MyFolder", ["MYFOLDER"]) == "MYFOLDER"
        assert matches_exclusion_pattern("File.BAK", ["*.bak"]) == "*.bak"

    def test_no_match(self):
        """Returns None when no match."""
        assert matches_exclusion_pattern("normal_folder", ["temp", "*.bak"]) is None


class TestExclusionPatterns:
    """Tests for exclusion patterns in FolderMover."""

    def test_exclude_by_substring(self):
        """Excludes folders by substring."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            src = base / "source" / "Case_00123_temp"
            dest_root = base / "dest"
            src.mkdir(parents=True)
            dest_root.mkdir()

            match = FolderMatch("00123", str(src), "Case_00123_temp")
            mover = FolderMover(dest_root, exclude_patterns=["temp"])
            result = mover.move_folder(match)

            assert result.status == MoveStatus.SKIPPED_EXCLUDED
            assert "temp" in result.message
            assert src.exists()  # Not moved

    def test_exclude_by_glob(self):
        """Excludes folders by glob pattern."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            src = base / "source" / "backup.bak"
            dest_root = base / "dest"
            src.mkdir(parents=True)
            dest_root.mkdir()

            match = FolderMatch("001", str(src), "backup.bak")
            mover = FolderMover(dest_root, exclude_patterns=["*.bak"])
            result = mover.move_folder(match)

            assert result.status == MoveStatus.SKIPPED_EXCLUDED
            assert "*.bak" in result.message

    def test_multiple_patterns(self):
        """Tests multiple exclusion patterns."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            # Create matching and non-matching folders
            src1 = base / "temp_folder"
            src2 = base / "backup.bak"
            src3 = base / "normal_folder"
            src1.mkdir()
            src2.mkdir()
            src3.mkdir()

            matches = [
                FolderMatch("001", str(src1), "temp_folder"),
                FolderMatch("002", str(src2), "backup.bak"),
                FolderMatch("003", str(src3), "normal_folder"),
            ]

            mover = FolderMover(dest_root, exclude_patterns=["temp", "*.bak"])
            results = mover.move_all(matches)

            assert results[0].status == MoveStatus.SKIPPED_EXCLUDED
            assert results[1].status == MoveStatus.SKIPPED_EXCLUDED
            assert results[2].status == MoveStatus.SUCCESS

    def test_stats_track_excluded(self):
        """Stats track excluded folders."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            src = base / "temp_folder"
            dest_root = base / "dest"
            src.mkdir()
            dest_root.mkdir()

            match = FolderMatch("001", str(src), "temp_folder")
            mover = FolderMover(dest_root, exclude_patterns=["temp"])
            mover.move_folder(match)

            stats = mover.get_stats()
            assert stats["skipped_excluded"] == 1


class TestOnDestExists:
    """Tests for on_dest_exists behavior."""

    def test_rename_is_default(self):
        """Default behavior is rename."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            src = base / "Case_00123"
            dest_root = base / "dest"
            src.mkdir()
            dest_root.mkdir()
            (dest_root / "Case_00123").mkdir()  # Collision

            match = FolderMatch("00123", str(src), "Case_00123")
            mover = FolderMover(dest_root)  # Default on_dest_exists="rename"
            result = mover.move_folder(match)

            assert result.status == MoveStatus.SUCCESS_RENAMED
            assert (dest_root / "Case_00123_1").exists()

    def test_skip_on_exists(self):
        """Skip when destination exists with on_dest_exists='skip'."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            src = base / "Case_00123"
            dest_root = base / "dest"
            src.mkdir()
            dest_root.mkdir()
            (dest_root / "Case_00123").mkdir()  # Collision

            match = FolderMatch("00123", str(src), "Case_00123")
            mover = FolderMover(dest_root, on_dest_exists="skip")
            result = mover.move_folder(match)

            assert result.status == MoveStatus.SKIPPED_EXISTS
            assert src.exists()  # Not moved
            assert "skip" in result.message.lower()

    def test_skip_respects_claimed_names(self):
        """Skip also respects names claimed in session."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            src1 = base / "loc1" / "SameName"
            src2 = base / "loc2" / "SameName"
            src1.mkdir(parents=True)
            src2.mkdir(parents=True)

            matches = [
                FolderMatch("001", str(src1), "SameName"),
                FolderMatch("002", str(src2), "SameName"),
            ]

            mover = FolderMover(dest_root, on_dest_exists="skip")
            results = mover.move_all(matches)

            assert results[0].status == MoveStatus.SUCCESS
            assert results[1].status == MoveStatus.SKIPPED_EXISTS


class TestResumeFromReport:
    """Tests for resume functionality."""

    def test_skip_already_moved_paths(self):
        """Skips paths that were already moved."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            src = base / "Case_00123"
            dest_root = base / "dest"
            src.mkdir()
            dest_root.mkdir()

            # Pretend this path was already moved in a previous run
            already_moved = {str(src)}

            match = FolderMatch("00123", str(src), "Case_00123")
            mover = FolderMover(dest_root, already_moved_paths=already_moved)
            result = mover.move_folder(match)

            assert result.status == MoveStatus.SKIPPED_RESUME
            assert src.exists()  # Not moved again

    def test_resume_stats_tracked(self):
        """Stats track resumed skips."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            src = base / "Case_00123"
            dest_root = base / "dest"
            src.mkdir()
            dest_root.mkdir()

            already_moved = {str(src)}

            match = FolderMatch("00123", str(src), "Case_00123")
            mover = FolderMover(dest_root, already_moved_paths=already_moved)
            mover.move_folder(match)

            stats = mover.get_stats()
            assert stats["skipped_resume"] == 1

    def test_resume_with_mixed_paths(self):
        """Handles mix of already-moved and new paths."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            src1 = base / "Case_001"
            src2 = base / "Case_002"
            src1.mkdir()
            src2.mkdir()

            already_moved = {str(src1)}  # Only first was moved before

            matches = [
                FolderMatch("001", str(src1), "Case_001"),
                FolderMatch("002", str(src2), "Case_002"),
            ]

            mover = FolderMover(dest_root, already_moved_paths=already_moved)
            results = mover.move_all(matches)

            assert results[0].status == MoveStatus.SKIPPED_RESUME
            assert results[1].status == MoveStatus.SUCCESS


class TestSafetyFeaturesCombined:
    """Tests for combined safety features."""

    def test_exclusion_checked_before_resume(self):
        """Exclusion is checked before resume."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            src = base / "temp_folder"
            dest_root = base / "dest"
            src.mkdir()
            dest_root.mkdir()

            # Both excluded AND in resume set
            already_moved = {str(src)}

            match = FolderMatch("001", str(src), "temp_folder")
            mover = FolderMover(
                dest_root,
                exclude_patterns=["temp"],
                already_moved_paths=already_moved
            )
            result = mover.move_folder(match)

            # Exclusion takes precedence
            assert result.status == MoveStatus.SKIPPED_EXCLUDED

    def test_all_features_together(self):
        """All safety features work together."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            # Create various folders
            excluded_folder = base / "temp_123"
            resumed_folder = base / "Case_001"
            existing_folder = base / "Case_002"
            normal_folder = base / "Case_003"

            excluded_folder.mkdir()
            resumed_folder.mkdir()
            existing_folder.mkdir()
            normal_folder.mkdir()

            # Create existing destination for Case_002
            (dest_root / "Case_002").mkdir()

            already_moved = {str(resumed_folder)}

            matches = [
                FolderMatch("temp", str(excluded_folder), "temp_123"),
                FolderMatch("001", str(resumed_folder), "Case_001"),
                FolderMatch("002", str(existing_folder), "Case_002"),
                FolderMatch("003", str(normal_folder), "Case_003"),
            ]

            mover = FolderMover(
                dest_root,
                exclude_patterns=["temp"],
                on_dest_exists="skip",
                already_moved_paths=already_moved
            )
            results = mover.move_all(matches)

            assert results[0].status == MoveStatus.SKIPPED_EXCLUDED
            assert results[1].status == MoveStatus.SKIPPED_RESUME
            assert results[2].status == MoveStatus.SKIPPED_EXISTS
            assert results[3].status == MoveStatus.SUCCESS


class TestDuplicatesHandling:
    """Tests for duplicate CaseID handling."""

    def test_quarantine_duplicates(self):
        """Quarantine moves duplicates to _DUPLICATES/<case_id>/."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            # Create two folders matching same CaseID
            src1 = base / "loc1" / "Case_00123_A"
            src2 = base / "loc2" / "Case_00123_B"
            src1.mkdir(parents=True)
            src2.mkdir(parents=True)
            (src1 / "file1.txt").write_text("content1")
            (src2 / "file2.txt").write_text("content2")

            matches = [
                FolderMatch("00123", str(src1), "Case_00123_A"),
                FolderMatch("00123", str(src2), "Case_00123_B"),
            ]

            mover = FolderMover(
                dest_root,
                duplicates_action="quarantine",
                duplicate_case_ids={"00123"}
            )
            results = mover.move_all(matches)

            # Both should be quarantined
            assert results[0].status == MoveStatus.QUARANTINED
            assert results[1].status == MoveStatus.QUARANTINED

            # Check quarantine folder structure
            quarantine_dir = dest_root / "_DUPLICATES" / "00123"
            assert quarantine_dir.exists()
            assert (quarantine_dir / "Case_00123_A").exists()
            assert (quarantine_dir / "Case_00123_B").exists()
            assert (quarantine_dir / "Case_00123_A" / "file1.txt").exists()
            assert (quarantine_dir / "Case_00123_B" / "file2.txt").exists()

    def test_quarantine_with_collision(self):
        """Quarantine handles name collisions within quarantine folder."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            # Create folders with same name matching same CaseID
            src1 = base / "loc1" / "Case_00123"
            src2 = base / "loc2" / "Case_00123"
            src1.mkdir(parents=True)
            src2.mkdir(parents=True)

            matches = [
                FolderMatch("00123", str(src1), "Case_00123"),
                FolderMatch("00123", str(src2), "Case_00123"),
            ]

            mover = FolderMover(
                dest_root,
                duplicates_action="quarantine",
                duplicate_case_ids={"00123"}
            )
            results = mover.move_all(matches)

            assert results[0].status == MoveStatus.QUARANTINED
            assert results[1].status == MoveStatus.QUARANTINED_RENAMED

            quarantine_dir = dest_root / "_DUPLICATES" / "00123"
            assert (quarantine_dir / "Case_00123").exists()
            assert (quarantine_dir / "Case_00123_1").exists()

    def test_skip_duplicates(self):
        """Skip duplicates does not move anything."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            src1 = base / "Case_00123_A"
            src2 = base / "Case_00123_B"
            src1.mkdir()
            src2.mkdir()

            matches = [
                FolderMatch("00123", str(src1), "Case_00123_A"),
                FolderMatch("00123", str(src2), "Case_00123_B"),
            ]

            mover = FolderMover(
                dest_root,
                duplicates_action="skip",
                duplicate_case_ids={"00123"}
            )
            results = mover.move_all(matches)

            # Both should be skipped
            assert results[0].status == MoveStatus.SKIPPED_DUPLICATE
            assert results[1].status == MoveStatus.SKIPPED_DUPLICATE

            # Sources should still exist
            assert src1.exists()
            assert src2.exists()

            # Dest should be empty
            assert list(dest_root.iterdir()) == []

    def test_move_all_duplicates(self):
        """Move-all moves duplicates to main destination (old behavior)."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            src1 = base / "Case_00123_A"
            src2 = base / "Case_00123_B"
            src1.mkdir()
            src2.mkdir()

            matches = [
                FolderMatch("00123", str(src1), "Case_00123_A"),
                FolderMatch("00123", str(src2), "Case_00123_B"),
            ]

            mover = FolderMover(
                dest_root,
                duplicates_action="move-all",
                duplicate_case_ids={"00123"}
            )
            results = mover.move_all(matches)

            # Both should be moved to main dest
            assert results[0].status == MoveStatus.SUCCESS
            assert results[1].status == MoveStatus.SUCCESS

            # Check they're in main dest, not quarantine
            assert (dest_root / "Case_00123_A").exists()
            assert (dest_root / "Case_00123_B").exists()
            assert not (dest_root / "_DUPLICATES").exists()

    def test_single_match_not_affected_by_duplicates_action(self):
        """Single matches are not affected by duplicates_action setting."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            src = base / "Case_00123"
            src.mkdir()

            match = FolderMatch("00123", str(src), "Case_00123")

            # Even with quarantine action, single match goes to main dest
            mover = FolderMover(
                dest_root,
                duplicates_action="quarantine",
                duplicate_case_ids=set()  # 00123 is NOT in duplicates
            )
            result = mover.move_folder(match)

            assert result.status == MoveStatus.SUCCESS
            assert (dest_root / "Case_00123").exists()
            assert not (dest_root / "_DUPLICATES").exists()

    def test_quarantine_dry_run(self):
        """Dry run shows correct quarantine destination."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            src1 = base / "Case_00123_A"
            src2 = base / "Case_00123_B"
            src1.mkdir()
            src2.mkdir()

            matches = [
                FolderMatch("00123", str(src1), "Case_00123_A"),
                FolderMatch("00123", str(src2), "Case_00123_B"),
            ]

            mover = FolderMover(
                dest_root,
                dry_run=True,
                duplicates_action="quarantine",
                duplicate_case_ids={"00123"}
            )
            results = mover.move_all(matches)

            assert results[0].status == MoveStatus.DRY_RUN_QUARANTINE
            assert results[1].status == MoveStatus.DRY_RUN_QUARANTINE

            # Sources should still exist
            assert src1.exists()
            assert src2.exists()

            # Quarantine folder should not be created
            assert not (dest_root / "_DUPLICATES").exists()

            # Check dest_path points to quarantine
            assert "_DUPLICATES" in results[0].dest_path
            assert "00123" in results[0].dest_path

    def test_quarantine_stats_tracked(self):
        """Stats track quarantined folders."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            src1 = base / "Case_00123_A"
            src2 = base / "Case_00123"
            src1.mkdir()
            src2.mkdir()

            matches = [
                FolderMatch("00123", str(src1), "Case_00123_A"),
                FolderMatch("00123", str(src2), "Case_00123"),
            ]

            mover = FolderMover(
                dest_root,
                duplicates_action="quarantine",
                duplicate_case_ids={"00123"}
            )

            # Pre-create a collision in quarantine
            quarantine_dir = dest_root / "_DUPLICATES" / "00123" / "Case_00123"
            quarantine_dir.mkdir(parents=True)

            results = mover.move_all(matches)

            stats = mover.get_stats()
            assert stats["quarantined"] == 1
            assert stats["quarantined_renamed"] == 1

    def test_mixed_single_and_duplicate_caseids(self):
        """Correctly handles mix of single and duplicate CaseIDs."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            # Single match CaseID
            src_single = base / "Case_00001"
            src_single.mkdir()

            # Duplicate match CaseID
            src_dup1 = base / "Case_00002_A"
            src_dup2 = base / "Case_00002_B"
            src_dup1.mkdir()
            src_dup2.mkdir()

            matches = [
                FolderMatch("00001", str(src_single), "Case_00001"),
                FolderMatch("00002", str(src_dup1), "Case_00002_A"),
                FolderMatch("00002", str(src_dup2), "Case_00002_B"),
            ]

            mover = FolderMover(
                dest_root,
                duplicates_action="quarantine",
                duplicate_case_ids={"00002"}  # Only 00002 is duplicate
            )
            results = mover.move_all(matches)

            # Single goes to main dest
            assert results[0].status == MoveStatus.SUCCESS
            assert (dest_root / "Case_00001").exists()

            # Duplicates go to quarantine
            assert results[1].status == MoveStatus.QUARANTINED
            assert results[2].status == MoveStatus.QUARANTINED
            quarantine_dir = dest_root / "_DUPLICATES" / "00002"
            assert (quarantine_dir / "Case_00002_A").exists()
            assert (quarantine_dir / "Case_00002_B").exists()


class TestScanQuarantinedDuplicates:
    """Tests for scan_quarantined_duplicates function."""

    def test_no_duplicates_folder(self):
        """Returns empty list when _DUPLICATES folder doesn't exist."""
        with tempfile.TemporaryDirectory() as tmp:
            result = scan_quarantined_duplicates(tmp)
            assert result == []

    def test_empty_duplicates_folder(self):
        """Returns empty list when _DUPLICATES folder is empty."""
        with tempfile.TemporaryDirectory() as tmp:
            duplicates_dir = Path(tmp) / DUPLICATES_FOLDER
            duplicates_dir.mkdir()

            result = scan_quarantined_duplicates(tmp)
            assert result == []

    def test_scans_single_duplicate(self):
        """Scans a single quarantined duplicate folder."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create quarantine structure: _DUPLICATES/00123/Case_00123_A/
            duplicates_dir = Path(tmp) / DUPLICATES_FOLDER
            case_dir = duplicates_dir / "00123"
            folder = case_dir / "Case_00123_A"
            folder.mkdir(parents=True)

            result = scan_quarantined_duplicates(tmp)

            assert len(result) == 1
            assert result[0].case_id == "00123"
            assert result[0].folder_name == "Case_00123_A"
            assert "Case_00123_A" in result[0].folder_path

    def test_scans_multiple_duplicates_same_caseid(self):
        """Scans multiple folders under same CaseID."""
        with tempfile.TemporaryDirectory() as tmp:
            duplicates_dir = Path(tmp) / DUPLICATES_FOLDER
            case_dir = duplicates_dir / "00123"
            (case_dir / "Case_00123_A").mkdir(parents=True)
            (case_dir / "Case_00123_B").mkdir(parents=True)

            result = scan_quarantined_duplicates(tmp)

            assert len(result) == 2
            folder_names = {r.folder_name for r in result}
            assert folder_names == {"Case_00123_A", "Case_00123_B"}

    def test_scans_multiple_caseids(self):
        """Scans folders from multiple CaseIDs."""
        with tempfile.TemporaryDirectory() as tmp:
            duplicates_dir = Path(tmp) / DUPLICATES_FOLDER
            (duplicates_dir / "00123" / "Folder_A").mkdir(parents=True)
            (duplicates_dir / "00456" / "Folder_B").mkdir(parents=True)
            (duplicates_dir / "00789" / "Folder_C").mkdir(parents=True)

            result = scan_quarantined_duplicates(tmp)

            assert len(result) == 3
            case_ids = {r.case_id for r in result}
            assert case_ids == {"00123", "00456", "00789"}

    def test_age_calculation_days(self):
        """Calculates age in days correctly."""
        with tempfile.TemporaryDirectory() as tmp:
            duplicates_dir = Path(tmp) / DUPLICATES_FOLDER
            folder = duplicates_dir / "00123" / "TestFolder"
            folder.mkdir(parents=True)

            # Set modification time to 10 days ago
            ten_days_ago = datetime.now() - timedelta(days=10)
            mtime_timestamp = ten_days_ago.timestamp()
            os.utime(folder, (mtime_timestamp, mtime_timestamp))

            result = scan_quarantined_duplicates(tmp)

            assert len(result) == 1
            # Allow 1 day tolerance for edge cases
            assert 9 <= result[0].age_days <= 11

    def test_age_with_reference_time(self):
        """Uses reference_time for age calculation."""
        with tempfile.TemporaryDirectory() as tmp:
            duplicates_dir = Path(tmp) / DUPLICATES_FOLDER
            folder = duplicates_dir / "00123" / "TestFolder"
            folder.mkdir(parents=True)

            # Set mtime to a known date
            known_date = datetime(2024, 1, 15, 12, 0, 0)
            os.utime(folder, (known_date.timestamp(), known_date.timestamp()))

            # Use reference time 30 days later
            reference = datetime(2024, 2, 14, 12, 0, 0)
            result = scan_quarantined_duplicates(tmp, reference_time=reference)

            assert len(result) == 1
            assert result[0].age_days == 30

    def test_sorted_by_age_oldest_first(self):
        """Results are sorted by age with oldest first."""
        with tempfile.TemporaryDirectory() as tmp:
            duplicates_dir = Path(tmp) / DUPLICATES_FOLDER

            # Create folders with different ages
            folder_old = duplicates_dir / "00001" / "Old"
            folder_mid = duplicates_dir / "00002" / "Mid"
            folder_new = duplicates_dir / "00003" / "New"
            folder_old.mkdir(parents=True)
            folder_mid.mkdir(parents=True)
            folder_new.mkdir(parents=True)

            # Set ages: old=30 days, mid=15 days, new=5 days
            now = datetime.now()
            os.utime(folder_old, ((now - timedelta(days=30)).timestamp(),) * 2)
            os.utime(folder_mid, ((now - timedelta(days=15)).timestamp(),) * 2)
            os.utime(folder_new, ((now - timedelta(days=5)).timestamp(),) * 2)

            result = scan_quarantined_duplicates(tmp)

            assert len(result) == 3
            assert result[0].folder_name == "Old"
            assert result[1].folder_name == "Mid"
            assert result[2].folder_name == "New"

    def test_ignores_files_in_duplicates_folder(self):
        """Ignores files (not directories) in _DUPLICATES."""
        with tempfile.TemporaryDirectory() as tmp:
            duplicates_dir = Path(tmp) / DUPLICATES_FOLDER
            duplicates_dir.mkdir()

            # Create a file instead of a directory
            (duplicates_dir / "some_file.txt").write_text("test")

            # Also create a valid folder
            (duplicates_dir / "00123" / "ValidFolder").mkdir(parents=True)

            result = scan_quarantined_duplicates(tmp)

            assert len(result) == 1
            assert result[0].case_id == "00123"

    def test_ignores_files_in_caseid_folder(self):
        """Ignores files inside CaseID subdirectories."""
        with tempfile.TemporaryDirectory() as tmp:
            duplicates_dir = Path(tmp) / DUPLICATES_FOLDER
            case_dir = duplicates_dir / "00123"
            case_dir.mkdir(parents=True)

            # Create a file instead of a folder
            (case_dir / "some_file.txt").write_text("test")

            # Also create a valid folder
            (case_dir / "ValidFolder").mkdir()

            result = scan_quarantined_duplicates(tmp)

            assert len(result) == 1
            assert result[0].folder_name == "ValidFolder"

    def test_returns_correct_folder_path(self):
        """folder_path contains the full path to the folder."""
        with tempfile.TemporaryDirectory() as tmp:
            duplicates_dir = Path(tmp) / DUPLICATES_FOLDER
            folder = duplicates_dir / "00123" / "MyFolder"
            folder.mkdir(parents=True)

            result = scan_quarantined_duplicates(tmp)

            assert len(result) == 1
            assert result[0].folder_path == str(folder)


class TestMaxMovesAsOperations:
    """Tests for --max-moves counting operations, not list truncation."""

    def test_max_moves_counts_quarantine_as_operation(self):
        """With max_moves=1 and duplicates, exactly 1 quarantine happens, 0 moves."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            # Create two folders matching same duplicate CaseID
            src1 = base / "Case_00123_A"
            src2 = base / "Case_00123_B"
            src1.mkdir()
            src2.mkdir()

            matches = [
                FolderMatch("00123", str(src1), "Case_00123_A"),
                FolderMatch("00123", str(src2), "Case_00123_B"),
            ]

            mover = FolderMover(
                dest_root,
                max_moves=1,
                duplicates_action="quarantine",
                duplicate_case_ids={"00123"}
            )
            results = mover.move_all(matches)

            # Only 1 result because we stopped after 1 operation
            assert len(results) == 1
            assert results[0].status == MoveStatus.QUARANTINED

            # Stats should show 1 quarantine, 0 moves
            stats = mover.get_stats()
            assert stats["quarantined"] == 1
            assert stats["success"] == 0

    def test_max_moves_two_quarantines(self):
        """With max_moves=2 and duplicates, exactly 2 quarantines happen."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            # Create three folders matching same duplicate CaseID
            src1 = base / "Case_00123_A"
            src2 = base / "Case_00123_B"
            src3 = base / "Case_00123_C"
            src1.mkdir()
            src2.mkdir()
            src3.mkdir()

            matches = [
                FolderMatch("00123", str(src1), "Case_00123_A"),
                FolderMatch("00123", str(src2), "Case_00123_B"),
                FolderMatch("00123", str(src3), "Case_00123_C"),
            ]

            mover = FolderMover(
                dest_root,
                max_moves=2,
                duplicates_action="quarantine",
                duplicate_case_ids={"00123"}
            )
            results = mover.move_all(matches)

            # Only 2 results
            assert len(results) == 2
            assert all(r.status == MoveStatus.QUARANTINED for r in results)

            # Third folder should still exist (not processed)
            assert src3.exists()

    def test_max_moves_single_move_no_duplicates(self):
        """With max_moves=1 and no duplicates, exactly 1 move happens."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            # Create three non-duplicate folders
            src1 = base / "Case_001"
            src2 = base / "Case_002"
            src3 = base / "Case_003"
            src1.mkdir()
            src2.mkdir()
            src3.mkdir()

            matches = [
                FolderMatch("001", str(src1), "Case_001"),
                FolderMatch("002", str(src2), "Case_002"),
                FolderMatch("003", str(src3), "Case_003"),
            ]

            mover = FolderMover(
                dest_root,
                max_moves=1,
                duplicates_action="quarantine",
                duplicate_case_ids=set()  # No duplicates
            )
            results = mover.move_all(matches)

            # Only 1 result
            assert len(results) == 1
            assert results[0].status == MoveStatus.SUCCESS

            # Only first folder moved
            assert (dest_root / "Case_001").exists()
            assert src2.exists()  # Not processed
            assert src3.exists()  # Not processed

    def test_max_moves_skips_dont_count(self):
        """Skipped operations don't count toward max_moves limit."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            # First two will be skipped (excluded), third should move
            src1 = base / "temp_folder_1"
            src2 = base / "temp_folder_2"
            src3 = base / "normal_folder"
            src1.mkdir()
            src2.mkdir()
            src3.mkdir()

            matches = [
                FolderMatch("001", str(src1), "temp_folder_1"),
                FolderMatch("002", str(src2), "temp_folder_2"),
                FolderMatch("003", str(src3), "normal_folder"),
            ]

            mover = FolderMover(
                dest_root,
                max_moves=1,
                exclude_patterns=["temp"],  # First two will be excluded
            )
            results = mover.move_all(matches)

            # All 3 processed: 2 skipped + 1 moved = 3 results
            assert len(results) == 3
            assert results[0].status == MoveStatus.SKIPPED_EXCLUDED
            assert results[1].status == MoveStatus.SKIPPED_EXCLUDED
            assert results[2].status == MoveStatus.SUCCESS

            # Skips didn't count, so we got 1 op (the move)
            stats = mover.get_stats()
            assert stats["skipped_excluded"] == 2
            assert stats["success"] == 1

    def test_max_moves_mixed_moves_and_quarantines(self):
        """Max moves counts both regular moves and quarantines toward limit."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            # One single-match, two duplicates
            src_single = base / "Case_001"
            src_dup1 = base / "Case_002_A"
            src_dup2 = base / "Case_002_B"
            src_single.mkdir()
            src_dup1.mkdir()
            src_dup2.mkdir()

            matches = [
                FolderMatch("001", str(src_single), "Case_001"),  # Will move
                FolderMatch("002", str(src_dup1), "Case_002_A"),  # Will quarantine
                FolderMatch("002", str(src_dup2), "Case_002_B"),  # Would quarantine but limit hit
            ]

            mover = FolderMover(
                dest_root,
                max_moves=2,
                duplicates_action="quarantine",
                duplicate_case_ids={"002"}
            )
            results = mover.move_all(matches)

            # 2 ops: 1 move + 1 quarantine
            assert len(results) == 2
            assert results[0].status == MoveStatus.SUCCESS
            assert results[1].status == MoveStatus.QUARANTINED

            # Third folder not processed
            assert src_dup2.exists()

    def test_max_moves_dry_run_counts_operations(self):
        """Dry-run operations also count toward max_moves."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest_root = base / "dest"
            dest_root.mkdir()

            src1 = base / "Case_001"
            src2 = base / "Case_002"
            src1.mkdir()
            src2.mkdir()

            matches = [
                FolderMatch("001", str(src1), "Case_001"),
                FolderMatch("002", str(src2), "Case_002"),
            ]

            mover = FolderMover(
                dest_root,
                dry_run=True,
                max_moves=1,
            )
            results = mover.move_all(matches)

            # Only 1 dry-run op
            assert len(results) == 1
            assert results[0].status == MoveStatus.DRY_RUN

            # Both sources still exist (dry run)
            assert src1.exists()
            assert src2.exists()
