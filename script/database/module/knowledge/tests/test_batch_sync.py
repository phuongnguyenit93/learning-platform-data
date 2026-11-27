"""Unit tests for the real Menu/Knowledge batch apply path (no Oracle writes)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _knowledge_menu_sync as sync  # noqa: E402


def source_module(lessons: int = 115, languages: tuple[str, ...] = ("vi", "en")) -> sync.SourceModule:
    locales = []
    for lang in languages:
        children = tuple(sync.Lesson(
            f"intro-{i + 1:03d}", f"Lesson {i} ({lang})", i,
            "TRANSLATE" if lang == "en" else "WRITTEN", "BASIC", f"# Content {lang} {i}\n" * 5,
            None, None, None, None, None, True,
        ) for i in range(lessons))
        locales.append(sync.Locale(lang, (sync.Chapter(
            "intro", f"Introduction ({lang})", 0, children),)))
    return sync.SourceModule(Path("module/test"), "TEST_BATCH", tuple(locales))


class FakeCursor:
    """Emulate identity generation and DML changes while verifying array SQL."""

    def __init__(self) -> None:
        self.chapter: dict[str, tuple[int, int]] = {}
        self.section: dict[tuple[int, str], tuple[int, int]] = {}
        self.knowledge: dict[int, tuple[int, str]] = {}
        self.title: dict[tuple[int, str], str] = {}
        self.content: dict[tuple[int, str], tuple[str | None, str]] = {}
        self.active: dict[tuple[str, int], int] = {}
        self.calls: list[tuple[str, int]] = []
        self.types: list[dict] = []
        self.pending: list = []
        self.rowcount = 0
        self.next_id = 100
        self.fail_on_call: int | None = None

    def _id(self) -> int:
        self.next_id += 1
        return self.next_id

    def setinputsizes(self, **kwargs: object) -> None:
        self.types.append(kwargs)

    def execute(self, statement: str, **kwargs: object) -> None:
        sql = " ".join(statement.upper().split())
        if sql.startswith("SELECT ID, SLUG FROM X.MODULE_MENU"):
            self.pending = [(item[0], slug) for slug, item in self.chapter.items()]
        elif sql.startswith("SELECT SECTION.ID, SECTION.MENU_PARENT_ID"):
            self.pending = [(item[0], key[0], key[1]) for key, item in self.section.items()]
        elif sql.startswith("SELECT K.ID, K.MENU_ID"):
            self.pending = [(item[0], menu_id) for menu_id, item in self.knowledge.items()]
        else:
            raise AssertionError(f"Unexpected row-wise SQL: {sql}")

    def fetchall(self) -> list:
        return self.pending

    def executemany(self, statement: str, rows: list[dict]) -> None:
        sql = " ".join(statement.upper().split())
        self.calls.append((sql, len(rows)))
        if self.fail_on_call == len(self.calls):
            raise RuntimeError("Simulated Oracle batch failure")
        for row in rows:
            if sql.startswith("INSERT INTO X.MODULE_MENU "):
                id_ = self._id()
                if "VALUES (:MODULE_ID, NULL, 'CHAPTER'" in sql:
                    self.chapter[row["slug"]] = (id_, row["sort_order"])
                else:
                    self.section[(row["parent_id"], row["slug"])] = (id_, row["sort_order"])
                self.active[("MODULE_MENU", id_)] = 0
            elif sql.startswith("UPDATE X.MODULE_MENU SET SORT_ORDER"):
                for key, (id_, _) in self.chapter.items():
                    if id_ == row["menu_id"]:
                        self.chapter[key] = (id_, row["sort_order"])
                        break
                for key, (id_, _) in self.section.items():
                    if id_ == row["menu_id"]:
                        self.section[key] = (id_, row["sort_order"])
                        break
            elif sql.startswith("INSERT INTO X.MODULE_MENU_LANGUAGE"):
                self.title[(row["menu_id"], row["lang"])] = row["title"]
            elif sql.startswith("UPDATE X.MODULE_MENU_LANGUAGE"):
                self.title[(row["menu_id"], row["lang"])] = row["title"]
            elif sql.startswith("INSERT INTO X.MODULE_KNOWLEDGE "):
                kid = self._id()
                self.knowledge[row["menu_id"]] = (kid, row["difficult"])
                self.active[("MODULE_KNOWLEDGE", kid)] = 0
            elif sql.startswith("UPDATE X.MODULE_KNOWLEDGE SET DIFFICULT"):
                for menu_id, (kid, _) in self.knowledge.items():
                    if kid == row["knowledge_id"]:
                        self.knowledge[menu_id] = (kid, row["difficult"])
                        break
            elif sql.startswith("INSERT INTO X.MODULE_KNOWLEDGE_LANGUAGE"):
                self.content[(row["knowledge_id"], row["lang"])] = (row["content"], row["status"])
            elif sql.startswith("UPDATE X.MODULE_KNOWLEDGE_LANGUAGE"):
                self.content[(row["knowledge_id"], row["lang"])] = (row["content"], row["status"])
            elif sql.startswith("UPDATE X.MODULE_MENU SET IS_ACTIVE"):
                self.active[("MODULE_MENU", row["id"])] = row["active"]
            elif sql.startswith("UPDATE X.MODULE_KNOWLEDGE SET IS_ACTIVE"):
                self.active[("MODULE_KNOWLEDGE", row["id"])] = row["active"]
            else:
                raise AssertionError(f"Unexpected batch SQL: {sql}")
        self.rowcount = len(rows)


class Driver:
    DB_TYPE_CLOB = "CLOB_TYPE"


class BatchSyncTests(unittest.TestCase):
    def test_new_module_batches_every_table_and_unchanged_is_idempotent(self) -> None:
        source = source_module()
        snapshot = sync.Snapshot()
        cursor = FakeCursor()
        stats = sync.sync_module(Driver, cursor, "X.", source, snapshot, 9, apply=True)
        self.assertEqual(stats["menu_insert"], 116)
        self.assertEqual(stats["knowledge_insert"], 115)
        self.assertEqual(stats["knowledge_language_insert"], 230)
        self.assertEqual(len(cursor.chapter), 1)
        self.assertEqual(len(cursor.section), 115)
        self.assertEqual(len(cursor.knowledge), 115)
        self.assertEqual(len(cursor.content), 230)
        self.assertTrue(all(n <= 100 for _, n in cursor.calls))
        content_batches = [n for sql, n in cursor.calls
                           if sql.startswith("INSERT INTO X.MODULE_KNOWLEDGE_LANGUAGE")]
        self.assertEqual(content_batches, [100, 100, 30])
        self.assertEqual(len(cursor.types), 3)
        self.assertTrue(all(item["content"] == Driver.DB_TYPE_CLOB for item in cursor.types))
        self.assertTrue(all(value == 1 for value in cursor.active.values()))
        self.assertEqual(sync._has_changes(sync.sync_module(Driver, None, "X.", source,
                                                           snapshot, 9, apply=False)), False)

        cursor.calls.clear()
        again = sync.sync_module(Driver, cursor, "X.", source, snapshot, 9, apply=True)
        self.assertFalse(sync._has_changes(again))
        self.assertFalse(cursor.calls, "Unchanged module must not submit DML")

    def test_partially_imported_module_only_adds_missing_translations(self) -> None:
        source = source_module(2)
        snapshot = sync.Snapshot()
        cursor = FakeCursor()
        sync.sync_module(Driver, cursor, "X.", source, snapshot, 9, apply=True)
        section_id = next(iter(snapshot.knowledge))
        kid = snapshot.knowledge[section_id].id
        snapshot.translations.pop((kid, "en"))
        cursor.content.pop((kid, "en"))
        cursor.calls.clear()
        result = sync.sync_module(Driver, cursor, "X.", source, snapshot, 9, apply=True)
        self.assertEqual(result["knowledge_language_insert"], 1)
        self.assertEqual(result["knowledge_insert"], 0)
        self.assertEqual(result["menu_insert"], 0)
        self.assertEqual(len(cursor.content), 4)
        self.assertEqual(len(cursor.calls), 1)
        self.assertEqual(cursor.calls[0][1], 1)

    def test_existing_module_accepts_new_lesson_without_reinserting_old_ids(self) -> None:
        original = source_module(2)
        expanded = source_module(3)
        snapshot = sync.Snapshot()
        cursor = FakeCursor()
        sync.sync_module(Driver, cursor, "X.", original, snapshot, 9, apply=True)
        chapter_id = snapshot.chapters["intro"].id
        retained = {key: node.id for key, node in snapshot.sections.items()}
        cursor.calls.clear()

        result = sync.sync_module(Driver, cursor, "X.", expanded, snapshot, 9, apply=True)
        self.assertEqual(result["menu_insert"], 1)
        self.assertEqual(result["knowledge_insert"], 1)
        self.assertEqual(result["knowledge_language_insert"], 2)
        self.assertEqual(result["menu_language_insert"], 2)
        self.assertEqual(snapshot.chapters["intro"].id, chapter_id)
        self.assertTrue(all(snapshot.sections[key].id == value
                            for key, value in retained.items()))
        self.assertEqual(len(snapshot.sections), 3)
        self.assertEqual(len(snapshot.knowledge), 3)
        self.assertEqual(len(cursor.content), 6)
        self.assertFalse(sync._has_changes(sync.sync_module(Driver, None, "X.",
                                                          expanded, snapshot, 9)))

    def test_existing_content_updates_only_relevant_columns(self) -> None:
        source = source_module(2)
        snapshot = sync.Snapshot()
        cursor = FakeCursor()
        sync.sync_module(Driver, cursor, "X.", source, snapshot, 9, apply=True)
        first = source.locales[0].chapters[0].lessons[0]
        changed_lesson = sync.Lesson(
            first.slug, first.title + " updated", first.order, first.source_status,
            "ADVANCED", "# Updated markdown", None, None, None, None, None, True)
        changed_chapter = sync.Chapter("intro", "Introduction (vi)", 0,
                                       (changed_lesson, source.locales[0].chapters[0].lessons[1]))
        english_lessons = source.locales[1].chapters[0].lessons
        english_first = sync.Lesson(
            english_lessons[0].slug, english_lessons[0].title,
            english_lessons[0].order, "TRANSLATE", "ADVANCED",
            english_lessons[0].content, None, None, None, None, None, True)
        changed_english = sync.Chapter("intro", "Introduction (en)", 0,
                                        (english_first, english_lessons[1]))
        changed = sync.SourceModule(source.path, source.service_name, (
            sync.Locale("vi", (changed_chapter,)),
            sync.Locale("en", (changed_english,))))
        cursor.calls.clear()
        result = sync.sync_module(Driver, cursor, "X.", changed, snapshot, 9, apply=True)
        self.assertEqual(result["knowledge_language_update"], 1)
        self.assertEqual(result["menu_language_update"], 1)
        self.assertEqual(result["knowledge_update"], 1)
        self.assertTrue(any("UPDATE X.MODULE_MENU_LANGUAGE SET TITLE" in sql for sql, _ in cursor.calls))
        self.assertTrue(any("UPDATE X.MODULE_KNOWLEDGE_LANGUAGE" in sql for sql, _ in cursor.calls))
        self.assertEqual(len(cursor.calls), 3)

    def test_preflight_conflict_stops_before_any_batch(self) -> None:
        source = source_module(1)
        snapshot = sync.Snapshot(
            chapters={"intro": sync.NodeRow(100, "intro", 1, True, None, "CHAPTER")},
            titles={(100, "fr"): "Autre"},
        )
        cursor = FakeCursor()
        with self.assertRaises(sync.SyncError):
            sync.sync_module(Driver, cursor, "X.", source, snapshot, 9, apply=True)
        self.assertEqual(cursor.calls, [])

    def test_batch_error_bubbles_without_committing(self) -> None:
        source = source_module()
        cursor = FakeCursor()
        cursor.fail_on_call = 2
        with self.assertRaisesRegex(RuntimeError, "Simulated Oracle batch failure"):
            sync.sync_module(Driver, cursor, "X.", source, sync.Snapshot(), 9, apply=True)
        self.assertEqual(len(cursor.calls), 2)

    def test_short_batch_rowcount_aborts_module(self) -> None:
        class ShortWriteCursor(FakeCursor):
            def executemany(self, statement: str, rows: list[dict]) -> None:
                super().executemany(statement, rows)
                self.rowcount -= 1

        cursor = ShortWriteCursor()
        with self.assertRaisesRegex(sync.SyncError, "Batch affected"):
            sync.sync_module(Driver, cursor, "X.", source_module(1),
                             sync.Snapshot(), 9, apply=True)
        self.assertEqual(len(cursor.calls), 1)


if __name__ == "__main__":
    unittest.main()
