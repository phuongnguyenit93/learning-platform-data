# Import Reference YAML into Oracle MODULE_REFERENCE

`script/database/all-module/import-module-references.py` reads the real module source tree:
`module/**/content/reference/<lang>/references.yml`. Each item becomes a
separate `MODULE_REFERENCE` row. It never scans generated output in
`build/learning-data/` or nested `build/`, `backup/`, vendor and cache folders.

## Prerequisites

Run `learning-platform-backend/sql/07_module_reference.sql` **manually** as
the Oracle schema owner after `03_module_structure.sql` and
`04_language.sql`. Backend schema generation is disabled: `ddl-auto=none`.

The import account needs SELECT on `MODULE_STRUCTURE` and `LANGUAGE`,
and SELECT/DELETE/INSERT on `MODULE_REFERENCE`. The importer uses
`SELECT ... FOR UPDATE` when applying to serialize imports: grant required
row-locking permissions on the referenced tables if using a separate account.
For a separate user, set `ORACLE_SCHEMA=LEARNING_PLATFORM`.
Do not use the backend's production read-only account for imports.

## Install and configure

```powershell
python -m pip install -r script/requirements-oracle-reference.txt
```

The default config is the same **Git-ignored**
`learning-platform-data/.env.oracle-overview` used by the existing
importers (`.env.oracle-overview` from this repository root).
A custom location is accepted using
`--env-file path/to/file`. Set `ORACLE_USER`, `ORACLE_PASSWORD`,
`ORACLE_DSN` and optionally `ORACLE_SCHEMA`. The DSN is the Python
oracledb Thin TLS descriptor (not JDBC); do not put credentials in logs.

## Commands

```powershell
# Validate source only; no Oracle connection:
python script/database/all-module/import-module-references.py --dry-run --offline

# Default: inspect Oracle and preview planned actions; SELECT only:
python script/database/all-module/import-module-references.py --dry-run

# Limit preview to one module/language:
python script/database/all-module/import-module-references.py --dry-run --module COLLABORATION_AZURE_DEVOPS --lang vi

# Explicitly apply to one module after reviewing the report:
python script/database/all-module/import-module-references.py --apply --module COLLABORATION_AZURE_DEVOPS --lang vi

# Explicitly import all eligible authored lists:
python script/database/all-module/import-module-references.py --apply
```

Options: `--module-root`, `--env-file`, `--report`, `--help`.
`--module` accepts the exact uppercase MODULE_STRUCTURE.NODE_KEY (not URL
slug). Unmatched explicit filters exit nonzero.

## Mapping and semantics

| YAML | Oracle |
| --- | --- |
| `master.json.SERVICE_NAME.VALUE` | Lookup `MODULE_STRUCTURE.ID_STRUCTURE` |
| `content/reference/vi/references.yml` | `LANGUAGE_CODE='vi'` |
| `references[*].title` | `TITLE` |
| `references[*].url` | `URL` |
| `references[*].description` (optional) | `DESCRIPTION` (NULL if empty) |
| Position in YAML array | `SORT_ORDER`, 1-based |
| Generated in Oracle | `ID_REFERENCE` |

**INSERT** when no existing rows, **REPLACE** when ordered values differ
(DELETE + batch INSERT for only that module/language), **UNCHANGED** when
identical (preserve IDs), **SKIP_EMPTY** for skeletons/empty files (never
delete Oracle content), and **SKIP** for missing module, GROUP or
missing/inactive language.

All actionable changes run in **one transaction** and roll back on error.
Before replacement, the script locks/checks the module, language and rows.
Do not run independent DB writers concurrently with an import.

There is no business key or UNIQUE(URL). The same URL can appear in VI and
EN with different titles/descriptions. REPLACE regenerates ID_REFERENCE;
avoid durable external references to these IDs unless design changes.

Validation: `title` and `url` required, `description` optional. URLs must
be absolute HTTPS with hostname, no username/password, whitespace or control
characters. Column character limits: TITLE 300, URL 2000, DESCRIPTION 1000;
each value is also checked against 4000 UTF-8 bytes for default Oracle
MAX_STRING_SIZE=STANDARD. SQL uses bind parameters.

Default report: `build/reports/module-reference-import.json`; contains
statuses, counts, relative source paths and SHA-256, no content/secrets.
Offline `READY_LOCAL_ONLY` does not imply Oracle data exists.

## Tests

```powershell
python -m unittest script/tests/test_import_module_references.py -v
```

Tests mock database operations; no test writes to a live Oracle database.
