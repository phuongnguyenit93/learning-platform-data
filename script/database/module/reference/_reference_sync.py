#!/usr/bin/env python3
"""Reference sync: existing MODULE -> MODULE_REFERENCE -> translated rows.

One-way, idempotent INSERT/UPDATE via Oracle MERGE. No DELETE, no MODULE insert.
URLs (per module) are identity keys; changing a URL inserts a new Reference.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _module_source_sync import (  # noqa: E402
    ModuleSource, SyncError, connect_oracle, discover_sources,
    print_problems, read_module_language_index, safe_oracle_error, validate_text,
)


@dataclass(frozen=True)
class ReferenceEntry:
    url: str
    title: str
    description: str | None
    sort_order: int


@dataclass(frozen=True)
class ReferenceRow:
    id: int
    sort_order: int


@dataclass
class Snapshot:
    modules: dict[str, int]
    languages: set[str]
    references: dict[tuple[int, str], ReferenceRow]
    translations: dict[tuple[int, str], tuple[str, str | None]]
    translated_languages: dict[int, set[str]]


MERGE_REFERENCE_SQL = """
MERGE INTO {prefix}MODULE_REFERENCE dst
USING (
    SELECT :module_id MODULE_ID, :reference_url URL,
           :sort_order SORT_ORDER FROM DUAL
) src
ON (dst.MODULE_ID = src.MODULE_ID AND dst.URL = src.URL)
WHEN MATCHED THEN UPDATE SET dst.SORT_ORDER = src.SORT_ORDER
    WHERE dst.SORT_ORDER <> src.SORT_ORDER
WHEN NOT MATCHED THEN INSERT (MODULE_ID, URL, SORT_ORDER)
    VALUES (src.MODULE_ID, src.URL, src.SORT_ORDER)
"""

MERGE_REFERENCE_LANGUAGE_SQL = """
MERGE INTO {prefix}MODULE_REFERENCE_LANGUAGE dst
USING (
    SELECT ref.ID REFERENCE_ID, :language_code LANGUAGE_CODE,
           :title TITLE, :description DESCRIPTION
    FROM {prefix}MODULE_REFERENCE ref
    WHERE ref.MODULE_ID = :module_id AND ref.URL = :reference_url
) src
ON (dst.REFERENCE_ID = src.REFERENCE_ID AND dst.LANGUAGE_CODE = src.LANGUAGE_CODE)
WHEN MATCHED THEN UPDATE SET
    dst.TITLE = src.TITLE, dst.DESCRIPTION = src.DESCRIPTION
    WHERE DECODE(dst.TITLE, src.TITLE, 0, 1) = 1
       OR DECODE(dst.DESCRIPTION, src.DESCRIPTION, 0, 1) = 1
WHEN NOT MATCHED THEN INSERT (
    REFERENCE_ID, LANGUAGE_CODE, TITLE, DESCRIPTION
) VALUES (
    src.REFERENCE_ID, src.LANGUAGE_CODE, src.TITLE, src.DESCRIPTION
)
"""


def read_references(path: Path) -> tuple[ReferenceEntry, ...]:
    try:
        import yaml
    except ImportError as exc:
        raise SyncError("Missing PyYAML: python -m pip install pyyaml") from exc
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise SyncError(f"Invalid Reference YAML: {path} ({type(exc).__name__})") from exc
    if not isinstance(document, dict) or not isinstance(document.get("references"), list):
        raise SyncError(f"{path}: 'references' must be a list")
    result: list[ReferenceEntry] = []
    seen: set[str] = set()
    for index, row in enumerate(document["references"], 1):
        context = f"{path}: references[{index}]"
        if not isinstance(row, dict):
            raise SyncError(f"{context}: expected mapping")
        title = validate_text(row.get("title"), limit=300, context=context + ".title")
        url = validate_text(row.get("url"), limit=2000, context=context + ".url")
        assert isinstance(title, str) and isinstance(url, str)
        if row["url"] != url or re.search(r"[\s\x00-\x1f\x7f]", url):
            raise SyncError(f"{context}: URL must not include whitespace/control characters")
        try:
            parsed = urlsplit(url)
            valid = (
                parsed.scheme == "https" and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None
            )
        except ValueError:
            valid = False
        if not valid:
            raise SyncError(f"{context}: expected absolute HTTPS URL without credentials")
        if url in seen:
            raise SyncError(f"{context}: duplicate URL within this module/language: {url}")
        seen.add(url)
        description = validate_text(
            row.get("description"), limit=1000, context=context + ".description",
            required=False,
        )
        result.append(ReferenceEntry(url, title, description, index))
    return tuple(result)


def read_snapshot(connection: Any, prefix: str) -> Snapshot:
    modules, languages = read_module_language_index(connection, prefix)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT ID, MODULE_ID, URL, SORT_ORDER FROM {prefix}MODULE_REFERENCE")
        refs: dict[tuple[int, str], ReferenceRow] = {}
        for id_, module_id, url, sort_order in cursor:
            key = (int(module_id), url)
            if key in refs:
                raise SyncError(
                    "Oracle MODULE_REFERENCE contains duplicate (MODULE_ID, URL); "
                    "resolve duplicates before syncing"
                )
            refs[key] = ReferenceRow(int(id_), int(sort_order))

        cursor.execute(
            f"SELECT REFERENCE_ID, LANGUAGE_CODE, TITLE, DESCRIPTION "
            f"FROM {prefix}MODULE_REFERENCE_LANGUAGE"
        )
        translated: dict[tuple[int, str], tuple[str, str | None]] = {}
        languages_by_ref: dict[int, set[str]] = defaultdict(set)
        for ref_id, lang, title, description in cursor:
            translated[(int(ref_id), lang)] = (title, description)
            languages_by_ref[int(ref_id)].add(lang)
    return Snapshot(modules, languages, refs, translated, dict(languages_by_ref))


def plan_module(
    source: ModuleSource, entries: tuple[ReferenceEntry, ...],
    lang: str, snapshot: Snapshot,
) -> Counter[str]:
    module_id = snapshot.modules[source.service_name]
    counts: Counter[str] = Counter()
    for item in entries:
        previous = snapshot.references.get((module_id, item.url))
        if previous is None:
            counts["reference_insert"] += 1
            counts["translation_insert"] += 1
            continue
        if previous.sort_order != item.sort_order:
            others = snapshot.translated_languages.get(previous.id, set()) - {lang}
            if others:
                raise SyncError(
                    f"{source.data_path}: URL {item.url} changes shared SORT_ORDER "
                    f"but another language exists ({', '.join(sorted(others))})"
                )
            counts["reference_update"] += 1
        else:
            counts["reference_unchanged"] += 1
        old_translation = snapshot.translations.get((previous.id, lang))
        if old_translation is None:
            counts["translation_insert"] += 1
        elif old_translation != (item.title, item.description):
            counts["translation_update"] += 1
        else:
            counts["translation_unchanged"] += 1
    counts["references"] += len(entries)
    return counts


def merge_module(
    connection: Any, prefix: str, module_id: int,
    entries: tuple[ReferenceEntry, ...], lang: str,
) -> None:
    with connection.cursor() as cursor:
        # Serializes this script's concurrent imports for one module. The
        # reference table has no UNIQUE(MODULE_ID,URL), so external writers
        # still need to use the same lock or add a unique constraint.
        cursor.execute(
            f"SELECT ID FROM {prefix}MODULE WHERE ID = :module_id FOR UPDATE",
            module_id=module_id,
        )
        if cursor.fetchone() is None:
            raise SyncError(f"Oracle MODULE.ID={module_id} disappeared before MERGE")
        cursor.execute(
            f"SELECT URL, COUNT(*) FROM {prefix}MODULE_REFERENCE "
            f"WHERE MODULE_ID = :module_id GROUP BY URL HAVING COUNT(*) > 1",
            module_id=module_id,
        )
        if cursor.fetchone() is not None:
            raise SyncError(f"Duplicate Reference URLs in Oracle MODULE.ID={module_id}")
        for item in entries:
            cursor.execute(
                MERGE_REFERENCE_SQL.format(prefix=prefix),
                module_id=module_id, reference_url=item.url, sort_order=item.sort_order,
            )
            cursor.execute(
                MERGE_REFERENCE_LANGUAGE_SQL.format(prefix=prefix),
                module_id=module_id, reference_url=item.url, language_code=lang,
                title=item.title, description=item.description,
            )
    connection.commit()


def run(args: argparse.Namespace, *, single: bool) -> int:
    sources, missing, source_errors = discover_sources(
        args.lang, data_dir="reference", filename="references.yml",
        module_arg=args.module if single else None,
    )
    _, connection, prefix = connect_oracle()
    try:
        snapshot = read_snapshot(connection, prefix)
        if args.lang not in snapshot.languages:
            raise SyncError(f"Language {args.lang!r} is not present in Oracle LANGUAGE")
        planned: list[tuple[ModuleSource, tuple[ReferenceEntry, ...], Counter[str]]] = []
        unmatched: list[str] = []
        errors = list(source_errors)
        empty = 0
        for source in sources:
            if source.service_name not in snapshot.modules:
                unmatched.append(source.service_name)
                continue
            try:
                entries = read_references(source.data_path)
                if not entries:
                    empty += 1
                    continue
                diff = plan_module(source, entries, args.lang, snapshot)
                planned.append((source, entries, diff))
            except SyncError as exc:
                errors.append(str(exc))

        counts: Counter[str] = Counter()
        committed = 0
        unchanged_modules = 0
        for source, entries, diff in planned:
            changes = sum(diff[k] for k in (
                "reference_insert", "reference_update",
                "translation_insert", "translation_update",
            ))
            if args.apply and changes:
                try:
                    merge_module(
                        connection, prefix, snapshot.modules[source.service_name],
                        entries, args.lang,
                    )
                    committed += 1
                except Exception as exc:
                    connection.rollback()
                    errors.append(f"{source.service_name}: {safe_oracle_error(exc)}")
                    continue
            elif not changes:
                unchanged_modules += 1
            counts.update(diff)

        print(f"MODE={'APPLY' if args.apply else 'DRY_RUN'} LANG={args.lang}")
        print(
            f"MODULES sources={len(sources)} matched={len(planned)} "
            f"skipped_not_in_db={len(unmatched)} skipped_no_file={missing} "
            f"skipped_empty={empty} committed={committed} "
            f"unchanged={unchanged_modules} failed={len(errors)}"
        )
        print(
            f"REFERENCE total={counts['references']} insert={counts['reference_insert']} "
            f"update={counts['reference_update']} unchanged={counts['reference_unchanged']}"
        )
        print(
            f"LANGUAGE insert={counts['translation_insert']} "
            f"update={counts['translation_update']} unchanged={counts['translation_unchanged']}"
        )
        print("POLICY MERGE INSERT/UPDATE only; no DELETE, no new MODULE")
        print_problems(errors=errors, unmatched=unmatched, entity="REFERENCE")
        return 1 if errors else 0
    finally:
        connection.close()


def entrypoint(*, single: bool) -> int:
    parser = argparse.ArgumentParser(
        description="Sync module references to existing Oracle MODULE rows using MERGE."
    )
    if single:
        parser.add_argument(
            "--module", required=True,
            help="Repository-relative module path, e.g. module/infrastructure/cloud/architecture",
        )
    parser.add_argument("--lang", default="vi", help="Language code (default vi)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview only (default)")
    mode.add_argument("--apply", action="store_true", help="MERGE changes into Oracle")
    args = parser.parse_args()
    try:
        return run(args, single=single)
    except (SyncError, OSError, ValueError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"BLOCKED: {safe_oracle_error(exc)}", file=sys.stderr)
        return 1
