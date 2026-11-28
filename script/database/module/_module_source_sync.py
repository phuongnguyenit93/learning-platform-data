#!/usr/bin/env python3
"""Shared read-only source/module lookup helpers for database sync scripts.

Never creates or changes MODULE rows. Database writes are owned by each
importer and are enabled only by its explicit --apply switch.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
import os
from pathlib import Path, PureWindowsPath
import re
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_ROOT = REPO_ROOT / "module"
CONNECT_FILE = REPO_ROOT / "script" / "database" / "connect-oracle-db.py"
LANGUAGE_RE = re.compile(r"[a-z][a-z0-9-]{0,9}\Z")
SERVICE_NAME_RE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*\Z")
PRUNED_DIRS = frozenset({
    ".git", ".gradle", ".idea", ".venv", ".worktrees", "__pycache__",
    "backup", "build", "content", "docs", "node_modules", "out", "target",
})


class SyncError(ValueError):
    """Invalid local source, database mapping or sync precondition."""


@dataclass(frozen=True)
class ModuleSource:
    path: Path
    service_name: str
    data_path: Path


def load_connector() -> Any:
    if not CONNECT_FILE.is_file():
        raise SyncError(f"Shared Oracle connector missing: {CONNECT_FILE}")
    spec = importlib.util.spec_from_file_location("module_source_db_connection", CONNECT_FILE)
    if spec is None or spec.loader is None:
        raise SyncError("Cannot load Oracle connector")
    connector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(connector)
    return connector


def connect_oracle():
    connector = load_connector()
    connector.load_env_file(connector.DEFAULT_ENV_FILE)
    config = connector.config_from_env()
    schema = config["schema"] or config["user"].upper()
    driver, connection = connector.connect(config)
    return driver, connection, f"{schema}."


def read_service_name(module: Path) -> str:
    path = module / "module-info.json"
    try:
        info = json.loads(path.read_text(encoding="utf-8-sig"))
        value = info["SERVICE_NAME"]["VALUE"]
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        raise SyncError(f"Invalid module-info.json: {path} ({type(exc).__name__})") from exc
    if not isinstance(value, str) or not SERVICE_NAME_RE.fullmatch(value):
        raise SyncError(f"Invalid SERVICE_NAME.VALUE: {path}")
    return value


def _target_module(module_arg: str) -> Path:
    normalized = module_arg.replace("\\", "/")
    relative = Path(normalized)
    if (not normalized or relative.is_absolute() or PureWindowsPath(module_arg).is_absolute()
            or ".." in relative.parts or not relative.parts
            or relative.parts[0] != "module"):
        raise SyncError("--module must be relative to the data repository and start with module/")
    target = (MODULE_ROOT / Path(*relative.parts[1:])).resolve()
    if not target.is_relative_to(MODULE_ROOT.resolve()) or not target.is_dir():
        raise SyncError(f"Invalid module directory: {module_arg}")
    return target


def discover_sources(
    lang: str,
    *,
    data_dir: str,
    filename: str,
    module_arg: str | None = None,
) -> tuple[list[ModuleSource], int, list[str]]:
    """Discover modules with the requested file, skipping missing translations.

    The single-module form validates the actual directory, not a SERVICE_NAME
    supplied by a caller. Duplicate SERVICE_NAME values are always an error.
    """
    if not LANGUAGE_RE.fullmatch(lang):
        raise SyncError("--lang must be a language code such as vi or en")
    if module_arg is not None:
        module = _target_module(module_arg)
        service_name = read_service_name(module)
        path = module / "content" / data_dir / lang / filename
        if not path.is_file():
            return [], 1, []
        if path.is_symlink():
            raise SyncError(f"Symlink source not allowed: {path}")
        return [ModuleSource(module, service_name, path)], 0, []

    sources: list[ModuleSource] = []
    missing = 0
    errors: list[str] = []
    seen: dict[str, Path] = {}
    for current, dirs, files in os.walk(MODULE_ROOT):
        dirs[:] = sorted(d for d in dirs if d not in PRUNED_DIRS)
        if "module-info.json" not in files:
            continue
        module = Path(current)
        path = module / "content" / data_dir / lang / filename
        if not path.is_file():
            missing += 1
            continue
        if path.is_symlink():
            errors.append(f"Symlink source not allowed: {path}")
            continue
        try:
            service_name = read_service_name(module)
        except SyncError as exc:
            errors.append(str(exc))
            continue
        if service_name in seen:
            errors.append(
                f"Duplicate SERVICE_NAME {service_name}: {seen[service_name]} and {module}"
            )
            # Neither duplicate should be eligible for import.
            sources = [item for item in sources if item.service_name != service_name]
            continue
        seen[service_name] = module
        sources.append(ModuleSource(module, service_name, path))
    return sorted(sources, key=lambda item: item.service_name), missing, errors


def read_module_language_index(connection: Any, prefix: str):
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT ID, SERVICE_NAME FROM {prefix}MODULE")
        modules = {name: int(module_id) for module_id, name in cursor.fetchall()}
        cursor.execute(f"SELECT CODE FROM {prefix}LANGUAGE")
        languages = {code for (code,) in cursor.fetchall()}
    return modules, languages


def validate_text(value: Any, *, limit: int, context: str, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or "\x00" in value:
        raise SyncError(f"{context}: expected text")
    result = value.strip()
    if not result:
        if required:
            raise SyncError(f"{context}: must not be blank")
        return None
    if len(result) > limit or len(result.encode("utf-8")) > 4000:
        raise SyncError(f"{context}: exceeds Oracle VARCHAR2 limit ({limit} chars)")
    return result


def safe_oracle_error(exc: Exception) -> str:
    # Do not log database connection strings or SQL bind values.
    match = re.search(r"ORA-\d{5}", str(exc))
    return match.group(0) if match else type(exc).__name__


def print_problems(*, errors: list[str], unmatched: list[str], entity: str) -> None:
    import sys
    for service_name in unmatched[:15]:
        print(f"SKIP_NOT_IN_DB: {service_name}")
    for error in errors[:20]:
        print(f"{entity}_ERROR: {error}", file=sys.stderr)
