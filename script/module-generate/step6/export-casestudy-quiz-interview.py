#!/usr/bin/env python3
"""STEP 6 PRIME: export byte-identical local assessment YAMLs after Phase 5."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import sys
import tempfile

from split_menu import (
    Step6Error, check_manifest, digest, load_manifest, module_context,
    regular_file,
)
from readme_related import (
    KINDS, RelatedError, chapter_catalog, load_yaml, read_assessments,
    read_file, related_links, semantic_fingerprint,
)


def export_plan(module_arg: str, *, lang: str = "vi",
                replace_existing: bool = False) -> tuple[list, dict]:
    module, service, stage = module_context(module_arg, lang)
    manifest = load_manifest(stage)
    check_manifest(manifest, module, service, lang)
    merged = stage / "merged.json"
    if not merged.is_file():
        raise Step6Error("Knowledge merge missing before assessment export")
    import json

    marker = json.loads(regular_file(merged).decode("utf-8"))
    knowledge = module / "content" / "knowledge" / lang / "menu-detail-status.yml"
    if digest(regular_file(knowledge)) != marker.get("merged_sha256"):
        raise Step6Error("Knowledge source no longer matches merged data")
    chapter_menu = module / "content" / "knowledge" / lang / "menu-level-1-slug.yml"
    if digest(regular_file(chapter_menu)) != manifest["chapter_menu_sha256"]:
        raise Step6Error("Knowledge chapter catalog changed")
    from split_menu import read_status
    if any(read_status(stage / ch["status_file"]) != "WRITTEN"
           for ch in manifest["chapters"]):
        raise Step6Error("Not all chapter Workers completed Related")
    assess_stage = module / "content" / "temp" / "step5"
    inputs, data, items = read_assessments(assess_stage)
    links = related_links(assess_stage, chapter_catalog(module, lang), items)
    for kind in KINDS:
        status = load_yaml(assess_stage / "status" / f"{kind}.yml")
        if type(status) is not dict or status != {"status": "Phase 5"}:
            raise Step6Error(f"{kind} has not reached Phase 5")
        if semantic_fingerprint(kind, data[kind]) != manifest["assessment_semantic_sha256"][kind]:
            raise Step6Error(f"Non-related assessment content changed after split: {kind}")
        for key, item in items[kind].items():
            if item["readmeRelated"]["anchorList"] != links[kind][key]:
                raise Step6Error(f"Mismatched Related for {kind} {key}")
    writes = []
    counts = {}
    for kind in KINDS:
        source = assess_stage / "format" / f"{kind}.yml"
        target = module / "content" / kind / lang / f"{kind}.yml"
        for parent in (target.parent.parent, target.parent):
            if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                raise Step6Error(f"Unsafe export directory: {parent}")
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise Step6Error(f"Unsafe export target: {target}")
        before = read_file(target) if target.exists() else None
        new = inputs[kind]
        if before is not None and before != new and not replace_existing:
            raise Step6Error(f"Existing {target} differs; require --replace-existing")
        if before != new:
            writes.append((target, before, new))
        counts[kind] = {"items": len(items[kind]), "bytes": len(new)}
    return writes, counts


def atomic_replace(path: Path, before: bytes | None, after: bytes) -> None:
    if before is None:
        if path.exists() or path.is_symlink():
            raise Step6Error(f"Concurrent creation at {path}")
    elif read_file(path) != before:
        raise Step6Error(f"Export target modified concurrently: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".step6-export-", dir=path.parent)
    try:
        if before is not None:
            os.chmod(tmp, stat.S_IMODE(path.stat().st_mode))
        with os.fdopen(fd, "wb") as out:
            out.write(after)
            out.flush()
            os.fsync(out.fileno())
        if before is None and (path.exists() or path.is_symlink()):
            raise Step6Error(f"Concurrent creation at {path}")
        if before is not None and read_file(path) != before:
            raise Step6Error(f"Export target changed before commit: {path}")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    if read_file(path) != after:
        raise Step6Error(f"Export readback mismatch: {path}")


def export(module_arg: str, *, lang: str = "vi", dry_run: bool = False,
           replace_existing: bool = False) -> str:
    writes, counts = export_plan(module_arg, lang=lang, replace_existing=replace_existing)
    if dry_run:
        return f"DRY_RUN export PASS changed={len(writes)} counts={counts}"
    applied = []
    try:
        for target, before, content in writes:
            atomic_replace(target, before, content)
            applied.append((target, before, content))
    except Exception as exc:
        errors = []
        for target, before, content in reversed(applied):
            try:
                if read_file(target) != content:
                    raise Step6Error("Concurrent modification during rollback")
                if before is None:
                    target.unlink()
                else:
                    atomic_replace(target, content, before)
            except Exception as rollback_exc:
                errors.append(str(rollback_exc))
        raise Step6Error(f"Export failed: {exc}; rollback issues={errors}") from exc
    remaining, _ = export_plan(module_arg, lang=lang, replace_existing=True)
    if remaining:
        raise Step6Error(f"Export exact readback incomplete: {remaining}")
    return f"{'EXPORT_OK' if writes else 'ALREADY_EXPORTED'} byte-identical=True counts={counts}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True)
    parser.add_argument("--lang", default="vi")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--replace-existing", action="store_true",
                        help="Explicitly replace different existing assessment files")
    args = parser.parse_args()
    try:
        print(export(args.module, lang=args.lang, dry_run=args.dry_run,
                     replace_existing=args.replace_existing))
        return 0
    except (RelatedError, Step6Error, OSError, ValueError, UnicodeError) as exc:
        print(f"BLOCKER: STEP6_EXPORT: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
