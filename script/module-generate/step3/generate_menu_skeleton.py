#!/usr/bin/env python3
"""STEP_3_NEW: create the two empty Knowledge menu YAML files only."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from generate_menu_detail import (
    Step3Error,
    dump_yaml,
    ensure_regular_or_absent,
    load_yaml_object,
    knowledge_root,
    module_path,
    service_name,
    write_new,
)


def prestart(module: Path, dry_run: bool, lang: str = "vi") -> None:
    subject = service_name(module)
    target_dir = knowledge_root(module, lang)
    if target_dir.is_symlink() or (target_dir.exists() and not target_dir.is_dir()):
        raise Step3Error(f"Knowledge path is not a normal directory: {target_dir}")

    templates = {
        "menu.yml": dump_yaml({"menu": []}),
        "menu-level-1-slug.yml": dump_yaml({"menu": []}),
    }

    # Preflight EVERY target before writing anything. Existing work is preserved.
    for filename in templates:
        ensure_regular_or_absent(target_dir / filename)
    for filename in ("menu.yml", "menu-level-1-slug.yml"):
        if (target_dir / filename).is_file():
            current = load_yaml_object(target_dir / filename)
            if type(current.get("menu")) is not list or set(current) != {"menu"}:
                raise Step3Error(f"{filename} must contain only a menu list")

    new_files = [target_dir / name for name in templates if not (target_dir / name).exists()]
    if dry_run:
        print(f"DRY_RUN module={module} subject={subject} new_files={len(new_files)}")
        return

    created_files: list[Path] = []
    created_dirs: list[Path] = []
    try:
        for directory in (module / "content", module / "content" / "knowledge", target_dir):
            if not directory.exists():
                directory.mkdir()
                created_dirs.append(directory)
        for filename, text in templates.items():
            dest = target_dir / filename
            if not dest.exists():
                write_new(dest, text)
                created_files.append(dest)
    except Exception:
        for file in reversed(created_files):
            file.unlink(missing_ok=True)
        for directory in reversed(created_dirs):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise

    print(
        f"PRESTART_OK module={module} subject={subject} "
        f"created={len(created_files)} preserved={len(templates) - len(created_files)} "
        f"knowledge={target_dir}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True, help="Path to module containing module-info.json")
    parser.add_argument("--lang", "--language", dest="lang", default="vi",
                        help="Language folder under content/knowledge/ (default: vi)")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing files")
    args = parser.parse_args()
    try:
        prestart(module_path(args.module), args.dry_run, lang=args.lang)
    except (Step3Error, OSError, ValueError) as exc:
        print(f"BLOCKER: STEP_3_PRESTART: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
