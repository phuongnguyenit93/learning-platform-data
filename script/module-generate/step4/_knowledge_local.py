"""Validated local Knowledge layout and safe, minimal YAML updates for STEP_4_NEW."""

from __future__ import annotations

from dataclasses import dataclass
import copy
import os
from pathlib import Path
import re
import tempfile

import yaml

from generate_menu_detail import (
    QuotedEmpty,
    Step3Error,
    dump_yaml,
    load_yaml_object,
    knowledge_root,
    windows_long_path,
    service_name,
    validate_note,
    GENERATED_FOLDER_RE,
    GENERATED_LESSON_RE,
    read_menu,
    read_slugs,
    validate_existing_detail_status,
    detail_child_nodes,
    StrictLoader,
)


@dataclass(frozen=True)
class Lesson:
    chapter_index: int
    lesson_index: int
    slug: str
    title: str
    chapter_title: str
    info_path: Path
    markdown_path: Path
    info: dict


@dataclass
class KnowledgeLayout:
    root: Path
    note_path: Path | None
    note: dict | None
    detail_path: Path
    detail: dict
    lessons: list[Lesson]


def _regular_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise Step3Error(f"Required regular file missing or symlinked: {path}")


def load_layout(module: Path, *, lang: str = "vi", same_special_note: bool = True) -> KnowledgeLayout:
    """Validate the menu, generated chapter paths, lesson identity and summary."""
    subject = service_name(module)
    root = windows_long_path(knowledge_root(module, lang))
    if root.is_symlink() or not root.is_dir():
        raise Step3Error(f"Knowledge folder missing or symlinked: {root}")
    # Historical note.yml is optional. New STEP 3 never creates it.
    legacy_note_path = root / "note.yml"
    if legacy_note_path.exists() or legacy_note_path.is_symlink():
        note_path: Path | None = legacy_note_path
        note: dict | None = validate_note(
            load_yaml_object(legacy_note_path), subject, require_detail=True
        )
    else:
        note_path = None
        note = None
    chapters = read_menu(root / "menu.yml")
    slugs = read_slugs(root / "menu-level-1-slug.yml", chapters)
    detail_path = root / "menu-detail-status.yml"

    expected_detail = {"menu": [
        {"slug": slug, "title": title, "childs": [
            {"slug": f"{slug}-{j:03d}", "title": section, "status": ""}
            for j, section in enumerate(sections, 1)
        ]}
        for (title, sections), slug in zip(chapters, slugs)
    ]}
    validate_existing_detail_status(detail_path, expected_detail)
    detail = load_yaml_object(detail_path)

    expected_chapter_dirs = {f"{i}.{slug}".casefold()
                             for i, slug in enumerate(slugs, 1)}
    for path in root.iterdir():
        if path.is_symlink():
            raise Step3Error(f"Symlink not allowed inside Knowledge: {path}")
        if path.is_dir() and GENERATED_FOLDER_RE.fullmatch(path.name):
            if path.name.casefold() not in expected_chapter_dirs:
                raise Step3Error(f"Stale chapter directory: {path}")

    lessons: list[Lesson] = []
    for i, ((chapter_title, sections), slug) in enumerate(zip(chapters, slugs), 1):
        chapter_path = root / f"{i}.{slug}"
        if chapter_path.is_symlink() or not chapter_path.is_dir():
            raise Step3Error(f"Expected chapter directory: {chapter_path}")

        expected_filenames = set()
        for j, title in enumerate(sections, 1):
            stem = f"{slug}-{j:03d}"
            expected_filenames.update((stem + ".yml", stem + ".md"))
            info_path = chapter_path / (stem + ".yml")
            markdown_path = chapter_path / (stem + ".md")
            info = load_yaml_object(info_path)
            _regular_file(markdown_path)

            mandatory = {"menuLevel1", "menuLevel2", "status"}
            legacy = {"topic", "specialNote"}
            if not mandatory.issubset(info) or (set(info) - mandatory - legacy):
                raise Step3Error(f"Lesson metadata has unexpected/missing keys: {info_path}")
            if (info["menuLevel1"] != chapter_title or
                    info["menuLevel2"] != title):
                raise Step3Error(f"Lesson identity mismatch: {info_path}")
            if "topic" in info and type(info["topic"]) is not str:
                raise Step3Error(f"Legacy topic must be a string: {info_path}")
            if "specialNote" in info and type(info["specialNote"]) is not str:
                raise Step3Error(f"specialNote must be a string: {info_path}")
            if (note is not None and same_special_note and "specialNote" in info
                    and info["specialNote"] != note["specialNote"]):
                raise Step3Error(f"Lesson specialNote differs from note.yml: {info_path}")
            if type(info["status"]) is not str or (
                    info["status"].strip() != info["status"] or
                    "\n" in info["status"] or "\r" in info["status"]):
                raise Step3Error(f"Invalid lesson status: {info_path}")

            lessons.append(Lesson(i - 1, j - 1, stem, title, chapter_title,
                                  info_path, markdown_path, info))
        for child in chapter_path.iterdir():
            if child.is_symlink():
                raise Step3Error(f"Symlink not allowed in chapter: {child}")
            if child.is_file() and GENERATED_LESSON_RE.fullmatch(child.name):
                if child.name not in expected_filenames:
                    raise Step3Error(f"Stale generated lesson file: {child}")

    return KnowledgeLayout(root, note_path, note, detail_path, detail, lessons)


def markdown_has_content(path: Path) -> bool:
    _regular_file(path)
    try:
        return bool(path.read_text(encoding="utf-8-sig").strip())
    except (OSError, UnicodeError) as exc:
        raise Step3Error(f"Could not read Markdown: {path}: {exc}") from exc


def replace_top_level_scalar(raw: str, field: str, value: str, original: dict) -> str:
    """Change only one scalar field, leaving all other file text untouched."""
    lines = raw.splitlines(keepends=True)
    found = [i for i, line in enumerate(lines)
             if re.match(rf"^{re.escape(field)}[ \t]*:", line)]
    if len(found) != 1:
        raise Step3Error(f"Expected exactly one top-level {field}: field in YAML")
    start = found[0]
    end = start + 1
    while end < len(lines) and not re.match(r"^(?:[A-Za-z][A-Za-z0-9_]*[ \t]*:|#)", lines[end]):
        end += 1
    new_scalar = dump_yaml({field: QuotedEmpty(value)})
    if "\r\n" in raw:
        new_scalar = new_scalar.replace("\n", "\r\n")
    updated = "".join(lines[:start]) + new_scalar + "".join(lines[end:])
    # Confirm the replacement did not inadvertently modify other YAML fields.
    import yaml
    try:
        parsed = yaml.load(updated, Loader=StrictLoader)
    except yaml.YAMLError as exc:
        raise Step3Error(f"Invalid specialNote replacement: {exc}") from exc
    expected = dict(original)
    expected[field] = value
    if parsed != expected:
        raise Step3Error("Refusing replacement because other YAML fields would change")
    return updated


def replace_detail_statuses(raw: str, existing: dict, desired: dict) -> str:
    """Patch only child status lines; preserve titles, layout, comments, and order."""
    desired_statuses = [child["status"]
                        for chapter in desired["menu"] for child in chapter["childs"]]
    # Locate actual YAML mapping keys via AST. The Summary Markdown can contain
    # an indented line such as "status: FAILED"; regex matching all indented
    # status lines would corrupt that human-authored block scalar.
    children = detail_child_nodes(raw)
    if len(children) != len(desired_statuses):
        raise Step3Error("menu-detail-status.yml child count differs from lesson count")
    current_statuses = [child["status"]
                        for chapter in existing["menu"] for child in chapter["childs"]]
    if len(current_statuses) != len(desired_statuses):
        raise Step3Error("Existing status count differs from desired")
    lines = raw.splitlines(keepends=True)
    original_line_ends: list[int] = []
    offset = 0
    for line in lines:
        offset += len(line)
        original_line_ends.append(offset)
    for (_, fields), status, current in zip(children, desired_statuses, current_statuses):
        if type(status) is not str:
            raise Step3Error("Lesson status must be a string")
        if status == current:
            continue  # Preserve the exact original quotes, comments and whitespace.
        if "status" not in fields:
            raise Step3Error("Missing child status in menu-detail-status.yml")
        key, value = fields["status"]
        line_no = key.start_mark.line
        if (not isinstance(value, yaml.ScalarNode) or
                value.start_mark.line != line_no or value.end_mark.line != line_no):
            raise Step3Error("Child status must be on a single YAML line")
        old_line = lines[line_no]
        newline = "\r\n" if old_line.endswith("\r\n") else "\n" if old_line.endswith("\n") else ""
        scalar = dump_yaml({"status": QuotedEmpty(status) if status == "" else status})
        scalar_lines = scalar.splitlines()
        if len(scalar_lines) != 1:
            raise Step3Error("Status must be a single inline YAML scalar")
        # Preserve text after the scalar, including an optional inline comment.
        suffix = raw[value.end_mark.index:original_line_ends[line_no]]
        suffix = suffix.rstrip("\r\n")
        lines[line_no] = " " * key.start_mark.column + scalar_lines[0] + suffix + newline

    updated = "".join(lines)
    try:
        parsed = yaml.load(updated, Loader=StrictLoader)
    except yaml.YAMLError as exc:
        raise Step3Error(f"Invalid refreshed YAML: {exc}") from exc
    if parsed != desired:
        raise Step3Error("Refusing status refresh because non-status content would change")
    return updated


def atomic_write_bytes(path: Path, content: bytes) -> None:
    """One-file atomic replace, using a temp file in the same directory."""
    _regular_file(path)
    fd, name = tempfile.mkstemp(prefix=".knowledge-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def apply_changes(changes: dict[Path, tuple[bytes, bytes]]) -> None:
    """Preflight originals; rollback earlier replacements on a regular failure.

    Not a cross-file ACID transaction; do not run alongside active workers.
    """
    for path, (before, _) in changes.items():
        _regular_file(path)
        if path.read_bytes() != before:
            raise Step3Error(f"File changed since preflight: {path}")
    applied = []
    try:
        for path, (_, after) in changes.items():
            atomic_write_bytes(path, after)
            applied.append(path)
    except Exception as exc:
        rollback_errors = []
        for path in reversed(applied):
            original, replacement = changes[path]
            try:
                if path.read_bytes() != replacement:
                    raise Step3Error(f"Concurrent edit prevents safe rollback: {path}")
                atomic_write_bytes(path, original)
            except Exception as restore_exc:
                rollback_errors.append(str(restore_exc))
        if rollback_errors:
            raise Step3Error("Write failure; rollback incomplete: " +
                             "; ".join(rollback_errors)) from exc
        raise
