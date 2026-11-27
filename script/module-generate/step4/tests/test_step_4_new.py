"""Black-box tests for STEP_4_NEW refresh and Knowledge special-note modification."""

from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

import yaml


SCRIPT_DIR = Path(__file__).resolve().parents[1]
PRESTART = SCRIPT_DIR.parent / "step3" / "generate_menu_skeleton.py"
FINISH = SCRIPT_DIR.parent / "step3" / "generate_menu_detail.py"
REFRESH = SCRIPT_DIR / "refresh_menu_status.py"
MODIFY = SCRIPT_DIR.parent.parent / "module-generate" / "knowledge-modify-special-note.py"
SUBJECT = "DATA_ORIENTED_PROGRAMMING"


class Step4NewTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.module = self.root / "module" / "dop"
        self.module.mkdir(parents=True)
        (self.module / "master.json").write_text(json.dumps({
            "SERVICE_NAME": {"VALUE": SUBJECT}
        }), encoding="utf-8")
        self.knowledge = self.module / "content" / "knowledge" / "vi"
        self.run_script(PRESTART)
        # Legacy-only fixture: STEP 3 NEW no longer generates note.yml,
        # topic or specialNote. Add them explicitly to exercise historical
        # STEP 4 special-note migration without changing the NEW generator.
        self.write_yaml(self.knowledge / "note.yml", {
            "subject": SUBJECT, "detailName": "Data Oriented Programming",
            "specialNote": "",
        })
        self.write_yaml(self.knowledge / "menu.yml", {"menu": [
            {"level1": "Tổng quan", "level2": ["DOP là gì?", "So sánh với OOP"]},
            {"level1": "Ứng dụng", "level2": ["Tách xử lý và dữ liệu"]},
        ]})
        self.write_yaml(self.knowledge / "menu-level-1-slug.yml", {"menu": [
            {"title": "Tổng quan", "slug": "overview", "index": 0},
            {"title": "Ứng dụng", "slug": "application", "index": 1},
        ]})
        self.run_script(FINISH)
        for path in self.knowledge.glob("*/*.yml"):
            data = self.load(path)
            data["topic"] = SUBJECT + " - Data Oriented Programming"
            data["specialNote"] = ""
            self.write_yaml(path, data)
        self.info1 = self.knowledge / "1.overview" / "overview-001.yml"
        self.md1 = self.knowledge / "1.overview" / "overview-001.md"
        self.detail = self.knowledge / "menu-detail-status.yml"

    def run_script(self, script: Path, *args: str, ok: bool = True):
        result = subprocess.run(
            [sys.executable, str(script), "--module", str(self.module), *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            errors="replace",
            encoding="utf-8",
            check=False,
        )
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("BLOCKER:", result.stderr)
        return result

    @staticmethod
    def load(path: Path):
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    @staticmethod
    def write_yaml(path: Path, data):
        path.write_text(yaml.safe_dump(
            data, allow_unicode=True, sort_keys=False, width=120
        ), encoding="utf-8")

    def finished(self, path: Path) -> None:
        data = self.load(path)
        data["status"] = "WRITTEN"
        self.write_yaml(path, data)
        path.with_suffix(".md").write_text("# Article\n\nSome content.\n", encoding="utf-8")

    def test_refresh_and_special_note_target_only_selected_language(self):
        original_vi = self.detail.read_bytes()
        self.run_script(PRESTART, "--lang", "en")
        en = self.module / "content" / "knowledge" / "en"
        self.write_yaml(en / "note.yml", {
            "subject": SUBJECT, "detailName": "Data Oriented Programming",
            "specialNote": "English note",
        })
        self.write_yaml(en / "menu.yml", {
            "menu": [{"level1": "Overview", "level2": ["Why DOP?"]}],
        })
        self.write_yaml(en / "menu-level-1-slug.yml", {
            "menu": [{"title": "Overview", "slug": "overview", "index": 0}],
        })
        self.run_script(FINISH, "--lang", "en")
        for path in en.glob("*/*.yml"):
            data = self.load(path)
            data["topic"] = SUBJECT + " - Data Oriented Programming"
            data["specialNote"] = "English note"
            self.write_yaml(path, data)
        en_info = en / "1.overview" / "overview-001.yml"
        self.finished(en_info)
        self.run_script(REFRESH, "--lang", "en", "--verify")
        en_detail = self.load(en / "menu-detail-status.yml")
        self.assertEqual(en_detail["menu"][0]["childs"][0]["status"], "WRITTEN")
        self.run_script(MODIFY, "--lang", "en", "--mode", "add",
                        "--special-note", "Explain tradeoffs")
        self.assertIn("Explain tradeoffs", self.load(en / "note.yml")["specialNote"])
        self.assertEqual(original_vi, self.detail.read_bytes())

    def test_refresh_no_changes_preserves_bytes(self):
        before = self.detail.read_bytes()
        result = self.run_script(REFRESH)
        self.assertIn("UNCHANGED", result.stdout)
        self.assertIn("lessons=3", result.stdout)
        self.assertEqual(self.detail.read_bytes(), before)

    def test_refresh_keeps_new_step5_metadata_unchanged(self):
        (self.knowledge / "note.yml").unlink()
        for path in self.knowledge.glob("*/*.yml"):
            info = self.load(path)
            info.pop("topic", None)
            info.pop("specialNote", None)
            self.write_yaml(path, info)
        detail = self.load(self.detail)
        first = detail["menu"][0]["childs"][0]
        first.update({
            "difficult": "INTERMEDIATE",
            "focus": "Tổ chức dữ liệu",
            "problemSolved": "Giảm phụ thuộc",
            "mechanism": "Tách xử lý",
            "applicationValue": "Kiểm thử độc lập",
            "summary": "# 0. Định hướng học tập\n\n## 1. Mục đích\n",
        })
        self.write_yaml(self.detail, detail)
        before = self.load(self.detail)
        self.finished(self.info1)
        self.run_script(REFRESH)
        after = self.load(self.detail)
        self.assertEqual(after["menu"][0]["childs"][0]["status"], "WRITTEN")
        before["menu"][0]["childs"][0]["status"] = "WRITTEN"
        self.assertEqual(after, before)

    def test_refresh_supports_new_schema_without_note_or_legacy_fields(self):
        (self.knowledge / "note.yml").unlink()
        for info_path in self.knowledge.glob("*/*.yml"):
            info = self.load(info_path)
            info.pop("topic", None)
            info.pop("specialNote", None)
            self.write_yaml(info_path, info)
        before = self.detail.read_bytes()
        self.run_script(REFRESH, "--dry-run")
        self.run_script(REFRESH)
        self.assertEqual(self.detail.read_bytes(), before)
        self.finished(self.info1)
        self.run_script(REFRESH)
        self.assertEqual(
            self.load(self.detail)["menu"][0]["childs"][0]["status"], "WRITTEN"
        )
        self.run_script(MODIFY, "--mode", "add", "--special-note", "Legacy only", ok=False)
        self.assertFalse((self.knowledge / "note.yml").exists())
        self.assertNotIn("specialNote", self.load(self.info1))

    def test_refresh_writes_only_status_and_is_idempotent(self):
        self.finished(self.info1)
        before = self.detail.read_text(encoding="utf-8")
        dry = self.run_script(REFRESH, "--dry-run")
        self.assertIn("statuses_changed=1", dry.stdout)
        self.assertEqual(self.detail.read_text(encoding="utf-8"), before)
        self.run_script(REFRESH)
        after = self.detail.read_text(encoding="utf-8")
        self.assertIn("status: WRITTEN", after)
        self.assertEqual(after.count('status: ""'), 2)
        self.assertEqual(
            self.load(self.detail)["menu"][0]["childs"][0]["status"], "WRITTEN"
        )
        self.assertEqual(before.replace('status: ""', "status: WRITTEN", 1), after)
        self.run_script(REFRESH)
        self.assertEqual(after, self.detail.read_text(encoding="utf-8"))

    def test_refresh_does_not_rewrite_status_inside_summary_markdown(self):
        self.finished(self.info1)
        original = self.detail.read_text(encoding="utf-8")
        search = '    summary: ""'
        self.assertIn(search, original)
        inside = (
            "    summary: |-\n"
            "      ## Summary block\n"
            "      status: DO_NOT_TOUCH\n"
            "      - This is Markdown, not a YAML child status\n"
        )
        self.detail.write_text(original.replace(search, inside, 1), encoding="utf-8")
        self.run_script(REFRESH)
        updated = self.detail.read_text(encoding="utf-8")
        self.assertIn("      status: DO_NOT_TOUCH\n", updated)
        self.assertEqual(
            self.load(self.detail)["menu"][0]["childs"][0]["summary"],
            "## Summary block\nstatus: DO_NOT_TOUCH\n- This is Markdown, not a YAML child status",
        )
        self.assertEqual(
            self.load(self.detail)["menu"][0]["childs"][0]["status"], "WRITTEN"
        )
        self.run_script(REFRESH)
        self.assertEqual(self.detail.read_text(encoding="utf-8"), updated)

    def test_refresh_rejects_written_with_empty_md_before_writing(self):
        data = self.load(self.info1)
        data["status"] = "WRITTEN"
        self.write_yaml(self.info1, data)
        before = self.detail.read_bytes()
        self.run_script(REFRESH, ok=False)
        self.assertEqual(self.detail.read_bytes(), before)

    def test_refresh_rejects_missing_and_invalid_info(self):
        before = self.detail.read_bytes()
        self.info1.unlink()
        self.run_script(REFRESH, ok=False)
        self.assertEqual(self.detail.read_bytes(), before)
        self.write_yaml(self.info1, {
            "topic": SUBJECT + " - Data Oriented Programming",
            "specialNote": "", "menuLevel1": "Sai", "menuLevel2": "DOP là gì?",
            "status": "",
        })
        self.run_script(REFRESH, ok=False)
        self.assertEqual(self.detail.read_bytes(), before)

    def test_verify_only_when_every_lesson_completed(self):
        self.run_script(REFRESH, "--verify", ok=False)
        for file in self.knowledge.glob("*/*.yml"):
            self.finished(file)
        result = self.run_script(REFRESH, "--verify")
        self.assertIn("verified=True", result.stdout)
        self.assertEqual(
            [c["status"] for m in self.load(self.detail)["menu"] for c in m["childs"]],
            ["WRITTEN"] * 3,
        )

    def test_unknown_status_can_refresh_but_does_not_pass_verify(self):
        self.finished(self.info1)
        data = self.load(self.info1)
        data["status"] = "REVIEWED"
        self.write_yaml(self.info1, data)
        self.run_script(REFRESH)
        self.assertEqual(self.load(self.detail)["menu"][0]["childs"][0]["status"], "REVIEWED")
        self.run_script(REFRESH, "--verify", ok=False)

    def test_add_updates_note_and_all_lessons_without_other_changes(self):
        original_info = self.load(self.info1)
        original_detail = self.detail.read_bytes()
        source_menu = (self.knowledge / "menu.yml").read_bytes()
        note = "Ưu tiên ví dụ Java 21"
        dry = self.run_script(MODIFY, "--mode", "add", "--special-note", note, "--dry-run")
        self.assertIn("changed_files=4", dry.stdout)
        self.assertEqual(self.load(self.knowledge / "note.yml")["specialNote"], "")
        result = self.run_script(MODIFY, "--mode", "add", "--special-note", note)
        self.assertIn("changed_files=4", result.stdout)
        self.assertEqual(self.load(self.knowledge / "note.yml")["specialNote"], note)
        for path in self.knowledge.glob("*/*.yml"):
            info = self.load(path)
            self.assertEqual(info["specialNote"], note)
        updated = self.load(self.info1)
        self.assertEqual({k: v for k, v in updated.items() if k != "specialNote"},
                         {k: v for k, v in original_info.items() if k != "specialNote"})
        self.assertEqual(self.detail.read_bytes(), original_detail)
        self.assertEqual((self.knowledge / "menu.yml").read_bytes(), source_menu)
        self.assertEqual(self.md1.read_bytes(), b"")
        self.run_script(FINISH, "--dry-run")
        rerun = self.run_script(MODIFY, "--mode", "add", "--special-note", note)
        self.assertIn("changed_files=0", rerun.stdout)

    def test_add_multiple_notes_and_no_repeating_prior_block(self):
        self.run_script(MODIFY, "--mode", "add", "--special-note", "Dùng Java 21")
        self.run_script(MODIFY, "--mode", "add", "--special-note", "Nêu trade-offs")
        self.assertEqual(self.load(self.knowledge / "note.yml")["specialNote"],
                         "Dùng Java 21\n\nNêu trade-offs")
        same = self.run_script(MODIFY, "--mode", "add", "--special-note", "Dùng Java 21")
        self.assertIn("changed_files=0", same.stdout)

    def test_replace_overwrites_both_note_and_preexisting_per_lesson_divergence(self):
        self.run_script(MODIFY, "--mode", "add", "--special-note", "Note A")
        self.finished(self.info1)
        data = self.load(self.info1)
        data["specialNote"] = "Lesson-specific note"
        self.write_yaml(self.info1, data)
        before_md = self.md1.read_bytes()
        before_detail = self.detail.read_bytes()
        self.run_script(MODIFY, "--mode", "replace", "--special-note", "Note B")
        self.assertEqual(self.load(self.knowledge / "note.yml")["specialNote"], "Note B")
        for path in self.knowledge.glob("*/*.yml"):
            self.assertEqual(self.load(path)["specialNote"], "Note B")
        self.assertEqual(self.load(self.info1)["status"], "WRITTEN")
        self.assertEqual(self.md1.read_bytes(), before_md)
        self.assertEqual(self.detail.read_bytes(), before_detail)

    def test_replace_can_clear_all_notes_with_bare_flag(self):
        self.run_script(MODIFY, "--mode", "add", "--special-note", "A")
        self.run_script(MODIFY, "--mode", "replace", "--special-note")
        for path in [self.knowledge / "note.yml", *self.knowledge.glob("*/*.yml")]:
            self.assertEqual(self.load(path)["specialNote"], "")
        self.run_script(FINISH, "--dry-run")

    def test_add_rejects_mismatched_existing_note(self):
        bad = self.load(self.info1)
        bad["specialNote"] = "Private note"
        self.write_yaml(self.info1, bad)
        before = {p: p.read_bytes() for p in [self.knowledge / "note.yml",
                                               *self.knowledge.glob("*/*.yml")]}
        self.run_script(MODIFY, "--mode", "add", "--special-note", "New", ok=False)
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data)

    def test_add_empty_is_rejected(self):
        self.run_script(MODIFY, "--mode", "add", "--special-note", "", ok=False)

    def test_multiline_note_file_and_repeated_add(self):
        text = "Yêu cầu Java 21\n- Giải thích\n- Ví dụ cụ thể"
        source = self.root / "new-note.txt"
        source.write_text(text, encoding="utf-8")
        self.run_script(MODIFY, "--mode", "add", "--note-file", str(source))
        self.assertEqual(self.load(self.knowledge / "note.yml")["specialNote"], text)
        self.assertEqual(self.load(self.info1)["specialNote"], text)
        self.run_script(MODIFY, "--mode", "add", "--note-file", str(source))
        self.assertEqual(self.load(self.info1)["specialNote"], text)

    def test_bad_yml_prevents_partial_changes(self):
        last = self.knowledge / "2.application" / "application-001.yml"
        last.write_text("topic: bad\ntopic: bad2\n", encoding="utf-8")
        before = self.load(self.knowledge / "note.yml")["specialNote"]
        self.run_script(MODIFY, "--mode", "replace", "--special-note", "New", ok=False)
        self.assertEqual(self.load(self.knowledge / "note.yml")["specialNote"], before)

    def test_invalid_detail_status_tree_blocks_both_scripts(self):
        detail = self.load(self.detail)
        detail["menu"][0]["childs"][0]["slug"] = "wrong-001"
        self.write_yaml(self.detail, detail)
        self.run_script(REFRESH, ok=False)
        self.run_script(MODIFY, "--mode", "replace", "--special-note", "New", ok=False)

    def test_add_no_longer_updates_unrelated_status_after_writing(self):
        self.finished(self.info1)
        original = self.load(self.info1)["status"]
        self.run_script(MODIFY, "--mode", "add", "--special-note", "Scope")
        self.run_script(REFRESH)
        self.assertEqual(self.load(self.info1)["status"], original)
        self.assertEqual(self.load(self.detail)["menu"][0]["childs"][0]["status"], "WRITTEN")


if __name__ == "__main__":
    unittest.main()
