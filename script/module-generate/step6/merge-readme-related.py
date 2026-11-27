#!/usr/bin/env python3
"""STEP 6 PRIME: merge all chapter related proposals into three local YAMLs.

This script is the ONLY writer of assessment status "Phase 5". It never writes
Knowledge or worker chapter files. It can safely resume partial prior commits.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from split_menu import (
    Step6Error, check_manifest, digest, load_manifest, module_context,
    read_status, regular_file,
)
from merge_menu import safe_write
from readme_related import (
    FINAL_BEFORE_RELATED, KINDS, RelatedError, chapter_catalog, load_yaml,
    read_assessments, read_file, related_links, semantic_fingerprint,
    to_yaml, validate_assessment,
)


def plan(module_arg: str, *, lang: str = "vi") -> tuple[list, dict]:
    module, service, stage = module_context(module_arg, lang)
    manifest = load_manifest(stage)
    check_manifest(manifest, module, service, lang)
    menu_path = module / "content" / "knowledge" / lang / "menu-level-1-slug.yml"
    if digest(regular_file(menu_path)) != manifest["chapter_menu_sha256"]:
        raise Step6Error("Chapter menu changed since STEP 6 split")
    marker = stage / "merged.json"
    if not marker.is_file():
        raise Step6Error("Run merge_menu.py before merging Related")
    receipt = json.loads(regular_file(marker).decode("utf-8"))
    source = module / "content" / "knowledge" / lang / "menu-detail-status.yml"
    if digest(regular_file(source)) != receipt.get("merged_sha256"):
        raise Step6Error("Knowledge merge marker or source changed")
    for chapter in manifest["chapters"]:
        if read_status(stage / chapter["status_file"]) != "WRITTEN":
            raise Step6Error(f"Related work not completed: {chapter['slug']}")
    catalog = chapter_catalog(module, lang)
    if [ch["slug"] for ch in catalog] != [e["slug"] for e in manifest["chapters"]]:
        raise Step6Error("Knowledge catalog does not match STEP 6 split")

    assessments = module / "content" / "temp" / "step5"
    contents, data, items = read_assessments(assessments)
    links = related_links(assessments, catalog, items)
    writes = []
    report = {}
    for kind in KINDS:
        if semantic_fingerprint(kind, data[kind]) != manifest["assessment_semantic_sha256"][kind]:
            raise Step6Error(f"Non-related assessment content changed: {kind}")
        original = assessments / "format" / f"{kind}.yml"
        status_path = assessments / "status" / f"{kind}.yml"
        status = load_yaml(status_path)
        if type(status) is not dict or set(status) != {"status"} or (
            status["status"] not in (f"Phase {FINAL_BEFORE_RELATED[kind]}", "Phase 5")
        ):
            raise Step6Error(f"Invalid Phase 5 prerequisite: {kind} {status!r}")
        changed = 0
        for key, item in items[kind].items():
            expected = links[kind][key]
            current = item["readmeRelated"]["anchorList"]
            if current not in ([], expected):
                raise Step6Error(f"Existing Related conflicts with proposals: {kind} {key}")
            if current != expected:
                item["readmeRelated"]["anchorList"] = expected
                changed += 1
        if status["status"] == "Phase 5" and changed:
            raise Step6Error(f"Phase 5 set before Related completion: {kind}")
        validate_assessment(kind, data[kind])
        new_bytes = to_yaml(data[kind]) if changed else contents[kind]
        if changed:
            writes.append((original, contents[kind], new_bytes))
        status_bytes = read_file(status_path)
        final_status = b"status: Phase 5\n"
        if status["status"] != "Phase 5":
            writes.append((status_path, status_bytes, final_status))
        report[kind] = {"items": len(items[kind]), "linked_items": sum(
            bool(value) for value in links[kind].values()
        ), "links": sum(len(value) for value in links[kind].values()),
                        "updated_items": changed}
    return writes, report


def merge_related(module_arg: str, *, lang: str = "vi", dry_run: bool = False) -> str:
    writes, report = plan(module_arg, lang=lang)
    if dry_run:
        return f"DRY_RUN Related validation PASS; pending_files={len(writes)} report={report}"
    applied = []
    try:
        # All formats are written/verified before any status is advanced.
        for path, before, after in writes:
            safe_write(path, before, after)
            applied.append((path, before, after))
    except Exception as exc:
        errors = []
        for path, before, after in reversed(applied):
            try:
                safe_write(path, after, before)
            except Exception as rollback_exc:
                errors.append(f"{path}: {rollback_exc}")
        if errors:
            raise Step6Error(f"Related transaction failed ({exc}); rollback blocked: {errors}") from exc
        raise Step6Error(f"Related transaction rolled back: {exc}") from exc
    again, _ = plan(module_arg, lang=lang)
    if again:
        raise Step6Error("Readback not fully complete after Related merge")
    return f"{'MERGE_OK' if writes else 'ALREADY_MERGED'} Related status=Phase 5 report={report}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True)
    parser.add_argument("--lang", default="vi")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        print(merge_related(args.module, lang=args.lang, dry_run=args.dry_run))
        return 0
    except (RelatedError, Step6Error, OSError, UnicodeError, ValueError) as exc:
        print(f"BLOCKER: STEP6_RELATED_MERGE: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
