# Log Rotation, Retention Policies, and Disk-Full Alerting

MySQL generates several types of logs for diagnostics, query optimization, replication, and data recovery. Without a lifecycle policy, log files can grow continuously, fill up the filesystem, and prevent MySQL from writing data or starting normally. Safe operations require defining **which logs must be enabled, where they are stored, when they rotate, how long they are kept, under what conditions they are deleted, and how alerts fire before space runs out**.

This lesson belongs to the **Configuration and Operations** section of MySQL. You will distinguish the error log, general log, slow query log, binary log, and relay log; configure appropriate logging levels; rotate files and instruct MySQL to reopen logs; set retention; monitor space and inodes; build alerts; and handle nearly full filesystems without damaging InnoDB storage state.

## 1. Distinguishing MySQL Log Types

Not every file with `log` in its name serves the same purpose or rotates the same way. Classify them before writing a policy:

| Log Type | Purpose | When to Enable/Retain | Lifecycle Management |
| --- | --- | --- | --- |
| Error log | Records startup/shutdown events, errors, warnings, engine incidents, and operational notices. | Always needs an appropriate destination; usually stored durably or shipped to centralized logging. | Rotate by day/size or manage via journald/syslog/Event Log; instruct MySQL to reopen the file after renaming. |
| General query log | Records client connections and statements sent to the server. | Enable only during targeted diagnostics due to high write volume and potential sensitive data. | Disable after investigation; if retention is required, rotate frequently with short retention. |
| Slow query log | Records queries exceeding a time threshold or matching logging criteria. | Can remain enabled long-term to detect slow queries and track trends. | Rotate periodically, compress, and retain per analysis/compliance needs. |
| Binary log (binlog) | Records data-change events for replication and point-in-time recovery. | Enable when replication, PITR, or event-level audit requirements apply. | Use expiration policies and `PURGE BINARY LOGS`; never delete files manually. |
| Relay log | Stores binlog events received by a replica from its source before applying. | Present on replicas using replication. | Let the replication mechanism manage it; monitor `relay_log_purge` and replica status. |
| InnoDB redo/undo logs | Crash recovery, rollback, and reconstructing old versions for MVCC. | Internal InnoDB components. | Managed via InnoDB configuration/mechanisms; never rotate or delete like text logs. |

Audit logs may be provided by plugins or commercial products depending on version and environment. If auditing is enabled, include its capacity, retention, read permissions, and shipping to centralized logging in the same operational plan.

## 2. Locating Logs and Their Filesystems

Before setting retention, you must know where each log lives. Run the following statements on the exact target instance:

```sql
SELECT
    @@hostname AS host_name,
    @@port AS port_number,
    @@datadir AS data_directory,
    @@tmpdir AS temporary_directory,
    @@log_error AS error_log;

SHOW VARIABLES WHERE Variable_name IN (
    'general_log',
    'general_log_file',
    'slow_query_log',
    'slow_query_log_file',
    'log_output',
    'log_bin',
    'log_bin_basename',
    'relay_log',
    'relay_log_basename',
    'innodb_redo_log_capacity'
);
```

Some variables may not exist in older versions or may return empty values if the corresponding feature is disabled. Read the actual configuration instead of assuming every instance has binlogs or relay logs.

Inspect the filesystems holding `datadir`, the log directory, `tmpdir`, the redo directory, and centralized log locations. Placing the error log on a separate filesystem helps preserve diagnostic capability when the data volume hits trouble, though only if that volume is also monitored and adequately sized.

Do not let the general log, slow log, binlog, relay log, redo, and temporary files all depend on a single small volume without quotas or alerts. A single query creating huge temporary files can fill the volume even when logs are rotated properly.

## 3. Configuring the Error Log

The error log is the first place to look when MySQL fails to start, crashes, detects storage problems, or logs replication warnings. On MySQL 8.0, key variables include:

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'log_error',
    'log_error_verbosity',
    'log_error_services'
);
```

`log_error_verbosity` controls detail level:

| Value | General Contents |
| ---: | --- |
| `1` | Errors only. |
| `2` | Errors and warnings. |
| `3` | Errors, warnings, and notes. |

Higher levels aid investigation but generate more log volume. Choose the level based on monitoring needs and disk capacity. `log_error_services` defines filter/sink components for the error log; defaults and supported sinks depend on version and platform.

The error log can be written to a file, stderr, system log, or Windows Event Log depending on configuration. When using journald/syslog or Event Log, rotation and retention are typically managed by the OS. When writing to a file, coordinate log rotation tools with instructing MySQL to reopen the file.

## 4. General Log: Enable Only When Necessary

The general query log records connections and statements sent by clients to the server. It is useful when verifying what an application actually sends, but can substantially increase I/O on query-heavy workloads.

Check status:

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'general_log',
    'general_log_file',
    'log_output'
);
```

Enable temporarily during an investigation:

```sql
SET GLOBAL log_output = 'FILE';
SET GLOBAL general_log = ON;
```

Immediately disable once sufficient information is gathered:

```sql
SET GLOBAL general_log = OFF;
```

GLOBAL changes can affect the entire instance. Announce an investigation window, set a time limit, monitor file growth rate, and enable only when genuinely needed. The general log can capture SQL literals or sensitive business data; restrict read permissions, avoid pasting raw files into tickets/chats, and delete per approved retention.

`log_output` controls the destination for the general log and slow query log (`FILE`, `TABLE`, or a combination depending on version). It does not control the error log or binary log. Writing to `mysql.general_log`/`mysql.slow_log` tables has different management overhead than files and still consumes storage space.

## 5. Slow Query Log: Targeted Collection

The slow query log helps detect queries whose execution time or examined row count exceeds configured thresholds. Common variables:

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'slow_query_log',
    'slow_query_log_file',
    'long_query_time',
    'min_examined_row_limit',
    'log_queries_not_using_indexes',
    'log_throttle_queries_not_using_indexes',
    'log_output'
);
```

Configuration example:

```sql
SET GLOBAL slow_query_log = ON;
SET GLOBAL long_query_time = 1;
SET GLOBAL min_examined_row_limit = 100;
```

This example logs queries exceeding 1 second that examined at least 100 rows. Suitable thresholds depend on SLAs, workload, and query rates; 1 second is not a universal standard for every system.

`log_queries_not_using_indexes` can cause logs to grow rapidly, especially with frequent small-table scans or periodic queries. If enabled, consider `log_throttle_queries_not_using_indexes` to rate-limit logged entries over time. Analyze logs alongside digests, `EXPLAIN`, and actual metrics; never add indexes solely because a query appeared in the slow log.

The slow log should be rotated periodically and retained long enough to spot trends. For aggregate analysis, run `pt-query-digest` or an equivalent tool on a protected log copy; sanitize sensitive data before sharing.

## 6. Rotating Error Log, General Log, and Slow Query Log

Rotating text log files typically involves three steps:

1. Rename the current file or move the old file to an archive location.
2. Create a new file with appropriate owner, group, and permissions if required by the rotation tool.
3. Instruct MySQL to close the old handle and reopen the log file.

With MySQL, use the corresponding FLUSH commands where supported:

```sql
FLUSH ERROR LOGS;
FLUSH GENERAL LOGS;
FLUSH SLOW LOGS;
```

`FLUSH LOGS` has broader scope and can also rotate binary logs. When you only want to reopen a specific text log, use the targeted command if supported by your version. The executing account needs appropriate administrative privileges, typically `RELOAD` or the corresponding FLUSH privilege for your version.

### Example Integration with logrotate on Linux

An illustrative configuration for the error log:

```text
/var/log/mysql/error.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 mysql adm
    sharedscripts
    postrotate
        mysql --login-path=logrotate -e "FLUSH ERROR LOGS;" >/dev/null 2>&1
    endscript
}
```

This template must be adapted to your server's exact paths, user/group, and authentication mechanism. Create a secure login path using `mysql_config_editor` or use your system's secrets mechanism; never put plaintext passwords in logrotate configs or command lines.

For slow/general logs, create separate rules and use `FLUSH SLOW LOGS` or `FLUSH GENERAL LOGS` in their respective `postrotate` steps. Do not combine multiple files into one rule if each file needs a different reopen command.

The rename-then-reopen approach is generally safer than `copytruncate`. With `copytruncate`, log lines can be lost or duplicated during the window between copy and truncate because MySQL is still writing to the same file. If forced to use it, understand and accept that risk window.

### Rotating Logs on Windows or Centralized Logging Systems

If the error log writes to a file on Windows, use an appropriate OS rotation mechanism or log agent, then run `FLUSH ERROR LOGS` so MySQL reopens the file when needed. If logs go to Event Log, journald, or syslog, retention is managed by that service; configure size and retention limits directly in the receiving log service.

Never delete an open log file via filesystem commands and assume space is freed. On some OSes, a deleted open file continues consuming disk space until the process closes its handle; on others, deleting an open file causes errors or breaks logging.

## 7. Binary Log: Retention Must Align with Replication and PITR

The binary log contains data-change events. It can serve as the source stream applied by replicas and is required when recovering to a specific point in time after restoring a backup. Deleting binlogs too early can prevent replicas from fetching needed events or make PITR unable to reach the desired point in time.

Check configuration:

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'log_bin',
    'log_bin_basename',
    'binlog_expire_logs_seconds',
    'sync_binlog',
    'server_id',
    'gtid_mode'
);
```

In MySQL 8.0, `binlog_expire_logs_seconds` sets automatic binary log expiration in seconds. For example, keeping approximately 14 days:

```sql
SET PERSIST binlog_expire_logs_seconds = 1209600;
```

`SET PERSIST` writes configuration for subsequent startups and updates the dynamic variable if supported. On versions without `SET PERSIST`, configure it in the config file under `[mysqld]` and restart per procedure.

Retention must exceed the maximum expected replica outage plus the PITR window, plus a safety margin. Do not pick 14 days merely because of the example; calculate from backup schedules, backup retention, replica lag, recovery requirements, and actual disk capacity.

### Checking Binlogs Before Purging

List files and sizes:

```sql
SHOW BINARY LOGS;
```

On a MySQL 8.0 source, check how far replicas have read/applied using version-appropriate replication status, for example on versions supporting the new syntax:

```sql
SHOW REPLICA STATUS\G
```

On older MySQL versions, the command may be `SHOW SLAVE STATUS\G`. Cross-check executed positions/GTIDs across all replicas, including offline replicas, along with backup metadata and PITR policies.

If manual binlog deletion is needed, use the administrative statement:

```sql
PURGE BINARY LOGS TO 'binlog.000250';
```

This deletes files prior to the specified file, preserving the target file itself. You can also purge by timestamp:

```sql
PURGE BINARY LOGS BEFORE '2026-11-01 00:00:00';
```

Purge only after confirming no replica still needs those files and backups/PITR do not require them. Never delete binlogs with `rm`, PowerShell `Remove-Item`, or direct file manipulation; let MySQL update the binlog index and corresponding metadata.

### Rotating the Binary Log

You can proactively close the current file and open a new binlog file:

```sql
FLUSH BINARY LOGS;
```

This creates a new file boundary; it does not delete old logs. Avoid using `FLUSH LOGS` inside error-log rotation scripts if you do not want to unintentionally create extra binlog files. Track hourly/daily binlog growth to forecast retention.

## 8. Relay Logs on Replicas

A replica receives events from its source and stores them in relay logs before the SQL applier processes them. Check:

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'relay_log',
    'relay_log_basename',
    'relay_log_purge',
    'relay_log_space_limit',
    'relay_log_recovery'
);
```

Normally `relay_log_purge` is enabled so MySQL automatically deletes relay logs once applied. `relay_log_recovery` helps replicas recover relay logs on startup in appropriate configurations. `relay_log_space_limit`, if set, can pause the receiver thread when the limit is exceeded.

When relay logs grow abnormally, check for SQL applier errors or slowness, replica lag, I/O thread state, disk space, and source connectivity. Never delete relay logs manually to free disk space; doing so can corrupt replication state. Fix the root cause preventing the replica from applying logs, then let replication manage purging automatically.

## 9. Redo, Undo, and Temporary Files Are Not Text Logs

Redo logs and undo tablespaces are internal InnoDB components. They are not rotated with `logrotate` or `FLUSH SLOW LOGS`.

On MySQL 8.0.30 and later, `innodb_redo_log_capacity` manages target redo log capacity:

```sql
SHOW VARIABLES LIKE 'innodb_redo_log_capacity';
```

In older versions, redo configuration may involve `innodb_log_file_size` and the number of log files. Never modify or delete redo files directly while the server is running. Growing undo history can relate to long transactions or slow purge; inspect transactions and InnoDB status rather than deleting undo files.

`tmpdir` must also be monitored. Sorts, joins, internal temporary tables, or large queries can create temporary files. If this volume fills up, queries can fail even if binlog and error log volumes still have space.

## 10. Designing a Retention Policy

Retention should match usage goals rather than choosing the same number of days for every log:

| Log | Reference Policy | Conditions to Verify |
| --- | --- | --- |
| Error log | Retain 14–30 days or ship to centralized logging per operational requirements. | Sufficient history to investigate crashes and recurring incidents; no logs lost before agent collection. |
| General log | Off by default; when enabled, keep only for short investigation windows. | Approved, sensitive data controlled, and disk usage bounded. |
| Slow query log | Retain 7–30 days or ship to an analytics system. | Enough data to identify trends; throttled when logging queries without indexes. |
| Binary log | Based on replica and PITR needs, e.g., 7–30 days or longer. | All replicas received needed logs; backups record matching binlog/GTID positions. |
| Relay log | Let MySQL auto-purge after applying. | Replication threads healthy with no unresolved errors needing investigation. |
| Audit log | Per organizational security/compliance policy. | Access permissions, integrity, storage location, and retention period approved. |

The day ranges above are starting points for discussion. Systems with different compliance, security investigation, or RPO/RTO requirements must define custom retention. Centralized logs also need retention policies and capacity alerts; shipping logs off the MySQL host does not eliminate lifecycle management.

### Estimating Required Capacity

Basic estimate for a log type:

\[
\text{Expected capacity} =
\text{daily log generation} \times
\text{retention days} \times
\text{safety factor}
\]

For example, if binlogs average 18 GB/day, need 7 days of retention, and use a 1.3 safety factor:

\[
18 \times 7 \times 1.3 = 163.8\ \text{GB}
\]

This is the projected space for binlogs alone, excluding data files, redo, relay logs, temporary files, backups, or long-term growth. Use daily peak figures rather than averages alone; month-end workloads or batch ETL can generate significantly more logs.

## 11. Disk-Full Alerting: Tracking Percentage, Bytes, and Growth Rate

Alerting solely on free percentage is insufficient. A 10 GB volume with 20% free has only 2 GB left; a 10 TB volume with 5% free still has 500 GB. Monitor simultaneously:

- Free space percentage.
- Absolute free bytes/GB.
- Hourly/daily disk growth rate.
- Estimated time to exhaustion.
- Free inodes on Linux if logs create many small files.
- Space per directory/log type and volumes holding `datadir`/`tmpdir`.

Illustrative thresholds, to be calibrated to write rate and expansion speed:

| Severity | Example Condition | Action |
| --- | --- | --- |
| Warning | Free space under 25% or projected full within 7 days. | Review growth rate, retention, and capacity expansion plan. |
| High | Free space under 15% or projected full within 72 hours. | Open early incident ticket, identify fast-growing logs/files, check replicas and backups. |
| Critical | Free space under 8% or projected full within 24 hours. | Page on-call, throttle/pause non-essential workloads, and free space via safe procedures. |

Percentage thresholds are examples only. On small filesystems, add absolute byte thresholds; when logs grow very rapidly, time-to-exhaustion alerts must fire before percentage thresholds.

### Checking Space on Linux

```bash
df -h
df -i
du -sh /var/log/mysql/*
du -sh /var/lib/mysql/*
```

`df -h` shows filesystem space; `df -i` shows inodes; `du` finds large directories/files. Ensure appropriate read permissions and avoid running `du` scans too frequently on very large volumes.

### Checking on Windows

```powershell
Get-Volume | Select-Object DriveLetter, FileSystemLabel, Size, SizeRemaining
```

Cross-check the drives holding `datadir`, log directories, and `tmpdir`. If MySQL runs in a container or mounted volume, check both the filesystem inside the container and the storage host.

## 12. Monitoring Logs via SQL and System Monitoring

A query to check binlog configuration and sizes:

```sql
SHOW BINARY LOGS;
```

Monitor replication status on a replica:

```sql
SHOW REPLICA STATUS\G
```

Fields such as `Replica_IO_Running`, `Replica_SQL_Running`, `Seconds_Behind_Source`, source positions, and relay logs help assess progress. `Seconds_Behind_Source` can be `NULL` when the replica is stopped or lag cannot be determined; read it together with thread status and recent errors.

Check the slow query counter:

```sql
SHOW GLOBAL STATUS LIKE 'Slow_queries';
```

This is a cumulative counter since server startup or status reset; compute deltas over time to observe trends. It does not replace analyzing slow log contents.

An operational dashboard should include:

1. Free space and inodes across every relevant filesystem.
2. Size and growth rate of error/general/slow/binlog/relay logs.
3. Current binlog count, latest file size, and remaining retention.
4. Replication lag, I/O/SQL applier state, and replication errors.
5. Latest log rotation status and count of un-compressed/un-cleaned old files.
6. Projected time to exhaustion based on recent and peak growth rates.
7. Backup/PITR status confirming which old binlogs are safe to purge.

Configure alerts in a monitoring system external to MySQL. If the filesystem holding logs fills up, do not depend on MySQL writing one more error line to alert you; the host monitoring agent must detect it independently.

## 13. Handling Nearly Full or Full Filesystems

When an alert fires, prioritize keeping MySQL operational and preserving recoverability:

1. Identify which filesystem is nearly full: `datadir`, logs, redo, relay, `tmpdir`, or backup volume.
2. Identify fast-growing files using OS tools and cross-check MySQL variables to see which files are actively used by the server.
3. If the general log was left enabled unexpectedly, disable it after confirming collection is no longer needed.
4. Rotate and compress error/slow/general logs using the proper reopen workflow; move archived copies to other storage if retention requires them.
5. For binlogs, verify replicas and backups/PITR before running `PURGE BINARY LOGS`; never delete files directly.
6. For relay logs, resolve replica errors/lag and let MySQL purge automatically after applying.
7. If temporary files grew, identify the queries/jobs generating them; throttle or pause non-essential workloads.
8. Expand the volume or relocate logs to monitored storage if projected capacity remains insufficient.
9. After freeing sufficient space, verify the error log, MySQL status, replication, backups, and business data.

Never delete `ibdata1`, redo logs, undo tablespaces, binlogs, or relay logs via filesystem operations to fix a full disk. Never delete a log file currently held open by the process without executing the reopen procedure. If the data volume is completely full, prioritize stopping/throttling non-essential write workloads and escalate to DBA/on-call following the runbook rather than blindly running purge commands.

## 14. Example Configuration Policy and Operational Schedule

An illustrative starting configuration in a MySQL config file:

```ini
[mysqld]
log_error_verbosity=2
slow_query_log=ON
long_query_time=1
min_examined_row_limit=100
general_log=OFF
log_output=FILE
binlog_expire_logs_seconds=1209600
```

Values must be tuned to version, workload, security requirements, and PITR needs. Never copy configuration to production without verifying file paths, permissions, disk capacity, and write impact.

Reference operational schedule:

| Frequency | Task |
| --- | --- |
| Continuous | Alert on free disk space, inodes, log growth rate, time to exhaustion, and replication lag. |
| Daily | Check abnormal binlog/relay log growth, unintended general log activation, and rotation errors. |
| Weekly | Review slow logs/digests, verify retention, size per log type, and PITR readiness. |
| Monthly | Rehearse backup + binlog recovery, audit retention periods, log access permissions, and capacity forecasts. |
| On change | Re-evaluate retention, filesystems, volumes, replication topology, and log configuration. |

Every retention change must record the reason, timestamp, approver, affected replicas/backups, and rollback method. Log policy is part of RPO/RTO and incident response, not merely file housekeeping.

## 15. Common Operational Mistakes

- **Deleting old binlogs based solely on file age.** Can prevent offline replicas from catching up or break PITR.
- **Using logrotate yet forgetting to reopen the log.** MySQL keeps writing to the renamed file or old handle, leaving the new file empty.
- **Using `copytruncate` without understanding the risk.** Can lose or duplicate lines in the window between copy and truncate.
- **Leaving the general log enabled continuously.** Generates heavy I/O and disk usage while capturing sensitive data.
- **Enabling `log_queries_not_using_indexes` without throttling.** Can produce massive logs from small table scans or high-frequency queries.
- **Confusing `FLUSH LOGS` with purging.** Flush mainly closes/reopens log files; it does not delete old logs and can rotate a new binlog.
- **Deleting relay logs manually.** Can corrupt replication state; let the replica manage purging automatically.
- **Treating redo/undo like text logs.** These are internal InnoDB structures and must never be rotated with logrotate.
- **Alerting solely on disk percentage.** Can miss small volumes nearing exhaustion or sudden growth spikes.
- **Never testing PITR.** Binlog retention is meaningless if backup/restore and log replay have never been rehearsed.

## 16. Self-Check Exercises

1. Distinguish the error log, general log, slow query log, and binary log by purpose.
2. Why should the general log typically be enabled only during active investigations?
3. Which log types does `log_output` affect, and which does it not affect?
4. Describe the rename, create, and reopen steps when rotating the error log.
5. Why can `copytruncate` lose log entries?
6. What requirements must guide the choice of `binlog_expire_logs_seconds`?
7. Before running `PURGE BINARY LOGS`, which replicas and backups must be checked?
8. Why must you never delete relay logs or redo/undo files via filesystem operations?
9. Design a disk-full alert combining free percentage, free bytes, inodes, and time to exhaustion.
10. When the data directory filesystem is full, outline the order of operations to protect data and replication.

A sound log policy connects **logging purpose → storage location → generation rate → rotation → retention → purge conditions → capacity alerting → recovery verification**. When these steps are defined and rehearsed, logs support both diagnostics and recovery without becoming the cause of a MySQL outage.
