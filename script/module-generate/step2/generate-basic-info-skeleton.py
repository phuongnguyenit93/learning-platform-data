#!/usr/bin/env python3
"""Create the three empty, file-first STEP_2_NEW targets for one module.

From the learning-platform-data repository root:
    python script/module-generate/step2/generate-basic-info-skeleton.py --module module/path --lang vi
    python script/module-generate/step2/generate-basic-info-skeleton.py --module module/path --lang vi --dry-run

Existing files are never rewritten. No Google Sheets, Gradle or database work.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[3]
MODULE_ROOT = ROOT / "module"
LANG_RE = re.compile(r"[a-z][a-z0-9-]{0,9}\Z")
SERVICE_NAME_RE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*\Z")


class SkeletonError(Exception):
    pass


def json_object(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise SkeletonError(f"Missing or unsafe metadata file: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise SkeletonError(f"Invalid JSON: {path}") from exc
    if type(data) is not dict:
        raise SkeletonError(f"JSON root must be an object: {path}")
    return data


def module_directory(request: str) -> Path:
    root = MODULE_ROOT.resolve(strict=True)
    candidate = Path(request)
    if not candidate.is_absolute():
        candidate = (MODULE_ROOT / Path(*candidate.parts[1:])
                     if candidate.parts and candidate.parts[0] == "module"
                     else ROOT / candidate)
    # Inspect the user-provided path before resolve() hides symlink segments.
    for ancestor in (candidate, *candidate.parents):
        if ancestor.is_symlink():
            raise SkeletonError(f"Symlink module directory is not allowed: {ancestor}")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root) or resolved == root:
        raise SkeletonError("Module must be inside learning-platform-data/module/")
    if not candidate.is_dir():
        raise SkeletonError(f"Module directory not found: {candidate}")
    current = root
    for part in resolved.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise SkeletonError(f"Symlink module directory is not allowed: {current}")
    activation = json_object(resolved / "module_activate.json")
    if activation.get("isModule") is not True:
        raise SkeletonError("module_activate.json must contain boolean isModule: true")
    info = json_object(resolved / "module-info.json")
    service_field = info.get("SERVICE_NAME")
    service_name = service_field.get("VALUE") if type(service_field) is dict else None
    if type(service_name) is not str or not SERVICE_NAME_RE.fullmatch(service_name):
        raise SkeletonError("module-info.json SERVICE_NAME.VALUE is missing or invalid")
    return resolved


def plan(module: Path, lang: str) -> tuple[dict[Path, bytes], list[Path]]:
    info = json_object(module / "module-info.json")
    languages = info.get("MODULE_LANGUAGE")
    supported = languages.get("VALUE") if type(languages) is dict else None
    if type(supported) is not list or lang not in supported:
        raise SkeletonError(f"Module does not list language {lang!r} in MODULE_LANGUAGE.VALUE")
    targets = {
        module / "content" / "reference" / lang / "references.yml": b"references: []\n",
        module / "content" / "roadmap" / lang / "roadmap.yml": b"roadmap: []\n",
        module / "content" / "base" / lang / "base.md": b"",
    }
    for target in targets:
        current = target.parent
        while current != module:
            if current.is_symlink() or (current.exists() and not current.is_dir()):
                raise SkeletonError(f"Unsafe output directory: {current}")
            current = current.parent
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise SkeletonError(f"Unsafe output file: {target}")
    return targets, [target for target in targets if not target.exists()]


def generate(module: Path, lang: str, dry_run: bool) -> None:
    targets, missing = plan(module, lang)
    if dry_run:
        print(f"DRY_RUN module={module} lang={lang} new={len(missing)} existing={len(targets)-len(missing)}")
        for target in targets:
            print(f"  {'CREATE' if target in missing else 'PRESERVE'} {target.relative_to(ROOT.resolve())}")
        return

    created_files: list[Path] = []
    created_dirs: list[Path] = []
    try:
        for target in missing:
            directories: list[Path] = []
            current = target.parent
            while not current.exists():
                directories.append(current)
                current = current.parent
            for directory in reversed(directories):
                directory.mkdir()
                created_dirs.append(directory)
            with target.open("xb") as out:
                created_files.append(target)
                out.write(targets[target])
    except Exception:
        for target in reversed(created_files):
            target.unlink(missing_ok=True)
        for directory in reversed(created_dirs):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise
    print(f"SKELETON_OK module={module} lang={lang} created={len(created_files)} preserved={len(targets)-len(missing)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True, help="Existing module directory inside learning-platform-data/module/")
    parser.add_argument("--lang", default="vi", help="Target language (default: vi)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating files")
    args = parser.parse_args()
    if not LANG_RE.fullmatch(args.lang):
        parser.error("--lang must be a valid language code")
    try:
        generate(module_directory(args.module), args.lang, args.dry_run)
    except (SkeletonError, OSError) as exc:
        print(f"BLOCKER: STEP_2_SKELETON: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
