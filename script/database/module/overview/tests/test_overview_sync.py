"""Overview sync unit tests; no live database writes."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _overview_sync as sync  # noqa: E402


class FakeCursor:
    def __init__(self):
        self.calls = []
        self.inputs = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, **params):
        self.calls.append((sql, params))

    def fetchone(self):
        return (23,)

    def setinputsizes(self, **kwargs):
        self.inputs.update(kwargs)


class FakeConnection:
    def __init__(self):
        self.cur = FakeCursor()
        self.commits = 0

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1


class FakeDriver:
    DB_TYPE_CLOB = "oracle-clob"


class OverviewSyncTests(unittest.TestCase):
    def setUp(self):
        self.source = sync.ModuleSource(
            Path("module/sample"), "SAMPLE",
            Path("module/sample/content/base/vi/base.md"),
        )

    def make_file(self, contents: bytes):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "base.md"
        path.write_bytes(contents)
        return path

    def test_preserve_unicode_and_crlf_in_clob(self):
        content = "# Tiếng Việt\r\nNội dung có dấu.\r\n"
        path = self.make_file(b"\xef\xbb\xbf" + content.encode("utf-8"))
        self.assertEqual(sync.read_overview(path), content)

    def test_empty_file_is_skipped(self):
        self.assertIsNone(sync.read_overview(self.make_file(b" \r\n\t")))

    def test_nul_is_rejected(self):
        with self.assertRaisesRegex(sync.SyncError, "NUL"):
            sync.read_overview(self.make_file(b"# Title\x00"))

    def test_unchanged_and_update_and_insert_plan(self):
        old = {(23, "vi"): "# Title\n"}
        self.assertEqual(
            sync.plan_module(self.source, "# Title\n", "vi", 23, old), "unchanged"
        )
        self.assertEqual(
            sync.plan_module(self.source, "# Changed\n", "vi", 23, old), "update"
        )
        self.assertEqual(
            sync.plan_module(self.source, "# Title\n", "en", 23, old), "insert"
        )

    def test_clob_merge_keeps_content_and_has_no_delete(self):
        connection = FakeConnection()
        markdown = "# Tiếng Việt\n" + "Kiến thức. " * 10000
        sync.merge_module(
            FakeDriver, connection, "LEARNING_PLATFORM.",
            23, markdown, "vi",
        )
        self.assertEqual(connection.commits, 1)
        self.assertEqual(connection.cur.inputs["content"], "oracle-clob")
        self.assertEqual(len(connection.cur.calls), 2)
        statement, binds = connection.cur.calls[-1]
        self.assertIn("MERGE INTO LEARNING_PLATFORM.MODULE_OVERVIEW", statement)
        self.assertIn("DBMS_LOB.COMPARE", statement)
        self.assertNotIn("DELETE ", statement.upper())
        self.assertEqual(binds["content"], markdown)
        self.assertEqual(binds["language_code"], "vi")


if __name__ == "__main__":
    unittest.main()
