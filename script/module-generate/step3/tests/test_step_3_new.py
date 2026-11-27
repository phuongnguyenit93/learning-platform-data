"""Black-box regression tests for the local STEP_3_NEW Python workflow."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml


SCRIPT_DIR = Path(__file__).resolve().parents[1]
PRESTART = SCRIPT_DIR / "generate_menu_skeleton.py"
FINISH = SCRIPT_DIR / "generate_menu_detail.py"
SUBJECT = "OBJECT_ORIENTED_PROGRAMMING"


class Step3NewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.module = Path(self.tmp.name) / "module" / "oop"
        self.module.mkdir(parents=True)
        (self.module / "module-info.json").write_text(
            json.dumps({"SERVICE_NAME": {"VALUE": SUBJECT}}, ensure_ascii=False),
            encoding="utf-8",
        )
        self.knowledge = self.module / "content" / "knowledge" / "vi"

    def run_script(self, script: Path, *args: str, ok: bool = True) -> subprocess.CompletedProcess:
        result = subprocess.run(
            [sys.executable, str(script), "--module", str(self.module), *args],
            cwd=self.tmp.name,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("BLOCKER:", result.stderr)
        return result

    def write_yaml(self, name: str, data: dict) -> None:
        (self.knowledge / name).write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )

    def load_yaml(self, path: Path) -> dict:
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    def init_valid(self, note: str = "Ưu tiên Java 21\nCó ví dụ") -> None:
        self.run_script(PRESTART)
        self.write_yaml("menu.yml", {
            "menu": [
                {"level1": "Tư duy OOP", "level2": ["OOP là gì?", "Đối tượng: trạng thái và hành vi"]},
                {"level1": "Thực hành OOP", "level2": ["Xây dựng ứng dụng"]},
            ]
        })
        self.write_yaml("menu-level-1-slug.yml", {
            "menu": [
                {"title": "Tư duy OOP", "slug": "oop-basic", "index": 0},
                {"title": "Thực hành OOP", "slug": "oop-practice", "index": 1},
            ]
        })

    def test_prestart_creates_two_valid_yaml_files(self) -> None:
        self.run_script(PRESTART)
        self.assertEqual(
            {p.name for p in self.knowledge.iterdir()},
            {"menu.yml", "menu-level-1-slug.yml"},
        )
        self.assertEqual(self.load_yaml(self.knowledge / "menu.yml"), {"menu": []})
        self.assertEqual(self.load_yaml(self.knowledge / "menu-level-1-slug.yml"), {"menu": []})
        self.assertFalse((self.knowledge / "note.yml").exists())

    def test_prestart_dry_run_then_create(self) -> None:
        self.run_script(PRESTART, "--dry-run")
        self.assertFalse(self.knowledge.exists())
        self.run_script(PRESTART)
        self.assertFalse((self.knowledge / "note.yml").exists())

    def test_prestart_idempotent_and_preserves_legacy_note(self) -> None:
        self.run_script(PRESTART)
        self.write_yaml("note.yml", {
            "subject": SUBJECT, "detailName": "Đã điền", "specialNote": "A"
        })
        before = (self.knowledge / "note.yml").read_bytes()
        self.run_script(PRESTART)
        self.assertEqual(self.load_yaml(self.knowledge / "note.yml")["detailName"], "Đã điền")
        self.assertEqual((self.knowledge / "note.yml").read_bytes(), before)
        self.assertEqual(self.load_yaml(self.knowledge / "note.yml")["specialNote"], "A")

    def test_module_info_takes_priority_over_legacy_master(self) -> None:
        (self.module / "master.json").write_text(
            json.dumps({"SERVICE_NAME": {"VALUE": "BAD_LEGACY_NAME"}}),
            encoding="utf-8",
        )
        self.run_script(PRESTART)
        self.assertEqual(
            self.load_yaml(self.knowledge / "menu.yml"), {"menu": []}
        )

    def test_generator_preserves_existing_legacy_lesson_fields(self) -> None:
        self.init_valid()
        self.run_script(FINISH)
        info_path = self.knowledge / "1.oop-basic" / "oop-basic-001.yml"
        info = self.load_yaml(info_path)
        info["topic"] = "Existing topic"
        info["specialNote"] = "Existing user note"
        self.write_yaml("1.oop-basic/oop-basic-001.yml", info)
        legacy_note = self.knowledge / "note.yml"
        legacy_note.write_text(
            'subject: OBJECT_ORIENTED_PROGRAMMING\n'
            'detailName: "Existing"\nspecialNote: "Existing user note"\n',
            encoding="utf-8",
        )
        before_info = info_path.read_bytes()
        before_note = legacy_note.read_bytes()
        self.run_script(PRESTART)
        self.run_script(FINISH)
        self.assertEqual(info_path.read_bytes(), before_info)
        self.assertEqual(legacy_note.read_bytes(), before_note)
        for other in self.knowledge.glob("*/*.yml"):
            if other != info_path:
                self.assertNotIn("topic", self.load_yaml(other))
                self.assertNotIn("specialNote", self.load_yaml(other))

    def test_full_flow_creates_correct_structure_and_is_restart_safe(self) -> None:
        self.init_valid()
        dry_run = self.run_script(FINISH, "--dry-run")
        self.assertIn("new_files=7", dry_run.stdout)
        self.assertFalse((self.knowledge / "1.oop-basic").exists())
        self.assertFalse((self.knowledge / "menu-detail-status.yml").exists())
        self.run_script(FINISH)
        self.assertEqual(
            {p.name for p in self.knowledge.iterdir() if p.is_dir()},
            {"1.oop-basic", "2.oop-practice"},
        )
        self.assertEqual(
            {p.name for p in (self.knowledge / "1.oop-basic").iterdir()},
            {"oop-basic-001.yml", "oop-basic-001.md", "oop-basic-002.yml", "oop-basic-002.md"},
        )
        detail_path = self.knowledge / "menu-detail-status.yml"
        self.assertEqual(self.load_yaml(detail_path), {
            "menu": [
                {"slug": "oop-basic", "title": "Tư duy OOP", "childs": [
                    {"slug": "oop-basic-001", "title": "OOP là gì?", "status": "",
                     "difficult": "", "focus": "", "problemSolved": "",
                     "mechanism": "", "applicationValue": "", "summary": ""},
                    {"slug": "oop-basic-002", "title": "Đối tượng: trạng thái và hành vi",
                     "status": "", "difficult": "", "focus": "", "problemSolved": "",
                     "mechanism": "", "applicationValue": "", "summary": ""},
                ]},
                {"slug": "oop-practice", "title": "Thực hành OOP", "childs": [
                    {"slug": "oop-practice-001", "title": "Xây dựng ứng dụng", "status": "",
                     "difficult": "", "focus": "", "problemSolved": "",
                     "mechanism": "", "applicationValue": "", "summary": ""},
                ]},
            ],
        })
        self.assertEqual(detail_path.read_text(encoding="utf-8").count('status: ""'), 3)
        info = self.load_yaml(self.knowledge / "1.oop-basic" / "oop-basic-001.yml")
        self.assertEqual(info, {
            "menuLevel1": "Tư duy OOP",
            "menuLevel2": "OOP là gì?",
            "status": "",
        })
        self.assertEqual((self.knowledge / "1.oop-basic" / "oop-basic-001.md").read_text(encoding="utf-8"), "")
        self.assertIn('status: ""', (self.knowledge / "1.oop-basic" / "oop-basic-001.yml").read_text(encoding="utf-8"))
        md = self.knowledge / "1.oop-basic" / "oop-basic-001.md"
        md.write_text("# Human-authored Knowledge\n", encoding="utf-8")
        info["status"] = "WRITTEN"
        self.write_yaml("1.oop-basic/oop-basic-001.yml", info)
        self.run_script(FINISH)
        self.assertEqual(md.read_text(encoding="utf-8"), "# Human-authored Knowledge\n")
        self.assertEqual(self.load_yaml(self.knowledge / "1.oop-basic" / "oop-basic-001.yml")["status"], "WRITTEN")
        # Finish does not synchronize status: the consolidated file remains unchanged.
        self.assertEqual(self.load_yaml(detail_path)["menu"][0]["childs"][0]["status"], "")

    def test_preserves_existing_detail_status_without_syncing_from_lessons(self) -> None:
        self.init_valid()
        self.run_script(FINISH)
        path = self.knowledge / "menu-detail-status.yml"
        detail = self.load_yaml(path)
        detail["menu"][0]["childs"][0]["status"] = "IN_PROGRESS"
        self.write_yaml("menu-detail-status.yml", detail)
        before = path.read_bytes()
        info = self.load_yaml(self.knowledge / "1.oop-basic" / "oop-basic-001.yml")
        info["status"] = "WRITTEN"
        self.write_yaml("1.oop-basic/oop-basic-001.yml", info)
        self.run_script(FINISH)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.load_yaml(path)["menu"][0]["childs"][0]["status"], "IN_PROGRESS")

    def test_rejects_stale_detail_status_structure_before_file_creation(self) -> None:
        self.init_valid()
        self.run_script(FINISH)
        path = self.knowledge / "menu-detail-status.yml"
        detail = self.load_yaml(path)
        detail["menu"][0]["childs"][0]["slug"] = "wrong-001"
        self.write_yaml("menu-detail-status.yml", detail)
        md = self.knowledge / "1.oop-basic" / "oop-basic-002.md"
        md.unlink()
        self.run_script(FINISH, ok=False)
        self.assertFalse(md.exists())
        self.assertEqual(self.load_yaml(path)["menu"][0]["childs"][0]["slug"], "wrong-001")

    def test_rejects_non_string_detail_status(self) -> None:
        self.init_valid()
        self.run_script(FINISH)
        path = self.knowledge / "menu-detail-status.yml"
        detail = self.load_yaml(path)
        detail["menu"][0]["childs"][0]["status"] = None
        self.write_yaml("menu-detail-status.yml", detail)
        self.run_script(FINISH, ok=False)

    def test_can_backfill_detail_status_without_overwriting_existing_lessons(self) -> None:
        self.init_valid()
        self.run_script(FINISH)
        path = self.knowledge / "menu-detail-status.yml"
        path.unlink()
        md = self.knowledge / "1.oop-basic" / "oop-basic-001.md"
        md.write_text("# Already written", encoding="utf-8")
        info = self.load_yaml(self.knowledge / "1.oop-basic" / "oop-basic-001.yml")
        info["status"] = "WRITTEN"
        self.write_yaml("1.oop-basic/oop-basic-001.yml", info)
        result = self.run_script(FINISH)
        self.assertIn("created=1", result.stdout)
        self.assertEqual(self.load_yaml(path)["menu"][0]["childs"][0]["status"], "")
        self.assertEqual(md.read_text(encoding="utf-8"), "# Already written")
        self.assertEqual(self.load_yaml(self.knowledge / "1.oop-basic" / "oop-basic-001.yml")["status"], "WRITTEN")

    def test_backfills_missing_child_fields_without_touching_status_or_summary(self) -> None:
        self.init_valid()
        self.run_script(FINISH)
        path = self.knowledge / "menu-detail-status.yml"
        detail = self.load_yaml(path)
        for chapter in detail["menu"]:
            for child in chapter["childs"]:
                for key in ("difficult", "focus", "problemSolved",
                            "mechanism", "applicationValue", "summary"):
                    del child[key]
        detail["menu"][0]["childs"][0]["status"] = "IN_PROGRESS"
        self.write_yaml("menu-detail-status.yml", detail)
        path.write_text(path.read_text(encoding="utf-8") + "# A human note\n", encoding="utf-8")
        original = path.read_bytes()

        dryrun = self.run_script(FINISH, "--dry-run")
        self.assertIn("missing_detail_fields=18", dryrun.stdout)
        self.assertEqual(path.read_bytes(), original)
        applied = self.run_script(FINISH)
        self.assertIn("added_detail_fields=18", applied.stdout)
        updated = self.load_yaml(path)
        self.assertEqual(updated["menu"][0]["childs"][0]["status"], "IN_PROGRESS")
        self.assertTrue(path.read_text(encoding="utf-8").endswith("# A human note\n"))
        for chapter in updated["menu"]:
            for child in chapter["childs"]:
                self.assertEqual([child[key] for key in
                                 ("difficult", "focus", "problemSolved",
                                  "mechanism", "applicationValue", "summary")], [""] * 6)
        after = path.read_bytes()
        self.run_script(FINISH)
        self.assertEqual(path.read_bytes(), after)

    def test_preserves_nonempty_new_fields_on_finish_rerun(self) -> None:
        self.init_valid()
        self.run_script(FINISH)
        path = self.knowledge / "menu-detail-status.yml"
        detail = self.load_yaml(path)
        first = detail["menu"][0]["childs"][0]
        first["status"] = "REVIEWED"
        first["difficult"] = "ADVANCED"
        first["focus"] = "Trách nhiệm của đối tượng"
        first["problemSolved"] = "Ranh giới trách nhiệm không rõ"
        first["mechanism"] = "Đóng gói và ủy quyền"
        first["applicationValue"] = "Thiết kế dễ bảo trì"
        first["summary"] = "# Tóm tắt\n\nstatus: LEARNING"
        self.write_yaml("menu-detail-status.yml", detail)
        before = path.read_bytes()
        self.run_script(FINISH)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.load_yaml(path)["menu"][0]["childs"][0], first)

    def test_rejects_invalid_new_field_without_writing(self) -> None:
        self.init_valid()
        self.run_script(FINISH)
        path = self.knowledge / "menu-detail-status.yml"
        detail = self.load_yaml(path)
        detail["menu"][0]["childs"][0]["difficult"] = "UNKNOWN_LEVEL"
        self.write_yaml("menu-detail-status.yml", detail)
        before = path.read_bytes()
        self.run_script(FINISH, ok=False)
        self.assertEqual(path.read_bytes(), before)

    def test_legacy_detail_fields_are_preserved_without_auto_migration(self) -> None:
        self.init_valid()
        self.run_script(FINISH)
        path = self.knowledge / "menu-detail-status.yml"
        detail = self.load_yaml(path)
        for chapter in detail["menu"]:
            for child in chapter["childs"]:
                for key in ("focus", "problemSolved", "mechanism", "applicationValue"):
                    del child[key]
                child["keyQuestion"] = "Câu hỏi cũ"
                child["valueForModule"] = "Giá trị cũ"
                child["mindset"] = "Tư duy cũ"
        self.write_yaml("menu-detail-status.yml", detail)
        before = path.read_bytes()
        dryrun = self.run_script(FINISH, "--dry-run")
        self.assertIn("missing_detail_fields=0", dryrun.stdout)
        self.run_script(FINISH)
        self.assertEqual(path.read_bytes(), before)

    def test_can_generate_without_note_or_detail_name(self) -> None:
        self.run_script(PRESTART)
        self.write_yaml("menu.yml", {"menu": [{"level1": "Basic", "level2": ["What?"]}]})
        self.write_yaml("menu-level-1-slug.yml", {"menu": [{"title": "Basic", "slug": "basic", "index": 0}]})
        self.run_script(FINISH)
        self.assertTrue((self.knowledge / "1.basic/basic-001.yml").exists())
        self.assertEqual(
            set(self.load_yaml(self.knowledge / "1.basic/basic-001.yml")),
            {"menuLevel1", "menuLevel2", "status"},
        )

    def test_rejects_invalid_index_title_and_slug_before_writes(self) -> None:
        self.init_valid()
        good_slugs = self.load_yaml(self.knowledge / "menu-level-1-slug.yml")
        bad_cases = [
            [{"title": "Tư duy OOP", "slug": "oop-basic", "index": 1},
             {"title": "Thực hành OOP", "slug": "oop-practice", "index": 2}],
            [{"title": "Wrong title", "slug": "oop-basic", "index": 0},
             {"title": "Thực hành OOP", "slug": "oop-practice", "index": 1}],
            [{"title": "Tư duy OOP", "slug": "../evil", "index": 0},
             {"title": "Thực hành OOP", "slug": "oop-practice", "index": 1}],
            [{"title": "Tư duy OOP", "slug": "oop-basic", "index": 0},
             {"title": "Thực hành OOP", "slug": "oop-basic", "index": 1}],
        ]
        for items in bad_cases:
            self.write_yaml("menu-level-1-slug.yml", {"menu": items})
            self.run_script(FINISH, ok=False)
            self.assertFalse((self.knowledge / "1.oop-basic").exists())
        self.write_yaml("menu-level-1-slug.yml", good_slugs)

    def test_rejects_existing_metadata_conflict_without_deleting_content(self) -> None:
        self.init_valid()
        self.run_script(FINISH)
        md = self.knowledge / "1.oop-basic" / "oop-basic-001.md"
        md.write_text("valuable", encoding="utf-8")
        info = self.load_yaml(self.knowledge / "1.oop-basic" / "oop-basic-001.yml")
        info["menuLevel2"] = "Different"
        self.write_yaml("1.oop-basic/oop-basic-001.yml", info)
        self.run_script(FINISH, ok=False)
        self.assertEqual(md.read_text(encoding="utf-8"), "valuable")

    def test_rejects_stale_generated_folders_and_files(self) -> None:
        self.init_valid()
        (self.knowledge / "1.old").mkdir()
        self.run_script(FINISH, ok=False)
        (self.knowledge / "1.old").rmdir()
        self.run_script(FINISH)
        stale = self.knowledge / "1.oop-basic" / "oop-basic-099.md"
        stale.write_text("stale authored material", encoding="utf-8")
        self.run_script(FINISH, ok=False)
        self.assertEqual(stale.read_text(encoding="utf-8"), "stale authored material")

    def test_rejects_duplicate_yaml_keys(self) -> None:
        self.init_valid()
        (self.knowledge / "menu.yml").write_text(
            "menu: []\nmenu: []\n", encoding="utf-8"
        )
        self.run_script(FINISH, ok=False)
        self.assertFalse((self.knowledge / "1.oop-basic").exists())

    def test_rejects_more_than_999_lessons(self) -> None:
        self.init_valid()
        self.write_yaml("menu.yml", {
            "menu": [{"level1": "One", "level2": [f"Lesson {i}" for i in range(1000)]}]
        })
        self.write_yaml("menu-level-1-slug.yml", {
            "menu": [{"title": "One", "slug": "one", "index": 0}]
        })
        self.run_script(FINISH, ok=False)
        self.assertFalse((self.knowledge / "1.one").exists())

    def test_two_language_folders_are_independent(self) -> None:
        self.init_valid()
        self.run_script(FINISH, "--lang", "vi")
        vi_bytes = {
            str(p.relative_to(self.knowledge)): p.read_bytes()
            for p in self.knowledge.rglob("*") if p.is_file()
        }
        self.run_script(PRESTART, "--lang", "en")
        english = self.module / "content" / "knowledge" / "en"
        self.assertFalse((english / "note.yml").exists())
        self.assertFalse((english / "menu-detail-status.yml").exists())
        (english / "menu.yml").write_text(yaml.safe_dump({
            "menu": [{"level1": "Basics", "level2": ["What is OOP?"]}],
        }, sort_keys=False), encoding="utf-8")
        (english / "menu-level-1-slug.yml").write_text(yaml.safe_dump({
            "menu": [{"title": "Basics", "slug": "basics", "index": 0}],
        }, sort_keys=False), encoding="utf-8")
        self.run_script(FINISH, "--language", "en")
        self.assertTrue((english / "1.basics" / "basics-001.md").is_file())
        self.assertEqual(
            {str(p.relative_to(self.knowledge)): p.read_bytes()
             for p in self.knowledge.rglob("*") if p.is_file()}, vi_bytes
        )
        self.run_script(FINISH, "--lang", "en", "--dry-run")
        self.run_script(PRESTART, "--lang", "../vi", ok=False)
        self.run_script(FINISH, "--lang", "..", ok=False)

    def test_legacy_flat_knowledge_is_blocked(self) -> None:
        flat = self.module / "content" / "knowledge"
        flat.mkdir(parents=True)
        (flat / "menu.yml").write_text("menu: []\n", encoding="utf-8")
        self.run_script(PRESTART, "--lang", "vi", ok=False)
        self.assertFalse((flat / "vi").exists())

    def test_bad_service_name_prevents_prestart(self) -> None:
        (self.module / "module-info.json").write_text(
            json.dumps({"SERVICE_NAME": {"VALUE": "../escape"}}), encoding="utf-8"
        )
        self.run_script(PRESTART, ok=False)
        self.assertFalse(self.knowledge.exists())


if __name__ == "__main__":
    unittest.main()
