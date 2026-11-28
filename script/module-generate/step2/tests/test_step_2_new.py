"""Offline regression tests for the STEP_2_NEW skeleton and scoped importers."""

from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
import importlib.util
from io import StringIO
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[5]


def load_script(label: str, filename: Path):
    spec = importlib.util.spec_from_file_location(label, filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[label] = module
    spec.loader.exec_module(module)
    return module


SKELETON = load_script(
    "step2_skeleton_new", REPO / "learning-platform-data/script/module-generate/step2/generate-basic-info-skeleton.py"
)
ROADMAP = load_script(
    "step2_roadmap_new", REPO / "learning-platform-data/script/module-generate/step2/import-module-roadmaps.py"
)
REFERENCE = load_script(
    "step2_reference_new", REPO / "learning-platform-data/script/module-generate/step2/import-module-references.py"
)
OVERVIEW = load_script(
    "step2_overview_new", REPO / "learning-platform-data/script/module-generate/step2/import-module-overviews.py"
)


class NewStep2Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        (self.repo / "module").mkdir()
        self.make_module("topic-a", "TOPIC_A")

    def make_module(self, name, service, *, activated=True):
        directory = self.repo / "module" / name
        directory.mkdir()
        (directory / "module_activate.json").write_text(
            json.dumps({"isModule": activated}), encoding="utf-8"
        )
        (directory / "module-info.json").write_text(
            json.dumps({
                "SERVICE_NAME": {"TYPE": "string", "VALUE": service},
                "MODULE_LANGUAGE": {"TYPE": "list", "VALUE": ["vi"]},
                "SERVICE_NAME_DESCRIBE": {"VALUE": "A short description"},
                "SPECIAL_NOTE": {"VALUE": ""},
            }), encoding="utf-8"
        )
        return directory

    def skeleton(self, name="topic-a", *, dry_run=False):
        with patch.object(SKELETON, "ROOT", self.repo), patch.object(
            SKELETON, "MODULE_ROOT", self.repo / "module"
        ):
            directory = SKELETON.module_directory(f"module/{name}")
            with redirect_stdout(StringIO()):
                SKELETON.generate(directory, "vi", dry_run)

    def test_skeleton_creates_three_targets_without_overwriting(self):
        module = self.repo / "module" / "topic-a"
        self.skeleton(dry_run=True)
        self.assertFalse((module / "content").exists())
        self.skeleton()
        roadmap = module / "content/roadmap/vi/roadmap.yml"
        reference = module / "content/reference/vi/references.yml"
        base = module / "content/base/vi/base.md"
        self.assertEqual(roadmap.read_text(encoding="utf-8"), "roadmap: []\n")
        self.assertEqual(reference.read_text(encoding="utf-8"), "references: []\n")
        self.assertEqual(base.read_bytes(), b"")
        roadmap.write_text("roadmap:\n  - authored\n", encoding="utf-8")
        base.write_text("# Author content\n", encoding="utf-8")
        self.skeleton()
        self.assertEqual(roadmap.read_text(encoding="utf-8"), "roadmap:\n  - authored\n")
        self.assertEqual(base.read_text(encoding="utf-8"), "# Author content\n")

    def test_skeleton_does_not_accept_unactivated_module(self):
        self.make_module("topic-b", "TOPIC_B", activated=False)
        with patch.object(SKELETON, "ROOT", self.repo), patch.object(
            SKELETON, "MODULE_ROOT", self.repo / "module"
        ):
            with self.assertRaises(SKELETON.SkeletonError):
                SKELETON.module_directory("module/topic-b")

    def test_skeleton_rejects_wrong_language(self):
        module = self.repo / "module" / "topic-a"
        with self.assertRaises(SKELETON.SkeletonError):
            SKELETON.plan(module, "en")

    def set_authored(self, name="topic-a", *, empty=False):
        directory = self.repo / "module" / name
        roadmap = directory / "content/roadmap/vi"
        refs = directory / "content/reference/vi"
        roadmap.mkdir(parents=True, exist_ok=True)
        refs.mkdir(parents=True, exist_ok=True)
        (roadmap / "roadmap.yml").write_text(
            "roadmap: []\n" if empty else
            "roadmap:\n  - id: topic\n    title: Topic\n    purpose: Learn\n"
            "    objectives:\n      - Understand the basics\n",
            encoding="utf-8"
        )
        (refs / "references.yml").write_text(
            "references: []\n" if empty else
            "references:\n  - title: Official Docs\n"
            "    url: https://docs.python.org/3/\n"
            "    description: Verified documentation\n",
            encoding="utf-8"
        )

    def importer_run(self, importer, *args):
        suffix = "roadmap" if importer is ROADMAP else (
            "reference" if importer is REFERENCE else "overview"
        )
        report = self.repo / "reports" / f"{suffix}.json"
        with patch.object(importer, "REPO_ROOT", self.repo):
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = importer.main([*args, "--report", str(report)])
        return code, json.loads(report.read_text(encoding="utf-8")) if report.exists() else None

    def set_base(self, name="topic-a", content="# Chủ đề\r\n\r\nMô tả **hữu ích**.\r\n"):
        path = self.repo / "module" / name / "content/base/vi/base.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))
        return path

    def test_overview_reads_only_selected_vi_base_and_preserves_line_endings(self):
        path = self.set_base()
        self.make_module("topic-b", "TOPIC_B")
        self.set_base("topic-b", "# Other module\n")
        old = path.parents[2] / "readme/docs/vi/BASE.md"
        old.parent.mkdir(parents=True, exist_ok=True)
        old.write_text("# Legacy must be ignored\n", encoding="utf-8")
        (self.repo / "module/topic-b/module-info.json").write_text(
            "{ malformed metadata", encoding="utf-8"
        )
        with patch.object(OVERVIEW, "REPO_ROOT", self.repo):
            entries, skipped, errors = OVERVIEW.scan_overviews(
                self.repo / "module", module_filter=frozenset({"TOPIC_A"})
            )
        self.assertFalse(skipped)
        self.assertFalse(errors)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].markdown.encode("utf-8"), path.read_bytes())
        self.assertEqual(entries[0].language_code, "vi")
        self.assertEqual(entries[0].file_path, "topic-a/content/base/vi/base.md")

        code, report = self.importer_run(OVERVIEW, "--module", "TOPIC_A", "--offline")
        self.assertEqual(code, 0)
        self.assertEqual([item["nodeKey"] for item in report["items"]], ["TOPIC_A"])
        self.assertEqual(report["counts"], {"READY_LOCAL_ONLY": 1})

    def test_overview_multiple_modules(self):
        self.make_module("topic-b", "TOPIC_B")
        self.set_base()
        self.set_base("topic-b")
        code, report = self.importer_run(
            OVERVIEW, "--module", "TOPIC_A", "--module", "TOPIC_B", "--offline"
        )
        self.assertEqual(code, 0)
        self.assertEqual({item["nodeKey"] for item in report["items"]}, {"TOPIC_A", "TOPIC_B"})

    def test_overview_missing_file_or_module_is_blocker(self):
        self.make_module("topic-b", "TOPIC_B")
        self.set_base()
        code, report = self.importer_run(
            OVERVIEW, "--module", "TOPIC_A", "--module", "TOPIC_B", "--offline"
        )
        self.assertEqual(code, 1)
        self.assertTrue(any("TOPIC_B" in error for error in report["errors"]))

        code, report = self.importer_run(
            OVERVIEW, "--module", "TOPIC_A", "--module", "NOT_PRESENT", "--offline"
        )
        self.assertEqual(code, 1)
        self.assertTrue(any("NOT_PRESENT" in error for error in report["errors"]))

    def test_overview_rejects_inactive_module(self):
        self.make_module("topic-b", "TOPIC_B", activated=False)
        self.set_base("topic-b")
        code, report = self.importer_run(OVERVIEW, "--module", "TOPIC_B", "--offline")
        self.assertEqual(code, 1)
        self.assertTrue(any("not activated" in error for error in report["errors"]))

    def test_overview_empty_skeleton_cannot_be_applied(self):
        self.set_base(content="")
        code, report = self.importer_run(OVERVIEW, "--module", "TOPIC_A", "--apply")
        self.assertEqual(code, 1)
        self.assertTrue(any("empty Base" in error for error in report["errors"]))

    def test_overview_requires_scope_and_vi(self):
        for argv in (["--offline"], ["--module", "TOPIC_A", "--lang", "en", "--offline"],
                     ["--module", "TOPIC_A", "--module", "TOPIC_A", "--offline"],
                     ["--module", "../BAD", "--offline"]):
            with self.subTest(argv=argv), redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as error:
                    OVERVIEW.main(argv)
                self.assertEqual(error.exception.code, 2)

    def test_overview_db_dry_run_and_apply_are_scoped(self):
        self.set_base()

        class FakeCursor:
            def __init__(self, *, rowcount=1, registered=True):
                self.queries = []
                self.rows = ()
                self.rowcount = rowcount
                self.registered = registered

            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter(self.rows)
            def setinputsizes(self, **kwargs): self.sizes = kwargs

            def execute(self, sql, params=None):
                self.queries.append((sql, params))
                if params is not None:
                    return
                number = len([q for q, p in self.queries if p is None])
                self.rows = [
                    [("TOPIC_A", 101, "MODULE")] if self.registered else [],
                    [("vi",)],
                    [],
                ][number - 1]

        class FakeConnection:
            def __init__(self, cursor):
                self.c = cursor
                self.commits = 0
                self.rollbacks = 0
                self.closed = False
            def cursor(self): return self.c
            def commit(self): self.commits += 1
            def rollback(self): self.rollbacks += 1
            def close(self): self.closed = True

        env = {
            "ORACLE_USER": "TEST", "ORACLE_PASSWORD": "test-secret",
            "ORACLE_DSN": "dummy", "ORACLE_SCHEMA": "",
        }
        for mode, expected_commit in (("--dry-run", 0), ("--apply", 1)):
            with self.subTest(mode=mode):
                cursor = FakeCursor()
                connection = FakeConnection(cursor)
                driver = SimpleNamespace(
                    connect=lambda **_: connection, DB_TYPE_CLOB=object()
                )
                with patch.dict(os.environ, env, clear=True), patch.dict(
                    sys.modules, {"oracledb": driver}
                ):
                    code, report = self.importer_run(
                        OVERVIEW, "--module", "TOPIC_A", mode
                    )
                self.assertEqual(code, 0)
                self.assertEqual(connection.commits, expected_commit)
                self.assertEqual(connection.rollbacks, 1 - expected_commit)
                self.assertTrue(connection.closed)
                mutations = [(sql, params) for sql, params in cursor.queries if params]
                self.assertEqual(len(mutations), expected_commit)
                if mutations:
                    self.assertEqual(mutations[0][1]["node_key"], "TOPIC_A")
                    self.assertEqual(mutations[0][1]["language_code"], "vi")
                    self.assertIn("# Chủ đề", mutations[0][1]["markdown_content"])
                self.assertEqual(report["items"][0]["nodeKey"], "TOPIC_A")

    def test_overview_apply_rejects_missing_oracle_module_before_merging(self):
        self.set_base()

        class StubCursor:
            def __init__(self):
                self.queries = []
                self.rows = []
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter(self.rows)
            def execute(self, sql, params=None):
                self.queries.append((sql, params))
                self.rows = [] if len(self.queries) != 2 else [("vi",)]

        class StubConnection:
            def __init__(self):
                self.c = StubCursor()
                self.commits = 0
                self.rollbacks = 0
            def cursor(self): return self.c
            def commit(self): self.commits += 1
            def rollback(self): self.rollbacks += 1
            def close(self): pass

        connection = StubConnection()
        driver = SimpleNamespace(
            connect=lambda **_: connection, DB_TYPE_CLOB=object()
        )
        env = {
            "ORACLE_USER": "TEST", "ORACLE_PASSWORD": "test-secret",
            "ORACLE_DSN": "dummy", "ORACLE_SCHEMA": "",
        }
        with patch.dict(os.environ, env, clear=True), patch.dict(
            sys.modules, {"oracledb": driver}
        ):
            code, report = self.importer_run(OVERVIEW, "--module", "TOPIC_A", "--apply")
        self.assertEqual(code, 1)
        self.assertEqual(connection.commits, 0)
        self.assertGreaterEqual(connection.rollbacks, 1)
        self.assertTrue(all(params is None for _, params in connection.c.queries))
        self.assertTrue(report["errors"])

    def test_only_named_module_is_selected(self):
        self.make_module("topic-b", "TOPIC_B")
        self.set_authored()
        self.set_authored("topic-b")
        for importer in (ROADMAP, REFERENCE):
            with self.subTest(importer=importer.__name__):
                code, report = self.importer_run(importer, "--module", "TOPIC_A", "--offline")
                self.assertEqual(code, 0)
                self.assertEqual([item["nodeKey"] for item in report["items"]], ["TOPIC_A"])

    def test_multiple_explicit_modules_are_allowed(self):
        self.make_module("topic-b", "TOPIC_B")
        self.set_authored()
        self.set_authored("topic-b")
        for importer in (ROADMAP, REFERENCE):
            code, report = self.importer_run(
                importer, "--module", "TOPIC_A", "--module", "TOPIC_B", "--offline"
            )
            self.assertEqual(code, 0)
            self.assertEqual({item["nodeKey"] for item in report["items"]},
                             {"TOPIC_A", "TOPIC_B"})

    def test_missing_selected_module_fails_even_if_other_module_exists(self):
        self.set_authored()
        for importer in (ROADMAP, REFERENCE):
            code, report = self.importer_run(
                importer, "--module", "TOPIC_A", "--module", "NOT_PRESENT", "--offline"
            )
            self.assertEqual(code, 1)
            self.assertTrue(report["errors"])

    def test_apply_rejects_empty_skeleton_before_database_connection(self):
        self.set_authored(empty=True)
        for importer in (ROADMAP, REFERENCE):
            code, report = self.importer_run(importer, "--module", "TOPIC_A", "--apply")
            self.assertEqual(code, 1)
            self.assertTrue(report["errors"])

    def test_unactivated_module_cannot_be_imported(self):
        self.make_module("topic-b", "TOPIC_B", activated=False)
        self.set_authored("topic-b")
        for importer in (ROADMAP, REFERENCE):
            code, report = self.importer_run(
                importer, "--module", "TOPIC_B", "--offline"
            )
            self.assertEqual(code, 1)
            self.assertTrue(any("not activated" in error for error in report["errors"]))

    def test_roadmap_rejects_ten_milestones(self):
        self.set_authored()
        target = self.repo / "module/topic-a/content/roadmap/vi/roadmap.yml"
        content = "roadmap:\n" + "".join(
            f"  - id: topic-{i}\n    title: Topic {i}\n"
            f"    purpose: Learn topic {i}\n    objectives:\n      - Understand topic {i}\n"
            for i in range(10)
        )
        target.write_text(content, encoding="utf-8")
        code, report = self.importer_run(ROADMAP, "--module", "TOPIC_A", "--offline")
        self.assertEqual(code, 1)
        self.assertTrue(any("fewer than 10" in error for error in report["errors"]))

    def test_importer_requires_scope_and_vietnamese(self):
        for importer in (ROADMAP, REFERENCE):
            with redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as no_module:
                    importer.main(["--offline"])
                with self.assertRaises(SystemExit) as non_vi:
                    importer.main(["--module", "TOPIC_A", "--lang", "en", "--offline"])
            self.assertEqual(no_module.exception.code, 2)
            self.assertEqual(non_vi.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
