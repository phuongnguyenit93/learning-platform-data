# Impact on Replication Lag, Disk Space, Redo, and Maintenance Windows

Changing the schema on a large MySQL table can affect the entire system, even when the application is only adding a single column or index. Depending on DDL type and MySQL version, the operation may update metadata only, rebuild the table structure in place, or build an intermediate table and copy data. Each approach carries distinct costs in lock duration, CPU, I/O, disk space, redo/undo logs, and binary logs.

In a replication topology, DDL also executes on every replica. An operation that finishes quickly on the primary yet takes a long time on a replica can drive replication lag up, causing replica reads to return stale data. Therefore, a schema evolution plan must anticipate costs on every topology member, determine the DDL algorithm, monitor backlog, and define clear abort or recovery procedures.

## 1. Why can a schema change consume heavy resources?

`ALTER TABLE` does not always just edit one metadata row. MySQL may have to:

- Read all records to convert data types or rebuild the clustered index.
- Rebuild secondary indexes and update storage structures.
- Record concurrent modifications occurring during DDL in the online alter log.
- Write corresponding redo, undo, and binary logs for the work performed.
- Use extra temporary files or intermediate tables while the old table remains intact.
- Acquire metadata locks at the start and end of the operation to keep table structure consistent across critical phases.

Cost depends on change type, data size, index count, row format, MySQL version, storage engine, disk speed, concurrent write load, and replication state. Two tables with identical row counts but different index layouts or row sizes can have vastly different schema-change durations.

Before scheduling, classify DDL by actual execution mechanism: `INSTANT`, `INPLACE`, or `COPY`. Algorithm names are not absolute guarantees of online behavior; verify that the exact operation is supported on your exact version and table structure.

## 2. InnoDB's three DDL algorithms

### INSTANT — metadata modification

`ALGORITHM=INSTANT` applies to changes supported by updating metadata without rebuilding the entire table. Common examples include certain column additions or drops on eligible MySQL 8.0 versions.

```sql
ALTER TABLE sales.orders
  ADD COLUMN source_channel VARCHAR(32) NULL,
  ALGORITHM=INSTANT;
```

Characteristics:

- Usually completes very quickly, even on huge tables, because it avoids scanning and copying all rows.
- Minimizes I/O and temporary disk usage compared to rebuilds.
- Still requires metadata locks at specific points, so it can wait on transactions holding metadata locks.
- Usable only for operations and table structures supported by that version. Certain limits vary by version, row format, and table alteration history.

When `ALGORITHM=INSTANT` is specified, MySQL returns an error if the operation does not support instant execution rather than silently falling back to a slower algorithm. This prevents an expected near-instant change from unexpectedly becoming a full rebuild. Verify version-specific documentation before deploying.

### INPLACE — operating within InnoDB structures

`ALGORITHM=INPLACE` lets InnoDB execute changes without the general `COPY` workflow of creating a new table and copying all rows. However, **`INPLACE` does not mean no rebuild**. Some operations still rebuild the table or indexes and can read/write huge volumes of data.

Example creating a secondary index, when operation and table support online DDL:

```sql
ALTER TABLE sales.orders
  ADD INDEX idx_status_created (status, created_at),
  ALGORITHM=INPLACE,
  LOCK=NONE;
```

`LOCK=NONE` requests permitting concurrent DML while the operation runs. If MySQL cannot satisfy that lock level for the specific change, the statement fails rather than silently using a stricter lock. Even so, DDL still needs brief metadata locks at start or finish.

For online DDLs permitting concurrent DML, InnoDB records concurrent modifications in an online alter log and applies them before finalizing. If concurrent changes exceed `innodb_online_alter_log_max_size`, the DDL fails. Raising the limit reduces overflow risk yet adds work during finalization; never raise this variable without measuring write load and disk space first.

### COPY — creating an intermediate table and copying data

`ALGORITHM=COPY` builds an intermediate table structure, copies data and indexes, and swaps in the new table. This is typically the most resource-intensive method on large tables.

Impacts may include:

- Reading nearly the entire old table and writing the new table.
- Rebuilding all indexes on the new table.
- Requiring simultaneous disk space for old table, new table, indexes, and temporary files.
- Scaling I/O, CPU, and completion duration with table size.
- Restricting or blocking writes during copying depending on supported lock levels.
- Requiring a cutover metadata lock to swap active table structures.

Never treat `COPY` as safe merely because reads can continue during part of the operation. Assess impacts on writers, readers, replicas, and disk space before running.

### Quick comparison

| Algorithm | Execution method | Typical impact | Things to verify |
|---|---|---|---|
| `INSTANT` | Updates metadata for supported operations | Short duration, minimal I/O and extra space | Version, change type, row format, metadata locks |
| `INPLACE` | InnoDB handles change in place; some operations still rebuild | Can consume heavy CPU, I/O, redo, and space | Whether rebuild occurs, `LOCK=NONE` support, online alter log |
| `COPY` | Builds intermediate table and copies data | Heavy I/O, large space needed, can block writes long | Copy time, peak disk usage, locks, and cutover |

## 3. Metadata locks and maintenance wait windows

MySQL uses metadata locks (MDL) to protect table, view, routine, and related object definitions while statements use them. A transaction accessing a table can hold metadata locks until the transaction ends. DDL must acquire locks compatible with altering structure, typically requiring stronger locks at start or cutover.

A common incident scenario:

1. Transaction A opens and touches `sales.orders` without committing for a long time.
2. DDL B requests an exclusive metadata lock and waits on Transaction A.
3. Incoming queries C and D accessing the table queue behind the pending DDL request.
4. An `ALTER TABLE` that appears to have done nothing yet creates a query pileup and spikes response latency.

Therefore, maintenance time is not just how long MySQL takes to copy or rebuild. Add MDL wait time, concurrent-change sync phases, cutover, and post-change verification.

Inspect active metadata locks:

```sql
SELECT
  OBJECT_TYPE,
  OBJECT_SCHEMA,
  OBJECT_NAME,
  LOCK_TYPE,
  LOCK_DURATION,
  LOCK_STATUS,
  OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = 'sales'
  AND OBJECT_NAME = 'orders';
```

`LOCK_STATUS` shows whether locks are granted or pending. Join `OWNER_THREAD_ID` with `performance_schema.threads` to locate the corresponding connection:

```sql
SELECT
  ml.LOCK_STATUS,
  ml.LOCK_TYPE,
  ml.OWNER_THREAD_ID,
  th.PROCESSLIST_ID,
  th.PROCESSLIST_USER,
  th.PROCESSLIST_HOST,
  th.PROCESSLIST_TIME,
  th.PROCESSLIST_STATE,
  th.PROCESSLIST_INFO
FROM performance_schema.metadata_locks AS ml
LEFT JOIN performance_schema.threads AS th
  ON th.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.OBJECT_SCHEMA = 'sales'
  AND ml.OBJECT_NAME = 'orders';
```

Also inspect `SHOW FULL PROCESSLIST` and open transactions. On systems with the `sys` schema, `sys.schema_table_lock_waits` helps identify waiting and blocking sessions.

Before running DDL, cap metadata lock wait time in the session:

```sql
SET SESSION lock_wait_timeout = 30;
```

`lock_wait_timeout` governs metadata lock waits. It differs from `innodb_lock_wait_timeout`, which governs InnoDB row lock waits. Setting a timeout makes DDL fail fast when a long transaction holds a lock, though it does not make the DDL execute faster once started.

Never `KILL` a session based solely on runtime. Determine whether it is a business transaction, waiting DDL, or copying DDL; assess rollback impact and coordinate with the workload owner before terminating connections.

## 4. Impact on replication lag

When binary logging is enabled, DDL is written to the binary log as statements. DDL does not turn into row events merely because `binlog_format=ROW`. Replicas receive the DDL event and execute the statement locally on their own tables.

This creates costs in two places:

- The primary executes the schema change and absorbs the DDL load.
- Every replica must execute the corresponding DDL according to its own version and table structure.

If DDL takes a long time on a replica, the replication applier cannot apply subsequent transactions during that interval. Meanwhile, the primary continues accepting writes, causing relay logs and backlog to grow. Read queries hitting the replica may see stale data or become unusable while the schema change runs.

Causes of rising lag:

1. Replicas have slower I/O or CPU than the primary, prolonging rebuilds.
2. Replicas are running reporting queries or backups that compete for resources.
3. Index creation or table rebuilds generate heavy I/O and redo activity.
4. Primary DML continues arriving while the applier is busy with DDL.
5. Large transactions or multiple replication workers are serialized around DDL execution boundaries.
6. Replica version or schema is incompatible with the DDL, stopping the applier on error rather than merely increasing lag.

Before running, inspect all replicas and downstream topology. A replica in another region or on slower disks can become the bottleneck even when the primary finishes quickly. In chained replication, lag on an intermediate replica cascades downstream.

Check replication status:

```sql
SHOW REPLICA STATUS\G
```

Monitor fields such as `Replica_IO_Running`, `Replica_SQL_Running`, `Seconds_Behind_Source`, `Last_SQL_Error`, `Retrieved_Gtid_Set`, and `Executed_Gtid_Set`. `Seconds_Behind_Source` is a helpful indicator but not a complete measure in all situations; it can read `NULL` depending on applier or connection state. Combine GTIDs, worker states, and application metrics to confirm replicas have caught up.

On MySQL 8.0, inspect worker states:

```sql
SELECT *
FROM performance_schema.replication_applier_status_by_worker;
```

On older versions, command and column names may differ. Cross-check with your exact version's docs.

### Do not confuse lag with replication errors

| Symptom | Interpretation |
|---|---|
| `Replica_SQL_Running=Yes`, lag rising | Applier is running but hasn't caught up with workload or long DDL |
| `Replica_SQL_Running=No`, `Last_SQL_Error` populated | Applier stopped on an error; resolve root cause rather than waiting |
| `Replica_IO_Running=No` | Replica is not receiving logs from source; check network, privileges, and source state |
| Retrieved GTIDs grow while Executed GTIDs stay flat | Transactions are queued or applier is blocked |
| Replica is readable yet schema diverges | Check whether DDL was delayed, failed, or run manually outside replication |

Never promote a lagging replica or one with divergent schema without evaluating missing transactions and application compatibility.

## 5. Disk space to provision

For rebuild or `COPY` operations, the old table generally stays on disk while MySQL builds the new structure. Peak disk usage may include:

- The existing InnoDB table.
- Intermediate or rebuilt table copy.
- Rebuilt secondary indexes.
- Temporary files and DDL sort workspace.
- Redo logs, undo tablespaces, and binary logs generated during execution.
- Relay logs on replicas while DDL or subsequent transactions wait to apply.
- Backups/snapshots or shadow copies created by migration tools.

Never equate required disk space with the current `.ibd` file size alone. Rebuilds require enough space for both old and new copies to coexist, plus overhead and operational headroom. Exact peak usage depends on algorithm, file-per-table, tablespaces, indexes, version, and tooling.

Estimate data and index sizes for a table:

```sql
SELECT
  TABLE_SCHEMA,
  TABLE_NAME,
  ENGINE,
  TABLE_ROWS,
  ROUND(DATA_LENGTH / 1024 / 1024, 1) AS data_mb,
  ROUND(INDEX_LENGTH / 1024 / 1024, 1) AS index_mb,
  ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024, 1) AS total_mb
FROM information_schema.tables
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'orders';
```

In InnoDB, `TABLE_ROWS` is usually an estimate, not an exact count. `DATA_LENGTH` and `INDEX_LENGTH` aid rough planning; combine them with filesystem usage, tablespaces, and actual growth history.

Inspect data, temporary file, and binary log locations:

```sql
SHOW VARIABLES LIKE 'datadir';
SHOW VARIABLES LIKE 'tmpdir';
SHOW VARIABLES LIKE 'innodb_data_home_dir';
SHOW VARIABLES LIKE 'log_bin_basename';
SHOW BINARY LOGS;
```

Directories may reside on separate filesystems or volumes. Operations must verify free space on every mount point across hosts—`datadir`, `tmpdir`, redo/undo, binary logs, and relay logs. A full temporary directory can fail DDL even when the table's data volume still has free space.

With online schema change tools, the shadow table typically needs space roughly equal to the original table plus indexes while the original continues serving traffic. Add space for binlogs, relay logs, and retained copies during cutover.

## 6. Redo, undo, and the online alter log

### Redo log

The redo log lets InnoDB recover committed changes. Rebuilds, index creation, and concurrent DML generate significant write pressure on storage and redo. When redo generation outpaces checkpoint/flushing capacity, redo pressure and I/O latency rise, impacting both DDL and live workloads.

On MySQL versions supporting `innodb_redo_log_capacity`, redo space is governed by this variable. Adjusting capacity absorbs moderate bursts, yet does not reduce the total work DDL must do. Monitor redo, checkpoints, I/O latency, and `Innodb_log_waits` rather than enlarging capacity to mask an overly heavy rebuild.

### Undo and purge

Undo logs support rollbacks and consistent reads. Long-running active transactions retain old row versions, preventing purge from reclaiming undo history. When schema changes run alongside heavy write loads or long transactions, history list length and undo tablespaces grow. Review long-open transactions before maintenance and check `SHOW ENGINE INNODB STATUS\G` if undo/purge pressure is suspected.

### Online alter log

For online DDL permitting concurrent DML, InnoDB records concurrent changes occurring while building the index or table. The online alter log is capped by `innodb_online_alter_log_max_size`.

Check setting:

```sql
SHOW VARIABLES LIKE 'innodb_online_alter_log_max_size';
```

Under sustained high writes, the online alter log can grow rapidly and hit its cap, failing the operation. Raising the cap may help, though you must evaluate disk space and final log-apply duration. Alternatives include throttling writes, splitting changes, choosing lower-traffic windows, or using another migration strategy.

### Binary logs and relay logs

DDL is recorded in binary logs for replicas to execute. DML during the migration also keeps generating binary logs. If the applier slows down, relay logs accumulate and consume additional disk. Never purge binary logs solely to free disk space while replicas or PITR pipelines still need them; respect retention and confirm all consumers have read them.

## 7. Schema changes with varying costs

You cannot predict the algorithm from the `ALTER TABLE` keyword alone. Verify support for your exact version and table structure.

| Change | Typical cost | Notes |
|---|---|---|
| Instant-supported nullable column add | Low | Still needs MDL; check version limits and column position |
| Adding a secondary index | Usually scans table and builds index `INPLACE` | Consumes I/O, CPU, index space; may allow concurrent DML |
| Changing column data type | May rebuild or `COPY` | Depends on old/new types, length, charset, signedness, and version |
| Changing primary key | Usually rebuilds clustered index | May rebuild entire table and secondary indexes |
| Changing charset/collation | May convert data and rebuild indexes | Check unrepresentable characters and changed comparison order |
| Renaming column or table | May be metadata-only in supported cases | Applications, views, triggers, procedures, and replicas must stay compatible |
| Adding/dropping partitions | Depends on operation and partition layout | May move data or rebuild affected partitions |

Example changing a data type:

```sql
ALTER TABLE sales.orders
  MODIFY COLUMN customer_note VARCHAR(500) NULL;
```

Do not run this example assuming it is always instant or inplace. MySQL may require a rebuild depending on current column definition, version, and table properties. If you need to constrain the algorithm, specify `ALGORITHM` and `LOCK` explicitly after confirming support in staging.

## 8. Atomic DDL does not mean transaction rollback

MySQL 8.0 supports atomic DDL for many InnoDB operations. This ensures DDL recovers consistently if the server crashes mid-execution: metadata and changes from the operation are handled as an atomic unit within supported scope.

However, DDL still follows implicit-commit rules. You cannot wrap `ALTER TABLE` inside an application transaction and use `ROLLBACK` to revert the schema like DML. Atomic DDL also does not restore application logic if new code deployed while the schema change failed, or if the migration completed while the application remains incompatible.

Therefore, every migration needs a viable forward-fix plan or reverse migration. For destructive changes like dropping columns, narrowing types, changing charsets, or dropping tables, take backups and confirm data has moved to the new structure before running irreversible steps.

## 9. Safe schema change planning

A production workflow should start with assessment, not with running `ALTER TABLE`.

### Before running

1. Record MySQL version, engine, exact DDL, `SHOW CREATE TABLE`, table size, and index sizes.
2. Determine usable algorithm: `INSTANT`, `INPLACE`, or `COPY`; check supported `LOCK` levels.
3. Inspect MDL, long-open transactions, writers, and long queries touching the table.
4. Estimate peak disk space on primary and all replicas, covering `datadir`, `tmpdir`, redo/undo, binlogs, and relay logs.
5. Test on a clone matching production size, indexes, version, and write load.
6. Measure duration, I/O, redo, disk space, replication lag, and impact on p95/p99 app latency.
7. Define abort thresholds: max lag, min free disk, max latency, and max maintenance time.
8. Notify application and ops teams; prepare forward-fix, application rollback, or backup restore plans.

### During execution

- Monitor processlist, metadata locks, and DDL progress.
- Monitor CPU, IOPS, storage latency, filesystem free space, redo, and online alter log.
- Monitor replication receiver/applier threads and GTIDs on every replica.
- Watch application response times, timeouts, lock waits, and errors.
- Avoid running multiple heavy rebuild DDLs concurrently on the same storage or topology without load testing.
- Halt further rollout if lag, disk space, or latency hits defined thresholds.

### After execution

- Inspect `SHOW CREATE TABLE` and metadata to confirm exact schema.
- Verify indexes, constraints, defaults, nullability, charset, and collation.
- Confirm replicas applied the DDL and GTIDs caught up.
- Run smoke tests across the application and critical queries.
- Reconcile data, especially after backfills or type conversions.
- Record actual runtime, peak disk usage, peak lag, and incidents to improve future maintenance.

## 10. Expand-and-contract for changes requiring app compatibility

For changes impacting code, deploy schema and application across multiple steps rather than requiring every component to switch simultaneously.

Example renaming `full_name` to `display_name`:

1. **Expand:** add `display_name` as nullable or with a compatible default. Choose a supported algorithm and verify no unexpected rebuild occurs.
2. **Compatible application:** deploy code capable of reading old and new columns and dual-writing both during transition if needed.
3. **Backfill:** update legacy rows in small checkpointed chunks. Each chunk generates redo, undo, and binlogs, so throttle speed to prevent lag spikes.
4. **Switch reads:** switch the application to read `display_name`, check `NULL` counts, and reconcile values between both columns.
5. **Stop old writes:** once all application instances have moved, stop writing `full_name`.
6. **Contract:** in a later deployment, drop `full_name` only after confirming zero code, views, triggers, procedures, or jobs depend on it.

Chunked backfill:

```sql
UPDATE customers
SET display_name = full_name
WHERE customer_id > 0
  AND customer_id <= 10000
  AND display_name IS NULL;
```

This illustrates a key-range update. In practice, size chunks by primary key, row count, runtime, and system load. Update one chunk, commit, save checkpoint, and sleep/throttle if replication lag or I/O rises. Never run one massive transaction updating the whole large table unnecessarily.

## 11. When to consider online schema change tools?

If native online DDL cannot satisfy lock or duration requirements, evaluate tools such as `pt-online-schema-change` or `gh-ost`. These tools generally build a shadow table, copy data in chunks, sync ongoing modifications, and perform cutover.

They shorten prolonged locking in certain cases, but do not eliminate resource costs:

- Require disk space for the shadow table and indexes, roughly matching the original table.
- Copying and syncing changes increase CPU, I/O, redo, and binary logs.
- Replicas must still apply all ongoing changes; lag can rise.
- Cutover still requires metadata locks and can be blocked by long transactions.
- `pt-online-schema-change` uses triggers to sync changes, requiring evaluation of existing triggers, foreign keys, and write overhead.
- `gh-ost` relies on binary logs to track changes and has specific config/version requirements; verify topology compatibility before use.

Never select a tool just because its name says "online." Test on a clone, verify eligibility, privileges, binlog format, foreign keys, triggers, replica topology, disk space, and cutover workflow. Migration tools represent another heavy database workload requiring throttling and monitoring just like native DDL.

## 12. Diagnosing abnormal symptoms

| Symptom | Possible cause | Resolution |
|---|---|---|
| `ALTER TABLE` hangs before starting | Waiting on metadata lock from another transaction or query | Check `performance_schema.metadata_locks`, processlist, and long transactions |
| App queries queue while DDL waits | DDL waits on a strong lock and new requests queue behind it | Identify blocker; cap `lock_wait_timeout`; reschedule if needed |
| DDL runs while I/O spikes | Rebuild, index build, `COPY`, or backfill | Monitor storage latency, throttle workload, and check disk space |
| Filesystem nearly full | Intermediate table, indexes, temp files, redo/binlog, or relay logs growing | Identify growing volume; halt per threshold, never delete needed log files |
| `DB_ONLINE_LOG_TOO_BIG` or online alter log error | Concurrent DML exceeded `innodb_online_alter_log_max_size` | Reduce write load, split change, or reassess cap and timing |
| Replica lag rises after DDL | Applier executing DDL or unable to catch up fast enough | Monitor workers/GTIDs, throttle writes if needed, wait for catch-up before next step |
| Replica SQL thread stops | Incompatible DDL or execution error on replica | Read `Last_SQL_Error`, compare version/schema, follow replication runbook |
| App errors after migration | Code and schema incompatible, constraint/default changed | Halt code rollout, execute forward-fix or restore compatible app version |

Preserve the DDL statement, start/end timestamps, MySQL logs, replication status, and disk metrics during investigation. Never delete temp files or binary logs at the filesystem level without verifying MySQL no longer uses them.

## 13. Practice scenario

A `sales.orders` table has tens of millions of rows, continuous write load, and three read replicas. The engineering team needs an index on `(status, created_at)` to speed up dashboard queries. Requirements: minimize disruption, keep replica lag below threshold, and avoid filling disk volumes.

**Step 1 — Measure baseline.** Collect `SHOW CREATE TABLE`, data/index sizes, write rate, long transactions, free disk space across all four servers, and current replication lag.

**Step 2 — Verify algorithm.** Confirm version and InnoDB support building the secondary index with `ALGORITHM=INPLACE, LOCK=NONE`. Test on a clone with comparable data and write load. Verify online alter log headroom and disk space for the new index.

**Step 3 — Pick window.** Choose a low-write period, set thresholds for lag, I/O latency, free disk, and metadata lock waits. Set `lock_wait_timeout` on the DDL session to avoid unbounded MDL waits.

**Step 4 — Run on primary.** Execute DDL with verified algorithm and lock. Monitor progress, disk, redo, online alter log, processlist, and application health. Do not run other heavy rebuild DDLs concurrently.

**Step 5 — Monitor replicas.** Watch each replica as its applier executes the DDL. If any replica crosses lag thresholds, hold further rollout steps, throttle writes, or wait for catch-up per runbook.

**Step 6 — Verify.** Inspect the index in `SHOW CREATE TABLE`, run queries and `EXPLAIN`, confirm GTIDs applied across all replicas, and monitor post-migration latency.

If native online DDL cannot satisfy lock or disk limits, evaluate an online schema change tool in staging. Account for shadow tables, triggers or binlog capture, copy load, and cutover before deciding.

## 14. Pre-schema-maintenance checklist

- [ ] Identified exact DDL, MySQL version, engine, and table structure.
- [ ] Confirmed whether operation supports `INSTANT`, `INPLACE`, or requires `COPY`.
- [ ] Understood that `INPLACE` can still rebuild tables and `LOCK=NONE` still needs MDL at certain phases.
- [ ] Checked long-open transactions and metadata locks before execution.
- [ ] Estimated peak space for old table, new table, indexes, temp space, redo/undo, binlogs, and relay logs.
- [ ] Checked `innodb_online_alter_log_max_size` and concurrent DML load.
- [ ] Tested on a clone matching production size, indexes, version, and load.
- [ ] Verified all replicas, versions, and compatible schemas.
- [ ] Defined abort thresholds for replication lag, disk space, I/O, latency, and MDL wait time.
- [ ] Prepared DDL failure handling and appropriate forward-fix/recovery plans.
- [ ] Verified schema, indexes, data, application, and GTIDs post-change.
- [ ] Recorded actual runtime, peak lag, peak disk usage, and test outcomes.

Schema evolution is an operational change on live data. `INSTANT` dramatically reduces cost when supported; `INPLACE` can still rebuild and consume heavy resources; `COPY` generally needs more space and time. In replicated environments, account for applier DDL execution time on every replica. Assessing algorithms, metadata locks, redo/undo, disk space, and replication lag thresholds before maintenance prevents turning a schema change into a performance incident or service outage.
