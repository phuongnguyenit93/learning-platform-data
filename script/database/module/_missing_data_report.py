#!/usr/bin/env python3
"""Read-only Oracle checks for missing module Roadmap/Reference data.

The parent row is checked by MODULE_ID. A language is complete only when
every parent row for the module has a matching row in its LANGUAGE table.
If the parent row is absent, every language is also reported as missing.

Reports are written below script/database/module/<type>/report. Oracle is queried
with one SELECT statement per report type; this module never executes DML.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[4]
SHARED_DATABASE_HELPERS = REPO_ROOT / "learning-platform-data" / "script" / "database" / "module"
sys.path.insert(0, str(SHARED_DATABASE_HELPERS))
from _module_source_sync import connect_oracle, safe_oracle_error


LANGUAGE_RE = re.compile(r"[a-z][a-z0-9-]{0,9}\Z")
SERVICE_NAME_RE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*\Z")
SCHEMA_PREFIX_RE = re.compile(r"[A-Z][A-Z0-9_$#]*\.\Z")


@dataclass(frozen=True)
class ReportSpec:
    kind: str
    parent_table: str
    language_table: str
    language_parent_fk: str
    header_key: str
    detail_key: str


REPORT_SPECS = {
    "roadmap": ReportSpec(
        kind="roadmap",
        parent_table="MODULE_ROADMAP",
        language_table="MODULE_ROADMAP_LANGUAGE",
        language_parent_fk="ROADMAP_ID",
        header_key="missingRoadmap",
        detail_key="missingRoadmapDetail",
    ),
    "reference": ReportSpec(
        kind="reference",
        parent_table="MODULE_REFERENCE",
        language_table="MODULE_REFERENCE_LANGUAGE",
        language_parent_fk="REFERENCE_ID",
        header_key="missingReference",
        detail_key="missingReferenceDetail",
    ),
}


class ReportError(ValueError):
    """Invalid Oracle result or report configuration."""


def build_query(spec: ReportSpec, prefix: str) -> str:
    """Build one SELECT for parent presence and complete translation coverage."""
    if not SCHEMA_PREFIX_RE.fullmatch(prefix):
        raise ReportError("Invalid Oracle schema prefix")

    return f"""
WITH GROUP_PATHS AS (
    SELECT ID,
           LTRIM(SYS_CONNECT_BY_PATH(SLUG, '/'), '/') AS GROUP_PATH
    FROM {prefix}TOPIC_GROUP
    START WITH PARENT_GROUP_ID IS NULL
    CONNECT BY PRIOR ID = PARENT_GROUP_ID
),
MODULE_PATHS AS (
    SELECT TGM.MODULE_ID,
           C.CODE || '/' || T.SLUG ||
           CASE
               WHEN TGM.GROUP_ID IS NOT NULL AND GP.GROUP_PATH IS NOT NULL
                   THEN '/' || GP.GROUP_PATH
               ELSE ''
           END AS MODULE_PATH
    FROM {prefix}TOPIC_GROUP_MODULE TGM
    LEFT JOIN {prefix}TOPIC_GROUP TG ON TG.ID = TGM.GROUP_ID
    LEFT JOIN GROUP_PATHS GP ON GP.ID = TG.ID
    LEFT JOIN {prefix}TOPIC T
        ON T.ID = COALESCE(TGM.TOPIC_ID, TG.TOPIC_ID)
    LEFT JOIN {prefix}CATEGORY C ON C.ID = T.CATEGORY_ID
),
PARENT_COUNTS AS (
    SELECT MODULE_ID, COUNT(*) AS PARENT_COUNT
    FROM {prefix}{spec.parent_table}
    GROUP BY MODULE_ID
),
LANGUAGE_COUNTS AS (
    SELECT P.MODULE_ID,
           PL.LANGUAGE_CODE,
           COUNT(DISTINCT P.ID) AS TRANSLATED_COUNT
    FROM {prefix}{spec.parent_table} P
    JOIN {prefix}{spec.language_table} PL
        ON PL.{spec.language_parent_fk} = P.ID
    GROUP BY P.MODULE_ID, PL.LANGUAGE_CODE
)
SELECT M.SERVICE_NAME,
       MP.MODULE_PATH,
       L.CODE AS LANGUAGE_CODE,
       CASE
           WHEN NVL(PC.PARENT_COUNT, 0) = 0 THEN 1
           ELSE 0
       END AS MISSING_PARENT,
       CASE
           WHEN NVL(PC.PARENT_COUNT, 0) = 0 THEN 1
           WHEN NVL(LC.TRANSLATED_COUNT, 0) < PC.PARENT_COUNT THEN 1
           ELSE 0
       END AS MISSING_LANGUAGE
FROM {prefix}MODULE M
CROSS JOIN {prefix}LANGUAGE L
LEFT JOIN MODULE_PATHS MP ON MP.MODULE_ID = M.ID
LEFT JOIN PARENT_COUNTS PC ON PC.MODULE_ID = M.ID
LEFT JOIN LANGUAGE_COUNTS LC
    ON LC.MODULE_ID = M.ID AND LC.LANGUAGE_CODE = L.CODE
ORDER BY M.SERVICE_NAME, L.CODE
""".strip()


def build_documents(
    rows: Iterable[tuple[Any, Any, Any, Any, Any]], spec: ReportSpec,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Convert query rows into header/detail YAML documents.

    The SQL returns one row per MODULE x LANGUAGE. A detail is missing if at
    least one parent row has no translation for that language. This detects
    partially translated multi-row Roadmaps/References, not just zero rows.
    """
    modules: dict[str, dict[str, Any]] = {}
    languages_by_module: dict[str, set[str]] = {}
    detail_missing: dict[str, set[str]] = {}
    languages: set[str] = set()

    for raw in rows:
        if len(raw) != 5:
            raise ReportError("Oracle query returned an unexpected row shape")
        service_name, path, language, missing_parent, missing_language = raw
        if not isinstance(service_name, str) or not SERVICE_NAME_RE.fullmatch(service_name):
            raise ReportError("Oracle returned an invalid SERVICE_NAME")
        if not isinstance(language, str) or not LANGUAGE_RE.fullmatch(language):
            raise ReportError("Oracle returned an invalid LANGUAGE.CODE")
        if missing_parent not in (0, 1, False, True) or missing_language not in (0, 1, False, True):
            raise ReportError(f"Oracle returned invalid missing flags for {service_name}")

        normalized_path = path.strip() if isinstance(path, str) and path.strip() else None
        existing = modules.get(service_name)
        if existing is None:
            modules[service_name] = {
                "Path": normalized_path,
                "missing_parent": bool(missing_parent),
            }
        elif (
            existing["Path"] != normalized_path
            or existing["missing_parent"] != bool(missing_parent)
        ):
            raise ReportError(f"Inconsistent Oracle rows for {service_name}")

        languages.add(language)
        languages_by_module.setdefault(service_name, set()).add(language)
        if bool(missing_language):
            detail_missing.setdefault(language, set()).add(service_name)

    expected_languages = languages
    for service_name, actual_languages in languages_by_module.items():
        if actual_languages != expected_languages:
            raise ReportError(f"Incomplete language rows returned for {service_name}")

    header_items = [
        {
            "Module": name,
            "Path": modules[name]["Path"],
            spec.header_key: True,
        }
        for name in sorted(modules)
        if modules[name]["missing_parent"]
    ]
    documents: dict[str, dict[str, Any]] = {
        f"missing-{spec.kind}-header.yml": {spec.header_key: header_items}
    }

    for language in sorted(languages):
        missing_names = detail_missing.get(language, set())
        detail_items = [
            {
                "Module": name,
                "Path": modules[name]["Path"],
                spec.detail_key: True,
            }
            for name in sorted(missing_names)
        ]
        documents[f"missing-{spec.kind}-detail-{language}.yml"] = {
            spec.detail_key: detail_items
        }

    summary = {
        "modules": len(modules),
        "languages": sorted(languages),
        "missing_parent": len(header_items),
        "missing_detail": {
            language: len(detail_missing.get(language, set()))
            for language in sorted(languages)
        },
        "missing_path": sum(1 for item in modules.values() if item["Path"] is None),
    }
    return documents, summary


def write_documents(
    report_dir: Path, documents: dict[str, dict[str, Any]], kind: str,
) -> list[Path]:
    """Atomically write fresh YAML reports and remove stale language reports."""
    try:
        import yaml
    except ImportError as exc:
        raise ReportError("PyYAML is required: python -m pip install pyyaml") from exc

    report_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, document in documents.items():
        target = report_dir / filename
        payload = yaml.safe_dump(
            document,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=120,
        )
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=report_dir,
                prefix=f".{filename}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_path = Path(stream.name)
                stream.write(payload)
            os.replace(temporary_path, target)
            written.append(target)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    expected = set(documents)
    for stale in report_dir.glob(f"missing-{kind}-detail-*.yml"):
        if stale.name not in expected and stale.is_file() and not stale.is_symlink():
            stale.unlink()
    return written


def run(kind: str) -> int:
    try:
        spec = REPORT_SPECS[kind]
    except KeyError as exc:
        raise ReportError(f"Unsupported report type: {kind}") from exc

    _, connection, prefix = connect_oracle()
    try:
        with connection.cursor() as cursor:
            cursor.arraysize = 1000
            cursor.execute(build_query(spec, prefix))
            rows = cursor.fetchall()
    finally:
        connection.close()

    documents, summary = build_documents(rows, spec)
    report_dir = REPO_ROOT / "learning-platform-data" / "script" / "database" / "module" / kind / "report"
    written = write_documents(report_dir, documents, kind)

    print(f"MODE=READ_ONLY TYPE={kind}")
    print(
        f"MODULES={summary['modules']} LANGUAGES={','.join(summary['languages'])} "
        f"MISSING_PARENT={summary['missing_parent']} MISSING_PATH={summary['missing_path']}"
    )
    for language, count in summary["missing_detail"].items():
        print(f"MISSING_DETAIL.{language}={count}")
    print(f"REPORT_FILES={len(written)} REPORT_DIR={report_dir.relative_to(REPO_ROOT).as_posix()}")
    return 0


def entrypoint(kind: str, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=f"Generate read-only Oracle missing {kind} reports."
    )
    parser.parse_args(argv)
    try:
        return run(kind)
    except ReportError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"BLOCKED: {safe_oracle_error(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit("Run check_missing_roadmap.py or check_missing_reference.py instead.")
