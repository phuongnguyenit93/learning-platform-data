#!/usr/bin/env python3
"""STEP_3_NEW: create lesson YAML/Markdown skeletons and menu-detail status.

Includes reusable validation and YAML field helpers used by STEP 4 and
historical data converters. No existing module data is automatically cleaned.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Any

import yaml


SERVICE_NAME_RE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*\Z")
LANG_RE = re.compile(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*\Z")
SLUG_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
RESERVED_STEMS = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


class Step3Error(Exception):
    """A user-correctable STEP 3 input or filesystem conflict."""


class StrictLoader(yaml.SafeLoader):
    """Safe YAML loader that also rejects duplicate mapping keys."""


def _unique_mapping(loader: StrictLoader, node: yaml.MappingNode) -> dict:
    loader.flatten_mapping(node)
    result: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise Step3Error("YAML mapping key must be hashable") from exc
        if duplicate:
            raise Step3Error(f"Duplicate YAML key: {key!r}")
        result[key] = loader.construct_object(value_node, deep=True)
    return result


StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping
)


class QuotedEmpty(str):
    """Write empty YAML strings as double quotes rather than null or ''."""


class Step3Dumper(yaml.SafeDumper):
    pass


def _quote_empty(dumper: yaml.SafeDumper, value: QuotedEmpty) -> yaml.Node:
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style='"')


Step3Dumper.add_representer(QuotedEmpty, _quote_empty)


def dump_yaml(data: Any) -> str:
    return yaml.dump(
        data,
        Dumper=Step3Dumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=120,
        line_break="\n",
    )


def load_yaml_object(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise Step3Error(f"Expected regular YAML file: {path}")
    try:
        value = yaml.load(path.read_text(encoding="utf-8-sig"), Loader=StrictLoader)
    except (OSError, UnicodeError, yaml.YAMLError, Step3Error) as exc:
        raise Step3Error(f"Invalid YAML in {path}: {exc}") from exc
    if type(value) is not dict:
        raise Step3Error(f"Expected YAML mapping at root: {path}")
    return value


def nonempty_string(value: Any, label: str) -> str:
    if type(value) is not str or not value.strip():
        raise Step3Error(f"{label} must be a non-blank string")
    if "\x00" in value:
        raise Step3Error(f"{label} contains a NUL character")
    return value.strip()


def module_path(raw_path: str) -> Path:
    try:
        target = Path(raw_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise Step3Error(f"Module directory does not exist: {raw_path}") from exc
    if not target.is_dir():
        raise Step3Error(f"Module path is not a directory: {target}")
    if not (target / "module-info.json").is_file() and not (target / "master.json").is_file():
        raise Step3Error(f"Module is missing module-info.json (or legacy master.json): {target}")
    return target


def knowledge_root(module: Path, lang: str = "vi") -> Path:
    """Return content/knowledge/<lang>, refusing unsafe or legacy flat layouts."""
    if type(lang) is not str or not LANG_RE.fullmatch(lang):
        raise Step3Error(
            f"Invalid --lang {lang!r}; use lowercase language tags such as vi or en"
        )
    parent = module / "content" / "knowledge"
    content = module / "content"
    if content.is_symlink() or (content.exists() and not content.is_dir()):
        raise Step3Error(f"Unsafe content directory: {content}")
    if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
        raise Step3Error(f"Unsafe Knowledge directory: {parent}")
    # Never silently create a parallel language folder next to legacy
    # language-less YAML. Move the old tree manually before converting again.
    if parent.is_dir():
        legacy = [name for name in (
            "note.yml", "menu.yml", "menu-level-1-slug.yml", "menu-detail-status.yml"
        ) if (parent / name).exists() or (parent / name).is_symlink()]
        if legacy:
            raise Step3Error(
                f"Legacy flat Knowledge layout at {parent}: {legacy}. "
                "Move the existing contents into content/knowledge/vi first."
            )
    dest = parent / lang
    if dest.is_symlink() or (dest.exists() and not dest.is_dir()):
        raise Step3Error(f"Unsafe language Knowledge directory: {dest}")
    return dest


def windows_long_path(path: Path) -> Path:
    """Address long regular files through the extended Win32 path namespace.

    Deep module + chapter + lesson paths can exceed the legacy MAX_PATH limit.
    With ordinary Windows paths, Path.is_file() may silently return False for
    those files and STEP 3 may mistakenly plan duplicate files. Extend the
    already validated Knowledge root *before* appending chapter/lesson paths.
    """
    if os.name != "nt":
        return path
    value = str(path)
    if value.startswith("\\\\?\\"):
        return path
    if value.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + value[2:])
    if not path.is_absolute():
        raise Step3Error(f"Expected absolute Knowledge path: {path}")
    return Path("\\\\?\\" + value)


def service_name(module: Path) -> str:
    metadata = module / "module-info.json"
    if not metadata.is_file():
        metadata = module / "master.json"
    try:
        data = json.loads(metadata.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError, UnicodeError) as exc:
        raise Step3Error(f"Invalid module metadata {metadata}: {module}") from exc
    if type(data) is not dict or type(data.get("SERVICE_NAME")) is not dict:
        raise Step3Error(f"{metadata.name} must contain SERVICE_NAME.VALUE")
    value = data["SERVICE_NAME"].get("VALUE")
    if type(value) is not str or not SERVICE_NAME_RE.fullmatch(value):
        raise Step3Error(f"Invalid SERVICE_NAME.VALUE in {metadata.name}: {value!r}")
    return value


def validate_note(data: dict, subject: str, *, require_detail: bool) -> dict:
    if set(data) != {"subject", "detailName", "specialNote"}:
        raise Step3Error("note.yml must contain exactly subject, detailName, specialNote")
    if data["subject"] != subject:
        raise Step3Error("note.yml subject differs from module SERVICE_NAME.VALUE")
    if type(data["detailName"]) is not str:
        raise Step3Error("note.yml detailName must be a string")
    if type(data["specialNote"]) is not str:
        raise Step3Error("note.yml specialNote must be a string")
    if require_detail:
        nonempty_string(data["detailName"], "note.yml detailName")
    return data


def ensure_regular_or_absent(path: Path) -> None:
    if path.is_symlink():
        raise Step3Error(f"Refusing symlink target: {path}")
    if path.exists() and not path.is_file():
        raise Step3Error(f"File target is not a regular file: {path}")


def write_new(path: Path, content: str) -> None:
    """Create only when absent; clean partial output but never a competing file."""
    opened = False
    try:
        with path.open("x", encoding="utf-8", newline="\n") as output:
            opened = True
            output.write(content)
    except BaseException:
        if opened:
            path.unlink(missing_ok=True)
        raise


# --- Local menu-detail field patching helpers ---
# Keep formatting and human-authored values intact; use parsed YAML key
# positions, not strings inside Markdown block scalars.

# STEP 5 NEW writes these per-lesson fields. They also supply the four
# comparison criteria that a future frontend may render as a table.
CHILD_FIELDS = (
    "difficult", "focus", "problemSolved", "mechanism", "applicationValue", "summary"
)
# Read-only compatibility for already generated menu-detail-status.yml.
# Changing the generator must not silently migrate authored module files.
LEGACY_CHILD_FIELDS = frozenset(("keyQuestion", "valueForModule", "mindset"))
DIFFICULTIES = frozenset(("", "BASIC", "INTERMEDIATE", "ADVANCED"))


class LiteralText(str):
    """YAML literal block scalar; preserve the original Markdown newlines."""


def _dump_literal(dumper: yaml.Dumper, value: LiteralText) -> yaml.Node:
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|")


Step3Dumper.add_representer(LiteralText, _dump_literal)


def empty_fields() -> dict:
    return {field: QuotedEmpty("") for field in CHILD_FIELDS}


def as_yaml_field(field: str, value: str) -> str:
    if value == "":
        value = QuotedEmpty("")
    elif field == "summary":
        value = LiteralText(value)
    return dump_yaml({field: value})


def _map(node: yaml.Node, label: str) -> dict[str, tuple[yaml.Node, yaml.Node]]:
    if not isinstance(node, yaml.MappingNode):
        raise Step3Error(f"{label} must be a YAML mapping")
    fields = {}
    for key, value in node.value:
        if not isinstance(key, yaml.ScalarNode):
            raise Step3Error(f"{label} has a non-scalar YAML key")
        if key.value in fields:
            raise Step3Error(f"{label} contains duplicate YAML key: {key.value}")
        fields[key.value] = (key, value)
    return fields


def detail_child_nodes(raw: str) -> list[tuple[yaml.MappingNode, dict]]:
    """Return only real child YAML nodes, excluding text within block scalars."""
    try:
        root = yaml.compose(raw, Loader=StrictLoader)
    except yaml.YAMLError as exc:
        raise Step3Error(f"Invalid menu-detail-status.yml YAML: {exc}") from exc
    if root is None:
        raise Step3Error("menu-detail-status.yml is empty")
    outer = _map(root, "menu-detail-status.yml")
    if "menu" not in outer or not isinstance(outer["menu"][1], yaml.SequenceNode):
        raise Step3Error("menu-detail-status.yml must contain a menu list")
    nodes = []
    for i, chapter in enumerate(outer["menu"][1].value, start=1):
        fields = _map(chapter, f"menu[{i}]")
        if "childs" not in fields or not isinstance(fields["childs"][1], yaml.SequenceNode):
            raise Step3Error(f"menu[{i}].childs must be a sequence")
        for j, child in enumerate(fields["childs"][1].value, start=1):
            nodes.append((child, _map(child, f"menu[{i}].childs[{j}]")))
    return nodes


def _field_block(field: str, value: str, indent: int, newline: str) -> str:
    rendered = as_yaml_field(field, value).splitlines()
    return newline.join(" " * indent + line for line in rendered) + newline


def plan_detail_enrichment(
    raw: str,
    incoming: dict[str, dict[str, str]] | None = None,
) -> tuple[str, int, int]:
    """Add missing STEP 5 fields and optionally fill empty authored values.

    Existing non-empty field vs a different incoming non-empty value is a
    BLOCKER. Legacy comparison keys are accepted but never renamed or
    auto-backfilled; migration of existing module files is a separate task.
    Never mutate status/identity/Markdown or existing human-authored values.
    """
    try:
        old = yaml.load(raw, Loader=StrictLoader)
    except (yaml.YAMLError, Step3Error) as exc:
        raise Step3Error(f"Invalid menu-detail-status.yml: {exc}") from exc
    if not isinstance(old, dict):
        raise Step3Error("menu-detail-status.yml root must be a mapping")

    incoming = incoming or {}
    edits: list[tuple[int, int, str]] = []
    expected = deepcopy(old)
    newline = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    children_nodes = detail_child_nodes(raw)
    expected_children = [
        child for chapter in expected["menu"] for child in chapter["childs"]
    ]
    if len(children_nodes) != len(expected_children):
        raise Step3Error("Mismatch parsing child YAML nodes")

    seen: set[str] = set()
    added = filled = 0
    for (_, fields), child in zip(children_nodes, expected_children):
        slug = child.get("slug")
        if type(slug) is not str or slug in seen:
            raise Step3Error(f"Invalid/duplicate lesson slug: {slug!r}")
        seen.add(slug)
        if "status" not in fields:
            raise Step3Error(f"Missing status key for lesson {slug!r}")
        status_key, status_node = fields["status"]
        if not isinstance(status_node, yaml.ScalarNode):
            raise Step3Error(f"Invalid multiline status for lesson {slug!r}")
        if status_node.start_mark.line != status_node.end_mark.line:
            raise Step3Error(f"Status is not single-line for lesson {slug!r}")
        status_line = status_key.start_mark.line
        indent = status_key.start_mark.column
        desired = incoming.get(slug, {})
        if not isinstance(desired, dict) or set(desired) - set(CHILD_FIELDS):
            raise Step3Error(f"Unknown lesson field(s) for {slug!r}")

        missing_text = []
        is_legacy = bool(set(child) & LEGACY_CHILD_FIELDS)
        for field in CHILD_FIELDS:
            # The prior three comparison fields are intentionally not
            # converted or supplemented by a STEP 3 rerun on old data.
            if is_legacy and field in (
                "focus", "problemSolved", "mechanism", "applicationValue"
            ) and field not in child:
                if field in desired and desired[field]:
                    raise Step3Error(
                        f"Legacy {slug} requires an explicit STEP 5 field migration"
                    )
                continue
            incoming_value = desired.get(field, "")
            if type(incoming_value) is not str:
                raise Step3Error(f"Incoming {field} must be a string for {slug}")
            if field == "difficult" and incoming_value not in DIFFICULTIES:
                raise Step3Error(f"Invalid incoming difficult={incoming_value!r} for {slug}")
            if field not in child:
                child[field] = incoming_value
                missing_text.append(_field_block(field, incoming_value, indent, newline))
                added += 1
                continue
            existing = child[field]
            if type(existing) is not str:
                raise Step3Error(f"Existing {field} must be a string for {slug}")
            if field == "difficult" and existing not in DIFFICULTIES:
                raise Step3Error(f"Existing difficult={existing!r} is invalid for {slug}")
            if incoming_value == "" or incoming_value == existing:
                continue
            if existing:
                raise Step3Error(
                    f"Conflict for {slug}.{field}: both local and Sheet have non-empty "
                    "different values; refusing overwrite"
                )
            if field not in fields:
                raise Step3Error(f"Missing YAML node for existing {slug}.{field}")
            key_node, value_node = fields[field]
            line_index = key_node.start_mark.line
            if (not isinstance(value_node, yaml.ScalarNode) or
                    value_node.start_mark.line != line_index or
                    value_node.end_mark.line != line_index):
                raise Step3Error(
                    f"Cannot safely fill non-inline empty YAML value for {slug}.{field}"
                )
            source_line = lines[line_index].rstrip("\r\n")
            # Do not drop a human-authored trailing comment when replacing.
            pattern = rf'^([ \t]*){re.escape(field)}[ \t]*:[ \t]*(?:""|\x27\x27)[ \t]*(#.*)?$'
            match = re.fullmatch(pattern, source_line)
            if not match:
                raise Step3Error(
                    f"Cannot safely fill {slug}.{field} with custom inline formatting"
                )
            replacement = _field_block(field, incoming_value, key_node.start_mark.column, newline)
            if match.group(2):
                pos = replacement.find(newline)
                replacement = replacement[:pos].rstrip() + " " + match.group(2) + replacement[pos:]
            edits.append((offsets[line_index], offsets[line_index + 1], replacement))
            child[field] = incoming_value
            filled += 1

        if missing_text:
            # Place new fields directly after the REAL status key. A fake
            # "status:" appearing inside summary Markdown is never matched.
            insert_at = offsets[status_line + 1]
            prefix = "" if lines[status_line].endswith(("\n", "\r")) else newline
            edits.append((insert_at, insert_at, prefix + "".join(missing_text)))

    unknown = set(incoming) - seen
    if unknown:
        raise Step3Error(f"Sheet has extra lesson IDs not in menu: {sorted(unknown)[:5]}")

    updated = raw
    for start, end, replacement in sorted(edits, reverse=True):
        updated = updated[:start] + replacement + updated[end:]
    try:
        actual = yaml.load(updated, Loader=StrictLoader)
    except (yaml.YAMLError, Step3Error) as exc:
        raise Step3Error(f"Updated menu-detail-status.yml would be invalid: {exc}") from exc
    if actual != expected:
        raise Step3Error("YAML patch would change data other than requested child fields")
    return updated, added, filled


def read_exact_text(path: Path) -> tuple[bytes, str]:
    before = path.read_bytes()
    return before, before.decode("utf-8-sig")


def atomic_update_if_unchanged(path: Path, before: bytes, updated: str) -> None:
    """Replace only a verified file, preserving BOM, permissions and file bytes elsewhere."""
    if path.is_symlink() or not path.is_file():
        raise Step3Error(f"Refusing non-regular YAML path: {path}")
    prefix = b"\xef\xbb\xbf" if before.startswith(b"\xef\xbb\xbf") else b""
    after = prefix + updated.encode("utf-8")
    if before == after:
        return
    if path.read_bytes() != before:
        raise Step3Error(f"YAML file changed after preflight: {path}")
    handle, name = tempfile.mkstemp(prefix=".menu-detail-", suffix=".tmp", dir=path.parent)
    try:
        os.chmod(name, stat.S_IMODE(path.stat().st_mode))
        with os.fdopen(handle, "wb") as stream:
            stream.write(after)
            stream.flush()
            os.fsync(stream.fileno())
        if path.read_bytes() != before:
            raise Step3Error(f"YAML file changed before publishing: {path}")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


# --- STEP 3 menu-detail generation CLI ---
GENERATED_FOLDER_RE = re.compile(r"[1-9][0-9]*\..+\Z")
GENERATED_LESSON_RE = re.compile(r"[a-z][a-z0-9-]*-[0-9]{3,}\.(?:md|yml)\Z")


def read_menu(path: Path) -> list[tuple[str, list[str]]]:
    document = load_yaml_object(path)
    if set(document) != {"menu"} or type(document["menu"]) is not list or not document["menu"]:
        raise Step3Error("menu.yml must contain a nonempty 'menu' list")
    result: list[tuple[str, list[str]]] = []
    seen_titles: set[str] = set()
    for i, item in enumerate(document["menu"], start=1):
        if type(item) is not dict or set(item) != {"level1", "level2"}:
            raise Step3Error(f"menu.yml item {i} requires exactly level1 and level2")
        title = nonempty_string(item["level1"], f"menu[{i}].level1")
        if title.casefold() in seen_titles:
            raise Step3Error(f"Duplicate level1 title: {title}")
        seen_titles.add(title.casefold())
        lessons = item["level2"]
        if type(lessons) is not list or not lessons:
            raise Step3Error(f"menu[{i}].level2 must contain at least one lesson")
        if len(lessons) > 999:
            raise Step3Error(f"menu[{i}] has over 999 lessons (three-digit IDs required)")
        labels = [nonempty_string(value, f"menu[{i}].level2[{j}]")
                  for j, value in enumerate(lessons, start=1)]
        if len({value.casefold() for value in labels}) != len(labels):
            raise Step3Error(f"Duplicate level2 title inside menu[{i}]")
        result.append((title, labels))
    return result


def read_slugs(path: Path, chapters: list[tuple[str, list[str]]]) -> list[str]:
    document = load_yaml_object(path)
    if set(document) != {"menu"} or type(document["menu"]) is not list:
        raise Step3Error("menu-level-1-slug.yml must contain a 'menu' list")
    items = document["menu"]
    if len(items) != len(chapters):
        raise Step3Error("Slug count does not match menu.yml level1 count")
    slugs: list[str] = []
    for i, (item, (title, _)) in enumerate(zip(items, chapters)):
        if type(item) is not dict or set(item) != {"title", "slug", "index"}:
            raise Step3Error(f"Slug entry {i} requires exactly title, slug, index")
        if item["title"] != title:
            raise Step3Error(f"Slug entry {i} title/order differs from menu.yml: {title}")
        if type(item["index"]) is not int or item["index"] != i:
            raise Step3Error(f"Slug entry {i} index must be {i} (starting at zero)")
        slug = item["slug"]
        if type(slug) is not str or not SLUG_RE.fullmatch(slug) or len(slug) > 80:
            raise Step3Error(f"Invalid English kebab-case slug at index {i}: {slug!r}")
        if slug in RESERVED_STEMS:
            raise Step3Error(f"Reserved filename slug at index {i}: {slug}")
        if slug.casefold() in {part.casefold() for part in slugs}:
            raise Step3Error(f"Duplicate slug: {slug}")
        slugs.append(slug)
    return slugs


def validate_existing_detail_status(path: Path, expected: dict) -> None:
    """Check the menu identity without overwriting independently edited statuses."""
    existing = load_yaml_object(path)
    if set(existing) != {"menu"} or type(existing["menu"]) is not list:
        raise Step3Error(f"Invalid menu-detail-status.yml root: {path}")
    actual_menus = existing["menu"]
    expected_menus = expected["menu"]
    if len(actual_menus) != len(expected_menus):
        raise Step3Error(f"Menu count changed in existing menu-detail-status.yml: {path}")

    for i, (actual, planned) in enumerate(zip(actual_menus, expected_menus), start=1):
        if type(actual) is not dict or set(actual) != {"slug", "title", "childs"}:
            raise Step3Error(f"Invalid menu-detail-status.yml chapter {i}: {path}")
        if actual["slug"] != planned["slug"] or actual["title"] != planned["title"]:
            raise Step3Error(f"Menu identity changed in menu-detail-status.yml chapter {i}: {path}")

        children = actual["childs"]
        planned_children = planned["childs"]
        if type(children) is not list or len(children) != len(planned_children):
            raise Step3Error(f"Child count changed in menu-detail-status.yml chapter {i}: {path}")
        for j, (child, planned_child) in enumerate(zip(children, planned_children), start=1):
            mandatory = {"slug", "title", "status"}
            if (type(child) is not dict or not mandatory.issubset(child) or
                    set(child) - mandatory - set(CHILD_FIELDS) - LEGACY_CHILD_FIELDS):
                raise Step3Error(f"Invalid menu-detail-status.yml chapter {i} child {j}: {path}")
            if child["slug"] != planned_child["slug"] or child["title"] != planned_child["title"]:
                raise Step3Error(f"Child identity changed in menu-detail-status.yml chapter {i} child {j}: {path}")
            if type(child["status"]) is not str:
                raise Step3Error(f"Invalid status in menu-detail-status.yml chapter {i} child {j}: {path}")
            for field in CHILD_FIELDS:
                if field not in child:
                    continue  # Backward-compatible: generate_menu_detail will add it without overwriting.
                if type(child[field]) is not str:
                    raise Step3Error(f"Invalid {field} in chapter {i} child {j}: {path}")
                if field == "difficult" and child[field] not in DIFFICULTIES:
                    raise Step3Error(f"Invalid difficulty in chapter {i} child {j}: {path}")


def plan_output(module: Path, lang: str = "vi") -> tuple[Path, dict[Path, str], list[Path], int, int]:
    service_name(module)
    root = windows_long_path(knowledge_root(module, lang))
    if root.is_symlink() or not root.is_dir():
        raise Step3Error(f"Run generate_menu_skeleton.py first: {root}")
    chapters = read_menu(root / "menu.yml")
    slugs = read_slugs(root / "menu-level-1-slug.yml", chapters)

    files: dict[Path, str] = {}
    expected_dirs: list[Path] = []
    detail_menus: list[dict] = []
    for i, ((level1, level2), slug) in enumerate(zip(chapters, slugs), start=1):
        folder = root / f"{i}.{slug}"
        expected_dirs.append(folder)
        detail_children: list[dict] = []
        for j, title in enumerate(level2, start=1):
            stem = f"{slug}-{j:03d}"
            info = {
                "menuLevel1": level1,
                "menuLevel2": title,
                "status": QuotedEmpty(""),
            }
            files[folder / f"{stem}.yml"] = dump_yaml(info)
            files[folder / f"{stem}.md"] = ""
            detail_children.append({
                "slug": stem,
                "title": title,
                "status": QuotedEmpty(""),
                **empty_fields(),
            })
        detail_menus.append({"slug": slug, "title": level1, "childs": detail_children})

    detail_path = root / "menu-detail-status.yml"
    detail_document = {"menu": detail_menus}
    files[detail_path] = dump_yaml(detail_document)

    # Prevent a stale folder or lesson from a previous menu revision being
    # silently mistaken for the new version. Never delete any old work.
    expected_folder_names = {p.name.casefold() for p in expected_dirs}
    for entry in root.iterdir():
        if entry.is_symlink():
            raise Step3Error(f"Refusing symlink in Knowledge root: {entry}")
        if entry.is_dir() and GENERATED_FOLDER_RE.fullmatch(entry.name):
            if entry.name.casefold() not in expected_folder_names:
                raise Step3Error(f"Unexpected old/generated chapter directory: {entry}")

    for folder in expected_dirs:
        if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
            raise Step3Error(f"Invalid chapter folder target: {folder}")
        if folder.is_dir():
            expected_paths = {p.name.casefold() for p in files if p.parent == folder}
            for entry in folder.iterdir():
                if entry.is_symlink():
                    raise Step3Error(f"Refusing symlink in chapter: {entry}")
                if entry.is_file() and GENERATED_LESSON_RE.fullmatch(entry.name):
                    if entry.name.casefold() not in expected_paths:
                        raise Step3Error(f"Unexpected old/generated lesson file: {entry}")

    for path, expected_text in files.items():
        ensure_regular_or_absent(path)
        if not path.exists():
            continue
        if path == detail_path:
            validate_existing_detail_status(path, detail_document)
        elif path.suffix == ".yml":
            existing = load_yaml_object(path)
            expected = load_yaml_text(expected_text)
            if any(existing.get(field) != expected[field] for field in
                   ("menuLevel1", "menuLevel2")):
                raise Step3Error(f"Existing lesson metadata differs; refusing overwrite: {path}")
            if type(existing.get("status")) is not str:
                raise Step3Error(f"Existing lesson status must be a string: {path}")
        # Pre-existing Markdown is human-owned, intentionally never replaced.
    return root, files, expected_dirs, len(chapters), sum(len(v) for _, v in chapters)


def load_yaml_text(text: str) -> dict:
    # This text is generated by our own dumper; safe_load is sufficient here.
    import yaml
    value = yaml.safe_load(text)
    assert type(value) is dict
    return value


def finish(module: Path, dry_run: bool, lang: str = "vi") -> None:
    root, files, folders, chapter_count, lesson_count = plan_output(module, lang=lang)
    missing = [path for path in files if not path.exists()]
    existing = len(files) - len(missing)
    detail_path = root / "menu-detail-status.yml"
    detail_before: bytes | None = None
    detail_updated: str | None = None
    added_fields = 0
    if detail_path.is_file():
        # Preflight every field before creating anything. Existing, non-empty
        # human-authored fields/statuses are always preserved.
        detail_before, detail_raw = read_exact_text(detail_path)
        detail_updated, added_fields, _ = plan_detail_enrichment(detail_raw)

    if dry_run:
        print(
            f"DRY_RUN module={module} chapters={chapter_count} lessons={lesson_count} "
            f"new_files={len(missing)} existing_files={existing} "
            f"missing_detail_fields={added_fields}"
        )
        return

    created_dirs: list[Path] = []
    created_files: list[Path] = []
    try:
        for folder in folders:
            if not folder.exists():
                folder.mkdir()
                created_dirs.append(folder)
        for path in missing:
            write_new(path, files[path])
            created_files.append(path)
        if detail_before is not None and detail_updated is not None and added_fields:
            atomic_update_if_unchanged(detail_path, detail_before, detail_updated)
    except Exception:
        # Roll back only files/directories created by this invocation.
        # The existing detail YAML uses an atomic single-file patch.
        for path in reversed(created_files):
            path.unlink(missing_ok=True)
        for folder in reversed(created_dirs):
            try:
                folder.rmdir()
            except OSError:
                pass
        raise

    print(
        f"FINISH_OK knowledge={root} chapters={chapter_count} lessons={lesson_count} "
        f"created={len(created_files)} preserved={existing} "
        f"added_detail_fields={added_fields}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True, help="Path to module containing module-info.json")
    parser.add_argument("--lang", "--language", dest="lang", default="vi",
                        help="Language folder under content/knowledge/ (default: vi)")
    parser.add_argument("--dry-run", action="store_true", help="Validate and preview without writing")
    args = parser.parse_args()
    try:
        finish(module_path(args.module), args.dry_run, lang=args.lang)
    except (Step3Error, OSError, ValueError) as exc:
        print(f"BLOCKER: STEP_3_FINISH: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
