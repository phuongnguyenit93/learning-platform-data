#!/usr/bin/env python3
"""Legacy-only: update note.yml and each per-lesson specialNote consistently.

STEP 3/4 NEW does not create or use these fields. This command refuses the
modern layout, never creates legacy files, and only edits existing legacy YAML.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


SCRIPT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_ROOT / "step3"))
sys.path.insert(0, str(SCRIPT_ROOT / "step4"))
from generate_menu_detail import Step3Error, module_path  # noqa: E402
from _knowledge_local import (  # noqa: E402
    apply_changes, load_layout, replace_top_level_scalar,
)


def update(module: Path, lang: str, mode: str, text: str, *, dry_run: bool) -> int:
    # The layout is fully validated BEFORE any changes. Existing legacy lesson
    # fields may differ when replacing, but not when adding a note.
    layout = load_layout(module, lang=lang, same_special_note=False)
    if layout.note_path is None or layout.note is None:
        raise Step3Error("Legacy note.yml absent; modern STEP 3/4 NEW does not use specialNote")
    if any("specialNote" not in lesson.info for lesson in layout.lessons):
        raise Step3Error("Legacy specialNote missing from a lesson; refusing partial migration")

    old = layout.note["specialNote"]
    if mode == "add":
        if not text.strip():
            raise Step3Error("Cannot add an empty special note")
        if any(lesson.info["specialNote"] != old for lesson in layout.lessons):
            raise Step3Error("Existing lesson specialNote differs from note.yml; use replace")
        parts = old.split("\n\n") if old else []
        new_value = old if text in parts else (old + "\n\n" + text if old else text)
    else:
        new_value = text

    changes: dict[Path, tuple[bytes, bytes]] = {}
    sources = [(layout.note_path, layout.note), *(
        (lesson.info_path, lesson.info) for lesson in layout.lessons
    )]
    for path, data in sources:
        if data["specialNote"] == new_value:
            continue
        before = path.read_bytes()
        raw = before.decode("utf-8-sig")
        after = replace_top_level_scalar(raw, "specialNote", new_value, data).encode("utf-8")
        if before != after:
            changes[path] = (before, after)
    if not dry_run and changes:
        apply_changes(changes)
    print(f"{'DRY_RUN' if dry_run else 'UPDATED'} changed_files={len(changes)} "
          f"mode={mode} lang={lang}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True)
    parser.add_argument("--lang", default="vi")
    parser.add_argument("--mode", required=True, choices=("add", "replace"))
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--special-note", nargs="?", const="", default=None)
    source.add_argument("--note-file", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.mode == "add" and args.special_note == "":
            raise Step3Error("Cannot add an empty special note")
        text = args.note_file.read_text(encoding="utf-8-sig") if args.note_file else args.special_note
        return update(module_path(args.module), args.lang, args.mode, text,
                      dry_run=args.dry_run)
    except (Step3Error, OSError, ValueError, UnicodeError) as exc:
        print(f"BLOCKER: LEGACY_SPECIAL_NOTE: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
