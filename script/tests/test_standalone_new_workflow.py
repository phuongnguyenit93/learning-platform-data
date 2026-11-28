"""Standalone smoke tests: no java-learning parent, Gradle or Oracle available."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SOURCE_ROOT = Path(__file__).resolve().parents[2]


class StandaloneWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="standalone-data-check-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "renamed-standalone-repo"
        self.root.mkdir()
        shutil.copy2(SOURCE_ROOT / "module-info-base.json", self.root / "module-info-base.json")
        for source in (SOURCE_ROOT / "script").rglob("*.py"):
            if "__pycache__" in source.parts:
                continue
            dest = self.root / source.relative_to(SOURCE_ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
        self.module = self.root / "module" / "demo"
        self.module.mkdir(parents=True)
        (self.module / "module_activate.json").write_text('{"isModule": true}', encoding="utf-8")

    def cli(self, script, *args, ok=True):
        process = subprocess.run(
            ["python", f"script/module-generate/{script}", *args],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=20,
        )
        if ok:
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        else:
            self.assertNotEqual(process.returncode, 0, process.stdout + process.stderr)
        return process.stdout + process.stderr

    def create_metadata(self):
        script = "step1/activate_module.py"
        self.cli(script, "--module", "module/demo", "--dry-run")
        self.assertFalse((self.module / "module-info.json").exists())
        self.cli(script, "--module", "module/demo", "--apply")
        path = self.module / "module-info.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["SERVICE_NAME"]["VALUE"] = "STANDALONE_DEMO"
        value["SERVICE_NAME_DESCRIBE"]["VALUE"] = "Test the Python workflow"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_step1_is_standalone_idempotent_and_preserves_metadata(self):
        info = self.create_metadata()
        before = info.read_bytes()
        self.cli("step1/activate_module.py", "--module", "module/demo", "--apply")
        self.assertEqual(info.read_bytes(), before)
        self.assertFalse((self.root.parent / "module").exists())

        (self.module / "module_activate.json").write_text('{"isModule": false}', encoding="utf-8")
        self.cli("step1/activate_module.py", "--module", "module/demo", "--apply", ok=False)
        self.assertEqual(info.read_bytes(), before)

    def test_step2_to_step6_offline_with_renamed_clone(self):
        self.create_metadata()
        step2 = "step2/generate-basic-info-skeleton.py"
        self.cli(step2, "--module", "module/demo", "--lang", "vi", "--dry-run")
        self.cli(step2, "--module", "module/demo", "--lang", "vi")
        roadmap = self.module / "content/roadmap/vi/roadmap.yml"
        refs = self.module / "content/reference/vi/references.yml"
        base = self.module / "content/base/vi/base.md"
        roadmap.write_text(
            "roadmap:\n  - id: intro\n    title: Intro\n    purpose: Start\n"
            "    objectives:\n      - Know the basics\n", encoding="utf-8"
        )
        refs.write_text(
            "references:\n  - title: Python\n    url: https://docs.python.org/3/\n",
            encoding="utf-8",
        )
        base.write_bytes(b"# Module introduction\r\n\r\nUseful text.\r\n")
        for entity in ("roadmaps", "references", "overviews"):
            self.cli(f"step2/import-module-{entity}.py", "--module",
                     "STANDALONE_DEMO", "--lang", "vi", "--offline")
        self.assertFalse((self.root.parent / "build").exists())
        for entity in ("roadmap", "reference", "overview"):
            report = self.root / "build/reports" / f"step2-vi-{entity}s.json"
            self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["counts"],
                             {"READY_LOCAL_ONLY": 1})

        self.cli("step3/generate_menu_skeleton.py", "--module", "module/demo",
                 "--lang", "vi", "--dry-run")
        self.cli("step3/generate_menu_skeleton.py", "--module", "module/demo", "--lang", "vi")
        chapter = self.module / "content/knowledge/vi/menu-level-1-slug.yml"
        chapter.write_text(
            "menu:\n  - title: Intro\n    slug: intro\n    index: 0\n",
            encoding="utf-8",
        )
        self.cli("step4/refresh_menu_status.py", "--help")
        self.cli("step5/generate-temp-file.py", "--module", "module/demo", "--dry-run")
        self.cli("step6/split_menu.py", "--help")

        # STEP 6 staging must belong to this repository, not its parent.
        probe = subprocess.run(
            ["python", "-c",
             "import sys;sys.path.insert(0,'script/module-generate/step6');"
             "import split_menu;print(split_menu.module_context('module/demo','vi')[2])"],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=20,
        )
        self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertEqual(Path(probe.stdout.strip()).resolve(),
                         (self.root / "temp/step6/STANDALONE_DEMO/vi").resolve())

    def test_data_report_and_oracle_env_are_repo_local(self):
        self.create_metadata()
        lesson = self.module / "content/knowledge/vi/intro/intro.md"
        lesson.parent.mkdir(parents=True)
        lesson.write_text("Nonempty lesson", encoding="utf-8")
        self.cli("status-report/get-knowledge-report.py", "--output-dir",
                 "build/reports", "--no-cache")
        self.assertTrue((self.root / "build/reports/knowledge-finished.yml").is_file())
        probe = subprocess.run(
            ["python", "-c",
             "import importlib.util,pathlib;"
             "p=pathlib.Path('script/database/connect-oracle-db.py').resolve();"
             "s=importlib.util.spec_from_file_location('connector',p);"
             "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
             "print(m.DEFAULT_ENV_FILE)"],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=20,
        )
        self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertEqual(Path(probe.stdout.strip()).resolve(),
                         (self.root / ".env.oracle-overview").resolve())


if __name__ == "__main__":
    unittest.main()
