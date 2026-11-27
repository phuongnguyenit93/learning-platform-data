# Log Rotation and Protecting Log Storage Capacity in PostgreSQL

PostgreSQL generates logs to record errors, warnings, connection activity, slow statements, checkpoints, vacuum activity, lock waits, and recovery events. Logs are an essential data source when investigating incidents and evaluating performance, yet logs can grow rapidly during heavy workloads or overly verbose logging configurations. If the log filesystem fills up, monitoring loses visibility; if logs share a filesystem with data or WAL, log volume can directly compete with database files and disrupt service.

Log administration must solve three things simultaneously: generating sufficiently useful logs, rotating files in a controlled manner, and keeping storage within predictable bounds. PostgreSQL provides a logging collector with time- and size-based rotation; the system can also send logs to syslog, Windows Event Log, or journald so an external platform manages lifecycle. Rotation only creates a new file. It does not delete old logs on its own and does not replace retention, archival, monitoring, or capacity planning.

~~~text
                 PostgreSQL server
                       |
                log messages
                       |
             +---------+----------+
             |                    |
             v                    v
       logging_collector      syslog / eventlog
             |                    |
             v                    v
       log_directory          OS log service
             |                    |
       +-----+------+        rotation / retention
       |            |
       v            v
   time rotation  size rotation
       |            |
       +------+-----+
              |
              v
       current_logfiles
              |
              v
       log shipper / archive
              |
       +------+--------+
       |               |
       v               v
  Central storage   Retention policy
       |
       v
  Monitoring / alert
       |
       v
  Operator response
~~~

This lesson belongs to the **Administration** chapter of the *Database Engine Relational PostgreSQL* module, focusing on log rotation and protecting log storage capacity in operational environments.

## 1. Learning Objectives

After this lesson, you can:

1. Explain the role of PostgreSQL's logging collector and log destinations.
2. Distinguish between `stderr`, `csvlog`, `jsonlog`, `syslog`, and Windows Event Log.
3. Understand the relationship between `logging_collector`, `log_directory`, and `log_filename`.
4. Configure time-based and size-based rotation.
5. Explain the exact effect and limits of `log_truncate_on_rotation`.
6. Use `pg_rotate_logfile()` or `pg_ctl logrotate` to request rotation.
7. Distinguish between rotation, retention, compression, and archival.
8. Understand why rotation alone does not cap total log storage.
9. Design filenames to avoid overwrites and collisions.
10. Use `current_logfiles` to identify active log files.
11. Choose between built-in rotation and `syslog`/`journald`.
12. Avoid conflicts between the logging collector and external `logrotate`.
13. Estimate log volume and retention capacity.
14. Separate the log filesystem from data/WAL when appropriate.
15. Monitor disk space, inodes, growth rates, and time remaining.
16. Tune `log_min_duration_statement` and `log_statement`.
17. Control logging of connections, checkpoints, autovacuum, lock waits, and temporary files.
18. Keep logs detailed enough for investigation without capturing excessive sensitive data.
19. Implement log shipping, compression, archival, and safe cleanup.
20. Handle full log filesystems, collector errors, and lost logs.
21. Build retention policies by environment and audit requirements.
22. Design log dashboards, alerts, and operational runbooks.

## 2. Why Must Logs Be Managed?

Logs are both an investigative tool and a continuous consumer of storage.

### 2.1. Error Investigation

Error messages, SQLSTATEs, context, application names, and timestamps help identify incidents, affected connections, and when errors began.

### 2.2. Performance Investigation

Slow query logs, lock waits, checkpoint logs, autovacuum logs, and temporary file logs help pinpoint causes of slow queries or rising resource usage.

### 2.3. Auditing and Operations

Some systems must retain logs for audits, incident reviews, or internal retention requirements. Retention must align with organizational policy.

### 2.4. Continuous Log Growth

If PostgreSQL writes an average of 2 MB/s, the system can generate roughly 172.8 GB per day in decimal units. Even a few days can consume most of a filesystem.

### 2.5. Logs Can Impact the Database

If logs and `PGDATA` or `pg_wal` share a filesystem, a sudden log surge can starve database writes, WAL, temporary files, or checkpoints of disk space.

### 2.6. Logging Too Little Is Also Dangerous

Disabling nearly all logging cripples investigation capability. The goal is choosing the right events, thresholds, and retention periods rather than logging everything or nothing.

## 3. Logging Architecture in PostgreSQL

PostgreSQL can write logs across multiple destinations.

| Destination | Characteristics | Lifecycle Management System |
| --- | --- | --- |
| stderr | Text-formatted logs | `logging_collector` or service manager |
| csvlog | CSV lines with structured fields | `logging_collector` |
| jsonlog | Structured JSON lines, version-dependent | `logging_collector` |
| syslog | Sent to syslog on supported OSes | syslog daemon |
| eventlog | Windows Event Log | Windows Event Log service |

### 3.1. stderr

This is the common default destination. With the logging collector enabled, PostgreSQL captures `stderr` and writes it to files in `log_directory`. With the collector disabled, `stderr` goes to whatever launched the server, such as `systemd` or a container runtime.

### 3.2. csvlog

`csvlog` writes logs as CSV rows with structured fields such as timestamp, user, database, process ID, severity, SQLSTATE, message, detail, query, and application name. Exact fields depend on PostgreSQL version.

### 3.3. jsonlog

Versions supporting `jsonlog` can emit logs as JSON for easier parsing by log pipelines. Check your PostgreSQL version before using it; older installations may lack this destination.

### 3.4. syslog

On supported operating systems, PostgreSQL can send logs to `syslog`. The syslog daemon handles receiving, routing, rotating, and retaining logs per OS configuration.

### 3.5. Windows Event Log

On Windows, PostgreSQL can write to the Event Log. The Windows service and Event Log policies manage storage, retention, and export.

### 3.6. Multiple Destinations

Multiple destinations can be enabled simultaneously, such as `stderr` and `csvlog`. This can create multiple physical copies of the same event and increase storage and ingestion volume. Enable multiple destinations only when clearly justified.

## 4. logging_collector

`logging_collector` is a background process that captures messages sent to `stderr` and writes them into log files.

### 4.1. Enabling the Collector

~~~conf
logging_collector = on
~~~

This parameter generally requires a PostgreSQL restart to take effect. A configuration reload cannot start the collector if the server started with it disabled.

### 4.2. When the Collector Is Enabled

PostgreSQL creates log files in `log_directory` according to `log_filename` and rotation settings. The collector manages file descriptors and switches files when rotation conditions are met.

### 4.3. When the Collector Is Disabled

`stderr` may be captured by `systemd`, a container runtime, or a service manager. Rotation and retention then depend on that external system.

### 4.4. Built-In Rotation Does Not Apply to syslog

Parameters `log_rotation_age`, `log_rotation_size`, and `log_truncate_on_rotation` apply to log files managed by the logging collector. `syslog`, `journald`, and Event Log have their own mechanisms.

### 4.5. Checking Status

~~~sql
SHOW logging_collector;
SHOW log_destination;
~~~

### 4.6. Collector and Availability

If the collector cannot open a log file, PostgreSQL may report errors and fall back to sending some messages to `stderr` depending on the situation and version. Do not rely on this fallback as a capacity policy. Monitor the filesystem and collector logs.

### 4.7. Service Managers

When the collector is disabled, confirm whether the service manager retains logs, bounds retention, and exports them per policy. Changing the logging destination changes where operators must look.

## 5. log_directory and log_filename

These two parameters determine the location and names of log files created by the collector.

### 5.1. log_directory

~~~conf
log_directory = 'log'
~~~

Relative paths are resolved relative to the data directory. An absolute path can place logs on a separate filesystem.

### 5.2. Absolute Paths

Example:

~~~conf
log_directory = '/var/log/postgresql'
~~~

Ensure the OS account running PostgreSQL has permission to create and write files in the directory. If using a separate directory, configure the mount and ownership before restarting.

### 5.3. log_filename

A common default name takes the form `postgresql-%Y-%m-%d_%H%M%S.log`. `strftime` escapes can embed date and time into filenames.

~~~conf
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
~~~

### 5.4. Useful Escapes

| Escape | Common Meaning |
| --- | --- |
| %Y | Four-digit year |
| %m | Month |
| %d | Day of month |
| %H | Hour 00–23 |
| %M | Minute |
| %S | Second |
| %a | Abbreviated weekday name |
| %A | Full weekday name |
| %j | Day of the year |

Formatting follows the platform's `strftime` behavior. Check timezone and actual naming on your operating system.

### 5.5. Avoiding Static Filenames

If `log_filename` is simply `postgresql.log`, repeated rotations can reopen the same filename. You must understand exact append/truncate behavior and avoid unintended data loss.

### 5.6. Timestamped Names

Including date/time in filenames creates distinct files and simplifies archiving. If size rotation triggers multiple times within the same second, or if the pattern has coarse resolution, filenames can collide and the collector may keep appending to the existing file.

### 5.7. CSV and JSON Suffixes

When `csvlog` or `jsonlog` is enabled, the collector creates corresponding files with format-specific extensions such as `.csv` or `.json`. Check actual files and `current_logfiles` rather than guessing names.

### 5.8. log_file_mode

~~~conf
log_file_mode = 0600
~~~

File permissions should be tightly restricted because logs can contain SQL, usernames, client addresses, and sensitive details. Some OS/group sharing setups may use different permissions, which must be explicitly approved.

## 6. Time-Based Rotation: log_rotation_age

`log_rotation_age` specifies the maximum lifetime of an individual log file before the collector switches to a new file.

~~~conf
log_rotation_age = 1d
~~~

### 6.1. Units

Configured as a time interval. Units such as seconds, minutes, hours, or days can be specified using PostgreSQL configuration syntax.

### 6.2. Zero Value

Set `log_rotation_age = 0` to disable time-based rotation.

### 6.3. Rotation Does Not Necessarily Occur at the Exact Expiration Second

The collector checks conditions when a log message needs to be written. If the system is quiet, the file may only switch when the next message arrives.

### 6.4. Purpose

Time rotation produces hourly or daily files, breaking logs into chunks and simplifying archival and retention.

### 6.5. Daily Rotation

With `log_rotation_age = 1d`, the collector creates a new file roughly every day of use. This is an interval, not a guarantee that files always open right at midnight in a given timezone.

### 6.6. Time Rotation and Naming

If `log_filename` includes the date, files naturally get distinct names across days. If names repeat by weekday or month, `log_truncate_on_rotation` may affect older files with the same name.

### 6.7. Not Retention

`log_rotation_age` does not delete old files. After 90 days, without cleanup/retention, the server can still hold all 90 days of logs.

## 7. Size-Based Rotation: log_rotation_size

`log_rotation_size` sets a file size threshold before the collector switches to a new log file.

~~~conf
log_rotation_size = 102400
~~~

The value above is 102400 KB, approximately 100 MiB.

### 7.1. Units

The base unit is kilobytes. Check your running version's units and syntax when specifying suffixes.

### 7.2. Zero Value

Set `log_rotation_size = 0` to disable size-based rotation.

### 7.3. Threshold Is Not a Strict Hard Cap

Rotation is checked when new messages arrive. A huge log message or rapid burst of writes can push the file past the threshold before switching.

### 7.4. Size Rotation Helps Under Variable Workloads

A database might log very little overnight yet log heavily during a batch job or incident. Size rotation splits files based on actual log output.

### 7.5. Combining Age and Size

Both conditions can be enabled together. The collector switches files whenever either rotation condition is met. This caps file size during high-volume periods and splits files by time during quiet periods.

### 7.6. Do Not Infer Total Capacity from One Threshold

100 MiB per file does not mean total logs only use 100 MiB. If 40 files are produced, total usage can exceed 4 GiB.

## 8. log_truncate_on_rotation

`log_truncate_on_rotation` controls whether an existing file with the same name is truncated when opening a new file under specific rotation conditions.

~~~conf
log_truncate_on_rotation = off
~~~

### 8.1. Safe Default

Keep it `off` to avoid wiping out an older file's contents when a filename is reused.

### 8.2. Only Applies to Time-Based Rotation

This parameter only truncates an existing same-named file when rotation is triggered by time and the collector reopens an already-existing filename. It does not apply to size-based rotation.

### 8.3. Does Not Act as Log Cleanup on Restart

Restarting PostgreSQL and reopening a file is not a time-based rotation. Never rely on `log_truncate_on_rotation` to clear old logs on every restart.

### 8.4. Repeating Filenames

Example filename by day of week:

~~~conf
log_filename = 'postgresql-%a.log'
log_rotation_age = 1d
log_truncate_on_rotation = on
~~~

When a weekday's filename is reused the following week, old contents may be truncated under time-based rotation rules. This is only suitable when retention is handled separately and overwriting is explicitly accepted.

### 8.5. Do Not Enable Arbitrarily

If filenames have coarse resolution or repeat, enabling truncation can destroy history operators assumed was still preserved.

### 8.6. Does Not Replace Retention

Truncation does not establish an explicit retention policy. It only governs reopening a colliding filename under specific conditions.

## 9. Sample Rotation Configuration

Example configuration for the logging collector writing `stderr` and CSV:

~~~conf
# Restart required when changing logging_collector from off to on
logging_collector = on

log_destination = 'stderr,csvlog'
log_directory = '/var/log/postgresql'
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
log_file_mode = 0600

# Rotate when either age or size is reached
log_rotation_age = 1d
log_rotation_size = 102400
log_truncate_on_rotation = off
~~~

### 9.1. Choosing the Filesystem

The path `/var/log/postgresql` is illustrative. Before using it, create the directory, mount the filesystem, set owner/group, and verify write permissions.

### 9.2. Filenames

Timestamped names simplify archiving. With `csvlog`, inspect the corresponding `.csv` files as well.

### 9.3. Rotation Policy

One day or 100 MiB is an initial example, not a universal standard. Pick values based on log volume, ingestion pipelines, and file size limits of processing tools.

### 9.4. Reload and Restart

`logging_collector` requires a restart when changed. Other log rotation and destination parameters may reload depending on version. Check `pg_settings.context` and `pg_settings.pending_restart` to be sure.

~~~sql
SELECT name, setting, unit, context, pending_restart
FROM pg_settings
WHERE name IN (
    'logging_collector',
    'log_destination',
    'log_directory',
    'log_filename',
    'log_rotation_age',
    'log_rotation_size',
    'log_truncate_on_rotation'
)
ORDER BY name;
~~~

### 9.5. Post-Change Verification

After restarting or reloading, inspect PostgreSQL logs, `current_logfiles`, and the filesystem to confirm the collector opened the expected files.

## 10. Requesting Manual Rotation

You can ask PostgreSQL to switch to a new log file immediately without waiting for rotation thresholds.

### 10.1. SQL Function

~~~sql
SELECT pg_rotate_logfile();
~~~

This function signals the logging collector to rotate the log. It only works when the logging collector is active; the boolean result indicates whether the request was sent successfully.

### 10.2. Privileges

Calling this function may require administrative privileges or explicit `EXECUTE` grants. Do not grant broad rights merely to let any user rotate logs.

### 10.3. pg_ctl logrotate

On supported versions:

~~~bash
pg_ctl -D /var/lib/postgresql/data logrotate
~~~

This command requests the server to rotate its log file. Exact syntax depends on your `pg_ctl` version.

### 10.4. SIGHUP Differs from Rotation

Reloading configuration via `SIGHUP`/`pg_ctl reload` does not always open a new log file. Use the rotation function or command for that purpose.

### 10.5. When to Rotate Manually?

- Before archiving or moving a log file.
- After changing `log_filename` or `log_directory`.
- Before controlled cleanup.
- When separating logs around an incident or maintenance window.

### 10.6. Do Not Call Continuously

Rotating too frequently creates many tiny files, raising file counts and ingestion overhead. Rely on age/size policies as the primary mechanism.

## 11. current_logfiles

When the logging collector is active, PostgreSQL maintains a `current_logfiles` file in the data directory recording the paths of log files currently in use for each destination.

### 11.1. Purpose

Log shippers can read `current_logfiles` to identify the active file rather than guessing with globs or picking the newest file by timestamp.

### 11.2. Contents

The file lists destination and path—such as `stderr` or `csvlog` paired with the current log file path. Exact formatting depends on version.

### 11.3. Updated on Rotation

When the collector switches files, `current_logfiles` is updated to point to the new file. Consumers must re-read it and continue tailing the updated path.

### 11.4. Not a Log Index

`current_logfiles` does not list full log history. It only points to currently active files.

### 11.5. Do Not Use as a Retention Inventory

To know total file counts and historical storage usage, you need filesystem inventories or log storage backend metrics.

### 11.6. The File May Be Absent

If the logging collector is off or the destination is not file-based, this file may not exist. Do not assume a missing file always means PostgreSQL is broken.

## 12. Built-In Rotation vs. External logrotate

Distinguish log files owned by PostgreSQL's logging collector from log files managed by `syslog` or a service manager.

### 12.1. Collector-Owned Files

When `logging_collector` is on and writing files, PostgreSQL holds the file descriptors and manages rotation itself. Use `log_rotation_age`, `log_rotation_size`, or `pg_rotate_logfile()`.

### 12.2. External logrotate on Open Files

If an external utility renames or deletes a file while PostgreSQL still holds the file descriptor, the process can keep writing to the renamed or unlinked inode. Operators may think the new file is receiving logs while PostgreSQL is still writing to the old inode.

### 12.3. copytruncate

`copytruncate` copies contents and then truncates the file in place. In the window between copy and truncate, log messages can be lost or duplicated. It is also not a good default choice for collector-managed files.

### 12.4. Recommendation

Prefer built-in rotation for collector-owned files. Use external `logrotate` for files created by a syslog daemon or service manager, following that system's guidelines.

### 12.5. Cleanup Differs from Rotation

A retention script can delete closed, expired log files, provided it accurately accounts for active files, archive status, and race conditions. Never delete files merely because their timestamps look old.

### 12.6. Log Shippers

Filebeat, Fluent Bit, Vector, or similar agents can tail log files. Configure them to handle renames, rotation, inode reuse, and `current_logfiles` so records are never missed.

## 13. Syslog, journald, and Windows Event Log

When not using logging collector file output, rotation and retention are managed by the receiving system.

### 13.1. Syslog

PostgreSQL sends messages to the syslog daemon. Syslog can route by facility/severity to local files or remote destinations.

### 13.2. syslog_facility

Configuring a facility helps separate PostgreSQL logs from other services. Pick a dedicated facility so policies and filters stay clean.

### 13.3. syslog_ident

Set an identifier to recognize PostgreSQL in syslog. Avoid identifiers that collide with other applications.

### 13.4. journald

On systemd systems, service stdout/stderr can be captured by `journald`. `journald` enforces its own disk limits, retention, and vacuum policies.

### 13.5. journalctl

PostgreSQL logs can be queried via `journalctl` by service/unit. Unit names depend on the package and service setup.

~~~bash
journalctl -u postgresql --since "1 hour ago"
~~~

### 13.6. Journal Size Limits

Settings such as `SystemMaxUse`, `SystemKeepFree`, `SystemMaxFileSize`, and `RuntimeMaxUse` govern journal disk usage. Verify parameter names and semantics against your `systemd` version.

### 13.7. Windows Event Log

On Windows, configure `log_destination` appropriately and manage retention and exports via Event Viewer / Windows Event Log policies. PostgreSQL file rotation settings do not apply to the Event Log.

### 13.8. Remote Syslog

Sending logs to a central server reduces reliance on local disk and preserves logs if the host fails. However, it requires network resilience, buffering, encryption, and collector capacity.

## 14. Rotation, Retention, Compression, and Archival

These four concepts solve distinct problems.

| Operation | Goal | Deletes Old Logs? |
| --- | --- | --- |
| Rotation | Split the active file into a new file | No |
| Retention | Keep logs for a defined duration or count | Potentially |
| Compression | Reduce size of closed files | Does not delete on its own |
| Archival | Copy logs to long-term/central storage | Not necessarily |

### 14.1. Rotation

Creates a new file for ongoing writes. The old file remains on disk.

### 14.2. Retention

For example, keep 7 days locally, 90 days in central storage, and 1 year in cold archive. Actual periods must follow legal, audit, and internal policies.

### 14.3. Compression

Compress closed files to save storage. Never compress a file currently being written by PostgreSQL or read by a shipper unless the pipeline explicitly supports it.

### 14.4. Archival

Copy or ship logs to object storage, a log platform, or a backup repository. Verify upload completion and checksums before deleting local copies if required by policy.

### 14.5. Lifecycle

Remote storage can apply lifecycle rules to transition data to cheaper tiers or expire it after retention. Ensure rules respect legal holds and ongoing incident investigations.

### 14.6. Rotation Does Not Cap Total Log Volume

If you generate 10 GB per day and retain logs indefinitely, rotation simply produces many 10 GB files; total usage still grows without bound.

## 15. Capacity Planning for Logs

Capacity estimates must account for actual rates and peak behavior.

### 15.1. Measuring Log Rate

Measure bytes produced over a representative window, such as an hour or a full workday. Include peak hours, batch jobs, and maintenance.

### 15.2. Basic Formula

If the average log rate is $R$ bytes/second and local retention is $D$ days:

\[
S_{\text{raw}} = R \times 86400 \times D
\]

### 15.3. Example

At an average of 500 KB/s retained for 7 days:

\[
500 \times 1024 \times 86400 \times 7
\approx 309.4\ \text{GB}
\]

This is an approximate decimal capacity before compression, metadata, and headroom.

### 15.4. Peak Factor

Apply a peak factor for batch jobs and incidents. If peak volume is 3x baseline, your capacity plan must handle sustained bursts rather than averages alone.

### 15.5. Compression Ratio

Never assume compression always achieves a fixed ratio. SQL text, JSON, repeated prefixes, and CSV often compress well, but measure on real data.

### 15.6. Headroom

Never allocate 100% of a filesystem to logs. Reserve free space for active open files, rotation, temporary archive copies, log shipper buffers, and OS operations.

### 15.7. Inodes and File Counts

Many small files can exhaust inodes even while free bytes remain. Monitor file counts and inode usage too.

### 15.8. Storage Isolation

Putting logs on a separate filesystem protects `PGDATA` and WAL from log surges. However, a separate mount still needs monitoring, backups, and capacity planning; if that mount fails or fills, the logging pipeline is affected.

### 15.9. Avoid Sharing One Filesystem for Everything Under High Risk

Data files, WAL, temporary files, and logs have distinct growth patterns. Separating volumes limits blast radius, though you should avoid creating too many tiny, hard-to-manage mounts.

## 16. Monitoring Filesystem Capacity

PostgreSQL statistics views do not expose full log filesystem capacity. Combine them with OS monitoring.

### 16.1. Linux df

~~~bash
df -h /var/log/postgresql
df -i /var/log/postgresql
~~~

### 16.2. Checking File Sizes

~~~bash
du -sh /var/log/postgresql
du -ah /var/log/postgresql | sort -h | tail -20
~~~

### 16.3. Windows

Use `Get-Volume` or OS monitoring tools to check free space and log directory size.

### 16.4. Node Exporter

Collect filesystem free bytes, available bytes, total size, and inode metrics. Alert per dedicated mountpoint for the log volume.

### 16.5. Growth Rate

Measure hourly/daily growth to estimate time-to-full:

\[
T_{\text{full}} =
\frac{\text{free bytes}}
{\text{bytes generated per second}}
\]

This formula is an estimate; use peak rates and reserve margins when designing alerts.

### 16.6. Monitoring Log File Count

Abnormally rising file counts can indicate overly small rotation thresholds, naming collisions, or failed cleanup jobs.

### 16.7. Alert Thresholds

For example, warn at 75%, alert critical at 90%, or alert when time-to-full drops below response lead time. Tune based on volume size, growth rate, and expansion capability.

## 17. Controlling Log Volume with Logging Parameters

Rotation only splits files. To control growth rate, choose which events get logged.

### 17.1. log_min_messages

Controls the minimum message severity logged. Changing log levels can affect both error reporting and diagnostic visibility; never raise the threshold blindly.

### 17.2. log_min_error_statement

Determines the minimum severity at which offending statements are logged. Balance investigative needs with privacy.

### 17.3. log_statement

Common values:
- `none`: do not log statements via this mechanism.
- `ddl`: log DDL statements.
- `mod`: log DDL and data-modifying statements.
- `all`: log all statements.

Enabling `all` can generate massive log volume and capture sensitive payloads.

### 17.4. log_min_duration_statement

Logs completed statements whose duration meets or exceeds the threshold. Example:

~~~conf
log_min_duration_statement = 500ms
~~~

This is a duration threshold, unlike planner cost. Setting `-1` disables it; `0` logs all statement durations per parameter semantics.

### 17.5. log_duration

Logs statement durations. Combined with `log_min_duration_statement` or statement logging, this can produce duplicate information. Understand output and volume before enabling.

### 17.6. Sampling

Some versions support `log_min_duration_sample` and `log_statement_sample_rate` to sample slow queries. Use sampling to observe high-volume workloads without logging every qualifying query.

### 17.7. log_connections and log_disconnections

Log connection and disconnection events. Useful for investigating connection churn, though workloads with many short-lived connections can emit high line volumes.

### 17.8. log_checkpoints

Logs checkpoint details. Valuable for diagnosing I/O and WAL behavior, with volume tied to checkpoint frequency.

### 17.9. log_lock_waits

Logs lock waits exceeding `deadlock_timeout`. Useful for finding blocking contention, though volume increases during heavy contention.

### 17.10. log_temp_files

Logs temporary files larger than the threshold; `-1` disables it and `0` logs all temporary files. Pick a threshold suited to investigating sort and hash spills.

### 17.11. log_autovacuum_min_duration

Logs autovacuum actions running longer than the threshold. Useful for spotting slow vacuums or logging all autovacuum runs as configured.

### 17.12. auto_explain

The `auto_explain` extension can log execution plans for queries exceeding a threshold. Enabling analyze, buffers, or timing adds overhead and can substantially inflate log volume. Use appropriate sample rates, duration thresholds, and role/scope controls.

## 18. Practical Goal-Oriented Logging Configurations

### 18.1. Production Baseline

Example:

~~~conf
log_min_messages = warning
log_min_error_statement = error
log_min_duration_statement = 500ms
log_checkpoints = on
log_lock_waits = on
log_temp_files = 64MB
log_line_prefix = '%m [%p] %q%u@%d %r app=%a '
~~~

This is only a reference baseline. Adjust thresholds to match SLAs, workloads, and incident needs.

### 18.2. Short-Term Investigation

You can temporarily lower `log_min_duration_statement` or enable extra connection/statement logging for a controlled window. Record start/end times and a rollback plan.

### 18.3. Avoid Prolonged log_statement=all

Enable only with clear justification, volume estimates, and sensitive-data review. A chatty application can generate logs faster than database data growth itself.

### 18.4. Slow Query Logs and pg_stat_statements

Use slow query logs to see specific executions; use `pg_stat_statements` to aggregate workloads by query identity. These two tools complement each other and reduce the need to log every statement.

### 18.5. Useful Prefixes

`log_line_prefix` can include timestamp, PID, user, database, remote address, and `application_name` on every line. This aids correlation while slightly increasing size per record.

### 18.6. Sampling and Thresholds

Raise thresholds or lower sampling rates to control volume under massive workloads. Always ensure enough detail remains to investigate incidents.

## 19. Protecting Sensitive Data in Logs

Logs can contain SQL text, bind values, usernames, database names, client IPs, and error payloads.

### 19.1. Statement Logging

`log_statement` and `log_min_duration_statement` can record query text. Query text sometimes contains literal credentials, tokens, personal data, or business information.

### 19.2. Bind Parameters

On supported versions, `log_parameter_max_length` and `log_parameter_max_length_on_error` govern how much parameter data is logged. Verify your version's defaults and semantics before applying.

### 19.3. Passwords

Never embed raw passwords in SQL statements or connection strings. Use secret mechanisms and avoid leaking credentials into error messages.

### 19.4. File Permissions

Keep `log_file_mode` restrictive, ownership accurate, and read-group access tightly bounded.

### 19.5. Transport Encryption

Log shippers should transmit to central storage over TLS or an equivalent encrypted channel.

### 19.6. Access Control

Restrict log viewers by role. Do not grant raw SQL log access to everyone simply because they can view summary dashboards.

### 19.7. Retention and Privacy

Retain logs as long as required, while avoiding indefinite storage without justification. Execute deletion per policy and legal holds.

### 19.8. Redaction

Use application logging redaction or log pipeline filters when data must be masked. Test filters so they do not inadvertently strip SQLSTATEs, query context, or fields needed for troubleshooting.

## 20. Log Formats and Parsing

### 20.1. stderr Text

Plain text is easy for operators to read directly, though parsers must handle multiline messages and prefixes.

### 20.2. csvlog

CSV provides structured fields convenient for importing into analysis tools. Query text and details can contain commas, newlines, and quotes; use a standard CSV parser instead of naive string splitting.

### 20.3. jsonlog

JSON integrates cleanly with log platforms and structured search. Verify field schemas against your PostgreSQL version.

### 20.4. Multiline Entries

Error details, context, and statements can span multiple lines. Log shippers need proper multiline parsers.

### 20.5. Correlation

Use `log_line_prefix` and `application_name` to link logs with session and request traces. Session IDs, PIDs, and transaction IDs aid debugging but should not become high-cardinality metrics labels.

### 20.6. Timezone

Align `log_timezone` consistently with your log platform. Sync clocks via NTP/chrony so correlation across database, application, and OS logs remains accurate.

### 20.7. Timestamp Precision

Use timestamps with explicit timezone and appropriate precision. When parsing, never assume log timestamps are always UTC if the server is configured for local time.

## 21. Log Shipping and Central Storage

Log shipping stores logs off the database host, reducing the risk of losing logs if the host or volume fails.

### 21.1. Agents

Fluent Bit, Vector, Filebeat, or equivalent agents can tail files and forward logs.

### 21.2. current_logfiles

For collector-managed files, agents can read `current_logfiles` to locate the active file. Verify the agent handles renames, rotation, and file reopens properly.

### 21.3. Buffers

Agents often need buffering when the network or central storage is temporarily unavailable. Buffers also consume disk; cap their size and monitor backlogs.

### 21.4. Delivery Semantics

Some pipelines deliver at-least-once and create duplicates on retries. Use timestamps, host, instance, PID/session metadata, and event fields to deduplicate where needed.

### 21.5. Central Retention

Enforce retention on central storage per policy. Local retention can be shorter once central delivery is verified.

### 21.6. Archive Checksums

For long-term archives, generate checksums and record metadata covering cluster, instance, PostgreSQL version, time range, and log format.

### 21.7. Failure Behavior

Define what happens when the central endpoint disconnects: how long to buffer, when to drop, which alerts fire, and whether local disk has sufficient room.

## 22. Safe Compression and Cleanup

### 22.1. Compress Only Closed Files

Never compress or rename a file the PostgreSQL collector is actively writing. Use `current_logfiles` or pipeline state to identify active files.

### 22.2. Batch Compression

Compress rotated logs on a schedule, preferring streaming pipelines/central storage where suitable.

### 22.3. Verify Success

Delete source files only after compression/archival succeeds, output file size is sensible, and checksum/verification passes.

### 22.4. Retention Cleanup

Cleanup should check file age, archive status, and policy. Exclude active files and unshipped files before deleting.

### 22.5. Dry Runs

Before enabling deletion jobs, list the files targeted for removal and review them. Use dry-run mode if supported by the script or tool.

### 22.6. Avoid Broad Wildcard Deletions

Never run generic delete commands inside `/var/log` or `PGDATA`. Scope tightly to the exact directory, filename pattern, and file ownership of log files.

### 22.7. Race Conditions

A newly rotated file may still be read by the shipper. Retention must give shippers ample time to finish and never delete files still open or retrying.

### 22.8. Disk Emergencies

When a filesystem nears full, prioritize keeping the database running and the log pipeline recoverable. Identify active files, archive status, and cleanup candidates; never blindly delete current logs or WAL.

## 23. Separating Logs, Data, and WAL

### 23.1. Separate Log Filesystems

Placing `log_directory` on a dedicated volume prevents log bursts from exhausting space needed by `PGDATA` and `pg_wal`.

### 23.2. Independent Limits

Separate filesystems allow independent quotas, alerts, and capacity planning.

### 23.3. Mount Dependencies

Ensure the mount is present before PostgreSQL starts. If the mount is missing, the server could write into the mountpoint directory on the root filesystem, causing unexpected disk consumption.

### 23.4. Mount Validation

Service startup can use dependencies or preflight checks to verify the volume has the expected mount source and sufficient free space.

### 23.5. Do Not Place Logs on tmpfs Arbitrarily

Logs on volatile storage vanish on reboot and have tight memory caps. Use only with an explicit shipping and retention design.

### 23.6. PGDATA/WAL Safety

Never allow log cleanup scripts to traverse into `PGDATA`, `pg_wal`, or tablespace paths. Enforce path allowlists and canonical path checks.

## 24. Monitoring the Log Pipeline

Monitor both PostgreSQL logging and the log ingestion system.

| Metric | Meaning |
| --- | --- |
| Filesystem free bytes | Remaining disk space |
| Filesystem usage ratio | Percentage used |
| Inode free ratio | Capacity to create additional files |
| Log bytes generated | Log generation rate |
| Log file count | Current number of files |
| Oldest local log age | Age of oldest log still on disk |
| Archive success/failure | Archival status |
| Shipper backlog | Unshipped log volume |
| Dropped events | Logs lost in the pipeline |
| Collector errors | File write/open errors |
| Rotation count | Rotation frequency |
| Time to full | Estimated time until disk exhaustion |

### 24.1. Filesystem Metrics

Use `node_exporter` or an OS agent to monitor the log mount.

### 24.2. PostgreSQL Metrics

You can track logging settings, collector process health, and database workload, though actual file sizes generally require OS-level metrics.

### 24.3. Log Shipper Metrics

Monitor queue size, retries, output errors, dropped records, and processing lag.

### 24.4. Central Storage

Monitor ingest rate, indexing latency, retention capacity, and query availability on the log platform.

### 24.5. Alert Ownership

Every alert needs an owner: DBA, platform/infra, or observability team. Disk full and log shipping failures may belong to different teams.

## 25. Alerts and Capacity Thresholds

### 25.1. Disk Usage

Examples:
- Warning when the log filesystem exceeds 75%.
- Critical when it exceeds 90%.
- Emergency when free bytes drop below minimum reserve.

Actual thresholds must reflect growth rate and response time.

### 25.2. Time-to-Full

Alert if projected remaining capacity falls below the time required to expand the volume or mitigate a log burst.

### 25.3. Shipper Backlog

Alert when backlog exceeds tolerance windows or local buffers near capacity.

### 25.4. Archive Failures

Alert when archival/shipping fails repeatedly or the oldest unshipped log exceeds policy age.

### 25.5. No New Logs

If workload is active yet no logs or heartbeats appear for a prolonged period, inspect the collector and destination. Conversely, having no new logs on a genuinely idle system may be normal.

### 25.6. Rotation Failures

Watch for `current_logfiles` remaining unchanged past expected rotation, collector errors, or file sizes exceeding thresholds for too long.

### 25.7. Inode Pressure

Alert on inode usage separately, especially when size rotation creates huge numbers of small files.

## 26. Troubleshooting Common Issues

### Issue 1. Logs Do Not Appear in log_directory

Check `logging_collector`, `log_destination`, `log_directory`, file permissions, and startup logs. If the collector is off, logs may be going to `systemd` or container `stderr`.

### Issue 2. logging_collector Does Not Turn On After Reload

This parameter requires a restart. Check `pg_settings.context` and `pending_restart`, then restart per maintenance procedures.

### Issue 3. Log File Does Not Rotate by Time

Check `log_rotation_age`, collector state, filename, log destination, and whether any new log messages were emitted after the age threshold elapsed.

### Issue 4. File Does Not Rotate by Size

Check whether `log_rotation_size` is zero, actual file size, destination, and collector logs. Rotation is evaluated when a new log message arrives.

### Issue 5. Old File Gets Truncated

Check `log_truncate_on_rotation` and whether the filename pattern reuses names. Turn truncation off if history must be preserved.

### Issue 6. Total Storage Keeps Growing

Rotation does not delete files. Configure retention, compression, archival, and cleanup for closed logs.

### Issue 7. External logrotate Creates Empty Files

PostgreSQL may still be writing to the old file descriptor after rename/unlink. Use built-in rotation for collector-owned files and fix the logrotate architecture.

### Issue 8. current_logfiles Does Not Exist

Check `logging_collector` and file destinations. Do not expect this file when using `syslog` or `journald`.

### Issue 9. CSV Logs Do Not Appear

Check that `log_destination` includes `csvlog`, `logging_collector` is on, restart/reload was performed appropriately, and directory permissions allow writing.

### Issue 10. Disk Full

Inspect active files, log rate, shipper backlog, archive status, and filesystem usage. Perform controlled cleanup of closed/archived logs; never delete WAL or active logs recklessly.

### Issue 11. Log Shipper Drops Records

Check rotation handling, file identity/inode tracking, multiline parsers, buffer limits, and permissions.

### Issue 12. Sudden Log Volume Spike

Look for `log_statement`, `log_min_duration_statement`, `log_connections`, `log_disconnections`, `log_temp_files`, `auto_explain`, and application retry storms.

### Issue 13. Slow Queries Missing from Logs

Check `log_min_duration_statement`, sampling settings, role/database overrides, and timezone/time ranges.

### Issue 14. Logs Contain Sensitive Information

Tighten statement/parameter logging, restrict access, apply redaction, and review log retention.

### Issue 15. Rotation Produces Too Many Tiny Files

Increase `log_rotation_size` or `log_rotation_age`, improve filename patterns, and reduce log noise.

### Issue 16. Log Filesystem Not Mounted

Check mount dependencies, service startup ordering, mountpoint permissions, and alerts. Confirm PostgreSQL is not accidentally writing to the root filesystem.

### Issue 17. Syslog Logs Are Not Rotating

Check syslog daemon rules and external rotation policies; PostgreSQL `log_rotation_*` settings do not govern syslog-owned files.

### Issue 18. Journald Consumes Excessive Disk

Check `journald` retention/vacuum settings and persistent journal policies. Never delete journal files directly while the daemon manages them.

### Issue 19. Archival Succeeds Yet Local Disk Remains Full

Verify the retention cleanup job is running, archive verification status, and active-file exclusions. Archiving alone does not remove local files.

### Issue 20. Cannot Write Logs When Volume Goes Read-Only

Check filesystem state, kernel/storage errors, and mount status. Fix the underlying storage issue before altering PostgreSQL logging policies.

## 27. Runbook When the Log Filesystem Nears Full

1. Confirm the mountpoint and percentage of bytes and inodes used.
2. Check growth rate and estimate time-to-full.
3. Identify `log_directory`, active log files, and `current_logfiles`.
4. Check PostgreSQL collector errors and server logs.
5. Check log shipper backlog, archive failures, and central storage availability.
6. Find the cause of volume growth: statement logging, retry storm, connection churn, or error burst.
7. If needed, temporarily dial down logging verbosity with incident owner approval and record the timestamp.
8. Never disable logging entirely if error/security records are still required.
9. Rotate logs via PostgreSQL or the destination owner's mechanism.
10. Confirm old files are closed and the shipper finished reading them.
11. Archive/compress old logs per policy.
12. Delete only logs meeting retention and archive verification requirements.
13. Expand the volume or add capacity if needed.
14. Confirm `PGDATA` and `pg_wal` retain sufficient headroom.
15. Monitor filesystem usage and log rate afterward.
16. Record the incident timeline, freed capacity, and root cause.

## 28. Runbook for Adjusting Logging During an Incident

### 28.1. Define the Investigative Question

For example, determine whether you need to capture slow queries, lock waits, connection churn, or checkpoint stalls.

### 28.2. Pick the Minimal Parameter Set

Enable only relevant log categories. Avoid `log_statement=all` if a slow-query threshold or targeted diagnostics suffice.

### 28.3. Define a Time Window

Record the start time, how long the setting will stay active, and who is responsible for reverting it.

### 28.4. Estimate Volume

Based on current workload and log rate, calculate additional storage consumed during the investigation window.

### 28.5. Check Privacy

Assess whether query text, parameter values, credentials, or personal data could appear.

### 28.6. Revert

Once enough data is captured, restore baseline settings and verify using `SHOW` or `current_setting`.

### 28.7. Preserve Artifacts

Ship/archive incident-related logs with metadata and appropriate access controls.

## 29. Designing a Retention Policy

Retention should be classified by environment, log type, and purpose.

| Category | Example Policy Elements to Define |
| --- | --- |
| Local active logs | Keep enough buffer when central storage temporarily fails |
| Local rotated logs | Short-term retention bounded by volume capacity |
| Central searchable logs | Retain long enough for operations and incident investigation |
| Cold archive | Long-term retention per audit and legal policies |
| Debug/temporary logs | Short retention with explicit cleanup |
| Security/audit logs | Governed by dedicated policies and access controls |

### 29.1. Local Retention

Local storage needs enough buffer when shippers are interrupted. Never use local disk as an indefinite archive.

### 29.2. Central Retention

The central log platform keeps data searchable as long as needed, then transitions it to archival storage.

### 29.3. Legal Hold

If a legal hold or active investigation exists, ensure retention jobs do not delete preserved artifacts.

### 29.4. Retention by Severity

Some organizations retain error/security logs longer than debug or statement logs. Define this based on policy and classification capabilities.

### 29.5. Periodic Reviews

Regularly review log volumes, retention durations, compression ratios, central storage costs, and access patterns.

## 30. Checking Current Configuration with SQL

### 30.1. Viewing Logging Settings

~~~sql
SELECT name, setting, unit, context, source, pending_restart
FROM pg_settings
WHERE name LIKE 'log%'
   OR name = 'logging_collector'
ORDER BY name;
~~~

### 30.2. Checking Current Log Paths

Read `current_logfiles` on the filesystem when the collector is running. SQL does not replace verifying the actual file paths.

### 30.3. Checking Configuration Source

`pg_settings.source` shows where a setting originates—such as default, configuration file, command line, database/role, or session.

### 30.4. Checking Configuration File Errors

~~~sql
SELECT *
FROM pg_file_settings
WHERE error IS NOT NULL;
~~~

This view surfaces parsing/configuration errors in files read by the server; access depends on role privileges.

### 30.5. Checking Reload Time

~~~sql
SELECT pg_conf_load_time();
~~~

Config load time helps correlate recent changes. For parameters requiring a restart, check `pending_restart`.

## 31. Testing Rotation in a Lab Environment

### 31.1. Preparation

Use a dedicated PostgreSQL lab, enable `logging_collector`, and point `log_directory` to a test directory with adequate space.

### 31.2. Small Size Setting

Set `log_rotation_size` low to observe rotation quickly. Never apply test values to production.

### 31.3. Generating Log Messages

Emit controlled statements or notices to produce logs. Avoid infinite loops or heavy load.

### 31.4. Inspecting Files

Observe filenames, sizes, and `current_logfiles` after rotation.

### 31.5. Testing Age Rotation

Lower `log_rotation_age` in the lab and generate a message after the threshold passes to observe behavior.

### 31.6. Testing Truncation

Use a repeating filename pattern in the lab and observe `log_truncate_on_rotation=off` vs. `on` to understand overwrite risks. Keep test backups.

### 31.7. Testing Shippers

Trigger rotation while a shipper is tailing the file. Confirm no records are lost or duplicated and the shipper follows the new file.

### 31.8. Cleanup

Test retention cleanup in dry-run mode and confirm active files are excluded.

## 32. Practice Exercises

Perform these exercises in a PostgreSQL lab or dedicated observability sandbox. Never attempt to delete active logs or fill production filesystems.

### Exercise 1. Logging Collector

What is the responsibility of `logging_collector`?

### Exercise 2. Destinations

Name five log destinations PostgreSQL can support depending on OS and version.

### Exercise 3. CSV

Why is `csvlog` convenient for log analysis?

### Exercise 4. JSON

Can `jsonlog` be used on every major version?

### Exercise 5. Restart

Why does toggling `logging_collector` usually require a restart?

### Exercise 6. Directory

What is a relative `log_directory` resolved against?

### Exercise 7. Filename

What kind of patterns does `log_filename` support?

### Exercise 8. Age Rotation

Which parameter controls time-based rotation?

### Exercise 9. Size Rotation

Which parameter controls size-based rotation?

### Exercise 10. Zero

What does setting `log_rotation_size=0` mean?

### Exercise 11. Truncate

Does `log_truncate_on_rotation` apply to size-based rotation?

### Exercise 12. Filename Reuse

Why can a filename containing only the day of the week lose old logs when truncation is enabled?

### Exercise 13. Retention

Does rotation automatically delete old logs?

### Exercise 14. Manual Rotation

Write the SQL statement requesting PostgreSQL to rotate logs.

### Exercise 15. pg_ctl

Which `pg_ctl` command requests log rotation?

### Exercise 16. current_logfiles

What is the `current_logfiles` file used for?

### Exercise 17. External logrotate

Why can external `logrotate` cause PostgreSQL to keep writing to a renamed file?

### Exercise 18. Syslog

Who manages rotation when PostgreSQL sends logs to `syslog`?

### Exercise 19. Journald

Which utility views logs for a `systemd` service?

### Exercise 20. Capacity

Write the formula estimating raw log storage from bytes/second and retention days.

### Exercise 21. Inodes

Why must inodes be monitored in addition to disk bytes?

### Exercise 22. Filesystem Isolation

What is the benefit of a dedicated log filesystem?

### Exercise 23. Slow Queries

Which parameter sets the duration threshold for logging slow statements?

### Exercise 24. Statement Logging

List the common levels of `log_statement`.

### Exercise 25. Connections

Which parameters log connects and disconnects?

### Exercise 26. Lock Waits

Which parameter enables logging for sufficiently long lock waits?

### Exercise 27. Temp Files

Which parameter controls logging temporary files?

### Exercise 28. Checkpoints

Which parameter enables checkpoint logging?

### Exercise 29. Sensitive Data

Why can `log_statement=all` pose security and capacity risks?

### Exercise 30. Compression

When should log files be compressed?

### Exercise 31. Archival

Why verify archival success before deleting local logs?

### Exercise 32. Monitoring

Name four metrics to track for a log filesystem/pipeline.

### Exercise 33. Time-to-Full

Write the formula estimating time until disk exhaustion.

### Exercise 34. Disk Full

List the first three steps when the log volume nears full.

### Exercise 35. CSV Parsers

Why should you not parse `csvlog` by splitting on commas?

### Exercise 36. Log Shippers

Name two risks to test when file rotation occurs.

### Exercise 37. Config Inspection

Which view displays logging settings and `pending_restart`?

### Exercise 38. File Settings

Which view displays errors encountered while parsing configuration files?

### Exercise 39. Lab

Design a lab exercise testing time rotation, size rotation, and truncate behavior.

### Exercise 40. Production Policy

Propose a rotation, retention, archival, and alerting policy for production PostgreSQL.

## 33. Reference Solutions

### Exercises 1–7. Collector and Destinations

`logging_collector` captures `stderr` messages and writes them to log files. Destinations include `stderr`, `csvlog`, `jsonlog` (version-dependent), `syslog`, and `eventlog` on Windows. `csvlog` provides structured fields easy to parse with a CSV parser. `jsonlog` is not present in every major version. `logging_collector` requires a restart when toggled because it is a postmaster startup parameter. Relative `log_directory` paths resolve from `PGDATA`. `log_filename` supports `strftime` patterns.

### Exercises 8–13. Rotation Semantics

`log_rotation_age` controls time rotation; `log_rotation_size` controls size rotation. Size=0 disables size rotation. `log_truncate_on_rotation` does not apply to size-based rotation; it truncates colliding filenames only during time-based rotation. A weekly repeating weekday filename with truncate enabled can wipe out the previous week's logs. Rotation only creates a new file; it never deletes old files.

### Exercises 14–19. Manual Rotation and External Systems

~~~sql
SELECT pg_rotate_logfile();
~~~

`pg_ctl logrotate` instructs the collector to rotate files. `current_logfiles` identifies active files for collector-managed destinations. External `logrotate` can rename or unlink an inode while PostgreSQL retains the old file descriptor. The syslog daemon manages syslog output. Use `journalctl` to inspect `systemd` service logs.

### Exercises 20–22. Capacity

Raw storage equals bytes/second × 86400 × retention days. Inodes must be monitored because huge numbers of small files can exhaust inodes while free bytes remain. A dedicated filesystem prevents log bursts from consuming `PGDATA`/WAL space.

### Exercises 23–29. Volume and Security

`log_min_duration_statement` sets the duration threshold. `log_statement` supports `none`, `ddl`, `mod`, `all`. `log_connections`/`log_disconnections` log connection events. `log_lock_waits` logs lock waits. `log_temp_files` logs temporary files. `log_checkpoints` enables checkpoint logs. `log_statement=all` can generate huge volume and expose query literals, secrets, or sensitive data.

### Exercises 30–38. Pipeline and Monitoring

Compress closed files after PostgreSQL is no longer writing to them. Delete local files only after archival/shipping is verified. Monitor filesystem free bytes/usage, free inodes, log generation rate, shipper backlog, and archive failures. Time-to-full = free bytes / bytes generated per second. When disk nears full, identify active files, shipper/archive status, and log bursts before performing controlled cleanup. CSV requires a standard parser because fields contain quoting, commas, and newlines. Rotation causes file renames and inode changes, risking dropped or duplicated records if shippers handle it poorly. `pg_settings` displays settings, context, and `pending_restart`; `pg_file_settings` displays configuration errors.

### Exercises 39–40. Lab and Policy

In the lab, enable the collector on a dedicated instance, set a small size threshold, emit controlled logs, check files/`current_logfiles`, test an age threshold followed by a new message, and use a repeating filename to observe truncate off vs. on. Test the shipper and dry-run cleanup.

A production policy should:
- Choose appropriate destinations and formats.
- Rotate by both age and size based on measured volume.
- Keep truncate `off` unless controlled overwriting is explicitly required.
- Use short local retention and policy-driven central/archive retention.
- Compress/delete only closed and archive-verified files.
- Monitor disk, inodes, log rate, backlog, and time-to-full.
- Alert based on headroom and response lead times.
- Periodically review statement logging and privacy.

## 34. Quick Reference Table

| Need | Parameter / Tool |
| --- | --- |
| Enable logging collector | `logging_collector` |
| Choose destination | `log_destination` |
| Choose directory | `log_directory` |
| Set filename pattern | `log_filename` |
| Set file permissions | `log_file_mode` |
| Rotate by time | `log_rotation_age` |
| Rotate by size | `log_rotation_size` |
| Truncate colliding filename | `log_truncate_on_rotation` |
| View active log paths | `current_logfiles` |
| Rotate immediately via SQL | `pg_rotate_logfile()` |
| Rotate via command | `pg_ctl logrotate` |
| Send to syslog | `log_destination = syslog` |
| Send to Windows Event Log | `log_destination = eventlog` |
| Threshold statement duration | `log_min_duration_statement` |
| Log DDL/DML/all | `log_statement` |
| Log connection events | `log_connections` / `log_disconnections` |
| Log checkpoints | `log_checkpoints` |
| Log lock waits | `log_lock_waits` |
| Log temp files | `log_temp_files` |
| Log autovacuum | `log_autovacuum_min_duration` |
| Limit parameter logging | `log_parameter_max_length*` |
| Check settings | `pg_settings` |
| Check config errors | `pg_file_settings` |
| View config load time | `pg_conf_load_time()` |
| View systemd logs | `journalctl` |
| Check Linux disk usage | `df` / `du` |
| Monitor filesystem | `node_exporter` |
| Central log shipping | Fluent Bit / Vector / Filebeat |

## 35. Log Rotation and Capacity Protection Checklist

1. Choose a destination compatible with your log platform.
2. Confirm whether `logging_collector` is enabled.
3. Verify `log_directory` and the underlying filesystem.
4. Separate the log volume from `PGDATA`/WAL when appropriate.
5. Verify owner, group, and `log_file_mode`.
6. Use `log_filename` with timestamps of sufficient resolution.
7. Pick `log_rotation_age` aligned with retention and ingestion workflows.
8. Pick `log_rotation_size` aligned with desired maximum file size.
9. Keep `log_truncate_on_rotation=off` unless an explicit overwrite policy exists.
10. Verify rotation age/size semantics on your running version.
11. Inspect `current_logfiles` after the collector starts.
12. Test `pg_rotate_logfile()` or `pg_ctl logrotate`.
13. Never use external `logrotate` to arbitrarily rename collector-owned files.
14. If using `syslog`/`journald`, configure rotation/retention at the service owner level.
15. Measure log rates during normal and peak hours.
16. Calculate capacity using retention, peak factor, and headroom.
17. Monitor bytes, inodes, file counts, and time-to-full.
18. Monitor log shipper backlog and dropped events.
19. Archive and compress closed files.
20. Verify archival and checksums before deleting local copies.
21. Clean up by age within allowlisted paths.
22. Exclude active files and unshipped files.
23. Control `log_statement` and slow query thresholds.
24. Review connection, checkpoint, lock, temp file, and autovacuum logging.
25. Protect query text, bind parameters, credentials, and personal data.
26. Restrict access to log readers and central dashboards.
27. Sync timezones and clocks between PostgreSQL and the log platform.
28. Alert when filesystem/inodes near full or time-to-full drops low.
29. Alert when archival, shipper, or collector fails.
30. Maintain disk emergency and logging incident runbooks.
31. Test rotation while the shipper is actively tailing files.
32. Review retention and storage costs periodically.

## 36. Summary

PostgreSQL can manage log files via `logging_collector` with time- and size-based rotation. `log_rotation_age` splits files by time, `log_rotation_size` splits files by size, and `log_truncate_on_rotation` truncates colliding filenames only during time-based rotation. `current_logfiles` helps log shippers track active files. When using `syslog`, `journald`, or Windows Event Log, the receiving system owns rotation and retention.

Rotation is not retention. It neither deletes old files nor bounds total capacity. Protecting storage requires measuring log rates, calculating capacity from retention days and peak factors, maintaining headroom, monitoring bytes/inodes/time-to-full, shipping/archiving logs off-host, and cleaning up closed files per policy. External `logrotate` must not arbitrarily rename collector-owned files because PostgreSQL can keep writing to old file descriptors.

Log growth also depends on logging verbosity. Select slow query thresholds, statement categories, and connection/checkpoint/lock/temp/autovacuum logging to fit investigative goals. Because logs can hold sensitive SQL and parameter values, enforce strict permissions, encrypted transport, and appropriate retention.

A reliable operational process combines rotation, retention, compression, archival, capacity alerts, and runbooks. Test rotation while shippers are active, verify archives before cleanup, and always keep a response plan ready for volumes nearing full. This keeps logs valuable for troubleshooting without risking disk exhaustion on the database host.
