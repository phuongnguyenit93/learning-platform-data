"""Locale workflow gates for Menu/Knowledge imports (no Oracle connection)."""

from __future__ import annotations

from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _knowledge_menu_sync as sync  # noqa: E402


class SourceStatusTests(unittest.TestCase):
    def parse(self, language: str, detail_status: str, lesson_status: str,
              markdown: str = "# Authored lesson\n") -> sync.Locale:
        def read_yaml(path: Path, _root: Path):
            name = path.name
            if name == "menu.yml":
                return {"menu": [{"level1": "Introduction", "level2": ["Lesson"]}]}
            if name == "menu-level-1-slug.yml":
                return {"menu": [{"title": "Introduction", "slug": "intro", "index": 0}]}
            if name == "menu-detail-status.yml":
                return {"menu": [{"title": "Introduction", "slug": "intro", "childs": [
                    {"slug": "intro-001", "title": "Lesson", "status": detail_status}]}]}
            return {"menuLevel1": "Introduction", "menuLevel2": "Lesson", "status": lesson_status}

        with patch.object(sync, "_yaml", side_effect=read_yaml), \
             patch.object(sync, "_read_file", return_value=markdown):
            return sync._parse_locale(Path("module/test"), language)

    def source(self, locale: sync.Locale) -> sync.SourceModule:
        return sync.SourceModule(Path("module/test"), "TEST_SOURCE_STATUS", (locale,))

    def test_english_translate_is_publishable_and_stored_as_written(self) -> None:
        source = self.source(self.parse("en", "TRANSLATE", "TRANSLATE"))
        sync.ensure_sync_ready(source)
        lesson = source.locales[0].chapters[0].lessons[0]
        self.assertEqual(lesson.source_status, "TRANSLATE")
        self.assertEqual(lesson.translation_values(), ("# Authored lesson\n", "WRITTEN"))
        counts = sync.sync_module(None, None, "X.", source, sync.Snapshot(), 7)
        self.assertEqual(counts["knowledge_language_insert"], 1)
        self.assertEqual(counts["menu_language_insert"], 2)
        self.assertEqual(counts["published_total"], 1)

    def test_vietnamese_written_is_publishable(self) -> None:
        source = self.source(self.parse("vi", "WRITTEN", "WRITTEN"))
        sync.ensure_sync_ready(source)
        lesson = source.locales[0].chapters[0].lessons[0]
        self.assertEqual(lesson.translation_values()[1], "WRITTEN")

    def test_english_written_cannot_sync_even_if_content_exists(self) -> None:
        source = self.source(self.parse("en", "WRITTEN", "WRITTEN"))
        with self.assertRaisesRegex(sync.NotReadyError, "must be TRANSLATE"):
            sync.sync_module(None, None, "X.", source, sync.Snapshot(), 7)

    def test_vietnamese_translate_cannot_sync(self) -> None:
        source = self.source(self.parse("vi", "TRANSLATE", "TRANSLATE"))
        with self.assertRaisesRegex(sync.NotReadyError, "must be WRITTEN"):
            sync.sync_module(None, None, "X.", source, sync.Snapshot(), 7)

    def test_blank_or_draft_source_is_skipped_before_menu_write(self) -> None:
        source = self.source(self.parse("en", "", "", ""))
        with self.assertRaises(sync.NotReadyError):
            sync.sync_module(None, None, "X.", source, sync.Snapshot(), 7)

    def test_status_mismatch_between_yaml_files_is_rejected(self) -> None:
        with self.assertRaisesRegex(sync.SyncError, "per-lesson status differs"):
            self.parse("en", "WRITTEN", "TRANSLATE")

    def test_translate_requires_nonempty_markdown(self) -> None:
        with self.assertRaisesRegex(sync.SyncError, "requires Markdown content"):
            self.parse("en", "TRANSLATE", "TRANSLATE", "")

    def test_mixed_ready_unready_lessons_cannot_partially_push_menu(self) -> None:
        locale = self.parse("en", "TRANSLATE", "TRANSLATE")
        chapter = locale.chapters[0]
        invalid = sync.Lesson("intro-002", "Other", 1, "WRITTEN", "BASIC",
                              "# other", None, None, None, None, None, False)
        mixed = sync.SourceModule(Path("module/test"), "TEST_SOURCE_STATUS", (
            sync.Locale("en", (sync.Chapter(chapter.slug, chapter.title, 0,
                                             chapter.lessons + (invalid,)),)),))
        with self.assertRaises(sync.NotReadyError):
            sync.sync_module(None, None, "X.", mixed, sync.Snapshot(), 7)

    def test_missing_report_expects_english_translate_as_oracle_written(self) -> None:
        module = Path(__file__).resolve().parents[1] / "get-missing-knowledge-module.py"
        read_outline = runpy.run_path(str(module), run_name="report_status_test")["read_source_outline"]
        docs = {
            "menu.yml": {"menu": [{"level1": "Introduction", "level2": ["Lesson"]}]},
            "menu-level-1-slug.yml": {"menu": [{"title": "Introduction", "slug": "intro", "index": 0}]},
            "menu-detail-status.yml": {"menu": [{"title": "Introduction", "slug": "intro", "childs": [
                {"slug": "intro-001", "title": "Lesson", "status": "TRANSLATE"}]}]},
        }
        header = sync.SourceHeader(Path("module/test"), "TEST_SOURCE_STATUS", ("en",))
        with patch.object(sync, "_yaml", side_effect=lambda path, _root: docs[path.name]):
            outline = read_outline(header)
        self.assertEqual(outline["locales"][0][1][0][3][0][3], "WRITTEN")

        # Historical EN lessons already in Oracle must not appear OUTDATED
        # just because new imports now use the TRANSLATE source workflow flag.
        docs["menu-detail-status.yml"]["menu"][0]["childs"][0]["status"] = "WRITTEN"
        with patch.object(sync, "_yaml", side_effect=lambda path, _root: docs[path.name]):
            legacy_outline = read_outline(header)
        self.assertEqual(legacy_outline["locales"][0][1][0][3][0][3], "WRITTEN")


if __name__ == "__main__":
    unittest.main()
