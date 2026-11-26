#!/usr/bin/env python3
"""Synchronize STEP 5 NEW Phase 1 queues using raw Markdown presence.

For each active module and each assessment type independently:
  - Nonempty content/temp/step5/raw/<type>.md -> completed.yml
  - Missing/empty/whitespace-only raw file        -> pending.yml

This intentionally does NOT validate Worker status or academic QA. The
completed list only means raw Phase 1 content exists, not that Prime QA passed.
The script updates only six Prime-owned queue files; it never edits modules.

Run without arguments to preview; pass --apply to write the queues.
No third-party YAML dependency is needed: the parser supports exactly the
location/status/reason subset of YAML used by these Prime queues.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile


TYPES = ("quiz", "interview", "casestudy")
COMPLETED_STATUS = "PHASE_1_COMPLETED"
DEFAULT_REPO = Path(__file__).resolve().parents[2]
LOCATION_PATTERN = re.compile(r"^  - location: (.+?)\s*$")
FIELD_PATTERN = re.compile(r"^    (status|reason):\s*(.*?)\s*$")


class SyncError(Exception):
    """The queue or inventory is unsafe to synchronize."""


def read_scalar(value: str) -> str:
    """Decode the small YAML scalar subset written by this script."""
    if value.startswith('"'):
        try:
            result = json.loads(value)
        except json.JSONDecodeError as exc:
            raise SyncError(f"Invalid quoted YAML scalar: {value!r}") from exc
        if not isinstance(result, str):
            raise SyncError("Expected string scalar")
        return result
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    return value


def read_queue(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file() or path.is_symlink():
        raise SyncError(f"Missing or unsafe queue file: {path}")
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    if not lines or lines[0].strip() not in ("modules:", "modules: []"):
        raise SyncError(f"Unsupported queue header: {path}")
    if lines[0].strip() == "modules: []" and any(line.strip() for line in lines[1:]):
        raise SyncError(f"Unexpected content after empty queue: {path}")
    result: dict[str, dict[str, str]] = {}
    location: str | None = None
    for number, line in enumerate(lines[1:], 2):
        if not line.strip():
            continue
        match = LOCATION_PATTERN.fullmatch(line)
        if match:
            location = read_scalar(match.group(1))
            if not location.startswith("module/") or "\\" in location:
                raise SyncError(f"Invalid module location at {path}:{number}")
            parts = Path(location).parts
            if "." in parts or ".." in parts:
                raise SyncError(f"Unsafe module location at {path}:{number}")
            if location in result:
                raise SyncError(f"Duplicate location in {path}: {location}")
            result[location] = {}
            continue
        field = FIELD_PATTERN.fullmatch(line)
        if field and location is not None:
            name, raw = field.groups()
            if name in result[location]:
                raise SyncError(f"Duplicate field at {path}:{number}")
            result[location][name] = read_scalar(raw)
            continue
        raise SyncError(f"Unexpected YAML line at {path}:{number}: {line!r}")
    return result


def write_queue(entries: list[tuple[str, dict[str, str]]], completed: bool) -> str:
    if not entries:
        return "modules: []\n"
    lines = ["modules:"]
    for location, fields in entries:
        # Keep ordinary module paths readable and avoid needless list rewrites.
        scalar = location if re.fullmatch(r"[A-Za-z0-9_./-]+", location) else json.dumps(location, ensure_ascii=False)
        lines.append(f"  - location: {scalar}")
        if completed:
            lines.append(f"    status: {COMPLETED_STATUS}")
            lines.append('    reason: ""')
        else:
            # Preserve an existing blocker/reason only when it is still pending.
            if fields.get("status"):
                lines.append(f'    status: {json.dumps(fields["status"], ensure_ascii=False)}')
            if fields.get("reason"):
                lines.append(f'    reason: {json.dumps(fields["reason"], ensure_ascii=False)}')
    return "\n".join(lines) + "\n"


def inventory(repo: Path) -> list[str]:
    modules = repo / "module"
    if not modules.is_dir():
        raise SyncError(f"Missing module directory: {modules}")
    locations: list[str] = []
    for activation in modules.rglob("module_activate.json"):
        if activation.is_symlink():
            raise SyncError(f"Symlinked activation file: {activation}")
        try:
            enabled = json.loads(activation.read_text(encoding="utf-8-sig"))["isModule"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise SyncError(f"Unreadable module activation: {activation}") from exc
        if enabled is True:
            location = activation.parent.relative_to(repo).as_posix()
            locations.append(location)
    if not locations:
        raise SyncError("No active modules found; refusing to empty the queues")
    return sorted(set(locations))


def has_raw_content(repo: Path, location: str, kind: str) -> bool:
    raw = repo / location / "content" / "temp" / "step5" / "raw" / f"{kind}.md"
    if raw.is_symlink():
        raise SyncError(f"Symlinked raw file: {raw}")
    if not raw.exists():
        return False
    if not raw.is_file():
        raise SyncError(f"Raw output is not a file: {raw}")
    try:
        with raw.open("r", encoding="utf-8-sig") as reader:
            return any(line.strip() for line in reader)
    except (UnicodeError, OSError) as exc:
        raise SyncError(f"Cannot read raw file: {raw}") from exc


def atomic_write(path: Path, data: bytes) -> None:
    """Replace one queue atomically; never leave a truncated YAML file."""
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".sync-phase1-",
                                         suffix=".tmp", delete=False) as stream:
            tmp_name = stream.name
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, path)
    finally:
        if tmp_name is not None and os.path.exists(tmp_name):
            os.unlink(tmp_name)


def sync(repo: Path, apply: bool) -> None:
    repo = repo.resolve()
    all_modules = inventory(repo)
    all_set = set(all_modules)
    queue_root = repo / "module-generate-agent" / "temp" / "step5" / "phase1"
    changes: list[tuple[Path, bytes, bytes]] = []

    for kind in TYPES:
        pending_file = queue_root / kind / "pending.yml"
        completed_file = queue_root / kind / "completed.yml"
        pending = read_queue(pending_file)
        completed = read_queue(completed_file)
        overlap = pending.keys() & completed.keys()
        if overlap:
            raise SyncError(f"{kind}: location in both files: {sorted(overlap)[:3]}")
        unknown = (pending.keys() | completed.keys()) - all_set
        if unknown:
            raise SyncError(f"{kind}: queue contains unknown modules: {sorted(unknown)[:3]}")

        found = {location for location in all_modules if has_raw_content(repo, location, kind)}
        # Keep the existing completed order; append newly detected modules in
        # deterministic inventory order. This avoids gratuitous rewrites.
        completed_order = [loc for loc in completed if loc in found]
        completed_order.extend(loc for loc in all_modules if loc in found and loc not in completed)
        # Preserve queue order as Prime already has it; append newly pending
        # modules in inventory order, without rewriting a stable queue.
        pending_order = [loc for loc in pending if loc not in found]
        pending_order.extend(loc for loc in all_modules if loc not in found and loc not in pending)
        completed_entries = [(loc, {}) for loc in completed_order]
        pending_entries = [(loc, pending.get(loc, {})) for loc in pending_order]

        print(f"{kind}: pending={len(pending_entries)}, completed={len(completed_entries)}, "
              f"to_completed={len(found - completed.keys())}, "
              f"to_pending={len(completed.keys() - found)}")
        for path, entries, is_complete in ((pending_file, pending_entries, False),
                                           (completed_file, completed_entries, True)):
            before = path.read_bytes()
            after = write_queue(entries, is_complete).encode("utf-8")
            if before != after:
                changes.append((path, before, after))

    if not changes:
        print("No changes needed; all six queues already match raw content.")
        return
    print(f"{'Applying' if apply else 'Preview only'}: {len(changes)} queue file(s) to update")
    if not apply:
        print("Run with --apply to save changes.")
        return

    updated: list[tuple[Path, bytes]] = []
    try:
        for path, before, after in changes:
            # Stop instead of overwriting an intervening Prime edit.
            if path.read_bytes() != before:
                raise SyncError(f"Queue changed during sync: {path}")
            atomic_write(path, after)
            updated.append((path, before))
    except Exception:
        for path, previous in reversed(updated):
            atomic_write(path, previous)
        raise
    print(f"Updated {len(updated)} queue file(s) successfully.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO,
                        help="Repository root (defaults to the script's repository)")
    args = parser.parse_args()
    try:
        sync(args.repo_root, args.apply)
        return 0
    except (SyncError, OSError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
