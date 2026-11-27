# pg_restore, Object Selection, and Parallel Restore in PostgreSQL

`pg_restore` is the tool for restoring logical backups created by `pg_dump` in archive formats: custom, directory, and tar. It reads the table of contents (TOC), recreates schema objects, loads data, and can coordinate multiple restore jobs simultaneously. Thanks to the TOC, operators can select objects, split the restore into sections, or adjust the execution order.

A restore is more than running a single command. You must prepare the target database, roles, extensions, tablespaces, access privileges, and object dependencies. For large databases, you need to balance the worker count against CPU, I/O, WAL, connection limits, and replication lag.

Key decisions:

- Choose the right tool for the format: psql for plain SQL, pg_restore for archives.
- Choose object scope based on dependencies, not just table names.
- Use parallel restore when the archive and workload are suitable.
- Control errors, transactions, locks, and DROP operations.
- Verify the database after restoring using catalogs, data checks, and smoke tests.

~~~mermaid
flowchart TD
    A["Receive backup"] --> B{"Format?"}
    B -->|"Plain SQL"| C["psql"]
    B -->|"Custom / Directory / Tar"| D["pg_restore"]
    D --> E["Read TOC"]
    E --> F["Select all or objects/sections"]
    F --> G["Prepare database and dependencies"]
    G --> H{"Parallelizable?"}
    H -->|"Custom or Directory"| I["pg_restore -j N"]
    H -->|"Tar or single transaction needed"| J["Serial restore"]
    C --> K["Load SQL script"]
    I --> L["Check errors and results"]
    J --> L
    K --> L
    L --> M["Smoke tests and handover"]
~~~

This lesson belongs to the **Recovery** chapter of the **Database Engine Relational PostgreSQL** module. We will progress from archive structure and TOC to selective restore, parallel jobs, error handling, ownership, progress monitoring, and repeatable recovery workflows.

## 1. Learning Objectives

After this lesson, you can:

1. Explain the role of pg_restore in a logical backup workflow.
2. Distinguish pg_restore from psql.
3. Identify custom, directory, and tar archives.
4. Read a TOC using pg_restore -l.
5. Select objects using --use-list, --schema, --table, and related options.
6. Understand why selective restore can miss dependencies.
7. Split restores across pre-data, data, and post-data.
8. Prepare the target database and global dependencies.
9. Control ownership, ACLs, roles, and tablespaces.
10. Use --clean, --if-exists, and --create within the proper scope.
11. Understand --exit-on-error and --single-transaction.
12. Choose an appropriate parallel job count for your resources.
13. Distinguish parallel restore from parallel dump.
14. Understand why tar does not support parallel restore.
15. Monitor a restore using progress views, pg_stat_activity, and logs.
16. Recover after a partial restore fails.
17. Verify sequences, constraints, indexes, and large objects.
18. Plan testing, RTO, and recovered data security.

## 2. What Does pg_restore Do?

pg_restore reads archives created by pg_dump in custom, directory, or tar format. An archive contains metadata describing components such as:

- Schema definitions.
- Table data.
- Sequences and sequence values.
- Indexes.
- Constraints.
- Triggers and rules.
- Functions, procedures, types.
- Views and materialized views.
- Large objects.
- Ownership and ACL metadata, if included in the dump.

pg_restore can generate SQL commands from the archive or connect directly to the target database to execute those commands.

### Two Primary Usage Modes

Export an SQL script for review:

~~~bash
pg_restore --file=restore.sql appdb.dump
~~~

Connect and restore directly:

~~~bash
pg_restore --dbname=appdb_restore appdb.dump
~~~

When outputting a script with --file, you can open and review the contents before executing. When restoring directly with --dbname, pg_restore runs the commands against the target database.

### pg_restore Does Not Read Plain SQL Dumps

If a file was created with:

~~~bash
pg_dump -Fp -d appdb -f appdb.sql
~~~

then restore it with:

~~~bash
psql -X -v ON_ERROR_STOP=1 -d appdb_restore -f appdb.sql
~~~

Do not pass a plain SQL file to pg_restore. Renaming the file extension does not change its actual format.

## 3. Formats Supported by pg_restore

| Format | Indicator | Restore tool | Parallel restore |
| --- | --- | --- | --- |
| Plain | SQL text | psql | No |
| Custom | Single-file PostgreSQL archive | pg_restore | Yes |
| Directory | Archive directory with TOC and data files | pg_restore | Yes |
| Tar | TAR archive | pg_restore | No |

### Custom

Custom format is typically selected with:

~~~bash
pg_dump -Fc -d appdb -f appdb.dump
~~~

This is a single archive file with a TOC, supporting object selection and parallel restore.

### Directory

Directory format:

~~~bash
pg_dump -Fd -d appdb -f appdb_dir
~~~

The archive directory contains a TOC and data files. It supports both parallel dump and parallel restore.

### Tar

Tar format:

~~~bash
pg_dump -Ft -d appdb -f appdb.tar
~~~

pg_restore can read the TOC and select objects in a tar archive, but it does not support parallel restore for this format.

### Why Does Format Affect Restores?

Custom and directory formats store archive entries in a structure that allows pg_restore to schedule work and launch multiple workers. Plain is a sequential stream of SQL commands; tar lacks a parallel restore mechanism supported by pg_restore. Therefore, choose the format at backup time based on recovery needs—you cannot change the format by renaming the file.

## 4. Checking Tool Versions

Before restoring:

~~~bash
pg_restore --version
psql --version
pg_dump --version
~~~

Use client tools compatible with the target server version. Archive formats and options can change across major versions.

Key operational rules:

- An older pg_restore client may not understand an archive created by a newer pg_dump.
- Restoring onto the same major version or a newer major version is the standard deployment path.
- Restoring backward to an older major version is not guaranteed.
- Extensions, collations, data types, and server-side features may also differ across versions.

Read the release notes and test the restore on a compatible staging environment before moving to production.

## 5. Creating the Target Database

For a full restore, the easiest approach to control is creating an empty database from template0:

~~~bash
createdb -T template0 appdb_restore
~~~

Or using SQL:

~~~sql
CREATE DATABASE appdb_restore
    WITH TEMPLATE template0
    ENCODING 'UTF8';
~~~

Encoding, locale, collation, and database options must match the source and application requirements. Do not assume UTF8 or the same locale across every system.

### Why Is template0 Usually Used?

template0 is a cleaner template for creating databases with a specified encoding/locale. template1 may contain custom objects added by administrators; those objects could conflict with the archive.

### Restoring Into an Existing Database

You can restore into an existing database, but you must handle:

- Objects with the same name.
- Existing schemas/tables.
- Duplicate constraints and indexes.
- Existing data.
- Differing owners/ACLs.
- Inconsistent dependencies.

When replacing an entire database, it is usually easier to restore into a new database, verify it, and then switch the application via a planned cutover.

## 6. Connection and Basic Syntax

General syntax:

~~~bash
pg_restore [options] [archive-file-or-directory]
~~~

Example:

~~~bash
pg_restore \
  -h db.example.internal \
  -p 5432 \
  -U restore_user \
  -d appdb_restore \
  --verbose \
  --exit-on-error \
  appdb.dump
~~~

Common connection and control options:

| Option | Meaning |
| --- | --- |
| -h | Host |
| -p | Port |
| -U | User |
| -d / --dbname | Database to connect to for restoring |
| -W | Prompt for password |
| -v / --verbose | Print detailed progress |
| -e / --exit-on-error | Stop on error |
| -j / --jobs | Number of restore workers |
| -f / --file | Output SQL script instead of connecting to a database |

Do not put passwords directly on the command line or in shared scripts. Use `.pgpass`, a service file, or a secret manager according to environment policy.

## 7. Reading the Table of Contents

An archive contains a TOC (table of contents) listing objects and data entries.

View the list:

~~~bash
pg_restore --list appdb.dump
~~~

Save to a file:

~~~bash
pg_restore --list appdb.dump > appdb.list
~~~

The TOC typically contains:

- Dump ID.
- Catalog identifiers.
- Object type.
- Schema.
- Object name.
- Owner or related metadata.

Abbreviated illustrative example:

~~~text
;
; Archive created at ...
;     dbname: appdb
;     TOC Entries: ...
;
... TABLE public customers ...
... TABLE DATA public customers ...
... SEQUENCE public customers_id_seq ...
... INDEX public customers_pkey ...
... CONSTRAINT public customers customers_pkey ...
... TABLE public orders ...
... TABLE DATA public orders ...
... INDEX public orders_customer_id_idx ...
~~~

Exact contents and formatting depend on the version and archive. Inspect the actual output from your own archive.

### What Is the TOC Used For?

- Confirming the archive has readable metadata.
- Finding objects to restore.
- Building a list of allowed objects to restore.
- Skipping unnecessary objects in test environments.
- Analyzing dependencies and restore ordering.
- Saving a reviewable recovery plan.

pg_restore --list only reads the TOC; its success does not prove all data payloads are intact or that the restore will succeed.

## 8. Selecting Objects with a TOC List

Create the list:

~~~bash
pg_restore -l appdb.dump > appdb.list
~~~

Open the file and comment out or remove lines you do not want to restore according to the list syntax. Then run:

~~~bash
pg_restore -L appdb.list -d appdb_restore appdb.dump
~~~

-L is the short form of --use-list. pg_restore processes the entries in the list file in the order they appear there.

### Example of Selecting Specific Objects

Suppose the archive contains:

- Table customers and data.
- Table orders and data.
- Indexes.
- Functions.
- Views.

If you only want to restore customers, you can keep the entries related to customers in the TOC. However, you must check whether dependencies such as types, sequences, functions, or schemas are also needed.

### Why Must You Be Careful?

One object can depend on another. If you omit a table but keep a view referencing it, view creation will fail. If you keep table data but omit a required type/function, the restore may fail.

A TOC list lets you select entries, but it does not automatically resolve the full dependency graph. Test on a temporary database first.

## 9. Selecting by Schema

Restore a single schema:

~~~bash
pg_restore -n sales -d appdb_restore appdb.dump
~~~

Or:

~~~bash
pg_restore --schema=sales --dbname=appdb_restore appdb.dump
~~~

You can exclude a schema:

~~~bash
pg_restore -N audit -d appdb_restore appdb.dump
~~~

-n/--schema selects objects in the specified schema. -N/--exclude-schema excludes the schema from the restore scope.

Notes:

- Schema names/patterns follow matching rules; use appropriate quoting.
- Selecting a schema does not guarantee all external objects it depends on are restored.
- Extensions and global roles still require separate preparation.
- Certain database-wide objects not belonging to a schema may not be selected.

## 10. Selecting by Table

Restore a table:

~~~bash
pg_restore -t orders -n sales -d appdb_restore appdb.dump
~~~

You can select multiple tables:

~~~bash
pg_restore \
  -n sales \
  -t customers \
  -t orders \
  -d appdb_restore \
  appdb.dump
~~~

Exclude a table:

~~~bash
pg_restore -T audit_log -n public -d appdb_restore appdb.dump
~~~

-t/--table selects tables matching a pattern. -T/--exclude-table excludes tables matching a pattern.

### Limitations of Table Selection

Selecting a table does not mean pg_restore automatically restores all dependent objects. In particular, check:

- Schemas and custom types.
- Sequences/identities.
- Indexes.
- Constraints.
- Triggers.
- Functions called by defaults/triggers.
- Views/materialized views.
- Foreign keys pointing to other tables.

Depending on the archive, options, and object types, inspect the actual TOC. Never assume -t is a self-contained dependency bundle.

## 11. Selecting Object Types

pg_restore provides options to select object types in the archive, for example:

| Option | Target |
| --- | --- |
| -I / --index | Select index |
| -P / --function | Select function |
| -n / --schema | Select schema |
| -t / --table | Select table |
| -N / --exclude-schema | Exclude schema |
| -T / --exclude-table | Exclude table |

Short option letters can overlap with other options in different contexts; always check `pg_restore --help` for the client you are using. Some object types have dedicated options, and pattern support varies by version.

For complex selective restores, a TOC list is usually clearer than combining many pattern flags.

## 12. Restoring by Section

An archive is divided into logical sections:

- **pre-data**: definitions needed before loading data, such as schemas, types, and table definitions.
- **data**: table data and large objects.
- **post-data**: many indexes, triggers, rules, and constraints created after data is loaded.

Example:

~~~bash
pg_restore --section=pre-data -d appdb_restore appdb.dump
pg_restore --section=data -d appdb_restore appdb.dump
pg_restore --section=post-data -d appdb_restore appdb.dump
~~~

### When Should You Split by Section?

- Load large data first, build indexes afterward.
- Investigate errors in a specific stage.
- Design multi-step workflows.
- Separate privileges or maintenance windows by stage.
- Track schema build, data load, and index build times separately.

### Do Not Run Sections Arbitrarily in Parallel

Post-data depends on pre-data and data. Running post-data before tables exist or before data is loaded can fail or create unnecessary work.

When restoring by section, preserve the order and check the exit code of each step.

## 13. Schema-Only or Data-Only

Schema-only:

~~~bash
pg_restore --schema-only -d appdb_restore appdb.dump
~~~

Data-only:

~~~bash
pg_restore --data-only -d appdb_restore appdb.dump
~~~

Schema-only is suitable when you want to create object definitions first. Data-only is suitable when the schema has already been deployed and verified.

However, data-only requires:

- Compatible tables and columns.
- Required types and functions already available.
- Matching sequences/identities.
- Planned constraints/triggers.
- Compatible target encoding/collation.

Do not load data into a differently structured schema and expect pg_restore to transform the data automatically.

## 14. Parallel Restore: Principles

With custom or directory archives, you can use -j:

~~~bash
pg_restore -j 4 -d appdb_restore appdb.dump
~~~

pg_restore opens multiple connections to the target database and schedules archive entries that can run concurrently.

Tasks that can be parallelized depending on dependencies include:

- Loading data for independent tables.
- Creating indexes for independent relations.
- Archive items without dependency ordering conflicts.

Some steps must still run serially due to object or metadata dependencies.

### Parallel Restore Does Not Split a Single Table Arbitrarily

-j 4 does not mean one large table is split into four chunks for four workers to load simultaneously. Parallelism primarily operates across independent archive items. A single huge table may still be one task handled by one worker.

This explains why a database with many independent tables benefits noticeably, whereas a database with a single giant table may not see proportional speedup.

## 15. Which Formats Support Parallel Restore?

| Format | Parallel restore | Operational reason |
| --- | --- | --- |
| Custom | Yes | Archive allows pg_restore to distribute entries |
| Directory | Yes | TOC and data files can be read by multiple workers |
| Tar | No | Does not support parallel restore mode |
| Plain | No (via pg_restore) | Restored using a psql script |

Custom example:

~~~bash
pg_restore -j 4 -d appdb_restore appdb.dump
~~~

Directory example:

~~~bash
pg_restore -j 4 -d appdb_restore appdb_dir
~~~

Do not pass -j with tar or plain expecting a parallel restore.

## 16. Choosing the Number of Jobs

The job count is the maximum number of workers/connections pg_restore uses for parallel restore. Choose a value based on target resources, not just CPU core count.

Consider:

- Available CPU.
- Disk throughput and IOPS.
- Storage latency.
- Memory and shared buffers.
- Connection limits.
- Index build concurrency.
- WAL generation.
- Physical replica replay rate.
- Other running application workloads.

Start small and benchmark. For example, you might try 2–4 jobs on staging, measure, and adjust. This is an illustrative starting point, not a universal production default.

### When Can Increasing Jobs Fail to Speed Things Up?

- Disk has already hit throughput limits.
- CPU is saturated.
- WAL replay on replicas cannot keep up.
- Target has few independent tables.
- Index builds compete for the same storage.
- Lock contention increases.
- Network or backup source is slow.

Increasing jobs can actually slow down the restore if workers contend for the same bottleneck resource.

## 17. Parallel Restore and Connection Count

Each worker requires a connection to the target database. Beyond the workers, there are administrative, monitoring, and application connections.

Before running:

- Check max_connections.
- Account for existing connection pool usage.
- Reserve headroom for administrators/monitoring.
- Check per-role/per-database connection limits.
- Avoid exhausting connection slots during the restore.

If a connection proxy/pooler is present, verify that its operating mode is compatible with multi-session restores and pg_restore's session-level commands.

## 18. Parallel Restore and Single Transaction

There are two major restore choices:

### Parallel jobs

~~~bash
pg_restore -j 4 -d appdb_restore appdb.dump
~~~

Multiple workers run concurrently. The entire operation cannot be wrapped in a single transaction.

### Single transaction

~~~bash
pg_restore --single-transaction --exit-on-error -d appdb_restore appdb.dump
~~~

--single-transaction/-1 wraps the restore commands into one transaction. If an error occurs and the transaction rolls back, partial changes inside the transaction are not committed.

Trade-offs:

- Incompatible with -j parallel jobs.
- A large transaction can hold locks and resources for a long time.
- Rollback duration may increase.
- Some commands cannot execute inside a transaction block.
- Database creation/drop commands do not fit a single transaction.

Only use single transaction when the archive and target operation are compatible and there is a clear requirement for all-or-nothing atomicity.

## 19. Error Handling: exit-on-error

By default, pg_restore may continue some tasks after encountering an error and report a summary at the end. This can be useful when collecting multiple errors in a single run, but the database may be left in a half-restored state.

Use:

~~~bash
pg_restore --exit-on-error -d appdb_restore appdb.dump
~~~

--exit-on-error tells pg_restore to stop on the first error. In production automation, it is typically recommended so pipelines detect failed restores early and do not mark the database as ready.

### Always Check the Exit Code

Do not rely solely on the last line of the log. Orchestration scripts must check the process exit status and capture stderr/stdout.

If a restore command fails:

1. Record the first error and subsequent errors.
2. Identify the failing phase/object.
3. Inspect how far the target database was modified.
4. Choose between retrying, restoring into a clean database, or selective recovery.
5. Do not open traffic to an unvalidated database.

## 20. Cleaning Before Restoring

Option:

~~~bash
pg_restore --clean --if-exists -d appdb_restore appdb.dump
~~~

- --clean drops objects before recreating them.
- --if-exists adds IF EXISTS to drop statements where applicable.

If the database holds active data, clean can delete existing objects and data. Confirm the exact target and scope before running.

### Clean Does Not Make a Database Brand New

It drops objects present in the archive within the restore scope. Objects outside the archive may remain. If your goal is a clean database, creating a new database from template0 is usually easier to control.

### Clean and Dependencies

pg_restore orders drop/create statements based on TOC/dependencies. If the list was edited or the target has different dependencies, drops may fail. Inspect logs and do not use --clean as a quick fix for duplicate-object errors without understanding the target state.

## 21. Creating a Database from an Archive with --create

You can instruct pg_restore to create the database recorded in the archive:

~~~bash
pg_restore --create --dbname=postgres appdb.dump
~~~

--dbname=postgres is the initial database pg_restore connects to in order to issue the database creation command. When using --create, the target database is created using the name stored in the archive metadata, and pg_restore connects to that database to restore.

### Renaming the Target Database

If you want to restore an archive under a new name, the workflow is usually clearer as follows:

1. Create the new database using createdb/template0.
2. Restore the archive into the new database using --dbname, without --create.

Example:

~~~bash
createdb -T template0 appdb_recovered
pg_restore --dbname=appdb_recovered --exit-on-error appdb.dump
~~~

Do not assume `--dbname=appdb_recovered` combined with `--create` renames the archived database; `--create` uses the database name recorded in the archive.

## 22. Ownership and ACLs

An archive may contain ownership and ACL metadata.

When the target lacks the source roles, you can omit ownership/ACLs:

~~~bash
pg_restore --no-owner --no-acl -d appdb_restore appdb.dump
~~~

- --no-owner: do not emit commands to set ownership as recorded in the archive.
- --no-acl: do not restore GRANT/REVOKE statements saved in the archive.

You can use:

~~~bash
pg_restore --role=app_owner -d appdb_restore appdb.dump
~~~

--role instructs pg_restore to issue SET ROLE after connecting, provided the connecting user has the appropriate privileges.

### Skipping Ownership Does Not Create Roles

If ownership and grants must be preserved intact, create global roles/memberships before restoring. pg_restore does not automatically create cluster-wide roles from a database archive.

Global objects can be backed up using:

~~~bash
pg_dumpall --globals-only > globals.sql
~~~

The globals script may contain role attributes, memberships, and tablespaces. Protect this file as sensitive administrative data.

## 23. Tablespaces and Extensions

### Tablespaces

An archive may reference source tablespaces. The target must have matching tablespaces, or use:

~~~bash
pg_restore --no-tablespaces -d appdb_restore appdb.dump
~~~

This option omits tablespace assignment statements from the archive so objects use the target's default tablespace according to restore semantics.

### Extensions

An archive may contain CREATE EXTENSION statements, but it does not bundle server extension binaries.

Before restoring:

- Install compatible extension packages on the target host.
- Check extension versions.
- Verify shared libraries and control files.
- Determine whether extensions need upgrading after restoring.
- Review extension creation privileges and security policies.

A missing extension on the target can cause the restore to fail when creating dependent objects.

## 24. Large Objects and Sequences

### Large Objects

An archive may contain large objects exported by pg_dump. If the application uses the Large Object API, verify counts and access privileges after restoring. Do not confuse large objects with bytea/TOAST columns.

### Sequences

pg_restore restores sequence definitions and sequence values from the archive. After restoring, verify:

- Sequences exist.
- Ownership/identity dependencies are correct.
- Current values align with table data.
- New inserts do not collide with existing keys.

Do not mechanically reset sequences using MAX(id) if a sequence uses custom increments, cycles, caching, or specialized semantics.

## 25. Data Restore and Triggers

A data-only restore can interact with triggers/constraints on the target. There is an option:

~~~bash
pg_restore --disable-triggers --data-only -d appdb_restore appdb.dump
~~~

This option disables triggers during data loading and re-enables them afterward using pg_restore's mechanism. It requires elevated privileges (typically superuser) and should only be used when its impact is well understood.

Do not disable triggers just to speed up a restore if triggers enforce business invariants, audit data, or integrity. If an error occurs mid-process, verify trigger and constraint states before opening the application.

Usually, restoring a full archive in dependency order is the safer choice. pg_restore can create the schema first, load data, and build many indexes/constraints in post-data.

## 26. Choosing Between Script Output and Direct Database Restore

Export an SQL script:

~~~bash
pg_restore --file=restore.sql appdb.dump
~~~

Review or save the script, then execute:

~~~bash
psql -X -v ON_ERROR_STOP=1 -d appdb_restore -f restore.sql
~~~

Advantages:

- Review SQL before execution.
- Can adjust for environment specifics.
- Can save output as a migration artifact.
- Easy to observe exact statements.

Limitations:

- The script can be very large.
- Loses pg_restore's parallel restore capability.
- Object selection/ordering must be prepared prior to export or edited in the script.
- Requires psql to run.

When parallel restore is needed, connect pg_restore directly using --dbname.

## 27. Using a TOC List to Skip an Object

Example workflow:

~~~bash
pg_restore -l appdb.dump > appdb.list
~~~

Open appdb.list, comment out entries you do not want to restore per list syntax, then:

~~~bash
pg_restore -L appdb.list --exit-on-error -d appdb_restore appdb.dump
~~~

Can be combined with parallel jobs if the archive and options support it:

~~~bash
pg_restore -j 4 -L appdb.list -d appdb_restore --exit-on-error appdb.dump
~~~

### Keep the List File as an Artifact

You should retain:

- Archive filename/checksum.
- Original TOC file.
- Edited TOC file.
- Reviewer and reason for excluding objects.
- Restore command.
- Target database/version.
- Restore/validation results.

This makes selective restores reproducible when needed.

## 28. Restoring a Single Table from an Archive

Example:

~~~bash
pg_restore \
  --table=orders \
  --schema=sales \
  --dbname=appdb_restore \
  --exit-on-error \
  appdb.dump
~~~

Then verify:

~~~sql
SELECT count(*) FROM sales.orders;
SELECT * FROM sales.orders ORDER BY order_id DESC LIMIT 5;
~~~

You must also check sequences, indexes, constraints, and foreign keys. If the table depends on types/functions in another schema, prepare them first or adjust the TOC list.

### Moving Data Between Two Databases

You can use selective restore to recover a table into another database, but pg_restore does not map schemas/data onto a different structure. If column types or table definitions differ, use migration/ETL or a staging table with a controlled INSERT...SELECT.

## 29. Restoring by Schema and Data Phases

A multi-phase workflow:

~~~bash
pg_restore --section=pre-data --exit-on-error -d appdb_restore appdb.dump
pg_restore --section=data --exit-on-error -d appdb_restore appdb.dump
pg_restore --section=post-data --exit-on-error -d appdb_restore appdb.dump
~~~

Benefits:

- Clear visibility into schema creation time.
- Separate tracking of data loading.
- Indexes/constraints built after data is loaded.
- Easier error isolation.

Drawbacks:

- Must maintain the exact order.
- Each command requires its own exit code check.
- If an intermediate phase fails, the target is left in an incomplete state.
- Applications must not use the database between phases.

## 30. Does Parallel Restore Support TOC Lists?

You can combine an archive list with -j in supported formats and versions:

~~~bash
pg_restore -j 4 -L appdb.list -d appdb_restore appdb.dump
~~~

pg_restore still must respect dependency ordering. Reordering the list improperly can cause a required object to be missing when a worker starts its task.

Do not use a list to arbitrarily reorder dependent objects. If special ordering is needed, understand dependencies and test on staging.

## 31. Monitoring Restore Progress

### pg_stat_activity

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    query_start,
    wait_event_type,
    wait_event,
    left(query, 160) AS query_sample
FROM pg_stat_activity
WHERE datname = 'appdb_restore'
ORDER BY query_start;
~~~

You will see multiple sessions opened by pg_restore during parallel execution. Queries and wait events help identify workers running COPY, CREATE INDEX, or waiting on resources.

### CREATE INDEX Progress

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    command,
    phase,
    blocks_total,
    blocks_done,
    tuples_total,
    tuples_done
FROM pg_stat_progress_create_index
ORDER BY pid;
~~~

Index creation can account for most of the restore time on index-heavy databases.

### COPY Progress

Some PostgreSQL versions provide pg_stat_progress_copy to track COPY commands:

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    command,
    type,
    bytes_processed,
    bytes_total,
    tuples_processed
FROM pg_stat_progress_copy
ORDER BY pid;
~~~

Available columns and visibility depend on the version and COPY type. pg_restore may use different loading mechanisms depending on archive/target options; not every restore stage appears in this view.

### Do Not Extrapolate ETA from a Single Counter

A counter can pause while a worker waits on locks, index builds, WAL flushes, or dependencies. Combine phase info, wait events, logs, disk/CPU metrics, and the remaining archive entries.

## 32. Monitoring Locks and Transactions

A restore may wait on locks or be blocked by other DDL. Check:

~~~sql
SELECT
    a.pid,
    a.state,
    a.xact_start,
    a.query_start,
    a.wait_event_type,
    a.wait_event,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name
FROM pg_stat_activity AS a
LEFT JOIN pg_locks AS l
    ON l.pid = a.pid
WHERE a.datname = 'appdb_restore'
ORDER BY a.query_start;
~~~

Watch especially for:

- Other DDL or maintenance on the target.
- Long-running transactions.
- Lock waits.
- Connection slots.
- Application sessions if the database was opened prematurely.

Restoring a new database should normally run in an environment free of concurrent application writes.

## 33. Optimizing Restore Speed

Common measures to consider:

1. Choose custom/directory archives if parallel restore is needed.
2. Size -j appropriately for CPU and storage.
3. Create an empty target database and prepare dependencies beforehand.
4. Use pre-data/data/post-data if the workflow requires phase control.
5. Evaluate index builds and constraints.
6. Monitor WAL generation and replica replay.
7. Avoid competing application workloads.
8. Place target data on suitable storage.
9. Check the connection budget.
10. Run ANALYZE after bulk restores when needed.

Do not arbitrarily disable constraints/triggers or lower durability settings. Any durability relaxation increases data loss risk if the server crashes before the restore finishes and is properly protected.

## 34. Restores and WAL/Replication

A restore generates heavy changes on the target and can produce substantial WAL.

With a primary and physical standbys:

- Replicas must replay the WAL.
- Replication lag can increase.
- WAL archives/replication slots may retain large volumes of WAL.
- Disk usage on both primary and replicas can grow rapidly.
- Standby query latency may be affected.

Before a large restore, check:

- WAL filesystem headroom.
- Archive command/backup pipeline.
- Replication slot status.
- Replica replay rate.
- Disk throughput.
- Retention policy.

Do not mark a recovered database as ready if replicas or the backup pipeline are not yet stable per operational requirements.

## 35. When a Restore Fails Mid-Way

By default, a restore may have committed partial work before encountering an error. Without a single transaction, the database may contain some created tables, data, and indexes.

How to handle it:

1. Preserve logs and exit code.
2. Identify the failing object/phase.
3. Inspect the database state and catalog.
4. Determine whether individual objects can be retried or the target database should be dropped and restored fresh.
5. Verify dependencies before re-running.
6. Run full validation before opening traffic.

### Can pg_restore Be Re-Run?

You can re-run specific objects if you understand the state and select the right TOC entries. However, re-running the entire archive into a database that already has objects usually causes duplicate-object errors or data conflicts.

For complete recovery environments, it is usually safer to create a fresh target database and restore from scratch if time and resources allow.

### Do Not Treat Re-Running as Automatic Resume

pg_restore is not a row-level checkpoint/resume system for full restores. Using a TOC list to resume selectively requires the operator to identify completed entries and remaining dependencies.

## 36. Handling Duplicate Objects

Common errors:

- Schema already exists.
- Table already exists.
- Duplicate index/constraint.
- Duplicate function signature.
- Missing/differing role or extension.

Options:

- Restore into a new database.
- Use --clean --if-exists if intentionally replacing objects.
- Select appropriate TOC entries.
- Prepare dependencies beforehand.
- Check whether existing objects are used by an application.

Do not manually drop objects just to push a restore past errors without understanding dependencies and ownership.

## 37. Restores and Access Privileges

The connecting user needs adequate privileges to create schemas/tables/indexes, load data, and set owners/ACLs. Some operations require superuser or special privileges.

If restoring without preserving owners/ACLs:

~~~bash
pg_restore --no-owner --no-acl --role=app_owner -d appdb_restore appdb.dump
~~~

Then verify privileges:

~~~sql
SELECT
    grantee,
    table_schema,
    table_name,
    privilege_type
FROM information_schema.role_table_grants
WHERE table_schema = 'public'
ORDER BY table_name, grantee, privilege_type;
~~~

This is one view of table grants; also check schema privileges, sequence privileges, function execute privileges, and default privileges per application policy.

## 38. Restores and Security Labels/Comments

An archive may contain comments and security labels depending on objects and dump options. The target must support the corresponding provider for security labels. If the provider is absent, the restore may fail.

Do not skip security labels or comments just to make the command succeed without determining whether they carry compliance/audit significance.

Inspect the TOC and logs when errors occur on specialized object metadata.

## 39. Restoring on Servers with Different Locale/Collation

A database dump does not automatically give the target the same OS locale, collation provider, or collation version.

Differences can affect:

- Sort order.
- Unique index semantics.
- Text comparison.
- Query result ordering.
- Index validity/need for rebuild depending on the situation.
- Application behavior.

Before a production restore, verify encoding, locale, collation provider/version, and extension dependencies. After restoring, check for collation version mismatch warnings and handle them per PostgreSQL documentation.

## 40. Checking the Database After Restore

Do not stop at the exit code. Verify multiple layers.

### Object inventory

~~~sql
SELECT
    schemaname,
    count(*) AS table_count
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
GROUP BY schemaname
ORDER BY schemaname;
~~~

### Table row estimates

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup
FROM pg_stat_user_tables
ORDER BY schemaname, relname;
~~~

These are estimates, not exact row counts. Pick critical tables to cross-check using appropriate queries.

### Constraints

~~~sql
SELECT
    conname,
    contype,
    convalidated,
    conrelid::regclass AS table_name
FROM pg_constraint
WHERE connamespace = 'public'::regnamespace
ORDER BY conrelid::regclass::text, conname;
~~~

### Index validity

~~~sql
SELECT
    indexrelid::regclass AS index_name,
    indisvalid,
    indisready,
    indislive
FROM pg_index
WHERE NOT indisvalid OR NOT indisready OR NOT indislive;
~~~

### Sequences

Check critical sequences/identities and test inserts safely in a test environment. Do not run test INSERTs on production before assessing their impact.

## 41. Smoke Tests and Business Verification

Post-restore steps should include:

- Connecting with the application role.
- Reading key tables.
- Verifying critical row counts or aggregates.
- Checking unique/foreign key constraints.
- Checking views/functions/procedures.
- Checking sequences/identities.
- Checking triggers.
- Checking large objects.
- Checking grants and schema privileges.
- Running representative queries and measuring latency.
- Confirming application health checks.

A database with all tables present but missing permissions or extensions can still leave the application broken.

## 42. Switching the Application to the Restored Database

If restoring into a new database, cutover should be planned:

1. Restore and validate the target database.
2. Sync final changes if the workflow requires it.
3. Stop writes or switch the application per the migration procedure.
4. Update connection strings/secrets/service discovery.
5. Open traffic incrementally.
6. Monitor errors, latency, and connection pools.
7. Retain the old database per retention/rollback policy.
8. Only delete the old database after confirmation and expiration of the rollback window.

Do not delete the source database immediately after a successful restore. Preserve a rollback path per policy and clearly define the point of no return.

## 43. Selective Restore During an Incident

When only a single table is lost or corrupted, you can restore that table from the archive into a temporary database:

1. Create a separate recovery database.
2. Restore required schemas/dependencies.
3. Restore the table/data into the temporary database.
4. Verify rows and constraints.
5. Compare data against current production.
6. Transfer selective data using transactional INSERT/UPDATE statements.
7. Reconcile sequences and foreign keys.
8. Record an audit trail of the recovered data.

Do not overwrite a production table directly without knowing the state of current rows and the impact of triggers/foreign keys.

## 44. How Plain SQL Restore Differs from Archive Restore

| Task | Plain SQL | Custom/Directory/Tar |
| --- | --- | --- |
| Tool | psql | pg_restore |
| View contents | Text editor | pg_restore -l or pg_restore -f |
| Object selection | Select at dump time or carefully edit script | TOC and options |
| Parallel restore | No | Custom/Directory |
| Section restore | No archive TOC; needs separate scripts | Yes |
| Exit on error | psql ON_ERROR_STOP | pg_restore --exit-on-error |
| Single transaction | psql -1 if script is compatible | pg_restore --single-transaction |
| Dependency ordering | Script order | TOC/dependency scheduler |

If your workflow needs flexible restores, custom/directory archives are usually more suitable than plain scripts.

## 45. Complete Workflow Example: Custom Archive

Create target database:

~~~bash
createdb -T template0 appdb_recovered
~~~

Restore:

~~~bash
pg_restore \
  --dbname=appdb_recovered \
  --exit-on-error \
  --verbose \
  appdb.dump
~~~

If omitting owner/ACL is needed:

~~~bash
pg_restore \
  --dbname=appdb_recovered \
  --no-owner \
  --no-acl \
  --exit-on-error \
  appdb.dump
~~~

Then verify:

~~~sql
SELECT current_database();
SELECT count(*) FROM public.orders;
~~~

Cross-check business invariants and verify roles/extensions/constraints before cutover.

## 46. Complete Workflow Example: Parallel Restore

Prepare database:

~~~bash
createdb -T template0 appdb_recovered
~~~

Restore:

~~~bash
pg_restore \
  --jobs=4 \
  --dbname=appdb_recovered \
  --exit-on-error \
  --verbose \
  appdb.dump
~~~

While running, monitor:

- pg_stat_activity.
- pg_stat_progress_create_index.
- pg_stat_progress_copy if applicable to the version/operation.
- CPU, I/O, memory.
- WAL rate and replica lag.
- Disk free space.
- Server logs.

After completion, check catalogs, row counts, constraints, and application smoke tests.

## 47. Selective Restore Workflow Example with TOC

~~~bash
pg_restore --list appdb.dump > appdb.list
~~~

Review and edit appdb.list, then:

~~~bash
createdb -T template0 recovery_subset
pg_restore \
  --use-list=appdb.list \
  --dbname=recovery_subset \
  --exit-on-error \
  appdb.dump
~~~

If the archive is custom/directory and dependencies allow, you can add:

~~~bash
pg_restore -j 4 -L appdb.list -d recovery_subset --exit-on-error appdb.dump
~~~

Document excluded entries and verify the subset database has all objects needed for the incident/test goal.

## 48. Common Mistakes

1. **Using pg_restore for plain SQL**, when plain scripts must be loaded via psql.
2. **Using tar with -j**, even though tar does not support parallel restore.
3. **Thinking -j splits one large table across multiple workers**, whereas parallelism mainly runs across independent archive items.
4. **Increasing jobs without checking the connection budget**, exhausting max_connections.
5. **Increasing jobs on already saturated storage**, making the restore slower.
6. **Using -t and assuming dependencies are restored automatically**, leading to missing types/functions/schemas.
7. **Editing the TOC list without checking dependencies**, causing errors on downstream objects.
8. **Restoring post-data before data**, leaving indexes/constraints without target objects or data.
9. **Using --clean on a live database**, potentially deleting active data.
10. **Using --create while misunderstanding --dbname as the new database name**, creating the wrong target.
11. **Dropping owners/ACLs without recreating privileges**, breaking application access.
12. **Failing to prepare roles/global objects**, causing owner/GRANT failures.
13. **Failing to install extensions on the target**, preventing dependent objects from being created.
14. **Failing to prepare tablespaces**, causing restore errors or wrong storage placement.
15. **Combining --single-transaction with -j**, which is unsupported.
16. **Using --single-transaction with commands that cannot run in a transaction**, causing the restore to fail.
17. **Omitting --exit-on-error in automation**, then marking the database ready despite errors.
18. **Re-running the whole archive into a partially restored database**, creating duplicate objects and conflicts.
19. **Treating pg_restore -l as full backup verification**, when it only confirms TOC readability.
20. **Ignoring WAL/replication lag**, causing replicas to fall behind.
21. **Not verifying sequences/identities**, causing duplicate key errors when the application writes.
22. **Not checking constraint/index validity**, leaving the database lacking integrity.
23. **Not checking locale/collation/extension versions**, causing behavioral differences.
24. **Opening traffic before smoke tests**, turning restore issues into production outages.
25. **Deleting the old database right after cutover**, losing the rollback path.
26. **Using --disable-triggers without understanding business logic**, bypassing integrity/audit behavior.
27. **Running selective restore directly onto production**, without staging and data reconciliation.
28. **Not checking privileges of the restore user**, causing mid-restore failures.

## 49. Practice Exercises with Answers

### Exercise 1. What is pg_restore used for?

**Answer:** Reading custom, directory, or tar archives created by pg_dump to restore schemas/data into a database or output an SQL script.

### Exercise 2. What is used to restore a plain SQL dump?

**Answer:** psql, not pg_restore.

### Exercise 3. Which command views an archive's TOC?

~~~bash
pg_restore -l appdb.dump
~~~

**Answer:** Lists the archive entries.

### Exercise 4. How do you use a TOC list during a restore?

~~~bash
pg_restore -L appdb.list -d appdb_restore appdb.dump
~~~

**Answer:** Restores only entries included in the list, in list order.

### Exercise 5. Which formats support parallel restore?

**Answer:** Custom and directory.

### Exercise 6. Does tar support parallel restore?

**Answer:** No.

### Exercise 7. Which option enables parallel restore?

**Answer:** -j or --jobs.

### Exercise 8. What does -j 4 mean?

**Answer:** Up to four restore workers/connections are coordinated; it does not guarantee four jobs run at every moment.

### Exercise 9. Why doesn't one giant table necessarily speed up fourfold?

**Answer:** Parallelism mainly runs across independent archive items; a single table data item may still be one task.

### Exercise 10. How do you restore a single schema?

~~~bash
pg_restore -n sales -d appdb_restore appdb.dump
~~~

**Answer:** Selects objects in the sales schema via pattern matching.

### Exercise 11. How do you restore a single table?

~~~bash
pg_restore -t orders -n sales -d appdb_restore appdb.dump
~~~

**Answer:** Selects the orders table; separate dependencies must be checked manually.

### Exercise 12. Which three sections is an archive divided into?

**Answer:** pre-data, data, and post-data.

### Exercise 13. Why does post-data usually run after data?

**Answer:** Many indexes, triggers, and constraints require the tables/data to already exist.

### Exercise 14. What does --exit-on-error do?

**Answer:** Stops the restore upon encountering the first error.

### Exercise 15. What is the benefit of --single-transaction?

**Answer:** Wraps compatible commands in one transaction to roll back everything if an error occurs.

### Exercise 16. Can --single-transaction be used with -j?

**Answer:** No. Parallel jobs are incompatible with single-transaction mode.

### Exercise 17. What does --clean do?

**Answer:** Drops objects within the restore scope before recreating them; can delete existing data.

### Exercise 18. What is the role of --if-exists?

**Answer:** Adds IF EXISTS to drop commands where applicable, reducing errors when an object does not exist yet.

### Exercise 19. What does --create combined with --dbname mean?

**Answer:** --dbname is the initial connection database; --create instructs creating the database using the name stored in archive metadata.

### Exercise 20. What should you do to restore into a new database name?

**Answer:** Create the new database first, then restore into it with --dbname without using --create.

### Exercise 21. How do --no-owner and --no-acl differ?

**Answer:** --no-owner skips ownership commands; --no-acl skips GRANT/REVOKE statements.

### Exercise 22. Does pg_restore automatically create cluster-wide roles?

**Answer:** No. Use pg_dumpall --globals-only or create roles separately before restoring.

### Exercise 23. What is --no-tablespaces used for?

**Answer:** Skips tablespace assignment commands from the archive so the target uses an appropriate default tablespace.

### Exercise 24. Why must extensions be installed on the target?

**Answer:** Archives store declarations, not server extension binaries/packages.

### Exercise 25. Why can a failed restore leave the database in a partial state?

**Answer:** Without single-transaction mode, steps prior to the error may already be committed.

### Exercise 26. Can you immediately re-run the entire archive after an error?

**Answer:** Not recommended. Inspect object states; creating a new database and restoring cleanly is usually easier to control.

### Exercise 27. What is pg_stat_progress_create_index used for?

**Answer:** Monitoring the phase and progress of index builds during a restore when the operation is supported by the view.

### Exercise 28. Why monitor WAL and replica lag?

**Answer:** Restores generate heavy changes/WAL; standbys must replay them and may fall behind.

### Exercise 29. Where do you check for invalid indexes?

**Answer:** The pg_index catalog via the indisvalid, indisready, and indislive columns.

### Exercise 30. What conditions must be met before opening traffic after a restore?

**Answer:** No unresolved restore errors; objects, data, constraints, sequences, permissions, extensions, and smoke tests all pass; required replication/monitoring is stable.

## 50. Restore Operations Checklist

- [ ] Identify archive format and use the right tool.
- [ ] Verify pg_restore and target PostgreSQL versions.
- [ ] Read the TOC before selective restores.
- [ ] Choose target database and appropriate template/encoding/locale.
- [ ] Prepare roles, memberships, and tablespaces.
- [ ] Install required extension packages.
- [ ] Decide whether to keep or omit owners/ACLs.
- [ ] Check dependencies of selected schemas/tables/objects.
- [ ] Keep pre-data, data, post-data order if restoring by phase.
- [ ] Choose job count based on CPU, disk, WAL, and connection budget.
- [ ] Do not use parallel restore with tar/plain.
- [ ] Do not combine --single-transaction with -j.
- [ ] Only use --clean after confirming the drop scope.
- [ ] Understand the meaning of --create and --dbname.
- [ ] Use --exit-on-error for automation requiring early failure.
- [ ] Save logs and exit code.
- [ ] Monitor pg_stat_activity and progress views.
- [ ] Monitor lock waits, disk, WAL, and replication lag.
- [ ] Inspect state after error/cancellation before retrying.
- [ ] Verify index validity, constraints, and sequences.
- [ ] Check large objects, extensions, and ACLs.
- [ ] Run smoke tests using the application role.
- [ ] Measure RTO and compare against target.
- [ ] Keep the old database per rollback/retention policy.
- [ ] Only open traffic after validation completes.

## 51. Official PostgreSQL Documentation

Read the documentation for your deployed major version:

- [pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html) — options, archive restore, TOC list, parallel jobs, and selective restore.
- [pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html) — archive formats, dump scope, and compression.
- [psql](https://www.postgresql.org/docs/current/app-psql.html) — running plain SQL scripts and ON_ERROR_STOP.
- [pg_dumpall](https://www.postgresql.org/docs/current/app-pg-dumpall.html) — global objects and role backups.
- [Backup and Restore](https://www.postgresql.org/docs/current/backup.html) — logical and physical backups.
- [SQL Dump](https://www.postgresql.org/docs/current/backup-dump.html) — dump/restore workflows.
- [CREATE DATABASE](https://www.postgresql.org/docs/current/sql-createdatabase.html) — database creation, templates, encoding, and locale.
- [Database Roles](https://www.postgresql.org/docs/current/user-manag.html) — roles, memberships, and privileges.
- [Privileges](https://www.postgresql.org/docs/current/ddl-priv.html) — database object access privileges.
- [CREATE EXTENSION](https://www.postgresql.org/docs/current/sql-createextension.html) — extensions on the target.
- [Tablespaces](https://www.postgresql.org/docs/current/manage-ag-tablespaces.html) — storage placement.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_activity and statistics.
- [Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html) — progress views for COPY and CREATE INDEX.
- [Collation Support](https://www.postgresql.org/docs/current/collation.html) — locale/collation behavior.
- [Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html) — WAL-based physical recovery.

The `/current/` URLs point to the current PostgreSQL documentation. Options, progress columns, parallel restore restrictions, and certain behaviors may vary by major version; check the documentation matching your client/server versions before running in production.

## 52. Summary

**pg_restore restores logical archives with support for object selection, ordering control, and multi-job execution.** Safe outcomes depend on choosing the right format, preparing dependencies, controlling errors, and verifying the database after restoring.

1. **Plain SQL uses psql; custom, directory, and tar use pg_restore.**
2. **Custom and directory support parallel restore; tar does not.**
3. **Parallel jobs run across independent archive items**, without automatically splitting one large table into multiple parts.
4. **TOC and --use-list help select objects**, but operators must understand dependencies.
5. **pre-data, data, and post-data require proper ordering** when restoring by section.
6. **--clean and --create can heavily impact the target database**, so target and scope must be confirmed.
7. **--single-transaction cannot be combined with parallel jobs** and does not suit every command.
8. **Owners, ACLs, roles, extensions, and tablespaces must be prepared** to restore the right security/storage model.
9. **A failed restore can leave partial state.** Check catalogs and consider restoring again into a clean database.
10. **Monitor CPU, I/O, connections, WAL, and replica lag** during large restores.
11. **Verify sequences, constraints, index validity, permissions, and smoke tests** before opening traffic.
12. **Test restores periodically and measure RTO** to prove backups work during incidents.

A complete recovery procedure must prove that the restored database has complete data, accurate permissions, proper dependencies, and works with the application within the target timeframe.
