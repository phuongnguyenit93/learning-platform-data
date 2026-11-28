# Import `BASE.md` into Oracle `MODULE_OVERVIEW`

The script `script/database/all-module/import-module-overviews.py` scans the **source** tree under
`module/`, reads `master.json.SERVICE_NAME.VALUE` as the stable `NODE_KEY`, and
imports the raw `content/readme/docs/<language>/BASE.md` Markdown. It never
imports copies under `build/`, `backup/`, `src/`, or output folders.

**Prerequisites:** `MODULE_STRUCTURE`, the shared `LANGUAGE` table (containing
`vi`/`en`), and `MODULE_OVERVIEW` must already exist in Oracle. The DDL for the
last two is in `learning-platform-backend/sql/04_language.sql` and
`learning-platform-backend/sql/05_module_overview.sql`. Structure rows are
imported separately; this script never creates them.

## Installation (Windows PowerShell)

```powershell
python -m pip install -r script/requirements-oracle-overview.txt
Copy-Item script/oracle-overview.env.example .env.oracle-overview
```

Edit the **untracked** `learning-platform-data/.env.oracle-overview` file
(the root of this data repository, if running the commands above):

```dotenv
ORACLE_USER=LEARNING_PLATFORM
ORACLE_PASSWORD=your-password
ORACLE_DSN=(description=(address=(protocol=tcps)(port=1521)(host=your-adb-host.oraclecloud.com))(connect_data=(service_name=your_db_low.adb.oraclecloud.com))(security=(ssl_server_dn_match=yes)))
```

Copy the actual **TLS** connection descriptor from Oracle Autonomous Database
Console > Database Connection, not a JDBC URL. Python-oracledb uses Thin mode by
default (no Instant Client/wallet required for TLS). The machine running the
import must be allowed by Oracle's network access list and have outbound TCP
access to the ADB port. Don't paste passwords into commands, reports, commits,
or logs. The existing `.gitignore` ignores `.env.*`.

When connecting with a *separate* import user, set `ORACLE_SCHEMA=LEARNING_PLATFORM`
and grant it `SELECT` on the schema owner's `MODULE_STRUCTURE` and `LANGUAGE`, and
`SELECT`, `INSERT`, `UPDATE` on `MODULE_OVERVIEW`. Avoid using the application's
read-only user or the privileged `ADMIN` user for imports. Importing does **not**
require DELETE rights. If process environment variables are set, they take
precedence over file values. You can also specify `--env-file path/to/file`.

## Running

```powershell
# Reads Oracle to preview INSERT, UPDATE, and SKIP; does not write to Oracle:
python script/database/all-module/import-module-overviews.py --dry-run

# Explicit write operation; processes all rows in one transaction:
python script/database/all-module/import-module-overviews.py --apply

# Offline local file inventory (no credentials, no database connection):
python script/database/all-module/import-module-overviews.py --dry-run --offline

# Other options:
python script/database/all-module/import-module-overviews.py --help
```

`DRY_RUN` is the default even without a flag; it checks Oracle structure and
language existence and reports intended actions. `--offline` only checks local
sources; `READY_LOCAL_ONLY` **does not** mean the matching database row exists.
`--apply` is the **only** operation that issues `MERGE` and `COMMIT`; a DB error
rolls back the whole batch.

Each execution writes a JSON report (no content or secrets) to
`build/reports/module-overview-import.json`, including `INSERT`, `UPDATE`,
`SKIP_EMPTY`, `SKIP_MISSING_MODULE`, `SKIP_NOT_MODULE`, and
`SKIP_MISSING_OR_INACTIVE_LANGUAGE`. The report includes file paths,
character counts, and SHA-256 hashes but **not** the Markdown itself.

Mapping rules and safety:

- `NODE_KEY` comes **only** from the module's `master.json.SERVICE_NAME.VALUE`;
  `ID_STRUCTURE` is looked up in Oracle and never hardcoded.
- Empty `BASE.md` files are skipped. Missing translations are not fabricated.
- If the `MODULE_STRUCTURE` row or `LANGUAGE` row does not exist, it is a normal
  `SKIP`, not an error; the import can be rerun after the missing row is added.
- Duplicate `(NODE_KEY, language)` sources or invalid/missing `SERVICE_NAME`
  block the entire import to prevent silently writing an incorrect module.
- `MERGE` matches `(ID_STRUCTURE, LANGUAGE_CODE)`. Matching rows are updated,
  missing Overview rows inserted, and a missing `MODULE_STRUCTURE` source row
  yields 0 affected rows without raising an error.
- Markdown is stored via a bound **CLOB**, not concatenated into SQL text: it
  preserves Unicode, apostrophes, links, and line endings and avoids Oracle's
  SQL string literal length limits. The importer does not trim the content.
- The script does **not** modify source files, `MODULE_STRUCTURE`, or `LANGUAGE`.

To check imported counts in Oracle:

```sql
SELECT LANGUAGE_CODE, COUNT(*) AS TOTAL
FROM MODULE_OVERVIEW
GROUP BY LANGUAGE_CODE
ORDER BY LANGUAGE_CODE;
```

For a functional read check after a successful import:

```http
GET /api/v1/modules/java-stream-api/overview?lang=vi
```
