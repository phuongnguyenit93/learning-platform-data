# Disk Full, Table Is Full, and Exhausted Temporary Space

MySQL can stop accepting writes, fail to create temporary tables, or fail during `ALTER TABLE`, `CREATE INDEX`, `ORDER BY`, or `GROUP BY` when storage runs out. Common messages include `No space left on device`, `Disk full`, `The table is full`, or temporary file creation errors. These failures can originate in the filesystem holding the data directory, InnoDB tablespaces, binary logs, relay logs, `tmpdir`, storage engine size limits, or OS quotas.

Never treat every `Table is full` error by deleting files inside the data directory. First determine **which filesystem is full**, **what kind of file MySQL is writing**, and **which limit was reached**. Then free or expand the right storage area, preserve recovery files, and verify the database can write again.

## 1. Distinguishing Different Kinds of Space Exhaustion

A MySQL server uses several storage areas with distinct lifecycles and management rules:

| Storage Area | Contents | Symptoms When Exhausted |
|---|---|---|
| Data directory (`datadir`) | Table files, tablespaces, system tables, metadata, and InnoDB data | `INSERT`/`UPDATE`/DDL fails; server may error while writing data or starting up. |
| InnoDB system tablespace | Files configured by `innodb_data_file_path`, usually containing `ibdata1` | Cannot allocate new pages if hitting an autoextend max limit or full filesystem. |
| File-per-table tablespace | `.ibd` files for InnoDB tables when `innodb_file_per_table` is enabled | Specific table cannot grow if filesystem or quota runs out of space. |
| InnoDB temporary tablespace | Shared temporary tablespace and session temporary tablespaces | Queries needing InnoDB temp tables or temp operations fail. |
| `tmpdir` | Temporary files for certain sorts, merges, temp operations, and utilities | Queries/DDL fail creating temporary files even while the data volume still has space. |
| Binary log | Transaction history for replication and PITR | Transaction commits may fail if logs cannot grow; replicas/PITR are also impacted. |
| Relay log | Events received from source on a replica | Receiver cannot write relay logs and replication stops pulling data. |
| Backup/archive | Dumps, physical backups, log archives | Backup jobs fail or fill a shared volume. |
| Filesystem inodes/quotas | File metadata or per-user/project disk limits | Free bytes remain yet new files cannot be created, or the `mysql` user hits quota. |

`ERROR 1114: The table is full` does not necessarily mean the entire disk is full. It can stem from engine/table size limits, tablespace limits, quotas, or temporary areas. Conversely, a full filesystem can surface under other codes such as `1021`, `1030`, or OS error `errno 28`.

## 2. Recognizing Error Codes and Symptoms

| Message / Code | Common Meaning | Investigation Path |
|---|---|---|
| `No space left on device` / `errno: 28` | OS cannot allocate additional blocks or inodes. | `df -h`, `df -i`, quotas, mounts, and target write directories. |
| `1021: Disk full ...` | MySQL cannot write a data file or temporary file. | Path named in error, filesystem, and write permissions. |
| `1114: The table is full` | Storage engine or tablespace cannot accept more data. | Engine, table limits, tablespaces, and filesystem. |
| `1030: Got error ... from storage engine` | Storage engine error; sub-code depends on underlying cause. | MySQL error log, InnoDB status, and OS error. |
| Error creating `#sql...` or temp file | DDL/query cannot create a temporary file/table. | `tmpdir`, temporary tablespaces, sorts, and temp space. |
| Replica I/O error writing relay log | Replica cannot persist events received from source. | Relay log path, disk/inode/quota, and source connectivity. |
| Backup job out of space | Backup destination or staging volume is full. | Backup target, retention, active file being written, and archive usage. |

Record the full error message, timestamp, query/DDL, schema/table, connection ID, and file paths if reported. Cross-reference with the MySQL error log and OS logs. An error during `ALTER TABLE` often requires more temporary space than the net size increase of the table, because MySQL may build an intermediate copy or temporary indexes.

## 3. Identifying Which Filesystem Is Full

### Linux

Check space by mount:

```bash
df -hT
df -i
```

- `df -hT` displays block capacity, used space, free space, filesystem type, and mount point.
- `df -i` displays used/free inodes. A filesystem can run out of inodes while free bytes still remain.

Inspect paths used by MySQL:

```bash
sudo du -xhd1 /var/lib/mysql | sort -h
sudo du -xhd1 /var/tmp | sort -h
sudo du -xhd1 /tmp | sort -h
```

Substitute paths matching your actual environment. `-x` stays within a single filesystem, avoiding double-counting other mounts. Use directory-level `du` first to spot abnormal growth; avoid running deep recursive scans repeatedly on busy production volumes if they add heavy I/O.

Check for deleted files still held open by processes:

```bash
sudo lsof +L1
```

A log file unlinked from a directory while a process still holds an open file descriptor continues consuming blocks until that descriptor closes. Use proper service log rotation/reopen mechanisms. Never kill `mysqld` just to release a file descriptor without assessing impact and recovery plans.

If your organization uses quotas, check quotas for the `mysql` user, project quotas, or filesystem quotas. On cloud block volumes, also check volume size, IOPS/throughput limits, and resize status.

### Windows

Check volumes and free space:

```powershell
Get-Volume | Select-Object DriveLetter, FileSystemLabel, FileSystem, Size, SizeRemaining
Get-PSDrive -PSProvider FileSystem
```

Locate `datadir`, `tmpdir`, and log paths in the MySQL configuration file. Inspect the volume hosting each path, quotas, and permissions of the MySQL service account. If MySQL runs as a Windows service, that service account may have different permissions than the admin account running PowerShell.

### Containers and Kubernetes

In Docker, distinguish the container writable layer, named volumes, and bind mounts. Inspect actual mounts and host disk usage. `docker system df` helps inventory images/containers/volumes; never run `docker system prune --volumes` or delete volumes by guesswork, as that can destroy database data.

In Kubernetes, inspect `PersistentVolume`/`PersistentVolumeClaim`, node ephemeral storage, `emptyDir`, container `ephemeral-storage` limits, and `DiskPressure` events. `tmpdir` inside the container filesystem or `emptyDir` can fill up even while the PVC holding `datadir` still has plenty of space. Inspect Pod events and mount paths before modifying storage.

## 4. Inventorying MySQL Storage Paths

If an administrative connection is still possible, check key variables:

```sql
SHOW VARIABLES LIKE 'datadir';
SHOW VARIABLES LIKE 'tmpdir';
SHOW VARIABLES LIKE 'socket';
SHOW VARIABLES LIKE 'log_error';
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'log_bin_basename';
SHOW VARIABLES LIKE 'relay_log';
SHOW VARIABLES LIKE 'relay_log_basename';
SHOW VARIABLES LIKE 'innodb_data_home_dir';
SHOW VARIABLES LIKE 'innodb_data_file_path';
SHOW VARIABLES LIKE 'innodb_file_per_table';
SHOW VARIABLES LIKE 'innodb_temp_data_file_path';
SHOW VARIABLES LIKE 'innodb_temp_tablespaces_dir';
```

Not every variable exists on every MySQL version. If a query returns no rows or reports an unknown variable, check `SHOW VARIABLES LIKE 'pattern'` and version-specific documentation. `tmpdir` may contain multiple paths; separator syntax depends on the OS.

Check table sizes by schema:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH,
    DATA_FREE,
    ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024, 1) AS total_mb
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
  AND TABLE_SCHEMA NOT IN (
      'mysql', 'sys', 'performance_schema', 'information_schema'
  )
ORDER BY DATA_LENGTH + INDEX_LENGTH DESC
LIMIT 30;
```

For InnoDB, `TABLE_ROWS` is an estimate and `DATA_FREE` is not an exact measure of immediately reclaimable disk space. Use these figures to locate large tables, then cross-check the actual filesystem and tablespaces. Never sum `DATA_FREE` across all tables and assume that space can be freed immediately.

Inspect binary logs:

```sql
SHOW BINARY LOGS;
SHOW BINARY LOG STATUS;
```

On older versions, `SHOW MASTER STATUS` may be the corresponding command. Verify log sizes, retention, current replica positions, and PITR requirements before purging old logs.

## 5. Checking InnoDB Tablespace Limits

### System Tablespace

`innodb_data_file_path` defines system tablespace files, typically formatted like:

```text
ibdata1:12M:autoextend
```

If the configuration includes a `max` limit, such as `autoextend:max:...`, the system tablespace can hit that cap even when the filesystem still has free space. Check the actual configuration and version rather than assuming from the filename `ibdata1`.

### File-per-Table

When `innodb_file_per_table=ON`, InnoDB tables normally store their own tablespace in `.ibd` files. Files grow with data and indexes and require space on the filesystem hosting the data directory or tablespace path depending on setup. Deleting rows does not necessarily shrink `.ibd` files immediately; freed space may simply be reused internally within the tablespace.

### Temporary Tablespace

InnoDB uses temporary tablespaces for certain temporary operations. `innodb_temp_data_file_path` controls the shared temporary tablespace on versions supporting this variable. If a maximum size limit is configured, operations needing more temporary space fail when hitting the cap. Temporary tablespaces have their own lifecycle; never manually delete their files while the server is running.

Inspect InnoDB status:

```sql
SHOW ENGINE INNODB STATUS\G
```

Read sections covering transactions, history list length, file I/O, pending I/O, and recent errors. If authorized, check tablespace metadata in `INFORMATION_SCHEMA.FILES` and version-appropriate InnoDB/Performance Schema tables.

## 6. Temporary Space Exhaustion During Queries or DDL

MySQL may require temporary space for:

- `ORDER BY`, `GROUP BY`, `DISTINCT`, and certain sort/merge operations.
- Derived tables, CTEs, window functions, or queries materializing intermediate results.
- Joins lacking appropriate indexes or processing large intermediate result sets.
- `ALTER TABLE`, creating/rebuilding indexes, altering column types, or certain online DDLs.
- Internal temporary tables exceeding in-memory storage thresholds.
- Application-created temporary tables kept open long in a session.

Check related variables:

```sql
SHOW VARIABLES LIKE 'tmp_table_size';
SHOW VARIABLES LIKE 'max_heap_table_size';
SHOW VARIABLES LIKE 'temptable_max_ram';
SHOW VARIABLES LIKE 'temptable_max_mmap';
SHOW VARIABLES LIKE 'temptable_use_mmap';
SHOW VARIABLES LIKE 'tmpdir';
```

`temptable_*` variables and internal temporary table behavior depend on the MySQL version. Several variables have changed or been deprecated across 8.0 releases; only tune variables supported by your current version. `tmp_table_size` and `max_heap_table_size` behave differently depending on internal temporary table engine and temp table type. Raising memory limits increases RAM consumption across concurrent connections and is not a default fix when temporary disk space fills up.

Monitor temporary counters:

```sql
SHOW GLOBAL STATUS LIKE 'Created_tmp%';
```

Counters like `Created_tmp_tables` and `Created_tmp_disk_tables` help track internal temporary table trends. Alone, they do not pinpoint which query filled the disk and may not reflect all temporary files identically across versions. Combine them with the slow query log, Performance Schema statement history, processlist, and error timestamps.

To find queries consuming temporary space:

1. Identify queries/DDLs running when disk usage spiked.
2. Read `EXPLAIN` and check sorts, temporary tables, join order, indexes, and estimated rows.
3. Check whether queries materialize massive datasets or select unnecessary columns.
4. Test adding proper indexes or rewriting queries in staging with representative data.
5. If a query is legitimate and genuinely needs large temp space, provision a sufficiently large temporary filesystem and monitor growth.

Do not conclude every `Using temporary` or `Using filesort` is a bug. They are execution indicators; measure actual disk usage, duration, and operational impact.

## 7. Why `ALTER TABLE` Can Need More Space Than Expected

A schema change can create intermediate tables or indexes, copy new data, keep the old copy until completion, and create temporary sort files on the filesystem. Thus, adding one column or index can require more free space than the final net size growth.

Before running large DDL:

- Estimate table size, index size, and rows to be rebuilt.
- Identify available DDL algorithms (`INSTANT`, `INPLACE`, or `COPY`) for your exact version and change type.
- Identify which filesystems host `tmpdir`, the data directory, and tablespaces.
- Budget space for temporary copies, sort files, redo/undo, and generated binary logs.
- Check replica lag, metadata lock duration, and maintenance windows.
- Test on a data copy of representative size.

Do not force `ALGORITHM=INPLACE` or `LOCK=NONE` if the operation does not support them. Use `EXPLAIN ALTER TABLE` when supported by your MySQL version to inspect the DDL plan; otherwise, test in staging and consult version-specific docs. `OPTIMIZE TABLE` can also rebuild the table and require substantial extra disk space; never run it as an emergency disk cleanup step.

## 8. Checking Binary Logs and Relay Logs Consuming Disk

Binary logs can grow rapidly under heavy write workloads, long retention, or replication/PITR log requirements. Check:

```sql
SHOW BINARY LOGS;
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW VARIABLES LIKE 'max_binlog_size';
SHOW REPLICA STATUS\G
```

If multiple replicas or channels exist, check every channel and confirm replicas have received and applied up to safe positions. Check backup/PITR policies to determine which logs must be retained.

Once you confirm a log range is no longer needed for replicas, recovery, or audits, use MySQL commands to purge per policy:

```sql
PURGE BINARY LOGS TO 'binlog.000125';
```

This deletes binary logs older than the specified file, keeping the target file itself. The filename is an example only; obtain the real list from `SHOW BINARY LOGS` and verify replicas/backups before running. Never purge files still required by a replica or PITR window.

Never use `rm`/File Explorer to delete binary logs inside the data directory. Deleting files directly desynchronizes MySQL's log index and metadata. Relay logs are likewise managed by the replica; never delete them manually while the server runs. If relay log recovery is needed, follow proper replication recovery procedures.

Set intentional retention via `binlog_expire_logs_seconds` aligned with backup, replication, audit, and incident-response needs. Never shorten retention while investigating a lagging replica or unverified backups.

## 9. Identifying Sessions or Operations Growing Disk Usage

While the server is still reachable, inspect active sessions and statements:

```sql
SHOW FULL PROCESSLIST;
```

Look for long-running queries, states such as `Creating sort index`, `Copying to tmp table`, `altering table`, `Creating index`, or sessions holding temporary tables. State names can vary by version and do not by themselves prove a session is the sole cause.

If Performance Schema is enabled, check running statements and recent history via `events_statements_current`/`events_statements_history_long`, joined with `performance_schema.threads` for connection IDs. Available columns and data depend on consumer/instrumentation settings.

Terminate a query only after confirming its owner, impact, and application recovery behavior. `KILL QUERY` stops the current statement; `KILL CONNECTION` closes the session. For InnoDB DML, rollback can take time and generate undo/log I/O; do not expect disk space to drop instantaneously. For DDL, stop/cleanup behavior depends on the DDL type and execution phase.

If a temporary query filled `tmpdir`, canceling the query may free temporary files once MySQL cleans them up. Verify the filesystem after cleanup completes; never manually delete open files.

## 10. Runbook When Disk Is Nearly Full or Full

### Step 1: Stop Growth Safely

Identify which application, batch, ETL, backup, or DDL is generating abnormal write or temporary load. Pause non-essential jobs or halt deployments creating large files if permitted. Avoid reflexively restarting MySQL: the server may require additional disk space for crash recovery or startup.

### Step 2: Identify the Filesystem and File Types

Run `df -hT`, `df -i`, and check mounts for `datadir`, `tmpdir`, binary logs, and backups. Use `du` to find directories growing abnormally. Determine whether blocks, inodes, or quotas are exhausted.

### Step 3: Prefer Expanding Storage or the Right Mount

If the filesystem holding `datadir` is nearly full, expanding the volume/filesystem per infrastructure runbooks is usually safer than deleting data files. Confirm the OS sees the added space via `df`/`Get-Volume`. In containers/Kubernetes, resize the PVC or address ephemeral storage per platform procedures.

### Step 4: Free Unneeded Data with Owner Coordination

- Prune old backups on the backup target only after confirming valid newer backups exist and retention permits.
- Clean application logs via log rotation or log management tools.
- Move obsolete export/staging files off the MySQL volume.
- Purge binary logs via SQL after confirming replicas, PITR, and audits no longer need them.
- Stop runaway temporary queries/sessions only after identifying owners and stopping safely.

Never manually delete `.ibd` files, `ibdata*`, redo logs, undo tablespaces, `ibtmp1`, binary logs, relay logs, or open files in the data directory. Never run `docker system prune --volumes` on a host storing database volumes.

### Step 5: Verify MySQL Can Write Again

Confirm the filesystem has headroom, the error log shows no write errors, replicas/receivers are running, and a test write on a test schema or safe transaction succeeds. Monitor space across several intervals to ensure usage does not spike right back up.

### Step 6: Find Root Cause and Prevent Recurrence

Identify growth rates, offending jobs/queries, misconfigured retention, abnormal indexes/DDL, tablespace caps, or under-sized storage. Configure alerts on both percentage and absolute free GB, inode usage, growth rate, and estimated time-to-full based on trend.

## 11. Actions to Avoid When Disk Is Full

| Risky Action | Why It Is Dangerous | Proper Approach |
|---|---|---|
| Deleting `.ibd` files while MySQL runs | Destroys tablespaces and corrupts InnoDB metadata. | Use SQL/DDL or restore via supported procedures. |
| Manually deleting `ibdata1`, redo/undo, or `ibtmp1` | Can prevent server startup or destroy recovery capability. | Manage via tablespace config and version docs; touch offline only under verified runbooks. |
| Deleting binary logs via filesystem commands | Leaves MySQL's index/metadata pointing to missing files; can break replication/PITR. | Use `PURGE BINARY LOGS` after verifying dependencies. |
| Manually deleting relay logs | Desynchronizes relay log index and applier metadata. | Use replication recovery procedures. |
| Running `OPTIMIZE TABLE` for immediate space relief | Often copies the table and needs extra disk space before reclaiming any. | Estimate space, test in staging, and schedule maintenance. |
| Arbitrarily raising `tmp_table_size`/`max_heap_table_size` | Shifts pressure from disk to RAM; concurrent sessions can exhaust memory. | Analyze queries and tune within global memory limits. |
| Raising `max_connections` when disk is full | Fails to fix root cause and can increase temporary/log workload. | Address disk growth source and connection pressure separately. |
| Killing every running query | Can trigger long rollbacks, business disruption, and not free space right away. | Identify the growing session and assess before stopping. |
| Repeatedly restarting MySQL | Does not permanently free data; crash recovery can fail without free disk. | Read error log, expand storage, and restart per runbook when needed. |

## 12. Distinguishing Storage Engine Limits

### InnoDB

Check tablespaces, autoextend settings, filesystems, quotas, and temporary tablespaces. If the system tablespace has a `max` cap or temporary tablespaces have configured limits, simply expanding the filesystem may not lift internal limits. Plan configuration updates and expansion for the exact tablespace type.

### MyISAM

MyISAM enforces file size limits depending on filesystem and settings such as `MAX_ROWS`, `AVG_ROW_LENGTH`, `myisam_data_pointer_size`, or platform caps. `ERROR 1114` can trigger even with plenty of free disk if a table hits engine/configuration limits. Inspect `SHOW CREATE TABLE`, `SHOW TABLE STATUS`, and MySQL settings before changing anything.

### MEMORY

`MEMORY` tables reside in RAM and are bounded by `max_heap_table_size` (plus related version limits). Tables report full upon hitting that limit even when disk has abundant space. Check the table engine and limiting variables before raising config; raising the limit increases RAM risk.

### Partitions and Quotas

Partitioned tables can place files/tablespaces across multiple paths or filesystems depending on configuration. A specific partition or mount can fill up before others. User/project quotas can also fail operations even when `df -h` shows free space. Always identify the exact failing file and mount.

## 13. Capacity Planning and Alerting

Never wait until a filesystem hits 100% to alert. Budget capacity for:

- Current data and index sizes.
- Daily row growth and real disk growth rates.
- Binary log retention, replica lag, and PITR windows.
- Temporary backup staging and parallel backups.
- Peak temporary space during DDL, sorts, reports, and batches.
- Redo/undo logs, crash recovery, and operational headroom.
- OS logs, container overlays, and inodes.

Dashboards should track at minimum:

| Metric | What to Alert On |
|---|---|
| Filesystem used/free bytes | Usage percentage and absolute GB remaining. |
| Inodes used/free | Inode percentage and file creation rate. |
| Data directory growth | Daily/weekly growth rate and projected days to threshold. |
| Binary log size/count | Total size, retention, and replica/PITR dependencies. |
| Relay log space | Sustained growth or receiver write failures. |
| Temporary space | Peak usage, file lifetime, and triggering queries. |
| Tablespace usage | Growth of file-per-table, system tablespace, and temporary tablespaces. |
| Backup target | Remaining space, age of last backup, and job status. |

Configure tiered alerts—for instance, early warning below a defined operational headroom threshold and urgent alert when remaining space cannot cover projected workloads/DDL. Thresholds must reflect growth velocity and the lead time operations needs to expand storage, never one generic percentage across all systems.

## 14. Remediation and Recovery Verification Checklist

- [ ] Saved verbatim error message, timestamp, query/DDL, and relevant MySQL error log entries.
- [ ] Identified the exact filesystem/mount and distinguished block, inode, and quota exhaustion.
- [ ] Checked `datadir`, `tmpdir`, tablespaces, binary logs, relay logs, and backup targets.
- [ ] Identified the engine/table/tablespace or session triggering `Table is full`.
- [ ] Inspected processlist, temporary queries, DDLs, and file growth rates.
- [ ] Paused or deferred growth-causing workloads in a controlled way.
- [ ] Expanded the right volume or freed unneeded files with owner confirmation.
- [ ] Avoided manually deleting data files, redo/undo logs, binary logs, or relay logs.
- [ ] Verified MySQL writes succeed, error log is clean, and replication/backups are healthy.
- [ ] Monitored storage post-remediation and identified the root cause.
- [ ] Updated capacity forecasts, retention policies, or alerts to prevent recurrence.

When MySQL reports out of disk, the key is finding the exact storage area and limit reached. The filesystem may be full, inodes/quotas may be exhausted, tablespaces may have hit max caps, an engine may have hit its own limit, or a query/DDL may need large temporary space. Expanding the right mount, managing logs through MySQL mechanisms, handling queries deliberately, and leaving core data files untouched ensures safe recovery without breaking recoverability or replication.
