#!/usr/bin/env python3
"""STEP 6: cleanup local staging only after Knowledge + Phase 5 export pass.

The source menu-detail-status.yml remains untouched. Cleanup is NEVER part
of merge_menu.py, and cannot run without a valid merge completion marker.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

from split_menu import (
    Step6Error, check_manifest, digest, load_json, load_manifest, module_context,
    read_status, regular_file, verify_stage_inventory,
)
from merge_menu import staged_hashes
from readme_related import (
    KINDS, RelatedError, chapter_catalog, read_assessments,
    read_file, load_yaml, related_links,
)


def cleanup(module_arg: str, *, lang: str = "vi", dry_run: bool = False) -> str:
    module, service, stage = module_context(module_arg, lang)
    manifest = load_manifest(stage)
    check_manifest(manifest, module, service, lang)
    verify_stage_inventory(stage, manifest, merged=True)
    marker = load_json(stage / "merged.json")
    if marker.get("version") != 1 or marker.get("source_sha256") != manifest["source_sha256"]:
        raise Step6Error("Invalid merge completion marker")
    if marker.get("manifest_sha256") != digest(regular_file(stage / "manifest.json")):
        raise Step6Error("Manifest changed since merge")
    if marker.get("files_sha256") != staged_hashes(stage, manifest):
        raise Step6Error("Staged chapter/status files changed since merge")
    if any(read_status(stage / item["status_file"]) != "WRITTEN"
           for item in manifest["chapters"]):
        raise Step6Error("A chapter is no longer marked WRITTEN")
    source = module / "content" / "knowledge" / lang / "menu-detail-status.yml"
    if digest(regular_file(source)) != marker.get("merged_sha256"):
        raise Step6Error("Merged source no longer matches marker; refusing cleanup")
    assess_stage = module / "content" / "temp" / "step5"
    contents, _data, items = read_assessments(assess_stage)
    links = related_links(assess_stage, chapter_catalog(module, lang), items)
    for kind in KINDS:
        status = load_yaml(assess_stage / "status" / f"{kind}.yml")
        if status != {"status": "Phase 5"}:
            raise Step6Error(f"Assessment {kind} is not at Phase 5")
        if any(item["readmeRelated"]["anchorList"] != links[kind][key]
               for key, item in items[kind].items()):
            raise Step6Error(f"Assessment {kind} related not fully merged")
        output = module / "content" / kind / lang / f"{kind}.yml"
        if regular_file(output) != contents[kind]:
            raise Step6Error(f"Export not byte-identical to STEP 5 format: {output}")
    # Never delete files outside the exact 3 kinds x 3 root files and chapter inventory.
    expected = {"raw", "format", "status", "readme-related"}
    if assess_stage.is_symlink() or {entry.name for entry in assess_stage.iterdir()} != expected:
        raise Step6Error("Unexpected STEP 5 staging content; refusing cleanup")
    for folder in ("raw", "format", "status"):
        entries = assess_stage / folder
        if entries.is_symlink() or not entries.is_dir() or (
            {entry.name for entry in entries.iterdir()} != {f"{kind}.{'md' if folder == 'raw' else 'yml'}" for kind in KINDS}
        ):
            raise Step6Error(f"STEP 5 staging inventory differs: {entries}")
        for file in entries.iterdir():
            regular_file(file)

    if dry_run:
        return f"DRY_RUN stage={stage} verified_merged=True verified_export=True"

    # Both scoped staging folders have been checked against exact inventories.
    # Remove STEP 5 and then chapter staging; never remove exported content.
    shutil.rmtree(assess_stage)
    shutil.rmtree(stage)
    for directory in (stage.parent, stage.parent.parent):
        if directory.is_dir() and not directory.is_symlink():
            try:
                directory.rmdir()  # Only remove empty parent folders.
            except OSError:
                break
    for directory in (assess_stage.parent,):
        if directory.is_dir() and not directory.is_symlink():
            try:
                directory.rmdir()
            except OSError:
                pass
    return f"CLEANUP_OK removed={assess_stage},{stage} exports_preserved=True"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True)
    parser.add_argument("--lang", default="vi")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        print(cleanup(args.module, lang=args.lang, dry_run=args.dry_run))
        return 0
    except (Step6Error, OSError, UnicodeError, ValueError) as exc:
        print(f"BLOCKER: STEP6_CLEANUP: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
