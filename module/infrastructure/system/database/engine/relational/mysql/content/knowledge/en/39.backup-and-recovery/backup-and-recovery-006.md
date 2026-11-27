# MySQL Shell Dump/Load Utilities and Compatibility Requirements

MySQL Shell provides a suite of dump and load utilities to export logical data from MySQL, move that dataset to another server, or restore it into a new environment. These utilities are well-suited when you need to select specific schemas or tables, split large datasets, run in parallel, and resume loading after an interruption.

This lesson belongs to the **DATABASE_MYSQL** module, focusing on practical relational database backup and recovery. We will use **util.dumpInstance()**, **util.dumpSchemas()**, **util.dumpTables()**, and **util.loadDump()**, while examining version differences, server settings, access privileges, and how to verify results.

## 1. What Is MySQL Shell Dump/Load?

MySQL Shell dump/load is a logical-level backup and data transfer mechanism:

1. MySQL Shell reads database structure, metadata, and data from the source server.
2. The dump utility writes structure and data into a set of files in a target directory or supported storage location.
3. The file set is transferred to the target server.
4. The load utility reads the manifest and files, recreates objects, loads data, and completes configured steps.

This is not a physical copy of the InnoDB data directory. A dump set does not replace physical backups, volume snapshots, or storage-platform backups. Nor does it automatically save all server configurations, TLS certificate files, encryption keys, replication configuration, or all operational state outside the database.

A dump set typically contains a manifest describing its contents, DDL files, and multiple chunked data files, which may be compressed. Therefore, preserve the directory structure and all accompanying files. Never copy only a few data files or rename files arbitrarily.

### When Should You Use It?

- Migrating an instance or selected schemas to a new server.
- Creating logical backups for selective schema or table recovery.
- Populating development, testing, and staging environments.
- Exporting large datasets using multiple parallel read and load threads.
- Producing a dump set compatible with a target platform using supported checks and transformations.

If the goal is very fast recovery of a large server while keeping data files intact and minimizing export/import time, also evaluate physical backups or platform-level backup solutions. A logical dump must read and re-write data, so recovery time depends on data size, object count, storage speed, network, and server resources.

## 2. Choosing the Right Dump Utility

MySQL Shell has three primary data export utilities:

| Utility | Scope | Use Case |
|---|---|---|
| **util.dumpInstance()** | User schemas in the instance and account components configured for export | Instance-level migration or logical backup |
| **util.dumpSchemas()** | A specified list of schemas | Moving only certain databases |
| **util.dumpTables()** | A list of tables within one schema | Moving a subset of data or a group of tables |

System schemas such as **mysql**, **sys**, **performance_schema**, and **information_schema** are not treated like ordinary application schemas in an instance dump. User accounts and roles are a separate concern that must be verified based on the utility, options, and MySQL Shell version. Never assume dumping application schemas means all accounts, grants, or server configurations were exported.

### Dumping the Entire Instance

Open MySQL Shell and connect to the source server:

~~~javascript
shell.connect("backup_user@mysql-source.example:3306");
~~~

Then run in JavaScript mode:

~~~javascript
util.dumpInstance("/backup/mysql-instance", {
  threads: 8,
  consistent: true,
  chunking: true,
  bytesPerChunk: "64M",
  showProgress: true
});
~~~

The path above is an example on the machine running MySQL Shell. Account, directory, and thread count must be adjusted to the actual environment. Choose a fresh directory to avoid overwriting older dumps.

### Dumping Selected Schemas

~~~javascript
util.dumpSchemas(
  ["sales", "warehouse"],
  "/backup/business-schemas",
  {
    threads: 4,
    consistent: true,
    showProgress: true
  }
);
~~~

The schema list must exist on the source server and the executor must have privileges to read the corresponding objects.

### Dumping Selected Tables

~~~javascript
util.dumpTables(
  "sales",
  ["orders", "order_items"],
  "/backup/sales-orders",
  {
    threads: 4,
    consistent: true,
    showProgress: true
  }
);
~~~

When dumping only a few tables, identify the dependencies among them. A table may reference a foreign key on another table, and views or routines may depend on tables outside the list. A table dump does not automatically guarantee that the selected objects form a standalone, runnable application.

## 3. Important Dump Options

### Threads and Chunking

**threads** controls the number of threads executing work in parallel. Increasing threads can speed up reading, compressing, and writing data, but also increases CPU, memory, I/O, and connection load on the source server.

**chunking** allows large tables to be split into multiple data chunks so multiple threads can process them. **bytesPerChunk** sets the target chunk size. For example, **64M** requests chunks of roughly 64 MB; actual sizes may differ depending on data and splitting boundaries.

Effective chunking depends on table structure and keys suitable for partitioning data. Large tables without a primary key or suitable unique index may not split as desired, reducing parallelism. Check dump logs to see which tables were chunked and which were processed as one large piece.

Do not set threads very high right from the start. Measure CPU, I/O, temporary space, query times, and application load on the source server. Parallel dumps still compete for resources with production workloads.

### Data Consistency

The **consistent** option is enabled by default in the dump utilities. The goal is to produce a dump reflecting data at a single consistent point in time. For InnoDB, transactional snapshots allow reader threads to see a consistent data state. To handle metadata and non-transactional tables, MySQL Shell may also require locks or backup privileges appropriate to the server version.

This does not mean a consistent dump always runs with zero locking impact. Concurrent DDL activity, non-transactional tables, and version-specific locking mechanisms can affect the workload. Schedule dumps in suitable windows, watch for long-running transactions, and limit schema changes during the dump.

Only disable **consistent** when you clearly understand the risks and have another mechanism to guarantee consistency. If the source keeps writing during an inconsistent dump, tables or data chunks may reflect different points in time.

### Compression and Rate Limiting

MySQL Shell can compress dump data to reduce storage footprint and transfer volume. Compression saves bandwidth at the expense of CPU; algorithm and compression level choices depend on the MySQL Shell version.

Rate-limiting options such as **maxRate** can be used to prevent the dump from consuming excessive bandwidth or read resources. Check the units and scope of the option in your exact Shell version before setting a limit.

### Content Filtering

The utilities support selecting schemas, tables, and in some cases filtering objects to export. When designing a selective dump:

- Confirm selected tables include all necessary referenced data.
- Check views, triggers, routines, events, and foreign keys depending on out-of-scope objects.
- Decide whether accounts and privileges need to be exported.
- Record the command, filters, and tool version so the same scope can be reproduced next time.

Never use filters to skip data that the application needs for integrity or startup.

## 4. Checking Compatibility Before Dumping and Loading

A successfully created dump does not prove it can load onto any MySQL server. You must simultaneously check the MySQL Shell version, source server version, target server version, data structures, and features in use.

### MySQL Shell and MySQL Server Versions

The dump/load utilities ship with MySQL Shell; the Shell version dictates which options and dump format the tool understands. Use a MySQL Shell version equal to or newer than the version that created the dump when loading, and review release notes for both Shell and MySQL Server.

The target server must support the data types, DDL syntax, collations, engines, authentication plugins, and features used by the dump. When moving from a newer version to an older version, unsupported syntax or features may occur. Never assume that both being MySQL is enough to guarantee compatibility.

Before running, record versions at both ends:

~~~sql
SELECT VERSION();
SELECT @@version_comment;
SHOW VARIABLES LIKE 'lower_case_table_names';
SHOW VARIABLES LIKE 'sql_mode';
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'collation_server';
~~~

Cross-check further:

- Table engines, data types, numeric precision, and temporal representations.
- Character sets, collations, and string comparison rules.
- Whether table or column names collide with newly reserved keywords in the target version.
- Whether views, routines, triggers, and events use source-version-specific syntax or functions.
- Whether accounts, roles, authentication plugins, and privileges are supported on the target.
- Whether `DEFINER`, tablespaces, plugins, components, and external configs need recreation or adjustment.
- Differences in **lower_case_table_names**, especially when moving between operating systems with different case-sensitivity rules.

For upgrades or transitions across major versions, follow MySQL's supported upgrade path. Test loading into a target server whose version and configuration match production before performing a real cutover.

### Compatibility Checks for MySQL Database Service

When the target is MySQL Database Service, the **ocimds** option of the dump utility can enable compatibility checks tailored to that service:

~~~javascript
util.dumpSchemas(
  ["sales"],
  "/backup/sales-for-managed-mysql",
  {
    ocimds: true,
    threads: 4,
    showProgress: true
  }
);
~~~

These checks can detect objects or privileges incompatible with the target platform. You can combine the **compatibility** option to request supported DDL transformations, for example:

~~~javascript
util.dumpInstance("/backup/mysql-for-target", {
  ocimds: true,
  compatibility: [
    "strip_definers",
    "strip_restricted_grants",
    "strip_tablespaces"
  ]
});
~~~

Only apply transformations after reviewing their impact:

- **strip_definers** removes `DEFINER` clauses per the utility's rules. This can alter the security context when views, routines, or other objects execute.
- **strip_restricted_grants** adjusts privileges restricted on the target platform. Review carefully to ensure the application still retains required privileges.
- **strip_tablespaces** removes tablespace references per compatibility rules. Verify the planned storage layout on the target server.
- **force_innodb** can convert table definitions to InnoDB. Only use when engine and behavioral differences are acceptable.

Supported transformations and capabilities vary across MySQL Shell versions. Check documentation for your exact version before using them. Do not enable **ocimds** as a generic option for every MySQL target; it is a check mode meant for the specified platform.

## 5. Preparing the Target Server

Before loading data, prepare the target server and clearly define the recovery scope:

1. Install a supported MySQL Server version with compatible configuration.
2. Install a MySQL Shell version compatible with the dump set.
3. Check disk space for data, indexes, logs, temporary files, and growth during loading.
4. Verify network connectivity, TLS, and privileges of the load account.
5. Identify pre-existing schemas or objects and how conflicts should be handled.
6. Check the **local_infile** setting per version and load-workflow requirements.
7. Define binary log, GTID, and replication policies if the target server joins a topology.

Some load mechanisms use local data loading over the MySQL protocol. Therefore, **local_infile** may need to be enabled on the target server. Only enable it for the scope and duration needed under your system's security policy; verify its state again once finished.

Do not use a routine application account for recovery. The load account needs privileges to create databases and objects, write data, build indexes, and additional privileges if loading users/roles. Grant privileges appropriate to the utility and version, preferring a dedicated recovery account with a clear lifetime.

## 6. Loading a Dump with `util.loadDump()`

Connect MySQL Shell to the target server and run:

~~~javascript
shell.connect("restore_user@mysql-target.example:3306");

util.loadDump("/backup/mysql-instance", {
  threads: 8,
  showProgress: true
});
~~~

The path must point to the complete dump directory. If the dump resides on another machine, transfer the entire directory or configure a remote storage location supported by your MySQL Shell version.

### Trial Loading with `dryRun`

Before modifying the target server, you can run in trial mode:

~~~javascript
util.loadDump("/backup/mysql-instance", {
  dryRun: true,
  showProgress: true
});
~~~

A dry run checks the dump set and reports planned actions without executing the full data load. It does not replace a full test recovery; some errors only surface when actually creating objects, writing data, or building indexes.

### Tuning Parallelism and Indexes

For large datasets, you can increase **threads** to load multiple tables or chunks concurrently. Monitor CPU, I/O, redo logs, disk space, and target server load. If the server bottlenecks, lower thread count or throttle throughput instead of raising parallelism further.

The **deferTableIndexes** option defers building certain indexes until after data is loaded. For example:

~~~javascript
util.loadDump("/backup/mysql-instance", {
  threads: 8,
  deferTableIndexes: "all",
  showProgress: true
});
~~~

Building secondary indexes after loading data can be faster for some large workloads, though the index-building phase requires extra space and I/O. Do not enable it merely because data is large; benchmark and compare total runtime.

After loading, you may need to update optimizer statistics so execution plans reflect the new data. The load utility's **analyzeTables** option can assist with this step. If not used, the DBA can proactively run `ANALYZE TABLE` on appropriate tables after loading.

### Resuming After an Interruption

Loading can take a long time and be interrupted by dropped connections, out-of-space errors, or server faults. MySQL Shell maintains progress state to support resuming loads under supported conditions. Keep the dump set, progress files, and target environment intact; read error messages to decide whether to rerun or resolve already-created objects.

Do not delete progress files or use progress-reset options out of habit. Resetting can cause the utility to repeat already-finished work and collide with existing objects. If you need to reload from scratch, define how to clean the target schema or server and ensure existing data is protected.

## 7. Accounts, Privileges, and Sensitive Data

Dumping application schemas and dumping accounts are two separate concerns. When migrating an instance, check whether the dump includes users and roles under the chosen options. If accounts are not loaded, users, roles, and grants must be recreated via an approved administrative procedure.

When loading users/roles:

- Review internal accounts or accounts no longer needed.
- Check host patterns and connection source restrictions in the target environment.
- Check authentication plugins and password policies supported by the target server.
- Review `DEFINER` attributes of views, routines, triggers, and events.
- Never copy broader administrative privileges than the application requires.
- Protect the dump set because it may contain sensitive data, account information, and internal structures.

Dump files may reside in staging directories or object storage. Restrict read access, encrypt at rest and in transit, manage copy lifecycles, log downloads, and purge temporary copies per policy. Never place dump files in source repositories or share them over unapproved channels.

## 8. GTIDs and Binary Logs During Migration

If the source or target server participates in replication, GTID handling must be planned explicitly. A logical load may need to carry or update GTID state depending on the objective: creating a standalone server, replacing a replica, or initializing a new topology.

Do not automatically apply the source's GTIDs onto the target server simply to recover data. Replacing or injecting executed GTID sets can affect replication connectivity, duplicate-transaction detection, and topology correctness. Before using `loadDump`'s GTID update options, determine:

- Is the target server a fresh instance, a replica, or a server with an existing workload?
- What are the existing GTID sets on source and target?
- Does the binary log need to record the loaded changes?
- From which position or GTID set will replicas start?
- Must existing replication history be preserved, or is a new topology being initialized?

Options such as **updateGtidSet** and **skipBinlog** affect replication state or binary logging. Only use them after checking version documentation and securing a DBA-approved plan. For ordinary recovery into a standalone environment, do not alter GTIDs unless specifically required.

## 9. Verifying Results After Recovery

A load command finishing cleanly only confirms the utility completed its executed steps. The DBA still needs to verify data and application functionality.

### Verifying Objects and Row Counts

~~~sql
SHOW DATABASES;
SHOW TABLES FROM sales;
SHOW CREATE TABLE sales.orders\G
SELECT COUNT(*) FROM sales.orders;
SELECT COUNT(*) FROM sales.order_items;
~~~

Compare record counts with the source for the same scope and snapshot point. For large datasets, compare table by table or by key ranges to spot discrepancies faster.

### Verifying Structure and Dependencies

- Confirm required tables, views, routines, triggers, and events exist.
- Check primary keys, foreign keys, unique constraints, and indexes.
- Check `DEFINER`, access privileges, and application accounts.
- Check charsets, collations, SQL modes, and engines.
- Check the event scheduler and background tasks before allowing them to run in the target environment.

### Verifying Application Behavior

Run smoke tests covering critical reads and writes, test transactions, join queries, reports, background jobs, and connections from dependent services. Check execution plans for critical queries if version, statistics, or optimizer configuration changed.

Do not open production traffic to the new server until verification results, an accountable owner, and a rollback plan to the old server are in place.

## 10. Common Errors and Troubleshooting

### Permission Errors During Dump

The executor may lack privileges to read tables, views, triggers, events, or privileges required to take a snapshot/backup. Read the exact error message, identify the failing object, and grant the minimum required privileges. Do not solve this by using a broad admin account across all environments.

### Insufficient Disk Space

Check capacity on the dump directory, temp directory, target data volume, log storage area, and space needed for index builds. Compression reduces dump storage size, but it does not proportionally shrink data and index size after recovery. Clean up only files confirmed safe to remove; never delete an active dump set or progress file in use.

### DDL Compatibility Errors

Compare source and target versions, DDL statements, collations, tablespaces, engines, `DEFINER`s, and privileges. If **compatibility** options are needed, regenerate the dump using the chosen transformations and review the output before loading. Avoid hand-editing numerous DDL files after dumping, as that easily breaks consistency with the manifest.

### Slow Data Loading

Check thread count, chunking, storage throughput, CPU, redo logs, binary logs, and index building. If a large table does not chunk, examine its keys and data partitioning options. Raising threads will not fix a bottleneck on a single unchunked table or saturated I/O.

### Objects Already Exist on Target

Determine whether the object came from a prior load attempt, an application deployment, or pre-existing data. Never blindly skip or overwrite. Use a clean target environment, change the target schema, or build a controlled data merge workflow.

### Accounts Unable to Log In After Cutover

Check user/host, authentication plugin, password, lock/expiration state, grants, TLS, and host patterns. Also check `DEFINER` attributes on SQL objects. Recreate or adjust accounts via controlled administrative statements, then test with the actual application account.

## 11. Sample Workflow for an Instance Migration

An instance migration using MySQL Shell can be organized into the following phases:

**Phase 1 — Assessment**

- Record source and target MySQL Shell and MySQL Server versions.
- List schemas, data sizes, large tables, engines, and special objects.
- Inspect accounts, roles, `DEFINER`s, replication, GTIDs, and binary logs.
- Define dump window, cutover time, and rollback criteria.

**Phase 2 — Creating the Dump Set**

- Choose `dumpInstance`, `dumpSchemas`, or `dumpTables` based on scope.
- Enable `consistent` if a consistent snapshot is needed and confirm backup privileges.
- Select `threads`, `chunking`, `bytesPerChunk`, and compression based on test benchmarks.
- Preserve the entire dump directory, logs, and tool version details.

**Phase 3 — Checking and Transferring the Dump Set**

- Confirm the manifest and all data/DDL files are present and complete.
- Protect the dump set during transfer.
- Run `dryRun` on the target server.
- Resolve compatibility issues before real loading.

**Phase 4 — Loading and Verification**

- Prepare the target server, privileges, and `local_infile` as required.
- Run `loadDump` with the tested thread count.
- Monitor logs, progress, disk space, and server resources.
- Verify objects, data, privileges, and application behavior.

**Phase 5 — Shifting Traffic**

- Freeze write state on the source according to the cutover plan.
- Complete syncing any post-snapshot changes if required by the workflow.
- Verify application connections, monitor errors and performance.
- Only route traffic after acceptance criteria pass.
- Retain the old source for the agreed rollback window; decommission only after approval.

## 12. Pre- and Post-Dump/Load Checklist

**Before Dump**

- [ ] Defined instance, schema, or table scope.
- [ ] Checked Shell and source server versions.
- [ ] Confirmed read privileges and required snapshot/backup privileges.
- [ ] Inspected large tables, engines, keys, and chunking suitability.
- [ ] Evaluated `consistent` impact and execution schedule.
- [ ] Prepared storage capacity, location, encryption, and dump access permissions.

**Before Load**

- [ ] Checked target server version and DDL support.
- [ ] Checked charsets, collations, SQL modes, and `lower_case_table_names`.
- [ ] Prepared privileges, `local_infile`, and disk space for data/indexes/logs.
- [ ] Reviewed users, roles, `DEFINER`s, tablespaces, and compatibility options.
- [ ] Defined GTID and binary log policy if replication is involved.
- [ ] Ran `dryRun` and planned handling for pre-existing objects.

**After Load**

- [ ] Verified schemas, tables, views, routines, triggers, and events.
- [ ] Compared row counts or data checksums against appropriate criteria.
- [ ] Verified indexes, keys, privileges, accounts, and TLS connections.
- [ ] Ran smoke tests and inspected critical queries.
- [ ] Checked logs, replication, and monitoring post-cutover.
- [ ] Confirmed rollback plan and source retention end time.

## Conclusion

MySQL Shell dump/load is a strong toolset for logical backups, schema transfers, and instance migrations. Good outcomes depend on selecting the right dump scope, establishing an appropriate snapshot, tuning chunking and threads to available resources, and thoroughly verifying compatibility across Shell, source server, and target server. Treat the dump set as an artifact to protect, validate, and periodically test-restore. Consider a cutover complete only after data, schema, privileges, replication, and application behavior are all verified.
