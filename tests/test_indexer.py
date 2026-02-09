"""
Unit tests for the folder indexer.
"""

import os
import tempfile
from pathlib import Path

import pytest

from folder_mover.indexer import (
    FolderIndexer,
    HAS_AHOCORASICK,
    MatcherNotAvailableError,
    match_caseids,
    scan_folders,
)
from folder_mover.types import FolderEntry


def create_test_tree(structure: dict, base_path: Path) -> None:
    """
    Create a directory tree from a nested dict structure.

    Args:
        structure: Dict where keys are folder names, values are nested dicts
        base_path: Base path to create the tree under
    """
    for name, children in structure.items():
        folder_path = base_path / name
        folder_path.mkdir(parents=True, exist_ok=True)
        if children:
            create_test_tree(children, folder_path)


class TestScanFolders:
    """Tests for scan_folders function."""

    def test_scan_empty_directory(self):
        """Empty directory returns empty list."""
        with tempfile.TemporaryDirectory() as tmp:
            folders = scan_folders(tmp)
            assert folders == []

    def test_scan_single_folder(self):
        """Single subfolder is found."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "folder1").mkdir()
            folders = scan_folders(tmp)
            assert len(folders) == 1
            assert folders[0].name == "folder1"

    def test_scan_nested_folders(self):
        """Nested folders are all found."""
        with tempfile.TemporaryDirectory() as tmp:
            structure = {
                "level1": {
                    "level2a": {
                        "level3": {}
                    },
                    "level2b": {}
                }
            }
            create_test_tree(structure, Path(tmp))
            folders = scan_folders(tmp)

            names = {f.name for f in folders}
            assert names == {"level1", "level2a", "level2b", "level3"}

    def test_scan_returns_full_paths(self):
        """Folder entries contain full absolute paths."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "myfolder").mkdir()
            folders = scan_folders(tmp)

            assert len(folders) == 1
            assert folders[0].path.endswith("myfolder")
            assert Path(folders[0].path).is_absolute()

    def test_scan_ignores_files(self):
        """Files are not included in scan results."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "folder1").mkdir()
            (base / "file.txt").write_text("content")
            (base / "folder1" / "nested_file.txt").write_text("content")

            folders = scan_folders(tmp)
            assert len(folders) == 1
            assert folders[0].name == "folder1"

    def test_scan_many_folders(self):
        """Can scan many folders efficiently."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            # Create 100 folders
            for i in range(100):
                (base / f"folder_{i:03d}").mkdir()

            folders = scan_folders(tmp)
            assert len(folders) == 100

    def test_scan_nonexistent_raises(self):
        """Non-existent path raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            scan_folders("/nonexistent/path/that/does/not/exist")

    def test_scan_file_raises(self):
        """File path raises NotADirectoryError."""
        # Use mkstemp and close fd immediately for Windows compatibility
        fd, path = tempfile.mkstemp()
        os.close(fd)
        try:
            with pytest.raises(NotADirectoryError):
                scan_folders(path)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_folder_entry_equality(self):
        """FolderEntry equality is based on path."""
        entry1 = FolderEntry(name="test", path="/path/to/test")
        entry2 = FolderEntry(name="test", path="/path/to/test")
        entry3 = FolderEntry(name="test", path="/other/path/test")

        assert entry1 == entry2
        assert entry1 != entry3

    def test_folder_entry_hashable(self):
        """FolderEntry can be used in sets."""
        entry1 = FolderEntry(name="test", path="/path/to/test")
        entry2 = FolderEntry(name="test", path="/path/to/test")
        entry3 = FolderEntry(name="test", path="/other/path/test")

        s = {entry1, entry2, entry3}
        assert len(s) == 2


class TestMatchCaseids:
    """Tests for match_caseids function."""

    def test_exact_match(self):
        """CaseID exactly matching folder name is found."""
        folders = [
            FolderEntry(name="00123", path="/data/00123"),
            FolderEntry(name="00456", path="/data/00456"),
        ]
        case_ids = ["00123"]

        results = match_caseids(case_ids, folders)

        assert len(results["00123"]) == 1
        assert results["00123"][0].name == "00123"

    def test_substring_match(self):
        """CaseID as substring of folder name is found."""
        folders = [
            FolderEntry(name="Case_00123_Documents", path="/data/Case_00123_Documents"),
            FolderEntry(name="Project_00456_Files", path="/data/Project_00456_Files"),
        ]
        case_ids = ["00123", "00456"]

        results = match_caseids(case_ids, folders)

        assert len(results["00123"]) == 1
        assert results["00123"][0].name == "Case_00123_Documents"
        assert len(results["00456"]) == 1
        assert results["00456"][0].name == "Project_00456_Files"

    def test_no_match(self):
        """CaseID not in any folder name returns empty list."""
        folders = [
            FolderEntry(name="folder1", path="/data/folder1"),
            FolderEntry(name="folder2", path="/data/folder2"),
        ]
        case_ids = ["99999"]

        results = match_caseids(case_ids, folders)

        assert results["99999"] == []

    def test_multiple_matches_same_caseid(self):
        """CaseID matching multiple folders returns all matches."""
        folders = [
            FolderEntry(name="00123_A", path="/data/00123_A"),
            FolderEntry(name="00123_B", path="/data/00123_B"),
            FolderEntry(name="00456", path="/data/00456"),
        ]
        case_ids = ["00123"]

        results = match_caseids(case_ids, folders)

        assert len(results["00123"]) == 2
        names = {f.name for f in results["00123"]}
        assert names == {"00123_A", "00123_B"}

    def test_case_insensitive_default(self):
        """Matching is case-insensitive by default."""
        folders = [
            FolderEntry(name="CASE_ABC_Docs", path="/data/CASE_ABC_Docs"),
        ]
        case_ids = ["abc"]

        results = match_caseids(case_ids, folders)

        assert len(results["abc"]) == 1

    def test_case_sensitive_option(self):
        """Case-sensitive matching when enabled."""
        folders = [
            FolderEntry(name="CASE_ABC_Docs", path="/data/CASE_ABC_Docs"),
            FolderEntry(name="case_abc_docs", path="/data/case_abc_docs"),
        ]
        case_ids = ["abc"]

        results = match_caseids(case_ids, folders, case_sensitive=True)

        assert len(results["abc"]) == 1
        assert results["abc"][0].name == "case_abc_docs"

    def test_empty_caseids(self):
        """Empty CaseID list returns empty dict."""
        folders = [FolderEntry(name="folder", path="/data/folder")]
        results = match_caseids([], folders)
        assert results == {}

    def test_empty_folders(self):
        """Empty folder list returns empty matches for all CaseIDs."""
        case_ids = ["001", "002"]
        results = match_caseids(case_ids, [])
        assert results == {"001": [], "002": []}

    def test_leading_zeros_preserved(self):
        """Leading zeros in CaseIDs are matched correctly."""
        folders = [
            FolderEntry(name="00123_Project", path="/data/00123_Project"),
            FolderEntry(name="123_Project", path="/data/123_Project"),
        ]
        case_ids = ["00123"]

        results = match_caseids(case_ids, folders)

        assert len(results["00123"]) == 1
        assert results["00123"][0].name == "00123_Project"

    def test_special_characters_in_caseid(self):
        """CaseIDs with special characters match correctly."""
        folders = [
            FolderEntry(name="Case-A.001_Files", path="/data/Case-A.001_Files"),
        ]
        case_ids = ["A.001"]

        results = match_caseids(case_ids, folders)

        assert len(results["A.001"]) == 1

    def test_all_caseids_in_results(self):
        """All CaseIDs appear in results dict even with no matches."""
        folders = [FolderEntry(name="folder", path="/data/folder")]
        case_ids = ["A", "B", "C"]

        results = match_caseids(case_ids, folders)

        assert set(results.keys()) == {"A", "B", "C"}


class TestFolderIndexer:
    """Tests for FolderIndexer class."""

    def test_indexer_basic(self):
        """Basic indexer workflow."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "Case_00123").mkdir()
            (base / "Case_00456").mkdir()

            indexer = FolderIndexer(tmp)
            count = indexer.build_index()

            assert count == 2
            assert len(indexer.folders) == 2

    def test_indexer_find_matches(self):
        """FolderIndexer.find_matches returns FolderMatch objects."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "Project_ABC_2023").mkdir()

            indexer = FolderIndexer(tmp)
            matches = indexer.find_matches("ABC")

            assert len(matches) == 1
            assert matches[0].case_id == "ABC"
            assert matches[0].folder_name == "Project_ABC_2023"

    def test_indexer_find_all_matches(self):
        """FolderIndexer.find_all_matches handles multiple CaseIDs."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "Case_001_Docs").mkdir()
            (base / "Case_002_Files").mkdir()
            (base / "Other_Folder").mkdir()

            indexer = FolderIndexer(tmp)
            results = indexer.find_all_matches(["001", "002", "003"])

            assert len(results["001"]) == 1
            assert len(results["002"]) == 1
            assert len(results["003"]) == 0

    def test_indexer_lazy_build(self):
        """Indexer builds index lazily on first access."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "folder").mkdir()

            indexer = FolderIndexer(tmp)
            assert indexer._folders is None

            # Access triggers build
            _ = indexer.folders
            assert indexer._folders is not None

    def test_indexer_case_sensitive(self):
        """Indexer respects case_sensitive option."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "ABC_Folder").mkdir()

            indexer_insensitive = FolderIndexer(tmp, case_sensitive=False)
            indexer_sensitive = FolderIndexer(tmp, case_sensitive=True)

            matches_insensitive = indexer_insensitive.find_matches("abc")
            matches_sensitive = indexer_sensitive.find_matches("abc")

            assert len(matches_insensitive) == 1
            assert len(matches_sensitive) == 0


class TestLengthBucketOptimization:
    """Tests verifying length bucket optimization works correctly."""

    def test_short_caseid_matches_long_folder(self):
        """Short CaseID can match inside long folder name."""
        folders = [
            FolderEntry(name="VeryLongFolderName_001_WithMoreText", path="/a"),
        ]
        case_ids = ["001"]

        results = match_caseids(case_ids, folders)
        assert len(results["001"]) == 1

    def test_long_caseid_no_match_short_folder(self):
        """Long CaseID cannot match short folder name."""
        folders = [
            FolderEntry(name="ABC", path="/short"),
        ]
        case_ids = ["VERYLONGCASEID"]

        results = match_caseids(case_ids, folders)
        assert len(results["VERYLONGCASEID"]) == 0

    def test_mixed_length_caseids(self):
        """CaseIDs of various lengths all match correctly."""
        folders = [
            FolderEntry(name="A", path="/a"),
            FolderEntry(name="AB", path="/ab"),
            FolderEntry(name="ABC", path="/abc"),
            FolderEntry(name="ABCD", path="/abcd"),
            FolderEntry(name="ABCDE", path="/abcde"),
        ]
        case_ids = ["A", "ABC", "ABCDE"]

        results = match_caseids(case_ids, folders)

        # "A" matches A, AB, ABC, ABCD, ABCDE
        assert len(results["A"]) == 5
        # "ABC" matches ABC, ABCD, ABCDE
        assert len(results["ABC"]) == 3
        # "ABCDE" matches only ABCDE
        assert len(results["ABCDE"]) == 1


class TestIntegration:
    """Integration tests with realistic folder structures."""

    def test_realistic_case_structure(self):
        """Test with realistic folder naming patterns."""
        with tempfile.TemporaryDirectory() as tmp:
            structure = {
                "2023": {
                    "Q1": {
                        "Case_00123_Smith_v_Jones": {},
                        "Case_00456_Doe_v_State": {},
                    },
                    "Q2": {
                        "Case_00789_Corporate_Matter": {},
                    }
                },
                "2022": {
                    "Archive": {
                        "Case_00123_Old": {},  # Same CaseID, different case
                    }
                }
            }
            create_test_tree(structure, Path(tmp))

            indexer = FolderIndexer(tmp)
            count = indexer.build_index()

            # Should find all directories:
            # 2023, Q1, Q2, Case_00123_Smith_v_Jones, Case_00456_Doe_v_State,
            # Case_00789_Corporate_Matter, 2022, Archive, Case_00123_Old = 9
            assert count == 9

            # Match CaseID that appears twice
            matches = indexer.find_matches("00123")
            assert len(matches) == 2

            # Match CaseID that appears once
            matches = indexer.find_matches("00789")
            assert len(matches) == 1
            assert "Corporate_Matter" in matches[0].folder_name

    def test_deep_nesting(self):
        """Test with deeply nested structure."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create 10 levels deep
            current = Path(tmp)
            for i in range(10):
                current = current / f"level_{i}"
                current.mkdir()

            # Add target folder at bottom
            target = current / "Case_TARGET_Found"
            target.mkdir()

            folders = scan_folders(tmp)

            # Should find all 11 folders (10 levels + target)
            assert len(folders) == 11

            results = match_caseids(["TARGET"], folders)
            assert len(results["TARGET"]) == 1


class TestMatcherSelection:
    """Tests for matcher selection and availability."""

    def test_bucket_matcher_always_available(self):
        """Bucket matcher should always work."""
        folders = [
            FolderEntry(name="Case_00123", path="/data/Case_00123"),
        ]
        case_ids = ["00123"]

        results = match_caseids(case_ids, folders, matcher="bucket")
        assert len(results["00123"]) == 1

    def test_aho_matcher_falls_back_if_not_available(self):
        """Aho matcher should fall back to bucket when pyahocorasick is not installed."""
        if HAS_AHOCORASICK:
            pytest.skip("pyahocorasick is installed, cannot test fallback")

        folders = [FolderEntry(name="Case_00123", path="/data/Case_00123")]
        case_ids = ["00123"]

        # Should NOT raise; should silently fall back and produce correct results
        results = match_caseids(case_ids, folders, matcher="aho")
        assert len(results["00123"]) == 1
        assert results["00123"][0].name == "Case_00123"

    @pytest.mark.skipif(not HAS_AHOCORASICK, reason="pyahocorasick not installed")
    def test_aho_matcher_works_when_available(self):
        """Aho matcher should work when pyahocorasick is installed."""
        folders = [
            FolderEntry(name="Case_00123", path="/data/Case_00123"),
        ]
        case_ids = ["00123"]

        results = match_caseids(case_ids, folders, matcher="aho")
        assert len(results["00123"]) == 1

    def test_default_matcher_is_bucket(self):
        """Default matcher should be bucket."""
        folders = [
            FolderEntry(name="Test_ABC", path="/data/Test_ABC"),
        ]
        case_ids = ["ABC"]

        # Not specifying matcher should use bucket (no exception even if aho not available)
        results = match_caseids(case_ids, folders)
        assert len(results["ABC"]) == 1


class TestAhoFallback:
    """Tests for aho-to-bucket fallback when pyahocorasick is unavailable."""

    def test_fallback_produces_correct_matches(self, monkeypatch):
        """When aho is requested but unavailable, fallback produces the same results as bucket."""
        import folder_mover.indexer as indexer_mod

        # Force HAS_AHOCORASICK to False regardless of actual installation
        monkeypatch.setattr(indexer_mod, "HAS_AHOCORASICK", False)

        folders = [
            FolderEntry(name="Case_00123_Smith", path="/data/Case_00123_Smith"),
            FolderEntry(name="Case_00456_Jones", path="/data/Case_00456_Jones"),
            FolderEntry(name="00123_Duplicate", path="/archive/00123_Duplicate"),
            FolderEntry(name="NoMatch", path="/other/NoMatch"),
        ]
        case_ids = ["00123", "00456", "99999"]

        # Request aho — should fall back to bucket without raising
        aho_results = match_caseids(case_ids, folders, matcher="aho")

        # Verify correct match counts
        assert len(aho_results["00123"]) == 2
        assert len(aho_results["00456"]) == 1
        assert len(aho_results["99999"]) == 0

        # Verify results match explicit bucket call
        bucket_results = match_caseids(case_ids, folders, matcher="bucket")
        for cid in case_ids:
            aho_paths = {f.path for f in aho_results[cid]}
            bucket_paths = {f.path for f in bucket_results[cid]}
            assert aho_paths == bucket_paths, f"Mismatch for CaseID '{cid}'"

    def test_fallback_logs_warning(self, monkeypatch, caplog):
        """When aho falls back, a WARNING is logged."""
        import logging
        import folder_mover.indexer as indexer_mod

        monkeypatch.setattr(indexer_mod, "HAS_AHOCORASICK", False)

        folders = [FolderEntry(name="Test", path="/test")]
        case_ids = ["Test"]

        with caplog.at_level(logging.WARNING, logger="folder_mover.indexer"):
            match_caseids(case_ids, folders, matcher="aho")

        assert any("Falling back to bucket" in msg for msg in caplog.messages)

    def test_fallback_with_real_folder_tree(self, monkeypatch):
        """End-to-end fallback test with actual directory scanning."""
        import folder_mover.indexer as indexer_mod

        monkeypatch.setattr(indexer_mod, "HAS_AHOCORASICK", False)

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "Case_001_Alpha").mkdir()
            (base / "Case_002_Beta").mkdir()
            (base / "Unrelated").mkdir()

            folders = scan_folders(tmp)
            results = match_caseids(["001", "002", "003"], folders, matcher="aho")

            assert len(results["001"]) == 1
            assert len(results["002"]) == 1
            assert len(results["003"]) == 0


class TestMatcherParity:
    """Tests to verify bucket and aho matchers produce identical results."""

    @pytest.fixture
    def sample_folders(self):
        """Sample folder set for parity testing."""
        return [
            FolderEntry(name="Case_00123_Smith", path="/data/Case_00123_Smith"),
            FolderEntry(name="Case_00456_Jones", path="/data/Case_00456_Jones"),
            FolderEntry(name="00123_Duplicate", path="/archive/00123_Duplicate"),
            FolderEntry(name="Project_ABC_2023", path="/projects/Project_ABC_2023"),
            FolderEntry(name="ABC_Another", path="/projects/ABC_Another"),
            FolderEntry(name="CASE_abc_lower", path="/data/CASE_abc_lower"),
            FolderEntry(name="NoMatch_Folder", path="/other/NoMatch_Folder"),
            FolderEntry(name="Special-Chars.001", path="/special/Special-Chars.001"),
            FolderEntry(name="123_NumericStart", path="/numeric/123_NumericStart"),
            FolderEntry(name="VeryLongFolderNameWithMultipleMatches_ABC_123", path="/long/x"),
        ]

    @pytest.fixture
    def sample_caseids(self):
        """Sample CaseID set for parity testing."""
        return [
            "00123",      # Multiple matches
            "00456",      # Single match
            "ABC",        # Case-insensitive matches
            "99999",      # No matches
            "001",        # Partial match of 00123
            "123",        # Matches 00123, 123_NumericStart, and long folder
            "Special",    # Special characters
        ]

    @pytest.mark.skipif(not HAS_AHOCORASICK, reason="pyahocorasick not installed")
    def test_parity_case_insensitive(self, sample_folders, sample_caseids):
        """Bucket and aho matchers should produce identical results (case-insensitive)."""
        bucket_results = match_caseids(
            sample_caseids, sample_folders,
            case_sensitive=False, matcher="bucket"
        )
        aho_results = match_caseids(
            sample_caseids, sample_folders,
            case_sensitive=False, matcher="aho"
        )

        # Same keys
        assert set(bucket_results.keys()) == set(aho_results.keys())

        # Same matches for each CaseID
        for case_id in sample_caseids:
            bucket_paths = {f.path for f in bucket_results[case_id]}
            aho_paths = {f.path for f in aho_results[case_id]}
            assert bucket_paths == aho_paths, f"Mismatch for CaseID '{case_id}'"

    @pytest.mark.skipif(not HAS_AHOCORASICK, reason="pyahocorasick not installed")
    def test_parity_case_sensitive(self, sample_folders, sample_caseids):
        """Bucket and aho matchers should produce identical results (case-sensitive)."""
        bucket_results = match_caseids(
            sample_caseids, sample_folders,
            case_sensitive=True, matcher="bucket"
        )
        aho_results = match_caseids(
            sample_caseids, sample_folders,
            case_sensitive=True, matcher="aho"
        )

        # Same keys
        assert set(bucket_results.keys()) == set(aho_results.keys())

        # Same matches for each CaseID
        for case_id in sample_caseids:
            bucket_paths = {f.path for f in bucket_results[case_id]}
            aho_paths = {f.path for f in aho_results[case_id]}
            assert bucket_paths == aho_paths, f"Mismatch for CaseID '{case_id}'"

    @pytest.mark.skipif(not HAS_AHOCORASICK, reason="pyahocorasick not installed")
    def test_parity_with_real_folders(self):
        """Parity test with actual folder structure."""
        with tempfile.TemporaryDirectory() as tmp:
            structure = {
                "2023": {
                    "Case_00123_Smith": {},
                    "Case_00456_Jones": {},
                },
                "2022": {
                    "Case_00123_Old": {},
                    "Project_ABC": {},
                },
                "Archive": {
                    "ABC_Files": {},
                    "Other": {},
                }
            }
            create_test_tree(structure, Path(tmp))

            folders = scan_folders(tmp)
            case_ids = ["00123", "00456", "ABC", "99999"]

            bucket_results = match_caseids(case_ids, folders, matcher="bucket")
            aho_results = match_caseids(case_ids, folders, matcher="aho")

            for case_id in case_ids:
                bucket_count = len(bucket_results[case_id])
                aho_count = len(aho_results[case_id])
                assert bucket_count == aho_count, f"Count mismatch for {case_id}"

                bucket_names = {f.name for f in bucket_results[case_id]}
                aho_names = {f.name for f in aho_results[case_id]}
                assert bucket_names == aho_names, f"Name mismatch for {case_id}"

    @pytest.mark.skipif(not HAS_AHOCORASICK, reason="pyahocorasick not installed")
    def test_parity_empty_inputs(self):
        """Both matchers handle empty inputs identically."""
        # Empty folders
        bucket = match_caseids(["A", "B"], [], matcher="bucket")
        aho = match_caseids(["A", "B"], [], matcher="aho")
        assert bucket == aho

        # Empty CaseIDs
        folders = [FolderEntry(name="test", path="/test")]
        bucket = match_caseids([], folders, matcher="bucket")
        aho = match_caseids([], folders, matcher="aho")
        assert bucket == aho

    @pytest.mark.skipif(not HAS_AHOCORASICK, reason="pyahocorasick not installed")
    def test_parity_overlapping_caseids(self):
        """Both matchers handle overlapping CaseIDs correctly."""
        folders = [
            FolderEntry(name="ABC123XYZ", path="/a"),
            FolderEntry(name="123ABC", path="/b"),
            FolderEntry(name="XYZ", path="/c"),
        ]
        # CaseIDs that overlap in the folder names
        case_ids = ["ABC", "123", "ABC123", "XYZ"]

        bucket_results = match_caseids(case_ids, folders, matcher="bucket")
        aho_results = match_caseids(case_ids, folders, matcher="aho")

        for case_id in case_ids:
            bucket_paths = {f.path for f in bucket_results[case_id]}
            aho_paths = {f.path for f in aho_results[case_id]}
            assert bucket_paths == aho_paths, f"Mismatch for overlapping CaseID '{case_id}'"


class TestFolderIndexerMatcher:
    """Tests for FolderIndexer with matcher parameter."""

    def test_indexer_default_matcher(self):
        """FolderIndexer uses bucket matcher by default."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Test_ABC").mkdir()

            indexer = FolderIndexer(tmp)
            assert indexer.matcher == "bucket"

    def test_indexer_with_bucket_matcher(self):
        """FolderIndexer works with explicit bucket matcher."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Case_00123").mkdir()

            indexer = FolderIndexer(tmp, matcher="bucket")
            matches = indexer.find_matches("00123")

            assert len(matches) == 1

    @pytest.mark.skipif(not HAS_AHOCORASICK, reason="pyahocorasick not installed")
    def test_indexer_with_aho_matcher(self):
        """FolderIndexer works with aho matcher when available."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Case_00123").mkdir()

            indexer = FolderIndexer(tmp, matcher="aho")
            matches = indexer.find_matches("00123")

            assert len(matches) == 1

    def test_indexer_aho_falls_back_if_unavailable(self):
        """FolderIndexer with aho matcher falls back to bucket if pyahocorasick not installed."""
        if HAS_AHOCORASICK:
            pytest.skip("pyahocorasick is installed")

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Test_ABC").mkdir()

            indexer = FolderIndexer(tmp, matcher="aho")
            matches = indexer.find_matches("ABC")

            assert len(matches) == 1
            assert matches[0].folder_name == "Test_ABC"
