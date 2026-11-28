#!/usr/bin/env python3
"""Report Markdown knowledge completion for every java-learning module.

A module with Markdown belongs to exactly one of:
- unfinishedKnowledge: some Markdown files have content and some are blank.
- blankKnowledge: all Markdown files are blank.
- finishedKnowledge: all Markdown files contain non-whitespace text.

Files containing only whitespace count as blank, including nonzero-byte files.
All language folders under content/knowledge are included. No module content is
modified. Three separate YAML reports are written in report/ next to this script.
Modules without any Markdown are included separately in the blank report.

An incremental cache avoids reopening unchanged nonempty Markdown files.
Use --full-scan to verify every file and refresh the cache.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import tempfile

import yaml


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "report"
CACHE_FILENAME = ".knowledge-scan-cache.json"
CACHE_VERSION = 1
GROUPS = ("unfinishedKnowledge", "blankKnowledge", "finishedKnowledge")
REPORT_FILES = {
    "unfinishedKnowledge": "knowledge-unfinished.yml",
    "finishedKnowledge": "knowledge-finished.yml",
    "blankKnowledge": "knowledge-blank.yml",
}


def metadata_value(info: dict, name: str) -> str | None:
    """Read module-info.json's nested {TYPE, DESCRIPTION, VALUE} convention."""
    field = info.get(name)
    value = field.get("VALUE") if isinstance(field, dict) else field
    return str(value) if value is not None else None


def has_markdown_content(path: Path) -> bool:
    """Equivalent to bool(read_text(encoding='utf-8-sig').strip()), but streaming."""
    with path.open("r", encoding="utf-8-sig") as file:
        while chunk := file.read(64 * 1024):
            if chunk.strip():
                return True
    return False


def windows_long_path(directory: Path) -> str:
    """Preserve support for Windows paths longer than legacy MAX_PATH."""
    path = str(directory.resolve())
    if os.name == "nt" and not path.startswith("\\\\?\\"):
        if path.startswith("\\\\"):
            return "\\\\?\\UNC\\" + path.lstrip("\\")
        return "\\\\?\\" + path
    return path


def load_scan_cache(path: Path, root: Path) -> dict:
    """An absent, outdated or damaged cache simply triggers a full read."""
    try:
        with path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    if (
        not isinstance(data, dict)
        or data.get("version") != CACHE_VERSION
        or data.get("root") != str(root)
        or not isinstance(data.get("files"), dict)
    ):
        return {}
    return data["files"]


class KnowledgeScanner:
    def __init__(self, previous: dict | None = None, *, use_cache: bool = True) -> None:
        self.previous = previous if previous is not None else {}
        self.use_cache = use_cache
        self.updated: dict[str, list] = {}
        self.stats: Counter = Counter()

    def count_files(self, directory: Path, module_key: str) -> Counter:
        result: Counter = Counter()
        if not directory.is_dir():
            return result

        # scandir's DirEntry already holds file metadata on Windows. Calling
        # Path.stat() for every file causes extra HDD work on this repository.
        # Never follow directory symlinks, matching os.walk's default.
        stack = [(windows_long_path(directory), "")]
        while stack:
            folder, relative_folder = stack.pop()
            with os.scandir(folder) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append((entry.path, relative_folder + entry.name + "/"))
                        continue
                    if not entry.name.lower().endswith(".md"):
                        continue

                    stat = entry.stat()
                    result["totalFiles"] += 1
                    self.stats["visited"] += 1
                    if stat.st_size == 0:
                        result["blankFiles"] += 1
                        self.stats["zeroByteFiles"] += 1
                        continue

                    key = f"{module_key}/content/knowledge/{relative_folder}{entry.name}"
                    signature = [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]
                    cached = self.previous.get(key) if self.use_cache else None
                    if (
                        isinstance(cached, list)
                        and len(cached) == 4
                        and cached[:3] == signature
                        and type(cached[3]) is bool
                    ):
                        filled = cached[3]
                        self.stats["cacheHits"] += 1
                    else:
                        filled = has_markdown_content(Path(entry.path))
                        self.stats["contentReads"] += 1

                    if self.use_cache:
                        self.updated[key] = signature + [filled]
                    result["filledFiles" if filled else "blankFiles"] += 1
        return result


def build_report(root: Path, scanner: KnowledgeScanner | None = None) -> dict:
    module_root = root / "learning-platform-data" / "module"
    if not module_root.is_dir():
        raise FileNotFoundError(f"Module root not found: {module_root}")

    scanner = scanner if scanner is not None else KnowledgeScanner(use_cache=False)
    report: dict = {name: [] for name in GROUPS}
    without_md: list[dict] = []
    totals: Counter = Counter()
    info_paths = sorted(module_root.rglob("module-info.json"))

    for info_path in info_paths:
        module = info_path.parent
        module_key = module.relative_to(root).as_posix()
        module_info = json.loads(info_path.read_text(encoding="utf-8-sig"))
        if not isinstance(module_info, dict):
            raise ValueError(f"Invalid module-info.json object: {info_path}")

        counts = scanner.count_files(module / "content" / "knowledge", module_key)
        item = {
            "location": module_key,
            "CURRENT_STEP": metadata_value(module_info, "CURRENT_STEP"),
            "SERVICE_NAME": metadata_value(module_info, "SERVICE_NAME"),
            "totalFiles": counts["totalFiles"],
            "blankFiles": counts["blankFiles"],
            "filledFiles": counts["filledFiles"],
        }
        totals.update({k: item[k] for k in ("totalFiles", "blankFiles", "filledFiles")})
        if item["CURRENT_STEP"] is None or item["SERVICE_NAME"] is None:
            totals["missingMetadataModules"] += 1

        if item["totalFiles"] == 0:
            without_md.append(item)
        elif item["blankFiles"] == 0:
            report["finishedKnowledge"].append(item)
        elif item["filledFiles"] == 0:
            report["blankKnowledge"].append(item)
        else:
            report["unfinishedKnowledge"].append(item)

    # List empty modules from the smallest workload to the largest; use the
    # location as a deterministic tie-breaker when totalFiles are equal.
    report["blankKnowledge"].sort(
        key=lambda item: (item["totalFiles"], item["location"])
    )

    report["summary"] = {
        "totalModules": len(info_paths),
        "unfinishedModules": len(report["unfinishedKnowledge"]),
        "blankModules": len(report["blankKnowledge"]),
        "finishedModules": len(report["finishedKnowledge"]),
        "modulesWithoutMarkdown": len(without_md),
        "missingMetadataModules": totals["missingMetadataModules"],
        "totalMarkdownFiles": totals["totalFiles"],
        "blankMarkdownFiles": totals["blankFiles"],
        "filledMarkdownFiles": totals["filledFiles"],
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    if without_md:
        # Preserve full module coverage if a future module has no Markdown yet.
        report["noKnowledgeFiles"] = without_md

    assert (
        report["summary"]["totalModules"]
        == sum(len(report[key]) for key in GROUPS) + len(without_md)
    )
    assert totals["totalFiles"] == totals["blankFiles"] + totals["filledFiles"]
    return report


def write_yaml_atomic(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, staging = tempfile.mkstemp(prefix=".knowledge-status-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as file:
            yaml.safe_dump(report, file, allow_unicode=True, sort_keys=False, width=120)
            file.flush()
            os.fsync(file.fileno())
        os.replace(staging, path)
    finally:
        if os.path.exists(staging):
            os.unlink(staging)


def write_scan_cache(path: Path, root: Path, files: dict) -> None:
    """Write a complete snapshot; removed files disappear from the next cache."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, staging = tempfile.mkstemp(prefix=".knowledge-cache-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(
                {"version": CACHE_VERSION, "root": str(root), "files": files},
                stream,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staging, path)
    finally:
        if os.path.exists(staging):
            os.unlink(staging)


def write_reports(directory: Path, report: dict) -> list[Path]:
    """Write each classification to its own YAML without changing item fields."""
    paths = []
    for group, filename in REPORT_FILES.items():
        output = {group: report[group], "summary": report["summary"]}
        if group == "blankKnowledge" and "noKnowledgeFiles" in report:
            output["noKnowledgeFiles"] = report["noKnowledgeFiles"]
        path = directory / filename
        write_yaml_atomic(path, output)
        paths.append(path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=REPO_ROOT,
        help="java-learning repository root (default: detected from script location)",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
        help="Directory for three YAML reports (default: report/ beside this script)",
    )
    parser.add_argument(
        "--full-scan", action="store_true",
        help="Recheck every Markdown file and replace the incremental cache",
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="Read every Markdown file without reading or writing a cache",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    output_dir = args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
    cache_path = output_dir / CACHE_FILENAME
    use_cache = not args.no_cache
    previous = (
        load_scan_cache(cache_path, root) if use_cache and not args.full_scan else {}
    )
    scanner = KnowledgeScanner(previous, use_cache=use_cache)

    report = build_report(root, scanner)
    paths = write_reports(output_dir, report)
    if use_cache:
        try:
            write_scan_cache(cache_path, root, scanner.updated)
        except OSError as error:
            print(f"CACHE_WARNING {error}", file=sys.stderr)
    summary = report["summary"]
    for path in paths:
        print(f"REPORT_WRITTEN {path}")
    print(
        f"MODULES total={summary['totalModules']} "
        f"unfinished={summary['unfinishedModules']} "
        f"blank={summary['blankModules']} "
        f"finished={summary['finishedModules']} "
        f"no_markdown={summary['modulesWithoutMarkdown']}"
    )
    print(
        f"MARKDOWN total={summary['totalMarkdownFiles']} "
        f"blank={summary['blankMarkdownFiles']} "
        f"filled={summary['filledMarkdownFiles']}"
    )
    print(
        f"SCAN visited={scanner.stats['visited']} "
        f"zero_bytes={scanner.stats['zeroByteFiles']} "
        f"cache_hits={scanner.stats['cacheHits']} "
        f"content_reads={scanner.stats['contentReads']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
