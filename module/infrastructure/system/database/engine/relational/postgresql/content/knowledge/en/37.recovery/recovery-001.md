# Restoring SQL Dumps and Controlling Script Execution Errors in PostgreSQL

An SQL dump is only valuable when it can be restored accurately into the target database. In PostgreSQL, the restore method depends on the **dump format**:

- A plain SQL dump is a file of SQL commands executed with `psql`.
- A custom, directory, or tar dump is an archive created by `pg_dump` and read with `pg_restore`.

Another critical part is **error handling**. By default, `psql` can continue running subsequent commands after an SQL statement fails. `pg_restore` can also continue past certain errors and report a summary at the end. If a restore script needs to stop immediately on error, roll back everything, or log with a reliable exit code, you must choose the right options.

The lesson **"Restoring SQL Dumps and Controlling Script Execution Errors in PostgreSQL"**, part of the **Recovery** chapter of the **Database Engine Relational PostgreSQL** module, covers dump formats, choosing between `psql` and `pg_restore`, preparing databases/roles/extensions, full and partial restores, handling ownership/ACL, transaction scope, error handling, shell exit codes, logging, and post-restore verification.

> **Principle:** identify the dump format before restoring; restore into a prepared target; enable stop-on-error mode when an all-or-nothing result is required; always check the exit code and data after restoring.

---

## 1. What Is an SQL Dump?

An SQL dump is a logical representation of PostgreSQL schema and/or data. It can contain:

- `CREATE TABLE`, `CREATE SEQUENCE`, `CREATE VIEW`.
- `CREATE INDEX`, constraints, and triggers.
- `INSERT` or other data-loading statements.
- Function, procedure, type, and extension declarations.
- Ownership and privilege statements if preserved in the dump.
- Sequence values and required object metadata.

A logical dump is not a physical copy of the data directory. It is created by reading database objects and exporting them in a form that can be recreated on another server.

### 1.1. SQL Dumps vs. Physical Backups

| Logical SQL dump | Physical backup |
|---|---|
| Represents schema/data as SQL or a logical archive | Backs up physical files of the cluster/database |
| Usually restored with psql/pg_restore | Restored via physical backup/recovery procedures |
| Can select specific schemas/tables/sections | Usually recovers a physical cluster/instance |
| Suitable for migrations and logical data transfer | Suitable for PITR/physical disaster recovery |
| Does not preserve physical page layout | Preserves physical state according to the backup method |

Do not use `pg_restore` to restore a physical base backup. Do not use SQL dumps as a direct replacement for WAL archives/PITR.

## 2. Dump Formats

`pg_dump` supports the following primary formats:

| Format | Option | Characteristics | Restore tool |
|---|---|---|---|
| Plain | Default | Human-readable SQL file | `psql` |
| Custom | `-Fc` | Flexible archive, selective object/parallel restore | `pg_restore` |
| Directory | `-Fd` | A directory containing multiple archive files; supports parallel dump/restore | `pg_restore` |
| Tar | `-Ft` | Tar-format archive | `pg_restore` |

**Plain SQL** can be opened in a text editor to inspect its contents. Custom/directory/tar are archive formats; use `pg_restore --list` to view the table of contents.

### 2.1. Do Not Use the Wrong Tool

- Plain SQL: `psql -f dump.sql`.
- Custom/directory/tar: `pg_restore`.
- Do not pass a custom archive to psql as if it were SQL text.
- Do not pass a plain SQL file to pg_restore.

## 3. Creating a Plain SQL Dump

~~~bash
pg_dump -h db.example -p 5432 -U backup_user -d appdb -f appdb.sql
~~~

This command creates an SQL file that can be loaded using psql.

You can request the dump to include the database creation command:

~~~bash
pg_dump -h db.example -U backup_user -d appdb --create -f appdb-create.sql
~~~

When a dump contains a CREATE DATABASE statement and a psql connect meta-command, psql must connect to an appropriate maintenance database, such as `postgres`, so the script can create and switch to the target database on its own.

### 3.1. Inspecting a Plain Dump

You can look for `CREATE TABLE`, `COPY`, `ALTER TABLE`, `CREATE INDEX`, and `setval` statements. Do not arbitrarily edit parts involving dependency ordering or quoting.

## 4. Creating a Custom Archive

~~~bash
pg_dump -h db.example -U backup_user -d appdb -Fc -f appdb.dump
~~~

A custom archive is suitable when you want to:

- Select specific objects to restore.
- Restore schema-only or data-only.
- Restore by section.
- Use `pg_restore --list` and a TOC file.
- Run parallel restore with `-j`.

A custom archive is not a plain SQL file, although you can use pg_restore to output it as SQL text.

## 5. Creating a Directory Archive

~~~bash
pg_dump -h db.example -U backup_user -d appdb -Fd -j 4 -f appdb-dir
~~~

The directory format writes the archive as multiple files inside a directory. It supports both parallel dump and parallel restore.

Ensure the destination directory has sufficient disk space and is protected with appropriate access permissions.

### 5.1. Creating a Tar Archive

~~~bash
pg_dump -h db.example -U backup_user -d appdb -Ft -f appdb.tar
~~~

A tar archive can be restored with pg_restore, though it does not support all the parallel capabilities of custom/directory formats.

## 6. Dumping an Entire Cluster

`pg_dump` only dumps **one database** at a time. It does not export cluster-wide roles and tablespaces.

`pg_dumpall` can dump all databases and global objects:

~~~bash
pg_dumpall -h db.example -U postgres -f cluster.sql
~~~

You can also export only global objects:

~~~bash
pg_dumpall -h db.example -U postgres --globals-only -f globals.sql
~~~

Global objects include roles and tablespaces. The globals script may contain sensitive information such as role password hashes or tablespace paths; protect the dump file like credential material.

### 6.1. Restoring pg_dumpall

A pg_dumpall dump is a plain SQL script, typically run via psql:

~~~bash
psql -X -h target.example -U postgres -d postgres -v ON_ERROR_STOP=1 -f cluster.sql
~~~

The script can create databases itself and switch connections between them. Do not wrap a full-cluster dump containing CREATE DATABASE in a single transaction.

## 7. Preparing the Target Before Restoring

Before running a restore, identify:

1. Target server/port/database.
2. Source and target PostgreSQL versions.
3. Required encoding and locale/collation.
4. Roles/owners that need to exist.
5. Server-side extensions and packages that need to be installed.
6. Tablespaces and filesystem paths.
7. Connection privileges and object creation privileges.
8. Disk space, WAL space, and maintenance window.
9. Whether the target database is currently in use by an application.
10. Whether there is a backup/rollback plan for the current target.

Restoring into an empty database is usually more predictable than restoring over a database that already contains objects.

## 8. Creating the Target Database

Example of creating a new database:

~~~bash
createdb -h target.example -U db_admin -T template0 -E UTF8 appdb_restore
~~~

`template0` is often useful when you need to create a clean database with a specified encoding/locale, avoiding custom objects present in template1.

Depending on the operating system and PostgreSQL version, additional locale/collation options may be required. Choose ones compatible with the source and the application.

### 8.1. Why Not Restore Into the postgres Database?

`postgres` is typically the maintenance database for administrative connections. You should create a separate database for the application and restore into it, unless the dump script creates the database itself via the `--create` option.

## 9. Restoring Plain SQL with psql

Basic command:

~~~bash
psql -X -h target.example -p 5432 -U restore_user -d appdb_restore -f appdb.sql
~~~

Meaning:

- `-X`: do not read user/system psqlrc files, making the script less dependent on the environment.
- `-h`, `-p`: specify host/port.
- `-U`: connection role.
- `-d`: target database.
- `-f`: SQL file to execute.

For automated restore scripts, you should enable `ON_ERROR_STOP`:

~~~bash
psql -X -v ON_ERROR_STOP=1 -h target.example -U restore_user -d appdb_restore -f appdb.sql
~~~

When an SQL error occurs, psql stops the script and returns a non-zero exit code under this mode.

## 10. Restoring a Plain Dump with CREATE DATABASE

If the dump was created with `pg_dump --create`, the script may contain the database creation statement and a psql connect meta-command to that database.

Example:

~~~bash
psql -X -v ON_ERROR_STOP=1 -h target.example -U db_admin -d postgres -f appdb-create.sql
~~~

Connect to the maintenance database. The dump creates the database according to its metadata and switches the connection.

Do not run this type of script with `psql --single-transaction` if it contains CREATE DATABASE, because PostgreSQL does not allow CREATE DATABASE inside a transaction block.

## 11. Restoring a Custom Archive with pg_restore

If the target database has already been created:

~~~bash
createdb -h target.example -U db_admin -T template0 appdb_restore

pg_restore -h target.example -U restore_user -d appdb_restore appdb.dump
~~~

`pg_restore` reads the archive, creates the schema, and loads data according to the dependency order recorded in the archive.

By default, pg_restore can continue after some errors, logging them and reporting the total error count at the end. If you want it to stop on the first error, use `--exit-on-error`.

~~~bash
pg_restore --exit-on-error -h target.example -U restore_user -d appdb_restore appdb.dump
~~~

### 11.1. Inspecting an Archive Before Restoring

~~~bash
pg_restore --list appdb.dump
~~~

This command displays the Table of Contents (TOC): schemas, tables, data, indexes, constraints, functions, and other objects in the archive.

## 12. pg_restore --create

You can ask pg_restore to create the database recorded in the archive:

~~~bash
pg_restore --create -h target.example -U db_admin -d postgres appdb.dump
~~~

When using `--create`, the database is created with the name stored in the archive. `-d postgres` is the maintenance database that pg_restore connects to before creating and switching to the target database.

If you want to restore into a database with a different name, create that database beforehand and use `-d appdb_restore` **without** adding `--create`.

### 12.1. Do Not Confuse -d with the Source Database Name

- Without `--create`: `-d` is the database that receives the objects/data.
- With `--create`: `-d` is the maintenance database used to execute CREATE DATABASE, while the database name is taken from the archive.

## 13. Handling Ownership and Privileges

A dump may contain ownership and ACLs from the source. The target may not have those roles.

With a custom archive:

~~~bash
pg_restore --no-owner --no-privileges -d appdb_restore appdb.dump
~~~

- `--no-owner`: do not emit commands to restore original ownership; objects typically belong to the role performing the restore.
- `--no-privileges` (also called `--no-acl`): skip dumped GRANT/REVOKE statements.

With a plain dump, the corresponding options can be specified when creating the dump:

~~~bash
pg_dump --no-owner --no-acl -f appdb.sql appdb
~~~

Do not skip ownership/ACLs if the system needs to preserve the exact permission model. Decide based on the role mapping on the target.

## 14. Roles and Global Objects

`pg_dump` does not dump cluster-wide roles and tablespaces. If you restore an object whose owner or grant references a nonexistent role, the restore may report errors.

You can export globals separately:

~~~bash
pg_dumpall --globals-only -h source.example -U postgres -f globals.sql
~~~

Restore globals using an appropriate administrative role:

~~~bash
psql -X -v ON_ERROR_STOP=1 -h target.example -U postgres -d postgres -f globals.sql
~~~

Then restore the database dump.

### 14.1. Do Not Restore Password Hashes Blindly

A global dump may contain role definitions and password hashes. Only restore in trusted environments, restrict file read permissions, and review credential policies before applying.

## 15. Extensions and Dependencies

If the dump contains:

~~~sql
CREATE EXTENSION some_extension;
~~~

the target server must have the corresponding extension package installed at the OS/PostgreSQL installation level. An SQL dump alone does not install binary extensions.

Before restoring:

- List source extensions.
- Install compatible packages on the target.
- Verify versions.
- Check extension dependencies.
- Ensure the restore role has the required privileges.

Check current extensions on the source:

~~~sql
SELECT extname, extversion
FROM pg_extension
ORDER BY extname;
~~~

## 16. PostgreSQL Version Compatibility

Practical rules:

- Use a `pg_dump` of the same major version or newer than the source server; pg_dump does not support dumping a server with a newer major version than itself.
- Logical dumps are generally designed for migrating data to newer PostgreSQL versions.
- Restoring backward to an older major version is not guaranteed.
- Extensions, collations, data types, functions, and SQL syntax can introduce incompatibilities.
- Physical backups have different version compatibility rules than logical dumps.

Check versions:

~~~sql
SELECT version();
~~~

and:

~~~bash
pg_dump --version
pg_restore --version
psql --version
~~~

Do not just compare client version numbers; verify source/target major versions and extension compatibility.

## 17. Encoding, Locale, and Collation

A database created with a different encoding/collation can cause errors or alter comparison/sorting order.

Check the source:

~~~sql
SELECT
    datname,
    pg_encoding_to_char(encoding) AS encoding,
    datcollate,
    datctype
FROM pg_database
WHERE datname = current_database();
~~~

Check the target before restoring. For a database that needs compatible recreation, use `template0` and choose matching encoding/locale settings.

Some ICU/libc-based collations can depend on OS and version. Collation version changes can affect indexes; handle them according to the relevant PostgreSQL guidelines.

## 18. Restoring Into a Non-Empty Database

If the target already has tables/indexes, a restore may encounter:

- `relation already exists`.
- Duplicate keys.
- Existing functions/types.
- Conflicting owners/ACLs.
- Constraint/index name collisions.
- Duplicated or un-loadable data.

The safe approach is usually to restore into a new database, verify it, and then switch the application/routing.

If restoring over an existing database is unavoidable, clearly define the object scope and use `--clean`/`--if-exists` cautiously.

## 19. --clean and --if-exists

With pg_restore:

~~~bash
pg_restore --clean --if-exists -d appdb_restore appdb.dump
~~~

- `--clean`: emits DROP commands for objects before recreating them.
- `--if-exists`: uses the IF EXISTS condition when dropping where applicable, reducing errors when an object does not yet exist.

This can be a destructive operation for existing data/objects. Only use it when the target is clearly verified and appropriate backups/approvals are in place.

### 19.1. --clean Does Not Reset the Whole Cluster

It handles objects included in the archive and restore scope. It does not automatically delete every object or every database outside the archive.

## 20. Schema-Only and Data-Only Restores

Custom archives allow selecting the content:

**Schema-only:**

~~~bash
pg_restore --schema-only -d appdb_restore appdb.dump
~~~

**Data-only:**

~~~bash
pg_restore --data-only -d appdb_restore appdb.dump
~~~

Schema-only creates object definitions; data-only loads data into an existing schema.

### 20.1. Data-Only Requires a Compatible Schema

If tables/columns/types/constraints are incompatible, the data restore may fail. Check schema versions and dependencies beforehand.

## 21. Restoring by Section

An archive has three main sections:

- `pre-data`: definitions needed before data, such as tables/types/functions depending on the object.
- `data`: table data, large objects, sequence values.
- `post-data`: indexes, constraints, triggers, and objects needed after data.

Example:

~~~bash
pg_restore --section=pre-data -d appdb_restore appdb.dump
pg_restore --section=data -d appdb_restore appdb.dump
pg_restore --section=post-data -d appdb_restore appdb.dump
~~~

Running sections separately is useful for migrations/debugging, but proper order and dependencies must be maintained. If one phase fails, stop and resolve it before proceeding to the next phase.

## 22. Restoring Selected Schemas/Tables

You can filter an archive:

~~~bash
pg_restore --schema=public -d appdb_restore appdb.dump
~~~

Select a table:

~~~bash
pg_restore --table=orders -d appdb_restore appdb.dump
~~~

Object/schema names must match the TOC and quoting rules. Restoring a single table may require related types, sequences, functions, referenced tables, or extensions.

### 22.1. Partial Restore Does Not Automatically Resolve Dependencies

If you select only a table but omit a type/function/sequence that the table depends on, the restore may fail. Use `pg_restore --list` and inspect dependencies beforehand.

## 23. TOC Lists and Object Selection Files

You can export the TOC:

~~~bash
pg_restore --list appdb.dump > restore.list
~~~

Then edit the list file to select the entries you want to restore and run:

~~~bash
pg_restore --use-list=restore.list -d appdb_restore appdb.dump
~~~

The short option name is typically `-L`.

Keep the original TOC file for comparison. Omitting a line can prevent dependent objects from being restored.

## 24. Parallel Restore

Custom and directory archives support parallel restore via `-j`:

~~~bash
pg_restore -j 4 -d appdb_restore appdb.dump
~~~

PostgreSQL can restore multiple independent objects/data tasks concurrently, reducing duration when CPU, disk, and the target have sufficient capacity.

Parallelism increases connection count, disk I/O, CPU usage, concurrent WAL generation, and pressure on shared resources. Benchmark the job count to match target hardware and workload.

### 24.1. Parallel Restore Cannot Be Used with --single-transaction

`pg_restore --single-transaction` cannot be combined with `-j`. Choose one or the other: parallel restore or an all-or-nothing single transaction.

## 25. pg_restore --single-transaction

~~~bash
pg_restore --single-transaction -d appdb_restore appdb.dump
~~~

This option wraps the restore in a single transaction. If a restore command fails, the transaction rolls back to avoid leaving a partially committed restore.

This option implies `--exit-on-error` and is incompatible with parallel jobs.

### 25.1. When Is It Suitable?

- Moderate-sized dumps.
- Commands in the archive can run inside a transaction.
- All-or-nothing behavior is required.
- The target is new and not yet in use.

### 25.2. When Is It Not Suitable?

- Very large archives where the transaction would last too long.
- Parallel restore is needed.
- There are commands that cannot run inside a transaction block.
- The restore needs to be split into independent phases.
- Operational/locking requirements are incompatible with a long transaction.

`CREATE DATABASE`, `CREATE TABLESPACE`, `VACUUM`, and certain other commands cannot run inside a transaction block. If the restore contains these commands, do not wrap the entire restore in a single transaction.

## 26. psql ON_ERROR_STOP

By default, psql can continue executing subsequent commands after an SQL error in a script.

To stop when an error is encountered:

~~~bash
psql -X -v ON_ERROR_STOP=1 -d appdb_restore -f restore.sql
~~~

Or at the top of the script file, set the psql variable ON_ERROR_STOP to on.

When ON_ERROR_STOP is enabled, an SQL error in the script causes psql to stop and return a non-zero exit status.

### 26.1. psql Exit Codes

In non-interactive mode, the key exit statuses are:

| Exit code | Meaning |
|---|---|
| `0` | Normal completion |
| `1` | Fatal psql error, such as file or resource error |
| `2` | Connection to the server failed in non-interactive mode |
| `3` | Error in a script when ON_ERROR_STOP is enabled |

Scripts invoking psql must check the exit code, not just scan the log for ERROR lines.

## 27. ON_ERROR_STOP Is Not the Same as ON_ERROR_ROLLBACK

`ON_ERROR_STOP` controls **whether to stop the script** when an error occurs.

`ON_ERROR_ROLLBACK` controls how psql handles errors inside a transaction using savepoints.

When ON_ERROR_ROLLBACK is enabled, psql automatically creates a savepoint before each command in a transaction; if the command fails, psql rolls back to the savepoint so the transaction can continue.

This mechanism is useful in certain interactive sessions, but it does not replace a fail-fast strategy for restores.

### 27.1. Why Not Enable ON_ERROR_ROLLBACK to "Force a Restore Through"?

If errors are rolled back per statement and the script continues, the database may end up missing a subset of objects/data. This is rarely the desired outcome for a restore that needs to be complete.

## 28. Using psql Single Transaction

For a compatible SQL script, you can use:

~~~bash
psql -X -v ON_ERROR_STOP=1 --single-transaction -d appdb_restore -f schema-and-data.sql
~~~

psql opens a transaction before the input commands and commits upon completion. When an error occurs with ON_ERROR_STOP, the transaction can be rolled back instead of keeping partial changes executed earlier.

Do not use this with scripts containing CREATE DATABASE, CREATE TABLESPACE, VACUUM, psql connect meta-commands, or commands that must run outside a transaction. Also avoid it if the script manages BEGIN/COMMIT itself in a conflicting way.

## 29. Transaction Scope and Large Restores

A single restore transaction benefits atomicity but carries costs:

- Long-lived transaction.
- Locks may be held for a long time.
- Rollback on failure can take significant time.
- Snapshot/transaction state persists longer.
- Can affect vacuum and other workloads.
- The entire restore only commits at the end.

For large databases, restoring into a separate database not yet used by applications is often easier to operate than trying to wrap everything in a single transaction.

## 30. pg_restore --exit-on-error

By default, pg_restore may continue after errors to attempt restoring other objects and summarize the total error count at the end.

If you want to stop immediately:

~~~bash
pg_restore --exit-on-error -d appdb_restore appdb.dump
~~~

This option is appropriate when any error renders the restore unacceptable.

If you want to attempt recovering as much data as possible for analysis, you can use the default and then inspect the entire error summary; however, never treat a restore with errors as successful.

## 31. Combining pg_restore with Transactions

All-or-nothing, non-parallel:

~~~bash
pg_restore --single-transaction -d appdb_restore appdb.dump
~~~

Fail-fast, parallel-capable:

~~~bash
pg_restore --exit-on-error -j 4 -d appdb_restore appdb.dump
~~~

You cannot use a single transaction together with parallel jobs. If restoring in parallel, use a dedicated target and a clear verification/cleanup procedure when any job fails.

## 32. Distinguishing SQL Errors from Operational Errors

A restore can fail due to:

**SQL/object errors:**

- Role does not exist.
- Table/type already exists.
- Duplicate key.
- Missing extension.
- Incompatible function/operator.
- Permission denied.

**Environment/operational errors:**

- Unable to connect.
- Disk full.
- WAL/disk pressure.
- Unreadable dump file.
- Corrupted archive.
- Network timeout.
- Server restart.
- Incompatible client/server versions.

Read the first error and its context before deciding on a fix. One error early in a restore can cascade into hundreds of dependent errors afterward.

## 33. Restore Logging and Verbosity

With pg_restore:

~~~bash
pg_restore --verbose --exit-on-error -d appdb_restore appdb.dump > restore.log 2>&1
~~~

With psql:

~~~bash
psql -X -v ON_ERROR_STOP=1 -d appdb_restore -f appdb.sql > restore.log 2>&1
~~~

Logs must be protected because they can contain object names, SQL text, or sensitive data depending on the error type/verbosity.

Record start/end timestamps, command and tool versions, target database/server, exit code, error count, restore duration, and dump file/checksum.

Do not put passwords on the command line or in logs.

## 34. Shell Scripts Must Preserve the Exit Code

Bash example:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

pg_restore \
  --verbose \
  --exit-on-error \
  --dbname=appdb_restore \
  appdb.dump \
  >restore.log 2>&1

echo "Restore completed successfully"
~~~

`set -euo pipefail` causes the script to stop when a command fails, an unset variable is referenced, or a command in a pipeline fails.

If using `tee` to both display and save logs:

~~~bash
set -o pipefail
pg_restore --exit-on-error -d appdb_restore appdb.dump 2>&1 | tee restore.log
~~~

Do not omit `pipefail`: otherwise, the shell may capture the exit code of tee instead of pg_restore.

## 35. PowerShell and Client Exit Codes

In PowerShell, native programs like psql/pg_restore return their exit code via `LASTEXITCODE`.

~~~powershell
$ErrorActionPreference = 'Stop'

& pg_restore --verbose --exit-on-error --dbname=appdb_restore appdb.dump 2>&1 |
    Tee-Object -FilePath restore.log

if ($LASTEXITCODE -ne 0) {
    throw "pg_restore failed with exit code $LASTEXITCODE"
}

Write-Output "Restore completed successfully"
~~~

`ErrorActionPreference` controls PowerShell errors, whereas `LASTEXITCODE` holds the exit code of the native executable. Do not confuse the two mechanisms.

For complex pipelines, carefully verify how the shell/version handles native command exit statuses; the simplest approach is to run the command directly, save logs, and check LASTEXITCODE immediately after the command.

## 36. Passing Passwords Securely

Do not write passwords directly on the command line. The `-W` option only prompts for a password; it does not accept a password as a following argument.

Prefer:

- `.pgpass` on Unix-like systems.
- `PGPASSFILE` pointing to a file with appropriate permissions.
- Service definitions and environment-appropriate secret managers.
- Interactive prompting for manual operations.

Do not place passwords in source control, shell history, process lists, or logs.

## 37. Inspecting an Archive Before Restoring

For custom/directory/tar:

~~~bash
pg_restore --list appdb.dump
~~~

Check:

- Are the expected schemas/tables present?
- Are data entries present?
- Are sequences present?
- Are large objects present if the application uses them?
- Are functions/extensions present?
- Are owners/ACLs present?
- Are tablespaces present?
- Are there any objects you do not want to restore?

You can export the TOC to a file for review:

~~~bash
pg_restore --list appdb.dump > appdb.toc
~~~

This step only reads archive metadata and does not modify the target database.

## 38. Verifying Dump Files and Checksums

For dump files transferred over a network/storage, you should have a checksum:

~~~bash
sha256sum appdb.dump
~~~

On Windows:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath .\appdb.dump
~~~

Compare the checksum against a trusted manifest/source. A checksum only confirms identical bytes; it does not prove the dump can be restored successfully.

## 39. Restoring by pre-data/data/post-data

A controlled workflow can separate sections:

~~~bash
pg_restore --section=pre-data --exit-on-error -d appdb_restore appdb.dump
pg_restore --section=data --exit-on-error -d appdb_restore appdb.dump
pg_restore --section=post-data --exit-on-error -d appdb_restore appdb.dump
~~~

This approach helps analyze errors by stage and can allow loading data before creating indexes/constraints.

If a phase fails, stop and resolve it before the next phase. Do not assume re-running the entire command will automatically fix partial state.

## 40. Data-Only Restores and Triggers

Some data-only restore cases may require controlling triggers/foreign keys.

pg_restore has the `--disable-triggers` option for certain data-only restores; this requires elevated privileges (typically superuser) and carries risks if triggers are not re-enabled properly.

Do not use it to bypass constraint errors without understanding the data. If there are foreign key violations, determine the dependency/order and integrity of the dump.

## 41. Sequence Values After Restoring

Sequences are separate objects. Logical dumps typically include statements to restore the appropriate sequence state.

~~~sql
SELECT
    schemaname,
    sequencename,
    last_value
FROM pg_sequences
WHERE schemaname = 'public'
ORDER BY sequencename;
~~~

`last_value`/`is_called` semantics should be understood when checking a specific sequence. Test a new INSERT to confirm the sequence does not generate duplicate IDs against existing data.

## 42. Large Objects in Dumps

Large Objects are a separate PostgreSQL subsystem, though pg_dump can dump large objects with the database by default; `--blobs`/`--no-blobs` options control this scope.

If the application uses OID references:

- Confirm the dump contains LO contents.
- Confirm the restore has all LO objects.
- Check OID references.
- Check large object privileges.
- Check the backup/restore procedure.

A metadata row containing an OID without restored object contents creates an unusable reference.

## 43. Run ANALYZE After Restoring

After loading large amounts of data, planner statistics may not yet accurately reflect the new data.

~~~sql
ANALYZE;
~~~

Or use the tool:

~~~bash
vacuumdb --analyze-in-stages -d appdb_restore
~~~

Choose a command suitable for the database size and state. Do not run VACUUM FULL just because you finished a restore; the goal here is updating planner statistics and performing appropriate maintenance.

## 44. Post-Restore Verification

Do not just check the command exit code. Verify:

1. The database exists and accepts connections.
2. Schemas/tables/views/functions are accurate.
3. Row counts are reasonable.
4. Primary/foreign keys and constraints are present.
5. Indexes have been created.
6. Sequence values do not cause duplicate IDs.
7. Extensions and versions match.
8. Owners/GRANT/RLS are correct.
9. Large Objects or object references work.
10. Application smoke tests pass.
11. Logs contain no unacceptable errors.
12. Restore duration meets the RTO.

Example quick count:

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup
FROM pg_stat_user_tables
ORDER BY schemaname, relname;
~~~

`n_live_tup` is an estimate; for critical tables, run controlled COUNT queries or cross-check against a manifest/business invariants.

## 45. Restoring Into a New Database and Switching the Application

~~~text
Old production database
        |
        +--> create dump
        |
        v
Restore into new database
        |
        v
Verify schema/data/permissions
        |
        v
Run smoke tests
        |
        v
Switch connection string/routing
        |
        v
Monitor application
~~~

Keep the old database according to your retention/change window until the cutover is confirmed. Database rename/swap procedures must clearly handle connections, locks, ownership, and downtime.

## 46. Troubleshooting: role does not exist

Symptom:

~~~text
ERROR: role "app_owner" does not exist
~~~

Cause: the dump retains owners/grants from the source, but the target lacks the role.

Resolution:

- Restore global roles first if permitted.
- Or use `--no-owner --no-privileges` if the target uses a new permission model.
- Or create role mappings according to policy.
- Do not create a superuser just to bypass an owner error.

## 47. Troubleshooting: relation already exists

Symptom:

~~~text
ERROR: relation "orders" already exists
~~~

Cause: the target is not empty or a restore has partially run.

Resolution:

- Determine whether existing objects hold critical data.
- For a disposable target, creating a new database is the cleanest approach.
- For a target with existing data, review `--clean --if-exists` and scope.
- Do not DROP a schema/database without verifying the target.

## 48. Troubleshooting: extension missing

Symptom:

~~~text
ERROR: extension "some_extension" is not available
~~~

Install the right version of the extension package on the target, verify the server has the required control file/shared library, and re-run the restore according to the current database state.

A CREATE EXTENSION statement in a dump does not download the extension binary from the source.

## 49. Troubleshooting: permission denied

Check:

- The connecting role.
- Database CONNECT/CREATE privileges.
- Schema USAGE/CREATE.
- Ownership and role membership.
- Tablespace access.
- Extension installation permissions.
- Superuser-only commands in the dump.

Use a role with the least privilege necessary yet sufficient to restore. Do not grant broad SUPERUSER privileges to an application role.

## 50. Troubleshooting: Restore Stops Mid-Way

With psql ON_ERROR_STOP, the script stops at the first error. With pg_restore --exit-on-error, the restore also stops at the first error.

The database may retain partial committed objects/data if not executed inside a single transaction.

Recovery steps:

1. Save logs and exit code.
2. Identify the first failing object/statement.
3. Determine whether the restore used a single transaction.
4. Check whether the current database is a disposable target.
5. Fix the root cause.
6. Prefer restoring again into a fresh database when a clean state is needed.
7. Only resume via TOC/sections when you understand dependencies and what has already completed.

Do not blindly re-run the entire dump against a half-restored target.

## 51. Troubleshooting: Disk Full or Rapid WAL Growth

Large restores can generate significant WAL, indexes, and temporary files.

Monitor:

- Free disk space on the data directory and tablespaces.
- `pg_wal` size.
- WAL archive success/failure.
- Replication slots and standby lag.
- Temporary files.
- Index build progress.
- Storage IOPS/latency.

If disk space is running out, stop the process in a controlled manner and assess the target state. Do not manually delete WAL files to free up space.

## 52. Troubleshooting: Encoding or Invalid Byte Sequence

Check dump encoding, database encoding, and client encoding:

~~~sql
SHOW server_encoding;
SHOW client_encoding;
~~~

Dumps created by pg_dump usually include the required encoding information. If transferring via text tools, avoid altering encoding or line endings improperly.

Do not ignore invalid byte sequences by replacing random characters; identify the source data and exact encoding instead.

## 53. Troubleshooting: Client and Server Versions

If the client is older than the source server, pg_dump may refuse to connect/dump. If an archive was created by a newer tool, an older pg_restore may not understand the archive version.

Use pg_dump/pg_restore matching the source/target major versions and check `--version` before running.

## 54. Are Restore Scripts Safe to Re-Run?

Not by default.

A script may create objects, insert data, invoke functions, or cause side effects. Re-running it can:

- Fail on duplicate objects/keys.
- Duplicate rows if the dump uses INSERT.
- Alter sequence state.
- Trigger triggers multiple times.
- Drop/recreate objects if `--clean` is used.
- Create side effects outside the database if the script contains external commands.

To be idempotent, a script must be intentionally designed for it: fresh target, precondition checks, migration versioning, and a rollback strategy.

## 55. psql Meta-Commands in Scripts

Plain dumps may contain psql meta-commands such as connect, set, echo, include file, and script-control commands. These are not SQL statements sent directly to the server; psql interprets them on the client.

Therefore, do not execute a plain pg_dump script using a standard JDBC SQL statement executor driver. Use psql to handle both SQL and psql meta-commands.

## 56. Security When Restoring Untrusted Dumps

An SQL dump can contain commands chosen by the dump creator, including function definitions, triggers, extension declarations, and arbitrary SQL.

Do not restore dumps from untrusted sources into production as a superuser.

Practices:

- Verify source/checksum.
- Review TOC or SQL text.
- Restore into an isolated database/instance.
- Use the least-privileged role possible.
- Use `-X` to avoid loading unintended psqlrc files.
- Consider `--no-owner` and `--no-privileges`.
- Inspect extensions before installing them.
- Prevent the script from reading out-of-scope secrets.

`--no-owner`/`--no-acl` do not make a malicious dump safe; you must still review its contents and origin.

## 57. Choosing an Error Policy

| Goal | psql | pg_restore |
|---|---|---|
| Stop immediately on error | `ON_ERROR_STOP=1` | `--exit-on-error` |
| All-or-nothing if commands are compatible | `--single-transaction` + `ON_ERROR_STOP` | `--single-transaction` |
| Continue to collect multiple errors | ON_ERROR_STOP off by default | Continues and reports error count by default |
| Parallel restore | Not applicable in the same way | `-j N`, cannot combine with single transaction |
| Detailed logging | Redirect output/psql logging | `--verbose` and redirect output |

Choose your policy before running, not after a restore has already created partial state.

## 58. Sample Restore Workflow: Custom Archive

~~~bash
# 1. Check client.
pg_restore --version

# 2. View TOC.
pg_restore --list appdb.dump > appdb.toc

# 3. Create new database.
createdb -h target.example -U db_admin -T template0 appdb_restore

# 4. Restore, stop on error.
pg_restore \
  --verbose \
  --exit-on-error \
  --no-owner \
  --no-privileges \
  -h target.example \
  -U restore_user \
  -d appdb_restore \
  appdb.dump

# 5. Run analyze after successful restore.
vacuumdb --analyze-in-stages -h target.example -U db_admin -d appdb_restore
~~~

Use `--no-owner` and `--no-privileges` only when target policy requires them. If ownership/ACLs must be preserved, prepare roles and permissions beforehand and omit these two options.

## 59. Sample Restore Workflow: Plain SQL

~~~bash
psql \
  -X \
  -v ON_ERROR_STOP=1 \
  -h target.example \
  -U restore_user \
  -d appdb_restore \
  -f appdb.sql
~~~

If the dump has `--create`, connect to a maintenance database as described earlier.

For scripts that can run inside a single transaction:

~~~bash
psql \
  -X \
  -v ON_ERROR_STOP=1 \
  --single-transaction \
  -h target.example \
  -U restore_user \
  -d appdb_restore \
  -f schema-and-data.sql
~~~

Only use single transaction when the script contains no commands that must run outside a transaction and does not manage transactions in a conflicting manner.

## 60. Pre-Restore Checklist

**Dump and target**

1. Have you identified plain/custom/directory/tar correctly?
2. Does the dump file have a verified checksum/trusted source?
3. Are client tools compatible with source/target versions?
4. Have target host/port/database been confirmed?
5. Is the target currently used by an application?
6. Is there sufficient disk/WAL space?
7. Is there a backup/rollback plan?

**Dependencies**

8. Are roles and tablespaces prepared?
9. Are extensions installed at the right version?
10. Are encoding/locale/collation compatible?
11. Will owners/ACLs be preserved or mapped?
12. Are there large objects to restore?

**Error policy**

13. Does psql have ON_ERROR_STOP?
14. Does pg_restore have --exit-on-error?
15. Should single transaction be used?
16. Are parallel jobs needed?
17. Are there commands that cannot run inside a transaction?
18. Are logs and exit codes captured?

**Post-restore**

19. Are schema/data/sequences/indexes accurate?
20. Are constraints/permissions/RLS accurate?
21. Has ANALYZE been run?
22. Did smoke tests succeed?
23. Are restore duration/RPO/RTO recorded?
24. Is there a plan for switching the application and retaining the old target?

## 61. Practice Exercises

### Exercise 1 — Dump Formats

Name the four common pg_dump formats.

**Hint:** plain, custom, directory, tar.

### Exercise 2 — Restore Tool

Which tool is used for a plain SQL dump?

**Hint:** psql.

### Exercise 3 — Custom Archive

Which tool is used for a custom archive?

**Hint:** pg_restore.

### Exercise 4 — Creating a Custom Dump

Write a command to create a custom archive for the appdb database.

**Hint:** pg_dump -Fc.

### Exercise 5 — Directory Format

Which format supports both parallel dump and parallel restore?

**Hint:** directory.

### Exercise 6 — pg_dumpall

Why is pg_dumpall needed when exporting roles and multiple databases?

**Hint:** pg_dump only dumps one database; pg_dumpall includes globals/all DBs.

### Exercise 7 — Globals

Write a command to export global objects.

**Hint:** pg_dumpall --globals-only.

### Exercise 8 — Plain Restore

Write a psql restore command with ON_ERROR_STOP.

**Hint:** psql -X -v ON_ERROR_STOP=1 -f.

### Exercise 9 — Archive List

Which command views the TOC of a custom dump?

**Hint:** pg_restore --list.

### Exercise 10 — Create Database

Where does pg_restore --create get the database name from?

**Hint:** archive metadata.

### Exercise 11 — Maintenance Database

When using --create, what does -d usually point to?

**Hint:** a maintenance database such as postgres.

### Exercise 12 — Owner

What does --no-owner do?

**Hint:** does not restore source ownership.

### Exercise 13 — ACL

Which option is --no-privileges equivalent to?

**Hint:** --no-acl.

### Exercise 14 — Extensions

Why might CREATE EXTENSION in a dump fail on the target?

**Hint:** extension package/binary is not installed.

### Exercise 15 — Versions

Can you use an older pg_dump major version against a newer server major version?

**Hint:** not supported; pg_dump rejects a server newer than the client's major version.

### Exercise 16 — Clean

What does --clean do?

**Hint:** drops objects before recreating them.

### Exercise 17 — if-exists

Which option is --if-exists used with?

**Hint:** usually paired with --clean.

### Exercise 18 — Schema-Only

Write a command to restore schema only.

**Hint:** pg_restore --schema-only.

### Exercise 19 — Data-Only

Write a command to restore data only.

**Hint:** pg_restore --data-only.

### Exercise 20 — Sections

Name the three main sections.

**Hint:** pre-data, data, post-data.

### Exercise 21 — TOC List

Which option uses an edited TOC file?

**Hint:** --use-list/-L.

### Exercise 22 — Parallel

Write a command to restore with 4 jobs.

**Hint:** pg_restore -j 4.

### Exercise 23 — Single Transaction

Is pg_restore --single-transaction compatible with -j?

**Hint:** no.

### Exercise 24 — Exit on Error

Which option makes pg_restore stop on the first error?

**Hint:** --exit-on-error.

### Exercise 25 — psql Error Stop

Which variable makes psql stop when a script encounters an error?

**Hint:** ON_ERROR_STOP.

### Exercise 26 — psql Exit Code

What does exit code 3 mean?

**Hint:** script error when ON_ERROR_STOP is enabled.

### Exercise 27 — ON_ERROR_ROLLBACK

How does it differ from ON_ERROR_STOP?

**Hint:** savepoint rollback per statement vs. stopping the script.

### Exercise 28 — psql Single Transaction

When should --single-transaction be used?

**Hint:** when the script is transaction-compatible and all-or-nothing is needed.

### Exercise 29 — CREATE DATABASE

Why can't CREATE DATABASE be wrapped in a transaction?

**Hint:** PostgreSQL does not allow this command inside a transaction block.

### Exercise 30 — Shell pipefail

Why is pipefail needed when using tee?

**Hint:** preserves the error exit code of the command in the pipeline.

### Exercise 31 — PowerShell

Which variable holds the exit code of a native executable?

**Hint:** LASTEXITCODE.

### Exercise 32 — Password

Why shouldn't passwords be placed on the command line?

**Hint:** process list/history/log exposure.

### Exercise 33 — Large Objects

Why should LO be verified during a restore?

**Hint:** OID references may lack object contents/privileges.

### Exercise 34 — Sequence

What should be tested with sequences after a restore?

**Hint:** new INSERTs do not generate duplicate IDs.

### Exercise 35 — ANALYZE

Why run ANALYZE after a large restore?

**Hint:** updates planner statistics.

### Exercise 36 — Partial Restore

Why might restoring a single table fail?

**Hint:** missing types/functions/sequences/dependencies.

### Exercise 37 — Non-Empty Target

What does the relation already exists error usually indicate?

**Hint:** target already has objects or a restore ran partially.

### Exercise 38 — Disk Full

Why not manually delete WAL files to continue a restore?

**Hint:** can break recovery/replication/archive continuity.

### Exercise 39 — Restore Security

Why not restore an untrusted dump as superuser?

**Hint:** the dump may contain arbitrary SQL/commands.

### Exercise 40 — Choosing an Error Policy

A restore needs all-or-nothing, the archive is moderately sized, and parallel restore is not required. Which option should you choose?

**Hint:** pg_restore --single-transaction.

## 62. Frequently Asked Questions

### Can I use psql to restore a custom dump?

No. Custom/directory/tar archives use pg_restore; plain SQL uses psql.

### Does pg_restore stop on the first error by default?

No. By default it can continue and summarize errors. Use --exit-on-error to stop early.

### Does psql stop a script on an SQL error by default?

No. Enable ON_ERROR_STOP to stop when an error occurs in a script.

### Does ON_ERROR_STOP automatically roll back the entire script?

Not by itself. For all-or-nothing behavior, use an appropriate transaction such as psql --single-transaction or a properly designed transaction block.

### Can pg_restore --single-transaction be used with -j?

No. Single transaction and parallel restore are incompatible.

### Should --clean be used in production?

Only after confirming the target, object scope, backup, and rollback plan. --clean can drop existing objects.

### Does pg_dump dump roles?

No. Use pg_dumpall --globals-only to export roles/tablespaces.

### Does a dump contain extension binaries?

No. The target must have the corresponding extension package installed before CREATE EXTENSION can succeed.

### Does a successful restore mean the application works properly?

No. You must verify constraints, sequences, permissions, extensions, and application smoke tests.

### If psql errors mid-restore, could the database still contain partial data?

Yes, if not run inside an encompassing transaction. Check target state and prefer restoring into a fresh database when a clean state is needed.

### Should you re-run a dump on a partially restored database?

Not blindly. The dump may not be idempotent and will hit duplicate objects/data. Assess the state or create a fresh target.

### Should --no-owner and --no-privileges always be enabled?

No. Only enable them when mapping to new ownership/ACLs. If source permissions must be kept, prepare roles and keep the statements.

### Can you restore into an older PostgreSQL version than the source?

Not guaranteed. Logical dumps generally target the same or newer version; syntax, types, extensions, and collation compatibility must be checked.

### Why is -X needed when running psql scripts?

To avoid reading unintended psqlrc files, reducing differences caused by personal/host configurations.

### Does a checksum prove a dump is restorable?

No. It only confirms matching bytes. You must perform a restore test.

## 63. Summary

Core commands:

~~~bash
# Plain SQL dump.
pg_dump -d appdb -f appdb.sql

# Custom archive.
pg_dump -d appdb -Fc -f appdb.dump

# Directory archive.
pg_dump -d appdb -Fd -j 4 -f appdb-dir

# Dump globals.
pg_dumpall --globals-only -f globals.sql

# Restore plain SQL, fail-fast.
psql -X -v ON_ERROR_STOP=1 -d appdb_restore -f appdb.sql

# Restore custom archive, fail-fast.
pg_restore --exit-on-error -d appdb_restore appdb.dump

# Restore archive all-or-nothing, serial.
pg_restore --single-transaction -d appdb_restore appdb.dump

# Inspect archive.
pg_restore --list appdb.dump

# Restore parallel.
pg_restore --exit-on-error -j 4 -d appdb_restore appdb.dump

# Analyze after restore.
vacuumdb --analyze-in-stages -d appdb_restore
~~~

Key principles to remember:

1. **Plain SQL uses psql; custom/directory/tar uses pg_restore.**
2. pg_dump exports one database; pg_dumpall can export globals and multiple databases.
3. Base backups/physical recovery differ from logical SQL dumps.
4. Prepare roles, extensions, encoding, locale, tablespaces, and permissions before restoring.
5. Use --list to inspect the archive TOC before running.
6. --no-owner and --no-privileges change ownership/ACL semantics; use only when needed.
7. --clean can drop objects; confirm the target and backup beforehand.
8. Partial restores must account for dependencies.
9. -j increases throughput but is incompatible with --single-transaction.
10. pg_restore may continue past errors by default; use --exit-on-error for fail-fast.
11. psql may continue after SQL errors by default; use ON_ERROR_STOP=1.
12. ON_ERROR_ROLLBACK uses savepoints inside a transaction, unlike stopping the script.
13. Single transaction provides all-or-nothing when all commands are transaction-compatible; do not use with CREATE DATABASE and non-transactional commands.
14. Always save logs and check the native exit code.
15. Shell pipelines need pipefail; PowerShell needs LASTEXITCODE checks.
16. Never put passwords on the command line or in source control.
17. Verify sequence values, Large Objects, constraints, indexes, ACL/RLS, and extensions after restoring.
18. Run appropriate ANALYZE and application smoke tests.
19. Never re-run a partial restore on the same target without understanding its state.
20. A restore test is the strongest proof that a dump is usable.

Tool selection and error policy flow:

~~~text
Have a dump file?
     |
     v
Identify format
     |
     +--> Plain SQL
     |       |
     |       v
     |     psql -X -v ON_ERROR_STOP=1
     |       |
     |       +--> --single-transaction if script is compatible
     |
     +--> Custom / Directory / Tar
             |
             v
          pg_restore --list
             |
             v
          Select target/objects
             |
             +--> All-or-nothing, serial:
             |       --single-transaction
             |
             +--> Parallel:
                     -j N + --exit-on-error
             |
             v
       Check exit code/log
             |
             v
       Verify schema/data/ACL
             |
             v
       ANALYZE + smoke test
             |
             v
       Switch application when criteria met
~~~

**Conclusion:** Restoring SQL dumps is a workflow that involves choosing the right tool, preparing the environment, defining the transaction/error policy, and verifying the outcome. Use **psql with ON_ERROR_STOP** for plain SQL and **pg_restore with --exit-on-error or --single-transaction** for archives as appropriate; save logs, check exit codes, and run restore tests to ensure the database is truly and completely recovered.
