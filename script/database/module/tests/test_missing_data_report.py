"""Unit tests for read-only Oracle missing Roadmap/Reference reports."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _missing_data_report as report  # noqa: E402


class MissingDataReportTests(unittest.TestCase):
    def test_roadmap_header_and_language_details_are_split(self):
        rows = [
            ("NO_ROADMAP", "PLATFORM/java/core", "en", 1, 1),
            ("NO_ROADMAP", "PLATFORM/java/core", "vi", 1, 1),
            ("PARTIAL_ROADMAP", "PLATFORM/java/stream", "en", 0, 1),
            ("PARTIAL_ROADMAP", "PLATFORM/java/stream", "vi", 0, 0),
            ("COMPLETE_ROADMAP", "PLATFORM/java/collections", "en", 0, 0),
            ("COMPLETE_ROADMAP", "PLATFORM/java/collections", "vi", 0, 0),
        ]

        documents, summary = report.build_documents(rows, report.REPORT_SPECS["roadmap"])

        self.assertEqual(
            documents["missing-roadmap-header.yml"]["missingRoadmap"],
            [{"Module": "NO_ROADMAP", "Path": "PLATFORM/java/core", "missingRoadmap": True}],
        )
        self.assertEqual(
            documents["missing-roadmap-detail-en.yml"]["missingRoadmapDetail"],
            [
                {"Module": "NO_ROADMAP", "Path": "PLATFORM/java/core", "missingRoadmapDetail": True},
                {"Module": "PARTIAL_ROADMAP", "Path": "PLATFORM/java/stream", "missingRoadmapDetail": True},
            ],
        )
        self.assertEqual(
            documents["missing-roadmap-detail-vi.yml"]["missingRoadmapDetail"],
            [{"Module": "NO_ROADMAP", "Path": "PLATFORM/java/core", "missingRoadmapDetail": True}],
        )
        self.assertEqual(summary["missing_parent"], 1)
        self.assertEqual(summary["missing_detail"], {"en": 2, "vi": 1})

    def test_reference_reports_use_reference_keys(self):
        rows = [
            ("MISSING_REFERENCE", "INFRASTRUCTURE/cloud/architecture", "en", 1, 1),
            ("MISSING_REFERENCE", "INFRASTRUCTURE/cloud/architecture", "vi", 1, 1),
        ]
        documents, _ = report.build_documents(rows, report.REPORT_SPECS["reference"])

        self.assertIn("missingReference", documents["missing-reference-header.yml"])
        self.assertIn("missingReferenceDetail", documents["missing-reference-detail-en.yml"])
        self.assertEqual(len(documents), 3)

    def test_modules_with_all_false_flags_are_not_listed(self):
        rows = [
            ("COMPLETE", "PLATFORM/java/core", "en", 0, 0),
            ("COMPLETE", "PLATFORM/java/core", "vi", 0, 0),
        ]
        documents, summary = report.build_documents(rows, report.REPORT_SPECS["roadmap"])

        self.assertEqual(documents["missing-roadmap-header.yml"]["missingRoadmap"], [])
        self.assertEqual(documents["missing-roadmap-detail-en.yml"]["missingRoadmapDetail"], [])
        self.assertEqual(documents["missing-roadmap-detail-vi.yml"]["missingRoadmapDetail"], [])
        self.assertEqual(summary["missing_parent"], 0)
        self.assertEqual(summary["missing_detail"], {"en": 0, "vi": 0})

    def test_inconsistent_language_rows_are_rejected(self):
        rows = [
            ("MODULE_A", "PLATFORM/java/core", "en", 0, 0),
            ("MODULE_B", "PLATFORM/java/core", "vi", 0, 0),
        ]
        with self.assertRaisesRegex(report.ReportError, "Incomplete language rows"):
            report.build_documents(rows, report.REPORT_SPECS["roadmap"])

    def test_invalid_service_name_and_language_are_rejected(self):
        with self.assertRaisesRegex(report.ReportError, "SERVICE_NAME"):
            report.build_documents(
                [("not-valid", "PLATFORM/java/core", "vi", 1, 1)],
                report.REPORT_SPECS["roadmap"],
            )
        with self.assertRaisesRegex(report.ReportError, "LANGUAGE"):
            report.build_documents(
                [("MODULE_A", "PLATFORM/java/core", "../outside", 1, 1)],
                report.REPORT_SPECS["roadmap"],
            )

    def test_query_uses_one_read_only_select_and_checks_every_parent_row(self):
        sql = report.build_query(report.REPORT_SPECS["roadmap"], "LEARNING_PLATFORM.")
        self.assertIn("FROM LEARNING_PLATFORM.MODULE_ROADMAP", sql)
        self.assertIn("LEARNING_PLATFORM.MODULE_ROADMAP_LANGUAGE", sql)
        self.assertIn("SYS_CONNECT_BY_PATH(SLUG, '/')", sql)
        self.assertIn("C.CODE || '/' || T.SLUG", sql)
        self.assertIn("COUNT(DISTINCT P.ID)", sql)
        self.assertIn("CROSS JOIN LEARNING_PLATFORM.LANGUAGE", sql)
        self.assertNotIn("INSERT ", sql.upper())
        self.assertNotIn("UPDATE ", sql.upper())
        self.assertNotIn("DELETE ", sql.upper())
        with self.assertRaises(report.ReportError):
            report.build_query(report.REPORT_SPECS["roadmap"], "LEARNING_PLATFORM;DROP TABLE ")

    def test_report_writer_creates_empty_files_and_removes_stale_language_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            stale = report_dir / "missing-roadmap-detail-fr.yml"
            stale.write_text("missingRoadmapDetail: []\n", encoding="utf-8")
            docs = {
                "missing-roadmap-header.yml": {"missingRoadmap": []},
                "missing-roadmap-detail-en.yml": {"missingRoadmapDetail": []},
                "missing-roadmap-detail-vi.yml": {"missingRoadmapDetail": []},
            }

            written = report.write_documents(report_dir, docs, "roadmap")

            self.assertEqual(len(written), 3)
            self.assertTrue((report_dir / "missing-roadmap-header.yml").is_file())
            self.assertFalse(stale.exists())
            self.assertIn("missingRoadmap: []", (report_dir / "missing-roadmap-header.yml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
