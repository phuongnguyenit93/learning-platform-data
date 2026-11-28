"""Regression tests for the incremental Markdown completion report."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml


SCRIPT_PATH = Path(__file__).with_name("get-knowledge-report.py")
SPEC = importlib.util.spec_from_file_location("get_knowledge_report", SCRIPT_PATH)
report_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report_script)


class KnowledgeReportTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.modules = self.root / "module"
        self.cache_path = self.root / "out" / report_script.CACHE_FILENAME

    def add_module(self, name, files):
        module = self.modules / name
        module.mkdir(parents=True)
        (module / "module-info.json").write_text(
            json.dumps({"CURRENT_STEP": {"VALUE": "DONE"}, "SERVICE_NAME": {"VALUE": name}}),
            encoding="utf-8",
        )
        for filename, content in files.items():
            path = module / "content" / "knowledge" / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return module

    def scan(self, previous=None, cache=True):
        scanner = report_script.KnowledgeScanner(previous, use_cache=cache)
        report = report_script.build_report(self.root, scanner)
        return report, scanner

    def assert_same_data(self, first, second):
        for group in report_script.GROUPS:
            self.assertEqual(first[group], second[group])
        for key in first["summary"]:
            if key != "generatedAt":
                self.assertEqual(first["summary"][key], second["summary"][key])
        self.assertEqual(first.get("noKnowledgeFiles"), second.get("noKnowledgeFiles"))

    def test_incremental_handles_whitespace_edits_additions_and_deletions(self):
        self.add_module("finished", {"vi/a.md": "\ufeffComplete"})
        partial = self.add_module(
            "partial", {"vi/content.md": "actual text", "en/empty.md": " \n\t "}
        )
        self.add_module("blank", {"vi/empty.md": ""})
        self.add_module("no-files", {})

        initial, scanner = self.scan()
        self.assertEqual(
            (initial["summary"]["finishedModules"], initial["summary"]["unfinishedModules"],
             initial["summary"]["blankModules"], initial["summary"]["modulesWithoutMarkdown"]),
            (1, 1, 1, 1),
        )
        self.assertEqual(
            (initial["summary"]["totalMarkdownFiles"], initial["summary"]["blankMarkdownFiles"],
             initial["summary"]["filledMarkdownFiles"]),
            (4, 2, 2),
        )
        self.assertEqual(scanner.stats["contentReads"], 3)
        self.assertEqual(len(scanner.updated), 3)  # Zero-byte files need no cache entry.
        report_script.write_scan_cache(self.cache_path, self.root, scanner.updated)
        cache = report_script.load_scan_cache(self.cache_path, self.root)

        repeated, scanner = self.scan(cache)
        self.assert_same_data(initial, repeated)
        self.assertEqual(scanner.stats["contentReads"], 0)
        self.assertEqual(scanner.stats["cacheHits"], 3)

        whitespace = partial / "content" / "knowledge" / "en" / "empty.md"
        whitespace.write_text("Translated content", encoding="utf-8")
        # Force a distinct timestamp even when Windows updates it at coarse resolution.
        info = whitespace.stat()
        os.utime(whitespace, ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000))
        (partial / "content" / "knowledge" / "vi" / "content.md").unlink()
        new_file = partial / "content" / "knowledge" / "vi" / "new.md"
        new_file.write_text("New content", encoding="utf-8")

        refreshed, scanner = self.scan(cache)
        exhaustive, brute = self.scan(cache=False)
        self.assert_same_data(refreshed, exhaustive)
        self.assertEqual(refreshed["summary"]["filledMarkdownFiles"], 3)
        self.assertEqual(refreshed["summary"]["blankMarkdownFiles"], 1)
        self.assertEqual(scanner.stats["contentReads"], 2)
        self.assertEqual(scanner.stats["cacheHits"], 1)
        self.assertEqual(brute.stats["contentReads"], 3)
        self.assertNotIn(
            "learning-platform-data/module/partial/content/knowledge/vi/content.md",
            scanner.updated,
        )

    def test_invalid_cache_is_ignored_and_signature_is_validated(self):
        self.add_module("finished", {"vi/a.md": "Content"})
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text("{invalid json", encoding="utf-8")
        self.assertEqual(report_script.load_scan_cache(self.cache_path, self.root), {})
        initial, scanner = self.scan()
        report_script.write_scan_cache(self.cache_path, self.root, scanner.updated)
        cache = report_script.load_scan_cache(self.cache_path, self.root)
        cache["learning-platform-data/module/finished/content/knowledge/vi/a.md"] = [
            7, 0, 0, False
        ]
        refreshed, scanner = self.scan(cache)
        self.assert_same_data(initial, refreshed)
        self.assertEqual(scanner.stats["contentReads"], 1)

    def test_cli_full_scan_no_cache_and_incremental(self):
        self.add_module("finished", {"vi/a.md": "Content", "en/empty.md": ""})
        self.add_module("blank", {"vi/empty.md": " "})

        def run(*flags):
            argv = [
                str(SCRIPT_PATH), "--root", str(self.root), "--output-dir", "out", *flags
            ]
            out = io.StringIO()
            with patch.object(sys, "argv", argv), contextlib.redirect_stdout(out):
                self.assertEqual(report_script.main(), 0)
            return out.getvalue()

        cold = run()
        self.assertIn("cache_hits=0 content_reads=2", cold)
        self.assertTrue(self.cache_path.exists())
        warm = run()
        self.assertIn("cache_hits=2 content_reads=0", warm)
        full = run("--full-scan")
        self.assertIn("cache_hits=0 content_reads=2", full)
        no_cache = run("--no-cache")
        self.assertIn("cache_hits=0 content_reads=2", no_cache)
        self.assertIn("cache_hits=2 content_reads=0", run())

        summary = yaml.safe_load((self.root / "out" / "knowledge-finished.yml").read_text(
            encoding="utf-8"
        ))["summary"]
        self.assertEqual(summary["finishedModules"], 0)
        self.assertEqual(summary["unfinishedModules"], 1)
        self.assertEqual(summary["blankModules"], 1)


if __name__ == "__main__":
    unittest.main()
