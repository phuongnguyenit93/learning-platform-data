"""Verify Knowledge metadata array UPDATEs without writing to Oracle."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _knowledge_menu_sync as core  # noqa: E402
import _knowledge_metadata_sync as metadata  # noqa: E402


def source_with_rows(count: int, *, summary: bool = False):
    lessons = tuple(core.Lesson(
        f"intro-{i + 1:03d}", f"Lesson {i}", i, "WRITTEN", "BASIC",
        "# Content", f"Focus {i}", None, None, None,
        f"Summary {i}" if summary else None, True,
    ) for i in range(count))
    source = core.SourceModule(Path("module/test"), "TEST_METADATA", (
        core.Locale("vi", (core.Chapter("intro", "Intro", 0, lessons),)),
    ))
    rows = {("intro", lesson.slug, "vi"): (i + 1, (None,) * 5)
            for i, lesson in enumerate(lessons)}
    return source, rows


class FakeCursor:
    def __init__(self, *, short_batch: bool = False):
        self.calls = []
        self.types = []
        self.rowcount = 0
        self.short_batch = short_batch

    def execute(self, *_args, **_kwargs):
        raise AssertionError("Metadata updates must not use row-wise execute()")

    def setinputsizes(self, **kwargs):
        self.types.append(kwargs)

    def executemany(self, sql, rows):
        self.calls.append((sql, rows))
        self.rowcount = len(rows) - int(self.short_batch)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class Driver:
    DB_TYPE_CLOB = "CLOB_TYPE"


class MetadataBatchSyncTests(unittest.TestCase):
    def test_235_rows_use_three_array_updates(self):
        source, rows = source_with_rows(235)
        cursor = FakeCursor()
        counts = metadata.plan_metadata(Driver, cursor, "X.", source, rows, apply=True)
        self.assertEqual(counts["updated_rows"], 235)
        self.assertEqual(counts["updated_fields"], 235)
        self.assertEqual([len(batch) for _, batch in cursor.calls], [100, 100, 35])
        self.assertTrue(all("SET FOCUS = :focus WHERE" in sql for sql, _ in cursor.calls))
        self.assertEqual(cursor.types, [])

    def test_mixed_columns_and_clob_only_change_supplied_fields(self):
        source, rows = source_with_rows(3, summary=True)
        lessons = list(source.locales[0].chapters[0].lessons)
        lessons[0] = core.Lesson(*(
            lessons[0].slug, lessons[0].title, lessons[0].order,
            "WRITTEN", "BASIC", "# Content", "Focus 0", None, None, None, None, True,
        ))
        chapter = core.Chapter("intro", "Intro", 0, tuple(lessons))
        source = core.SourceModule(source.path, source.service_name,
                                   (core.Locale("vi", (chapter,)),))
        rows[("intro", "intro-002", "vi")] = (2, ("Focus 1", None, None, None, None))
        rows[("intro", "intro-003", "vi")] = (3, ("Focus 2", None, None, None, "Summary 2"))
        cursor = FakeCursor()
        counts = metadata.plan_metadata(Driver, cursor, "X.", source, rows, apply=True)
        self.assertEqual(counts["updated_rows"], 2)
        self.assertEqual([len(batch) for _, batch in cursor.calls], [1, 1])
        self.assertIn("SET FOCUS = :focus WHERE", cursor.calls[0][0])
        self.assertIn("SET SUMMARY = :summary WHERE", cursor.calls[1][0])
        self.assertEqual(cursor.types, [{"summary": Driver.DB_TYPE_CLOB}])

    def test_dry_run_does_not_send_dml(self):
        source, rows = source_with_rows(125)
        counts = metadata.plan_metadata(Driver, None, "X.", source, rows, apply=False)
        self.assertEqual(counts["updated_rows"], 125)

    def test_short_batch_raises_before_commit(self):
        source, rows = source_with_rows(120)
        cursor = FakeCursor(short_batch=True)
        with self.assertRaisesRegex(core.SyncError, "batch affected 99 rows instead of 100"):
            metadata.plan_metadata(Driver, cursor, "X.", source, rows, apply=True)

    def test_single_module_commits_only_after_all_batches(self):
        class Connection:
            commits = 0

            def cursor(self):
                return cursor

            def commit(self):
                self.commits += 1

        source, rows = source_with_rows(120)
        cursor = FakeCursor()
        connection = Connection()
        with patch.object(metadata.core, "_ensure_db_languages"), \
             patch.object(metadata.core, "find_module_id", return_value=7), \
             patch.object(metadata.core, "_lock_module"), \
             patch.object(metadata, "read_metadata_rows", return_value=rows):
            metadata._import_one(Driver, connection, "X.", source, {"vi": True}, apply=True)
        self.assertEqual(connection.commits, 1)
        self.assertEqual([len(batch) for _, batch in cursor.calls], [100, 20])

        source, rows = source_with_rows(120)
        cursor = FakeCursor(short_batch=True)
        connection = Connection()
        with patch.object(metadata.core, "_ensure_db_languages"), \
             patch.object(metadata.core, "find_module_id", return_value=7), \
             patch.object(metadata.core, "_lock_module"), \
             patch.object(metadata, "read_metadata_rows", return_value=rows):
            with self.assertRaises(core.SyncError):
                metadata._import_one(Driver, connection, "X.", source, {"vi": True}, apply=True)
        self.assertEqual(connection.commits, 0)


if __name__ == "__main__":
    unittest.main()
