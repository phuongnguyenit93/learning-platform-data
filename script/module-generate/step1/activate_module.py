#!/usr/bin/env python3
"""STEP 1 NEW: initialize metadata for explicitly activated modules.

No Gradle or java-learning parent checkout is required. By default the command
only previews changes; --apply is required for disk writes. An existing value
(including an empty value) is never overwritten.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path, PureWindowsPath
import re
import sys
import tempfile


DATA_ROOT = Path(__file__).resolve().parents[3]
MODULE_ROOT = DATA_ROOT / "module"
TEMPLATE_FILE = DATA_ROOT / "module-info-base.json"
SKIPPED_FOLDERS = frozenset({".git", ".gradle", "content", "build", "temp", "__pycache__"})
SERVICE_RE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*\Z")


class ActivationError(ValueError):
    """Unexpected module metadata or unsafe input; nothing should be changed."""


def read_object(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ActivationError(f"Missing or unsafe JSON file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise ActivationError(f"Invalid JSON file: {path}") from exc
    if type(value) is not dict:
        raise ActivationError(f"Expected a JSON object: {path}")
    return value


def ensure_below_modules(path: Path) -> Path:
    root = MODULE_ROOT.resolve(strict=True)
    if not MODULE_ROOT.is_dir() or MODULE_ROOT.is_symlink():
        raise ActivationError("Unsafe module root")
    if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root):
        raise ActivationError(f"Symlinked module path not allowed: {path}")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root) or resolved == root or not resolved.is_dir():
        raise ActivationError(f"Module must be inside {root}: {path}")
    return resolved


def module_from_arg(value: str) -> Path:
    value = value.replace("\\", "/")
    relative = Path(value)
    if (not value or relative.is_absolute() or PureWindowsPath(value).is_absolute()
            or ".." in relative.parts or not relative.parts or relative.parts[0] != "module"):
        raise ActivationError("--module must be a relative module/... path")
    candidate = MODULE_ROOT.joinpath(*relative.parts[1:])
    return ensure_below_modules(candidate)


def activated_modules() -> list[Path]:
    if not MODULE_ROOT.is_dir():
        raise ActivationError(f"Missing module directory: {MODULE_ROOT}")
    candidates: list[Path] = []
    for folder, dirs, names in os.walk(MODULE_ROOT, followlinks=False):
        dirs[:] = sorted(x for x in dirs if x not in SKIPPED_FOLDERS
                         and not (Path(folder) / x).is_symlink())
        if "module_activate.json" in names:
            candidates.append(ensure_below_modules(Path(folder)))
    return candidates


def plan_one(module: Path, template: dict) -> tuple[Path, dict, bool, list[str], bytes | None]:
    activation = read_object(module / "module_activate.json")
    if activation.get("isModule") is not True:
        raise ActivationError(f"Module not activated (isModule != true): {module}")
    path = module / "module-info.json"
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ActivationError(f"Unsafe module-info.json: {path}")
    original = path.read_bytes() if path.exists() else None
    if original is None:
        current = {}
    else:
        try:
            current = json.loads(original.decode("utf-8-sig"))
        except (UnicodeError, ValueError) as exc:
            raise ActivationError(f"Invalid JSON file: {path}") from exc
        if type(current) is not dict:
            raise ActivationError(f"Expected JSON object: {path}")
    result = deepcopy(current)
    for name, field in template.items():
        if name not in result:
            result[name] = deepcopy(field)
        elif type(result[name]) is dict and type(field) is dict:
            for key, value in field.items():
                result[name].setdefault(key, deepcopy(value))
        elif type(result[name]) is not dict:
            raise ActivationError(f"Invalid metadata field {name}: {path}")
    service = result["SERVICE_NAME"].get("VALUE")
    if service and (type(service) is not str or not SERVICE_RE.fullmatch(service)):
        raise ActivationError(f"Invalid SERVICE_NAME.VALUE: {path}")
    pending = [name for name in ("SERVICE_NAME", "SERVICE_NAME_DESCRIBE")
               if not isinstance(result[name].get("VALUE"), str)
               or not result[name]["VALUE"].strip()]
    return path, result, result != current, pending, original


def atomic_write_if_unchanged(path: Path, data: dict, before: bytes | None) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".module-info-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_symlink() or (path.read_bytes() if path.exists() else None) != before:
            raise ActivationError(f"module-info.json changed during activation: {path}")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def run(modules: list[Path], *, apply: bool) -> int:
    template = read_object(TEMPLATE_FILE)
    if not modules:
        raise ActivationError("No activated modules selected")
    planned = [plan_one(module, template) for module in modules]
    for path, _, changed, pending, _ in planned:
        print(f"{'WRITE' if apply and changed else 'WOULD_WRITE' if changed else 'UNCHANGED'} "
              f"{path.relative_to(DATA_ROOT)} pending={','.join(pending) or 'none'}")
    if apply:
        for path, data, changed, _, before in planned:
            if changed:
                atomic_write_if_unchanged(path, data, before)
    print(f"ACTIVATION_{'APPLIED' if apply else 'DRY_RUN'} modules={len(planned)} "
          f"changes={sum(x[2] for x in planned)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--module", action="append", help="One module/... directory (repeatable)")
    scope.add_argument("--all", action="store_true", help="Scan every activated module")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview only (default)")
    mode.add_argument("--apply", action="store_true", help="Write missing metadata")
    args = parser.parse_args(argv)
    try:
        modules = (activated_modules() if args.all else
                   [module_from_arg(item) for item in args.module])
        modules = sorted(set(modules))
        return run(modules, apply=args.apply)
    except (ActivationError, OSError) as exc:
        print(f"BLOCKER: STEP1_ACTIVATION: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
