# Role of the Binary Log and Distinguishing It from InnoDB Redo/Undo Logs

This lesson belongs to the **DATABASE_MYSQL** module. When mastering MySQL, operators need to understand how data is recorded, protected, and recovered, alongside table design, data types, keys, queries, indexes, and transactions. The binary log is a critical component for replication and point-in-time recovery (PITR). To use it properly, it must be distinguished from the redo log and undo log managed by InnoDB.

These three types of logs participate together in the transaction lifecycle but serve different purposes. The binary log records changes at the MySQL Server level to transmit to other servers or replay later. The redo log helps InnoDB recover recorded changes when a crash occurs. The undo log retains old data versions for rollback and to serve consistent reads under the MVCC mechanism.

## 1. What Is the Binary Log?

The **binary log (binlog)** is a log written by MySQL Server containing events that modify data or database structure, according to the binary logging configuration. Events are written in binary format, typically residing in a sequence of files such as `mysql-bin.000001`, `mysql-bin.000002`, and an `.index` file.

The binary log operates at the MySQL Server level, not as a log file private to InnoDB. It can record changes from multiple storage engines supported by MySQL. Read-only statements such as `SELECT` are not normally recorded as data changes in the binlog.

Two most important purposes:

- **Replication:** replica servers read events from the source's binary log and then execute or apply the corresponding changes to maintain data consistency.
- **Point-in-time recovery (PITR):** after restoring a baseline backup, operators replay events in the binlog to bring data to a desired point in time, such as immediately before an accidental deletion.

The binary log only contains events generated during the period when binary logging was enabled and the files were retained. It does not by itself contain the entire database state at a given point in time. Therefore, recovering from scratch requires a suitable baseline backup together with a continuous binlog sequence from the backup point onward.

## 2. The Three Log Types and Their Responsibilities

| Criterion | Binary log | InnoDB redo log | InnoDB undo log |
|---|---|---|---|
| Management scope | MySQL Server | InnoDB storage engine | InnoDB storage engine |
| General content | Data/schema change events in binlog format | Information needed to reapply changes to pages | Old version information to undo changes or provide consistent reads |
| Primary purpose | Replication, PITR, and server-level change recording | Crash recovery and supporting transaction durability | Rollback and MVCC consistent reads |
| Storage engine scope | Not limited to InnoDB | InnoDB only | InnoDB only |
| How it is used | Read by `mysqlbinlog`, replicas, or recovery procedures | Used automatically by InnoDB on startup and data writes | Managed automatically by InnoDB during transactions and the purge process |
| Replaces full backups? | No | No | No |

### 2.1. Binary log: recording changes at the MySQL Server level

The binlog answers the question: **which changes were recorded on the server, and in what order?** Depending on the format, it stores SQL statements or events describing changes to data rows. Replicas and `mysqlbinlog` can read this event stream to reconstruct changes.

The binlog is not a direct copy of pages in a tablespace. Nor is it where InnoDB looks to complete crash recovery on every startup. When MySQL recovers after a crash, InnoDB uses redo and undo; the binary log has a separate role in synchronizing transactions with the storage layer and serving replication/PITR pipelines.

### 2.2. Redo log: reapplying changes during crash recovery

The redo log is the mechanism that records the information needed for InnoDB to reapply changes to data pages. When a transaction updates a row, pages in the buffer pool might not yet be flushed directly to data files. The redo log ensures that committed changes made durable according to configuration can be recovered after a process or server failure.

The redo log is organized as sequential writes and reused across checkpoint cycles. When MySQL starts up after a crash, InnoDB reads the redo log to roll forward the necessary changes. Afterward, InnoDB handles incomplete transactions using the appropriate undo information.

The redo log is not a human-readable business history and is not used as an event stream for replicas to replay. It serves InnoDB's internal recovery on the respective instance.

### 2.3. Undo log: undoing changes and keeping old versions

The undo log stores the information needed to reverse a transaction's changes or provide older row versions for consistent reads. This is a key part of **Multi-Version Concurrency Control (MVCC)**.

For example, transaction A updates a balance from 500 to 650 but has not committed yet. Another read transaction that needs a consistent snapshot can read the appropriate old version from the undo chain instead of seeing the uncommitted value. If transaction A rolls back, InnoDB uses undo information to revert the change.

Undo records are not kept indefinitely. When no active transaction or read view needs an old version anymore, InnoDB can purge undo records whose retention is no longer needed. If a read transaction stays open for a long time, version history may have to be retained longer, increasing the amount of undo that must be managed.

## 3. How Does a Transaction Flow Through the Logs?

Consider a transaction updating an order in an InnoDB table:

```sql
START TRANSACTION;

UPDATE orders
SET status = 'PAID'
WHERE order_id = 10025;

COMMIT;
```

Conceptually, the process involves the following activities:

1. InnoDB modifies data in memory and generates undo information so it can roll back or provide old versions for consistent reads.
2. InnoDB generates redo records so the necessary changes can be reapplied after a crash.
3. When the transaction commits, MySQL coordinates InnoDB's commit with writing the corresponding transaction into the binary log.
4. Once the commit completes according to the configured durability guarantees, the client receives a success response.

Redo and undo serve InnoDB's internal operations. The binary log provides a server-level change record for replication and PITR. The three mechanisms complement each other; they are not three identical copies of the same data.

### 3.1. Why Does MySQL Need to Coordinate InnoDB and the Binary Log?

A transaction can simultaneously produce changes in InnoDB and events in the binlog. If one side commits while the other fails to record the transaction, data state and replication history can become inconsistent. MySQL uses **two-phase commit (2PC)** to coordinate both sides.

At a high level, the commit flow is organized as follows:

1. InnoDB prepares the transaction and writes the required state to the redo log.
2. MySQL writes the transaction to the binary log.
3. InnoDB commits the prepared transaction.

If the server crashes between steps, InnoDB can reconcile prepared transaction states against the binlog during recovery to decide whether to complete the commit or roll back. Internal details may vary by version and configuration, but the goal is to avoid a state where a transaction is committed in InnoDB without a corresponding entry in the binlog, or vice versa.

### 3.2. Durability Depends on Flush Configuration

Two configuration variables are commonly reviewed together:

```sql
SHOW VARIABLES LIKE 'sync_binlog';
SHOW VARIABLES LIKE 'innodb_flush_log_at_trx_commit';
```

- `sync_binlog` controls how frequently MySQL synchronizes the binary log to storage. A value of `1` requests syncing the binlog after every transaction commit according to MySQL's mechanism.
- `innodb_flush_log_at_trx_commit` controls how InnoDB writes and flushes the redo log. A value of `1` requests writing and flushing the redo log on every commit according to InnoDB's design.

Setting both variables to `1` is typically chosen when high data durability is prioritized. In return, it can increase the number of storage sync operations and impact performance. Actual settings should be based on RPO, write load, storage quality, and the system's fault tolerance. Controllers, device caches, or storage infrastructure also affect final guarantees; software configuration cannot compensate for a device that falsely reports write completion.

## 4. Binary Log Formats

MySQL supports different ways of representing events. When inspecting a system's configuration, you must identify the active format and its behavior for the exact server version.

| Format | Main content | Advantages | Caveats |
|---|---|---|---|
| `STATEMENT` | Records executed SQL statements | Can be more compact for certain workloads | Non-deterministic or environment-dependent statements may produce different results on replay |
| `ROW` | Records row-level data change events | Reflects actual row changes, generally safer for replication | Can generate large log volumes, especially for multi-row updates |
| `MIXED` | MySQL chooses statement or row depending on the case | Combines both representations | Requires understanding the switching rules of the running version |

With row-based logging, a single `UPDATE` affecting many rows can generate many row events. `mysqlbinlog -vv` can help decode row events into a more readable form. However, row events do not always contain every column; that also depends on `binlog_row_image` and related settings.

A common misconception: using `ROW` does not mean every operation is logged as a row event. DDL statements such as `CREATE TABLE` or `ALTER TABLE` are still logged as statement events. Inspect the actual binlog if you need to determine the exact event types.

You can check the format and row image options:

```sql
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
```

Default values, dynamic modifiability, and supported formats depend on the MySQL version. Some options have been marked deprecated in newer release series, so check the documentation for your exact version before designing a new configuration.

## 5. Enabling and Verifying Binary Logging

Binary logging must be enabled on MySQL Server before the changes you need to capture occur. Log filenames and paths can be configured in the server configuration file. Illustrative example:

```ini
[mysqld]
server_id=101
log_bin=/var/lib/mysql/mysql-bin
binlog_format=ROW
sync_binlog=1
binlog_expire_logs_seconds=604800
```

Meaning of the options:

- `server_id` identifies the server within a replication topology; each participating server needs an appropriate, unique ID within the topology.
- `log_bin` enables binary logging and specifies the base name/path for binlog files.
- `binlog_format` selects the logging format in versions that still support this option.
- `sync_binlog` controls syncing the binlog to storage.
- `binlog_expire_logs_seconds` sets log retention in seconds; choose a duration long enough for replicas and the required PITR window.

This is a reference configuration, not a universal preset for every system. Changing startup options may require restarting MySQL. The path must exist or be creatable by MySQL with appropriate filesystem permissions; do not manually create or move log files while the server is running.

Checking status:

```sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'server_id';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW BINARY LOGS;
```

To view the current write position, use the statement supported by your version. Newer MySQL versions provide `SHOW BINARY LOG STATUS`; many earlier versions use `SHOW MASTER STATUS` (the older name may be deprecated in newer releases). Verify the syntax against your actual version rather than assuming every server uses the same command name.

## 6. Reading and Replaying Binary Logs with `mysqlbinlog`

`mysqlbinlog` is a command-line tool for reading binlog files, filtering by time range or position, and generating output that can be replayed via the MySQL client.

### 6.1. Inspecting log contents

Read a binlog file:

```bash
mysqlbinlog /var/lib/mysql/mysql-bin.000123
```

With row-based logging, you can use decode mode to view row event information more clearly:

```bash
mysqlbinlog --base64-output=DECODE-ROWS -vv \
  /var/lib/mysql/mysql-bin.000123
```

The output may contain sensitive data values. Only authorized personnel should read, export, or store this decoded output.

### 6.2. Limiting by file position

The binlog uses byte offsets (positions) to mark event boundaries. You can select a range using `--start-position` and `--stop-position`:

```bash
mysqlbinlog \
  --start-position=154 \
  --stop-position=9821 \
  /var/lib/mysql/mysql-bin.000123 > replay.sql
```

The values above only illustrate syntax. During recovery, you must obtain actual positions from backup metadata, inspection command output, or verified points in the binlog. Ensure start and stop points lie cleanly on event/transaction boundaries; cutting mid-transaction can yield invalid replay content or fail to reach the intended state.

### 6.3. Limiting by time

You can filter by timestamp:

```bash
mysqlbinlog \
  --start-datetime="2026-11-19 01:00:00" \
  --stop-datetime="2026-11-19 10:14:59" \
  /var/lib/mysql/mysql-bin.000123 \
  /var/lib/mysql/mysql-bin.000124 > replay.sql
```

Timestamps are merely a convenient way to choose a range. Verify time zones, event timestamps, and transaction boundaries. When exact recovery is needed, file positions or GTIDs are usually a more reliable basis of control than relying solely on displayed seconds.

### 6.4. Replaying on a recovery server

After reviewing the `replay.sql` file, you can replay it into the recovery instance:

```bash
mysql --host=db-restore.example.net \
  --user=recovery_user --password < replay.sql
```

A safe procedure usually restores the baseline backup onto an isolated server first, and then replays the binlog up to the target point. Do not pipe unverified output directly into production. Verify the log files, ordering, range, execution account, and impact of DDL/DML statements before replaying.

## 7. GTID vs. File/Position

MySQL has two common ways to identify transaction progress in replication and recovery:

- **File/position:** identifies a binlog filename together with a byte offset in the file, for example `mysql-bin.000123` at position `9821`.
- **GTID (Global Transaction Identifier):** identifies a transaction using a unique identifier based on server UUID and transaction sequence number, for example `3E11FA47-71CA-11E1-9E33-C80AA9429562:57`.

GTIDs help identify executed transactions without manually tracking file/position pairs in many replication scenarios. However, GTID is not a log type that replaces the binlog. The binlog still holds the events; GTID attaches transaction identifiers and aids in tracking and locating progress.

In a GTID-enabled environment, record the GTID metadata at backup time and ensure the required transaction sequence remains available. During restore, the recovery instance's GTID state must match the transaction application workflow to avoid replaying duplicates or missing changes. Do not modify `gtid_purged` or GTID state by guesswork.

## 8. Binary Log Rotation, Retention, and Purging

MySQL writes the binlog across multiple files. When the current file reaches rotation criteria or a flush occurs, the server switches to a new file and updates the index file. Retention determines how long logs are kept before expiring or being deleted through administrative actions.

Binary logs need to be retained long enough for both sets of needs:

1. Slow or temporarily disconnected replicas still need unread logs.
2. PITR procedures require a continuous chain of logs from the baseline backup through any window where an incident may occur.

Do not manually delete binlog files from the filesystem while MySQL is managing them. Use administrative statements to purge up to an appropriate boundary:

```sql
-- View the list of existing files
SHOW BINARY LOGS;

-- Example: delete files older than the specified target file
PURGE BINARY LOGS TO 'mysql-bin.000120';

-- Or delete files with timestamps before the specified time
PURGE BINARY LOGS BEFORE '2026-11-01 00:00:00';
```

`PURGE BINARY LOGS TO` deletes files preceding the target file, not the target file itself. Before purging, verify whether replicas have read the required files and whether backup/PITR storage has archived them elsewhere. Purging too early can leave replicas without logs to catch up and break the PITR chain.

You can check the configured retention period:

```sql
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
```

Retention should exceed the expected backup and recovery window, accounting for incident detection, investigation, approval, and restore execution time. If logs are shipped to external storage, verify the integrity and retrievability of those stored copies.

## 9. The Binary Log in a PITR Workflow

PITR combines a baseline backup with a continuous chain of binlogs following the backup point. For example:

- 01:00: take a full backup and record the corresponding file/position or GTID.
- 10:15: an accidental deletion occurs.
- 10:30: the operations team detects the incident.

Recovery steps:

1. Select the 01:00 full backup and verify it can be restored.
2. Restore onto an isolated instance compatible with the source environment.
3. Retrieve the replay starting point from the backup's metadata.
4. Gather all continuous binlogs from that point up to immediately before the accidental deletion.
5. Inspect the events and transaction boundaries, then replay them on the recovery instance.
6. Reconcile business data and decide whether to restore the entire instance or extract only the needed data subset.

The binlog cannot recover changes that occurred before binary logging was enabled, a lost log, or a log gap missing from all archives. Therefore, monitor logging status and ship logs off the source server to an independent location.

Replication also does not replace backups. An accidental delete or corrupted data can be written to the binlog and propagated to replicas. Replicas improve availability and can reduce downtime, but independent backups plus retained binlogs are still required to return to a pre-incident state.

## 10. Common Operational Issues

| Symptom | Possible cause | What to check |
|---|---|---|
| No binlog files present | Binary logging is not enabled or path/config is incorrect | Check `log_bin`, startup configuration, and error log |
| Replica reports missing binlog | Source purged files that the replica had not yet read | Check replica status, retention, and log chain; may need to rebuild replica from a fresh backup |
| PITR stops before target time | Missing file, broken log chain, or inaccurate backup metadata | Check file list, position/GTID, and off-server archives |
| Statement error during replay | Wrong order, schema mismatch, different target environment, or unsuitable event | Inspect `mysqlbinlog` output, schema, and start/stop boundaries |
| Binlog grows rapidly | Heavy write load, many row events, or long retention | Measure log generation rate, inspect workload, and review storage planning |
| Discrepancy to investigate after crash | Durability settings, storage failure, or commit state needing analysis | Check error log, redo recovery, `sync_binlog`, and `innodb_flush_log_at_trx_commit` |

Binlogs can contain sensitive data, including values recorded in statements or row events. Restrict read permissions, encrypt in transit and at rest, and apply appropriate retention. Decoded output from `mysqlbinlog` must also be protected just like the source data.

## 11. Quick Inspection Procedure on a Server

Operators can start with the following statements:

```sql
-- Is binary logging enabled?
SHOW VARIABLES LIKE 'log_bin';

-- Does the server have an appropriate identifier?
SHOW VARIABLES LIKE 'server_id';

-- Binlog format and durability
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'sync_binlog';

-- Redo durability and binlog retention
SHOW VARIABLES LIKE 'innodb_flush_log_at_trx_commit';
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';

-- Binlog files remaining on the server
SHOW BINARY LOGS;
```

Next, check the current file/position using the status statement appropriate for the MySQL version, inspect replicas if any, and cross-check the binlog position recorded in the latest backup's metadata. Do not conclude a system is PITR-ready merely because `log_bin=ON`; you must prove that log files are stored completely, continuously, and can be read and replayed.

## 12. Self-Check

1. What are the two primary operational purposes of the binary log?
2. Why cannot the redo log and binary log replace each other in crash recovery and replication?
3. How does the undo log support rollback and MVCC consistent reads?
4. When an InnoDB transaction commits, why must MySQL coordinate InnoDB state with binlog writes?
5. What is the main difference between `STATEMENT` and `ROW` logging? Why can DDL still be logged as statement events when using row-based logging?
6. Which two mechanisms do `sync_binlog` and `innodb_flush_log_at_trx_commit` control?
7. Why must file/position or GTID be stored alongside backup metadata?
8. What can happen if binlogs are purged before a replica finishes reading them or before the required PITR window ends?
9. Why does a replica not replace an independent backup?
10. Describe how to restore a baseline backup and replay binlogs to recover immediately before a transaction that deleted data.

When answering, always identify whether a log belongs to the MySQL Server layer or InnoDB, what kind of information it records, and at which step of the transaction lifecycle it is used. Properly distinguishing these three roles helps you design replication, backups, PITR, and incident troubleshooting without confusing internal storage engine recovery with server-level change history replay.
