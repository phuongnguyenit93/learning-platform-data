#!/usr/bin/env python3
"""Overview sync: one Markdown CLOB per existing MODULE and language.

MERGE by (MODULE_ID, LANGUAGE_CODE). Preserve the Markdown line endings and
Unicode; empty/missing source is a SKIP, never a DELETE or content clearing.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _module_source_sync import (  # noqa: E402
    ModuleSource, SyncError, connect_oracle, discover_sources,
    print_problems, read_module_language_index, safe_oracle_error,
)


MERGE_OVERVIEW_SQL = """
MERGE INTO {prefix}MODULE_OVERVIEW dst
USING (
    SELECT :module_id MODULE_ID, :language_code LANGUAGE_CODE,
           :content CONTENT FROM DUAL
) src
ON (dst.MODULE_ID = src.MODULE_ID AND dst.LANGUAGE_CODE = src.LANGUAGE_CODE)
WHEN MATCHED THEN UPDATE SET dst.CONTENT = src.CONTENT
    WHERE DBMS_LOB.COMPARE(dst.CONTENT, src.CONTENT) <> 0
WHEN NOT MATCHED THEN INSERT (MODULE_ID, LANGUAGE_CODE, CONTENT)
    VALUES (src.MODULE_ID, src.LANGUAGE_CODE, src.CONTENT)
"""


def read_overview(path: Path) -> str | None:
    """Read without newline conversion; BOM is not part of Markdown."""
    try:
        content = path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise SyncError(f"Could not read Overview Markdown: {path} ({type(exc).__name__})") from exc
    if "\x00" in content:
        raise SyncError(f"Overview contains NUL byte: {path}")
    return content if content.strip() else None


def read_snapshot(connection: Any, prefix: str):
    modules, languages = read_module_language_index(connection, prefix)
    overviews: dict[tuple[int, str], str] = {}
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT MODULE_ID, LANGUAGE_CODE, CONTENT FROM {prefix}MODULE_OVERVIEW"
        )
        for module_id, language_code, content in cursor:
            # python-oracledb may yield a LOB locator or string depending on
            # the driver's fetch_lobs setting.
            if hasattr(content, "read"):
                content = content.read()
            overviews[(int(module_id), language_code)] = content
    return modules, languages, overviews


def plan_module(
    source: ModuleSource, content: str, lang: str,
    module_id: int, overviews: dict[tuple[int, str], str],
) -> str:
    key = (module_id, lang)
    if key not in overviews:
        return "insert"
    return "unchanged" if overviews[key] == content else "update"


def merge_module(
    driver: Any, connection: Any, prefix: str,
    module_id: int, content: str, lang: str,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT ID FROM {prefix}MODULE WHERE ID = :module_id FOR UPDATE",
            module_id=module_id,
        )
        if cursor.fetchone() is None:
            raise SyncError(f"Oracle MODULE.ID={module_id} disappeared before MERGE")
        cursor.setinputsizes(content=driver.DB_TYPE_CLOB)
        cursor.execute(
            MERGE_OVERVIEW_SQL.format(prefix=prefix),
            module_id=module_id, language_code=lang, content=content,
        )
    connection.commit()


def run(args: argparse.Namespace, *, single: bool) -> int:
    sources, missing, source_errors = discover_sources(
        args.lang, data_dir="base", filename="base.md",
        module_arg=args.module if single else None,
    )
    driver, connection, prefix = connect_oracle()
    try:
        modules, languages, overviews = read_snapshot(connection, prefix)
        if args.lang not in languages:
            raise SyncError(f"Language {args.lang!r} is not present in Oracle LANGUAGE")
        planned: list[tuple[ModuleSource, str, str]] = []
        unmatched: list[str] = []
        errors = list(source_errors)
        empty = 0
        for source in sources:
            module_id = modules.get(source.service_name)
            if module_id is None:
                unmatched.append(source.service_name)
                continue
            try:
                content = read_overview(source.data_path)
                if content is None:
                    empty += 1
                    continue
                action = plan_module(source, content, args.lang, module_id, overviews)
                planned.append((source, content, action))
            except SyncError as exc:
                errors.append(str(exc))

        counts: Counter[str] = Counter()
        committed = 0
        for source, content, action in planned:
            if args.apply and action != "unchanged":
                try:
                    merge_module(
                        driver, connection, prefix,
                        modules[source.service_name], content, args.lang,
                    )
                    committed += 1
                except Exception as exc:
                    connection.rollback()
                    errors.append(f"{source.service_name}: {safe_oracle_error(exc)}")
                    continue
            counts[action] += 1

        print(f"MODE={'APPLY' if args.apply else 'DRY_RUN'} LANG={args.lang}")
        print(
            f"MODULES sources={len(sources)} matched={len(planned)} "
            f"skipped_not_in_db={len(unmatched)} skipped_no_file={missing} "
            f"skipped_empty={empty} committed={committed} failed={len(errors)}"
        )
        print(
            f"OVERVIEW total={sum(counts.values())} "
            f"insert={counts['insert']} update={counts['update']} "
            f"unchanged={counts['unchanged']}"
        )
        print("POLICY MERGE INSERT/UPDATE only; no DELETE, no new MODULE")
        print_problems(errors=errors, unmatched=unmatched, entity="OVERVIEW")
        return 1 if errors else 0
    finally:
        connection.close()


def entrypoint(*, single: bool) -> int:
    parser = argparse.ArgumentParser(
        description="Sync base.md Overviews to existing Oracle MODULE rows using MERGE."
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
