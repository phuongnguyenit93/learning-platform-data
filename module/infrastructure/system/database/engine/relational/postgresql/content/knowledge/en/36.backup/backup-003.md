# `pg_dump` with Plain, Custom, Directory, and Tar Formats

`pg_dump` is PostgreSQL's logical backup tool. It connects to a single database, reads schemas and data under a consistent snapshot, and writes them to a file or directory in the chosen format. When restoration is needed, the output format determines the tool and procedure used to restore.

The four primary formats:

- **plain**: a text SQL script, typically loaded with `psql`.
- **custom**: PostgreSQL's proprietary single-file archive supporting object selection, restore reordering, and parallel restore.
- **directory**: a directory-based archive containing a TOC and separate data files; this is the format that supports parallel dump.
- **tar**: a TAR archive that `pg_restore` can read and select objects from, but does not support parallel restore.

No single format is best for every scenario. Plain fits cases needing a readable, editable script compatible with SQL tools. Custom is typically the flexible choice for single-file backups and selective restores. Directory suits large databases needing parallel dumps. Tar is useful when workflows require a TAR archive or integration with TAR tooling.

~~~mermaid
flowchart TD
    A["pg_dump database"] --> P["plain SQL"]
    A --> C["custom archive"]
    A --> D["directory archive"]
    A --> T["tar archive"]
    P --> PS["Restore with psql"]
    C --> PR["Restore with pg_restore"]
    D --> PR
    T --> PR
    D --> PD["Supports parallel dump"]
    C --> RR["Supports parallel restore"]
    D --> RR
~~~

This lesson belongs to the **Backup** chapter of the **Database Engine Relational PostgreSQL** module. We will compare file structures, compression, parallelism, dump/restore usage, object selection, owner/privilege handling, backup verification, and safe operational procedures.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain that `pg_dump` is a logical backup and define the scope of a single dump run.
2. Distinguish between plain, custom, directory, and tar formats.
3. Choose a format based on storage, restore, and operational needs.
4. Create dumps using the `-F`, `-f`, and `-Z` options.
5. Restore plain scripts using `psql`.
6. Restore archives using `pg_restore`.
7. Use `pg_restore -l` and `-L` to inspect/select object ordering.
8. Perform parallel dumps and parallel restores with the appropriate formats.
9. Distinguish parallel dump from parallel restore.
10. Use schema-only, data-only, and sections to partition scope.
11. Select tables/schemas and understand the limitations of selective dumps.
12. Manage owners, ACLs, roles, extensions, and tablespaces during restore.
13. Control errors using `ON_ERROR_STOP`, `--exit-on-error`, and single transaction mode.
14. Understand snapshot consistency and the impact of DDL/long-running transactions.
15. Verify archive files and validate via test restores.
16. Distinguish logical backups from physical backups/PITR.
17. Schedule backups, protect backup files, and record client/server versions.

## 2. `pg_dump` Is a Logical Backup

`pg_dump` exports object definitions and data of **one database** in logical form. It does not copy the cluster's physical data files verbatim.

For example, a database contains:

- Schemas and tables.
- Views/materialized views.
- Sequences.
- Indexes and constraints.
- Functions, procedures, types.
- Triggers and rules.
- Privileges/ownership depending on options.
- Large objects per dump scope.
- Extension declarations.

`pg_dump` exports components belonging to the database according to the selected scope and options. Cluster-wide objects such as roles and tablespaces are not the complete contents of a single-database dump.

### `pg_dump` Is Not a Full-Cluster Backup

A command:

~~~bash
pg_dump -d appdb -Fc -f appdb.dump
~~~

only dumps the `appdb` database. It does not automatically back up:

- Other databases in the cluster.
- Cluster-wide role definitions and role memberships.
- Tablespace definitions.
- PostgreSQL server configuration.
- WAL archives/replication slots.
- Physical files needed for PITR.

If roles/global objects are needed, you can run:

~~~bash
pg_dumpall --globals-only > globals.sql
~~~

`pg_dumpall` can export multiple databases and global objects into a SQL script, though it is a different tool/scope. Keep the role/global backup alongside the database dump to restore permissions and ownership completely.

### Logical Backups and Physical Backups Complement Each Other

Logical dumps are useful when moving a database, selecting objects, or upgrading versions. Physical base backups combined with a WAL archive suit cluster-level recovery and point-in-time recovery (PITR). Critical systems often design both around their RPO/RTO.

## 3. How to Choose a Format

| Format | Output | Restore | Parallel Dump | Parallel Restore | Object Filtering |
| --- | --- | --- | --- | --- | --- |
| Plain | Single SQL script | `psql` | No | No | Not via `pg_restore`; script can be edited |
| Custom | Single archive file | `pg_restore` | No | Yes | Yes |
| Directory | Archive directory | `pg_restore` | Yes | Yes | Yes |
| Tar | Single TAR archive | `pg_restore` | No | No | Yes |

### Selection Guidelines

- Choose **plain** if you need to read, review, edit SQL, or feed the script into deployment workflows.
- Choose **custom** for single-file backups, built-in compression, selective restore, and parallel restore.
- Choose **directory** when the database is large and dump duration matters; multiple workers can be used during the dump.
- Choose **tar** when workflows require a TAR archive or you want components packaged in a tar archive.

Custom is a sensible default for many logical backup/restore workflows due to its versatility. However, if parallel dump is the primary requirement, directory is the necessary choice.

## 4. Basic `pg_dump` Options

General syntax:

~~~bash
pg_dump [connection-options] [options] [dbname]
~~~

Common options:

| Option | Meaning |
| --- | --- |
| `-F` / `--format` | Select output format |
| `-f` / `--file` | Output file or output directory |
| `-d` / `--dbname` | Database connection string/name |
| `-h` / `--host` | PostgreSQL host |
| `-p` / `--port` | Port |
| `-U` / `--username` | Database role used to connect |
| `-W` / `--password` | Prompt for password |
| `-j` / `--jobs` | Number of parallel workers for supported formats |
| `-Z` / `--compress` | Compression for supported formats |
| `-v` / `--verbose` | Print detailed progress |
| `--no-owner` | Omit ownership commands during dump |
| `--no-acl` | Omit GRANT/REVOKE commands |
| `-C` / `--create` | Include database creation command in dump |

Connection example:

~~~bash
pg_dump -h db.example.internal -p 5432 -U backup_user -d appdb -Fc -f appdb.dump
~~~

Avoid putting passwords directly on the command line or in committed scripts. Use an appropriate authentication mechanism such as `.pgpass`, a secret manager, a service file, or interactive prompts per environment policy.

### Checking Client Versions

~~~bash
pg_dump --version
pg_restore --version
psql --version
~~~

Use client tools compatible with the server. PostgreSQL's general rule is that `pg_dump` cannot dump from a server with a newer major version than `pg_dump` itself. Newer clients can generally dump older servers within supported ranges. Output typically targets restoring into the same or newer major version; downgrading to an older major version is not guaranteed.

Always check release notes when dumping/restoring across major versions.

## 5. Plain Format

Plain is the default format if `-F` is not specified. The output is a plain-text SQL script containing object creation statements and data loading commands.

Dump:

~~~bash
pg_dump -F p -d appdb -f appdb.sql
~~~

Or:

~~~bash
pg_dump -d appdb > appdb.sql
~~~

### Advantages

- Can be opened with any text editor.
- Easy to review SQL and store in version control where appropriate.
- Can edit the script before restoring.
- Integrates easily with `psql` and Unix pipelines.
- Does not rely on `pg_restore`'s archive TOC.

### Limitations

- Does not support selective restore and reordering via `pg_restore`.
- No parallel restore.
- Script files can become huge.
- If you only need to restore one table, you must scope the dump upfront or carefully process the script.
- Manual edits can break consistency across objects.

### Restoring Plain Format with `psql`

Create the target database first:

~~~bash
createdb -T template0 appdb_restore
~~~

Then run:

~~~bash
psql -X -v ON_ERROR_STOP=1 -d appdb_restore -f appdb.sql
~~~

Meaning:

- `-X` skips reading the user's `psqlrc` file, ensuring more consistent script behavior.
- `ON_ERROR_STOP=1` tells `psql` to stop on SQL errors.
- `-d` specifies the target database.
- `-f` specifies the dump script.

Without `ON_ERROR_STOP`, `psql` may continue executing subsequent statements after an error, finishing the restore with the database in an incomplete state. Check `psql`'s exit code in automation.

### Plain Dump with CREATE DATABASE

You can generate a script including the database creation statement:

~~~bash
pg_dump -F p -C -d appdb -f appdb_create.sql
~~~

Restore via a maintenance database with privileges to create databases:

~~~bash
psql -X -v ON_ERROR_STOP=1 -d postgres -f appdb_create.sql
~~~

The script will contain commands to create and connect to the database named in the dump. If you want to restore under a different database name, it is simpler to dump without `-C`, create the target database with the new name, and load the script into it.

### Plain Scripts and Transactions

Do not blindly run every plain dump inside a single transaction. Certain commands like `CREATE DATABASE` cannot execute inside a transaction block. If using `psql -1`/`--single-transaction`, do so only when the script is compatible and tested; for scripts containing `CREATE DATABASE`, choose another workflow.

## 6. Custom Format

Custom format is selected with `-F c` or `--format=custom`:

~~~bash
pg_dump -F c -d appdb -f appdb.dump
~~~

The output is a PostgreSQL-specific archive file. The archive contains a table of contents (TOC) and schema/data components stored in the archive structure. Data items are typically compressed per this format's default configuration.

Restore using `pg_restore`, not directly with `psql`:

~~~bash
pg_restore -d appdb_restore appdb.dump
~~~

### Advantages

- Single file, easy to transfer and store.
- Includes a TOC to inspect the object list.
- Supports selecting schemas/tables/objects.
- Supports reordering restoration via the TOC list.
- Supports parallel restore.
- Built-in compression.

### Limitations

- Not directly readable as a SQL script.
- Requires `pg_restore` to unpack the archive.
- Custom format does not support parallel dump; use directory format for parallel dumps.
- Not a physical archive for cluster-wide/WAL recovery.

### Inspecting the TOC

~~~bash
pg_restore --list appdb.dump
~~~

You can save the list:

~~~bash
pg_restore --list appdb.dump > appdb.list
~~~

The TOC lets you see which objects the archive contains and prepare selective restoration. The list file can be edited to skip or reorder entries according to `pg_restore` rules.

## 7. Directory Format

Directory format is selected with `-F d`:

~~~bash
pg_dump -F d -d appdb -f appdb_dir
~~~

The output is an archive directory, typically containing TOC metadata and separate data files for tables/large objects. Do not treat this directory as a folder holding a single SQL file.

### Parallel Dump

Directory is the only `pg_dump` format that supports parallel dump:

~~~bash
pg_dump -F d -j 4 -d appdb -f appdb_dir
~~~

`-j 4` allows up to four concurrent dump workers per `pg_dump`'s mechanism. Workers use synchronized snapshots to ensure dump data stays consistent even when multiple connections read the database simultaneously.

### Operational Requirements

- The output path must be dedicated to the archive; ensure it does not overwrite other data.
- Disk space must suffice for the entire directory and overhead.
- Each worker uses a database connection; account for connection budgets.
- Too many workers can increase I/O, CPU, and load on the primary.
- Parallel dump requires a server supporting synchronized snapshots; modern PostgreSQL supports this, though check versions when dealing with legacy systems.
- The directory must be transferred/stored intact; missing component files can render the archive unrestorable.

### Advantages

- Parallel dump, which can shorten dump times on large databases.
- Each table/data object has its own file.
- Supports parallel restore.
- Supports selective restore and reordering.
- Supports data file compression per available options.

### Limitations

- Managing multiple files/directories instead of a single file.
- Copying, uploading, checksumming, and retention must apply to the entire directory.
- Do not delete or rename files inside the archive.
- High parallelism can overload the primary.

## 8. Tar Format

Tar format is selected with `-F t`:

~~~bash
pg_dump -F t -d appdb -f appdb.tar
~~~

This is a TAR-format archive readable by `pg_restore`:

~~~bash
pg_restore -d appdb_restore appdb.tar
~~~

### Characteristics

- Single archive file.
- Has a TOC for object selection and restore reordering.
- Does not support parallel dump.
- `pg_restore` parallel restore only supports custom and directory, so do not choose tar if parallel restore is required.
- Tar format lacks built-in compression like custom/directory. If you compress a tar archive with an external tool, decompress it before passing it to `pg_restore`, unless the workflow handles decompression separately.

### When to Choose Tar?

- Archival tooling or internal pipelines mandate TAR.
- You need components packaged in a standard archive format.
- Parallel dump/restore is not needed.
- External compression handling is acceptable if needed.

Do not confuse a tar file from `pg_dump` with a physical backup of PostgreSQL's data directory.

## 9. Compression Across Formats

Compression can reduce storage size and network transfer at the cost of CPU time.

| Format | Compression |
| --- | --- |
| Plain | No built-in compression; can compress output externally |
| Custom | Built-in compression |
| Directory | Compression for data files |
| Tar | No built-in compression; can compress archive externally |

The `-Z`/`--compress` option controls compression for supported formats. Syntax and compression methods depend on the PostgreSQL major version and client build. Check `pg_dump --help` and version-specific docs instead of assuming a method is always available.

Illustrative example:

~~~bash
pg_dump -F c -Z 6 -d appdb -f appdb.dump
~~~

Level `6` is an example of the compression level syntax supported in corresponding versions; newer releases may offer additional ways to specify methods/details.

### Choosing Compression by Bottleneck

- Spare CPU, slow network/disk: compression can help.
- CPU already busy: heavy compression can slow down the dump.
- Local backup on fast storage: you may prioritize speed.
- Backup sent over network: compression can save bandwidth.
- Need fast restore: measure both dump time and restore time, not just file size.

Compression ratio depends on the data. Repetitive JSON/text typically compresses far better than pre-compressed or high-entropy data.

## 10. Parallel Dump and Parallel Restore

These two features are independent:

| Operation | Supported Formats | Option |
| --- | --- | --- |
| Parallel dump | Directory | `pg_dump -Fd -j N` |
| Parallel restore | Custom, directory | `pg_restore -j N` |
| Parallel dump custom | No | Not supported |
| Parallel restore tar | No | Not supported |
| Parallel restore plain | No | Uses sequential `psql` script |

### Parallel Restore Custom

~~~bash
pg_restore -j 4 -d appdb_restore appdb.dump
~~~

### Parallel Restore Directory

~~~bash
pg_restore -j 4 -d appdb_restore appdb_dir
~~~

`pg_restore` coordinates restore jobs that can execute concurrently based on dependencies and the archive TOC. Not all objects can run concurrently; some steps require ordering or serialization.

### Choosing Worker Count

Start small and benchmark. Consider:

- Source/target CPU.
- Disk throughput and IOPS.
- Network bandwidth.
- Allowed connection count.
- Index builds and constraint validation.
- WAL generation/replay.
- Lock contention.
- Concurrent application workloads.

Increasing `-j` does not guarantee linear speedup. Once target storage saturates, adding more workers can make restore slower.

## 11. Restoring Custom Archives with `pg_restore`

Create the target database:

~~~bash
createdb -T template0 appdb_restore
~~~

Restore:

~~~bash
pg_restore -d appdb_restore --exit-on-error appdb.dump
~~~

With parallelism:

~~~bash
pg_restore -j 4 -d appdb_restore --exit-on-error appdb.dump
~~~

If the target database does not exist and you want to create it from archive metadata:

~~~bash
pg_restore -C -d postgres --exit-on-error appdb.dump
~~~

In the final example, the initial connection goes to the `postgres` database so `pg_restore` can create the target database named inside the archive. The `-C` option does not rename the database to whatever is passed to `-d`; treat `-d` as the initial connection database when using create.

## 12. Restoring Directory and Tar Archives

Directory:

~~~bash
pg_restore -d appdb_restore --exit-on-error appdb_dir
~~~

Tar:

~~~bash
pg_restore -d appdb_restore --exit-on-error appdb.tar
~~~

You can add object selection or clean options similar to custom archives. However, only custom/directory support parallel restore.

### `pg_restore` Detects Archive Formats

`pg_restore` reads custom, directory, and tar archives. Plain SQL is not valid input for `pg_restore`; use `psql`.

If you accidentally pass a plain file to `pg_restore`, the tool reports an invalid format error. Do not rename file extensions to turn a SQL script into an archive.

## 13. Inspecting and Editing the TOC List

For custom/directory/tar:

~~~bash
pg_restore -l appdb.dump > appdb.list
~~~

You can edit the list file to omit certain entries or adjust restore order, then run:

~~~bash
pg_restore -L appdb.list -d appdb_restore appdb.dump
~~~

`-L`/`--use-list` tells `pg_restore` to restore only the listed entries in the order given in the list file. Lines commented out or removed from the list will not be restored.

### When to Use a TOC List?

- Skipping a large data table unnecessary in a test environment.
- Restoring schemas first and data later in a custom workflow.
- Skipping an object incompatible with the target.
- Selectively recovering objects after an incident.

### Risks

Objects have dependencies. If you omit a table while keeping views/functions/constraints depending on that table, restore may fail. Filtering does not automatically resolve the full dependency graph; you must understand the schema and test restores in a staging environment.

## 14. Dumping and Restoring by Schema/Table

You can narrow the dump scope:

~~~bash
pg_dump -F c -n sales -d appdb -f sales.dump
~~~

Dump a single table:

~~~bash
pg_dump -F c -t sales.orders -d appdb -f orders.dump
~~~

Dump schema only:

~~~bash
pg_dump -F c --schema-only -d appdb -f schema.dump
~~~

Dump data only:

~~~bash
pg_dump -F c --data-only -d appdb -f data.dump
~~~

With an archive, restore can filter by schema/table:

~~~bash
pg_restore -n sales -d appdb_restore sales.dump
~~~

~~~bash
pg_restore -t orders -n sales -d appdb_restore orders.dump
~~~

### Selective Dumps Do Not Automatically Include All Dependencies

Dumping a single table does not necessarily bring along every type, function, schema, extension, or dependent object the table needs. When restoring into an empty database, you may need a broader schema dump or pre-created dependencies.

When using `--schema`/`--table`, inspect selected objects and test the restore. Pattern matching in `pg_dump`/`pg_restore` follows specific rules; use schema qualification and proper quoting when names contain special characters.

## 15. Sections: `pre-data`, `data`, and `post-data`

Archives can be divided into sections:

- **pre-data**: most schema definitions required before loading data, such as tables/types.
- **data**: table data, large objects, and data components.
- **post-data**: many indexes, triggers, constraints, and objects created after data loading.

Example restoring section by section:

~~~bash
pg_restore --section=pre-data -d appdb_restore appdb.dump
pg_restore --section=data -d appdb_restore appdb.dump
pg_restore --section=post-data -d appdb_restore appdb.dump
~~~

Sections are useful when designing multi-step workflows—such as creating tables first, loading data, and then building indexes/constraints. Maintain proper dependencies and transaction context.

Do not blindly run these three commands in parallel; `post-data` depends on data and schemas from earlier phases.

## 16. Owner, ACL, and Role

Dumps can include commands setting ownership and privileges. When restoring to a different environment, source roles may not exist.

You can omit ownership and ACLs:

~~~bash
pg_dump -Fc --no-owner --no-acl -d appdb -f appdb.dump
~~~

Or apply at restore time:

~~~bash
pg_restore --no-owner --no-acl -d appdb_restore appdb.dump
~~~

Differences:

- `--no-owner`: suppresses commands that set object ownership as recorded in the dump.
- `--no-acl`: omits `GRANT`/`REVOKE` commands stored in the archive.
- `--role=target_role`: instructs `pg_restore` to execute `SET ROLE` after connecting (if permitted).

These options do not create roles. If ownership and grants must be preserved intact, dump/restore global roles first, or create matching roles on the target.

### Do Not Drop ACLs Out of Habit

In production, access privileges are part of database security. If you omit ACLs to simplify restoring, include an explicit step to reapply privileges before opening the database to applications.

## 17. Extensions and Tablespaces

`pg_dump` records commands needed to create extensions in the database per metadata, but does not bundle server extension binaries. The target must have compatible extension packages installed before restoring.

Example:

~~~sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
~~~

This is only an example extension declaration; the corresponding package must exist on the target server.

Tablespace definitions are global objects. If a dump assigns objects to specific tablespaces, the target must have matching tablespaces or use options such as `--no-tablespaces` during dump/restore as appropriate.

### Dependency Checklist

- Roles and memberships.
- Tablespaces.
- Extension packages/versions.
- Locale/collation.
- Encoding.
- Database-level settings.
- Foreign data wrappers/servers and environment-specific credentials.
- External functions/libraries.
- Application-specific secrets/configuration.

A database dump cannot replace a system-wide dependency inventory.

## 18. Large Objects

PostgreSQL supports large objects (LO) separately from regular column TOAST storage. `pg_dump` provides `--blobs`/`-b` and `--no-large-objects` options to control large object dumping depending on version and chosen scope.

If the application uses the LO API, verify the dump includes the large objects referenced by the application. Do not confuse LO with `bytea`/TOAST column data; they are two separate mechanisms.

When dumping selectively by table/schema, check the docs because large object inclusion can differ from a full-database dump.

## 19. Handling Errors During Restore

### Plain Script

Use:

~~~bash
psql -X -v ON_ERROR_STOP=1 -d appdb_restore -f appdb.sql
~~~

Check `psql`'s exit code. When running in shell scripts, enable appropriate error handling and save stdout/stderr to protected logs.

### Archive

Use:

~~~bash
pg_restore --exit-on-error -d appdb_restore appdb.dump
~~~

By default, `pg_restore` may continue past some errors and report a summary of errors. `--exit-on-error` tells it to abort on the first error.

### Single Transaction

For archives you can request:

~~~bash
pg_restore --single-transaction --exit-on-error -d appdb_restore appdb.dump
~~~

This wraps the restore in a single transaction, providing all-or-nothing behavior when all commands are compatible. However:

- Cannot be combined with parallel jobs.
- Very large transactions can hold locks/resources for a long time.
- Certain commands cannot run inside a transaction block.
- A failed restore rolls back everything, which can consume significant time and WAL.

Do not mechanically enable single transaction for every large database.

## 20. Cleaning Before Restore

Option:

~~~bash
pg_restore --clean --if-exists -d appdb_restore appdb.dump
~~~

- `--clean`: issues `DROP` commands for objects before recreating them.
- `--if-exists`: adds `IF EXISTS` to drop statements where possible.

Caution: `--clean` can drop existing objects in the target database. Use only against a verified target database with appropriate backups/approval.

If restoring into a fresh database created from `template0`, cleaning is usually unnecessary.

## 21. Consistent Dump Snapshots and Concurrent Writes

`pg_dump` uses a snapshot so data is read consistently throughout the dump. Concurrent `INSERT`/`UPDATE`/`DELETE` operations can still proceed for most of the run; dumping is not a whole-database write lock.

However:

- `pg_dump` acquires appropriate read locks on relations.
- DDL requiring strong locks may block or conflict with the dump.
- Long-running transactions can hold back snapshots and affect vacuum.
- Extended dumps can increase storage/cache pressure.
- Parallel dumps use synchronized snapshots so workers see the same data state.

Do not treat dumps as completely zero-impact on production. Pick suitable windows, watch load, and avoid major DDL during dumps.

### Dumping from a Replica

Some environments dump from a standby to offload the primary. Verify permissions, standby state, recovery conflicts, and version support. Dumps from a standby can be canceled due to recovery conflicts or impacted by replay workloads. Check logs and `hot_standby` policies before deploying.

## 22. Dumping with a Connection String

You can pass a connection string:

~~~bash
pg_dump -Fc "host=db.internal port=5432 dbname=appdb user=backup_user sslmode=verify-full" -f appdb.dump
~~~

In automation, avoid placing passwords directly in command lines where they can appear in process lists/logs. Use `.pgpass`, a service file, or a protected secret manager.

Common environment variables:

- `PGHOST`
- `PGPORT`
- `PGDATABASE`
- `PGUSER`
- `PGSERVICE`
- `PGPASSFILE`

Avoid setting `PGPASSWORD` persistently in shared environments when safer mechanisms exist.

## 23. Example: Custom Dump and Restore to Another Database

Dump:

~~~bash
pg_dump -Fc -v -d appdb -f appdb_2026.dump
~~~

Create target database:

~~~bash
createdb -T template0 appdb_test_restore
~~~

Restore:

~~~bash
pg_restore -v --exit-on-error -d appdb_test_restore appdb_2026.dump
~~~

Verify:

~~~bash
psql -d appdb_test_restore -c "SELECT count(*) FROM public.orders;"
~~~

A count is only a sample check. For critical data, cross-check row counts, constraints, sequences, large objects, and business invariants.

## 24. Example: Parallel Directory Dump

~~~bash
pg_dump -Fd -j 4 -v -d appdb -f appdb_directory
~~~

Inspect TOC:

~~~bash
pg_restore -l appdb_directory > appdb_directory.list
~~~

Parallel restore:

~~~bash
createdb -T template0 appdb_restore
pg_restore -j 4 --exit-on-error -d appdb_restore appdb_directory
~~~

Keep the entire directory intact during copying/retention. If using object storage, upload every file and verify pipeline-generated manifests/checksums.

## 25. Example: Tar Dump and Restore

~~~bash
pg_dump -Ft -v -d appdb -f appdb.tar
~~~

List contents:

~~~bash
pg_restore -l appdb.tar
~~~

Restore:

~~~bash
pg_restore --exit-on-error -d appdb_restore appdb.tar
~~~

Do not pass `-j` expecting parallel restore on tar; the tar format does not support that mode.

## 26. Example: Externally Compressed Plain Dump

You can compress a SQL script using an external tool:

~~~bash
pg_dump -Fp -d appdb | gzip > appdb.sql.gz
~~~

Restore:

~~~bash
gzip -dc appdb.sql.gz | psql -X -v ON_ERROR_STOP=1 -d appdb_restore
~~~

The pipeline must check exit statuses of both processes. In Bash you can use `set -o pipefail`; in PowerShell handle each process's exit code via its mechanism.

External compression shrinks plain dump size, but the script still must be decompressed/streamed through `psql`; you cannot pass a `.gz` file directly into `pg_restore`.

## 27. Verifying an Archive Before Restore

For custom/directory/tar:

~~~bash
pg_restore --list appdb.dump
~~~

If the command reads the TOC, it signals the archive header/metadata is readable. However, it **does not prove the entire data payload is complete or will restore successfully**.

You can check file checksums after copying:

~~~bash
sha256sum appdb.dump
~~~

On Windows use an equivalent checksum tool such as `Get-FileHash`. For directory archives, checksum each file or maintain a manifest covering all component files.

### Non-Zero File Size Does Not Prove a Good Backup

A dump file can be truncated, missing data segments, or unrestorable. `pg_dump` exit codes, logs, checksums, and test restores are complementary verification layers.

## 28. Test Restore Is a Critical Verification Step

A backup is only valuable if it can restore within the required time.

Periodic procedure:

1. Select a representative backup.
2. Create a compatible test database/cluster.
3. Prepare needed roles, tablespaces, and extensions.
4. Restore using the production workflow.
5. Record restore duration.
6. Verify object counts, row counts, and constraints.
7. Run smoke tests/business queries.
8. Verify owners, ACLs, sequences, and large objects.
9. Measure RTO and compare against target.
10. Document errors and improve the runbook.

Do not just run `pg_restore -l` and treat the backup as verified.

## 29. Securing and Storing Dump Files

Logical dumps usually contain application data in recoverable or readable form. Protect them like production data.

- Encrypt in transit and at rest.
- Restrict file/directory read permissions.
- Do not upload to public buckets.
- Do not commit dumps to Git repositories.
- Do not attach dumps to unauthorized tickets/chats.
- Enforce encryption/key management per policy.
- Define clear retention and lifecycle rules.
- Securely delete temporary copies per policy after restore.
- Audit who creates, downloads, and restores backups.
- Never log credentials in shell history or logs.

Custom archives may compress data, but compression is not encryption.

## 30. Impact of `pg_dump` on Production

Large dumps can consume:

- CPU for serialization and compression.
- I/O reading heap/index/TOAST pages.
- Network bandwidth if the client runs on another host.
- Connections for workers.
- Cache bandwidth.
- Snapshot retention during the dump window.

To reduce impact:

- Run off-peak when possible.
- Dump from a replica when architecture allows.
- Tune `-j` according to real load.
- Avoid aggressive compression when CPU is bottlenecked.
- Use `--verbose` to monitor progress.
- Watch database latency, disk throughput, and replica lag.
- Avoid running multiple large dumps concurrently on the same storage.

## 31. Dumping and Restoring Sequence Values

`pg_dump` stores sequence state in the dump so sequences can resume from the backed-up state per the restore behavior. When dumping only a single table or data/schema separately, verify sequence dependencies and ownership.

After restore, verify:

- Sequences exist.
- `OWNED BY` points to the right column if the schema uses identity/serial.
- Sequence values align with restored data.
- New inserts do not collide with existing primary keys.

Do not blindly reset sequences to `MAX(id)` in every case without understanding increment, cycle, cache, and concurrent workloads.

## 32. Do Dumps Include Users/Roles?

`pg_dump` does not dump cluster-wide role definitions. It can dump object ownership and ACLs inside the database.

Therefore, there are two scenarios:

- **Restore preserving owner/ACL**: create required roles and memberships on the target beforehand.
- **Restore without preserving owner/ACL**: use `--no-owner` `--no-acl`, then apply the target environment's security policy.

Global backup:

~~~bash
pg_dumpall --globals-only > globals.sql
~~~

The global script may contain role attributes, memberships, and tablespace definitions; protect the file because it holds sensitive configuration/privilege details.

## 33. The `--no-tablespaces` Option

If you do not want to restore objects into the source tablespaces, you can omit tablespace assignments with the appropriate option:

~~~bash
pg_dump -Fc --no-tablespaces -d appdb -f appdb.dump
~~~

This helps when moving from an environment with custom storage layouts to a target using the default tablespace. Still check target disk space and storage policy; omitting tablespace metadata does not shrink the data itself.

## 34. Schema-Only Dump for Inspection/Migration

~~~bash
pg_dump --schema-only -d appdb -f appdb_schema.sql
~~~

Used for:

- DDL reviews.
- Comparing schemas across environments.
- Provisioning test environments.
- Inspecting index/constraint/function definitions.
- Preparing migration plans.

Schema-only contains no table data. It also does not replace a full schema diff tool when detecting semantic and dependency changes.

## 35. Data-Only Dump

~~~bash
pg_dump --data-only -Fc -d appdb -f appdb_data.dump
~~~

Data-only can be useful when schemas are deployed separately. However, restoring data requires matching table definitions, types, sequences, constraints, and dependencies.

For large data loads, you may need to coordinate triggers/constraints/indexes using a proper workflow. Do not disable triggers/constraints carelessly; doing so can leave invalid data behind.

## 36. Dumping Selected Tables for Test Environments

~~~bash
pg_dump -Fc \
  -t public.customers \
  -t public.products \
  -d appdb \
  -f sample_data.dump
~~~

This is an example of table selection, though it may omit dependent objects. If restoring into a new database, ensure required schemas, types, sequences, and functions already exist.

You can use `--exclude-table-data` to dump a table's schema while excluding its data by pattern. Inspect the resulting TOC before restoring.

## 37. Restoring into an Existing Database

If the target database already has objects with conflicting names, restore may fail with object-exists or constraint errors.

Options:

- Create an empty database from `template0`.
- Use `--clean` `--if-exists` if replacing objects intentionally and scope is verified.
- Restore schema/data in phases.
- Use a TOC list to pick objects.
- Restore into a temporary database, verify, and then switch the application.

Never run `--clean` against a live production database merely to suppress duplicate-object errors.

## 38. Optimizing Large Restores

Several strategies:

- Use custom/directory for parallel restore.
- Match job count to CPU/IO capacity.
- Restore schema/data/post-data in phases when needed.
- Pre-create extensions and roles.
- Check tablespaces/disk space.
- Ensure the target has sufficient WAL/disk headroom.
- Avoid competing query workloads during restore.
- Monitor `pg_stat_activity`, progress, and server logs.
- Run `ANALYZE` after bulk restore if fresh planner statistics are needed.

Do not manually disable constraints/triggers without a procedure to rebuild and validate them. `pg_restore` orders objects via TOC/dependencies; keep default behavior unless you have a clear reason.

## 39. Common Mistakes

1. **Creating a plain dump and calling `pg_restore`**, whereas plain SQL must be run with `psql`.
2. **Feeding a custom archive to `psql`**, even though archives are not SQL scripts.
3. **Choosing custom while expecting parallel dump**, whereas parallel dump only supports directory format.
4. **Choosing tar while expecting parallel restore**, whereas parallel restore only supports custom/directory.
5. **Confusing dump `-j` with restore `-j`**, as the two options run in different tools with distinct format restrictions.
6. **Setting jobs too high**, driving up CPU/I/O/connection pressure.
7. **Assuming `pg_dump` backs up the entire cluster**, when it dumps a single database.
8. **Forgetting roles/tablespaces**, causing owner/ACL or storage restoration to fail.
9. **Omitting ACLs without a step to reapply permissions**, leaving the target with an incorrect security posture.
10. **Failing to install extensions on the target**, causing `CREATE EXTENSION` to fail.
11. **Restoring into a populated database without checking object conflicts**.
12. **Using `--clean` without understanding DROP scope**, risking deletion of live objects.
13. **Omitting `ON_ERROR_STOP`/`--exit-on-error`**, letting scripts continue past errors.
14. **Combining single transaction with parallel jobs**, which is unsupported.
15. **Passing `-C` while connecting to a database lacking privileges**, or misunderstanding the created database name.
16. **Dumping a single table and assuming all dependencies are included**, leading to missing types/functions/schemas on restore.
17. **Failing to verify client/server versions**, causing incompatibilities.
18. **Failing to verify large objects**, especially when applications use the LO API.
19. **Renaming or deleting files inside a directory archive**, leaving the archive incomplete.
20. **Compressing tar and feeding the compressed file directly to `pg_restore`**, even though decompression is needed first.
21. **Treating `pg_restore -l` as a full restore test**, when it primarily reads the TOC.
22. **Checking only file size**, omitting exit codes/checksums/test restores.
23. **Ignoring disk/WAL/replication lag**, causing storage exhaustion or lag spikes.
24. **Skipping RTO testing**, only discovering restores are too slow during an incident.
25. **Storing dumps unencrypted or with overly broad permissions**, exposing sensitive data.
26. **Using logical dumps as a substitute for PITR**, without base backups/WAL archives.
27. **Forgetting `ANALYZE` after a large import**, leaving the planner with stale statistics.
28. **Manually editing plain SQL scripts without reviewing dependencies**, producing incomplete restores.

## 40. Practice Exercises with Answers

### Exercise 1. What type of backup is `pg_dump`?

**Answer:** A logical backup of a single database, exporting object definitions and data using a consistent snapshot.

### Exercise 2. Does `pg_dump` back up all roles?

**Answer:** No. Use `pg_dumpall --globals-only` or a dedicated global-object workflow.

### Exercise 3. Which tool restores plain format?

**Answer:** `psql`.

### Exercise 4. Which tool restores custom format?

**Answer:** `pg_restore`.

### Exercise 5. Selecting custom format

~~~bash
pg_dump -Fc -d appdb -f appdb.dump
~~~

**Answer:** Creates a custom archive file.

### Exercise 6. Selecting directory format

~~~bash
pg_dump -Fd -d appdb -f appdb_dir
~~~

**Answer:** Creates a directory archive.

### Exercise 7. Which format supports parallel dump?

**Answer:** Directory format.

### Exercise 8. Which formats support parallel restore?

**Answer:** Custom and directory.

### Exercise 9. Does tar support parallel restore?

**Answer:** No.

### Exercise 10. Restoring a plain script

~~~bash
psql -X -v ON_ERROR_STOP=1 -d appdb_restore -f appdb.sql
~~~

**Answer:** Runs the SQL script and stops on errors.

### Exercise 11. Restoring a custom archive

~~~bash
pg_restore -d appdb_restore appdb.dump
~~~

**Answer:** Restores the archive into the target database.

### Exercise 12. Inspecting the archive TOC

~~~bash
pg_restore -l appdb.dump
~~~

**Answer:** Lists the archive entries.

### Exercise 13. Using a TOC list to select objects

~~~bash
pg_restore -l appdb.dump > list.txt
pg_restore -L list.txt -d appdb_restore appdb.dump
~~~

**Answer:** Restores the entries in the list in the order given by the list.

### Exercise 14. Parallel dump with four workers

~~~bash
pg_dump -Fd -j 4 -d appdb -f appdb_dir
~~~

**Answer:** Directory format with up to four workers.

### Exercise 15. Parallel restore with four workers

~~~bash
pg_restore -j 4 -d appdb_restore appdb.dump
~~~

**Answer:** Parallel restore when the archive is custom or directory format.

### Exercise 16. Schema-only dump

~~~bash
pg_dump --schema-only -d appdb -f schema.sql
~~~

**Answer:** Exports definitions without table data.

### Exercise 17. Data-only dump

~~~bash
pg_dump --data-only -Fc -d appdb -f data.dump
~~~

**Answer:** Exports data; requires matching schemas on the target.

### Exercise 18. Dumping a single schema

~~~bash
pg_dump -Fc -n sales -d appdb -f sales.dump
~~~

**Answer:** Selects objects in the `sales` schema per `pg_dump` pattern matching.

### Exercise 19. Dumping a single table

~~~bash
pg_dump -Fc -t sales.orders -d appdb -f orders.dump
~~~

**Answer:** Selects the `orders` table; other dependencies may need separate dumping.

### Exercise 20. Omitting owner and ACL

**Answer:** Use `--no-owner` `--no-acl` during dump or restore, then apply the target's security policy.

### Exercise 21. Creating a database from an archive

~~~bash
pg_restore -C -d postgres appdb.dump
~~~

**Answer:** Connects to the `postgres` database and creates the database per metadata inside the archive.

### Exercise 22. Why must a directory dump keep the entire folder?

**Answer:** The archive consists of a TOC and multiple data files; missing any component file can make restore fail.

### Exercise 23. Why doesn't custom support parallel dump?

**Answer:** `pg_dump` implements parallel dump only for directory format.

### Exercise 24. Why isn't tar a physical backup?

**Answer:** Tar contains a logical archive created by `pg_dump`, not the cluster's physical data files/WAL.

### Exercise 25. Can `--single-transaction` be combined with `-j`?

**Answer:** No. Parallel restore is incompatible with single transaction mode.

### Exercise 26. What does `pg_restore -l` prove?

**Answer:** That the archive TOC is readable; it does not prove the full payload restores cleanly.

### Exercise 27. How do you verify a backup is good?

**Answer:** Check exit codes/logs/checksums and perform periodic test restores followed by smoke tests.

### Exercise 28. Why prepare extensions before restoring?

**Answer:** `pg_dump` stores declarations, not server extension binaries.

### Exercise 29. Is a dump consistent while the application keeps writing?

**Answer:** `pg_dump` uses a consistent snapshot; DML can continue for most of the run, though DDL/locks and snapshot retention still require attention.

### Exercise 30. Does a logical dump replace PITR?

**Answer:** No. PITR requires a physical base backup and an appropriate WAL archive.

## 41. Format Selection and Operations Checklist

- [ ] Determine whether you only need a single-database dump or global objects/cluster backup.
- [ ] Choose plain, custom, directory, or tar based on the restore workflow.
- [ ] Use plain when you need a SQL script and `psql` restore.
- [ ] Use custom when you need a flexible single-file archive.
- [ ] Use directory if you need parallel dump.
- [ ] Use custom/directory if you need parallel restore.
- [ ] Do not expect tar to support parallel restore.
- [ ] Check `pg_dump`/`pg_restore` client versions.
- [ ] Use secure authentication; never pass passwords on the command line.
- [ ] Account for CPU, I/O, network, and connection budgets.
- [ ] Choose compression based on bottlenecks.
- [ ] Keep the entire directory archive with no missing files.
- [ ] Dump roles/global objects when needed.
- [ ] Prepare roles, tablespaces, and extensions on the target.
- [ ] Decide intentionally whether to keep or omit owner/ACL.
- [ ] Check large objects and sequence state.
- [ ] Use `ON_ERROR_STOP`/`--exit-on-error` and verify exit codes.
- [ ] Use `--clean` only after confirming DROP scope.
- [ ] Do not combine single transaction with parallel restore.
- [ ] Inspect the TOC before selective restore.
- [ ] Test restores in a compatible environment.
- [ ] Measure RTO and verify data/objects/permissions.
- [ ] Protect dumps with encryption, access controls, and retention.
- [ ] Monitor WAL/replication lag during large backups/restores.
- [ ] Maintain physical backups/WAL archives if PITR is required.

## 42. Official PostgreSQL Documentation

Consult according to your deployed major version:

- [pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html) — options, formats, parallel dump, snapshots, and compression.
- [pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html) — archive restore, TOC lists, parallel jobs, and selective restore.
- [psql](https://www.postgresql.org/docs/current/app-psql.html) — executing plain SQL scripts, `ON_ERROR_STOP`, and single transactions.
- [pg_dumpall](https://www.postgresql.org/docs/current/app-pg-dumpall.html) — dumping multiple databases and global objects.
- [Backup and Restore](https://www.postgresql.org/docs/current/backup.html) — overview of logical/physical backups.
- [SQL Dump](https://www.postgresql.org/docs/current/backup-dump.html) — logical dumps and restores.
- [Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html) — base backups, WAL, and PITR.
- [Client Connection Defaults](https://www.postgresql.org/docs/current/libpq-envars.html) — `libpq` environment variables.
- [The Password File](https://www.postgresql.org/docs/current/libpq-pgpass.html) — password file configuration.
- [CREATE EXTENSION](https://www.postgresql.org/docs/current/sql-createextension.html) — extension installation on targets.
- [Database Roles](https://www.postgresql.org/docs/current/user-manag.html) — role and privilege management.
- [Tablespaces](https://www.postgresql.org/docs/current/manage-ag-tablespaces.html) — tablespace definitions and storage.

`/current/` URLs point to the current PostgreSQL documentation. Compression methods, archive options, progress reporting, and certain restrictions can vary across major versions/builds; verify documentation for your exact client/server version before operating.

## 43. Summary

**`pg_dump` creates a logical backup for a single database; plain is a SQL script, whereas custom, directory, and tar are archives for `pg_restore`.** The format must be chosen around actual dump, storage, and restore workflows.

1. **Plain** is readable and restored with `psql`, but lacks selective/parallel restore via `pg_restore`.
2. **Custom** creates a single archive file with built-in compression, TOC, and parallel restore.
3. **Directory** stores a TOC alongside separate data files and is the only format supporting parallel dump; it also supports parallel restore.
4. **Tar** is a TAR archive supporting object selection on restore, but does not support parallel dump/restore.
5. **Parallel dump and parallel restore are separate capabilities.** Directory supports parallel dump; custom/directory support parallel restore.
6. **`pg_dump` backs up only one database.** Roles and global objects require separate workflows such as `pg_dumpall --globals-only`.
7. **Owners, ACLs, extensions, and tablespaces must be prepared when restoring** into another environment.
8. **Selective dumps can miss dependencies.** Inspect the TOC and test restores before relying on an archive.
9. **Verify exit codes, checksums, and real restores.** Reading the TOC successfully does not prove the entire backup is valid.
10. **Size compression, worker counts, disk, WAL, and replica lag** to source/target capacity.
11. **Protect dump files like production data** using encryption, access control, and retention.
12. **Logical dumps do not replace physical backups/PITR.** Select your backup strategy according to your system's RPO/RTO.

A solid backup process does not end when `pg_dump` returns success. It must also protect the files, verify integrity, and prove that the operations team can restore data within the required time.
