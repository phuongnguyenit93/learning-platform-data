#!/usr/bin/env python3
"""Import per-module two-level Knowledge menus and lessons into Oracle SQL 17-20.

The default command reads Oracle to preview changes but never executes DML.
Use --offline for source-only validation or --apply to commit one module at a
time. No MODULE creation, cascading deletion, or destructive pruning is done.
Only complete locales with VI=WRITTEN or EN=TRANSLATE are imported; the
Oracle status for either ready locale is WRITTEN.
"""

from __future__ import annotations

import argparse
import copy
from collections import Counter
from dataclasses import dataclass, field
import json
import os
from pathlib import Path, PureWindowsPath
import re
import sys
from typing import Any

import yaml

import _checksum_cache as checksum

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _module_source_sync import (  # noqa: E402
    MODULE_ROOT, REPO_ROOT, PRUNED_DIRS, SyncError, connect_oracle,
    safe_oracle_error, validate_text,
)


LANGUAGE_RE = re.compile(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*\Z")
SLUG_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
SERVICE_RE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*\Z")
DIFFICULTIES = frozenset(("BASIC", "INTERMEDIATE", "ADVANCED"))
BATCH_SIZE = 100
# Source workflow states required before importing a complete locale. Oracle
# still stores WRITTEN for publishable content; TRANSLATE is a source-only gate.
SOURCE_READY_STATUS = {"vi": "WRITTEN", "en": "TRANSLATE"}
QA_FIELDS = ("focus", "problemSolved", "mechanism", "applicationValue")
QA_COLUMNS = ("FOCUS", "PROBLEM_SOLVED", "MECHANISM", "APPLICATION_VALUE")
CHILD_FIELDS = frozenset(("slug", "title", "status", "difficult", "summary", *QA_FIELDS))
LEGACY_FIELDS = frozenset(("keyQuestion", "valueForModule", "mindset"))


class StrictLoader(yaml.SafeLoader):
    """Reject silent duplicate keys, including in large Markdown scalars."""


class NotReadyError(SyncError):
    """An incomplete locale is intentionally excluded from Menu/Knowledge import."""


def _unique_mapping(loader: StrictLoader, node: yaml.MappingNode) -> dict:
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str) or key in result:
            raise SyncError(f"Duplicate/non-string YAML key: {key!r}")
        result[key] = loader.construct_object(value_node, deep=True)
    return result


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


@dataclass(frozen=True)
class Lesson:
    slug: str
    title: str
    order: int
    source_status: str
    difficult: str | None
    content: str | None
    focus: str | None
    problem_solved: str | None
    mechanism: str | None
    application_value: str | None
    summary: str | None
    ready: bool

    @property
    def database_status(self) -> str:
        return "WRITTEN" if self.ready else "DRAFT"

    def translation_values(self) -> tuple:
        """The main importer owns CONTENT/STATUS, never the five QA fields."""
        return (self.content, self.database_status)


@dataclass(frozen=True)
class Chapter:
    slug: str
    title: str
    order: int
    lessons: tuple[Lesson, ...]


@dataclass(frozen=True)
class Locale:
    language: str
    chapters: tuple[Chapter, ...]


@dataclass(frozen=True)
class SourceModule:
    path: Path
    service_name: str
    locales: tuple[Locale, ...]


@dataclass(frozen=True)
class SourceHeader:
    """Cheap JSON-only preflight, allowing cache hits before YAML parsing."""
    path: Path
    service_name: str
    languages: tuple[str, ...]


@dataclass
class NodeRow:
    id: int
    slug: str
    sort_order: int
    active: bool
    parent_id: int | None
    node_type: str


@dataclass
class KnowledgeRow:
    id: int
    difficult: str | None
    active: bool


@dataclass
class Snapshot:
    chapters: dict[str, NodeRow] = field(default_factory=dict)
    sections: dict[tuple[int, str], NodeRow] = field(default_factory=dict)
    titles: dict[tuple[int, str], str] = field(default_factory=dict)
    knowledge: dict[int, KnowledgeRow] = field(default_factory=dict)
    translations: dict[tuple[int, str], tuple] = field(default_factory=dict)


def _io_path(path: Path) -> Path:
    """Use Win32's extended-length namespace for deeply nested modules."""
    if os.name != "nt":
        return path
    value = str(path)
    if value.startswith("\\\\?\\"):
        return path
    if value.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + value[2:])
    if not path.is_absolute():
        raise SyncError(f"Expected an absolute source path: {path}")
    return Path("\\\\?\\" + value)


def _read_file(path: Path, root: Path) -> str:
    """Reject symlinks along the whole content path; preserve newline bytes."""
    current = path
    while True:
        if _io_path(current).is_symlink():
            raise SyncError(f"Symlink prohibited in Knowledge source: {current}")
        if current == root:
            break
        if current == current.parent or not current.is_relative_to(root):
            raise SyncError(f"Source path escapes module: {path}")
        current = current.parent
    if not _io_path(path).is_file():
        raise SyncError(f"Missing regular Knowledge file: {path}")
    try:
        result = _io_path(path).read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise SyncError(f"Could not read UTF-8 Knowledge file: {path} ({type(exc).__name__})") from exc
    if "\x00" in result:
        raise SyncError(f"Knowledge source contains NUL: {path}")
    return result


def _json(path: Path, root: Path) -> dict:
    try:
        result = json.loads(_read_file(path, root))
    except ValueError as exc:
        raise SyncError(f"Invalid JSON at {path} ({type(exc).__name__})") from exc
    if type(result) is not dict:
        raise SyncError(f"JSON root must be an object: {path}")
    return result


def _yaml(path: Path, root: Path) -> dict:
    try:
        result = yaml.load(_read_file(path, root), Loader=StrictLoader)
    except yaml.YAMLError as exc:
        raise SyncError(f"Invalid YAML at {path} ({type(exc).__name__})") from exc
    if type(result) is not dict:
        raise SyncError(f"YAML root must be a mapping: {path}")
    return result


def _required(value: Any, limit: int, context: str) -> str:
    result = validate_text(value, limit=limit, context=context)
    assert result is not None
    return result


def _optional(value: Any, limit: int, context: str, *, markdown: bool = False) -> str | None:
    if type(value) is not str:
        raise SyncError(f"{context}: expected a string (empty string allowed)")
    if "\x00" in value:
        raise SyncError(f"{context}: NUL not allowed")
    if not value.strip():
        return None
    if markdown:
        return value
    return validate_text(value, limit=limit, context=context)


def _slug(value: Any, context: str, *, max_length: int = 80) -> str:
    if type(value) is not str or len(value) > max_length or not SLUG_RE.fullmatch(value):
        raise SyncError(f"{context}: expected ASCII kebab-case slug <= {max_length} characters")
    if value in {"con", "prn", "aux", "nul"} | {
        f"{prefix}{i}" for prefix in ("com", "lpt") for i in range(1, 10)
    }:
        raise SyncError(f"{context}: reserved Windows filename slug")
    return value


def source_module_path(argument: str, *, repo_root: Path = REPO_ROOT) -> Path:
    """Accept only a repository-relative module/ path, never arbitrary filesystem."""
    normalized = argument.replace("\\", "/")
    candidate = Path(normalized)
    if (not normalized or candidate.is_absolute() or PureWindowsPath(argument).is_absolute()
            or ".." in candidate.parts or not candidate.parts or candidate.parts[0] != "module"):
        raise SyncError("--module must be a repository-relative module/... directory")
    root = repo_root / "module"
    root = root.resolve()
    resolved = (root / Path(*candidate.parts[1:])).resolve()
    if resolved == root or not resolved.is_relative_to(root) or not resolved.is_dir():
        raise SyncError(f"Invalid module directory: {argument}")
    return resolved


def _parse_locale(module: Path, lang: str, *, include_metadata: bool = False) -> Locale:
    root = module / "content" / "knowledge" / lang
    menu = _yaml(root / "menu.yml", module)
    catalog = _yaml(root / "menu-level-1-slug.yml", module)
    detail = _yaml(root / "menu-detail-status.yml", module)
    for name, document in (("menu.yml", menu), ("menu-level-1-slug.yml", catalog),
                           ("menu-detail-status.yml", detail)):
        if set(document) != {"menu"} or type(document["menu"]) is not list or not document["menu"]:
            raise SyncError(f"{lang}/{name}: expected one nonempty menu list")
    if len(menu["menu"]) != len(catalog["menu"]) or len(menu["menu"]) != len(detail["menu"]):
        raise SyncError(f"{lang}: chapter count mismatch across three menu YAMLs")

    chapters = []
    chapter_slugs: set[str] = set()
    chapter_titles: set[str] = set()
    for index, (entry, chapter_slug, chapter_detail) in enumerate(
            zip(menu["menu"], catalog["menu"], detail["menu"])):
        context = f"{lang} chapter {index + 1}"
        if type(entry) is not dict or set(entry) != {"level1", "level2"}:
            raise SyncError(f"{context}: menu.yml must have level1 and level2")
        title = _required(entry["level1"], 300, context + ".title")
        if title.casefold() in chapter_titles:
            raise SyncError(f"{context}: repeated chapter title")
        chapter_titles.add(title.casefold())
        if type(chapter_slug) is not dict or set(chapter_slug) != {"title", "slug", "index"}:
            raise SyncError(f"{context}: invalid chapter slug catalog entry")
        if chapter_slug["title"] != title or type(chapter_slug["index"]) is not int or chapter_slug["index"] != index:
            raise SyncError(f"{context}: chapter slug catalog/title/order mismatch")
        slug = _slug(chapter_slug["slug"], context + ".slug")
        if slug in chapter_slugs:
            raise SyncError(f"{context}: duplicate chapter slug: {slug}")
        chapter_slugs.add(slug)
        if type(chapter_detail) is not dict or set(chapter_detail) != {"slug", "title", "childs"}:
            raise SyncError(f"{context}: invalid chapter detail structure")
        if chapter_detail["slug"] != slug or chapter_detail["title"] != title:
            raise SyncError(f"{context}: menu-detail-status chapter differs from catalog")
        source_titles = entry["level2"]
        source_lessons = chapter_detail["childs"]
        if (type(source_titles) is not list or not source_titles or len(source_titles) > 999
                or type(source_lessons) is not list or len(source_lessons) != len(source_titles)):
            raise SyncError(f"{context}: invalid lesson count or lesson list")

        lessons = []
        lesson_titles: set[str] = set()
        for section_index, (lesson_title, lesson_detail) in enumerate(zip(source_titles, source_lessons), 1):
            lesson_context = f"{context} lesson {section_index}"
            label = _required(lesson_title, 300, lesson_context + ".title")
            if label.casefold() in lesson_titles:
                raise SyncError(f"{lesson_context}: duplicate lesson title")
            lesson_titles.add(label.casefold())
            if (type(lesson_detail) is not dict or not {"slug", "title", "status"}.issubset(lesson_detail)
                    or set(lesson_detail) - CHILD_FIELDS - LEGACY_FIELDS):
                raise SyncError(f"{lesson_context}: invalid menu-detail-status lesson fields")
            lesson_slug = f"{slug}-{section_index:03d}"
            if lesson_detail["slug"] != lesson_slug or lesson_detail["title"] != label:
                raise SyncError(f"{lesson_context}: mismatched lesson slug/title")
            stem = root / f"{index + 1}.{slug}" / lesson_slug
            info = _yaml(stem.with_suffix(".yml"), module)
            if not {"menuLevel1", "menuLevel2", "status"}.issubset(info) or (
                    set(info) - {"menuLevel1", "menuLevel2", "status", "topic", "specialNote"}):
                raise SyncError(f"{lesson_context}: invalid per-lesson YAML fields")
            if info["menuLevel1"] != title or info["menuLevel2"] != label:
                raise SyncError(f"{lesson_context}: per-lesson title mismatch")
            status = lesson_detail["status"]
            if type(status) is not str or len(status) > 30 or "\n" in status or "\r" in status:
                raise SyncError(f"{lesson_context}: invalid status string")
            if info["status"] != status:
                raise SyncError(f"{lesson_context}: per-lesson status differs from consolidated status")
            content_raw = _read_file(stem.with_suffix(".md"), module)
            content = content_raw if content_raw.strip() else None
            if status and content is None:
                raise SyncError(f"{lesson_context}: nonempty status requires Markdown content")
            difficult = _optional(lesson_detail.get("difficult", ""), 20, lesson_context + ".difficult")
            if difficult is not None and difficult not in DIFFICULTIES:
                raise SyncError(f"{lesson_context}: invalid difficult={difficult!r}")
            # Only the separate metadata sync owns and validates the QA fields.
            # Main Menu+Knowledge sync must not depend on their completion.
            qa = (None, None, None, None)
            summary = None
            if include_metadata:
                qa = tuple(_optional(lesson_detail.get(key, ""), 1000,
                                      lesson_context + "." + key) for key in QA_FIELDS)
                summary = _optional(lesson_detail.get("summary", ""), 0,
                                    lesson_context + ".summary", markdown=True)
            # An absent difficulty is resolved to BASIC when the shared DB
            # Knowledge row is created. Never unpublish authored Markdown just
            # because the optional source difficulty has not been filled in.
            ready = bool(status == SOURCE_READY_STATUS.get(lang, "WRITTEN") and content)
            lessons.append(Lesson(lesson_slug, label, section_index - 1, status,
                                  difficult, content, *qa, summary, ready))
        chapters.append(Chapter(slug, title, index, tuple(lessons)))
    return Locale(lang, tuple(chapters))


def load_module(module: Path, languages: tuple[str, ...] | None = None,
                *, include_metadata: bool = False) -> SourceModule:
    module = module.resolve(strict=True)
    activation = _json(module / "module_activate.json", module)
    if activation.get("isModule") is not True:
        raise SyncError(f"Module is not activated: {module}")
    info = _json(module / "module-info.json", module)
    item = info.get("SERVICE_NAME")
    service = item.get("VALUE") if type(item) is dict else None
    if type(service) is not str or not SERVICE_RE.fullmatch(service) or len(service) > 150:
        raise SyncError(f"Invalid SERVICE_NAME.VALUE in {module}")
    config = info.get("MODULE_LANGUAGE")
    declared = config.get("VALUE") if type(config) is dict else None
    if (type(declared) is not list or not declared or
            any(type(lang) is not str or not LANGUAGE_RE.fullmatch(lang) or len(lang) > 10
                for lang in declared) or len(set(declared)) != len(declared)):
        raise SyncError(f"Invalid MODULE_LANGUAGE.VALUE in {module}")
    if languages is not None:
        if not languages or len(set(languages)) != len(languages) or any(lang not in declared for lang in languages):
            raise SyncError(f"Requested language not enabled by module: {module}")
        selected = tuple(languages)
    else:
        selected = tuple(lang for lang in declared if _io_path(
            module / "content" / "knowledge" / lang / "menu-detail-status.yml").is_file())
    if not selected:
        raise SyncError(f"No Knowledge menu language files available in {module}")
    locales = tuple(_parse_locale(module, lang, include_metadata=include_metadata)
                    for lang in selected)
    baseline = tuple((chapter.slug, tuple(lesson.slug for lesson in chapter.lessons))
                     for chapter in locales[0].chapters)
    seen_difficult: dict[tuple[str, str], str] = {}
    for locale in locales:
        signature = tuple((chapter.slug, tuple(lesson.slug for lesson in chapter.lessons))
                          for chapter in locale.chapters)
        if signature != baseline:
            raise SyncError(f"{module}: inconsistent Chapter/Section slug hierarchy in {locale.language}")
        for chapter in locale.chapters:
            for lesson in chapter.lessons:
                if lesson.difficult is not None:
                    key = (chapter.slug, lesson.slug)
                    existing = seen_difficult.setdefault(key, lesson.difficult)
                    if existing != lesson.difficult:
                        raise SyncError(f"{module}: difficulty differs between languages: {lesson.slug}")
    return SourceModule(module, service, locales)


def ensure_sync_ready(source: SourceModule) -> None:
    """Never write a partial locale: Menu titles and lessons sync as one unit.

    A source status is a workflow gate, not necessarily the Oracle STATUS.
    For EN, TRANSLATE means the English lesson is ready to import and Oracle
    stores it as WRITTEN. For VI, only WRITTEN is eligible.
    """
    for locale in source.locales:
        required = SOURCE_READY_STATUS.get(locale.language, "WRITTEN")
        for chapter in locale.chapters:
            for lesson in chapter.lessons:
                if (lesson.source_status != required or not lesson.content
                        or not lesson.content.strip() or not lesson.ready):
                    raise NotReadyError(
                        f"{source.service_name}/{locale.language}/{chapter.slug}/{lesson.slug}: "
                        f"source status must be {required} with nonempty Markdown "
                        f"before syncing Menu/Knowledge; got {lesson.source_status!r}")


def read_source_header(module: Path, languages: tuple[str, ...] | None = None) -> SourceHeader:
    """Read activation and language declaration, without Menu YAML/lesson text."""
    module = module.resolve(strict=True)
    if _json(module / "module_activate.json", module).get("isModule") is not True:
        raise SyncError(f"Module is not activated: {module}")
    info = _json(module / "module-info.json", module)
    service_node = info.get("SERVICE_NAME")
    service = service_node.get("VALUE") if type(service_node) is dict else None
    if type(service) is not str or not SERVICE_RE.fullmatch(service) or len(service) > 150:
        raise SyncError(f"Invalid SERVICE_NAME.VALUE in {module}")
    language_node = info.get("MODULE_LANGUAGE")
    declared = language_node.get("VALUE") if type(language_node) is dict else None
    if (type(declared) is not list or not declared
            or any(type(lang) is not str or not LANGUAGE_RE.fullmatch(lang) or len(lang) > 10
                   for lang in declared) or len(set(declared)) != len(declared)):
        raise SyncError(f"Invalid MODULE_LANGUAGE.VALUE in {module}")
    if languages is not None:
        if (not languages or len(set(languages)) != len(languages)
                or any(lang not in declared for lang in languages)):
            raise SyncError(f"Requested language not enabled by module: {module}")
        selected = languages
    else:
        selected = tuple(lang for lang in declared if _io_path(
            module / "content" / "knowledge" / lang / "menu-detail-status.yml").is_file())
    if not selected:
        raise SyncError(f"No Knowledge menu language files available in {module}")
    return SourceHeader(module, service, tuple(selected))


def discover_modules(*, repo_root: Path = REPO_ROOT) -> list[Path]:
    root = repo_root / "module"
    matches: list[Path] = []
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name not in PRUNED_DIRS
                         and not (Path(current) / name).is_symlink())
        if "module-info.json" not in files:
            continue
        module = Path(current)
        knowledge = module / "content" / "knowledge"
        if _io_path(knowledge).is_dir() and not _io_path(knowledge).is_symlink() and any(
                _io_path(lang / "menu-detail-status.yml").is_file()
                for lang in _io_path(knowledge).iterdir() if lang.is_dir() and not lang.is_symlink()):
            matches.append(module)
    return matches


def _lob(value: Any) -> str | None:
    if hasattr(value, "read"):
        value = value.read()
    return value if value else None


def find_module_id(connection: Any, prefix: str, service_name: str) -> int | None:
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT ID FROM {prefix}MODULE WHERE SERVICE_NAME = :service_name",
                       service_name=service_name)
        row = cursor.fetchone()
        return int(row[0]) if row is not None else None


def read_languages(connection: Any, prefix: str) -> dict[str, bool]:
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT CODE, IS_ACTIVE FROM {prefix}LANGUAGE")
        return {code: bool(active) for code, active in cursor.fetchall()}


def read_snapshot(connection: Any, prefix: str, module_id: int) -> Snapshot:
    """Read one module and its descendants. Reads all locales to protect them."""
    snapshot = Snapshot()
    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT ID, NODE_TYPE, MENU_PARENT_ID, SLUG, SORT_ORDER, IS_ACTIVE
            FROM {prefix}MODULE_MENU
            WHERE (NODE_TYPE = 'CHAPTER' AND MODULE_ID = :module_id)
               OR (NODE_TYPE = 'SECTION' AND MENU_PARENT_ID IN
                    (SELECT ID FROM {prefix}MODULE_MENU
                     WHERE NODE_TYPE = 'CHAPTER' AND MODULE_ID = :module_id))
            """, module_id=module_id)
        nodes = list(cursor.fetchall())
        # Build chapters before sections regardless of Oracle's row ordering.
        for id_, kind, parent, slug, order, active in sorted(
                nodes, key=lambda row: 0 if row[1] == "CHAPTER" else 1):
            node = NodeRow(int(id_), slug, int(order), bool(active),
                           int(parent) if parent is not None else None, kind)
            if kind == "CHAPTER":
                if slug in snapshot.chapters:
                    raise SyncError(f"Duplicate DB Chapter slug for module ID {module_id}: {slug}")
                snapshot.chapters[slug] = node
            elif kind == "SECTION":
                if node.parent_id not in {chapter.id for chapter in snapshot.chapters.values()}:
                    raise SyncError(f"Section has no Chapter in module ID {module_id}: {slug}")
                key = (node.parent_id, slug)
                if key in snapshot.sections:
                    raise SyncError(f"Duplicate DB Section slug for module ID {module_id}: {slug}")
                snapshot.sections[key] = node
            else:
                raise SyncError(f"Unexpected MODULE_MENU.NODE_TYPE={kind!r}")

        cursor.execute(f"""
            SELECT t.MENU_ID, t.LANGUAGE_CODE, t.TITLE
            FROM {prefix}MODULE_MENU_LANGUAGE t
            JOIN {prefix}MODULE_MENU m ON m.ID = t.MENU_ID
            LEFT JOIN {prefix}MODULE_MENU parent ON parent.ID = m.MENU_PARENT_ID
            WHERE m.MODULE_ID = :module_id OR parent.MODULE_ID = :module_id
            """, module_id=module_id)
        for menu_id, language, title in cursor.fetchall():
            snapshot.titles[(int(menu_id), language)] = title

        cursor.execute(f"""
            SELECT k.ID, k.MENU_ID, k.DIFFICULT, k.IS_ACTIVE
            FROM {prefix}MODULE_KNOWLEDGE k
            JOIN {prefix}MODULE_MENU section ON section.ID = k.MENU_ID
            JOIN {prefix}MODULE_MENU chapter ON chapter.ID = section.MENU_PARENT_ID
            WHERE chapter.MODULE_ID = :module_id
            """, module_id=module_id)
        for knowledge_id, section_id, difficulty, active in cursor.fetchall():
            sid = int(section_id)
            if sid in snapshot.knowledge:
                raise SyncError(f"Multiple Knowledge rows for Section ID {sid}")
            snapshot.knowledge[sid] = KnowledgeRow(int(knowledge_id), difficulty, bool(active))

        cursor.execute(f"""
            SELECT t.KNOWLEDGE_ID, t.LANGUAGE_CODE, t.CONTENT, t.STATUS
            FROM {prefix}MODULE_KNOWLEDGE_LANGUAGE t
            JOIN {prefix}MODULE_KNOWLEDGE k ON k.ID = t.KNOWLEDGE_ID
            JOIN {prefix}MODULE_MENU section ON section.ID = k.MENU_ID
            JOIN {prefix}MODULE_MENU chapter ON chapter.ID = section.MENU_PARENT_ID
            WHERE chapter.MODULE_ID = :module_id
            """, module_id=module_id)
        for id_, language, content, status in cursor:
            key = (int(id_), language)
            if key in snapshot.translations:
                raise SyncError(f"Duplicate DB Knowledge translation for {key}")
            snapshot.translations[key] = (_lob(content), status)
    return snapshot


def _db_ready(values: tuple, difficult: str | None) -> bool:
    content, status = values[:2]
    return bool(difficult in DIFFICULTIES and status == "WRITTEN"
                and content and content.strip())


def sync_module(driver: Any, cursor: Any, prefix: str, source: SourceModule,
                snapshot: Snapshot, module_id: int, *, apply: bool = False) -> Counter[str]:
    """Diff only fully ready source locales. Applying uses the batch importer."""
    ensure_sync_ready(source)
    if apply:
        return sync_module_batched(driver, cursor, prefix, source, snapshot, module_id)
    counts: Counter[str] = Counter()
    incoming = {locale.language for locale in source.locales}
    fake_id = 0

    def new_id() -> int:
        nonlocal fake_id
        fake_id -= 1
        return fake_id

    def upsert_node(*, slug: str, order: int, node_type: str,
                    parent: int | None, lang_titles: dict[str, str]) -> NodeRow:
        location = snapshot.chapters if node_type == "CHAPTER" else snapshot.sections
        key = slug if parent is None else (parent, slug)
        current = location.get(key)
        if current is None:
            counts["menu_insert"] += 1
            id_ = new_id()
            current = NodeRow(id_, slug, order, False, parent, node_type)
            location[key] = current
        elif current.sort_order != order:
            extra_languages = {lang for (menu_id, lang) in snapshot.titles
                               if menu_id == current.id} - incoming
            if extra_languages:
                raise SyncError(f"{source.service_name}/{slug}: sort order differs from "
                                "existing unselected language translations")
            counts["menu_update"] += 1
            current.sort_order = order
        else:
            counts["menu_unchanged"] += 1

        for lang, title in lang_titles.items():
            title_key = (current.id, lang)
            previous = snapshot.titles.get(title_key)
            if previous == title:
                counts["menu_language_unchanged"] += 1
                continue
            counts["menu_language_insert" if previous is None else "menu_language_update"] += 1
            snapshot.titles[title_key] = title
        return current

    baseline = source.locales[0]
    for chapter_idx, chapter in enumerate(baseline.chapters):
        titles = {locale.language: locale.chapters[chapter_idx].title for locale in source.locales}
        chapter_row = upsert_node(slug=chapter.slug, order=chapter.order,
                                  node_type="CHAPTER", parent=None, lang_titles=titles)
        for lesson_idx, lesson in enumerate(chapter.lessons):
            translations = {locale.language: locale.chapters[chapter_idx].lessons[lesson_idx]
                            for locale in source.locales}
            section_row = upsert_node(
                slug=lesson.slug, order=lesson.order, node_type="SECTION",
                parent=chapter_row.id,
                lang_titles={lang: item.title for lang, item in translations.items()})
            knowledge = snapshot.knowledge.get(section_row.id)
            incoming_difficulty = next((item.difficult for item in translations.values()
                                        if item.difficult is not None), None)
            if incoming_difficulty is None:
                # The column is shared across locales. Prefer an existing
                # valid difficulty over a synthetic default so a vi-only run
                # cannot overwrite a previously authored en difficulty.
                incoming_difficulty = (knowledge.difficult if knowledge is not None
                                       and knowledge.difficult in DIFFICULTIES else "BASIC")
            if knowledge is None:
                counts["knowledge_insert"] += 1
                kid = new_id()
                knowledge = KnowledgeRow(kid, incoming_difficulty, False)
                snapshot.knowledge[section_row.id] = knowledge
            elif incoming_difficulty is not None and knowledge.difficult != incoming_difficulty:
                other_languages = {lang for (kid, lang) in snapshot.translations
                                   if kid == knowledge.id} - incoming
                if other_languages:
                    raise SyncError(f"{source.service_name}/{lesson.slug}: difficulty conflict "
                                    "with existing unselected language translations")
                counts["knowledge_update"] += 1
                knowledge.difficult = incoming_difficulty
            else:
                counts["knowledge_unchanged"] += 1

            for lang, item in translations.items():
                values = item.translation_values()
                key = (knowledge.id, lang)
                previous = snapshot.translations.get(key)
                if previous is not None and previous[:2] == values:
                    counts["knowledge_language_unchanged"] += 1
                    continue
                counts["knowledge_language_insert" if previous is None else "knowledge_language_update"] += 1
                if item.ready:
                    counts["published_locales"] += 1
                else:
                    counts["draft_locales"] += 1
                snapshot.translations[key] = values

    # IS_ACTIVE is shared between locales. Imported source workflow states
    # are mapped to Oracle WRITTEN; an existing DRAFT translation never activates.
    for chapter in baseline.chapters:
        chapter_row = snapshot.chapters[chapter.slug]
        for lesson in chapter.lessons:
            section = snapshot.sections[(chapter_row.id, lesson.slug)]
            knowledge = snapshot.knowledge[section.id]
            active = any(_db_ready(values, knowledge.difficult)
                         for (kid, _lang), values in snapshot.translations.items()
                         if kid == knowledge.id)
            for table, row in (("MODULE_KNOWLEDGE", knowledge),
                               ("MODULE_MENU", section)):
                if row.active != active:
                    counts["activation_update"] += 1
                    row.active = active
        # Existing sections omitted from the source are preserved, including
        # their activation state; this importer deliberately never prunes.
        active_chapter = any(section.active for (parent, _), section in
                             snapshot.sections.items() if parent == chapter_row.id)
        if chapter_row.active != active_chapter:
            counts["activation_update"] += 1
            chapter_row.active = active_chapter

    source_chapters = {chapter.slug for chapter in baseline.chapters}
    source_sections = {(chapter.slug, lesson.slug) for chapter in baseline.chapters
                       for lesson in chapter.lessons}
    counts["stale_chapters_preserved"] = sum(
        chapter.slug not in source_chapters for chapter in snapshot.chapters.values())
    chapters_by_id = {chapter.id: chapter.slug for chapter in snapshot.chapters.values()}
    counts["stale_sections_preserved"] = sum(
        (chapters_by_id[parent], slug) not in source_sections
        for parent, slug in snapshot.sections)
    counts["chapters"] = len(baseline.chapters)
    counts["sections"] = sum(len(chapter.lessons) for chapter in baseline.chapters)
    counts["languages"] = len(source.locales)
    counts["published_total"] = sum(lesson.ready for locale in source.locales
                                    for chapter in locale.chapters for lesson in chapter.lessons)
    counts["draft_total"] = counts["sections"] * counts["languages"] - counts["published_total"]
    return counts


def _execute_batches(cursor: Any, sql: str, rows: list[dict[str, Any]],
                     *, content_type: Any = None) -> None:
    """Array DML with bounded buffers; never commit or swallow partial failures."""
    for start in range(0, len(rows), BATCH_SIZE):
        chunk = rows[start:start + BATCH_SIZE]
        if content_type is not None:
            cursor.setinputsizes(content=content_type)
        cursor.executemany(sql, chunk)
        if cursor.rowcount != len(chunk):
            raise SyncError(
                f"Batch affected {cursor.rowcount} rows instead of {len(chunk)}; "
                "rolling back the module")


def sync_module_batched(driver: Any, cursor: Any, prefix: str, source: SourceModule,
                        snapshot: Snapshot, module_id: int) -> Counter[str]:
    """Apply the validated diff in dependency order using <=100-row array DML.

    Generated IDs are resolved by the existing unique Chapter/Section/Knowledge
    keys after each insertion phase. The caller owns the module lock and the
    single commit/rollback for the *whole* module; batches never commit.
    """
    if cursor is None:
        raise SyncError("Batch import requires an Oracle cursor")

    # Reuse the exact legacy diff/guard semantics (including unselected locales)
    # before making any change. Deepcopy leaves the authoritative snapshot intact.
    counts = sync_module(driver, None, prefix, source, copy.deepcopy(snapshot),
                         module_id, apply=False)
    baseline = source.locales[0]

    chapter_inserts = [
        {"module_id": module_id, "slug": chapter.slug, "sort_order": chapter.order}
        for chapter in baseline.chapters if chapter.slug not in snapshot.chapters
    ]
    _execute_batches(cursor, f"""
        INSERT INTO {prefix}MODULE_MENU
          (MODULE_ID, MENU_PARENT_ID, NODE_TYPE, MENU_PARENT_TYPE, SLUG, SORT_ORDER, IS_ACTIVE)
        VALUES (:module_id, NULL, 'CHAPTER', NULL, :slug, :sort_order, 0)
        """, chapter_inserts)
    if chapter_inserts:
        cursor.execute(f"""
            SELECT ID, SLUG FROM {prefix}MODULE_MENU
            WHERE MODULE_ID = :module_id AND NODE_TYPE = 'CHAPTER'
            """, module_id=module_id)
        ids = {slug: int(id_) for id_, slug in cursor.fetchall()}
        for row in chapter_inserts:
            chapter_id = ids.get(row["slug"])
            if chapter_id is None:
                raise SyncError(f"Inserted Chapter ID not found: {row['slug']}")
            snapshot.chapters[row["slug"]] = NodeRow(
                chapter_id, row["slug"], row["sort_order"], False, None, "CHAPTER")

    chapter_orders = []
    for chapter in baseline.chapters:
        node = snapshot.chapters[chapter.slug]
        if node.sort_order != chapter.order:
            chapter_orders.append({"sort_order": chapter.order, "menu_id": node.id})
            node.sort_order = chapter.order
    _execute_batches(cursor, f"UPDATE {prefix}MODULE_MENU SET SORT_ORDER = :sort_order "
                     "WHERE ID = :menu_id", chapter_orders)

    section_inserts = []
    for chapter in baseline.chapters:
        parent_id = snapshot.chapters[chapter.slug].id
        for lesson in chapter.lessons:
            if (parent_id, lesson.slug) not in snapshot.sections:
                section_inserts.append({
                    "parent_id": parent_id, "slug": lesson.slug, "sort_order": lesson.order})
    _execute_batches(cursor, f"""
        INSERT INTO {prefix}MODULE_MENU
          (MODULE_ID, MENU_PARENT_ID, NODE_TYPE, MENU_PARENT_TYPE, SLUG, SORT_ORDER, IS_ACTIVE)
        VALUES (NULL, :parent_id, 'SECTION', 'CHAPTER', :slug, :sort_order, 0)
        """, section_inserts)
    if section_inserts:
        cursor.execute(f"""
            SELECT section.ID, section.MENU_PARENT_ID, section.SLUG
            FROM {prefix}MODULE_MENU section
            JOIN {prefix}MODULE_MENU chapter ON chapter.ID = section.MENU_PARENT_ID
            WHERE chapter.MODULE_ID = :module_id AND section.NODE_TYPE = 'SECTION'
            """, module_id=module_id)
        ids = {(int(parent), slug): int(id_)
               for id_, parent, slug in cursor.fetchall()}
        for row in section_inserts:
            key = (row["parent_id"], row["slug"])
            section_id = ids.get(key)
            if section_id is None:
                raise SyncError(f"Inserted Section ID not found: {key}")
            snapshot.sections[key] = NodeRow(
                section_id, row["slug"], row["sort_order"], False, row["parent_id"], "SECTION")

    section_orders = []
    for chapter in baseline.chapters:
        parent_id = snapshot.chapters[chapter.slug].id
        for lesson in chapter.lessons:
            node = snapshot.sections[(parent_id, lesson.slug)]
            if node.sort_order != lesson.order:
                section_orders.append({"sort_order": lesson.order, "menu_id": node.id})
                node.sort_order = lesson.order
    _execute_batches(cursor, f"UPDATE {prefix}MODULE_MENU SET SORT_ORDER = :sort_order "
                     "WHERE ID = :menu_id", section_orders)

    title_inserts = []
    title_updates = []
    for locale in source.locales:
        for chapter in locale.chapters:
            chapter_id = snapshot.chapters[chapter.slug].id
            titles = [(chapter_id, chapter.title)]
            titles.extend(
                (snapshot.sections[(chapter_id, lesson.slug)].id, lesson.title)
                for lesson in chapter.lessons)
            for menu_id, title in titles:
                key = (menu_id, locale.language)
                old = snapshot.titles.get(key)
                if old == title:
                    continue
                row = {"menu_id": menu_id, "lang": locale.language, "title": title}
                (title_inserts if old is None else title_updates).append(row)
                snapshot.titles[key] = title
    _execute_batches(cursor, f"""
        INSERT INTO {prefix}MODULE_MENU_LANGUAGE
          (MENU_ID, LANGUAGE_CODE, TITLE, DESCRIPTION)
        VALUES (:menu_id, :lang, :title, NULL)
        """, title_inserts)
    _execute_batches(cursor, f"""
        UPDATE {prefix}MODULE_MENU_LANGUAGE SET TITLE = :title
        WHERE MENU_ID = :menu_id AND LANGUAGE_CODE = :lang
        """, title_updates)

    knowledge_inserts = []
    difficulty_updates = []
    for chapter_idx, chapter in enumerate(baseline.chapters):
        chapter_id = snapshot.chapters[chapter.slug].id
        for lesson_idx, lesson in enumerate(chapter.lessons):
            section_id = snapshot.sections[(chapter_id, lesson.slug)].id
            knowledge = snapshot.knowledge.get(section_id)
            translations = [loc.chapters[chapter_idx].lessons[lesson_idx]
                            for loc in source.locales]
            incoming_difficulty = next(
                (item.difficult for item in translations if item.difficult is not None), None)
            if incoming_difficulty is None:
                incoming_difficulty = (knowledge.difficult if knowledge is not None
                                       and knowledge.difficult in DIFFICULTIES else "BASIC")
            if knowledge is None:
                knowledge_inserts.append({
                    "menu_id": section_id, "difficult": incoming_difficulty})
            elif knowledge.difficult != incoming_difficulty:
                difficulty_updates.append({
                    "knowledge_id": knowledge.id, "difficult": incoming_difficulty})
                knowledge.difficult = incoming_difficulty
    _execute_batches(cursor, f"""
        INSERT INTO {prefix}MODULE_KNOWLEDGE
          (MENU_ID, MENU_NODE_TYPE, DIFFICULT, IS_ACTIVE)
        VALUES (:menu_id, 'SECTION', :difficult, 0)
        """, knowledge_inserts)
    if knowledge_inserts:
        cursor.execute(f"""
            SELECT k.ID, k.MENU_ID
            FROM {prefix}MODULE_KNOWLEDGE k
            JOIN {prefix}MODULE_MENU section ON section.ID = k.MENU_ID
            JOIN {prefix}MODULE_MENU chapter ON chapter.ID = section.MENU_PARENT_ID
            WHERE chapter.MODULE_ID = :module_id
            """, module_id=module_id)
        ids = {int(menu_id): int(knowledge_id) for knowledge_id, menu_id in cursor.fetchall()}
        for row in knowledge_inserts:
            knowledge_id = ids.get(row["menu_id"])
            if knowledge_id is None:
                raise SyncError(f"Inserted Knowledge ID not found for Section: {row['menu_id']}")
            snapshot.knowledge[row["menu_id"]] = KnowledgeRow(
                knowledge_id, row["difficult"], False)
    _execute_batches(cursor, f"UPDATE {prefix}MODULE_KNOWLEDGE "
                     "SET DIFFICULT = :difficult WHERE ID = :knowledge_id", difficulty_updates)

    content_inserts = []
    content_updates = []
    for locale in source.locales:
        for chapter in locale.chapters:
            chapter_id = snapshot.chapters[chapter.slug].id
            for lesson in chapter.lessons:
                section_id = snapshot.sections[(chapter_id, lesson.slug)].id
                knowledge_id = snapshot.knowledge[section_id].id
                key = (knowledge_id, locale.language)
                values = lesson.translation_values()
                old = snapshot.translations.get(key)
                if old is not None and old[:2] == values:
                    continue
                row = {"knowledge_id": knowledge_id, "lang": locale.language,
                       "content": values[0], "status": values[1]}
                (content_inserts if old is None else content_updates).append(row)
                snapshot.translations[key] = values
    _execute_batches(cursor, f"""
        INSERT INTO {prefix}MODULE_KNOWLEDGE_LANGUAGE
          (KNOWLEDGE_ID, LANGUAGE_CODE, CONTENT, STATUS)
        VALUES (:knowledge_id, :lang, :content, :status)
        """, content_inserts, content_type=driver.DB_TYPE_CLOB)
    _execute_batches(cursor, f"""
        UPDATE {prefix}MODULE_KNOWLEDGE_LANGUAGE
        SET CONTENT = :content, STATUS = :status
        WHERE KNOWLEDGE_ID = :knowledge_id AND LANGUAGE_CODE = :lang
        """, content_updates, content_type=driver.DB_TYPE_CLOB)

    knowledge_activation = []
    menu_activation = []
    for chapter in baseline.chapters:
        chapter_row = snapshot.chapters[chapter.slug]
        for lesson in chapter.lessons:
            section = snapshot.sections[(chapter_row.id, lesson.slug)]
            knowledge = snapshot.knowledge[section.id]
            active = any(_db_ready(values, knowledge.difficult)
                         for (kid, _lang), values in snapshot.translations.items()
                         if kid == knowledge.id)
            if knowledge.active != active:
                knowledge_activation.append({"active": int(active), "id": knowledge.id})
                knowledge.active = active
            if section.active != active:
                menu_activation.append({"active": int(active), "id": section.id})
                section.active = active
        # Existing out-of-source Sections retain their active state.
        active_chapter = any(section.active for (parent, _slug), section in
                             snapshot.sections.items() if parent == chapter_row.id)
        if chapter_row.active != active_chapter:
            menu_activation.append({"active": int(active_chapter), "id": chapter_row.id})
            chapter_row.active = active_chapter
    _execute_batches(cursor, f"UPDATE {prefix}MODULE_KNOWLEDGE "
                     "SET IS_ACTIVE = :active WHERE ID = :id", knowledge_activation)
    _execute_batches(cursor, f"UPDATE {prefix}MODULE_MENU "
                     "SET IS_ACTIVE = :active WHERE ID = :id", menu_activation)
    return counts


def _ensure_db_languages(source: SourceModule, supported: dict[str, bool]) -> None:
    for locale in source.locales:
        if locale.language not in supported:
            raise SyncError(f"Oracle LANGUAGE missing: {locale.language}")
        if not supported[locale.language]:
            raise SyncError(f"Oracle LANGUAGE inactive: {locale.language}")


def _format_counts(source: SourceModule, stats: Counter[str], *, applied: bool) -> str:
    return (f"{'APPLIED' if applied else 'DRY_RUN'} {source.service_name} "
            f"langs={','.join(item.language for item in source.locales)} "
            f"chapters={stats['chapters']} sections={stats['sections']} "
            f"ready={stats['published_total']} draft={stats['draft_total']} "
            f"menu+={stats['menu_insert']} menu~={stats['menu_update']} "
            f"title+={stats['menu_language_insert']} title~={stats['menu_language_update']} "
            f"knowledge+={stats['knowledge_insert']} knowledge~={stats['knowledge_update']} "
            f"content+={stats['knowledge_language_insert']} "
            f"content~={stats['knowledge_language_update']} "
            f"activation~={stats['activation_update']} "
            f"stale_chapters={stats['stale_chapters_preserved']} "
            f"stale_sections={stats['stale_sections_preserved']}")


def _import_one(driver: Any, connection: Any, prefix: str, source: SourceModule,
                supported: dict[str, bool], *, apply: bool) -> Counter[str]:
    _ensure_db_languages(source, supported)
    module_id = find_module_id(connection, prefix, source.service_name)
    if module_id is None:
        raise SyncError(f"No Oracle MODULE for SERVICE_NAME {source.service_name}")
    if apply:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT ID FROM {prefix}MODULE WHERE ID = :module_id FOR UPDATE",
                           module_id=module_id)
            if cursor.fetchone() is None:
                raise SyncError(f"MODULE.ID={module_id} disappeared before import")
            # Re-read after obtaining the module lock to prevent stale plans.
            snapshot = read_snapshot(connection, prefix, module_id)
            result = sync_module(driver, cursor, prefix, source, snapshot, module_id, apply=True)
        connection.commit()
        return result
    snapshot = read_snapshot(connection, prefix, module_id)
    return sync_module(driver, None, prefix, source, snapshot, module_id, apply=False)


def _has_changes(stats: Counter[str]) -> bool:
    return any(stats[key] for key in (
        "menu_insert", "menu_update", "menu_language_insert", "menu_language_update",
        "knowledge_insert", "knowledge_update", "knowledge_language_insert",
        "knowledge_language_update", "activation_update",
    ))


def _lock_module(connection: Any, prefix: str, module_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT ID FROM {prefix}MODULE WHERE ID = :module_id FOR UPDATE",
                       module_id=module_id)
        if cursor.fetchone() is None:
            raise SyncError(f"Oracle MODULE.ID={module_id} disappeared before import")


def _fast_skip(connection: Any, prefix: str, header: SourceHeader,
               supported: dict[str, bool], module_id: int, source_sha: str,
               *, force: bool) -> bool:
    """Lock first; validate an authenticated checkpoint and a lightweight DB witness.

    Never call load_module() or read_snapshot() on the successful hit path.
    A failed witness query is a cache miss, including ORA_ROWSCN errors.
    """
    if force:
        return False
    for language in header.languages:
        if not supported.get(language, False):
            return False
    try:
        _lock_module(connection, prefix, module_id)
        remote = checksum.oracle_identity(connection)
        record = checksum.load_checkpoint(
            header.path, header.service_name, header.languages,
            prefix, module_id, remote)
        if record is None or record["source"] != source_sha:
            return False
        if record["database"] != checksum.db_witness(connection, prefix, module_id):
            return False
        # A source edit during the DB probe must not create a false hit.
        return checksum.source_digest(header.path, header.languages, _io_path) == source_sha
    except Exception:
        # Never skip based on a witness we could not verify.
        return False
    finally:
        connection.rollback()  # Release MODULE row lock even on a cache hit.


def _checkpoint_after_commit(driver: Any, connection: Any, prefix: str,
                             header: SourceHeader, source: SourceModule,
                             module_id: int, source_sha: str) -> bool:
    """Recheck committed DB content before sealing the source+DB checkpoint.

    Reacquire the module lock because the prior transaction has committed.
    If another importer wrote between commit and this lock, full snapshot diff
    detects it; the checkpoint is never recorded against the wrong DB data.
    """
    if not os.environ.get("ORACLE_DSN"):
        return False
    try:
        _lock_module(connection, prefix, module_id)
        committed = read_snapshot(connection, prefix, module_id)
        check = sync_module(driver, None, prefix, source, committed, module_id,
                            apply=False)
        if _has_changes(check):
            return False
        remote = checksum.oracle_identity(connection)
        db_sha = checksum.db_witness(connection, prefix, module_id)
        # Changes made while importing invalidate the checkpoint, but do not
        # roll back the successfully committed Oracle transaction.
        if checksum.source_digest(header.path, header.languages, _io_path) != source_sha:
            return False
        return checksum.save_checkpoint(
            header.path, header.service_name, header.languages,
            prefix, module_id, remote, source_sha, db_sha)
    except Exception:
        return False
    finally:
        connection.rollback()


def run(args: argparse.Namespace, *, single: bool) -> int:
    languages = tuple(args.lang) if args.lang else None
    paths = ([source_module_path(args.module)] if single else discover_modules())
    candidates: list[SourceHeader] = []
    errors: list[str] = []
    seen: dict[str, Path] = {}
    conflicted: set[str] = set()
    for path in paths:
        try:
            header = read_source_header(path, languages)
            if header.service_name in conflicted:
                raise SyncError(f"Repeated SERVICE_NAME already blocked: {header.service_name} at {path}")
            if header.service_name in seen:
                # Reject *both* modules: it is unsafe to import the first
                # candidate after discovering a second owner for its key.
                candidates = [item for item in candidates if item.service_name != header.service_name]
                conflicted.add(header.service_name)
                raise SyncError(f"Duplicate SERVICE_NAME {header.service_name} "
                                f"in {seen[header.service_name]} and {path}")
            seen[header.service_name] = path
            candidates.append(header)
        except (SyncError, OSError, ValueError) as exc:
            errors.append(str(exc))
    skipped = 0
    skipped_not_ready = 0
    synced = 0
    cache_saved = 0
    if args.offline:
        for header in candidates:
            try:
                source = load_module(header.path, header.languages)
                ensure_sync_ready(source)
                count = sum(len(chapter.lessons) for chapter in source.locales[0].chapters)
                ready = sum(lesson.ready for locale in source.locales
                            for chapter in locale.chapters for lesson in chapter.lessons)
                print(f"OFFLINE_VALID {source.service_name} "
                      f"langs={','.join(locale.language for locale in source.locales)} "
                      f"chapters={len(source.locales[0].chapters)} lessons={count} "
                      f"ready={ready} draft={count * len(source.locales) - ready}")
                synced += 1
            except NotReadyError as exc:
                skipped_not_ready += 1
                print(f"SKIPPED_NOT_READY {header.service_name}: {exc}")
            except (SyncError, OSError, ValueError) as exc:
                errors.append(str(exc))
    elif candidates:
        driver, connection, prefix = connect_oracle()
        try:
            supported = read_languages(connection, prefix)
            for header in candidates:
                try:
                    for lang in header.languages:
                        if lang not in supported or not supported[lang]:
                            raise SyncError(f"Oracle LANGUAGE missing/inactive: {lang}")
                    # --apply may use checksum fast path; dry-run ALWAYS parses
                    # and compares the complete DB snapshot for a real diff.
                    source_sha = None
                    module_id = None
                    if args.apply:
                        module_id = find_module_id(connection, prefix, header.service_name)
                        if module_id is None:
                            raise SyncError(f"No Oracle MODULE for SERVICE_NAME {header.service_name}")
                        try:
                            source_sha = checksum.source_digest(
                                header.path, header.languages, _io_path)
                        except (OSError, ValueError) as exc:
                            # A source hash failure cannot justify skipping;
                            # the canonical parser will validate real inputs.
                            source_sha = None
                        if source_sha is not None and _fast_skip(
                                connection, prefix, header, supported, module_id, source_sha,
                                force=bool(getattr(args, "force", False))):
                            skipped += 1
                            print(f"SKIPPED_UNCHANGED {header.service_name} "
                                  f"langs={','.join(header.languages)} "
                                  "(source SHA-256 and Oracle state verified)")
                            continue
                    source = load_module(header.path, header.languages)
                    ensure_sync_ready(source)
                    stats = _import_one(driver, connection, prefix, source,
                                        supported, apply=args.apply)
                    print(_format_counts(source, stats, applied=args.apply))
                    synced += 1
                    if args.apply and source_sha is not None and module_id is not None:
                        if _checkpoint_after_commit(driver, connection, prefix,
                                                    header, source, module_id, source_sha):
                            cache_saved += 1
                except NotReadyError as exc:
                    connection.rollback()
                    skipped_not_ready += 1
                    print(f"SKIPPED_NOT_READY {header.service_name}: {exc}")
                except Exception as exc:
                    connection.rollback()
                    errors.append(f"{header.service_name}: " + (
                        str(exc) if isinstance(exc, SyncError) else safe_oracle_error(exc)))
            if not args.apply:
                connection.rollback()
        finally:
            connection.close()
    print(f"MODE={'OFFLINE' if args.offline else 'APPLY' if args.apply else 'DRY_RUN'} "
          f"valid_sources={len(candidates)} synced={synced} skipped_unchanged={skipped} "
          f"skipped_not_ready={skipped_not_ready} "
          f"checkpoints_saved={cache_saved} errors={len(errors)}; "
          "POLICY no DELETE, no MODULE creation; unselected locales preserved")
    for error in errors[:20]:
        print(f"MENU_KNOWLEDGE_ERROR: {error}", file=sys.stderr)
    return 1 if errors else 0


def entrypoint(*, single: bool) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    if single:
        parser.add_argument("--module", required=True,
                            help="Repository-relative path starting with module/")
    parser.add_argument("--lang", action="append", metavar="CODE",
                        help="Only this language; repeat for vi/en. Default: all available languages")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Read-only Oracle diff (default)")
    mode.add_argument("--offline", action="store_true", help="Validate source; do not connect Oracle")
    mode.add_argument("--apply", action="store_true", help="Write to Oracle with per-module transaction")
    parser.add_argument("--no-skip-unchanged", "--force", dest="force", action="store_true",
                        help="Always re-parse/re-sync on --apply; ignore checksum checkpoints")
    args = parser.parse_args()
    try:
        if args.lang and any(not LANGUAGE_RE.fullmatch(lang) or len(lang) > 10 for lang in args.lang):
            raise SyncError("Invalid --lang: use a lowercase language code")
        return run(args, single=single)
    except (SyncError, OSError, ValueError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"BLOCKED: {safe_oracle_error(exc)}", file=sys.stderr)
        return 1
