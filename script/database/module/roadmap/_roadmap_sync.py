#!/usr/bin/env python3
"""Shared implementation for one-way Roadmap YAML -> Oracle synchronization.

Only MODULE rows already present in Oracle are eligible. No SQL DELETE is used.
Default mode is read-only. --apply runs two MERGE statements per milestone.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import importlib.util
import json
import os
from pathlib import Path, PureWindowsPath
import re
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
MODULE_ROOT = REPO_ROOT / "module"
CONNECT_FILE = REPO_ROOT / "script" / "database" / "connect-oracle-db.py"
SERVICE_NAME_RE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*\Z")
LANGUAGE_RE = re.compile(r"[a-z][a-z0-9-]{0,9}\Z")
ROADMAP_KEY_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
PRUNED_DIRS = frozenset({
    ".git", ".gradle", ".idea", ".venv", "__pycache__", "backup",
    "build", "content", "docs", "node_modules", "out", "target",
})
VARCHAR_LIMITS = {"ROADMAP_KEY": 150, "TITLE": 300, "PURPOSE": 1000, "OBJECTIVE": 2000}


class SyncError(ValueError):
    """A source or schema problem: do not modify this module."""


@dataclass(frozen=True)
class Milestone:
    key: str
    sort_order: int
    title: str
    purpose: str
    objective: str | None


@dataclass(frozen=True)
class ModuleSource:
    path: Path
    service_name: str
    roadmap_path: Path


@dataclass(frozen=True)
class RoadmapRow:
    id: int
    sort_order: int


@dataclass
class Snapshot:
    modules: dict[str, int]
    roadmaps: dict[tuple[int, str], RoadmapRow]
    translations: dict[tuple[int, str], tuple[str, str, str | None]]
    languages_by_roadmap: dict[int, set[str]]
    languages: set[str]


MERGE_ROADMAP_SQL = """
MERGE INTO {prefix}MODULE_ROADMAP dst
USING (
    SELECT :module_id MODULE_ID, :roadmap_key ROADMAP_KEY,
           :sort_order SORT_ORDER FROM DUAL
) src
ON (dst.MODULE_ID = src.MODULE_ID AND dst.ROADMAP_KEY = src.ROADMAP_KEY)
WHEN MATCHED THEN UPDATE SET dst.SORT_ORDER = src.SORT_ORDER
    WHERE dst.SORT_ORDER <> src.SORT_ORDER
WHEN NOT MATCHED THEN INSERT (MODULE_ID, ROADMAP_KEY, SORT_ORDER)
    VALUES (src.MODULE_ID, src.ROADMAP_KEY, src.SORT_ORDER)
"""

MERGE_LANGUAGE_SQL = """
MERGE INTO {prefix}MODULE_ROADMAP_LANGUAGE dst
USING (
    SELECT roadmap.ID ROADMAP_ID, :language_code LANGUAGE_CODE,
           :title TITLE, :purpose PURPOSE, :objective OBJECTIVE
    FROM {prefix}MODULE_ROADMAP roadmap
    WHERE roadmap.MODULE_ID = :module_id
      AND roadmap.ROADMAP_KEY = :roadmap_key
) src
ON (dst.ROADMAP_ID = src.ROADMAP_ID AND dst.LANGUAGE_CODE = src.LANGUAGE_CODE)
WHEN MATCHED THEN UPDATE SET
    dst.TITLE = src.TITLE,
    dst.PURPOSE = src.PURPOSE,
    dst.OBJECTIVE = src.OBJECTIVE
    WHERE DECODE(dst.TITLE, src.TITLE, 0, 1) = 1
       OR DECODE(dst.PURPOSE, src.PURPOSE, 0, 1) = 1
       OR DECODE(dst.OBJECTIVE, src.OBJECTIVE, 0, 1) = 1
WHEN NOT MATCHED THEN INSERT (
    ROADMAP_ID, LANGUAGE_CODE, TITLE, PURPOSE, OBJECTIVE
) VALUES (
    src.ROADMAP_ID, src.LANGUAGE_CODE, src.TITLE, src.PURPOSE, src.OBJECTIVE
)
"""


def load_connector() -> Any:
    if not CONNECT_FILE.is_file():
        raise SyncError(f"Shared Oracle connector not found: {CONNECT_FILE}")
    spec = importlib.util.spec_from_file_location("roadmap_oracle_connector", CONNECT_FILE)
    if spec is None or spec.loader is None:
        raise SyncError("Cannot load shared Oracle connector")
    connector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(connector)
    return connector


def validate_text(value: Any, field: str, path: Path, index: int) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise SyncError(f"{path}: roadmap[{index}].{field} must be nonempty text")
    result = value.strip()
    max_chars = VARCHAR_LIMITS[field]
    if len(result) > max_chars or len(result.encode("utf-8")) > 4000:
        raise SyncError(f"{path}: roadmap[{index}].{field} exceeds Oracle column limit")
    return result


def read_roadmap(path: Path) -> tuple[Milestone, ...]:
    try:
        import yaml
    except ImportError as exc:
        raise SyncError("PyYAML is required: python -m pip install pyyaml") from exc
    try:
        content = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise SyncError(f"Unable to read roadmap YAML: {path}: {type(exc).__name__}") from exc
    if not isinstance(content, dict) or not isinstance(content.get("roadmap"), list):
        raise SyncError(f"{path}: expected 'roadmap' as a list")
    result: list[Milestone] = []
    seen: set[str] = set()
    for i, entry in enumerate(content["roadmap"], 1):
        if not isinstance(entry, dict):
            raise SyncError(f"{path}: roadmap[{i}] must be a YAML mapping")
        key = validate_text(entry.get("id"), "ROADMAP_KEY", path, i)
        if not ROADMAP_KEY_RE.fullmatch(key):
            raise SyncError(f"{path}: invalid roadmap key {key!r}")
        if key in seen:
            raise SyncError(f"{path}: duplicate roadmap key {key!r}")
        seen.add(key)
        title = validate_text(entry.get("title"), "TITLE", path, i)
        purpose = validate_text(entry.get("purpose"), "PURPOSE", path, i)
        objectives = entry.get("objectives", [])
        if objectives is None:
            objectives = []
        if not isinstance(objectives, list):
            raise SyncError(f"{path}: roadmap[{i}].objectives must be a list")
        lines: list[str] = []
        for j, value in enumerate(objectives, 1):
            if not isinstance(value, str) or not value.strip() or "\x00" in value:
                raise SyncError(f"{path}: roadmap[{i}].objectives[{j}] is invalid")
            line = value.strip()
            if "\r" in line or "\n" in line:
                raise SyncError(f"{path}: roadmap[{i}].objectives[{j}] must be one line")
            lines.append(line)
        objective = "\n".join(lines) or None
        if objective is not None:
            validate_text(objective, "OBJECTIVE", path, i)
        result.append(Milestone(key, i, title, purpose, objective))
    return tuple(result)


def read_service_name(module_path: Path) -> str:
    path = module_path / "module-info.json"
    try:
        info = json.loads(path.read_text(encoding="utf-8-sig"))
        name = info["SERVICE_NAME"]["VALUE"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SyncError(f"Invalid module-info.json: {path}: {type(exc).__name__}") from exc
    if not isinstance(name, str) or not SERVICE_NAME_RE.fullmatch(name):
        raise SyncError(f"Invalid SERVICE_NAME.VALUE: {path}")
    return name


def discover_all(lang: str) -> tuple[list[ModuleSource], int, list[str]]:
    sources: list[ModuleSource] = []
    errors: list[str] = []
    missing_file_count = 0
    seen_names: dict[str, Path] = {}
    for current, dirs, files in os.walk(MODULE_ROOT):
        dirs[:] = sorted(d for d in dirs if d not in PRUNED_DIRS)
        if "module-info.json" not in files:
            continue
        folder = Path(current)
        roadmap_path = folder / "content" / "roadmap" / lang / "roadmap.yml"
        if not roadmap_path.is_file():
            missing_file_count += 1
            continue
        try:
            name = read_service_name(folder)
        except SyncError as exc:
            errors.append(str(exc))
            continue
        if name in seen_names:
            errors.append(f"Duplicate SERVICE_NAME {name}: {folder} and {seen_names[name]}")
            continue
        seen_names[name] = folder
        sources.append(ModuleSource(folder, name, roadmap_path))
    return sorted(sources, key=lambda s: s.service_name), missing_file_count, errors


def discover_single(module_arg: str, lang: str) -> tuple[list[ModuleSource], int, list[str]]:
    normalized = module_arg.replace("\\", "/")
    relative = Path(normalized)
    if (relative.is_absolute() or PureWindowsPath(module_arg).is_absolute()
            or ".." in relative.parts or not relative.parts or relative.parts[0] != "module"):
        raise SyncError("--module must be a relative path beginning with module/ (no '..')")
    target = (MODULE_ROOT / Path(*relative.parts[1:])).resolve()
    if not target.is_relative_to(MODULE_ROOT.resolve()) or not target.is_dir():
        raise SyncError(f"Module path not found under repository/module: {module_arg}")
    name = read_service_name(target)
    roadmap_path = target / "content" / "roadmap" / lang / "roadmap.yml"
    if not roadmap_path.is_file():
        return [], 1, []
    return [ModuleSource(target, name, roadmap_path)], 0, []


def safe_oracle_error(exc: Exception) -> str:
    message = str(exc)
    match = re.search(r"ORA-\d{5}", message)
    return match.group(0) if match else type(exc).__name__


def read_snapshot(connection: Any, prefix: str) -> Snapshot:
    with connection.cursor() as cur:
        cur.execute(f"SELECT ID, SERVICE_NAME FROM {prefix}MODULE")
        modules = {name: int(module_id) for module_id, name in cur.fetchall()}
        cur.execute(f"SELECT ID, MODULE_ID, ROADMAP_KEY, SORT_ORDER FROM {prefix}MODULE_ROADMAP")
        roadmaps = {
            (int(module_id), key): RoadmapRow(int(roadmap_id), int(sort_order))
            for roadmap_id, module_id, key, sort_order in cur.fetchall()
        }
        cur.execute(
            f"SELECT ROADMAP_ID, LANGUAGE_CODE, TITLE, PURPOSE, OBJECTIVE "
            f"FROM {prefix}MODULE_ROADMAP_LANGUAGE"
        )
        translations: dict[tuple[int, str], tuple[str, str, str | None]] = {}
        languages_by_roadmap: dict[int, set[str]] = defaultdict(set)
        for roadmap_id, lang, title, purpose, objective in cur:
            translations[(int(roadmap_id), lang)] = (title, purpose, objective)
            languages_by_roadmap[int(roadmap_id)].add(lang)
        cur.execute(f"SELECT CODE FROM {prefix}LANGUAGE")
        languages = {row[0] for row in cur.fetchall()}
    return Snapshot(modules, roadmaps, translations, dict(languages_by_roadmap), languages)


def plan_module(
    source: ModuleSource,
    milestones: tuple[Milestone, ...],
    lang: str,
    snapshot: Snapshot,
) -> Counter[str]:
    module_id = snapshot.modules[source.service_name]
    counters: Counter[str] = Counter()
    for entry in milestones:
        existing = snapshot.roadmaps.get((module_id, entry.key))
        if existing is None:
            counters["roadmap_insert"] += 1
            counters["translation_insert"] += 1
            continue
        if existing.sort_order != entry.sort_order:
            other_languages = snapshot.languages_by_roadmap.get(existing.id, set()) - {lang}
            if other_languages:
                raise SyncError(
                    f"{source.roadmap_path}: sort order for {entry.key!r} differs from DB "
                    f"and other translations exist ({', '.join(sorted(other_languages))})"
                )
            counters["roadmap_update"] += 1
        else:
            counters["roadmap_unchanged"] += 1
        original = snapshot.translations.get((existing.id, lang))
        incoming = (entry.title, entry.purpose, entry.objective)
        if original is None:
            counters["translation_insert"] += 1
        elif original != incoming:
            counters["translation_update"] += 1
        else:
            counters["translation_unchanged"] += 1
    counters["milestones"] += len(milestones)
    return counters


def merge_module(
    connection: Any, prefix: str, source: ModuleSource,
    milestones: tuple[Milestone, ...], lang: str, module_id: int,
) -> None:
    # One transaction per MODULE. A failure rolls back both tables for this module.
    with connection.cursor() as cur:
        for item in milestones:
            cur.execute(
                MERGE_ROADMAP_SQL.format(prefix=prefix),
                module_id=module_id, roadmap_key=item.key, sort_order=item.sort_order,
            )
            cur.execute(
                MERGE_LANGUAGE_SQL.format(prefix=prefix),
                module_id=module_id, roadmap_key=item.key, language_code=lang,
                title=item.title, purpose=item.purpose, objective=item.objective,
            )
    connection.commit()


def run(*, single: bool, args: argparse.Namespace) -> int:
    if not LANGUAGE_RE.fullmatch(args.lang):
        raise SyncError("--lang must be a language code such as vi or en")
    if single:
        sources, missing_files, source_errors = discover_single(args.module, args.lang)
    else:
        sources, missing_files, source_errors = discover_all(args.lang)

    connector = load_connector()
    connector.load_env_file(connector.DEFAULT_ENV_FILE)
    config = connector.config_from_env()
    schema = config["schema"] or config["user"].upper()
    prefix = f"{schema}."
    _, connection = connector.connect(config)
    try:
        snapshot = read_snapshot(connection, prefix)
        if args.lang not in snapshot.languages:
            raise SyncError(f"Language {args.lang!r} does not exist in Oracle LANGUAGE")
        matched: list[tuple[ModuleSource, tuple[Milestone, ...], Counter[str]]] = []
        skipped_unmatched: list[str] = []
        errors = list(source_errors)
        for source in sources:
            if source.service_name not in snapshot.modules:
                skipped_unmatched.append(source.service_name)
                continue
            try:
                milestones = read_roadmap(source.roadmap_path)
                if not milestones:
                    # Empty list is not an instruction to delete existing rows.
                    missing_files += 1
                    continue
                counts = plan_module(source, milestones, args.lang, snapshot)
                matched.append((source, milestones, counts))
            except SyncError as exc:
                errors.append(str(exc))

        counts: Counter[str] = Counter()
        committed = 0
        failures: list[str] = []
        for source, milestones, change_counts in matched:
            if args.apply:
                try:
                    merge_module(
                        connection, prefix, source, milestones, args.lang,
                        snapshot.modules[source.service_name],
                    )
                    committed += 1
                except Exception as exc:
                    connection.rollback()
                    failures.append(f"{source.service_name}: {safe_oracle_error(exc)}")
                    continue
            counts.update(change_counts)

        print(f"MODE={'APPLY' if args.apply else 'DRY_RUN'} LANG={args.lang}")
        print(
            f"MODULES sources={len(sources)} matched={len(matched)} "
            f"skipped_not_in_db={len(skipped_unmatched)} "
            f"skipped_no_roadmap={missing_files} "
            f"committed={committed} failed={len(errors) + len(failures)}"
        )
        print(
            f"ROADMAP milestones={counts['milestones']} "
            f"insert={counts['roadmap_insert']} update={counts['roadmap_update']} "
            f"unchanged={counts['roadmap_unchanged']}"
        )
        print(
            f"LANGUAGE insert={counts['translation_insert']} "
            f"update={counts['translation_update']} unchanged={counts['translation_unchanged']}"
        )
        print("POLICY only MERGE INSERT/UPDATE; never DELETE or create MODULE")
        for warning in source_errors[:10]:
            print(f"SOURCE_WARNING: {warning}", file=sys.stderr)
        for name in skipped_unmatched[:10]:
            print(f"SKIP_NOT_IN_DB: {name}")
        for error in errors[:15]:
            print(f"ERROR: {error}", file=sys.stderr)
        for failure in failures[:15]:
            print(f"DB_ERROR: {failure}", file=sys.stderr)
        return 1 if errors or failures else 0
    finally:
        connection.close()


def build_parser(*, single: bool) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync Roadmap YAML to existing Oracle MODULEs using MERGE INTO; never DELETE."
    )
    if single:
        parser.add_argument(
            "--module", required=True,
            help="Module directory relative to java-learning, e.g. module/infrastructure/cloud/architecture",
        )
    parser.add_argument("--lang", default="vi", help="Roadmap language (default: vi)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview using Oracle SELECT only (default)")
    mode.add_argument("--apply", action="store_true", help="MERGE into Oracle, committing each module")
    return parser


def entrypoint(*, single: bool) -> int:
    args = build_parser(single=single).parse_args()
    try:
        return run(single=single, args=args)
    except (SyncError, OSError, ValueError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        # Avoid exposing Oracle connection strings/passwords via raw driver errors.
        print(f"BLOCKED: {safe_oracle_error(exc)}", file=sys.stderr)
        return 1
