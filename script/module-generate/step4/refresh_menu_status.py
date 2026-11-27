#!/usr/bin/env python3
"""STEP_4_NEW: refresh consolidated lesson status from per-lesson YAML (local only)."""

from __future__ import annotations

import argparse
from collections import Counter
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "step3"))

from generate_menu_detail import Step3Error, module_path
from _knowledge_local import (
    apply_changes, load_layout, markdown_has_content, replace_detail_statuses,
)

FINISHED_STATES = frozenset({"WRITTEN", "UPLOADED", "SKIPPED_EXISTING"})


def refresh(module, *, dry_run: bool, verify: bool, lang: str = "vi") -> None:
    layout = load_layout(module, lang=lang)
    desired = copy.deepcopy(layout.detail)
    status_counts: Counter[str] = Counter()
    changed = 0

    # Read and validate ALL lesson statuses before changing the summary.
    for lesson in layout.lessons:
        status = lesson.info["status"]
        if status and not markdown_has_content(lesson.markdown_path):
            raise Step3Error(
                f"Non-empty status {status!r} but Markdown is blank: {lesson.markdown_path}"
            )
        status_counts[status or "PENDING"] += 1
        child = desired["menu"][lesson.chapter_index]["childs"][lesson.lesson_index]
        if child["status"] != status:
            child["status"] = status
            changed += 1

    if verify:
        unfinished = [lesson.slug for lesson in layout.lessons
                      if lesson.info["status"] not in FINISHED_STATES]
        if unfinished:
            example = ", ".join(unfinished[:5])
            raise Step3Error(
                f"STEP 4 not complete: {len(unfinished)} lessons unfinished; first: {example}"
            )
        # All status-bearing Markdown files were read above. This checks
        # technical storage completion, NOT the academic correctness of content.

    original_bytes = layout.detail_path.read_bytes()
    raw = original_bytes.decode("utf-8-sig")
    updated = replace_detail_statuses(raw, layout.detail, desired)
    if changed == 0 and updated != raw:
        raise Step3Error("Unexpected text-only status mutation; refusing rewrite")
    planned = {layout.detail_path: (original_bytes, updated.encode("utf-8"))} \
        if changed else {}
    if not dry_run and planned:
        apply_changes(planned)

    labels = ", ".join(f"{k}={v}" for k, v in sorted(status_counts.items()))
    action = "DRY_RUN" if dry_run else ("REFRESHED" if changed else "UNCHANGED")
    print(f"{action} module={module} chapters={len(desired['menu'])} "
          f"lessons={len(layout.lessons)} statuses_changed={changed} "
          f"counts=[{labels}] verified={verify}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True, help="Module folder containing module-info.json")
    parser.add_argument("--lang", "--language", dest="lang", default="vi",
                        help="Language folder under content/knowledge/ (default: vi)")
    parser.add_argument("--dry-run", action="store_true", help="Validate and preview; no writes")
    parser.add_argument(
        "--verify", action="store_true",
        help="Require all lessons finished and Markdown non-empty (not content QA)",
    )
    args = parser.parse_args()
    try:
        refresh(module_path(args.module), dry_run=args.dry_run, verify=args.verify,
                lang=args.lang)
        return 0
    except (Step3Error, OSError, UnicodeError, ValueError) as exc:
        print(f"BLOCKER: STEP_4_REFRESH: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
