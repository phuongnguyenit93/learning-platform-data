#!/usr/bin/env python3
"""Report modules whose Menu/Knowledge import is missing or incomplete in Oracle.

Read-only: checks the same chapter/section slug and locale identities as
sync-menu-knowledge-*.py. It does not import, delete, or edit Oracle rows.
This fast check compares structure, localized titles, publication status and
whether a published lesson has content. It does not compare Markdown text bytes
or the five QA metadata fields (those have a separate importer).
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

import yaml

import _knowledge_menu_sync as core


REPORT = Path(__file__).resolve().parent / "report" / "missing-knowledge.yml"
SAMPLE_LIMIT = 8
ISSUE_KEYS = (
    "chapters", "sections", "menu_languages", "knowledge",
    "knowledge_languages", "menu_order", "menu_titles",
    "knowledge_status", "empty_content", "difficulty", "activation",
)


def read_source_outline(header: core.SourceHeader) -> dict[str, Any]:
    """Read three source menu YAMLs without loading thousands of lesson Markdown files."""
    locales = []
    for language in header.languages:
        root = header.path / "content" / "knowledge" / language
        menu = core._yaml(root / "menu.yml", header.path)
        catalog = core._yaml(root / "menu-level-1-slug.yml", header.path)
        detail = core._yaml(root / "menu-detail-status.yml", header.path)
        for data in (menu, catalog, detail):
            if set(data) != {"menu"} or not isinstance(data["menu"], list) or not data["menu"]:
                raise core.SyncError(f"{header.service_name}/{language}: invalid menu YAML")
        if not (len(menu["menu"]) == len(catalog["menu"]) == len(detail["menu"])):
            raise core.SyncError(f"{header.service_name}/{language}: chapter counts differ")
        chapters = []
        for index, (entry, cat, d) in enumerate(
                zip(menu["menu"], catalog["menu"], detail["menu"])):
            if (not isinstance(entry, dict) or not isinstance(cat, dict)
                    or not isinstance(d, dict) or not isinstance(entry.get("level2"), list)):
                raise core.SyncError(f"{header.service_name}/{language}: invalid chapter {index + 1}")
            slug = cat.get("slug")
            title = entry.get("level1")
            if (not isinstance(slug, str) or not core.SLUG_RE.fullmatch(slug)
                    or cat.get("index") != index or cat.get("title") != title
                    or d.get("slug") != slug or d.get("title") != title):
                raise core.SyncError(f"{header.service_name}/{language}: chapter slug/title mismatch")
            children = d.get("childs")
            if not isinstance(children, list) or len(children) != len(entry["level2"]):
                raise core.SyncError(f"{header.service_name}/{language}: lesson count mismatch at {slug}")
            lessons = []
            for position, (label, child) in enumerate(zip(entry["level2"], children)):
                if not isinstance(child, dict):
                    raise core.SyncError(f"{header.service_name}/{language}: malformed lesson in {slug}")
                lesson_slug = f"{slug}-{position + 1:03d}"
                if child.get("slug") != lesson_slug or child.get("title") != label:
                    raise core.SyncError(f"{header.service_name}/{language}: lesson slug/title mismatch at {lesson_slug}")
                status = child.get("status")
                if not isinstance(status, str):
                    raise core.SyncError(f"{header.service_name}/{language}: invalid status at {lesson_slug}")
                difficult = child.get("difficult") or None
                if difficult is not None and difficult not in core.DIFFICULTIES:
                    raise core.SyncError(f"{header.service_name}/{language}: invalid difficulty at {lesson_slug}")
                # New EN imports require TRANSLATE, but pre-existing EN rows
                # (e.g. the preserved OOP translation) may have source WRITTEN.
                # Audit their Oracle WRITTEN status without treating those
                # already-synced rows as outdated. This does NOT relax import.
                ready_status = core.SOURCE_READY_STATUS.get(language, "WRITTEN")
                source_ready = status == ready_status or (language == "en" and status == "WRITTEN")
                lessons.append((lesson_slug, label, position,
                                "WRITTEN" if source_ready else "DRAFT", difficult))
            chapters.append((slug, title, index, lessons))
        locales.append((language, chapters))
    shape = [(slug, [lesson[0] for lesson in lessons]) for slug, _, _, lessons in locales[0][1]]
    if len({slug for slug, _ in shape}) != len(shape):
        raise core.SyncError(f"{header.service_name}: duplicate chapter slugs")
    for language, chapters in locales[1:]:
        other = [(slug, [lesson[0] for lesson in lessons]) for slug, _, _, lessons in chapters]
        if other != shape:
            raise core.SyncError(f"{header.service_name}/{language}: locale chapter/lesson slug hierarchy differs")
    return {
        "locales": locales,
        "chapters": len(shape),
        "lessons": sum(len(lessons) for _, _, _, lessons in locales[0][1]),
        "languages": len(locales),
    }


def read_database(connection: Any, prefix: str) -> dict[str, Any]:
    """Fetch compact identifiers/status, never download Knowledge content CLOBs."""
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT ID, SERVICE_NAME FROM {prefix}MODULE")
        modules: dict[str, int] = {}
        for mid, service in cursor:
            if service in modules:
                raise core.SyncError(f"Oracle contains duplicate SERVICE_NAME: {service}")
            modules[service] = int(mid)

        cursor.execute(
            f"SELECT ID, MODULE_ID, MENU_PARENT_ID, NODE_TYPE, SLUG, SORT_ORDER, IS_ACTIVE "
            f"FROM {prefix}MODULE_MENU"
        )
        chapter: dict[tuple[int, str], tuple[int, int, bool]] = {}
        section: dict[tuple[int, str], tuple[int, int, bool]] = {}
        for mid, module_id, parent_id, node_type, slug, order, active in cursor:
            if node_type == "CHAPTER" and module_id is not None:
                key = (int(module_id), slug)
                target = chapter
            elif node_type == "SECTION" and parent_id is not None:
                key = (int(parent_id), slug)
                target = section
            else:
                continue
            if key in target:
                raise core.SyncError(f"Duplicate Oracle menu key: {key}")
            target[key] = (int(mid), int(order), bool(active))

        cursor.execute(f"SELECT MENU_ID, LANGUAGE_CODE, TITLE FROM {prefix}MODULE_MENU_LANGUAGE")
        titles: dict[tuple[int, str], str] = {}
        for mid, lang, title in cursor:
            key = (int(mid), lang)
            if key in titles:
                raise core.SyncError(f"Duplicate Oracle menu translation: {key}")
            titles[key] = title

        cursor.execute(f"SELECT ID, MENU_ID, DIFFICULT, IS_ACTIVE FROM {prefix}MODULE_KNOWLEDGE")
        knowledge: dict[int, tuple[int, str | None, bool]] = {}
        for kid, menu_id, difficult, active in cursor:
            key = int(menu_id)
            if key in knowledge:
                raise core.SyncError(f"Duplicate Oracle Knowledge for Menu: {key}")
            knowledge[key] = (int(kid), difficult, bool(active))

        cursor.execute(
            f"SELECT KNOWLEDGE_ID, LANGUAGE_CODE, STATUS, DBMS_LOB.GETLENGTH(CONTENT) "
            f"FROM {prefix}MODULE_KNOWLEDGE_LANGUAGE"
        )
        translations: dict[tuple[int, str], tuple[str, int]] = {}
        for kid, lang, status, length in cursor:
            key = (int(kid), lang)
            if key in translations:
                raise core.SyncError(f"Duplicate Oracle Knowledge translation: {key}")
            translations[key] = (status, int(length or 0))

    return dict(modules=modules, chapters=chapter, sections=section,
                titles=titles, knowledge=knowledge, translations=translations)


def inspect_module(header: core.SourceHeader, source: dict[str, Any], db: dict[str, Any]) -> dict[str, Any] | None:
    module_id = db["modules"].get(header.service_name)
    if module_id is None:
        raise core.SyncError(f"Oracle MODULE missing for {header.service_name}")
    counts: Counter[str] = Counter()
    samples: dict[str, list[str]] = defaultdict(list)

    def record(issue: str, slug: str) -> None:
        counts[issue] += 1
        if len(samples[issue]) < SAMPLE_LIMIT:
            samples[issue].append(slug)

    existing = 0
    ready_chapters = {
        chapter_slug
        for _lang, chapters in source["locales"]
        for chapter_slug, _title, _order, lessons in chapters
        if any(lesson[3] == "WRITTEN" for lesson in lessons)
    }
    ready_sections = {
        (chapter_slug, lesson[0])
        for _lang, chapters in source["locales"]
        for chapter_slug, _title, _order, lessons in chapters
        for lesson in lessons if lesson[3] == "WRITTEN"
    }
    for lang, chapters in source["locales"]:
        for chapter_slug, chapter_title, ch_order, lessons in chapters:
            chapter = db["chapters"].get((module_id, chapter_slug))
            if chapter is None:
                if lang == source["locales"][0][0]:
                    record("chapters", chapter_slug)
                for lesson_slug, _, _, _, _ in lessons:
                    if lang == source["locales"][0][0]:
                        record("sections", f"{chapter_slug}/{lesson_slug}")
                        record("knowledge", f"{chapter_slug}/{lesson_slug}")
                    record("menu_languages", f"{lang}/{chapter_slug}/{lesson_slug}")
                    record("knowledge_languages", f"{lang}/{chapter_slug}/{lesson_slug}")
                record("menu_languages", f"{lang}/{chapter_slug}")
                continue
            ch_id, ch_sort, ch_active = chapter
            if lang == source["locales"][0][0]:
                existing += 1
                if ch_sort != ch_order:
                    record("menu_order", chapter_slug)
                if chapter_slug in ready_chapters and not ch_active:
                    record("activation", chapter_slug)
            ch_title = db["titles"].get((ch_id, lang))
            if ch_title is None:
                record("menu_languages", f"{lang}/{chapter_slug}")
            elif ch_title != chapter_title:
                record("menu_titles", f"{lang}/{chapter_slug}")
            for lesson_slug, lesson_title, ls_order, expected_status, difficult in lessons:
                label = f"{chapter_slug}/{lesson_slug}"
                section = db["sections"].get((ch_id, lesson_slug))
                if section is None:
                    if lang == source["locales"][0][0]:
                        record("sections", label)
                        record("knowledge", label)
                    record("menu_languages", f"{lang}/{label}")
                    record("knowledge_languages", f"{lang}/{label}")
                    continue
                section_id, sort, section_active = section
                if lang == source["locales"][0][0]:
                    existing += 1
                    if sort != ls_order:
                        record("menu_order", label)
                    if (chapter_slug, lesson_slug) in ready_sections and not section_active:
                        record("activation", label)
                title = db["titles"].get((section_id, lang))
                if title is None:
                    record("menu_languages", f"{lang}/{label}")
                elif title != lesson_title:
                    record("menu_titles", f"{lang}/{label}")
                knowledge = db["knowledge"].get(section_id)
                if knowledge is None:
                    if lang == source["locales"][0][0]:
                        record("knowledge", label)
                    record("knowledge_languages", f"{lang}/{label}")
                    continue
                knowledge_id, db_difficulty, knowledge_active = knowledge
                if lang == source["locales"][0][0] and difficult and db_difficulty != difficult:
                    record("difficulty", label)
                if (lang == source["locales"][0][0] and
                        (chapter_slug, lesson_slug) in ready_sections and not knowledge_active):
                    record("activation", f"Knowledge:{label}")
                translation = db["translations"].get((knowledge_id, lang))
                if translation is None:
                    record("knowledge_languages", f"{lang}/{label}")
                else:
                    db_status, content_length = translation
                    if db_status != expected_status:
                        record("knowledge_status", f"{lang}/{label}")
                    if expected_status == "WRITTEN" and content_length == 0:
                        record("empty_content", f"{lang}/{label}")

    if not counts:
        return None
    missing_keys = ISSUE_KEYS[:5]
    has_missing = any(counts[x] for x in missing_keys)
    state = "NOT_SYNCED" if existing == 0 else ("PARTIAL" if has_missing else "OUTDATED")
    return {
        "module": "module/" + header.path.relative_to(core.MODULE_ROOT).as_posix(),
        "serviceName": header.service_name,
        "moduleId": module_id,
        "state": state,
        "languages": list(header.languages),
        "expected": {
            "chapters": source["chapters"], "sections": source["lessons"],
            "menuLanguages": (source["chapters"] + source["lessons"]) * source["languages"],
            "knowledgeLanguages": source["lessons"] * source["languages"],
        },
        "missing": {key: int(counts[key]) for key in missing_keys},
        "mismatched": {key: int(counts[key]) for key in ISSUE_KEYS[5:]},
        "examples": {key: value for key, value in samples.items()},
    }


def write_report(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            yaml.safe_dump(payload, stream, allow_unicode=True, sort_keys=False,
                           default_flow_style=False, width=120)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", help="Optional single module, e.g. module/infrastructure/system/database/sql")
    parser.add_argument("--lang", action="append", help="Only selected language(s); default all source locales")
    args = parser.parse_args()
    try:
        if args.lang and (len(set(args.lang)) != len(args.lang) or
                          any(not core.LANGUAGE_RE.fullmatch(x) for x in args.lang)):
            raise core.SyncError("Invalid or duplicate --lang")
        paths = ([core.source_module_path(args.module)] if args.module
                 else core.discover_modules())
        headers = []
        errors = []
        seen: set[str] = set()
        for path in paths:
            try:
                h = core.read_source_header(path, tuple(args.lang) if args.lang else None)
                if h.service_name in seen:
                    raise core.SyncError(f"Duplicate SERVICE_NAME in source: {h.service_name}")
                seen.add(h.service_name)
                headers.append(h)
            except (core.SyncError, OSError, ValueError) as error:
                errors.append({"module": str(path), "error": str(error)})
        if not headers and not errors:
            raise core.SyncError("No modules with Knowledge source found")
        _, connection, prefix = core.connect_oracle()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
            db = read_database(connection, prefix)
            modules = []
            state_counts: Counter[str] = Counter()
            compared = 0
            for i, header in enumerate(headers, 1):
                try:
                    source = read_source_outline(header)
                    entry = inspect_module(header, source, db)
                    compared += 1
                    if entry is not None:
                        modules.append({key: entry[key] for key in (
                            "module", "serviceName", "moduleId", "languages")})
                        state_counts[entry["state"]] += 1
                except (core.SyncError, OSError, ValueError, TypeError, KeyError) as error:
                    errors.append({
                        "module": "module/" + header.path.relative_to(core.MODULE_ROOT).as_posix(),
                        "serviceName": header.service_name,
                        "error": str(error),
                    })
                if i % 100 == 0:
                    print(f"Checked {i}/{len(headers)} modules", flush=True)
        finally:
            connection.rollback()
            connection.close()
        modules.sort(key=lambda x: x["module"])
        payload = {
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "mode": "READ_ONLY_STRUCTURAL_CHECK",
            "note": ("Compares source Menu/Knowledge keys, titles, ordering, "
                     "lesson status and presence of published content. "
                     "Does not compare full Markdown text or optional QA metadata."),
            "summary": {
                "scanned": len(headers),
                "missingModules": len(modules),
                "notSynced": state_counts["NOT_SYNCED"],
                "partial": state_counts["PARTIAL"],
                "outdated": state_counts["OUTDATED"],
                "complete": compared - len(modules),
                "errors": len(errors),
            },
            "modules": modules,
            "errors": errors,
        }
        write_report(payload, REPORT)
        print(f"Report: {REPORT}")
        print("Summary:", payload["summary"])
        return 1 if errors else 0
    except Exception as error:
        print(f"REPORT_ERROR: {core.safe_oracle_error(error)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
