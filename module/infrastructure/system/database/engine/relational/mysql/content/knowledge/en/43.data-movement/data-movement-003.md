# MySQL Shell Dump/Load, Parallel Processing, and Compatibility Metadata

MySQL Shell provides dump and load utilities to export, transfer, and load MySQL data with parallel processing capabilities. The `util.dumpInstance()`, `util.dumpSchemas()`, and `util.dumpTables()` utilities create a dump set consisting of data, DDL, and metadata; `util.loadDump()` reads that dump set, inspects the metadata, and loads it into the target server. They are suitable for migrations, cloning environments, provisioning replicas from logical backups, and moving workloads between servers.

A dump set is more than just data files. Metadata describes the dump structure, source version, exported objects, and how data pieces relate to one another. During loading, MySQL Shell uses this metadata to coordinate workers, order object creation, and process data as configured. Ignoring metadata or manually editing dump files can cause out-of-order loading, loss of resume capability, or target incompatibility.

This lesson belongs to the **Data Movement and Migration** chapter of the `DATABASE_MYSQL` module. The module covers table design, data types, keys, SQL queries, indexes, transactions, authorization, backup, and relational database operations. The content focuses on MySQL Shell dump/load on MySQL 8.0; check documentation for the exact MySQL Server and MySQL Shell versions before using in production.

After this lesson, you will be able to:

- Choose the right dump utility for instance, schema, or table scope.
- Create consistent dump sets and understand file structure and metadata.
- Tune threads, chunking, chunk size, and transfer rate.
- Load dumps in parallel, preview with dry run, and resume loads when appropriate.
- Evaluate version, charset, collation, engine, and SQL feature compatibility.
- Handle privileges, GTIDs, users, definers, and risks when changing environments.
- Establish a post-migration data verification workflow.

## 1. MySQL Shell and Dump/Load Utilities

MySQL Shell is a MySQL administrative client with JavaScript, Python, and SQL modes. The dump/load utilities are invoked in JavaScript or Python mode through the global `util` object.

Primary utilities:

| Utility | Scope | Use Case |
|---|---|---|
| `util.dumpInstance()` | Entire instance, within the object scope supported by the utility | Create a logical dump of a server or serve as the source to provision a new instance. |
| `util.dumpSchemas()` | One or more schemas | Migrate a set of application databases. |
| `util.dumpTables()` | A set of tables within one schema | Extract a subset of data or migrate a specific group of tables. |
| `util.loadDump()` | Load a dump set created by the corresponding utilities | Perform logical recovery or load data onto a target server. |

These commands are MySQL Shell utilities, not SQL statements run in the `mysql` client. Open MySQL Shell in JavaScript mode, connect to the source server, and invoke the utility.

Example of connecting and checking versions:

~~~text
mysqlsh
MySQL JS> \connect backup_user@mysql-source.example.internal:3306
MySQL JS> shell.version
MySQL JS> session.runSql("SELECT VERSION()");
~~~

In real environments, use dedicated accounts for backup and migration, secure authentication, and TLS when connecting over the network. Never store real passwords in scripts, command history, or dump files.

## 2. Selecting the Dump Scope

### 2.1. Dumping an Entire Instance

`util.dumpInstance()` is suitable when moving an instance or creating a complete dump set for a new environment. The utility handles supported schemas and objects while writing metadata so `util.loadDump()` can reconstruct them.

~~~javascript
util.dumpInstance("/backup/mysql-full", {
  threads: 8
});
~~~

The target directory must be prepared according to the utility's requirements. Do not overwrite an older dump set currently used by another process. If keeping multiple backup versions, name directories by date, run ID, or snapshot ID.

Dumping the entire instance does not mean all state outside the database is copied. Separately identify components that need to be migrated, such as server configuration, plugins, keyrings, TLS certificates, OS accounts, external jobs, and application files.

### 2.2. Dumping One or More Schemas

When only specific application databases are needed, use `util.dumpSchemas()`:

~~~javascript
util.dumpSchemas(
  ["sales", "inventory"],
  "/backup/sales-inventory",
  {threads: 8}
);
~~~

This reduces time and storage compared to a full-instance dump. However, check for dependencies outside the selected scope: views referencing another schema, routines accessing tables in other databases, cross-schema foreign keys, or applications relying on shared data.

### 2.3. Dumping a Set of Tables

Use `util.dumpTables()` when moving a subset of tables within a schema:

~~~javascript
util.dumpTables(
  "sales",
  ["orders", "order_items"],
  "/backup/sales-orders",
  {threads: 4}
);
~~~

A table-level dump covers only the selected scope. It does not automatically bring along all dependent tables, referenced data, application privileges, or external configuration. Before loading into the target environment, inspect foreign keys, triggers, views, routines, and related data relationships.

### 2.4. Comparing Scope Choices

| Requirement | Suggested Utility | Additional Checks |
|---|---|---|
| Migrating an application server | `dumpInstance()` | Users, system schemas, configuration, plugins, and GTIDs. |
| Moving several databases | `dumpSchemas()` | Cross-schema dependencies, users, and access privileges. |
| Moving a few large tables | `dumpTables()` | DDL, foreign keys, triggers, views, and referenced data. |
| Creating a small test environment | `dumpSchemas()` or `dumpTables()` | Anonymize sensitive data and strip secrets. |

## 3. Dump Set Structure and the Role of Metadata

MySQL Shell dump utilities generate a set of files in the specified directory or storage destination. Depending on scope and version, a dump set typically contains:

- Dump-level metadata describing version, options, scope, and format.
- DDL files for exported schemas, tables, views, routines, triggers, or events.
- Data files for tables; large tables may be split into multiple chunks.
- Table descriptor files and metadata used for data mapping.
- Status or completion files generated by the utility.

File names and structures can vary by MySQL Shell version. Treat the dump directory as a single cohesive unit and use `util.loadDump()` to read the metadata. Do not rename, delete, or edit metadata files unless you understand the impact on the loader.

Metadata is essential because it tells the loader:

1. Which utility version created the dump set.
2. Which schemas/tables and objects belong to the dump set.
3. Which DDL must be executed before loading data.
4. Which files or chunks table data is split into.
5. Which compatibility options were applied during export.
6. What progress state was recorded during a load run.

Metadata does not replace business verification. A dump set may be read successfully by the loader yet still lack dependent tables because the chosen dump scope was incomplete.

## 4. Dump Consistency

When dumping a database actively receiving writes, data must reflect a consistent point in time. For InnoDB, the dump utilities support consistent snapshot mechanisms so tables are exported from the same logical state within the utility's scope and configured conditions.

Before dumping, check:

- Whether the tables to move use InnoDB or other engines.
- Whether DDL such as ALTER, DROP, or RENAME is running or scheduled during the dump window.
- Whether the backup account has the required privileges and locking/snapshot mechanisms.
- Whether heavy write workloads could lengthen dump time or grow temporary files.
- Whether the backup needs to include users, routines, events, and triggers.

An InnoDB consistent snapshot does not automatically protect non-transactional tables in the same way. Concurrent DDL can interrupt or alter structures the dump is reading. For critical migrations, coordinate DDL within an appropriate window and inspect utility messages before proceeding.

A single dump command can run multiple workers. That does not mean each worker creates an independent snapshot. Let the utility manage consistency according to its design; do not split a single dump into multiple independent commands without determining how snapshots are synchronized across them.

## 5. Parallel Processing During Dump

The dump utilities support the `threads` parameter to control the number of workers performing work concurrently.

~~~javascript
util.dumpInstance("/backup/mysql-full", {
  threads: 8
});
~~~

Increasing worker count can improve read and file-write speeds if CPU, storage, and network have headroom. However, more workers can also:

- Increase read I/O on the source server.
- Increase CPU usage for serialization, compression, and metadata computation.
- Increase the number of files or chunks created concurrently.
- Increase network load when writing dumps to remote storage.
- Compete with production workloads and raise application latency.

Do not default to setting threads equal to CPU cores. Start with a moderate value, measure dump duration, throughput, CPU, I/O, and application latency, and scale up gradually if the source has spare capacity.

### 5.1. Chunking for Large Tables

For large tables, chunking splits data into smaller parts so workers can process them in parallel. Related options can include enabling/disabling chunking and setting a target chunk size.

Illustrative example:

~~~javascript
util.dumpSchemas(
  ["sales"],
  "/backup/sales",
  {
    threads: 8,
    chunking: true,
    bytesPerChunk: "64M"
  }
);
~~~

Chunking is beneficial when a table has a suitable key or column for partitioning data ranges. Tables without a suitable key, small tables, or heavily skewed data may not parallelize effectively.

A larger chunk reduces file count and metadata overhead, but can reduce worker flexibility and increase retry cost for a slice of data. Smaller chunks create more work units, increasing file-open, metadata, scheduling overhead, and the total number of files to manage.

Chunk size is an operational target, not a guarantee that every chunk will have identical size. Variable row lengths or uneven key distributions can produce chunks of varying sizes.

### 5.2. Choosing the Chunking Key

Chunking typically requires a column or set of columns that can be used to partition row ranges. An auto-incrementing numeric primary key is favorable, though not every table has such a key.

Before enabling chunking, check:

- Does the table have a suitable primary key or unique key?
- Does the key's data type support the utility's chunking method?
- Are key values evenly distributed or clustered in certain ranges?
- Are there many very large rows making chunk sizes unpredictable?
- Is the table changing continuously during the dump?

Do not add keys solely to force faster dumps without evaluating the impact on the application, indexes, and replication. For tables that cannot be chunked effectively, let the utility handle them in its supported manner and measure actual timings.

### 5.3. Rate Limiting

When dumping from production, maximum throughput can be throttled to reduce workload impact. Rate-limiting options can be used to regulate the amount of data read or transferred as supported by the utility.

Do not set the limit so low that the backup cannot finish within the allowed window; nor run at full speed if it degrades live transactions. Measure throughput, application latency, IOPS, and completion time to find the right balance.

## 6. Compression and Dump Storage Location

Compression reduces storage footprint and transfer traffic at the expense of CPU for compression/decompression. Choose the algorithm and compression level based on MySQL Shell version, data type, and machine resources.

Text, JSON, and repetitive values usually compress well. Already compressed data, images, or binary payloads may shrink much less. Benchmark on a representative sample rather than guessing from database size.

Dump storage can be a local filesystem, network mount, or remote object storage supported by the utility version. Consider:

- Directory permissions and service accounts.
- Available free space and quotas.
- Network throughput, latency, and stability.
- Encryption at rest and in transit.
- Retention, versioning, and pruning policies.
- How to verify files were written completely before starting a load.

If storing the dump on an intermediate host, ensure the directory contains the entire dump set and metadata. Never copy partial files while a dump is still running and treat the copy as a complete backup. After the dump completes, record logs, size, timestamp, and final exit status.

## 7. Loading the Dump and Parallel Processing

`util.loadDump()` reads the dump set, validates metadata, and loads structure/data into the target server.

~~~javascript
util.loadDump("/backup/mysql-full", {
  threads: 8
});
~~~

The loader can use multiple workers to load independent tables or chunks. Actual parallelism depends on chunk count, DDL dependencies, indexes, foreign keys, resource capacity, and target configuration.

Before loading, confirm:

- The target server runs the right version and has sufficient disk space.
- Charset, collation, SQL mode, and timezone are appropriate.
- Conflicting schemas or objects with identical names are handled per plan.
- The load account has sufficient privileges to create and load objects.
- Replication, binary logging, and GTIDs are configured according to target goals.
- No applications are writing to the target database during data load.
- A backup or snapshot of the target state exists before making changes.

### 7.1. Dry Run Before Loading

Use `dryRun` to inspect the load plan without executing all write operations:

~~~javascript
util.loadDump("/backup/mysql-full", {
  dryRun: true
});
~~~

Dry run helps uncover certain metadata, compatibility, and target object issues before loading. It does not guarantee the entire load will succeed: permission errors at execution time, disk exhaustion, connection drops, data errors, or DDL conflicts can still occur.

Read the dry run output carefully, confirming target schemas and options before running for real.

### 7.2. Choosing Worker Count During Load

~~~javascript
util.loadDump("/backup/mysql-full", {
  threads: 12
});
~~~

Loading with more workers can accelerate file reading and inserts, but the target server must concurrently handle indexes, constraints, redo/undo, binlogs, and data writes. Excessive threads can saturate CPU, I/O, and memory, lengthening total elapsed time.

Measure these metrics:

- Data load throughput and remaining chunk count.
- CPU, memory, IOPS, and storage latency.
- InnoDB buffer pool, redo log, and dirty page pressure.
- Lock wait and deadlock rates.
- Binary log growth if the target writes binlogs.
- Index build and DDL completion times.

Start with a moderate worker count and scale based on measurements. Never use the exact same `threads` setting across all machine sizes or workloads.

### 7.3. Deferring Index Creation

For certain dump sets and versions, the loader supports deferring index creation so data loads first and indexes are built afterward. Example:

~~~javascript
util.loadDump("/backup/mysql-full", {
  threads: 8,
  deferTableIndexes: "all"
});
~~~

This approach can speed up loading large datasets by reducing per-row secondary index maintenance overhead. However, the subsequent index build phase can consume heavy CPU, I/O, temporary space, and time. Tables without full indexes are also not ready for normal application workloads.

Only defer indexes when you have a migration window and a plan to verify indexes after loading. Check supported values and exact behavior for your MySQL Shell version.

## 8. Resuming a Load and Managing Progress

A load can take many hours. MySQL Shell records progress to support resuming in cases supported by the utility. If a connection drops or the command stops unexpectedly, inspect the output and progress state before retrying.

Handling procedure:

1. Record the error and the point where the process stopped.
2. Check that the target server is still healthy, has free disk space, and check worker status.
3. Verify the dump directory remains intact and unmodified.
4. Determine whether the loader can resume from saved state or requires manual intervention.
5. Use the exact same dump set and progress directory as required by your version.
6. Inspect already-loaded objects before deciding to skip or replace them.

Do not delete progress state files to force a restart without knowing the data state. Doing so makes the loader lose track of completed work and can cause existing-object errors, duplicate data, or conflicts.

Options like `ignoreExistingObjects` or `dropExistingObjects` strongly affect results. Do not enable them merely to bypass an error. `ignoreExistingObjects` may cause the loader to skip an existing object even if it differs from the dump; `dropExistingObjects` can delete target objects before recreating them. Use them only after confirming exact impact in a test environment.

## 9. Version Compatibility and Metadata

A dump set created by one MySQL Shell version and loaded by another must be checked for compatibility. Loadability depends on the Shell version, source and target MySQL Server versions, and SQL features used in the schema.

Before migration, record:

~~~sql
SELECT VERSION(), @@version_comment;
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'collation_server';
SHOW VARIABLES LIKE 'sql_mode';
SHOW VARIABLES LIKE 'lower_case_table_names';
~~~

Additionally, check the MySQL Shell version:

~~~javascript
shell.version
~~~

Points to review:

- Do source and target versions support the corresponding DDL syntax?
- Do data types, collations, and charsets exist on the target server?
- Do generated columns, functional indexes, invisible indexes, and CHECK constraints behave compatibly?
- Are plugins, authentication methods, and storage engines available on the target?
- Have JSON, spatial, temporal, or specialized data formats changed across versions?
- Could SQL mode alter how data or statements are interpreted?
- Could database/table names be affected by OS case sensitivity differences and `lower_case_table_names`?

Do not assume a dump from a newer version can safely load into an older version. Check MySQL's support matrix and test a full restore on a target server running the planned version.

### 9.1. Compatibility Options During Dump

MySQL Shell offers compatibility options to transform certain DDL or metadata to support targets with different constraints. Exact option names depend on the version; common transformation groups include:

- Stripping `DEFINER` from views, routines, triggers, or events when avoiding source account dependencies.
- Converting or removing tablespace clauses when the target lacks matching tablespaces.
- Adjusting incompatible grants or account metadata.
- Converting engines to InnoDB where aligned with goals.
- Creating invisible primary keys for tables lacking a primary key when features and application requirements permit.

Do not enable all compatibility options out of habit. Each option can alter schema behavior or metadata. For example, stripping `DEFINER` can change the privilege execution context; forcing engines can affect features and performance; adding primary keys can impact index size and replication.

Inspect options for your exact version using MySQL Shell's built-in help:

~~~javascript
util.help("dumpInstance")
util.help("dumpSchemas")
util.help("dumpTables")
util.help("loadDump")
~~~

Cross-check each change against security requirements, access privileges, and application behavior.

### 9.2. DEFINER and Execution Privileges

Views, stored procedures, functions, triggers, and events can be bound to a `DEFINER` account. On the target server, that account may not exist or may lack the same privileges.

If `DEFINER` is preserved when the account does not exist, objects may be created with warnings or fail to behave as expected depending on object type and version. If `DEFINER` is stripped, MySQL may use default or creator contexts per applicable rules, which can alter access permissions.

Before dumping, list all objects with a `DEFINER` and establish a strategy:

- Create corresponding `DEFINER` accounts on the target with least privileges.
- Reassign `DEFINER` to an appropriate application administrative account.
- Use a compatibility option to strip `DEFINER` once impact is evaluated.
- Re-verify privileges and test invoking routines/views with the application account after load.

Do not reassign every object to `root` just to eliminate `DEFINER` errors. Overly broad privileges increase security risk.

## 10. Users, Grants, and Non-Schema Objects

Dumping schemas and dumping users are distinct scopes. If accounts and privileges must be migrated, check user dump/load options for your MySQL Shell version. Never assume `dumpTables()` brings along users, grants, or dependent schemas.

When migrating users:

- Confirm account name and host.
- Check authentication plugins on source and target.
- Verify required plugins are installed.
- Review roles, dynamic privileges, and grant options.
- Do not export or share password hashes outside secure workflows.
- Check account locking, password expiration, and TLS requirements.

After loading, run `SHOW GRANTS` to verify privileges of key accounts and test connecting with the application account. Do not test only with an administrative account, as it does not reflect the application's effective permissions.

Some objects and configurations must be managed separately:

- MySQL system variables and server configuration files.
- Plugins, components, and keyrings.
- Event Scheduler setting.
- Replication channels and source configuration.
- Certificates, private keys, and CA bundles.
- Scheduled tasks on the OS or orchestration platform.
- Secrets in applications and connection configurations.

## 11. GTID and Binary Logging During Load

When loading a dump into a server with binary logging enabled, import changes can generate new transactions and GTIDs. If the dump is used to provision a replica or restore a source's GTID state, explicitly plan how GTIDs and binary logs are handled.

Relevant choices in the dump/load workflow may include:

- GTID metadata exported with the dump.
- Options for updating the GTID set in `util.loadDump()`, with version-dependent behavior.
- Options to disable binary logging for the load session if supported and appropriately privileged.

Do not pick a GTID update mode arbitrarily. If the goal is provisioning a replica from a backup, the GTID set must accurately reflect the transactions already present in the snapshot data. If moving only a subset of schemas to an independent environment, carrying over the source's full GTID set can mistakenly mark transactions from un-dumped schemas as executed.

Before loading, check the current version's help:

~~~javascript
util.help("loadDump")
~~~

After loading, inspect:

~~~sql
SELECT @@GLOBAL.gtid_executed, @@GLOBAL.gtid_purged;
SHOW BINARY LOGS;
~~~

If the target server will become a replica, configure auto-position only after confirming data and GTID metadata align to the same logical point. Never inject GTIDs manually to bypass missing-transaction errors; GTIDs only record history, they do not recreate data.

## 12. Required Privileges

Dumping and loading are broad-scope operations. The executing accounts require privileges matching the objects and snapshot, read, creation, or data modification mechanisms used. Exact privilege lists vary by version, utility, and enabled options.

The dump account generally needs privileges to read tables/views, inspect metadata, read routines/events/triggers, and perform any locking or snapshot actions the utility uses. The load account needs privileges to create schemas/tables, write data, create indexes, routines, triggers, events, and manage users if users are loaded.

Safe practices:

1. Read the privilege requirements for the exact utility and version.
2. Create a dedicated backup account on the source and a dedicated migration account on the target.
3. Grant only the privileges needed for the dump/load scope.
4. Do not use `root` for automated jobs.
5. Log run details without logging secrets.
6. Revoke temporary privileges once migration is complete if the account is no longer needed.

If permission errors occur, identify the exact object and denied operation. Never solve it by granting `ALL PRIVILEGES` to an application account.

## 13. Practical Migration Workflow

A migration workflow should be divided into preparation, dump, transfer, load, and verification.

### 13.1. Preparing Source and Target

- Record Server and Shell versions.
- Check schemas, engines, charsets, collations, SQL modes, and timezones.
- Verify capacity on source, target, and dump storage location.
- Check accounts, privileges, users, roles, and DEFINERs.
- List objects and dependencies within the migration scope.
- Select dump and load windows suited to system load.
- Define GTID and replication objectives for the target server.

### 13.2. Dump

Example of dumping multiple schemas:

~~~javascript
util.dumpSchemas(
  ["sales", "inventory"],
  "/backup/migration-2026-11-19",
  {
    threads: 8,
    chunking: true,
    bytesPerChunk: "64M"
  }
);
~~~

Monitor output until the utility confirms completion. Save the run log, tool version, configuration used, and completion timestamp. Confirm the directory contains metadata along with generated DDL/data files.

### 13.3. Transferring the Dump Set

If transferring to another host:

- Copy the entire dump directory.
- Preserve file names and structure.
- Verify file count and total size on both ends.
- Use OS or storage checksums to verify transfer integrity.
- Restrict read permissions since dumps can contain sensitive data.
- Do not delete the source copy until the target copy is verified.

### 13.4. Load

First run a dry run:

~~~javascript
util.loadDump("/backup/migration-2026-11-19", {
  dryRun: true
});
~~~

After reviewing output and confirming the target server:

~~~javascript
util.loadDump("/backup/migration-2026-11-19", {
  threads: 8
});
~~~

If index deferral or GTID adjustments are needed, add options only after confirming their version-specific behavior and impact.

### 13.5. Post-Load Verification

Verify across multiple layers:

- **Schema:** counts of tables, views, routines, triggers, and events.
- **Data:** row counts of critical tables and aggregate reconciliations.
- **Constraints:** primary keys, unique keys, foreign keys, and CHECK constraints.
- **Indexes:** names, types, column order, visibility, and build status.
- **Accounts:** users, roles, grants, DEFINERs, and authentication.
- **Replication:** GTID, binary logs, and replica status if applicable.
- **Application:** login, read queries, test writes, transactions, and business flows.
- **Performance:** execution plans, latency, and representative workloads.

Do not compare total row counts alone. Two tables can have identical row counts yet differ in content. For critical data, compare by key ranges, amount totals, quantity totals, min/max timestamps, or batch checksums. Choose a method that does not overload production.

## 14. Post-Migration Data Checks

### 14.1. Structure Checks

~~~sql
SHOW TABLES FROM sales;
SHOW CREATE TABLE sales.orders;
SHOW INDEX FROM sales.orders;
~~~

Check views and routines:

~~~sql
SHOW FULL TABLES FROM sales;
SHOW PROCEDURE STATUS WHERE Db = 'sales';
SHOW FUNCTION STATUS WHERE Db = 'sales';
~~~

Compare results against the manifest or object inventory locked prior to migration. Some metadata may have been intentionally transformed by compatibility options; document those differences.

### 14.2. Row Count and Aggregate Checks

~~~sql
SELECT COUNT(*) FROM sales.orders;
SELECT COUNT(*) FROM sales.order_items;

SELECT
  COUNT(*) AS order_count,
  SUM(total_amount) AS total_amount,
  MIN(created_at) AS first_order,
  MAX(created_at) AS last_order
FROM sales.orders;
~~~

Compare source and target results at the same snapshot point. If the source continues receiving writes after the dump point, figures taken directly at two different times will not match accurately. Use a snapshot or recorded checkpoint.

### 14.3. Key-Range Data Checks

For critical tables, partition data into key ranges and compare in batches. Example:

~~~sql
SELECT
  MIN(order_id),
  MAX(order_id),
  COUNT(*),
  SUM(total_amount)
FROM sales.orders
WHERE order_id >= 1 AND order_id < 100000;
~~~

Repeat for subsequent ranges. For tables with sensitive data, do not export full rows into log files solely for comparison. Batch checksums can be used if the method and data types support them.

## 15. Common Incidents

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Dump reports missing privilege | Account lacks object read rights or snapshot mechanism privileges | Read the specific error, grant proper privileges to the backup account, and retest on a small scope. |
| Slow dump despite high threads | Source I/O, CPU, network, or large tables that do not chunk effectively | Measure bottlenecks, test chunking, and tune workers to current load. |
| A table produces few chunks | No suitable key or table unsuited for range partitioning | Check schema and how the utility chunks; do not assume every table parallelizes. |
| Load reports object already exists | Target is not clean or a previous load partially created objects | Inspect objects and progress; decide whether to resume, skip, or rebuild per plan. |
| Load fails due to DDL | Incompatible version or schema feature | Review DDL error, check compatibility options, and test on a matching target version. |
| Routine/view fails to execute | Missing DEFINER or differing execution privileges | Check DEFINER, SQL SECURITY, grants, and accounts on the target. |
| Load slows down during index creation | Index build, I/O, or memory bottleneck | Measure the index phase; consider deferring indexes if appropriate. |
| Target has unexpected GTIDs | Import wrote to binlog or GTID metadata was misapplied | Check `gtid_executed`, load options, and replication goals. |
| Missing dump files after copy | Incomplete copy or omitted metadata/chunks | Compare file lists, sizes, and checksums; recopy before loading. |
| Dry run succeeds but load fails | Dry run does not execute all write operations | Check privileges, disk space, DDL, data, and server state during load. |

## 16. Practice Exercises

### Exercise 1: Choosing the Dump Utility

An application has databases `sales`, `inventory`, and `audit`. A test environment needs only `sales` plus the two tables `orders` and `order_items`. Choose among `dumpInstance`, `dumpSchemas`, and `dumpTables`; list the dependencies to check before exporting.

### Exercise 2: Tuning Threads and Chunking

Create a large table with a primary key and another table without a suitable key. Test dumping with varying thread counts and chunking enabled/disabled. Record elapsed time, size, CPU, and I/O; explain why increasing threads does not always increase throughput.

### Exercise 3: Performing Dry Run and Load

Create a dump set in a test environment, transfer it to a target server of the same version, run `dryRun`, inspect the output, and perform a parallel load. Verify schema and row counts after completion.

### Exercise 4: DEFINER Compatibility

Create a view or routine with a `DEFINER` set to a dedicated account. Dump and load it onto an instance lacking that account. Observe warnings/errors and test creating the matching account versus stripping `DEFINER`. Check effective privileges after each approach.

### Exercise 5: Checking GTIDs

Create an instance dump and a single-schema dump on a GTID-enabled source. Inspect GTID-related metadata or SQL output, then explain why a partial dump should not automatically be used as the GTID state for a full-instance replica.

## 17. Pre-Completion Migration Checklist

- [ ] Selected the right dump scope: instance, schema, or table.
- [ ] Checked storage engines, snapshots, concurrent DDL, and data consistency.
- [ ] Recorded MySQL Server and MySQL Shell versions.
- [ ] Tuned threads, chunking, chunk size, and rate according to actual load.
- [ ] Confirmed dump set contains metadata and complete DDL/data files.
- [ ] Verified integrity when transferring files to storage or the target host.
- [ ] Ran dry run and reviewed output.
- [ ] Confirmed privileges and storage capacity on the target server.
- [ ] Reviewed compatibility for charset, collation, SQL mode, engine, and DDL.
- [ ] Handled DEFINER, users, roles, and grants per security policy.
- [ ] Defined how binary logs and GTIDs are handled.
- [ ] Loaded successfully and verified all critical objects.
- [ ] Reconciled row counts and data via keys or appropriate checksums.
- [ ] Tested business workflows and representative queries.
- [ ] Saved migration logs, metadata, timestamps, and verification results.
- [ ] Deleted dump copies or reopened application writes only after formal completion sign-off.

MySQL Shell dump/load moves large datasets efficiently by combining metadata, chunking, and parallel workers. High speed only matters when the snapshot is consistent, the dump set is complete, the target is compatible, and loaded data is verified. Treat metadata and dump files as a single unit, test with dry run on the target, tune workers using measured metrics, and cut applications over to the new environment only after completing structure, data, privilege, and replication checks.
