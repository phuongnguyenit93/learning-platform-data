"""Reference sync unit tests; no live database writes."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _reference_sync as sync  # noqa: E402


class FakeCursor:
    def __init__(self):
        self.calls = []
        self.last_sql = ""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, **params):
        self.last_sql = sql
        self.calls.append((sql, params))

    def fetchone(self):
        if "FOR UPDATE" in self.last_sql:
            return (11,)
        return None


class FakeConnection:
    def __init__(self):
        self.cur = FakeCursor()
        self.commits = 0

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1


class ReferenceSyncTests(unittest.TestCase):
    def setUp(self):
        self.source = sync.ModuleSource(
            Path("module/sample"), "SAMPLE",
            Path("module/sample/content/reference/vi/references.yml"),
        )
        self.entry = sync.ReferenceEntry("https://example.org/path", "Tiêu đề", None, 1)

    def yaml_file(self, content: str):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "references.yml"
        path.write_text(content, encoding="utf-8")
        return path

    def test_valid_reference_yaml(self):
        path = self.yaml_file(
            "references:\n"
            "  - title: Tiêu đề\n"
            "    url: https://example.org/path\n"
            "    description: ''\n"
        )
        self.assertEqual(sync.read_references(path), (self.entry,))

    def test_duplicate_url_rejected(self):
        path = self.yaml_file(
            "references:\n"
            "  - {title: One, url: 'https://example.org/path'}\n"
            "  - {title: Two, url: 'https://example.org/path'}\n"
        )
        with self.assertRaisesRegex(sync.SyncError, "duplicate URL"):
            sync.read_references(path)

    def test_non_https_and_credentials_rejected(self):
        for url in ("http://example.org/a", "https://user:pass@example.org/a"):
            with self.subTest(url=url):
                path = self.yaml_file(
                    "references:\n  - title: Test\n    url: '" + url + "'\n"
                )
                with self.assertRaisesRegex(sync.SyncError, "HTTPS URL"):
                    sync.read_references(path)

    def test_empty_list_is_skip(self):
        self.assertEqual(sync.read_references(self.yaml_file("references: []\n")), ())

    def test_new_reference_plan(self):
        snapshot = sync.Snapshot({"SAMPLE": 11}, {"vi"}, {}, {}, {})
        result = sync.plan_module(self.source, (self.entry,), "vi", snapshot)
        self.assertEqual(result["reference_insert"], 1)
        self.assertEqual(result["translation_insert"], 1)

    def test_same_reference_is_unchanged(self):
        snapshot = sync.Snapshot(
            {"SAMPLE": 11}, {"vi", "en"},
            {(11, self.entry.url): sync.ReferenceRow(99, 1)},
            {(99, "vi"): ("Tiêu đề", None), (99, "en"): ("Title", None)},
            {99: {"vi", "en"}},
        )
        result = sync.plan_module(self.source, (self.entry,), "vi", snapshot)
        self.assertEqual(result["reference_unchanged"], 1)
        self.assertEqual(result["translation_unchanged"], 1)

    def test_translation_update_does_not_change_identity(self):
        snapshot = sync.Snapshot(
            {"SAMPLE": 11}, {"vi", "en"},
            {(11, self.entry.url): sync.ReferenceRow(99, 1)},
            {(99, "vi"): ("Cũ", None), (99, "en"): ("Title", None)},
            {99: {"vi", "en"}},
        )
        result = sync.plan_module(self.source, (self.entry,), "vi", snapshot)
        self.assertEqual(result["reference_unchanged"], 1)
        self.assertEqual(result["translation_update"], 1)

    def test_conflicting_sort_order_is_rejected_with_other_language(self):
        snapshot = sync.Snapshot(
            {"SAMPLE": 11}, {"vi", "en"},
            {(11, self.entry.url): sync.ReferenceRow(99, 2)},
            {(99, "en"): ("Title", None)}, {99: {"en"}},
        )
        with self.assertRaisesRegex(sync.SyncError, "another language"):
            sync.plan_module(self.source, (self.entry,), "vi", snapshot)

    def test_merge_runs_two_merges_and_no_delete(self):
        connection = FakeConnection()
        sync.merge_module(connection, "LEARNING_PLATFORM.", 11, (self.entry,), "vi")
        self.assertEqual(connection.commits, 1)
        sqls = [sql for sql, _ in connection.cur.calls]
        self.assertEqual(sum("MERGE INTO " in sql for sql in sqls), 2)
        self.assertTrue(all("DELETE " not in sql.upper() for sql in sqls))
        self.assertIn("FROM LEARNING_PLATFORM.MODULE_REFERENCE", sqls[3])
        self.assertEqual(connection.cur.calls[3][1]["language_code"], "vi")

    def test_common_source_rejects_traversal_and_skips_missing(self):
        import _module_source_sync as common
        with self.assertRaises(sync.SyncError):
            common.discover_sources(
                "vi", data_dir="reference", filename="references.yml",
                module_arg="module/../../outside",
            )
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            module = base / "module" / "sample"
            module.mkdir(parents=True)
            (module / "module-info.json").write_text(
                '{"SERVICE_NAME":{"VALUE":"SAMPLE"}}', encoding="utf-8"
            )
            with patch.object(common, "REPO_ROOT", base), patch.object(
                common, "MODULE_ROOT", base / "module"
            ):
                sources, missing, errors = common.discover_sources(
                    "en", data_dir="reference", filename="references.yml",
                    module_arg="module/sample",
                )
            self.assertEqual((sources, missing, errors), ([], 1, []))


if __name__ == "__main__":
    unittest.main()
