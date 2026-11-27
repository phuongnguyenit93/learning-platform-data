"""Isolated contract tests for STEP 5 NEW staging initialization."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "generate-temp-file.py"
SPEC = importlib.util.spec_from_file_location("step5_generate_temp_file", SCRIPT)
assert SPEC and SPEC.loader
step5 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(step5)


class Step5NewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sandbox = tempfile.TemporaryDirectory()
        self.addCleanup(self.sandbox.cleanup)
        self.repo = Path(self.sandbox.name) / "java-learning"
        self.module = self.repo / "module" / "platform" / "sample"
        (self.module / "content").mkdir(parents=True)
        (self.module / "module_activate.json").write_text(
            '{"isModule": true}', encoding="utf-8"
        )
        self.info = self.module / "module-info.json"
        self.write_info()
        knowledge = self.module / "content" / "knowledge" / "vi"
        knowledge.mkdir(parents=True)
        (knowledge / "menu-level-1-slug.yml").write_text(
            "menu:\n  - title: Tổng quan\n    slug: overview\n    index: 0\n"
            "  - title: Ứng dụng\n    slug: application\n    index: 1\n",
            encoding="utf-8",
        )
        self.patch = patch.object(step5, "REPO_ROOT", self.repo)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.stage = self.module / "content" / "temp" / "step5"

    def write_info(self, **overrides: object) -> None:
        values = {
            "SERVICE_NAME": "SAMPLE_MODULE",
            "SERVICE_NAME_DESCRIBE": "A module to learn",
            "SPECIAL_NOTE": "",
            "MODULE_LANGUAGE": ["vi"],
        }
        values.update(overrides)
        self.info.write_text(
            json.dumps({key: {"VALUE": value} for key, value in values.items()}),
            encoding="utf-8",
        )

    def test_dry_run_does_not_create_anything(self) -> None:
        result, missing = step5.prepare(str(self.module), dry_run=True)
        self.assertEqual(result, "WOULD_CREATE")
        self.assertEqual(len(missing), 15)
        self.assertFalse(self.stage.parent.exists())

    def test_fresh_create_nine_base_files_and_related_per_chapter(self) -> None:
        result, created = step5.prepare(str(self.module))
        self.assertEqual(result, "CREATED")
        self.assertEqual(len(created), 15)
        for kind in step5.KINDS:
            self.assertEqual((self.stage / "raw" / f"{kind}.md").read_bytes(), b"")
            self.assertEqual((self.stage / "format" / f"{kind}.yml").read_bytes(), b"")
            self.assertEqual(
                (self.stage / "status" / f"{kind}.yml").read_text(encoding="utf-8"),
                "status: Phase 0\n",
            )
            for slug in ("overview", "application"):
                self.assertEqual(
                    (self.stage / "readme-related" / slug / f"{kind}.yml").read_bytes(), b""
                )

    def test_resume_preserves_progress_exact_bytes(self) -> None:
        step5.prepare(str(self.module))
        raw = self.stage / "raw" / "interview.md"
        fmt = self.stage / "format" / "interview.yml"
        status = self.stage / "status" / "interview.yml"
        raw.write_text("Cơ chế hoạt động là gì?\n", encoding="utf-8")
        fmt.write_text(
            "interviewQuestion:\n  - groupID: 1\n    groupName: Tổng quan\n"
            "    questions:\n      - index: 0\n        question: Cơ chế hoạt động là gì?\n"
            "        knowledge: \"\"\n        answer: \"\"\n"
            "        readmeRelated: {anchorList: []}\n",
            encoding="utf-8",
        )
        status.write_text("status: Phase 2\n", encoding="utf-8")
        snapshot = {p: p.read_bytes() for p in (raw, fmt, status)}
        result, missing = step5.prepare(str(self.module))
        self.assertEqual((result, missing), ("RESUMED", ()))
        for path, original in snapshot.items():
            self.assertEqual(path.read_bytes(), original)

    def test_partial_phase_zero_missing_file_can_be_repaired(self) -> None:
        step5.prepare(str(self.module))
        missing = self.stage / "format" / "quiz.yml"
        missing.unlink()
        result, names = step5.prepare(str(self.module))
        self.assertEqual(result, "RESUMED")
        self.assertEqual(names, ("format/quiz.yml",))
        self.assertEqual(missing.read_bytes(), b"")

    def test_advanced_phase_missing_format_blocks_without_write(self) -> None:
        step5.prepare(str(self.module))
        (self.stage / "raw" / "quiz.md").write_text("Câu hỏi?\n", encoding="utf-8")
        (self.stage / "status" / "quiz.yml").write_text(
            "status: Phase 2\n", encoding="utf-8"
        )
        before = (self.stage / "format" / "quiz.yml").read_bytes()
        with self.assertRaises(step5.Step5Error):
            step5.prepare(str(self.module))
        self.assertEqual((self.stage / "format" / "quiz.yml").read_bytes(), before)

    def test_missing_status_with_authored_content_blocks(self) -> None:
        step5.prepare(str(self.module))
        (self.stage / "status" / "casestudy.yml").unlink()
        (self.stage / "raw" / "casestudy.md").write_text(
            "Hệ thống bị gián đoạn.\n", encoding="utf-8"
        )
        with self.assertRaises(step5.Step5Error):
            step5.prepare(str(self.module))
        self.assertFalse((self.stage / "status" / "casestudy.yml").exists())

    def test_quiz_cannot_advance_to_phase_four(self) -> None:
        step5.prepare(str(self.module))
        (self.stage / "status" / "quiz.yml").write_text(
            "status: Phase 4\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(step5.Step5Error, "Unexpected terminal status"):
            step5.prepare(str(self.module))

    def test_phase_three_quiz_requires_all_explanations(self) -> None:
        step5.prepare(str(self.module))
        (self.stage / "raw" / "quiz.md").write_text("Quiz 1?\n", encoding="utf-8")
        (self.stage / "format" / "quiz.yml").write_text(
            "quiz:\n"
            "  - groupID: 1\n    groupName: Nền tảng\n    questions:\n"
            "      - index: 0\n        question: Quiz 1?\n"
            "        readmeRelated: {anchorList: []}\n"
            "        answers:\n"
            "          - {id: A, answer: A1, explanation: X}\n"
            "          - {id: B, answer: B1, explanation: Y}\n"
            "          - {id: C, answer: C1, explanation: \"\"}\n"
            "          - {id: D, answer: D1, explanation: Z}\n"
            "        correctAnswerId: A\n",
            encoding="utf-8",
        )
        (self.stage / "status" / "quiz.yml").write_text(
            "status: Phase 3\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(step5.Step5Error, "Missing Phase data"):
            step5.prepare(str(self.module))

    def test_phase_four_noncode_casestudy_answer_is_valid(self) -> None:
        step5.prepare(str(self.module))
        (self.stage / "raw" / "casestudy.md").write_text(
            "Sự cố hệ thống.\n", encoding="utf-8"
        )
        (self.stage / "format" / "casestudy.yml").write_text(
            "caseStudy:\n"
            "  - groupID: 1\n    groupName: Vận hành\n    cases:\n"
            "      - index: 0\n        situation: Sự cố hệ thống.\n"
            "        resolve: Phân tích nguyên nhân và ưu tiên xử lý\n"
            "        knowledge: Mô hình phân tích sự cố\n"
            "        answer: |-\n"
            "          Kiểm tra nguyên nhân, đánh giá rủi ro rồi phối hợp khắc phục.\n"
            "        readmeRelated: {anchorList: []}\n",
            encoding="utf-8",
        )
        (self.stage / "status" / "casestudy.yml").write_text(
            "status: Phase 4\n", encoding="utf-8"
        )
        result, missing = step5.prepare(str(self.module))
        self.assertEqual((result, missing), ("RESUMED", ()))

    def test_phase_five_with_merged_readme_anchors_is_resumable(self) -> None:
        step5.prepare(str(self.module))
        (self.stage / "raw" / "quiz.md").write_text("Quiz 1?\n", encoding="utf-8")
        (self.stage / "format" / "quiz.yml").write_text(
            "quiz:\n"
            "  - groupID: 1\n    groupName: Nền tảng\n    questions:\n"
            "      - index: 0\n        question: Quiz 1?\n"
            "        readmeRelated: {anchorList: [overview-001]}\n"
            "        answers:\n"
            "          - {id: A, answer: A1, explanation: X}\n"
            "          - {id: B, answer: B1, explanation: Y}\n"
            "          - {id: C, answer: C1, explanation: Q}\n"
            "          - {id: D, answer: D1, explanation: Z}\n"
            "        correctAnswerId: A\n",
            encoding="utf-8",
        )
        (self.stage / "status" / "quiz.yml").write_text(
            "status: Phase 5\n", encoding="utf-8"
        )
        self.assertEqual(step5.prepare(str(self.module)), ("RESUMED", ()))

    def test_invalid_and_duplicate_status_keys_are_rejected(self) -> None:
        step5.prepare(str(self.module))
        status = self.stage / "status" / "quiz.yml"
        for value in ("status: Phase 0\nstatus: Phase 1\n", "status: DONE\n"):
            with self.subTest(value=value):
                status.write_text(value, encoding="utf-8")
                with self.assertRaises(step5.Step5Error):
                    step5.prepare(str(self.module))

    def test_foreign_file_is_not_removed(self) -> None:
        step5.prepare(str(self.module))
        foreign = self.stage / "raw" / "personal.txt"
        foreign.write_text("do not touch", encoding="utf-8")
        with self.assertRaisesRegex(step5.Step5Error, "Unexpected files"):
            step5.prepare(str(self.module))
        self.assertEqual(foreign.read_text(encoding="utf-8"), "do not touch")

    def test_inactive_and_wrong_module_block(self) -> None:
        (self.module / "module_activate.json").write_text(
            '{"isModule": false}', encoding="utf-8"
        )
        with self.assertRaises(step5.Step5Error):
            step5.prepare(str(self.module))
        with self.assertRaises(step5.Step5Error):
            step5.prepare(str(self.repo))

    def test_validation_of_metadata_prevents_creation(self) -> None:
        self.write_info(SPECIAL_NOTE=None)
        with self.assertRaises(step5.Step5Error):
            step5.prepare(str(self.module))
        self.assertFalse(self.stage.exists())

    def test_related_worker_content_survives_resume(self) -> None:
        step5.prepare(str(self.module))
        related = self.stage / "readme-related" / "overview" / "quiz.yml"
        payload = b"groups:\n  - groupID: 1\n    items:\n      - index: 0\n        readmeRelated:\n          - overview-001\n"
        related.write_bytes(payload)
        self.assertEqual(step5.prepare(str(self.module)), ("RESUMED", ()))
        self.assertEqual(related.read_bytes(), payload)

    def test_invalid_menu_fails_before_writing(self) -> None:
        menu = self.module / "content" / "knowledge" / "vi" / "menu-level-1-slug.yml"
        menu.write_text("menu:\n  - title: Test\n    slug: overview\n    index: 3\n", encoding="utf-8")
        with self.assertRaisesRegex(step5.Step5Error, "Noncontiguous"):
            step5.prepare(str(self.module))
        self.assertFalse(self.stage.exists())

    def test_changed_chapter_menu_after_worker_started_is_blocked(self) -> None:
        step5.prepare(str(self.module))
        (self.stage / "raw" / "quiz.md").write_text(
            "Câu hỏi?\nA. X\nB. Y\nC. Z\nD. T\nĐáp án đúng: A\n", encoding="utf-8"
        )
        (self.stage / "status" / "quiz.yml").write_text("status: Phase 1\n", encoding="utf-8")
        menu = self.module / "content" / "knowledge" / "vi" / "menu-level-1-slug.yml"
        menu.write_text(
            menu.read_text(encoding="utf-8") +
            "  - title: Bài mới\n    slug: new-chapter\n    index: 2\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(step5.Step5Error, "menu changed"):
            step5.prepare(str(self.module))
        self.assertFalse((self.stage / "readme-related" / "new-chapter").exists())


if __name__ == "__main__":
    unittest.main()
