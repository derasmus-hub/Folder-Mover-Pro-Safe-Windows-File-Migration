"""
Unit tests for the CSV report writer.
"""

import csv
import tempfile
from pathlib import Path

import pytest

from folder_mover.report import (
    REPORT_COLUMNS,
    ReportWriter,
    generate_report,
)
from folder_mover.types import MoveResult, MoveStatus, ReportStatus


class TestReportWriter:
    """Tests for ReportWriter class."""

    def test_creates_file_with_header(self):
        """Creates CSV file with header row."""
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.csv"

            with ReportWriter(report_path) as writer:
                pass  # Just open and close

            assert report_path.exists()

            with open(report_path) as f:
                reader = csv.reader(f)
                header = next(reader)
                assert header == REPORT_COLUMNS

    def test_writes_move_result(self):
        """Writes MoveResult entries correctly."""
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.csv"

            result = MoveResult(
                case_id="00123",
                source_path="/source/Case_00123",
                dest_path="/dest/Case_00123",
                status=MoveStatus.SUCCESS,
                message="Moved successfully"
            )

            with ReportWriter(report_path) as writer:
                writer.write_move_result(result)

            with open(report_path) as f:
                reader = csv.DictReader(f)
                row = next(reader)

                assert row["case_id"] == "00123"
                assert row["status"] == "MOVED"
                assert row["source_path"] == "/source/Case_00123"
                assert row["dest_path"] == "/dest/Case_00123"
                assert row["message"] == "Moved successfully"

    def test_writes_not_found(self):
        """Writes NOT_FOUND entries correctly."""
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.csv"

            with ReportWriter(report_path) as writer:
                writer.write_not_found("99999")

            with open(report_path) as f:
                reader = csv.DictReader(f)
                row = next(reader)

                assert row["case_id"] == "99999"
                assert row["status"] == "NOT_FOUND"
                assert row["source_path"] == ""
                assert row["dest_path"] == ""
                assert "No matching folders" in row["message"]

    def test_writes_error(self):
        """Writes ERROR entries with exception details."""
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.csv"

            with ReportWriter(report_path) as writer:
                writer.write_error(
                    case_id="00123",
                    error=PermissionError("Access denied"),
                    source_path="/source/locked"
                )

            with open(report_path) as f:
                reader = csv.DictReader(f)
                row = next(reader)

                assert row["case_id"] == "00123"
                assert row["status"] == "ERROR"
                assert "PermissionError" in row["message"]
                assert "Access denied" in row["message"]

    def test_writes_multiple_match(self):
        """Writes MULTIPLE_MATCHES status for multi-match CaseIDs."""
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.csv"

            result = MoveResult(
                case_id="00123",
                source_path="/source/Case_00123_A",
                dest_path="/dest/Case_00123_A",
                status=MoveStatus.SUCCESS,
                message="Moved successfully"
            )

            with ReportWriter(report_path) as writer:
                writer.write_move_result(result, is_multiple_match=True)

            with open(report_path) as f:
                reader = csv.DictReader(f)
                row = next(reader)

                assert row["status"] == "MULTIPLE_MATCHES"
                assert "[Multiple matches]" in row["message"]

    def test_status_conversions(self):
        """Tests all MoveStatus to ReportStatus conversions."""
        conversions = [
            (MoveStatus.SUCCESS, "MOVED"),
            (MoveStatus.SUCCESS_RENAMED, "MOVED_RENAMED"),
            (MoveStatus.SKIPPED_MISSING, "SKIPPED_MISSING"),
            (MoveStatus.SKIPPED_EXISTS, "SKIPPED_EXISTS"),
            (MoveStatus.ERROR, "ERROR"),
            (MoveStatus.DRY_RUN, "FOUND_DRYRUN"),
            (MoveStatus.DRY_RUN_RENAMED, "FOUND_DRYRUN_RENAMED"),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.csv"

            with ReportWriter(report_path) as writer:
                for move_status, _ in conversions:
                    result = MoveResult(
                        case_id="test",
                        source_path="/src",
                        dest_path="/dest",
                        status=move_status,
                        message="test"
                    )
                    writer.write_move_result(result)

            with open(report_path) as f:
                reader = csv.DictReader(f)
                rows = list(reader)

                for i, (_, expected_status) in enumerate(conversions):
                    assert rows[i]["status"] == expected_status

    def test_streaming_many_entries(self):
        """Handles many entries without memory issues."""
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.csv"

            with ReportWriter(report_path) as writer:
                for i in range(1000):
                    result = MoveResult(
                        case_id=f"{i:05d}",
                        source_path=f"/source/folder_{i}",
                        dest_path=f"/dest/folder_{i}",
                        status=MoveStatus.SUCCESS,
                        message="Moved"
                    )
                    writer.write_move_result(result)

                assert writer.get_row_count() == 1000

            # Verify file has all rows
            with open(report_path) as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                assert len(rows) == 1000

    def test_context_manager(self):
        """Context manager properly opens and closes file."""
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.csv"

            writer = ReportWriter(report_path)
            assert writer._file is None

            with writer:
                assert writer._file is not None
                writer.write_not_found("test")

            assert writer._file is None
            assert report_path.exists()

    def test_no_header_option(self):
        """Can disable header row."""
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.csv"

            with ReportWriter(report_path, include_header=False) as writer:
                writer.write_not_found("test")

            with open(report_path) as f:
                reader = csv.reader(f)
                first_row = next(reader)
                # First row should be data, not header
                assert first_row[1] == "test"  # case_id

    def test_get_stats(self):
        """Tracks statistics correctly."""
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.csv"

            with ReportWriter(report_path) as writer:
                # Write various statuses
                for status in [MoveStatus.SUCCESS, MoveStatus.SUCCESS]:
                    result = MoveResult("x", "/s", "/d", status, "msg")
                    writer.write_move_result(result)

                writer.write_not_found("y")
                writer.write_error("z", ValueError("test"))

                stats = writer.get_stats()
                assert stats["MOVED"] == 2
                assert stats["NOT_FOUND"] == 1
                assert stats["ERROR"] == 1

    def test_get_summary(self):
        """Generates readable summary."""
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.csv"

            with ReportWriter(report_path) as writer:
                result = MoveResult("x", "/s", "/d", MoveStatus.SUCCESS, "msg")
                writer.write_move_result(result)
                writer.write_not_found("y")

                summary = writer.get_summary()
                assert "Report Summary" in summary
                assert "Moved: 1" in summary
                assert "Not found: 1" in summary


class TestGenerateReport:
    """Tests for generate_report convenience function."""

    def test_generates_complete_report(self):
        """Generates report with results and not-found entries."""
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.csv"

            results = [
                MoveResult("001", "/s/a", "/d/a", MoveStatus.SUCCESS, "ok"),
                MoveResult("002", "/s/b", "/d/b", MoveStatus.SUCCESS, "ok"),
            ]
            not_found = ["003", "004"]

            writer = generate_report(results, not_found, report_path)

            assert writer.get_row_count() == 4
            assert writer.get_stats()["MOVED"] == 2
            assert writer.get_stats()["NOT_FOUND"] == 2

    def test_marks_multiple_matches(self):
        """Marks entries from CaseIDs with multiple matches."""
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.csv"

            results = [
                MoveResult("001", "/s/a", "/d/a", MoveStatus.SUCCESS, "ok"),
                MoveResult("001", "/s/b", "/d/b", MoveStatus.SUCCESS, "ok"),
                MoveResult("002", "/s/c", "/d/c", MoveStatus.SUCCESS, "ok"),
            ]
            match_counts = {"001": 2, "002": 1}

            generate_report(results, [], report_path, match_counts)

            with open(report_path) as f:
                reader = csv.DictReader(f)
                rows = list(reader)

                # First two should be MULTIPLE_MATCHES
                assert rows[0]["status"] == "MULTIPLE_MATCHES"
                assert rows[1]["status"] == "MULTIPLE_MATCHES"
                # Third should be regular MOVED
                assert rows[2]["status"] == "MOVED"


class TestReportStatus:
    """Tests for ReportStatus enum."""

    def test_from_move_status(self):
        """Converts MoveStatus correctly."""
        assert ReportStatus.from_move_status(MoveStatus.SUCCESS) == ReportStatus.MOVED
        assert ReportStatus.from_move_status(MoveStatus.DRY_RUN) == ReportStatus.FOUND_DRYRUN
        assert ReportStatus.from_move_status(MoveStatus.ERROR) == ReportStatus.ERROR

    def test_from_move_status_with_multiple(self):
        """Returns MULTIPLE_MATCHES when flag is set."""
        result = ReportStatus.from_move_status(MoveStatus.SUCCESS, is_multiple=True)
        assert result == ReportStatus.MULTIPLE_MATCHES


class TestDeterministicOutput:
    """Tests for deterministic, auditable output."""

    def test_consistent_column_order(self):
        """Columns are always in the same order."""
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(3):
                report_path = Path(tmp) / f"report_{i}.csv"

                with ReportWriter(report_path) as writer:
                    writer.write_not_found("test")

                with open(report_path) as f:
                    reader = csv.reader(f)
                    header = next(reader)
                    assert header == REPORT_COLUMNS

    def test_timestamps_included(self):
        """Every entry has a timestamp."""
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.csv"

            with ReportWriter(report_path) as writer:
                writer.write_not_found("test")
                result = MoveResult("x", "/s", "/d", MoveStatus.SUCCESS, "msg")
                writer.write_move_result(result)
                writer.write_error("y", ValueError("err"))

            with open(report_path) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    assert row["timestamp"]  # Not empty
                    # Should be ISO-ish format
                    assert "-" in row["timestamp"]
                    assert ":" in row["timestamp"]

    def test_special_characters_escaped(self):
        """CSV properly escapes special characters."""
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.csv"

            result = MoveResult(
                case_id="test,with,commas",
                source_path='/path/with "quotes"',
                dest_path="/path/with\nnewline",
                status=MoveStatus.SUCCESS,
                message='Message with, commas and "quotes"'
            )

            with ReportWriter(report_path) as writer:
                writer.write_move_result(result)

            # Re-read and verify values are intact
            with open(report_path) as f:
                reader = csv.DictReader(f)
                row = next(reader)

                assert row["case_id"] == "test,with,commas"
                assert row["source_path"] == '/path/with "quotes"'
                assert row["message"] == 'Message with, commas and "quotes"'

    def test_utf8_encoding(self):
        """Handles UTF-8 characters correctly."""
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.csv"

            result = MoveResult(
                case_id="案件001",
                source_path="/path/日本語フォルダ",
                dest_path="/dest/日本語フォルダ",
                status=MoveStatus.SUCCESS,
                message="Moved successfully: 成功"
            )

            with ReportWriter(report_path) as writer:
                writer.write_move_result(result)

            with open(report_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                row = next(reader)

                assert row["case_id"] == "案件001"
                assert "日本語" in row["source_path"]
                assert "成功" in row["message"]


class TestQuarantineReportStatus:
    """Tests for quarantine-related report statuses."""

    def test_quarantined_status_in_report(self):
        """Quarantined results show QUARANTINED status, not MULTIPLE_MATCHES."""
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.csv"

            result = MoveResult(
                case_id="00123",
                source_path="/source/Case_00123_A",
                dest_path="/dest/_DUPLICATES/00123/Case_00123_A",
                status=MoveStatus.QUARANTINED,
                message="Quarantined duplicate"
            )

            with ReportWriter(report_path) as writer:
                # Even with is_multiple_match=True, quarantine status is preserved
                writer.write_move_result(result, is_multiple_match=True)

            with open(report_path) as f:
                reader = csv.DictReader(f)
                row = next(reader)

                assert row["status"] == "QUARANTINED"
                # Message should note it's a multiple match
                assert "[Multiple matches]" in row["message"]

    def test_quarantined_renamed_status_in_report(self):
        """Quarantined with rename shows QUARANTINED_RENAMED status."""
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.csv"

            result = MoveResult(
                case_id="00123",
                source_path="/source/Case_00123",
                dest_path="/dest/_DUPLICATES/00123/Case_00123_1",
                status=MoveStatus.QUARANTINED_RENAMED,
                message="Quarantined duplicate (renamed)"
            )

            with ReportWriter(report_path) as writer:
                writer.write_move_result(result, is_multiple_match=True)

            with open(report_path) as f:
                reader = csv.DictReader(f)
                row = next(reader)

                assert row["status"] == "QUARANTINED_RENAMED"

    def test_dry_run_quarantine_status_in_report(self):
        """Dry-run quarantine shows FOUND_DRYRUN_QUARANTINE status."""
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.csv"

            result = MoveResult(
                case_id="00123",
                source_path="/source/Case_00123_A",
                dest_path="/dest/_DUPLICATES/00123/Case_00123_A",
                status=MoveStatus.DRY_RUN_QUARANTINE,
                message="Would quarantine duplicate"
            )

            with ReportWriter(report_path) as writer:
                writer.write_move_result(result, is_multiple_match=True)

            with open(report_path) as f:
                reader = csv.DictReader(f)
                row = next(reader)

                assert row["status"] == "FOUND_DRYRUN_QUARANTINE"

    def test_move_all_mode_still_uses_multiple_matches(self):
        """In move-all mode (non-quarantine), SUCCESS still becomes MULTIPLE_MATCHES."""
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.csv"

            # Regular SUCCESS with is_multiple=True (move-all mode)
            result = MoveResult(
                case_id="00123",
                source_path="/source/Case_00123_A",
                dest_path="/dest/Case_00123_A",
                status=MoveStatus.SUCCESS,
                message="Moved successfully"
            )

            with ReportWriter(report_path) as writer:
                writer.write_move_result(result, is_multiple_match=True)

            with open(report_path) as f:
                reader = csv.DictReader(f)
                row = next(reader)

                # Non-quarantine multiple matches should be MULTIPLE_MATCHES
                assert row["status"] == "MULTIPLE_MATCHES"

    def test_all_quarantine_status_conversions(self):
        """All quarantine-related MoveStatus values convert correctly."""
        conversions = [
            (MoveStatus.QUARANTINED, "QUARANTINED"),
            (MoveStatus.QUARANTINED_RENAMED, "QUARANTINED_RENAMED"),
            (MoveStatus.DRY_RUN_QUARANTINE, "FOUND_DRYRUN_QUARANTINE"),
            (MoveStatus.DRY_RUN_QUARANTINE_RENAMED, "FOUND_DRYRUN_QUARANTINE_RENAMED"),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.csv"

            with ReportWriter(report_path) as writer:
                for move_status, _ in conversions:
                    result = MoveResult(
                        case_id="test",
                        source_path="/src",
                        dest_path="/dest/_DUPLICATES/test/folder",
                        status=move_status,
                        message="test"
                    )
                    # Marked as multiple match, but should preserve quarantine status
                    writer.write_move_result(result, is_multiple_match=True)

            with open(report_path) as f:
                reader = csv.DictReader(f)
                rows = list(reader)

                for i, (_, expected_status) in enumerate(conversions):
                    assert rows[i]["status"] == expected_status
