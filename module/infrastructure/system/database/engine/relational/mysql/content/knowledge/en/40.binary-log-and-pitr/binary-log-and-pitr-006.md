# Rotating, Expiring, and Using PURGE BINARY LOGS for Recovery and Replication Needs

The binary log records events that modify data in MySQL. It is a critical input for replication and point-in-time recovery (PITR). Therefore, managing the binary log lifecycle must balance three goals: keeping enough history for recovery, keeping enough logs for every replica to catch up with the source, and bounding storage capacity.

This lesson belongs to the **DATABASE_MYSQL** module and focuses on relational database operations: inspecting log status, proactively rotating logs, configuring automatic expiration, performing manual purges, and planning based on recovery requirements. Examples use MySQL 8.0; some command and variable names differ across versions.

## 1. Role of the Binary Log in Recovery and Replication

The binary log is a sequence of files containing data-changing events recorded by the server. Depending on **binlog_format**, events may represent SQL statements or data row changes. Read-only queries such as **SELECT** are not normally recorded in the binary log.

The binary log serves two primary purposes:

- **Replication:** replicas read events from the source, store them in relay logs, and apply them to replica data.
- **PITR:** after restoring a full backup, the DBA replays events occurring after the backup time to bring data to a desired point in time.

The binary log is not a full backup. It is only meaningful for recovery when paired with an appropriate baseline backup and a continuous set of logs from that backup point onward. If a file is missing mid-chain, you cannot assume subsequent files suffice to reconstruct an exact state.

A server with binary logging enabled normally creates files named **mysql-bin.000001**, **mysql-bin.000002**... and a **.index** index file listing the binary logs. Filenames and paths depend on **log_bin** and **log_bin_index** settings.

Checking status:

~~~sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'log_bin_basename';
SHOW VARIABLES LIKE 'log_bin_index';
SHOW VARIABLES LIKE 'max_binlog_size';
SHOW BINARY LOGS;
~~~

To view the file currently being written:

~~~sql
-- MySQL 8.0
SHOW MASTER STATUS;

-- MySQL 8.4
SHOW BINARY LOG STATUS;
~~~

In MySQL 8.4, **SHOW BINARY LOG STATUS** replaces **SHOW MASTER STATUS**. Use the syntax supported by your server version.

## 2. What Is Binary Log Rotation?

Rotation closes the current binary log file and opens a new one with the next sequence number. Rotating creates clear file boundaries for managing, copying, archiving, or processing logs. Rotation does not delete history and does not lose events already written to older files.

MySQL rotates automatically in common situations:

- The server starts or restarts.
- The server executes a log flush operation.
- The current file size exceeds the **max_binlog_size** threshold.

The default value of **max_binlog_size** in MySQL 8.0 is 1 GB. This is a rotation trigger threshold, not an absolute hard cap. A transaction is written atomically into the binary log and is never split across multiple files, so a large transaction can push a file past the threshold.

View configuration:

~~~sql
SHOW VARIABLES LIKE 'max_binlog_size';
~~~

Change the threshold dynamically on a running server:

~~~sql
SET GLOBAL max_binlog_size = 536870912;
~~~

The example above sets a 512 MB threshold. To persist across the next restart, use **SET PERSIST** if your version and configuration management policy allow:

~~~sql
SET PERSIST max_binlog_size = 536870912;
~~~

There is no need to rotate overly frequently just to produce many small files. Every rotation increases the number of files to track, back up, and transfer. Choose a threshold suited to log generation rate, storage capacity, and operational workflow.

## 3. Proactively Rotating with FLUSH BINARY LOGS

A DBA can instruct MySQL to close the current binary log and open the next file:

~~~sql
FLUSH BINARY LOGS;
~~~

The executing account requires the **RELOAD** privilege. **FLUSH LOGS** can also flush supported logs, but **FLUSH BINARY LOGS** clearly expresses the intent to rotate only binary logs.

Before-and-after verification example:

~~~sql
SHOW BINARY LOGS;
SHOW MASTER STATUS;

FLUSH BINARY LOGS;

SHOW BINARY LOGS;
SHOW MASTER STATUS;
~~~

In MySQL 8.4, replace **SHOW MASTER STATUS** with **SHOW BINARY LOG STATUS**.

Appropriate situations for manual rotation:

- Creating a clean log boundary prior to a backup run or shipping logs to archive storage.
- Starting a new file to simplify collecting logs by operational interval.
- Testing binary log backup procedures or capacity monitoring workflows.
- Coordinating with a scheduled maintenance workflow.

Rotation does not equate to purging. **FLUSH BINARY LOGS** does not mean older files are deleted immediately; deletion depends on automatic expiration, manual purge commands, and related constraints.

## 4. Configuring Automatic Expiration

MySQL can automatically delete expired binary logs. In MySQL 8.0, the recommended variable is **binlog_expire_logs_seconds**.

~~~sql
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW VARIABLES LIKE 'binlog_expire_logs_auto_purge';
SHOW VARIABLES LIKE 'expire_logs_days';
~~~

**binlog_expire_logs_seconds** measures retention in seconds. The default in MySQL 8.0 is 2,592,000 seconds, equivalent to 30 days, unless overridden by other settings. For example, setting retention to 14 days:

~~~sql
SET PERSIST binlog_expire_logs_seconds = 1209600;
~~~

Automatic deletion can occur at server startup and when binary logs are flushed. Therefore, do not assume a file will vanish at the exact second day 14 elapses; actual deletion timing also depends on when MySQL runs its purge check.

### Enabling or Disabling Automatic Purge

Starting in MySQL 8.0.29, the **binlog_expire_logs_auto_purge** variable controls automatic purging:

~~~sql
-- Enable time-based automatic purging
SET PERSIST binlog_expire_logs_auto_purge = ON;

-- Disable automatic purging
SET PERSIST binlog_expire_logs_auto_purge = OFF;
~~~

When this variable is **OFF**, MySQL does not automatically purge expired logs, though manual **PURGE BINARY LOGS** commands remain effective. On MySQL 8.0.28 and earlier, this variable does not exist; disabling automatic purge is done by configuring **binlog_expire_logs_seconds = 0** per version rules.

### Legacy `expire_logs_days` Variable

**expire_logs_days** is a legacy variable, deprecated in MySQL 8.0. Its replacement is **binlog_expire_logs_seconds**. If both variables have non-zero values at startup, **binlog_expire_logs_seconds** takes precedence and MySQL emits a warning. At runtime, both cannot be set to non-zero values simultaneously. When administering older servers, check both to avoid misreading the effective retention period.

Do not set a short retention solely to resolve a full disk. Before lowering retention, recalculate the time required for PITR, replica lag, and the maximum outage duration that could occur.

## 5. Manual PURGE BINARY LOGS

**PURGE BINARY LOGS** deletes older binary log files while updating the **.index** file. This is the MySQL-supported way to delete logs by filename or timestamp.

### Deleting by Filename

~~~sql
PURGE BINARY LOGS TO 'mysql-bin.000125';
~~~

The command above deletes binary logs preceding **mysql-bin.000125**; **mysql-bin.000125** itself is kept and becomes the first remaining file in the list.

### Deleting by Timestamp

~~~sql
PURGE BINARY LOGS BEFORE '2026-11-01 00:00:00';
~~~

The command above deletes files whose timestamp precedes the specified boundary per MySQL rules. Inspect the file list and timestamps before running; never assume every file with a smaller sequence number is safe to delete.

The executing account needs the **BINLOG_ADMIN** privilege in MySQL 8.0. Never delete binary log files using filesystem commands such as **rm** or **Remove-Item**. Doing so can leave **.index** referencing missing files, causing errors during subsequent log management or purges by MySQL.

**PURGE BINARY LOGS** does not delete the binary log file currently being written. If the target filename does not exist or the timestamp is invalid, the command can fail. Always verify with **SHOW BINARY LOGS** after purging.

### Distinguishing PURGE from RESET

Never use reset commands for routine log cleanup. In MySQL 8.0, **RESET MASTER** deletes all binary logs and resets GTID history; in MySQL 8.4, the replacement command is **RESET BINARY LOGS AND GTIDS**. Reset commands have a much broader impact than purge, are not meant for routine maintenance, and must not be run while replicas are active. Consider them only when reinitializing an isolated, controlled environment after fully understanding their impact on GTIDs and replication.

## 6. Retaining Binary Logs Long Enough for Replicas

Replicas must read binary logs from the source to stay caught up. If the source purges a file a replica has not yet read, the replica may be unable to resume replication when it reconnects. This is a common risk when a replica stays stopped for a long time, experiences network outages, or has slow apply throughput.

Before purging, check status on every replica:

~~~sql
SHOW REPLICA STATUS\G
~~~

Read fields such as:

- **Source_Log_File**: the source binary log file currently being read by the I/O thread.
- **Read_Source_Log_Pos**: the position already read within the source file.
- **Replica_IO_Running** and **Replica_SQL_Running**: status of the receiver and applier threads.
- **Seconds_Behind_Source**: estimated replica lag; a **NULL** value does not mean the replica is caught up cleanly.
- Latest I/O and SQL errors to detect a stopped or falling-behind replica.

On the source, view the file list:

~~~sql
SHOW BINARY LOGS;
~~~

Safe purge-point selection workflow:

1. Check every replica, including offline replicas or replicas that run only on a schedule.
2. Determine the earliest source file each replica still needs to read.
3. Find the earliest file across all those replicas.
4. Archive binary logs slated for deletion if still needed for recovery or investigation.
5. Purge only files preceding the target file.
6. Monitor replication status after purging.

For example, if the slowest replica still needs **mysql-bin.000120**, you may only purge files preceding it:

~~~sql
PURGE BINARY LOGS TO 'mysql-bin.000120';
~~~

MySQL refuses to delete a file actively in use by a connected replica and any files newer than it; warnings may appear if certain files cannot be deleted yet. However, this safeguard does not protect an offline replica that has not read older files. When that replica reconnects, if required logs have already been purged, it must be rebuilt from an appropriate backup or another recovery procedure.

Do not rely solely on **Seconds_Behind_Source** when deciding to purge. Check receiver/applier thread state, file/position, maximum offline duration, and each replica's actual operating schedule.

## 7. Retaining Binary Logs Long Enough for PITR

PITR typically has two phases:

1. Restore a full backup to bring the database to its state at backup time.
2. Replay binary logs after that point up to the desired recovery point.

Consequently, retention must cover the entire recoverable window. For example, if full backups run every Sunday and the organization wants to recover to any point within the last 21 days, logs must be retained continuously at least from the oldest still-valid full backup onward, plus an operational buffer.

Plan capacity based on actual log generation rate:

**Estimated capacity ≈ average daily binlog volume × retention days × safety buffer factor**

For example, if the system generates an average of 12 GB of binlog per day and needs 21 days of retention, baseline space is roughly 252 GB before adding a safety factor. Measure across days with varying workloads; batch or large import days can generate far more log volume than average.

Beyond server-local retention, consider copying binary logs to an independent storage location. If the disk holding the data directory and binlogs fails together, local logs can be lost alongside the data. **mysqlbinlog** can be used to read and back up binary logs from the source server; protect those copies and verify readability.

## 8. Using mysqlbinlog to Inspect and Process Logs

**mysqlbinlog** reads binary logs and converts events into a form that can be inspected or replayed. Example reading a file:

~~~bash
mysqlbinlog mysql-bin.000120
~~~

To view detailed row events in readable form:

~~~bash
mysqlbinlog --base64-output=DECODE-ROWS -vv mysql-bin.000120
~~~

You can filter by time or position for investigation:

~~~bash
mysqlbinlog --start-datetime="2026-11-18 08:00:00" --stop-datetime="2026-11-18 10:30:00" mysql-bin.000120
~~~

To back up binary logs remotely in binary form, **mysqlbinlog** supports **--read-from-remote-server** and **--raw**. When reading encrypted logs, read over a connection to the server rather than opening encrypted files directly on the filesystem. Secure connections with TLS and use an account with appropriate replication privileges.

Never arbitrarily edit or delete binary log contents. If an erroneous transaction needs to be excluded during PITR, analyze the events, pick exact stop boundaries, and test recovery in an isolated environment before executing against a live system.

## 9. Example Point-in-Time Recovery

Suppose a full backup exists from 01:00 on November 18 and you need to restore the database to 10:30 the same day, right before an accidental deletion occurred.

**Step 1: restore the full backup**

Restore the full backup onto a dedicated recovery server following the backup tool's instructions. Record the binary log filename and position or GTID captured by the backup.

**Step 2: identify files and positions to replay**

Use **SHOW BINARY LOGS**, backup metadata, and **mysqlbinlog** to determine the log chain starting right after the backup point. Inspect events around 10:30 to locate the transaction to exclude.

**Step 3: generate a preview**

~~~bash
mysqlbinlog --start-datetime="2026-11-18 01:00:00" --stop-datetime="2026-11-18 10:30:00" mysql-bin.000120 mysql-bin.000121
~~~

This is an illustrative example; replace filenames, timestamps, and start points with actual backup metadata. Once exact event positions are known, prefer **--start-position** and **--stop-position** to control replay boundaries. Timestamps are only an initial locating aid and must be verified against actual events.

**Step 4: replay on the recovery server**

~~~bash
mysqlbinlog --start-position=154 --stop-position=987654 mysql-bin.000120 | mysql --binary-mode -u restore_user -p
~~~

If multiple files must be processed, pass them in order within a single **mysqlbinlog** invocation and a single **mysql** connection. This preserves cross-file context, such as when a temporary table is created in an earlier file and used in a subsequent file.

Never copy the example positions above into a real system. Positions must point to verified event boundaries; a wrong stop point can replay the erroneous transaction or omit valid transactions.

**Step 5: verify**

Inspect tables, row counts, business data, and referential integrity. Run application verification queries on the recovery server before deciding how to promote data back to production.

## 10. Common Operational Issues

### Disk full due to rapid binary log growth

Check log generation rate, file sizes, retention, replica lag, and PITR status. If space must be freed immediately, identify the oldest files safe to delete under both replica and backup requirements. Purge up to a safe boundary, then adjust retention or storage capacity. Never delete files directly from the filesystem.

### Replica reports missing binary log

Error messages typically indicate the replica requested a source file that no longer exists. Check the file/position requested by the replica, the remaining files on the source, and backups available to rebuild the replica. If needed logs are gone, reliable recovery usually means recreating the replica from a consistent backup and configuring replication from the corresponding point.

### Unable to purge certain files

Check files currently in use by replicas, the active log file, backup lock state, and the **BINLOG_ADMIN** privilege. Since MySQL 8.0.28, purging is blocked while **LOCK INSTANCE FOR BACKUP** is active. Never work around this by editing the **.index** file while the server is running.

### PITR fails to replay logs

Check whether the file sequence is continuous, whether files are encrypted, whether the log-reading account has sufficient privileges, and whether the start point matches backup metadata. Confirm the **mysqlbinlog** version is compatible with the logs. When using event positions, ensure start and stop offsets align with valid event boundaries.

### Automatic retention behaves unexpectedly

Check **binlog_expire_logs_seconds**, **binlog_expire_logs_auto_purge**, and the legacy **expire_logs_days** variable. Automatic deletion is checked at startup and during log flushes; files are not guaranteed to disappear at the exact expiration second. If an immediate cleanup of confirmed-safe files is needed, use **PURGE BINARY LOGS**.

## 11. Recommended Operating Procedure

**Daily monitoring**

- Record binary log capacity and daily generation rate.
- Monitor replica lag, I/O thread state, and SQL thread state.
- Alert when a replica remains offline longer than expected thresholds.
- Track remaining log span relative to the oldest backup required for recovery.

**When rotating or purging**

- Inspect the log list and current file status.
- Identify all replicas that still need logs.
- Identify backups and the PITR window that must be preserved.
- Back up files prior to purging if retention or investigation needs remain.
- Run purge by filename or timestamp, then verify the remaining list.
- Log the operator, purge boundary, and replication outcome.

**Periodic review**

- Test restoring a full backup and replaying binlogs to a target point.
- Verify off-server binary log archives.
- Tune retention according to RPO, RTO, backup schedule, replica lag, and capacity.
- Audit access permissions, encryption, and log retention policies.

Checklist:

- [ ] Binary logging is enabled and the log storage path is known.
- [ ] Operator knows how to inspect the active file and list binary logs.
- [ ] **max_binlog_size** fits generation rate and operational workflows.
- [ ] **binlog_expire_logs_seconds** accurately reflects the PITR window.
- [ ] **binlog_expire_logs_auto_purge** has been checked if supported by the version.
- [ ] Every replica has been checked prior to purging.
- [ ] Offline replicas and scheduled replicas have been accounted for.
- [ ] Only **PURGE BINARY LOGS** is used to delete logs, never manual filesystem deletion.
- [ ] Independent binary log copies exist if required by recovery objectives.
- [ ] Point-in-time recovery has been rehearsed.

## Conclusion

Rotation creates new binary log files to split history into manageable segments. Automatic expiration enforces time-based retention by policy, while **PURGE BINARY LOGS** lets DBAs remove files confirmed safe to delete. Before every purge operation, check both the PITR window and the needs of all replicas. A sound policy relies on log generation rate, backup intervals, replica lag, storage capacity, and recovery drill results.

## References

- [MySQL 8.0 Reference Manual — The Binary Log](https://dev.mysql.com/doc/refman/8.0/en/binary-log.html)
- [MySQL 8.0 Reference Manual — Binary Logging Options and Variables](https://dev.mysql.com/doc/refman/8.0/en/replication-options-binary-log.html)
- [MySQL 8.0 Reference Manual — PURGE BINARY LOGS Statement](https://dev.mysql.com/doc/refman/8.0/en/purge-binary-logs.html)
- [MySQL 8.0 Reference Manual — Server Log Maintenance](https://dev.mysql.com/doc/refman/8.0/en/log-file-maintenance.html)
- [MySQL 8.0 Reference Manual — Point-in-Time Recovery Using Binary Log](https://dev.mysql.com/doc/refman/8.0/en/point-in-time-recovery-binlog.html)
- [MySQL 8.4 Reference Manual — RESET BINARY LOGS AND GTIDS](https://dev.mysql.com/doc/refman/8.4/en/reset-binary-logs-and-gtids.html)
