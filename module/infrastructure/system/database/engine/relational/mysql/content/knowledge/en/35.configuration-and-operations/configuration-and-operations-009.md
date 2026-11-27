# Redo, Undo, Binary Logs, Temporary Files, and Capacity Planning

A MySQL instance can run out of disk space even when table data sizes have barely grown. Beyond data and index files, InnoDB uses redo logs, undo tablespaces, and temporary tablespaces; the server writes binary logs for replication and point-in-time recovery; replicas store relay logs; and large queries, transactions, and DDL can generate temporary files. Each file group has a different growth pattern, retention period, and cleanup mechanism.

Capacity management must therefore look across the entire write lifecycle rather than only the directory holding tables. You need to know which files are allowed to grow, which must be retained by policy, which can be regenerated, which require backups before removal, and how much free space must be reserved for peak workloads or incident recovery.

## Objectives

After this lesson, you will be able to:

- Distinguish the roles and lifecycles of redo logs, undo logs, binary logs, and temporary files.
- Explain the factors driving growth in each storage area.
- Configure transaction durability and log retention aligned with RPO/RTO.
- Monitor undo history, redo capacity, binary logs, relay logs, and temporary storage.
- Estimate capacity from data growth, retention, and peak load.
- Set up alerts, safety thresholds, and runbooks for nearly full filesystems.
- Clean up logs and temporary files using MySQL-supported mechanisms without deleting server-managed files directly.

Examples assume MySQL 8.0 or later with InnoDB and binary logging potentially enabled. Some variables and file layouts change across versions; always check actual configuration before applying in production.

## 1. Map of Storage Areas

A MySQL server typically uses several file groups:

| Group | Contents | Growth Drivers | Primary Role |
|---|---|---|---|
| Data and indexes | Tablespaces, clustered/secondary indexes | INSERT, UPDATE, new data, new indexes | Long-term data storage |
| Redo log | Log records describing page changes | Transaction writes, checkpoint speed | Crash recovery and write-ahead logging |
| Undo tablespace | Undo records and rollback segments | UPDATE/DELETE, long transactions, old snapshots | Rollback and MVCC |
| Binary log | Server-level change events | Logged transactions, row image, retention | Replication and point-in-time recovery |
| Relay log | Source events received by a replica | Slow replica apply, lost connection to source | Replication event queue |
| Temporary storage | Internal temp tables, sorts, DDL, transaction cache | GROUP BY, sorts, materialization, DDL, large transactions | Intermediate result storage |
| Operational logs | Error, slow query, general/audit logs | Errors, slow queries, logging configuration | Diagnostics and auditing |
| Backups | Full/incremental backups, binlog archives | Backup schedule and retention period | Recovery from data loss/corruption |

Not all groups must reside on the same filesystem. In production deployments, data, redo, binlog, temporary files, and backups can be separated onto distinct volumes to isolate growth and I/O. Separating volumes improves risk management, though it does not replace overall capacity monitoring.

## 2. Redo Log: Capacity and Checkpointing

The redo log records information needed by InnoDB to replay changes when starting after a crash. It is part of write-ahead logging: redo must be written durably before the corresponding data pages are written to their canonical locations.

### How Does the Redo Log Grow and Get Reused?

The redo log is a circular log space. InnoDB writes new log entries while page cleaners flush dirty pages from the buffer pool to tablespaces. Only once sufficiently old pages have been flushed and the checkpoint advances can older redo regions be reused.

If the redo generation rate exceeds page-flushing capacity, the checkpoint can fall behind. More redo space becomes occupied, forcing the system to flush more aggressively or throttle transactions to avoid overwriting unsafe log regions. Thus, redo pressure can manifest as elevated write latency even when the filesystem still has plenty of free space.

### innodb_redo_log_capacity

Starting in MySQL 8.0.30, `innodb_redo_log_capacity` is the primary configuration variable controlling total redo log capacity. Older versions use `innodb_log_file_size` and `innodb_log_files_in_group`. MySQL manages redo files in the `#innodb_redo` directory in modern versions; never rename or delete these files manually.

Check configuration:

```sql
SHOW VARIABLES LIKE 'innodb_redo_log_capacity';
SHOW VARIABLES LIKE 'innodb_log_file_size';
SHOW VARIABLES LIKE 'innodb_log_files_in_group';
```

Older variables may be deprecated or absent in newer versions. Use the variables matching your running version.

Increasing redo capacity can help absorb write bursts and reduce short-term checkpoint pressure, though it does not increase the physical write speed of storage. Excessively large capacity can also prolong crash recovery time and consume extra fixed disk space. Size it according to redo generation rate, flush capacity, acceptable recovery time, and volume space.

### Transaction Durability and Log Flushing

Two settings are commonly evaluated together:

- `innodb_flush_log_at_trx_commit`: controls how InnoDB writes and flushes the redo log.
- `sync_binlog`: controls how often the binary log is synchronized to storage.

| `innodb_flush_log_at_trx_commit` | General Behavior | Risk on OS Crash or Power Loss |
|---|---|---|
| `1` | Writes and flushes redo log at each commit (possibly via group commit) | Highest protection for committed transactions per storage guarantees |
| `2` | Writes log at each commit, flushes to storage periodically, typically about once per second | May lose recent commits if the OS or host loses power |
| `0` | InnoDB writes and flushes log periodically, typically about once per second | May lose recent commits if mysqld, the OS, or the host crashes before the next write/flush |

For binary logs, `sync_binlog = 1` requests syncing the binlog after every commit group; values greater than 1 sync every N commit groups, while 0 leaves flushing to the OS. When strict protection is required for both InnoDB and the binlog, a commonly chosen configuration is `innodb_flush_log_at_trx_commit = 1` with `sync_binlog = 1`, provided the storage device honors flush/fsync calls properly.

Actual durability also depends on controllers, device caches, backup power, and the filesystem. Never relax flush settings merely to improve benchmarks without defining the business's acceptable RPO.

## 3. Undo Log: MVCC, Rollback, and History List

The undo log stores information needed to roll back changes and reconstruct older row versions for consistent reads. InnoDB stores undo records in rollback segments inside undo tablespaces or corresponding undo regions depending on configuration/version.

### Why Can Undo Grow for Extended Periods?

Undo does not grow solely with the number of active transactions. Transactions modifying many rows generate many undo records; old read views can force purge to retain old versions longer. A long-open transaction—even a read-only one under `REPEATABLE READ`—can hold an old snapshot and prevent purge from removing unneeded undo versions.

Common causes:

- Long transactions running UPDATE/DELETE across many rows.
- `idle in transaction` sessions that fail to commit/roll back.
- Consistent reads holding read views open for a long time.
- Purge threads unable to keep pace with undo generation.
- Heavy delete/update workloads producing large amounts of history to clean up.

When history list length climbs persistently, undo storage can expand, purge consumes resources, and queries must traverse more row versions. Do not merely enlarge undo tablespaces to mask a transaction holding a snapshot too long.

### Monitoring Undo and Purge

```sql
SHOW ENGINE INNODB STATUS;
```

In the TRANSACTIONS section, watch `History list length` and long-running transactions. Combine with `information_schema.innodb_trx` to identify offending transactions:

```sql
SELECT trx_id,
       trx_state,
       trx_started,
       trx_mysql_thread_id,
       trx_rows_modified,
       trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

`History list length` is an InnoDB-reported history list metric; it is not directly bytes on disk and should not be converted straight into undo size. Correlate its trend with undo tablespace size, transaction age, and how fast history drops after blockers finish.

### Undo Tablespaces and Truncation

MySQL 8.0 typically uses dedicated undo tablespaces. Check related variables:

```sql
SHOW VARIABLES LIKE 'innodb_undo%';
```

`innodb_undo_log_truncate` allows InnoDB to automatically truncate eligible undo tablespaces when their size exceeds `innodb_max_undo_log_size`. Truncation can only happen when the selected undo tablespace has no active rollback segments; long transactions can delay this process. Filenames, tablespace counts, and configurability depend on version.

Never delete undo files directly. Before altering settings, verify version, tablespace state, and operational guidance; resolve snapshot-holding transactions before expecting space reclamation.

## 4. Binary Log: Replication, PITR, and Retention

The binary log records server-level change events. Replicas read binlogs from the source to re-execute statements or apply row events; backup tools combine binlogs with full backups for point-in-time recovery (PITR).

### What Drives Binary Log Growth?

Binary log size depends on:

- Volume of write transactions.
- `binlog_format` (`ROW`, `STATEMENT`, or `MIXED`).
- `binlog_row_image` and the number of columns logged in row events.
- Transaction size, bulk updates, and batch imports.
- DDL, metadata events, and log rotation frequency.
- Retention period and how quickly replicas/backups consume logs.

With `ROW`, an UPDATE can log changed row images; a transaction updating many rows can produce a binlog far larger than the original SQL text. Therefore, never forecast capacity solely from statement counts or query text size.

### Checking the Binary Log

```sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW BINARY LOGS;
```

`SHOW BINARY LOGS` lists files and sizes. Sample periodically to calculate binlog generation per hour/day. If binary logging is disabled, binlog commands and binlog-based PITR have no data to use.

### Retention and Safe Purging

`binlog_expire_logs_seconds` configures automatic binlog expiration on MySQL versions supporting it; `binlog_expire_logs_auto_purge` controls automatic purging. Do not assume auto-purge protects every lagging replica or every off-server backup. Retention must exceed the time needed for replicas to catch up plus the point-in-time recovery/backup window; operations must verify proactively before logs expire.

You can purge old logs using MySQL commands:

```sql
PURGE BINARY LOGS BEFORE '2026-10-01 00:00:00';
```

Or purge up to a specific file (the specified file is preserved):

```sql
PURGE BINARY LOGS TO 'binlog.000125';
```

Before purging, confirm:

1. All replicas needing those files have read and applied past a safe position.
2. Backups and PITR workflows no longer require the binlog segments about to be removed.
3. Off-server binlog copies exist if policy requires long-term retention.
4. The remaining retention period still satisfies RPO and recovery windows.

Never delete binlog files with filesystem commands while MySQL manages them. Use `PURGE BINARY LOGS` or automatic expiration so MySQL updates both the index file and internal state. Never use log reset commands as a routine space-clearing step, as that can break replication and GTID state.

### Binlog Cache and Large Transactions

MySQL keeps per-transaction caches in memory governed by variables such as `binlog_cache_size` and `binlog_stmt_cache_size`. When a transaction exceeds cache memory, excess data can spill to temporary files. Counters `Binlog_cache_disk_use` and `Binlog_stmt_cache_disk_use` help detect this:

```sql
SHOW GLOBAL STATUS LIKE 'Binlog_cache%';
SHOW GLOBAL STATUS LIKE 'Binlog_stmt_cache%';
SHOW VARIABLES LIKE 'binlog_cache_size';
SHOW VARIABLES LIKE 'binlog_stmt_cache_size';
```

Oversized transactions can simultaneously inflate undo, redo, binlog cache files, and replica lag. Batching can reduce peak resource usage, provided atomicity and business rules are preserved.

## 5. Relay Logs on Replicas

A replica receives binary logs from its source and writes them to relay logs before the applier executes them. If the replica stops applying or falls behind the source's binlog generation rate, relay logs can grow rapidly and fill the filesystem.

Check replication status:

```sql
SHOW REPLICA STATUS\G
```

Pay attention to fields such as `Relay_Log_Space`, `Relay_Log_File`, `Relay_Source_Log_File`, receiver/applier states, and SQL thread errors. Field names may differ on older versions using `SHOW SLAVE STATUS` terminology.

`relay_log_space_limit` can cap total relay log size on supported configurations. When the limit is reached, the receiver may have to wait until the applier frees space. This is a backpressure mechanism, not a fix for why the replica is lagging.

Never delete relay logs directly. Resolve applier errors, I/O bottlenecks, long transactions, or network latency; then let replication manage relay log purging based on applied state.

## 6. Temporary Files and Temporary Tablespaces

MySQL creates several types of temporary files:

- Memory-mapped files used by TempTable when its RAM budget is reached.
- On-disk internal temporary tables managed by InnoDB.
- Sort/merge files and other temporary files in `tmpdir`.
- Temporary files during certain DDL or import/export operations.
- Transaction cache files when binlog cache exceeds memory.

### tmpdir

`tmpdir` is the directory MySQL uses for certain server-level temporary files. Check:

```sql
SHOW VARIABLES LIKE 'tmpdir';
```

On platforms supporting unlinking open files, TempTable may create an mmap file in `tmpdir`, open it, and unlink its name immediately; thus the file might not appear in directory listings even though disk space remains held by the open file descriptor. Inspect actual filesystem usage rather than looking only for filenames.

If `tmpdir` contains multiple paths, MySQL may select a suitable directory depending on platform/configuration. Every directory must have adequate space, write permissions, and meet operational requirements. Avoid placing `tmpdir` on filesystems prone to filling up with logs or unrelated files.

### InnoDB Temporary Tablespaces

InnoDB uses temporary tablespaces for on-disk internal temporary tables and related temporary objects. There is a global temporary tablespace and session temporary tablespaces depending on version. The global file is commonly known as `ibtmp1`; session temporary tablespaces are managed per connection or server lifecycle.

Temporary tablespaces can grow during heavy workloads. File size may not shrink immediately after a query finishes; reclamation depends on tablespace type and version. Some files are reused for subsequent queries; the global temporary tablespace is reinitialized on server restart per version rules. Never delete `ibtmp1` or session temporary files while `mysqld` is running.

### innodb_tmpdir

`innodb_tmpdir` controls the location of certain temporary files created by InnoDB during online ALTER TABLE, such as temporary sort files in some index rebuild operations. It does not replace `tmpdir` for all temporary file types. Check:

```sql
SHOW VARIABLES LIKE 'innodb_tmpdir';
SHOW VARIABLES LIKE 'tmpdir';
```

If separating a directory for DDL, ensure the target filesystem has sufficient space for the rebuild, `mysqld` access permissions, and adequate I/O capacity. Large DDLs also need space for the new table/indexes while old data still exists.

## 7. Capacity for DDL and Schema Changes

Some `ALTER TABLE` operations must build a new structure and populate indexes before replacing the old structure. Meanwhile, disk usage can surge substantially because old data, the new copy, indexes, sort files, and ongoing workload logs coexist simultaneously.

Before running a major DDL, estimate:

- Current table and index sizes.
- Expected size of the new structure, including added indexes.
- Temporary sort files and engine staging areas.
- Redo/undo/binlog generated throughout the DDL duration.
- Space on replicas and backups if the DDL is replicated or snapshotted.
- Free headroom so normal workloads can keep writing while DDL runs.

Do not use current file size as the entire estimate. An index rebuild may require extra space roughly equal to the involved data/indexes depending on algorithm and change type. Test on a similarly sized copy; check whether suitable `ALGORITHM` and `LOCK` clauses can be used in `ALTER TABLE` for your version, engine, and change type. `EXPLAIN` on a SELECT query does not directly predict DDL disk requirements.

## 8. Overall Capacity Planning

### Forecasting Formula

For each storage group, estimate:

```text
Required storage capacity
  = baseline capacity
  + average daily growth rate × retention days
  + peak workload surge
  + headroom for maintenance and recovery
```

For example, if binlogs average 18 GB/day and must be retained for 10 days so replicas/backups can catch up, the baseline is about 180 GB. Add margin for peak days, large transactions, and incident handling time. This is an estimate; use measurements over a sufficiently long window and include peaks rather than relying on a quiet day.

### Planning Table by Group

| Group | How to Forecast | Metrics to Measure | Policy |
|---|---|---|---|
| Data/indexes | Daily row growth × retention window | Tablespace size, index size, growth rate | Archival/partitioning/retention |
| Redo | `innodb_redo_log_capacity` and redo generation rate | Redo capacity, checkpoint age, write throughput | Reserve sufficient capacity and recovery headroom |
| Undo | Peak update/delete and long transaction/snapshot duration | Undo tablespaces, history list length, transaction age | Transaction limits, purge, and truncation |
| Binary log | GB binlog/day × retention days | `SHOW BINARY LOGS`, binlog generation rate | Retention, backup archival, replica lag |
| Relay log | Log receive rate × replica lag duration | `Relay_Log_Space`, applier lag | Fix lag root cause, limits, and alerts |
| Temporary | Peak concurrent temp workload and DDL | `tmpdir`, temp tablespaces, `Created_tmp` counters, mmap | Separate volume, tune queries, resource limits |
| Backup | Full + incremental + binlog archive sizes | Backup catalog, compression ratio, retention | Store off primary data volumes |

### Headroom

Never operate filesystems near 100%. Leave free space for write bursts, DDL, crash recovery, log rotation, and emergency actions. A 20–30% free-space threshold can serve as a starting point for some systems, though it is not a MySQL rule; highly variable workloads or major DDLs may need more.

If file types reside on separate volumes, plan each volume individually. Total free space across the whole server will not help if the dedicated binlog or `tmpdir` volume fills up.

## 9. Monitoring and Alerting

### Quick Variable and Status Checks

```sql
SHOW VARIABLES LIKE 'innodb_redo_log_capacity';
SHOW VARIABLES LIKE 'innodb_undo%';
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW VARIABLES LIKE 'binlog_expire_logs_auto_purge';
SHOW VARIABLES LIKE 'tmpdir';
SHOW VARIABLES LIKE 'innodb_tmpdir';

SHOW GLOBAL STATUS LIKE 'Created_tmp%';
SHOW GLOBAL STATUS LIKE 'Binlog_cache%';
SHOW GLOBAL STATUS LIKE 'Binlog_stmt_cache%';
SHOW BINARY LOGS;
SHOW ENGINE INNODB STATUS;
```

### Monitoring File I/O via Performance Schema

If file instruments are enabled, you can inspect files with heavy I/O:

```sql
SELECT FILE_NAME,
       EVENT_NAME,
       COUNT_READ,
       COUNT_WRITE,
       SUM_NUMBER_OF_BYTES_READ,
       SUM_NUMBER_OF_BYTES_WRITE
FROM performance_schema.file_summary_by_instance
ORDER BY SUM_NUMBER_OF_BYTES_WRITE DESC
LIMIT 30;
```

This table provides per-file I/O statistics, not current filesystem space usage. Use it to find files with heavy read/write activity; use OS tools or storage monitoring systems to measure bytes used, free space, and file growth rates.

### Essential Alert Set

- Filesystem below operational thresholds, such as 25%, 15%, and 10% free; base exact thresholds on growth rate and response time.
- Hourly/daily binlog generation exceeding baseline or expected retention.
- Rising replica lag and continuously growing `Relay_Log_Space`.
- Persistently growing `History list length` and long-running open transactions.
- Abnormal growth in temp tablespaces or `tmpdir`.
- Redo checkpoint pressure or flush rate falling behind workload.
- Running DDL/backups when the volume lacks sufficient headroom.

## 10. Runbook When Disk Space Nears Full

When a filesystem-nearly-full alert triggers, prioritize identifying file types and growth rates before deleting anything:

1. Identify the full volume and space-consuming directories using OS tools.
2. Map files to data, redo, undo, binlog, relay log, temporary tablespace, `tmpdir`, operational logs, or backups.
3. Verify MySQL is still operational and check whether any transaction, DDL, or replication stream is generating files rapidly.
4. If binlogs grew, verify replicas and backups/PITR before purging with SQL.
5. If undo grew, find long transactions and old snapshots; clear the cause holding history, then monitor purge/truncation.
6. If temporary storage grew, identify queries/DDLs creating temp data and consider stopping or throttling workloads per operational procedure.
7. If relay logs grew, inspect applier errors, replication lag, and apply speed; never delete relay logs manually.
8. If data/redo volumes lack space, expand storage or throttle writes per emergency plan; never delete InnoDB files to free space.
9. Once stabilized, update growth forecasts, retention, alerts, and runbooks.

**Never directly delete** redo, undo, binlog, relay log, `ibtmp1`, or tablespace files while `mysqld` manages them. Accidental deletion can prevent the server from starting, break crash recovery, corrupt replication, or render data unrecoverable.

## 11. Aligning Retention and Backup Design

Binlog retention must align with backups. For instance, if full backups run weekly and 14-day PITR is required, ensure complete binlogs exist from the relevant backup point to the target recovery time. Deleting binlogs before the corresponding backup and log chain are safely archived can destroy PITR capability.

Similarly, relay logs must remain intact enough for a replica to resume after an interruption. If a replica stops for several days, the source may expire needed binlogs before the replica catches up; in that case, resync from a fresh backup or snapshot is required.

Backups should be stored on storage independent from primary data volumes and restore-tested regularly. A backup file sitting on the same volume as data offers no protection if that volume or device is lost.

## 12. Capacity Design Checklist

Before putting MySQL into production, verify:

- [ ] Data, redo, undo, binlogs, relay logs, temporary files, and backups are classified.
- [ ] Filesystems holding each file group and daily growth rates are known.
- [ ] Redo capacity suits write bursts and crash recovery time targets.
- [ ] `innodb_flush_log_at_trx_commit` and `sync_binlog` meet durability/RPO requirements.
- [ ] Transactions have time bounds; history list length and purge are monitored.
- [ ] Binlog retention suffices for replicas and PITR; an approved purge workflow exists.
- [ ] Relay logs and replication lag are alerted on.
- [ ] `tmpdir`, InnoDB temporary tablespaces, and `innodb_tmpdir` have sufficient capacity.
- [ ] Major DDLs include temporary space estimates and maintenance windows.
- [ ] Backups reside off primary data volumes and have been restore-tested.
- [ ] Each filesystem has headroom and alert thresholds calibrated to actual growth rates.
- [ ] Disk-full runbooks use only MySQL-supported mechanisms and never delete server-managed files.

## 13. Hands-On Exercises

On a test instance or staging environment:

1. Record `innodb_redo_log_capacity`, `innodb_flush_log_at_trx_commit`, and `sync_binlog`, and describe how each setting impacts durability.
2. Run a large UPDATE workload; monitor `SHOW ENGINE INNODB STATUS`, history list length, and transaction age.
3. Open a long-lived read transaction under `REPEATABLE READ`, run UPDATE/DELETE from another session, and observe undo history/purge. End the transaction and watch history drop.
4. Enable binary logging in a test environment, generate a write workload, and use `SHOW BINARY LOGS` to calculate binlog GB/day.
5. Inspect `binlog_expire_logs_seconds`, simulate replica lag, and determine when it is safe to purge old logs.
6. Run a large write transaction to observe `Binlog_cache_disk_use` and temporary files if cache memory is exceeded.
7. Run a large GROUP BY/sort query, capture `Created_tmp%` deltas, and monitor the filesystem containing `tmpdir` alongside the InnoDB temporary tablespace.
8. Build a 30-day forecast table for data, redo, undo, binlog, relay log, temporary storage, and backups; compute separate headroom for each volume.
9. Write a runbook for when the binlog volume hits 90% and another for when `tmpdir` nears full. Specify which data may be purged and which must be preserved.

## Key Takeaways

- Redo serves crash recovery; undo serves rollback and MVCC; binary logs serve replication/PITR; relay logs queue events on replicas.
- Long transactions and old read views can pin undo, slowing purge and growing tablespaces.
- Binlog retention must match replica needs and backup/PITR chains; purge via SQL, never delete files directly.
- Temporary files can live in `tmpdir`, memory-mapped storage, or InnoDB temporary tablespaces; counters do not reflect every spill path.
- Major DDLs require headroom for old data, new structures, indexes, temporary sorts, and generated logs.
- Forecast from growth rate and retention plus peak workload and headroom; plan each filesystem separately.
- When disk nears full, identify the exact file type and follow the runbook; never delete InnoDB/binlog/relay log files managed by MySQL.
