#!/usr/bin/env python3
"""STEP 2 NEW importers: explicitly scoped, activated modules only.

Source validation is completely offline. DB preview only SELECTs, and only
--apply performs Oracle MERGE via the existing repository-wide sync helpers.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any


DATA_ROOT = Path(__file__).resolve().parents[3]
MODULE_ROOT = DATA_ROOT / "module"
DATABASE_MODULE = DATA_ROOT / "script" / "database" / "module"
SERVICE_RE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*\Z")
KINDS = {"roadmap": ("roadmap", "roadmap.yml"),
         "reference": ("reference", "references.yml"),
         "overview": ("base", "base.md")}


def shared(kind: str):
    target = DATABASE_MODULE / kind / f"_{kind}_sync.py"
    module_name = f"step2_new_shared_{kind}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    sys.path.insert(0, str(DATABASE_MODULE))
    sys.path.insert(0, str(target.parent))
    spec = importlib.util.spec_from_file_location(module_name, target)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Missing database helper for {kind}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class LocalEntry:
    node_key: str
    module: Path
    file: Path
    file_path: str
    language_code: str
    content: Any

    @property
    def markdown(self) -> str | None:
        return self.content if isinstance(self.content, str) else None


def _metadata(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Unsafe/missing metadata: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"Invalid metadata JSON: {path}") from exc
    if type(data) is not dict:
        raise ValueError(f"Metadata must be a JSON object: {path}")
    return data


def _value(data: dict, field: str):
    node = data.get(field)
    return node.get("VALUE") if type(node) is dict else None


def _activated(module: Path) -> bool:
    value = _metadata(module / "module_activate.json")
    return value.get("isModule") is True


def _file_below_module(path: Path, module: Path) -> Path:
    if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != module):
        raise ValueError(f"Symlinked source not allowed: {path}")
    if not path.is_file() or not path.resolve().is_relative_to(module.resolve()):
        raise ValueError(f"Required source file missing/unsafe: {path}")
    return path


def scan_sources(kind: str, module_root: Path, selected: frozenset[str]) -> tuple[list[LocalEntry], list[str]]:
    """Validate only selected SERVICE_NAMEs; never inspect unrelated content."""
    if kind not in KINDS:
        raise ValueError(f"Unknown importer: {kind}")
    if not module_root.is_dir() or module_root.is_symlink():
        raise ValueError(f"Missing/unsafe module root: {module_root}")
    sources: list[LocalEntry] = []
    errors: list[str] = []
    found: set[str] = set()
    source_dir, filename = KINDS[kind]
    parser = shared(kind)
    # os.walk avoids recursively visiting content/knowledge, large build dirs,
    # and inactive symlinked directories.
    for folder, dirs, files in os.walk(module_root, followlinks=False):
        dirs[:] = sorted(x for x in dirs if x not in (
            "content", ".git", "build", "temp", ".gradle", "node_modules"
        ) and not (Path(folder) / x).is_symlink())
        if "module-info.json" not in files:
            continue
        module = Path(folder)
        try:
            metadata = _metadata(module / "module-info.json")
        except ValueError:
            # Unselected malformed modules must not block an explicit import.
            # If this was a requested module it will be reported as missing.
            continue
        try:
            name = _value(metadata, "SERVICE_NAME")
            if type(name) is not str or not SERVICE_RE.fullmatch(name):
                # An unrelated invalid module should not block a scoped import.
                continue
            if name not in selected:
                continue
            if name in found:
                errors.append(f"Duplicate SERVICE_NAME in module catalog: {name}")
                continue
            found.add(name)
            if not _activated(module):
                raise ValueError(f"{name}: module is not activated")
            languages = _value(metadata, "MODULE_LANGUAGE")
            if type(languages) is not list or "vi" not in languages:
                raise ValueError(f"{name}: vi is not enabled in MODULE_LANGUAGE")
            path = _file_below_module(module / "content" / source_dir / "vi" / filename, module)
            if kind == "roadmap":
                content = parser.read_roadmap(path)
                if len(content) >= 10:
                    raise ValueError(f"{name}: roadmap must have fewer than 10 milestones")
            elif kind == "reference":
                content = parser.read_references(path)
            else:
                content = parser.read_overview(path)
            if not content:
                raise ValueError(f"{name}: empty {'Base' if kind == 'overview' else kind} source")
            sources.append(LocalEntry(name, module, path, path.relative_to(module_root).as_posix(), "vi", content))
        except (ValueError, OSError) as exc:
            errors.append(f"{name}: {exc}" if isinstance(name, str) else str(exc))
    for name in sorted(selected - found):
        errors.append(f"Selected module not found: {name}")
    return sorted(sources, key=lambda e: e.node_key), errors


def scan_overviews(module_root: Path, *, module_filter: frozenset[str]):
    sources, errors = scan_sources("overview", module_root, module_filter)
    return sources, [], errors


def _write_report(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, staging = tempfile.mkstemp(prefix=".step2-report-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(document, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staging, path)
    finally:
        if os.path.exists(staging):
            os.unlink(staging)


def _db_plan(kind: str, parser, sources: list[LocalEntry], conn, prefix: str):
    snapshot = parser.read_snapshot(conn, prefix)
    modules = snapshot[0] if kind == "overview" else snapshot.modules
    languages = snapshot[1] if kind == "overview" else snapshot.languages
    if "vi" not in languages:
        raise ValueError("Language vi is missing from Oracle LANGUAGE")
    plans = []
    for item in sources:
        module_id = modules.get(item.node_key)
        if module_id is None:
            raise ValueError(f"{item.node_key}: MODULE not found in Oracle")
        if kind == "overview":
            from _module_source_sync import ModuleSource
            source = ModuleSource(item.module, item.node_key, item.file)
            action = parser.plan_module(source, item.content, "vi", module_id, snapshot[2])
            changes = int(action != "unchanged")
            details = {action.upper(): 1}
        else:
            source = parser.ModuleSource(item.module, item.node_key, item.file)
            diff = parser.plan_module(source, item.content, "vi", snapshot)
            changes = sum(v for k, v in diff.items()
                          if k.endswith("_insert") or k.endswith("_update"))
            details = dict(diff)
        plans.append((item, module_id, source, changes, details))
    return plans


def _db_apply(kind: str, parser, driver, connection, prefix: str, plan):
    item, module_id, source, _, _ = plan
    if kind == "roadmap":
        parser.merge_module(connection, prefix, source, item.content, "vi", module_id)
    elif kind == "reference":
        parser.merge_module(connection, prefix, module_id, item.content, "vi")
    else:
        parser.merge_module(driver, connection, prefix, module_id, item.content, "vi")


def main(kind: str, argv: list[str] | None = None) -> int:
    if kind not in KINDS:
        raise ValueError(f"Unknown importer: {kind}")
    cli = argparse.ArgumentParser(description=f"STEP 2 NEW: import selected {kind} into Oracle")
    cli.add_argument("--module", action="append", required=True,
                     help="Exact SERVICE_NAME; repeat up to ten times")
    cli.add_argument("--lang", default="vi", choices=["vi"])
    mode = cli.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="Only validate source; no Oracle connection")
    mode.add_argument("--dry-run", action="store_true", help="Oracle SELECT preview (default)")
    mode.add_argument("--apply", action="store_true", help="Oracle MERGE; never DELETE")
    cli.add_argument("--report", type=Path, default=DATA_ROOT / "build" / "reports" / f"step2-vi-{kind}s.json")
    args = cli.parse_args(argv)
    if len(args.module) > 10 or len(set(args.module)) != len(args.module):
        cli.error("--module must be unique and repeated at most 10 times")
    for name in args.module:
        if not SERVICE_RE.fullmatch(name):
            cli.error(f"Invalid SERVICE_NAME: {name!r}")
    output = args.report if args.report.is_absolute() else DATA_ROOT / args.report
    document: dict = {"entity": kind, "language": "vi",
                      "mode": "APPLY" if args.apply else "OFFLINE" if args.offline else "DRY_RUN",
                      "items": [], "counts": {}, "errors": []}
    connection = None
    try:
        sources, errors = scan_sources(kind, DATA_ROOT / "module", frozenset(args.module))
        document["errors"].extend(errors)
        if errors or len(sources) != len(args.module):
            return 1
        if args.offline:
            document["items"] = [{"nodeKey": x.node_key, "filePath": x.file_path,
                                   "action": "READY_LOCAL_ONLY"} for x in sources]
        else:
            parser = shared(kind)
            # All local files validated before the very first Oracle operation.
            from _module_source_sync import connect_oracle
            driver, connection, prefix = connect_oracle()
            plans = _db_plan(kind, parser, sources, connection, prefix)
            # All selected modules must pass DB planning before any MERGE.
            for item, _, _, changes, details in plans:
                document["items"].append({
                    "nodeKey": item.node_key, "filePath": item.file_path,
                    "action": "CHANGED" if changes else "UNCHANGED", "details": details,
                })
            if args.apply:
                for plan in plans:
                    if plan[3]:
                        try:
                            _db_apply(kind, parser, driver, connection, prefix, plan)
                        except Exception:
                            connection.rollback()
                            raise
                        document["items"][len(document["items"]) - len(plans) + plans.index(plan)]["action"] = "APPLIED"
        document["counts"] = dict(Counter(row["action"] for row in document["items"]))
        return 0
    except Exception as exc:
        # Do not log database DSNs/passwords or raw SQL binds.
        message = str(exc) if isinstance(exc, (ValueError, OSError)) else type(exc).__name__
        if "ORA-" in message:
            import re as _re
            match = _re.search(r"ORA-\d{5}", message)
            message = match.group(0) if match else type(exc).__name__
        document["errors"].append(message)
        return 1
    finally:
        if connection is not None:
            if not args.apply or document["errors"]:
                connection.rollback()
            connection.close()
        document["counts"] = dict(Counter(row["action"] for row in document["items"]))
        _write_report(output, document)
        print(f"STEP2_{kind.upper()} {document['mode']} count={len(document['items'])} "
              f"errors={len(document['errors'])} report={output}")
        for error in document["errors"]:
            print(f"BLOCKER: {error}", file=sys.stderr)
