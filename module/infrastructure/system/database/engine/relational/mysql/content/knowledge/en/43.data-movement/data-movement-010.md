# Migrating Large Datasets While Applications Keep Writing

In the **DATABASE_MYSQL** module, migrating large datasets commonly arises during server upgrades, infrastructure changes, schema splitting, region moves, or database cluster replacements. The hardest challenge is that data keeps changing while being copied. Simply taking a dump and loading it onto the new server leaves transactions committed after the snapshot missing on the target.

An online migration workflow typically combines an **initial consistent snapshot** with **Change Data Capture (CDC)** from the binary log. The snapshot moves baseline data to the target; replication or a binlog reader continuously streams new changes. Once the target catches up, operations briefly pause writes, confirm both sides are synchronized, and cut the application over to the new server.

This lesson focuses on planning, taking snapshots, parallel data loading, syncing remaining deltas, and executing a safe cutover. The goal is to minimize downtime while preserving data consistency.

## 1. Objectives and Migration Model

After this lesson, you will be able to:

- Explain why plain dump and restore are insufficient when the source keeps receiving writes.
- Design a consistent snapshot and capture its exact matching binary log position.
- Select dump/load tools suited to data volume.
- Configure GTID or file/position replication to sync post-snapshot changes.
- Monitor lag, binary log retention, and applier errors throughout the process.
- Plan write freeze, final verification, and cutting applications over to the target.
- Handle common failures and prepare a controlled rollback plan.

### 1.1. Why Are Two Phases Needed?

Suppose the source has an **orders** table with millions of rows. While the dump starts, the application continues inserting orders, updating statuses, and recording payments. A snapshot only reflects state at one point in time. If you load the snapshot and immediately open the application on the target, changes occurring during dump and load will be missing.

Suitable model:

~~~mermaid
flowchart LR
    APP[Application] --> SRC[Source MySQL]
    SRC -->|Consistent snapshot| DUMP[Dump / staging area]
    DUMP -->|Bulk load| DST[Target MySQL]
    SRC -->|Binary log / CDC| DST
    DST -->|Caught up| CUTOVER[Cutover]
    APP -. after cutover .-> DST
~~~

The workflow has two streams:

1. **Initial load:** transfer the baseline dataset at a defined snapshot point.
2. **Catch-up:** replay transactions recorded after the snapshot so the target approaches the source's current state.

During this time, the source remains the primary writer. The target receives data only through the bulk load and replication streams; applications must not write independently to the target yet. This avoids having to merge two potentially conflicting write streams.

### 1.2. Choosing Migration Scope

Before picking tools, define the scope clearly:

- Full instance or only a single schema?
- Do users, roles, grants, routines, events, and triggers need to move?
- Are there MyISAM or non-transactional tables?
- Are there large tables lacking primary or unique keys?
- Will DDL changes occur frequently during the migration?
- Must GTIDs be preserved so the target continues acting as a replica or joins another topology?
- How much write-pause downtime can the application tolerate?

If the target will replace the entire source instance and receive replication from the source during transition, prefer a snapshot covering the source's full data scope and GTIDs. When migrating a single schema, carefully inspect multi-schema transactions, triggers, routines, and dependent tables; GTID is a server-wide transaction identifier, not a per-schema identifier.

## 2. Preparing Source and Target

### 2.1. Compatibility Inventory

Record before copying:

| Item | What to Verify |
|---|---|
| Version | Source and target MySQL versions and replication compatibility between them |
| Engine | InnoDB, MyISAM, and other engines |
| Schema | Data types, generated columns, partitions, indexes, constraints |
| Charset/collation | Charsets at server, database, table, and column levels |
| SQL mode | Data conversion and statement-handling rules |
| Time zone | `time_zone`, `system_time_zone`, `TIMESTAMP` data |
| Objects | Views, triggers, routines, functions, events, and definers |
| Accounts | Users, roles, grants, authentication plugins, and app privileges |
| System | `lower_case_table_names`, InnoDB settings, disk capacity, IOPS, RAM |
| Security | TLS, replication accounts, secrets, and dump access controls |

Do not assume two servers share identical settings merely because they run the same MySQL version. For example, collation differences can alter string comparisons or index uniqueness. Time zone differences can shift displayed timestamps if `TIMESTAMP` conversion rules are not verified.

For version-upgrade migrations, check compatibility of DDL, reserved keywords, authentication plugins, data types, and changed features. Run the version-appropriate upgrade checker before loading large datasets.

### 2.2. Preparing Binary Logs and GTID

When using replication to catch up on changes, the source must retain binary logs long enough to cover the entire dump, transfer, load, and catch-up duration.

Check configuration:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'log_bin';
SHOW GLOBAL VARIABLES LIKE 'binlog_format';
SHOW GLOBAL VARIABLES LIKE 'binlog_row_image';
SHOW GLOBAL VARIABLES LIKE 'gtid_mode';
SHOW GLOBAL VARIABLES LIKE 'enforce_gtid_consistency';
SHOW GLOBAL VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW BINARY LOG STATUS;
~~~

For GTID-based migrations, both servers must have GTID configured per replication requirements. The source must have **gtid_mode=ON**; the target must be configured properly to use **SOURCE_AUTO_POSITION=1**. Verify actual GTID status before starting, not just configuration files.

For row-event replication, **binlog_format=ROW** is usually appropriate because logs record row changes. It reduces dependence on default schema context and SQL statement interpretation during replay. **binlog_row_image** must match your CDC tool and recovery requirements; check tool documentation before choosing anything other than `FULL`.

Retain binary logs from the snapshot checkpoint until the target catches up. If the source purges needed logs before the target reads them, replication can stop with missing-GTID or missing-log-file errors. Do not manually run `PURGE BINARY LOGS` during migration without confirming all replicas and CDC processes have consumed those logs.

### 2.3. Accounts and Connections

Use dedicated accounts for migration tasks:

- The dump account holds only read privileges and privileges needed to fetch snapshot/binlog metadata.
- The replication account holds only the replication privileges appropriate for your MySQL version.
- The load account holds privileges to create schemas, tables, indexes, and load data on the target.
- Replication connections use TLS and verify the source server certificate.
- Store passwords in a secret manager or equivalent vault; never place passwords in scripts, logs, or source repositories.

For replication connections, the source account needs appropriate replication privileges. The dump account may need **REPLICATION CLIENT** to read binary log coordinates; some snapshot methods also require privileges such as **RELOAD** or **BACKUP_ADMIN**. Grant exact privileges required by your tool and version.

## 3. Creating a Consistent Snapshot

### 3.1. The Snapshot Must Align with a Single Log Position

The snapshot and binary log coordinates must represent the exact same logical point in time. If you dump data at point A but start replication from point B later than A, transactions between A and B will be missed. Starting earlier than A without a mechanism to recognize transactions already in the snapshot can apply changes twice.

Therefore, use a snapshot tool capable of recording the matching GTID set or file/position. Never take a snapshot with one tool and fetch binlog coordinates separately at another time.

### 3.2. Using MySQL Shell for Large Datasets

MySQL Shell provides **util.dumpSchemas()**, **util.dumpInstance()**, and **util.loadDump()** with chunking, parallel dump/load, compression, and progress tracking. For large datasets, chunking lets multiple workers process independent slices concurrently.

Example dumping one schema:

~~~javascript
util.dumpSchemas(
  ['appdb'],
  '/backup/appdb-dump',
  {
    threads: 8,
    bytesPerChunk: '128M',
    consistent: true,
    checksum: true
  }
);
~~~

This example creates a consistent dump and splits data into chunks averaging roughly 128 MB before compression. Tune **threads** to source CPU, I/O, and read load. Adding workers does not always speed up the dump; too many workers can contend for I/O with production workloads.

For full-instance migrations, use **util.dumpInstance()** and explicitly select the scope of schemas, users, and objects to move. For single-schema migrations, **util.dumpSchemas()** fits better, though you must understand global GTID constraints if the target will continue replicating.

The dump utilities default to consistent snapshots. With **consistent: true**, the tool coordinates snapshot transactions and backup locks to maintain consistency while workers read data. Only InnoDB tables receive transactional snapshot guarantees. Non-transactional tables must be handled separately or with an appropriate locking plan.

### 3.3. Dump Metadata

Dumps created by MySQL Shell contain a metadata file **@.json**. The metadata stores **gtidExecuted** and may store the source binary log file/position if the dump account has **REPLICATION CLIENT** privilege.

During load, you can display metadata:

~~~javascript
util.loadDump('/backup/appdb-dump', {
  threads: 8,
  showMetadata: true,
  checksum: true
});
~~~

Inspect and record the GTID set and binlog coordinates from the metadata. This information is needed to configure replication after the initial load completes.

Note: **util.loadDump()** does not automatically apply the source's GTID set to the target just because metadata contains **gtidExecuted**. To use GTID auto-position, apply the GTID set per the MySQL Shell and MySQL Server procedure for your version, typically via **updateGtidSet**. For a MySQL 8.0 target, depending on the target's GTID state, you can use **append** or **replace**; both options have prerequisites regarding existing GTID sets and must not be chosen blindly.

When using **updateGtidSet** on standard MySQL Server, set **skipBinlog: true** during load as required by MySQL Shell. Do not use this option when Group Replication is running on the target. Review target-version prerequisites and inspect **gtid_executed** and **gtid_purged** before applying.

**Warning for single-schema migrations:** GTID is a server-wide transaction set. Metadata of a single-schema dump can still contain the source's full GTID set. If you load only **appdb** yet apply the source's entire GTID set to the target, the target may claim it already executed transactions for other schemas whose data was never loaded. When resuming replication, this can skip needed changes. Apply the full GTID set only when the snapshot and data scope truly cover those transactions; if migrating a single schema, design a dedicated CDC and transaction-scoping approach, or choose a full-instance migration.

### 3.4. Using mysqldump for Moderate Scale or File/Position Streams

For moderate datasets or when using file/position replication, you can use **mysqldump**:

~~~bash
mysqldump --login-path=migrate \
  --single-transaction --quick \
  --source-data=2 \
  --set-gtid-purged=OFF \
  --routines --events --triggers --hex-blob \
  --databases appdb \
  > appdb.sql
~~~

**--single-transaction** takes a consistent snapshot for InnoDB tables without locking writes for the entire dump duration. **--source-data=2** writes the corresponding binary log filename and position into the dump as a comment for administrators configuring a replica. **--set-gtid-purged=OFF** in this example selects the file/position workflow; do not mix it with a GTID auto-position workflow.

**--source-data** requires binary logging enabled and privileges to read binlog status; combined with **--single-transaction**, the server only holds a brief global read lock at the start. The account typically needs **RELOAD** and privileges to view binary log status. Check the exit code and the top of the dump file to confirm coordinates were recorded.

**--single-transaction** guarantees a consistent snapshot only for transactional tables such as InnoDB. During the dump, do not execute **ALTER TABLE**, **CREATE TABLE**, **DROP TABLE**, **RENAME TABLE**, or **TRUNCATE TABLE** on involved tables; concurrent DDL can cause the dump to fail or become inconsistent. **--quick** streams rows rather than buffering entire tables in client memory.

For very large datasets, a single SQL file takes a long time to load and cannot easily leverage parallelism. In those cases, consider MySQL Shell dump/load utilities or a physical backup tool compatible with the target version and architecture.

## 4. Loading Baseline Data onto the Target

### 4.1. Preparing the Target Machine

Before loading:

- Confirm the target is a fresh instance or target schemas have been cleaned per plan.
- Configure a unique **server_id**, GTID, and binary logging if the target will become a replica.
- Verify disk capacity for data, redo, undo, temporary tablespaces, binary logs, and staging.
- Check **max_allowed_packet**, connection limits, privileges, and required plugins.
- Confirm no applications or jobs are writing to target schemas.
- Set appropriate read-only policies to prevent out-of-band writes during migration.

If the load will apply the source's GTID set, prepare the target to meet **updateGtidSet** prerequisites. Do not let the target hold unrelated transactions that intersect the GTID set being imported.

### 4.2. Parallel Loading and Time Optimization

Example loading a MySQL Shell dump:

~~~javascript
util.loadDump('/backup/appdb-dump', {
  threads: 8,
  deferTableIndexes: 'all',
  analyzeTables: 'on',
  checksum: true
});
~~~

**deferTableIndexes: 'all'** creates primary keys first and defers secondary indexes until after data is loaded. This can reduce per-row index maintenance overhead, though the final index-building phase still demands CPU, I/O, and temporary space. **analyzeTables: 'on'** updates table statistics after load so the optimizer has accurate metadata.

If the target will become a GTID replica of the source, add GTID update options per plan, for example:

~~~javascript
util.loadDump('/backup/full-instance-dump', {
  threads: 8,
  deferTableIndexes: 'all',
  checksum: true,
  showMetadata: true,
  updateGtidSet: 'append',
  skipBinlog: true
});
~~~

This example applies to an instance/schema dump and a MySQL 8.0 target verified for GTID prerequisites. Use **append** only when the dump's GTID set does not intersect the target's existing **gtid_executed**. **replace** has different prerequisites and can overwrite **gtid_purged**; do not pick it without reconciling GTID sets first. Do not use **updateGtidSet** for table dumps or when Group Replication is running on the target.

During loading, monitor:

- Active worker count and load throughput.
- CPU, memory, disk I/O, storage latency, and remaining disk space.
- Data conversion errors, index errors, and constraint errors.
- Secondary index build duration.
- Progress by table/chunk and tool resume capability.

Adjust **threads** and chunk size based on measurements. If the source is heavily loaded, throttle read rate or run the dump during off-peak hours. If the target is I/O-bound, adding more workers can worsen total elapsed time.

### 4.3. Loading with mysqldump Output

For SQL dumps:

~~~bash
mysql --login-path=restore < appdb.sql
~~~

This command runs all SQL statements in the file. Check the client exit code and logs for mid-run errors. When re-running after a failure, determine how far statements executed and clean up or reinitialize the target before retrying. Never assume a dump file is safely idempotent on re-run.

## 5. Catching Up Changes via Replication or CDC

### 5.1. Creating a Replication Account

Example on the source:

~~~sql
CREATE USER 'migrate_repl'@'target-host'
  IDENTIFIED BY 'REPLACE_WITH_SECRET';

GRANT REPLICATION SLAVE ON *.* TO 'migrate_repl'@'target-host';
~~~

Replace password and host with securely managed values. Replication privilege names or requirements can vary by MySQL version; use the privilege name supported by your running version's documentation. Replication connections should use TLS and verify the source certificate.

### 5.2. GTID Auto-Position

Once source and target have GTID configured, after loading the snapshot and applying the GTID set, configure the target:

~~~sql
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST = 'mysql-source.example',
  SOURCE_PORT = 3306,
  SOURCE_USER = 'migrate_repl',
  SOURCE_AUTO_POSITION = 1,
  SOURCE_SSL = 1,
  SOURCE_SSL_CA = '/etc/mysql/ca.pem',
  SOURCE_SSL_VERIFY_SERVER_CERT = 1;

START REPLICA;
~~~

Credentials are supplied via your organization's secure secret workflow. Never put real passwords in documentation or shared command histories.

With **SOURCE_AUTO_POSITION=1**, the replica sends the GTID set it has received or executed; the source sends transactions whose GTIDs the replica lacks. The source must retain binary logs containing the needed GTIDs. If logs have been purged, the replica may fail to start and require reinitializing from a fresh snapshot or a complete log archive.

### 5.3. File/Position Replication

If using **mysqldump --source-data=2** with file/position, read the filename and position from the dump header comments and configure:

~~~sql
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST = 'mysql-source.example',
  SOURCE_PORT = 3306,
  SOURCE_USER = 'migrate_repl',
  SOURCE_LOG_FILE = 'mysql-bin.000123',
  SOURCE_LOG_POS = 456789,
  SOURCE_SSL = 1,
  SOURCE_SSL_CA = '/etc/mysql/ca.pem',
  SOURCE_SSL_VERIFY_SERVER_CERT = 1;

START REPLICA;
~~~

Replace **SOURCE_LOG_FILE** and **SOURCE_LOG_POS** with the actual coordinates from the dump. Never combine **SOURCE_AUTO_POSITION=1** with **SOURCE_LOG_FILE** or **SOURCE_LOG_POS** in the same configuration. Choose one consistent positioning mechanism per channel.

### 5.4. Monitoring Replication

On the target:

~~~sql
SHOW REPLICA STATUS\G
~~~

Monitor critical fields:

- **Replica_IO_Running** and **Replica_SQL_Running**: whether receiver and applier threads are running.
- **Last_IO_Error** and **Last_SQL_Error**: most recent connection or apply error.
- **Seconds_Behind_Source**: reference lag indicator, not sole proof of synchronization.
- **Retrieved_Gtid_Set** and **Executed_Gtid_Set**: GTID sets received and applied.
- **Relay_Source_Log_File** and **Exec_Source_Log_Pos**: source file read and applier position processed when using file/position.

Also monitor source binary log disk usage, target relay logs, applier worker count, and system load. If the receiver runs while the applier errors out, logs keep arriving while target data falls behind.

With GTID, you can wait for the target to execute a GTID set captured on the source:

~~~sql
SELECT WAIT_FOR_EXECUTED_GTID_SET('SOURCE_GTID_SET', 60);
~~~

Replace **SOURCE_GTID_SET** with the actual GTID set retrieved from the source. Return value **0** means the target executed the full GTID set within the timeout; **1** means the timeout expired. This function is useful when preparing cutover, provided the GTID set accurately represents the migrated data scope.

### 5.5. Do Not Filter Replication Arbitrarily

If migrating only one schema, using **replicate-do-db**, **replicate-wild-do-table**, or CDC filters must be designed carefully. Transactions can span multiple schemas or write to audit, ledger, outbox, and summary tables. Filters can cause parts of a transaction to be dropped.

GTID is also server-wide. Do not mark the source's full GTID set as executed on the target if only one schema's data was loaded. Identify cross-schema dependencies and test results on a clone. When an independent data boundary cannot be proven, migrate all coupled data together and split later.

## 6. Pre-Cutover Data Verification

### 6.1. Structure and Object Checks

Reconcile:

- Databases, tables, columns, indexes, primary keys, and foreign keys.
- Views, triggers, stored procedures, functions, and events.
- Charsets, collations, SQL modes, and time zones.
- Users, roles, grants, definers, and authentication plugins.
- Partitions, generated columns, and special table attributes.

Do not count tables alone. A missing trigger can let target writes succeed without generating audit records; a missing event can stop periodic jobs from running.

### 6.2. Data Checks

Use multiple verification layers:

- Compare row counts per table or partition.
- Compare monetary totals, quantities, min/max values, and business metrics.
- Check duplicate keys, orphan records, and table relationships.
- Compare checksums where tools support them.
- Sample records at the start, middle, and end of key ranges.
- Execute critical business queries on the target.

Example checking row count and total amount:

~~~sql
SELECT COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount,
       MIN(created_at) AS first_order,
       MAX(created_at) AS last_order
FROM appdb.orders;
~~~

Run the same query on source and target at the same data checkpoint. If the source keeps taking writes, results will differ due to query timing. Perform exact comparisons after pausing writes during cutover or at a consistent GTID checkpoint.

### 6.3. Application Load Checks

Before cutover, run smoke tests against the target:

- Authenticate using application accounts.
- Run common read queries.
- Test writes in a test schema or rollback-safe transaction.
- Verify queries use indexes as expected.
- Verify connection pools, TLS, privileges, and response times.
- Confirm background jobs, Event Scheduler, and dependent services.

Never open production traffic solely because replication shows no errors. Confirm the application works with target schemas and privileges.

## 7. Low-Downtime Cutover

### 7.1. Pre-Cutover Preparation

Before cutover:

1. Finish initial load and let replication catch up close to the source.
2. Verify zero receiver/applier errors and confirm binary logs have not been purged.
3. Complete structure checks, checksums, and business query verification.
4. Prepare new endpoints, DNS, Router, or connection pool settings.
5. Announce the cutover window and prepare maintenance mode.
6. Clearly designate who authorizes opening writes on the target.

Never wait until writes are paused to discover the target is missing an index, user, or privilege.

### 7.2. Cutover Procedure

A typical sequence for a GTID-based full-instance migration:

**Step 1 — Stop new writes.** Enable maintenance mode and pause workers, schedulers, consumers, and auxiliary write streams. Drain in-flight requests and wait for open transactions to finish.

**Step 2 — Fence the source.** Put the source in read-only mode to prevent accidental writes:

~~~sql
SET GLOBAL super_read_only = ON;
~~~

Keep the source running so the target can finish reading binary logs. Never allow applications to fail back automatically to the source during cutover.

**Step 3 — Capture final checkpoint.** Read the final GTID set after all write transactions have stopped:

~~~sql
SELECT @@GLOBAL.gtid_executed;
~~~

**Step 4 — Wait for target catch-up.** On the target, wait for the captured GTID set:

~~~sql
SELECT WAIT_FOR_EXECUTED_GTID_SET('FINAL_SOURCE_GTID_SET', 120);
~~~

If the wait times out, do not open writes on the target. Inspect receiver/applier status, SQL errors, missing GTIDs, and log capacity.

**Step 5 — Stop the replication stream.** Once the target has executed the final checkpoint, stop the channel:

~~~sql
STOP REPLICA;
~~~

Keep replication state and metadata for inspection or contingency. Reset the channel only after confirming configuration details and relay logs are no longer needed.

**Step 6 — Switch the application.** Point endpoints, DNS, or Router to the target. Verify new connections and read queries first.

**Step 7 — Open writes on the target.** Set target write mode per policy:

~~~sql
SET GLOBAL read_only = OFF;
~~~

Setting `read_only` to `OFF` also clears `super_read_only`, allowing applications to write on the target after endpoints have been switched and verified.

Only then disable maintenance mode and restart workers/consumers in the planned order.

**Step 8 — Keep the source fenced.** Keep the source read-only and isolated from application write paths. Record the cutover timestamp, final GTID, and verification results.

This sequence ensures two primaries never accept writes simultaneously during cutover. Adjust commands and privileges to your specific version, topology, and replication setup.

### 7.3. For Single-Schema Migrations

If migrating only one schema, comparing server-wide **gtid_executed** does not prove the target schema has all its data. The GTID set may include transactions from un-dumped schemas. Use a CDC tool capable of tracking exact tables and preserving needed transaction boundaries, or cut over against a dedicated application-level reconciliation checkpoint. Never rely on a global GTID set as sole proof of data completeness for a filtered schema.

## 8. Rollback and Stabilization Phase

### 8.1. No Simple Fallback Once the Target Accepts Writes

Before opening writes on the target, you can abort cutover and route applications back to the source because the source still holds intact data and the target has no new transactions.

Once applications write to the target, the source becomes stale. Switching applications straight back to the source drops transactions committed on the target. At that point you need one of these options:

- Establish reverse replication from target back to source per a tested plan.
- Sync post-cutover deltas via a CDC/reconciliation workflow.
- Restore from a fresh backup and re-run migration if data has diverged.

Never let applications write to both places simultaneously just for "easy rollback." Dual-write requires dedicated design for idempotency, transaction ordering, partial-failure handling, and reconciliation; without that, it introduces severe inconsistency risks.

### 8.2. Post-Cutover Monitoring

During stabilization, monitor:

- Application connection errors, timeouts, and retry rates.
- Query latency and throughput on the target.
- CPU, memory, IOPS, disk usage, and binary log growth rate.
- Deadlocks, lock waits, constraint errors, and SQL errors.
- Business reconciliation results.
- Background jobs, events, triggers, and integration flows.
- Queries whose execution plans differ markedly from the source.

Keep the old source read-only for the agreed rollback window. Do not delete source data, backups, or binary logs until system owners confirm stability and retention policy permits cleanup.

## 9. Common Incidents

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Snapshot slower than expected | Large tables, low source I/O, oversized chunks, or too few workers | Tune chunk/thread settings, throttle load, and re-measure |
| Load bottlenecks on indexes | Building many secondary indexes concurrently or slow storage | Defer indexes if appropriate, increase IOPS, and watch temp space |
| Replication fails to start | Wrong coordinates, missing privileges, TLS issue, or incompatible GTID set | Inspect replication status, account, and snapshot metadata |
| Source purged needed logs | Dump/load took longer than retention or logs were manually deleted | Take a fresh snapshot or use complete binlog archive; raise retention next time |
| Applier stops on duplicate key | Snapshot and replication start position mismatched, or target had independent writes | Reinitialize target from matching snapshot and coordinates; never skip errors blindly |
| Applier errors on missing table/column | DDL changed during dump or source/target schemas drifted | Inspect DDL history and align schemas before replaying |
| Checksums differ | Dump missed data, type/charset conversion, or load error | Halt cutover, isolate differing table/chunk, and reload cleanly |
| Target fails to catch up | High write rate, network, or underpowered applier | Reduce load, add resources, tune parallel applier workers via benchmarks, and widen window |
| Slow queries after cutover | Different index/statistics, collation, or optimizer settings | Run `ANALYZE TABLE`, inspect `EXPLAIN ANALYZE`, and tune on target |
| Rollback loses new transactions | Old source lacks new transactions committed on target | Avoid blind switch-back; use reverse replication or data reconciliation |

When replication stops, capture **Last_IO_Error**, **Last_SQL_Error**, server logs, GTID sets, binlog coordinates, and failure timestamp. Never use **SQL_SLAVE_SKIP_COUNTER** or manually skip transactions just to flip replication back to Running. Skipping transactions silently introduces data inconsistencies that are hard to detect immediately.

## 10. Operational Checklist

### Before Dumping

- [ ] Inventoried schemas, objects, engines, charsets, collations, and versions.
- [ ] Verified binary logs/GTID and adequate log retention duration.
- [ ] Verified accounts, TLS, staging capacity, and access privileges.
- [ ] Froze DDL on objects being migrated.
- [ ] Selected a snapshot tool that captures matching coordinate metadata.

### During Load and Catch-Up

- [ ] Confirmed dump completed and metadata is intact.
- [ ] Loaded data with appropriate chunking/workers.
- [ ] Monitored CPU, I/O, disk, index builds, and load errors.
- [ ] Configured replication with accurate GTID or file/position.
- [ ] Monitored receiver, applier, lag, GTIDs, and binary log retention.
- [ ] Verified checksums, row counts, and business invariants.

### Before and After Cutover

- [ ] Smoke-tested application and verified target endpoints.
- [ ] Stopped writes, drained transactions, and fenced the source.
- [ ] Waited for target to execute up to the final checkpoint.
- [ ] Stopped replication and switched endpoints.
- [ ] Opened writes on the target after verification.
- [ ] Kept source read-only with a rollback plan ready.
- [ ] Monitored errors, latency, data, and background jobs post-cutover.

## 11. Self-Check

**Scenario 1:** The dump took 4 hours and the load took 5 hours. Meanwhile, the application kept writing to the source. Why can't you open the application on the target right after loading finishes?

**Hint:** The snapshot contains data only as of a single checkpoint. Transactions committed after the snapshot checkpoint are not yet on the target; replication or CDC must catch up before cutover.

**Scenario 2:** The source uses GTID and the target loaded only one schema from `util.dumpSchemas()`. Should you apply the entire `gtidExecuted` from metadata onto the target?

**Hint:** Do not apply it mechanically. The GTID set is global to the source and may include transactions from un-loaded schemas. Ensure data and transaction scopes align, or design a dedicated CDC flow.

**Scenario 3:** The target reports `Replica_IO_Running=Yes` but `Replica_SQL_Running=No`. Does that mean the migration has caught up?

**Hint:** No. The receiver may still fetch logs while the applier cannot execute them. Check `Last_SQL_Error`, resolve the data/schema issue, and then resume.

**Scenario 4:** After cutting the application over to the target, several new transactions committed. Operations wants to switch immediately back to the old source. What is the risk?

**Hint:** The old source lacks the new transactions committed on the target. Switching straight back drops or forks data. Reverse replication or delta reconciliation is required before rolling back.

**Scenario 5:** Why must DDL be frozen while taking a transactional snapshot?

**Hint:** A transactional snapshot guarantees InnoDB data consistency, yet concurrent DDL can alter table metadata or structure mid-dump across tables, leading to errors or an inconsistent dump.

## 12. Key Takeaways

- Online migration requires a consistent snapshot plus a CDC stream to catch up on post-snapshot changes.
- Binary log or GTID coordinates must match the snapshot exactly; never capture two independent checkpoints.
- MySQL Shell dump/load utilities provide chunking, parallelism, checksums, and metadata suited to large datasets.
- `mysqldump --single-transaction --source-data=2` produces an InnoDB snapshot with binlog coordinates, using a brief global read lock at the start.
- Use `SOURCE_AUTO_POSITION=1` only when GTID on source/target and the snapshot's GTID set are properly aligned.
- GTID is server-wide; never mark the source's entire GTID set as executed when migrating only a subset of data without handling dependencies.
- Retain binary logs long enough, monitor receiver/applier, and never skip replication errors arbitrarily.
- Cutover requires stopping writes, draining transactions, fencing the source, waiting for target catch-up, and only then switching endpoints and opening writes.
- Once the target accepts writes, rollback requires reverse sync or reconciliation; you cannot simply point apps back to the old source.

## References

- [MySQL 8.4 Reference Manual: mysqldump](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html) — `single-transaction`, `source-data`, `quick`, and snapshot limitations.
- [MySQL Shell 8.4 API: Dump and Load Utilities](https://dev.mysql.com/doc/dev/mysqlsh-api-python/8.4/group__util.html) — parallel dump/load, consistent snapshot, and chunk options.
- [MySQL Shell 8.4 Reference: Dump Loading Utility](https://dev.mysql.com/doc/mysql-shell/8.4/en/mysql-shell-utilities-load-dump.html) — GTID metadata, `showMetadata`, `updateGtidSet`, and `checksum`.
- [MySQL 8.4 Reference Manual: CHANGE REPLICATION SOURCE TO](https://dev.mysql.com/doc/refman/8.4/en/change-replication-source-to.html) — configuring replication via GTID or file/position.
- [MySQL 8.4 Reference Manual: GTID Auto-Positioning](https://dev.mysql.com/doc/refman/8.4/en/replication-gtids-auto-positioning.html) — transaction synchronization via GTID.
