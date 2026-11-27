"""No-Oracle tests for Roadmap sync parsing, diffing and MERGE statements."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _roadmap_sync as sync  # noqa: E402


class StubCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __enter__(self):
        return self

    def __exit__(self, _kind, _exc, _tb):
        return False

    def execute(self, sql, **bindings):
        self.calls.append((sql, bindings))


class StubConnection:
    def __init__(self) -> None:
        self.cur = StubCursor()
        self.commits = 0

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1


class RoadmapSyncTests(unittest.TestCase):
    def setUp(self):
        self.source = sync.ModuleSource(
            Path("module/example"), "EXAMPLE_MODULE", Path("module/example/content/roadmap/vi/roadmap.yml")
        )
        self.milestone = sync.Milestone("first-step", 1, "Tiêu đề", "Mục đích", "A\nB")

    def test_parse_valid_roadmap_and_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "roadmap.yml"
            path.write_text(
                "roadmap:\n"
                "  - id: first-step\n"
                "    title: Tiêu đề\n"
                "    purpose: Mục đích\n"
                "    objectives:\n"
                "      - A\n"
                "      - B\n",
                encoding="utf-8",
            )
            self.assertEqual(sync.read_roadmap(path), (self.milestone,))

    def test_parse_duplicate_id_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "roadmap.yml"
            path.write_text(
                "roadmap:\n"
                "  - {id: first-step, title: A, purpose: P}\n"
                "  - {id: first-step, title: B, purpose: Q}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(sync.SyncError, "duplicate roadmap key"):
                sync.read_roadmap(path)

    def test_new_module_roadmap_inserts_both_tables(self):
        snapshot = sync.Snapshot({"EXAMPLE_MODULE": 20}, {}, {}, {}, {"vi", "en"})
        diff = sync.plan_module(self.source, (self.milestone,), "vi", snapshot)
        self.assertEqual(diff["roadmap_insert"], 1)
        self.assertEqual(diff["translation_insert"], 1)

    def test_existing_identical_roadmap_is_noop(self):
        snapshot = sync.Snapshot(
            {"EXAMPLE_MODULE": 20},
            {(20, "first-step"): sync.RoadmapRow(99, 1)},
            {(99, "vi"): ("Tiêu đề", "Mục đích", "A\nB")},
            {99: {"vi", "en"}},
            {"vi", "en"},
        )
        diff = sync.plan_module(self.source, (self.milestone,), "vi", snapshot)
        self.assertEqual(diff["roadmap_unchanged"], 1)
        self.assertEqual(diff["translation_unchanged"], 1)
        self.assertEqual(diff["translation_update"], 0)

    def test_existing_roadmap_only_updates_target_language(self):
        snapshot = sync.Snapshot(
            {"EXAMPLE_MODULE": 20},
            {(20, "first-step"): sync.RoadmapRow(99, 1)},
            {(99, "vi"): ("Cũ", "Mục đích", "A\nB"), (99, "en"): ("Old", "Purpose", None)},
            {99: {"vi", "en"}},
            {"vi", "en"},
        )
        diff = sync.plan_module(self.source, (self.milestone,), "vi", snapshot)
        self.assertEqual(diff["translation_update"], 1)
        self.assertEqual(diff["roadmap_unchanged"], 1)

    def test_reordering_conflict_with_other_language(self):
        snapshot = sync.Snapshot(
            {"EXAMPLE_MODULE": 20},
            {(20, "first-step"): sync.RoadmapRow(99, 5)},
            {(99, "en"): ("Old", "Purpose", None)},
            {99: {"en"}},
            {"vi", "en"},
        )
        with self.assertRaisesRegex(sync.SyncError, "other translations exist"):
            sync.plan_module(self.source, (self.milestone,), "vi", snapshot)

    def test_merge_uses_only_two_merge_statements_and_commits(self):
        conn = StubConnection()
        sync.merge_module(conn, "LEARNING_PLATFORM.", self.source, (self.milestone,), "vi", 20)
        self.assertEqual(conn.commits, 1)
        self.assertEqual(len(conn.cur.calls), 2)
        for sql, params in conn.cur.calls:
            self.assertIn("MERGE INTO LEARNING_PLATFORM.MODULE_ROADMAP", sql)
            self.assertNotIn("DELETE", sql.upper())
            self.assertEqual(params["module_id"], 20)
            self.assertEqual(params["roadmap_key"], "first-step")
        self.assertEqual(conn.cur.calls[1][1]["language_code"], "vi")

    def test_single_rejects_path_traversal(self):
        with self.assertRaises(sync.SyncError):
            sync.discover_single("module/../../elsewhere", "vi")

    def test_single_missing_language_file_is_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "module" / "example"
            folder.mkdir(parents=True)
            (folder / "module-info.json").write_text(
                '{"SERVICE_NAME":{"VALUE":"EXAMPLE_MODULE"}}', encoding="utf-8"
            )
            with patch.object(sync, "REPO_ROOT", root), patch.object(sync, "MODULE_ROOT", root / "module"):
                sources, missing, errors = sync.discover_single("module/example", "en")
            self.assertEqual(sources, [])
            self.assertEqual(missing, 1)
            self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
