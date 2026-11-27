# `innodb_flush_log_at_trx_commit`, `sync_binlog`, and Durability Trade-offs

MySQL uses multiple types of logs to protect data and support recovery. InnoDB writes the **redo log** to recover changes to data pages after an outage; the binary log records data change events for replication and point-in-time recovery (PITR). The two logs serve different roles and have separate synchronization mechanisms to storage devices.

Two configuration variables that directly govern when logs are synchronized are `innodb_flush_log_at_trx_commit` and `sync_binlog`. Choosing lower values can reduce flush or sync operations and raise write throughput, but it increases the risk of losing recent transactions when the system crashes. For workloads requiring strong durability, the commonly recommended setting is `1` for both variables.

## 1. Why Does MySQL Need Both the Redo Log and the Binary Log?

### InnoDB Redo Log

The redo log records the information needed to replay changes to data pages when InnoDB recovers after a crash. When a transaction modifies a row, the data page may remain in the buffer pool and be written to the data file later. Committing does not require every data page to be written immediately; instead, InnoDB ensures the corresponding redo is written and flushed according to the durability policy.

The redo log supports InnoDB crash recovery. It is not a full history log for replicas to apply transactions, nor does it replace backups.

### Binary Log

The binary log (binlog) records data change events at the server level. It is primarily used for:

- Replication: replicas read events from the source and apply them.
- Point-in-time recovery: restoring from a backup and replaying binlog events up to the required timestamp.
- Auditing and data integration: tools can read the binlog to capture changes.

The binlog does not replace the redo log. InnoDB needs redo to recover storage engine state; replication and PITR need the binlog to know which transactions were committed.

### The Two Logs Have Separate Synchronization Boundaries

A transaction can be written to the redo log before the binlog is durably synced, or vice versa depending on configuration and crash timing. MySQL coordinates InnoDB and the binlog in an internal two-phase commit process to maintain consistent state on recovery. Still, to achieve the desired durability for both InnoDB data and binlog history, appropriate flush/sync policies must be configured for both.

## 2. What Does `innodb_flush_log_at_trx_commit` Control?

This variable controls how InnoDB writes and flushes the redo log at commit time. Three main values:

| Value | Primary Behavior | Crash Risk |
|---:|---|---|
| `0` | InnoDB writes the log buffer to the redo log file and flushes roughly once per second; no write/flush required at each commit | Recent transactions may be lost if `mysqld`, the OS, or the host crashes before the next flush |
| `1` | Writes redo log and requests a flush to durable storage on every commit | Highest protection under InnoDB's flush mechanism; still depends on the OS, filesystem, and storage device honoring flushes |
| `2` | Writes to the redo log file on every commit, but flushes to storage roughly once per second | If only the `mysqld` process dies while the OS stays up, data in the OS cache typically survives; if the OS or host loses power, unflushed writes may be lost |

Check the current value:

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb_flush_log_at_trx_commit';
```

Set at runtime:

```sql
SET GLOBAL innodb_flush_log_at_trx_commit = 1;
```

To persist across restarts, you can use `SET PERSIST` if supported by the variable and version:

```sql
SET PERSIST innodb_flush_log_at_trx_commit = 1;
```

Or declare it in the option file under the server group:

```ini
[mysqld]
innodb_flush_log_at_trx_commit = 1
```

`1` is usually the default and the right choice when losing committed transactions is unacceptable. Always verify the effective value on your instance rather than assuming every environment keeps the default.

### Flush Interval When Using `0` or `2`

Roughly one second is the default background interval, not a guarantee that at most exactly one second of data can ever be lost under all conditions. Actual flush timing depends on scheduling, system load, `innodb_flush_log_at_timeout`, the OS, and the storage device. When a crash happens just before a flush, data loss can exceed a simple wall-clock expectation.

Check the related variable:

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb_flush_log_at_timeout';
```

Adjusting the timeout does not turn `0` or `2` into a mode that guarantees durable flushing on every commit. If the requirement is to acknowledge commits only after redo has been flushed, use `1`.

## 3. What Does `sync_binlog` Control?

`sync_binlog` specifies how often MySQL synchronizes the binary log to the storage device:

| Value | Primary Behavior | Crash Risk |
|---:|---|---|
| `0` | MySQL does not actively request binlog sync per commit group; the OS decides when to flush | Recent binlog events may not yet be durable if the OS or host crashes |
| `1` | Requests a binlog sync after every commit group | Best binlog protection under MySQL's sync mechanism; still depends on the device honoring flushes |
| `N` greater than `1` | Requests a sync after every `N` binlog commit groups | On crash, recent unsynced commit groups may be lost |

Check the value:

```sql
SHOW GLOBAL VARIABLES LIKE 'sync_binlog';
```

Set at runtime:

```sql
SET GLOBAL sync_binlog = 1;
```

Persist across restarts:

```sql
SET PERSIST sync_binlog = 1;
```

Or in the option file:

```ini
[mysqld]
sync_binlog = 1
```

With `sync_binlog = 1`, MySQL requests synchronization after each commit group, not necessarily invoking a separate sync for every individual transaction. Group commit lets multiple transactions share a flush/sync in certain phases, reducing I/O cost while preserving durable group commit boundaries.

## 4. Group Commit and Performance Impact

Flushing logs is an expensive I/O operation. If every transaction waited on its own separate flush, storage latency would cap transaction commits per second.

MySQL supports group commit: multiple transactions join commit groups to share log writing and synchronization work. This increases throughput without forcing you to give up durability requirements. Therefore, `innodb_flush_log_at_trx_commit = 1` and `sync_binlog = 1` do not mean the system always performs two completely independent syncs per individual transaction.

When write load rises, measure all of the following:

- Transaction commits per second.
- Commit latency, especially p95 and p99.
- Wait time for log file sync and related wait events in Performance Schema.
- IOPS, throughput, and latency of devices hosting the redo log and binlog.
- Transaction sizes and how well commits can be grouped.

Do not change these two variables merely because commit latency looks high. First verify whether the latency comes from storage hardware, contention, overly large transactions, filesystem configuration, or other waits.

## 5. Combining Both Variables Based on Durability Goals

The two variables govern two different logs. You can use the following table as an evaluation framework:

| `innodb_flush_log_at_trx_commit` | `sync_binlog` | Operational Meaning |
|---:|---:|---|
| `1` | `1` | Preferred choice when high durability is required for both redo and binlog |
| `1` | `0` | Redo is flushed at commit, but the binlog may not yet be durably synced on OS/host failure |
| `0` or `2` | `1` | Binlog is synced per commit group, but redo may not be durably flushed on every commit |
| `0` or `2` | `0` or `N > 1` | Reduces flush/sync frequency, potentially increasing throughput at the cost of a larger risk window for losing recent transactions and binlog events |

If the system uses the binary log for replication or PITR, you cannot care only about whether rows survive in InnoDB. The binlog must also consistently reflect committed transactions. Mismatched settings for the two variables can introduce different risks for crash recovery, replication, and binlog replayability.

For critical business workloads, a sensible baseline is:

```ini
[mysqld]
innodb_flush_log_at_trx_commit = 1
sync_binlog = 1
```

Consider relaxing these only when the system owner has clearly defined the maximum acceptable data loss, the failure modes to tolerate, and the recovery procedure. Document this decision as an RPO (Recovery Point Objective) requirement, not merely a performance tweak.

## 6. Distinguishing Failure Types

Not every crash carries the same scope of data loss:

| Failure | Impact on Buffers/Caches | Considerations |
|---|---|---|
| Only the `mysqld` process terminates abnormally | OS and hardware keep running; data already written out of process memory may remain in OS cache | With `innodb_flush_log_at_trx_commit=2`, redo already written to the OS typically remains recoverable; `0` may lose the unwritten log buffer |
| OS kernel crash or host power loss | OS page cache and volatile caches can be lost | Requires redo and binlog to have been truly flushed to durable media |
| Storage device or controller reports flush success without guaranteeing persistence | Data may be lost or corrupted even though MySQL requested sync | Check write caches, power-loss protection, firmware, and vendor guarantees |
| Device failure or total host loss | Cannot rely on a single log copy on the lost device | Requires backups, off-host copies, and tested restore/replication procedures |

`innodb_flush_log_at_trx_commit=1` and `sync_binlog=1` protect commits against crashes under MySQL's flush mechanisms, but they do not replace backups and do not protect against hardware destruction, software bugs, accidental deletes, or total infrastructure loss.

## 7. Why Storage Hardware Matters So Much

MySQL asks the OS to sync log data to storage using appropriate flush/sync calls. Actual durability depends on multiple layers:

1. Whether MySQL issues flush/sync calls as configured.
2. Whether the filesystem and kernel honor sync requests properly.
3. Whether the controller and drive report completion before data is truly durable.
4. Whether the write cache has battery/flash protection or loses data on power loss.
5. Whether the storage infrastructure has reliable power-loss protection and firmware.

If a device acknowledges flushes while holding data only in volatile cache, MySQL configuration cannot create durability that the hardware does not provide. For physical servers, inspect the RAID controller cache and battery protection. For cloud volumes, review the durability/flush guarantees of the storage service and volume type in use.

## 8. Measuring Performance Impact

Before making changes, record a baseline under the same workload:

```sql
SHOW GLOBAL STATUS LIKE 'Com_commit';
SHOW GLOBAL STATUS LIKE 'Innodb_os_log_fsyncs';
SHOW GLOBAL STATUS LIKE 'Innodb_log_waits';
SHOW GLOBAL VARIABLES LIKE 'innodb_flush_log_at_trx_commit';
SHOW GLOBAL VARIABLES LIKE 'sync_binlog';
```

Status counters are cumulative since server startup or reset. Capture two snapshots at two points and compute differences instead of reading a single value. Counter names and detail levels may vary by version.

You can inspect wait events in Performance Schema:

```sql
SELECT EVENT_NAME,
       COUNT_STAR,
       ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_wait_seconds,
       ROUND(AVG_TIMER_WAIT / 1000000000, 3) AS avg_wait_ms
FROM performance_schema.events_waits_summary_global_by_event_name
WHERE EVENT_NAME LIKE '%log%'
   OR EVENT_NAME LIKE '%file%'
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 30;
```

Exact event names depend on version and enabled instrumentation. Use the query to discover active events; focus on waits related to redo logs, binlogs, and file I/O. Do not conclude from total time alone, as counters accumulate over long periods and across many workloads.

### Controlled Benchmarking

A useful benchmark should:

1. Use the same data, client count, transaction size, and read/write ratio.
2. Keep other settings constant across test runs.
3. Measure throughput, p95/p99 commit latency, CPU, I/O latency, and wait events.
4. Run long enough for the system to reach steady state; avoid comparing a warm cache run with a cold cache run.
5. Repeat runs and record settings alongside results.
6. Evaluate acceptable data loss, not just TPS.

Never test relaxed durability on critical production data without risk sign-off, restorable backups, and a rollback plan.

## 9. Relationship to Replication and Point-in-Time Recovery

Replicas receive events from the source's binary log. If the latest binlog has not been durably synced when the source or OS crashes, the source may recover data that diverges from the event history the replica already received or needs to read, depending on crash timing and replication mechanics. Setting `sync_binlog=1` shrinks the window of unsynced binlog events.

PITR requires a valid full or physical backup plus continuous binlog files from the backup point up to the target recovery time. If binlogs are missing or corrupted, replay cannot reach the desired point. Thus, `sync_binlog` is part of the durability strategy, while backups and binlog chain verification are part of the recovery strategy.

For replication, also check:

- Whether binlogging is enabled and retention is long enough.
- Whether replicas keep up with the source or show abnormal lag.
- Whether binlog and relay log read/write errors are monitored.
- Whether backups include the required binlog position or GTID information.
- Whether the PITR procedure has been rehearsed in an isolated environment.

Replication does not replace backups: accidental deletions or bad data can be replicated to replicas.

## 10. Process for Changing Both Variables in Production

Before tuning:

1. Define RPO requirements and the crash scenarios the system must survive.
2. Record current values of both variables and their configuration source.
3. Confirm redo logs and binlogs reside on storage with proper flush behavior.
4. Measure baselines for commit latency, TPS, log waits, and I/O.
5. Test changes on staging or a representative test workload.
6. Change one variable at a time in a controlled manner and verify runtime values.
7. Monitor latency, error logs, replication lag, and recoverability.
8. Have a plan to restore previous settings if performance or stability degrades.

Verify values after the change:

```sql
SELECT @@GLOBAL.innodb_flush_log_at_trx_commit AS redo_flush_policy,
       @@GLOBAL.sync_binlog AS binlog_sync_policy;
```

If settings must persist across restarts, save them via option files or `SET PERSIST` per your organization's configuration management process. After a restart, re-verify the effective runtime values rather than just confirming the file was edited.

## 11. Configuration Selection Table by Objective

| Objective | `innodb_flush_log_at_trx_commit` | `sync_binlog` | Notes |
|---|---:|---:|---|
| Prioritize durability for critical transactions | `1` | `1` | Standard recommended choice |
| Accept risk of losing some recent transactions to reduce I/O | `2` or `0` | Value greater than `1`, or `0` | Must quantify RPO and understand crash modes that cause data loss |
| Need durable binlog for replication/PITR while evaluating redo policy | `1` | `1` | Do not trade off binlog independently without understanding commit coordination |
| Running benchmarks where test data preservation is not required | May test other values in an isolated environment | May test other values in an isolated environment | Never carry benchmark configs into production without re-evaluation |

No performance configuration comes for free. Reducing flushes/syncs may increase throughput on log-I/O-bound workloads, but in exchange for a wider data-loss window. If storage is slow, upgrading to storage with power-loss protection or improving I/O is usually worth considering before lowering durability requirements.

## 12. Self-Check

1. What two distinct purposes do the redo log and the binary log serve?
2. How do `innodb_flush_log_at_trx_commit = 0`, `1`, and `2` differ?
3. What do `sync_binlog = 0`, `1`, and `N` mean?
4. Why does `sync_binlog = 1` sync per commit group rather than necessarily syncing individually for every single transaction?
5. Why should both variables be aligned at `1` when prioritizing durability?
6. How does the difference between a `mysqld` process crash and an OS/power crash affect values `0` and `2`?
7. Why can MySQL not guarantee durability if a storage controller falsely reports flush completion?
8. How does `sync_binlog` affect replication and PITR?
9. Which metrics should be measured before trading durability for throughput?
