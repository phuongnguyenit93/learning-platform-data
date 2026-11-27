# Oracle Menu/Knowledge importer

## Find modules with missing or incomplete Oracle Knowledge

Run from the `java-learning` root:

```powershell
python -B script/database/module/knowledge/get-missing-knowledge-module.py
```

This is **read-only against Oracle**; it writes only
`script/database/module/knowledge/report/missing-knowledge.yml` (UTF-8).
It discovers modules with Knowledge source and compares Chapter/Section slugs,
localized Menu titles, Knowledge rows/translations, lesson status and presence
of published content, plus required activation flags. The report includes:

- `NOT_SYNCED`: no matching source Chapter/Section exists in Oracle.
- `PARTIAL`: some expected Menu/Knowledge or language rows are missing.
- `OUTDATED`: all expected rows exist, but order, title, status or other
  checked fields do not match.
- `errors`: sources or Oracle modules that could not be compared safely.

Each item in `modules` contains only `module`, `serviceName`, `moduleId`,
and `languages`. The overall status counts remain in `summary`, and
`summary.complete` counts the modules that passed. For one module, pass
`--module module/infrastructure/system/database/sql`, or use repeatable
`--lang vi` / `--lang en` to limit the language scope.

The scan is intentionally lightweight: it **does not** fetch/compare complete
Markdown content or the five optional QA metadata fields. A module with
updated Markdown of the same status can pass this check. Use the default
`sync-menu-knowledge-*.py` dry-run to verify exact content differences, and
`sync-knowledge-metadata-*.py` for separate QA metadata updates.

The importer reads a module's `module-info.json` and
`content/knowledge/<lang>/menu.yml`, `menu-level-1-slug.yml`,
`menu-detail-status.yml`, plus every lesson's `.yml` and `.md` files.
It targets only existing `MODULE` rows and the schema in backend SQL 17–20.

From the `java-learning` root:

```powershell
# Validate local source; NO Oracle connection or writes.
python -B script/database/module/knowledge/sync-menu-knowledge-single.py --module module/platform/development/programming/paradigm/object-oriented --offline

# Default: compare source to Oracle with SELECT only; NO writes.
python -B script/database/module/knowledge/sync-menu-knowledge-single.py --module module/platform/development/programming/paradigm/object-oriented

# Explicitly choose only locales to import (otherwise all available locales).
python -B script/database/module/knowledge/sync-menu-knowledge-single.py --module module/platform/development/programming/paradigm/object-oriented --lang vi --lang en

# Preview all modules with available Knowledge source.
python -B script/database/module/knowledge/sync-menu-knowledge-all.py

# ONLY after reviewing dry-run and authorizing a database update:
python -B script/database/module/knowledge/sync-menu-knowledge-single.py --module module/platform/development/programming/paradigm/object-oriented --apply

# Ignore the unchanged checkpoint and verify/reconcile the database again.
python -B script/database/module/knowledge/sync-menu-knowledge-single.py --module module/platform/development/programming/paradigm/object-oriented --apply --no-skip-unchanged
# --force is an alias for --no-skip-unchanged.

# Independently preview/fill the FIVE optional lesson metadata fields later.
# These never insert missing Menu/Knowledge rows and never change content/status.
python -B script/database/module/knowledge/sync-knowledge-metadata-single.py --module module/platform/development/programming/paradigm/object-oriented
python -B script/database/module/knowledge/sync-knowledge-metadata-all.py --lang vi

# Explicitly update metadata after reviewing its own dry-run:
python -B script/database/module/knowledge/sync-knowledge-metadata-single.py --module module/platform/development/programming/paradigm/object-oriented --apply
```

The Oracle connection is supplied by `script/database/connect-oracle-db.py`
and its existing environment configuration. The scripts never print credentials.
Both default dry-run and `--offline` perform **zero SQL writes**. `--apply`
locks the existing `MODULE` row, refreshes its snapshot, and commits the
Chapter, Section, Knowledge and translation updates together per module;
failures roll back that module. The all-module variant commits one module at
a time. Missing original rows and translations are never deleted or pruned;
stale rows are counted and retained. Existing IDs and unselected translations
are preserved. A change in generated lesson slug can create a new Section
while leaving the old one; review slug/order changes before applying.

**Batch writes:** `--apply` uses `cursor.executemany()` in groups of up to
**100 rows** (including Markdown CLOBs), first creating Chapters, then
Sections, then Knowledge records and localized translations. Generated IDs
are read back by their scoped slug/parent keys between dependency phases.
Changed rows alone are written; unchanged rows are not resent. **No batch
commits independently**: a single Module transaction commits once after all
batches have succeeded, or the caller rolls back the entire Module on failure.
Dry-run still computes the complete row-level diff without modifying Oracle.

Chapter slug identity is `(moduleId, slug)`, Section is `(chapterId, slug)`;
localized titles share these IDs. Chapters and lessons use source order
starting at zero. `MODULE_KNOWLEDGE.DIFFICULT` is language-independent:
explicit conflicting difficulties across selected locales block the update.
If no selected locale specifies a difficulty, the importer preserves an
existing valid Oracle difficulty (including one authored by an unselected
locale); otherwise new/missing database difficulty defaults to **`BASIC`**.
Explicit `INTERMEDIATE` or `ADVANCED` never silently becomes `BASIC`.
Conflicts with unselected stored translations still block explicit difficulty
updates. Missing locale files are ignored by default; explicitly requested
missing locales are an error.

The **core publication gate** is `status: WRITTEN` and nonblank Markdown;
the shared difficulty will have a valid `BASIC`/`INTERMEDIATE`/`ADVANCED` value
after import (defaulting to `BASIC` when unspecified). The five additional fields
`focus`, `problemSolved`, `mechanism`, `applicationValue`, `summary` are
**entirely optional** and may be generated much later by a separate script.
They do **not** force a lesson back to `DRAFT`, even if all five are blank.
The main importer INSERTs only `CONTENT` and `STATUS` into the localized
Knowledge table (the five QA fields default to SQL `NULL`); future main
imports UPDATE **only** `CONTENT` and `STATUS`, never those five metadata
columns. Missing difficulty does **not** force `DRAFT`; missing `WRITTEN` status
or Markdown still does. The importer never invents a source `WRITTEN` status.
`MODULE_KNOWLEDGE.IS_ACTIVE` and the Section
`IS_ACTIVE` become true when **any** language passes the gate; a Chapter
becomes active when any of its Sections is active. Existing translations
outside the import remain untouched. `--apply` can deactivate previously
published lessons if the selected source has regressed to draft, but it does
not delete any rows.

**Backend contract:** A public locale lesson endpoint MUST check the
requested `MODULE_KNOWLEDGE_LANGUAGE.STATUS='WRITTEN'`, nonblank `CONTENT`,
valid shared `DIFFICULT` and Module/Chapter/Section/Knowledge/Language
visibility. The five additional metadata fields are nullable and may be
returned as `null`; `hasSummary` can be computed separately. `IS_ACTIVE`
alone is insufficient because it is shared across locales. Never fall back
to another language. Locale parsing requires the same slug hierarchy across
languages being imported together.

## Independent Knowledge metadata importer

The separate `sync-knowledge-metadata-single.py` and
`sync-knowledge-metadata-all.py` accept the same `--module` (single only),
repeatable `--lang`, `--offline`, `--dry-run` (default), and explicit `--apply`.
They read each locale's existing `menu-detail-status.yml` under the normal
source layout. They resolve the already-imported Knowledge Language row by
`SERVICE_NAME` → Chapter slug → Section slug → language code and update
**only** `FOCUS`, `PROBLEM_SOLVED`, `MECHANISM`, `APPLICATION_VALUE`, and
`SUMMARY`. They do not change publication status or shared difficulty, and
never insert `MODULE`, `MODULE_MENU`, `MODULE_KNOWLEDGE` or missing localized
rows. Missing rows are counted as `missing_rows`, so run core sync first.

This metadata script is **non-destructive by default**: a missing/empty source
field preserves whatever is already stored in Oracle, while a nonblank source
field replaces that particular field if different. Partial metadata is fine.
It uses an Oracle module-row lock, a fresh scoped metadata-only snapshot and a
per-module transaction with rollback on error. There is no metadata checksum
cache: each run deliberately evaluates the five fields independently of the
core import cache. Run the metadata dry-run before applying, and avoid clearing
previously populated source metadata unless you intend to leave DB untouched.

The importer is intentionally separate from STEP 5/6 generation scripts,
which currently have Vietnamese-only staging restrictions. It accepts source
translations directly after validation, without launching those scripts.

## Skip unchanged modules with SHA-256

**Skip is enabled by default only on `--apply`.** The regular default dry-run
always parses and compares the complete source with Oracle, so it reports the
actual planned inserts/updates even if a previous apply created a checkpoint.
`--offline` always validates the source and never connects to Oracle. Explicit
`--force` / `--no-skip-unchanged` on apply performs a full reconciliation.

The module SHA-256 hashes `module_activate.json`, `module-info.json`, all `.yml`,
`.yaml`, and `.md` files throughout every selected Knowledge locale, as well as
relative file/directory names, the complete locale directory inventory, and
the importer contract version (now `default-basic-v3` for the missing-difficulty
default). A changed file, renamed/deleted lesson, added
chapter or added/deleted locale changes the digest. Each language subset has
its own checkpoint (`--lang vi` and `--lang vi --lang en` are distinct). The
preflight checks both small module JSON files, activation, language selection
and duplicate `SERVICE_NAME` across all discovered modules **before** import.

The checkpoint is machine-local, outside the repository and Git:

| Operating system | Default cache directory |
| --- | --- |
| Windows | `%LOCALAPPDATA%\\java-learning\\oracle-menu-knowledge\\` |
| Linux/macOS | `~/.cache/java-learning/oracle-menu-knowledge/` |

Only an explicit successful Oracle `--apply` can write this directory. A
per-machine random `.signing-key` authenticates cache files with HMAC-SHA256;
the Oracle DSN/database identity is included only as an HMAC input. Cache files
contain hashes and contract versions, **no database URL, password, source
Markdown or connection string**. Paths and parent directories containing a
symlink/junction are rejected. Missing, corrupted or modified cache files,
an unavailable signing key, changed schema/database/module ID, and any failed
DB verification are treated as cache misses and trigger a full import.

On a cache hit the importer first locks the existing `MODULE` row, checks the
source SHA-256, compares a lightweight database witness, then checks the source
SHA-256 again. **This path does not parse large YAML or fetch lesson CLOBs.**
The DB witness includes all four Menu/Knowledge tables, all current language
rows (including unselected locales), row identities and metadata, `ORA_ROWSCN`
and the lengths of lesson/summary CLOBs. A later metadata-only update may
invalidate the core cache once (safe but possibly slower); the subsequent
core import will not overwrite that metadata. If any witness differs, the full
import runs and its changes are committed per module. The cache is atomically
updated only **after a successful module commit**, after reacquiring the module
lock and verifying a fresh full database snapshot matches the source. This
extra verification makes the first successful apply somewhat slower; all
later unchanged applies avoid the expensive database snapshot and YAML parse.
The CLI displays `SKIPPED_UNCHANGED` and `skipped_unchanged=N` when it skips.

Oracle `ORA_ROWSCN` is block-level without `ROWDEPENDENCIES`, so unrelated
updates may cause harmless cache misses. Some manual **in-place LOB edits of
exactly the same length** may not change the row SCN/length and can evade the
cheap witness. When Oracle is edited outside this importer, run a normal
dry-run to inspect the actual diff, then run `--apply --force` to reconcile.
You can also invalidate all local checkpoints by deleting the dedicated cache
directory while the importer is not running; the next apply will fully sync
and recreate it. A cached module never skips solely because source files are
unchanged: the database witness and identity must match too.
