#!/usr/bin/env python3
"""Independent, non-destructive sync of five localized Knowledge QA fields.

Never inserts MODULE/MENU/KNOWLEDGE or language rows, and never writes lesson
content, status, difficulty, titles, activation or any other columns.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys
from typing import Any

import _knowledge_menu_sync as core


FIELDS = ("focus", "problem_solved", "mechanism", "application_value", "summary")
COLUMNS = ("FOCUS", "PROBLEM_SOLVED", "MECHANISM", "APPLICATION_VALUE", "SUMMARY")
BATCH_SIZE = 100


def read_metadata_rows(connection: Any, prefix: str, module_id: int) -> dict[tuple[str, str, str], tuple[int, tuple]]:
    """Existing translations only, with stable chapter/section slug ownership."""
    result: dict[tuple[str, str, str], tuple[int, tuple]] = {}
    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT chapter.SLUG, section.SLUG, k.ID, t.LANGUAGE_CODE,
                   t.FOCUS, t.PROBLEM_SOLVED, t.MECHANISM, t.APPLICATION_VALUE,
                   t.SUMMARY
            FROM {prefix}MODULE_MENU chapter
            JOIN {prefix}MODULE_MENU section
              ON section.MENU_PARENT_ID = chapter.ID AND section.NODE_TYPE = 'SECTION'
            JOIN {prefix}MODULE_KNOWLEDGE k ON k.MENU_ID = section.ID
            JOIN {prefix}MODULE_KNOWLEDGE_LANGUAGE t ON t.KNOWLEDGE_ID = k.ID
            WHERE chapter.MODULE_ID = :module_id AND chapter.NODE_TYPE = 'CHAPTER'
            """, module_id=module_id)
        for chapter, section, knowledge_id, lang, focus, problem, mechanism, application, summary in cursor:
            key = (chapter, section, lang)
            if key in result:
                raise core.SyncError(f"Duplicate Oracle metadata translation for {key}")
            result[key] = (int(knowledge_id),
                           (focus, problem, mechanism, application, core._lob(summary)))
    return result


def plan_metadata(driver: Any, cursor: Any, prefix: str, source: core.SourceModule,
                  rows: dict[tuple[str, str, str], tuple[int, tuple]], *, apply: bool = False) -> Counter[str]:
    """Plan/update only nonblank source QA values; preserve blanks and all other columns."""
    counts: Counter[str] = Counter()
    batches: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for locale in source.locales:
        for chapter in locale.chapters:
            for lesson in chapter.lessons:
                key = (chapter.slug, lesson.slug, locale.language)
                existing = rows.get(key)
                if existing is None:
                    counts["missing_translation"] += 1
                    continue
                knowledge_id, previous = existing
                incoming = tuple(getattr(lesson, field) for field in FIELDS)
                updates = {column: value for column, old, value in zip(COLUMNS, previous, incoming)
                           if value is not None and old != value}
                if not updates:
                    if all(value is None for value in incoming):
                        counts["empty_source_preserved"] += 1
                    else:
                        counts["unchanged"] += 1
                    continue
                counts["updated_rows"] += 1
                counts["updated_fields"] += len(updates)
                if apply:
                    # Each SQL statement must bind exactly the fields being changed.
                    columns = tuple(updates)
                    batches.setdefault(columns, []).append({
                        **{name.lower(): value for name, value in updates.items()},
                        "knowledge_id": knowledge_id,
                        "language": locale.language,
                    })
                rows[key] = (knowledge_id, tuple(updates.get(col, old)
                                                  for col, old in zip(COLUMNS, previous)))

    if apply:
        # Array DML is grouped by changed columns so absent/blank source fields
        # never overwrite existing Oracle values. A caller commits once per module.
        for columns, bindings in batches.items():
            assignments = ", ".join(f"{column} = :{column.lower()}" for column in columns)
            sql = (f"UPDATE {prefix}MODULE_KNOWLEDGE_LANGUAGE SET {assignments} "
                   "WHERE KNOWLEDGE_ID = :knowledge_id AND LANGUAGE_CODE = :language")
            for start in range(0, len(bindings), BATCH_SIZE):
                chunk = bindings[start:start + BATCH_SIZE]
                if "SUMMARY" in columns:
                    cursor.setinputsizes(summary=driver.DB_TYPE_CLOB)
                cursor.executemany(sql, chunk)
                if cursor.rowcount != len(chunk):
                    raise core.SyncError(
                        f"Knowledge metadata batch affected {cursor.rowcount} rows "
                        f"instead of {len(chunk)}; rolling back the module")
    return counts


def _import_one(driver: Any, connection: Any, prefix: str, source: core.SourceModule,
                supported: dict[str, bool], *, apply: bool) -> Counter[str]:
    core._ensure_db_languages(source, supported)
    module_id = core.find_module_id(connection, prefix, source.service_name)
    if module_id is None:
        raise core.SyncError(f"No Oracle MODULE for SERVICE_NAME {source.service_name}")
    if apply:
        with connection.cursor() as cursor:
            core._lock_module(connection, prefix, module_id)
            rows = read_metadata_rows(connection, prefix, module_id)
            result = plan_metadata(driver, cursor, prefix, source, rows, apply=True)
        connection.commit()
        return result
    rows = read_metadata_rows(connection, prefix, module_id)
    return plan_metadata(driver, None, prefix, source, rows, apply=False)


def run(args: argparse.Namespace, *, single: bool) -> int:
    languages = tuple(args.lang) if args.lang else None
    paths = ([core.source_module_path(args.module)] if single else core.discover_modules())
    headers: list[core.SourceHeader] = []
    errors: list[str] = []
    seen: dict[str, Path] = {}
    conflicts: set[str] = set()
    for path in paths:
        try:
            header = core.read_source_header(path, languages)
            if header.service_name in conflicts:
                raise core.SyncError(f"Repeated SERVICE_NAME blocked: {header.service_name}")
            if header.service_name in seen:
                headers = [item for item in headers if item.service_name != header.service_name]
                conflicts.add(header.service_name)
                raise core.SyncError(f"Duplicate SERVICE_NAME {header.service_name}: "
                                     f"{seen[header.service_name]} and {path}")
            seen[header.service_name] = path
            headers.append(header)
        except (core.SyncError, OSError, ValueError) as exc:
            errors.append(str(exc))

    updated_modules = 0
    totals: Counter[str] = Counter()
    if args.offline:
        for header in headers:
            try:
                source = core.load_module(header.path, header.languages, include_metadata=True)
                populated = sum(bool(getattr(lesson, field)) for locale in source.locales
                                for chapter in locale.chapters for lesson in chapter.lessons
                                for field in FIELDS)
                total = sum(len(chapter.lessons) for locale in source.locales
                            for chapter in locale.chapters) * len(FIELDS)
                print(f"OFFLINE_METADATA {header.service_name} "
                      f"langs={','.join(header.languages)} populated_fields={populated}/{total}")
            except (core.SyncError, OSError, ValueError) as exc:
                errors.append(str(exc))
    elif headers:
        driver, connection, prefix = core.connect_oracle()
        try:
            supported = core.read_languages(connection, prefix)
            for header in headers:
                try:
                    source = core.load_module(header.path, header.languages, include_metadata=True)
                    counts = _import_one(driver, connection, prefix, source,
                                         supported, apply=args.apply)
                    totals.update(counts)
                    if args.apply and counts["updated_rows"]:
                        updated_modules += 1
                    print(f"{'APPLIED' if args.apply else 'DRY_RUN'}_METADATA "
                          f"{header.service_name} langs={','.join(header.languages)} "
                          f"updates={counts['updated_rows']} fields={counts['updated_fields']} "
                          f"empty_preserved={counts['empty_source_preserved']} "
                          f"missing_rows={counts['missing_translation']}")
                except Exception as exc:
                    connection.rollback()
                    errors.append(f"{header.service_name}: " + (
                        str(exc) if isinstance(exc, core.SyncError) else core.safe_oracle_error(exc)))
            if not args.apply:
                connection.rollback()
        finally:
            connection.close()
    print(f"MODE={'OFFLINE' if args.offline else 'APPLY' if args.apply else 'DRY_RUN'} "
          f"metadata_modules={len(headers)} changed_modules={updated_modules} "
          f"updated_rows={totals['updated_rows']} missing_rows={totals['missing_translation']} "
          f"errors={len(errors)}; POLICY update five nonblank metadata fields only, no INSERT/DELETE")
    for error in errors[:20]:
        print(f"KNOWLEDGE_METADATA_ERROR: {error}", file=sys.stderr)
    return 1 if errors else 0


def entrypoint(*, single: bool) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    if single:
        parser.add_argument("--module", required=True,
                            help="Repository-relative module path starting with module/")
    parser.add_argument("--lang", action="append", metavar="CODE",
                        help="Import selected locale(s); default all available")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Read-only Oracle diff (default)")
    mode.add_argument("--offline", action="store_true", help="Validate source; no Oracle connection")
    mode.add_argument("--apply", action="store_true", help="Update existing metadata rows explicitly")
    args = parser.parse_args()
    try:
        if args.lang and any(not core.LANGUAGE_RE.fullmatch(lang) or len(lang) > 10
                             for lang in args.lang):
            raise core.SyncError("Invalid --lang: expected lowercase language code")
        return run(args, single=single)
    except (core.SyncError, OSError, ValueError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"BLOCKED: {core.safe_oracle_error(exc)}", file=sys.stderr)
        return 1
