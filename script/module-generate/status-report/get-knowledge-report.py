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
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "report"
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


def count_knowledge_files(directory: Path) -> Counter:
    result: Counter = Counter()
    if not directory.is_dir():
        return result

    # Windows' legacy MAX_PATH prevents stat/open on paths > 260 characters
    # even when os.walk can enumerate them. Use extended-length paths for
    # the entire walk so every existing Markdown file is counted correctly.
    if os.name == "nt":
        absolute = str(directory.resolve())
        if not absolute.startswith("\\\\?\\"):
            if absolute.startswith("\\\\"):
                absolute = "\\\\?\\UNC\\" + absolute.lstrip("\\")
            else:
                absolute = "\\\\?\\" + absolute
        directory = Path(absolute)

    # Walk the knowledge tree (vi, en, and any additional language folders).
    for folder, _, filenames in os.walk(directory):
        for filename in filenames:
            if not filename.lower().endswith(".md"):
                continue
            path = Path(folder) / filename
            result["totalFiles"] += 1
            if path.stat().st_size == 0 or not has_markdown_content(path):
                result["blankFiles"] += 1
            else:
                result["filledFiles"] += 1
    return result


def build_report(root: Path) -> dict:
    module_root = root / "learning-platform-data" / "module"
    if not module_root.is_dir():
        raise FileNotFoundError(f"Module root not found: {module_root}")

    report: dict = {name: [] for name in GROUPS}
    without_md: list[dict] = []
    totals: Counter = Counter()
    info_paths = sorted(module_root.rglob("module-info.json"))

    for info_path in info_paths:
        module = info_path.parent
        module_info = json.loads(info_path.read_text(encoding="utf-8-sig"))
        if not isinstance(module_info, dict):
            raise ValueError(f"Invalid module-info.json object: {info_path}")

        counts = count_knowledge_files(module / "content" / "knowledge")
        item = {
            "location": module.relative_to(root).as_posix(),
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
    args = parser.parse_args()
    root = args.root.resolve()
    output_dir = args.output_dir if args.output_dir.is_absolute() else root / args.output_dir

    report = build_report(root)
    paths = write_reports(output_dir, report)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
