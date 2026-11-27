"""Offline tests for STEP 6 split, Knowledge merge and gated cleanup."""

from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
import split_menu
import merge_menu
import delete_temp_split_menu


def load_hyphen_script(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


merge_related = load_hyphen_script("merge-readme-related.py", "step6_related_merge")
export_assessments = load_hyphen_script("export-casestudy-quiz-interview.py", "step6_export")


SUMMARY = """# 0. Định hướng học tập

## 1. Mục đích của bài học

**{title}**

Bài học giúp người đọc vận dụng kiến thức vào vấn đề cụ thể.

## 2. Những câu hỏi người học phải tự trả lời được

### Cơ chế chính
1. Thành phần này hoạt động như thế nào?
2. Khi nào cần áp dụng?

## 3. Sau khi học xong, người học phải đạt được điều gì?

| Năng lực | Kết quả mong đợi |
| --- | --- |
| Phân tích cơ chế | Giải thích và kiểm chứng bằng ví dụ thực tế |
"""


class Step6SplitMergeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "java-learning"
        self.root = self.repo / "module" / "platform" / "sample"
        self.root.mkdir(parents=True)
        self.mock_root = patch.object(split_menu, "REPO_ROOT", self.repo)
        self.mock_root.start()
        self.addCleanup(self.mock_root.stop)
        self.root.joinpath("module_activate.json").write_text(
            json.dumps({"isModule": True}), encoding="utf-8"
        )
        self.root.joinpath("module-info.json").write_text(
            json.dumps({
                "SERVICE_NAME": {"VALUE": "SAMPLE_STUDY"},
                "SERVICE_NAME_DESCRIBE": {"VALUE": "Sample for contract tests"},
                "MODULE_LANGUAGE": {"VALUE": ["vi", "en"]},
                "SPECIAL_NOTE": {"VALUE": ""},
            }), encoding="utf-8"
        )
        self.knowledge = self.root / "content" / "knowledge" / "vi"
        self.knowledge.mkdir(parents=True)
        self.write(self.knowledge / "menu.yml", {
            "menu": [{"level1": "Tổng quan", "level2": ["Khái niệm", "Cơ chế"]},
                     {"level1": "Ứng dụng", "level2": ["Thực hành"]}],
        })
        self.write(self.knowledge / "menu-level-1-slug.yml", {
            "menu": [{"title": "Tổng quan", "slug": "overview", "index": 0},
                     {"title": "Ứng dụng", "slug": "application", "index": 1}],
        })
        chapters = []
        for chapter_idx, (slug, title, lessons) in enumerate([
            ("overview", "Tổng quan", ["Khái niệm", "Cơ chế"]),
            ("application", "Ứng dụng", ["Thực hành"]),
        ], 1):
            folder = self.knowledge / f"{chapter_idx}.{slug}"
            folder.mkdir()
            children = []
            for i, lesson_title in enumerate(lessons, 1):
                stem = f"{slug}-{i:03d}"
                self.write(folder / f"{stem}.yml", {
                    "menuLevel1": title, "menuLevel2": lesson_title, "status": "WRITTEN"
                })
                (folder / f"{stem}.md").write_text(
                    f"# {lesson_title}\n\nGiải thích đầy đủ {lesson_title}.\n",
                    encoding="utf-8"
                )
                children.append({
                    "slug": stem, "title": lesson_title, "status": "WRITTEN",
                    "difficult": "", "focus": "", "problemSolved": "",
                    "mechanism": "", "applicationValue": "", "summary": "",
                })
            chapters.append({"slug": slug, "title": title, "childs": children})
        self.source = self.knowledge / "menu-detail-status.yml"
        self.write(self.source, {"menu": chapters})
        self.stage = self.repo / "temp" / "step6" / "SAMPLE_STUDY" / "vi"
        self.assess_stage = self.root / "content" / "temp" / "step5"
        for folder in ("raw", "format", "status"):
            (self.assess_stage / folder).mkdir(parents=True)
        assessments = {
            "quiz": {
                "quiz": [{"groupID": 1, "groupName": "Nền tảng", "questions": [{
                    "index": 0, "question": "Khái niệm?",
                    "readmeRelated": {"anchorList": []},
                    "answers": [
                        {"id": letter, "answer": f"Đáp án {letter}",
                         "explanation": f"Giải thích {letter}"}
                        for letter in "ABCD"
                    ], "correctAnswerId": "A",
                }]}
                ]
            },
            "interview": {
                "interviewQuestion": [{
                    "groupID": 1, "groupName": "Nền tảng", "questions": [{
                        "index": 0, "question": "Trình bày khái niệm?",
                        "readmeRelated": {"anchorList": []},
                        "knowledge": "Nguyên lý nền", "answer": "Lý giải đầy đủ",
                    }],
                }]
            },
            "casestudy": {
                "caseStudy": [{"groupID": 1, "groupName": "Ứng dụng", "cases": [{
                    "index": 0, "situation": "Cần xử lý tình huống.",
                    "readmeRelated": {"anchorList": []},
                    "knowledge": "Cơ chế", "resolve": "Phân tích tình huống",
                    "answer": "Giải thích bằng văn bản không code.",
                }]}]
            },
        }
        for kind, data in assessments.items():
            self.write(self.assess_stage / "format" / f"{kind}.yml", data)
            (self.assess_stage / "raw" / f"{kind}.md").write_text(
                "Nội dung đã được Worker tạo\n", encoding="utf-8"
            )
            self.write(self.assess_stage / "status" / f"{kind}.yml", {
                "status": "Phase 3" if kind == "quiz" else "Phase 4"
            })
        for slug in ("overview", "application"):
            folder = self.assess_stage / "readme-related" / slug
            folder.mkdir(parents=True)
            for kind in assessments:
                (folder / f"{kind}.yml").write_bytes(b"")

    @staticmethod
    def write(path: Path, value: dict) -> None:
        path.write_text(yaml.safe_dump(
            value, allow_unicode=True, sort_keys=False, width=120
        ), encoding="utf-8")

    @staticmethod
    def read(path: Path) -> dict:
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    def fill(self) -> None:
        for number, slug in [(1, "overview"), (2, "application")]:
            yaml_file = self.stage / f"{number}-{slug}.yml"
            doc = self.read(yaml_file)
            for child in doc["menu"][0]["childs"]:
                child.update({
                    "difficult": "INTERMEDIATE", "focus": f"Trọng tâm {child['slug']}",
                    "problemSolved": f"Giải quyết {child['slug']}",
                    "mechanism": f"Cơ chế {child['slug']}",
                    "applicationValue": f"Ứng dụng {child['slug']}",
                    "summary": SUMMARY.format(title=child["title"]),
                })
            self.write(yaml_file, doc)
            self.write(self.stage / f"{number}-{slug}-status.yml", {"status": "WRITTEN"})
            for kind in ("quiz", "interview", "casestudy"):
                self.write(
                    self.assess_stage / "readme-related" / slug / f"{kind}.yml",
                    {"groups": []},
                )

    def complete(self) -> None:
        self.assertIn("MERGE_OK", merge_menu.merge(str(self.root)))
        self.assertIn("MERGE_OK", merge_related.merge_related(str(self.root)))
        self.assertIn("EXPORT_OK", export_assessments.export(str(self.root)))

    def test_full_split_merge_cleanup_and_restart_safe(self) -> None:
        original = self.source.read_bytes()
        self.assertIn("DRY_RUN", split_menu.split(str(self.root), dry_run=True))
        self.assertFalse(self.stage.exists())
        self.assertIn("SPLIT_OK", split_menu.split(str(self.root)))
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(len(list(self.stage.glob("*"))), 5)
        self.assertEqual(self.read(self.stage / "1-overview.yml")["menu"][0],
                         self.read(self.source)["menu"][0])
        self.assertIn("RESUMED", split_menu.split(str(self.root)))
        self.fill()
        self.assertIn("DRY_RUN", merge_menu.merge(str(self.root), dry_run=True))
        self.assertEqual(self.source.read_bytes(), original)
        self.assertIn("MERGE_OK", merge_menu.merge(str(self.root)))
        self.assertTrue((self.stage / "merged.json").exists())
        self.assertTrue(self.stage.exists(), "merge must never delete temp")
        self.assertEqual(self.read(self.source)["menu"][0]["childs"][0]["focus"],
                         "Trọng tâm overview-001")
        self.assertIn("ALREADY_MERGED", merge_menu.merge(str(self.root)))
        self.assertIn("MERGE_OK", merge_related.merge_related(str(self.root)))
        self.assertIn("EXPORT_OK", export_assessments.export(str(self.root)))
        self.assertIn("DRY_RUN", delete_temp_split_menu.cleanup(str(self.root), dry_run=True))
        self.assertTrue(self.stage.exists())
        self.assertIn("CLEANUP_OK", delete_temp_split_menu.cleanup(str(self.root)))
        self.assertFalse(self.stage.exists())
        self.assertFalse((self.repo / "temp" / "step6").exists())
        self.assertFalse(self.assess_stage.exists())
        self.assertIn("Trọng tâm overview-001", self.source.read_text(encoding="utf-8"))

    def test_step5_initializer_can_verify_step6_input_without_changes(self) -> None:
        generator = load_hyphen_script(
            "../step5/generate-temp-file.py", "step5_generation_contract"
        )
        files_before = {
            path: path.read_bytes()
            for path in self.assess_stage.rglob("*") if path.is_file()
        }
        with patch.object(generator, "REPO_ROOT", self.repo):
            result, missing = generator.prepare(str(self.root))
        self.assertEqual((result, missing), ("RESUMED", ()))
        for path, before in files_before.items():
            self.assertEqual(path.read_bytes(), before)

    def test_split_copies_original_chapter_raw_text(self) -> None:
        raw = self.source.read_text(encoding="utf-8")
        raw = raw.replace("\n- slug: application\n", "\n# Chương tiếp theo\n- slug: application\n")
        self.source.write_text(raw, encoding="utf-8")
        split_menu.split(str(self.root))
        first = (self.stage / "1-overview.yml").read_text(encoding="utf-8")
        self.assertIn("# Chương tiếp theo", first)
        self.assertEqual(self.source.read_text(encoding="utf-8"), raw)

    def test_split_requires_step4_written(self) -> None:
        data = self.read(self.knowledge / "1.overview" / "overview-001.yml")
        data["status"] = ""
        self.write(self.knowledge / "1.overview" / "overview-001.yml", data)
        with self.assertRaisesRegex(split_menu.Step6Error, "STEP 4"):
            split_menu.split(str(self.root))
        self.assertFalse(self.stage.exists())

    def test_split_rejects_legacy_schema_without_migration(self) -> None:
        data = self.read(self.source)
        child = data["menu"][0]["childs"][0]
        for name in ("focus", "problemSolved", "mechanism", "applicationValue"):
            child.pop(name)
        child.update({"keyQuestion": "", "mindset": "", "valueForModule": ""})
        self.write(self.source, data)
        with self.assertRaisesRegex(split_menu.Step6Error, "schema invalid"):
            split_menu.split(str(self.root))
        self.assertFalse(self.stage.exists())

    def test_merge_requires_all_statuses_written(self) -> None:
        split_menu.split(str(self.root))
        self.fill()
        self.write(self.stage / "2-application-status.yml", {"status": ""})
        with self.assertRaisesRegex(split_menu.Step6Error, "not marked WRITTEN"):
            merge_menu.merge(str(self.root))
        self.assertFalse((self.stage / "merged.json").exists())

    def test_merge_blocks_empty_fields_even_if_status_written(self) -> None:
        split_menu.split(str(self.root))
        self.fill()
        data = self.read(self.stage / "1-overview.yml")
        data["menu"][0]["childs"][0]["mechanism"] = ""
        self.write(self.stage / "1-overview.yml", data)
        with self.assertRaisesRegex(split_menu.Step6Error, "mechanism"):
            merge_menu.merge(str(self.root))
        self.assertEqual(self.read(self.source)["menu"][0]["childs"][0]["mechanism"], "")

    def test_merge_blocks_identity_change(self) -> None:
        split_menu.split(str(self.root))
        self.fill()
        data = self.read(self.stage / "1-overview.yml")
        data["menu"][0]["childs"][0]["title"] = "Bài học bị đổi"
        self.write(self.stage / "1-overview.yml", data)
        with self.assertRaisesRegex(split_menu.Step6Error, "Immutable"):
            merge_menu.merge(str(self.root))

    def test_merge_rejects_changed_lesson_yaml(self) -> None:
        split_menu.split(str(self.root))
        self.fill()
        info_path = self.knowledge / "1.overview" / "overview-001.yml"
        info = self.read(info_path)
        info["status"] = "IN_PROGRESS"
        self.write(info_path, info)
        with self.assertRaisesRegex(split_menu.Step6Error, "Lesson YAML changed"):
            merge_menu.merge(str(self.root))
        self.assertFalse((self.stage / "merged.json").exists())

    def test_merge_rejects_blank_markdown_after_worker_review(self) -> None:
        split_menu.split(str(self.root))
        self.fill()
        (self.knowledge / "1.overview" / "overview-001.md").write_text(
            "", encoding="utf-8"
        )
        with self.assertRaisesRegex(split_menu.Step6Error, "Markdown/status not complete"):
            merge_menu.merge(str(self.root))
        self.assertTrue(self.stage.exists())

    def test_merge_blocks_source_changes_and_preserves_stage(self) -> None:
        split_menu.split(str(self.root))
        self.fill()
        data = self.read(self.source)
        data["menu"][0]["childs"][0]["summary"] = "Human changed after split"
        self.write(self.source, data)
        before = self.source.read_bytes()
        with self.assertRaisesRegex(split_menu.Step6Error, "Source changed"):
            merge_menu.merge(str(self.root))
        self.assertEqual(self.source.read_bytes(), before)
        self.assertTrue(self.stage.exists())

    def test_merge_blocks_source_header_change(self) -> None:
        split_menu.split(str(self.root))
        self.fill()
        original = self.source.read_bytes()
        self.source.write_bytes(b"# Author header changed\n" + original)
        with self.assertRaisesRegex(split_menu.Step6Error, "header changed"):
            merge_menu.merge(str(self.root))
        self.assertTrue(self.stage.exists())

    def test_cleanup_requires_merge_marker(self) -> None:
        split_menu.split(str(self.root))
        self.fill()
        with self.assertRaisesRegex(split_menu.Step6Error, "Unexpected/missing"):
            delete_temp_split_menu.cleanup(str(self.root))
        self.assertTrue(self.stage.exists())

    def test_cleanup_blocks_stage_changes_after_merge(self) -> None:
        split_menu.split(str(self.root))
        self.fill()
        merge_menu.merge(str(self.root))
        self.write(self.stage / "1-overview-status.yml", {"status": ""})
        with self.assertRaisesRegex(split_menu.Step6Error, "changed since merge"):
            delete_temp_split_menu.cleanup(str(self.root))
        self.assertTrue(self.stage.exists())

    def test_cleanup_blocks_external_source_change(self) -> None:
        split_menu.split(str(self.root))
        self.fill()
        merge_menu.merge(str(self.root))
        self.source.write_text(self.source.read_text(encoding="utf-8") + "# external\n",
                               encoding="utf-8")
        with self.assertRaisesRegex(split_menu.Step6Error, "no longer matches"):
            delete_temp_split_menu.cleanup(str(self.root))
        self.assertTrue(self.stage.exists())

    def test_cleanup_blocks_foreign_file(self) -> None:
        split_menu.split(str(self.root))
        self.fill()
        merge_menu.merge(str(self.root))
        (self.stage / "keep-me.txt").write_text("Do not delete", encoding="utf-8")
        with self.assertRaisesRegex(split_menu.Step6Error, "Unexpected/missing"):
            delete_temp_split_menu.cleanup(str(self.root))
        self.assertTrue((self.stage / "keep-me.txt").exists())

    def test_split_rerun_does_not_overwrite_partial_worker_progress(self) -> None:
        split_menu.split(str(self.root))
        data = self.read(self.stage / "1-overview.yml")
        data["menu"][0]["childs"][0]["focus"] = "Progress preserved"
        self.write(self.stage / "1-overview.yml", data)
        before = (self.stage / "1-overview.yml").read_bytes()
        self.assertIn("RESUMED", split_menu.split(str(self.root)))
        self.assertEqual((self.stage / "1-overview.yml").read_bytes(), before)

    def test_split_resume_rejects_changed_source(self) -> None:
        split_menu.split(str(self.root))
        self.source.write_text(self.source.read_text(encoding="utf-8") + "\n",
                               encoding="utf-8")
        with self.assertRaisesRegex(split_menu.Step6Error, "different source"):
            split_menu.split(str(self.root))

    def test_cleanup_does_not_delete_other_language(self) -> None:
        english = self.root / "content" / "knowledge" / "en"
        shutil.copytree(self.knowledge, english)
        split_menu.split(str(self.root))
        self.fill()
        self.complete()
        delete_temp_split_menu.cleanup(str(self.root))
        self.assertTrue(english.exists())
        self.assertFalse(self.stage.exists())

    def test_merge_can_recover_after_marker_writing_interrupted(self) -> None:
        split_menu.split(str(self.root))
        self.fill()
        merge_menu.merge(str(self.root))
        merged = self.source.read_bytes()
        (self.stage / "merged.json").unlink()  # Simulated process interruption.
        self.assertIn("MERGE_OK", merge_menu.merge(str(self.root)))
        self.assertEqual(merged, self.source.read_bytes())
        self.assertTrue((self.stage / "merged.json").is_file())

    def set_related(self, slug: str, kind: str, links: list[str],
                    *, group_id: int = 1, index: int = 0) -> None:
        groups = [{"groupID": group_id, "items": [
            {"index": index, "readmeRelated": links}
        ]}] if links else []
        self.write(
            self.assess_stage / "readme-related" / slug / f"{kind}.yml",
            {"groups": groups},
        )

    def test_two_chapters_union_same_question_then_byte_exact_export(self) -> None:
        split_menu.split(str(self.root))
        self.fill()
        self.set_related("overview", "quiz", ["overview-001", "overview-002"])
        self.set_related("application", "quiz", ["application-001"])
        self.set_related("application", "casestudy", ["application-001"])
        original_quiz = self.read(self.assess_stage / "format" / "quiz.yml")
        merge_menu.merge(str(self.root))
        self.assertIn("DRY_RUN", merge_related.merge_related(str(self.root), dry_run=True))
        self.assertEqual(self.read(self.assess_stage / "status" / "quiz.yml")["status"], "Phase 3")
        self.assertIn("MERGE_OK", merge_related.merge_related(str(self.root)))
        after = self.read(self.assess_stage / "format" / "quiz.yml")
        anchors = after["quiz"][0]["questions"][0]["readmeRelated"]["anchorList"]
        self.assertEqual(anchors, ["overview-001", "overview-002", "application-001"])
        self.assertEqual(after["quiz"][0]["questions"][0]["answers"],
                         original_quiz["quiz"][0]["questions"][0]["answers"])
        for kind in ("quiz", "interview", "casestudy"):
            self.assertEqual(self.read(self.assess_stage / "status" / f"{kind}.yml"),
                             {"status": "Phase 5"})
        self.assertIn("ALREADY_MERGED", merge_related.merge_related(str(self.root)))
        self.assertIn("DRY_RUN", export_assessments.export(str(self.root), dry_run=True))
        self.assertIn("EXPORT_OK", export_assessments.export(str(self.root)))
        for kind in ("quiz", "interview", "casestudy"):
            self.assertEqual(
                (self.root / "content" / kind / "vi" / f"{kind}.yml").read_bytes(),
                (self.assess_stage / "format" / f"{kind}.yml").read_bytes(),
            )
        self.assertIn("ALREADY_EXPORTED", export_assessments.export(str(self.root)))
        self.assertIn("RESUMED_MERGED", split_menu.split(str(self.root)))

    def test_related_slug_of_wrong_chapter_blocks_all_phase_five(self) -> None:
        split_menu.split(str(self.root))
        self.fill()
        self.set_related("overview", "quiz", ["application-001"])
        before = (self.assess_stage / "format" / "quiz.yml").read_bytes()
        with self.assertRaisesRegex(Exception, "non-chapter lesson"):
            merge_menu.merge(str(self.root))
        self.assertEqual((self.assess_stage / "format" / "quiz.yml").read_bytes(), before)
        self.assertEqual(self.read(self.assess_stage / "status" / "quiz.yml"), {"status": "Phase 3"})

    def test_related_unknown_index_blocks(self) -> None:
        split_menu.split(str(self.root))
        self.fill()
        self.set_related("overview", "interview", ["overview-001"], index=10)
        with self.assertRaisesRegex(Exception, "Unknown/duplicate related identity"):
            merge_menu.merge(str(self.root))

    def test_duplicate_proposals_block(self) -> None:
        split_menu.split(str(self.root))
        self.fill()
        path = self.assess_stage / "readme-related" / "overview" / "quiz.yml"
        self.write(path, {"groups": [
            {"groupID": 1, "items": [{"index": 0, "readmeRelated": ["overview-001"]}]},
            {"groupID": 1, "items": [{"index": 0, "readmeRelated": ["overview-002"]}]},
        ]})
        with self.assertRaisesRegex(Exception, "Unknown/duplicate related identity"):
            merge_menu.merge(str(self.root))

    def test_blank_related_file_is_not_equivalent_to_no_links(self) -> None:
        split_menu.split(str(self.root))
        self.fill()
        (self.assess_stage / "readme-related" / "overview" / "quiz.yml").write_bytes(b"")
        with self.assertRaisesRegex(Exception, "groups list"):
            merge_menu.merge(str(self.root))

    def test_uncompleted_chapter_blocks_related_merge(self) -> None:
        split_menu.split(str(self.root))
        self.fill()
        self.write(self.stage / "2-application-status.yml", {"status": ""})
        with self.assertRaisesRegex(Exception, "Run merge_menu.py"):
            merge_related.merge_related(str(self.root))

    def test_export_requires_prime_phase_five_and_knowledge_merge(self) -> None:
        split_menu.split(str(self.root))
        self.fill()
        merge_menu.merge(str(self.root))
        with self.assertRaisesRegex(Exception, "Phase 5"):
            export_assessments.export(str(self.root))

    def test_export_refuses_unowned_existing_file(self) -> None:
        split_menu.split(str(self.root))
        self.fill()
        self.complete()
        target = self.root / "content" / "quiz" / "vi" / "quiz.yml"
        target.write_text("human-authored\n", encoding="utf-8")
        with self.assertRaisesRegex(Exception, "require --replace-existing"):
            export_assessments.export(str(self.root))
        self.assertEqual(target.read_text(encoding="utf-8"), "human-authored\n")
        self.assertIn("EXPORT_OK", export_assessments.export(
            str(self.root), replace_existing=True
        ))

    def test_failed_merge_rolls_back_all_formats_and_statuses(self) -> None:
        split_menu.split(str(self.root))
        self.fill()
        self.set_related("overview", "quiz", ["overview-001"])
        merge_menu.merge(str(self.root))
        original = {
            str(path): path.read_bytes()
            for folder in ("status", "format")
            for path in (self.assess_stage / folder).iterdir()
        }
        actual_write = merge_related.safe_write
        counter = [0]

        def fail_second_write(*args):
            counter[0] += 1
            if counter[0] == 2:
                raise OSError("Simulated disk failure")
            return actual_write(*args)

        with patch.object(merge_related, "safe_write", side_effect=fail_second_write):
            with self.assertRaisesRegex(Exception, "rolled back"):
                merge_related.merge_related(str(self.root))
        for name, before in original.items():
            self.assertEqual(Path(name).read_bytes(), before)
        self.assertIn("MERGE_OK", merge_related.merge_related(str(self.root)))

    def test_failed_export_rolls_back_written_targets(self) -> None:
        split_menu.split(str(self.root))
        self.fill()
        merge_menu.merge(str(self.root))
        merge_related.merge_related(str(self.root))
        original_write = export_assessments.atomic_replace
        count = [0]

        def fail_second(*args):
            count[0] += 1
            if count[0] == 2:
                raise OSError("Disk is full")
            return original_write(*args)

        with patch.object(export_assessments, "atomic_replace", side_effect=fail_second):
            with self.assertRaisesRegex(Exception, "Export failed"):
                export_assessments.export(str(self.root))
        for kind in ("quiz", "interview", "casestudy"):
            self.assertFalse((self.root / "content" / kind / "vi" / f"{kind}.yml").exists())

    def test_cleanup_rejected_until_exports_complete(self) -> None:
        split_menu.split(str(self.root))
        self.fill()
        merge_menu.merge(str(self.root))
        merge_related.merge_related(str(self.root))
        with self.assertRaisesRegex(Exception, "regular file"):
            delete_temp_split_menu.cleanup(str(self.root))
        self.assertTrue(self.stage.exists())
        self.assertTrue(self.assess_stage.exists())


if __name__ == "__main__":
    unittest.main()
