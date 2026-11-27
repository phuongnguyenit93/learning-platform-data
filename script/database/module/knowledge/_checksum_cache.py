"""Machine-local, authenticated checkpoints for Oracle Menu/Knowledge imports.

The source digest hashes file contents and the full selected-locale file/directory
inventory. A DB witness hashes scalar rows/identifiers/ORA_ROWSCN/LOB lengths,
without transferring CLOB content. Missing or unsafe checkpoints are cache misses.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile
from typing import Any, Callable


CACHE_VERSION = 1
# Increment whenever source import meaning, readiness or DB mapping changes.
CONTRACT_REVISION = "knowledge-menu-sql17-20-default-basic-v3"
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_HOME_CACHE = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".cache"))
CACHE_ROOT = _HOME_CACHE / "java-learning" / "oracle-menu-knowledge"


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _hash_records(records: list[tuple]) -> str:
    sha = hashlib.sha256()
    for record in records:
        item = _json_bytes(record)
        sha.update(len(item).to_bytes(8, "big"))
        sha.update(item)
    return sha.hexdigest()


def source_digest(module: Path, locales: tuple[str, ...],
                  io_path: Callable[[Path], Path]) -> str:
    """Hash source bytes/inventory without parsing the large YAML or Markdown.

    Also inventory all locale directory names, including locales omitted by a
    CLI language subset, to detect added/deleted languages on subsequent runs.
    """
    parts: list[tuple] = [("contract", CONTRACT_REVISION),
                          ("selected-locales", tuple(locales))]

    def inspect(path: Path) -> tuple[bool, bool]:
        p = io_path(path)
        if p.is_symlink():
            raise ValueError("Source symlink detected: " + str(path))
        return p.is_file(), p.is_dir()

    def file_record(file: Path) -> None:
        is_file, _ = inspect(file)
        if not is_file:
            raise ValueError("Source file missing: " + str(file))
        digest = hashlib.sha256()
        with io_path(file).open("rb") as stream:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        parts.append(("file", file.relative_to(module).as_posix(), digest.hexdigest()))

    for name in ("module_activate.json", "module-info.json"):
        file_record(module / name)

    knowledge = module / "content" / "knowledge"
    is_file, is_directory = inspect(knowledge)
    if is_file or not is_directory:
        raise ValueError("Missing Knowledge directory: " + str(knowledge))
    all_locales = []
    for child in io_path(knowledge).iterdir():
        child_path = knowledge / child.name  # keep normal paths for relative_to
        child_file, child_directory = inspect(child_path)
        if child_directory:
            all_locales.append(child.name)
        elif child_file:
            # Any new root-level file invalidates an earlier checkpoint.
            all_locales.append("file:" + child.name)
        else:
            raise ValueError("Unexpected Knowledge entry: " + str(child_path))
    parts.append(("locale-inventory", tuple(sorted(all_locales))))

    for lang in sorted(locales):
        base = knowledge / lang
        _, is_directory = inspect(base)
        if not is_directory:
            raise ValueError("Selected language directory missing: " + str(base))
        stack = [base]
        while stack:
            folder = stack.pop()
            parts.append(("dir", folder.relative_to(module).as_posix()))
            subdirs = []
            for entry in sorted(io_path(folder).iterdir(), key=lambda item: item.name):
                candidate = folder / entry.name
                is_file, is_directory = inspect(candidate)
                if is_directory:
                    subdirs.append(candidate)
                elif is_file:
                    if candidate.suffix.lower() in (".md", ".yml", ".yaml"):
                        file_record(candidate)
                    else:
                        # Inventory non-Knowledge formats, without hashing assets.
                        parts.append(("other", candidate.relative_to(module).as_posix()))
                else:
                    raise ValueError("Unsupported Knowledge entry: " + str(candidate))
            stack.extend(reversed(subdirs))
    return _hash_records(parts)


def db_witness(connection: Any, prefix: str, module_id: int) -> str:
    """Cheap DB evidence; no CLOB content is fetched into Python.

    This checks *all* current translations, including unselected locales.
    ORA_ROWSCN is intentionally conservative/block-scoped by default; direct
    in-place LOB edits with unchanged size may require --force.
    """
    statements = (
        f"""
        SELECT m.ID, m.NODE_TYPE, m.MODULE_ID, m.MENU_PARENT_ID,
               m.MENU_PARENT_TYPE, m.SLUG, m.SORT_ORDER, m.IS_ACTIVE, m.ORA_ROWSCN
        FROM {prefix}MODULE_MENU m
        WHERE m.MODULE_ID = :module_id OR m.MENU_PARENT_ID IN
              (SELECT c.ID FROM {prefix}MODULE_MENU c
               WHERE c.NODE_TYPE = 'CHAPTER' AND c.MODULE_ID = :module_id)
        """,
        f"""
        SELECT t.MENU_ID, t.LANGUAGE_CODE, t.TITLE, t.DESCRIPTION, t.ORA_ROWSCN
        FROM {prefix}MODULE_MENU_LANGUAGE t
        JOIN {prefix}MODULE_MENU m ON m.ID = t.MENU_ID
        LEFT JOIN {prefix}MODULE_MENU c ON c.ID = m.MENU_PARENT_ID
        WHERE m.MODULE_ID = :module_id OR c.MODULE_ID = :module_id
        """,
        f"""
        SELECT k.ID, k.MENU_ID, k.MENU_NODE_TYPE, k.DIFFICULT,
               k.IS_ACTIVE, k.ORA_ROWSCN
        FROM {prefix}MODULE_KNOWLEDGE k
        JOIN {prefix}MODULE_MENU s ON s.ID = k.MENU_ID
        JOIN {prefix}MODULE_MENU c ON c.ID = s.MENU_PARENT_ID
        WHERE c.MODULE_ID = :module_id
        """,
        f"""
        SELECT t.KNOWLEDGE_ID, t.LANGUAGE_CODE, t.STATUS,
               t.FOCUS, t.PROBLEM_SOLVED, t.MECHANISM, t.APPLICATION_VALUE,
               DBMS_LOB.GETLENGTH(t.CONTENT), DBMS_LOB.GETLENGTH(t.SUMMARY),
               t.ORA_ROWSCN
        FROM {prefix}MODULE_KNOWLEDGE_LANGUAGE t
        JOIN {prefix}MODULE_KNOWLEDGE k ON k.ID = t.KNOWLEDGE_ID
        JOIN {prefix}MODULE_MENU s ON s.ID = k.MENU_ID
        JOIN {prefix}MODULE_MENU c ON c.ID = s.MENU_PARENT_ID
        WHERE c.MODULE_ID = :module_id
        """,
    )
    records: list[tuple] = [("witness-revision", CONTRACT_REVISION),
                             ("module-id", module_id)]
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT ID, SERVICE_NAME, IS_ACTIVE, ORA_ROWSCN "
                       f"FROM {prefix}MODULE WHERE ID = :module_id", module_id=module_id)
        module = cursor.fetchone()
        if module is None:
            raise ValueError("Oracle module disappeared before DB guard")
        records.append(("module", tuple(module)))
        for idx, sql in enumerate(statements):
            cursor.execute(sql, module_id=module_id)
            rows = [tuple(row) for row in cursor.fetchall()]
            records.append(("table", idx, len(rows)))
            records.extend(("row", idx, row) for row in sorted(rows, key=lambda x: _json_bytes(x)))
    return _hash_records(records)


def oracle_identity(connection: Any) -> tuple[str, ...]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT SYS_CONTEXT('USERENV','DB_NAME'), "
                       "SYS_CONTEXT('USERENV','CON_NAME'), "
                       "SYS_CONTEXT('USERENV','SESSION_USER'), "
                       "SYS_CONTEXT('USERENV','CURRENT_SCHEMA') FROM DUAL")
        row = cursor.fetchone()
        if row is None or not row[0]:
            raise ValueError("Could not identify Oracle database")
        return tuple(str(x or "") for x in row)


def _safe_path(path: Path) -> bool:
    """Reject existing symlinks/junctions in the checkpoint parent chain."""
    try:
        for parent in (path, *path.parents):
            if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
                return False
        return True
    except OSError:
        return False


def _signing_key(root: Path, *, create: bool) -> bytes | None:
    key_path = root / ".signing-key"
    if not _safe_path(key_path):
        return None
    if not root.is_dir():
        if not create or root.exists() or not _safe_path(root):
            return None
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not key_path.exists() and create:
        key = secrets.token_bytes(32)
        try:
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
            fd = os.open(key_path, flags, 0o600)
            with os.fdopen(fd, "wb") as writer:
                writer.write(key)
                writer.flush()
                os.fsync(writer.fileno())
        except FileExistsError:
            pass  # another writer just created it
    try:
        if not _safe_path(key_path):
            return None
        mode = key_path.stat().st_mode
        if not stat.S_ISREG(mode) or key_path.stat().st_size != 32:
            return None
        return key_path.read_bytes()
    except (OSError, ValueError):
        return None


def _cache_path(root: Path, module: Path, service: str, languages: tuple[str, ...],
                schema: str, module_id: int) -> Path:
    digest = hashlib.sha256(_json_bytes((str(module.resolve()), service,
                                        tuple(languages), schema, module_id))).hexdigest()
    return root / (digest + ".json")


def _identity(key: bytes, schema: str, remote: tuple[str, ...]) -> str | None:
    # ORACLE_DSN is never written to the checkpoint or logs, only HMAC-ed with
    # a random local signing key. Different DSN/schema/DB/user invalidate hits.
    dsn = os.environ.get("ORACLE_DSN", "")
    if not dsn:
        return None
    message = _json_bytes((CONTRACT_REVISION, schema, remote, dsn))
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _signature(key: bytes, payload: dict) -> str:
    return hmac.new(key, _json_bytes(payload), hashlib.sha256).hexdigest()


def load_checkpoint(module: Path, service: str, languages: tuple[str, ...],
                    schema: str, module_id: int, remote: tuple[str, ...],
                    *, root: Path | None = None) -> dict | None:
    root = CACHE_ROOT if root is None else root
    path = _cache_path(root, module, service, languages, schema, module_id)
    if not _safe_path(path) or not path.is_file() or path.stat().st_size > 4096:
        return None
    key = _signing_key(root, create=False)
    if key is None:
        return None
    identity = _identity(key, schema, remote)
    if identity is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if type(data) is not dict or set(data) != {"payload", "hmac"}:
            return None
        payload = data["payload"]
        if (type(payload) is not dict or set(payload) !=
                {"version", "contract", "identity", "source", "database"}):
            return None
        if (type(payload["version"]) is not int or payload["version"] != CACHE_VERSION
                or payload["contract"] != CONTRACT_REVISION or payload["identity"] != identity
                or any(type(payload[k]) is not str or not _HEX.fullmatch(payload[k])
                       for k in ("source", "database"))
                or type(data["hmac"]) is not str):
            return None
        if not hmac.compare_digest(_signature(key, payload), data["hmac"]):
            return None
        return payload
    except (OSError, ValueError, TypeError):
        return None


def save_checkpoint(module: Path, service: str, languages: tuple[str, ...],
                    schema: str, module_id: int, remote: tuple[str, ...],
                    source: str, database: str, *, root: Path | None = None) -> bool:
    """Atomic post-commit checkpoint. A failure never changes Oracle data."""
    root = CACHE_ROOT if root is None else root
    path = _cache_path(root, module, service, languages, schema, module_id)
    if (not _safe_path(path) or not all(type(x) is str and _HEX.fullmatch(x)
                                       for x in (source, database))):
        return False
    try:
        key = _signing_key(root, create=True)
        if key is None:
            return False
        identity = _identity(key, schema, remote)
        if identity is None:
            return False
        payload = {"version": CACHE_VERSION, "contract": CONTRACT_REVISION,
                   "identity": identity, "source": source, "database": database}
        output = _json_bytes({"payload": payload, "hmac": _signature(key, payload)}) + b"\n"
        fd, temporary = tempfile.mkstemp(prefix=".menu-knowledge-", suffix=".tmp", dir=root)
        try:
            os.chmod(temporary, 0o600)
            with os.fdopen(fd, "wb") as writer:
                writer.write(output)
                writer.flush()
                os.fsync(writer.fileno())
            if not _safe_path(path):
                return False
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return True
    except (OSError, ValueError):
        return False
