# Error Log, General Log, Slow Query Log, and Captured Data Scope

MySQL provides multiple log types to answer different operational questions. When the server fails to start, InnoDB performs recovery, or a plugin encounters an error, check the **error log**. When you need to know which clients connected and which SQL statements they sent, you can enable the **general query log**. When you need to find statements that run slowly or examine too many rows, use the **slow query log**.

These three logs capture different data scopes. The error log focuses on server events and diagnostics; the general log broadly records connections/commands received by the server; the slow query log only records statements that match filtering criteria. None of these logs is by itself a complete row-level record of every data change or a full auditing system.

Enabling logs also incurs costs: disk writes, CPU, storage capacity, I/O, and the risk of exposing SQL statements containing sensitive data. Operators need to know which log answers which question, how long to keep it enabled, where the log writes, who can read it, and how to rotate/purge data according to retention policy.

## 1. Three Log Types Solve Three Different Questions

| Log | Primary Question | Typical Recorded Content | Common Default |
| --- | --- | --- | --- |
| Error log | What happened to the server? | Errors, warnings, notes, startup/shutdown, recovery, component/plugin messages | Enabled |
| General query log | What commands did clients send? | Connections/disconnections and commands received by the server | Disabled |
| Slow query log | Which statements need performance investigation? | Statements meeting time/row thresholds and execution metadata | Disabled |

The error log does not replace the general log; the general log does not provide full execution plans; the slow query log does not record every query. Choose the log based on the investigative question rather than enabling all of them long-term.

## 2. What Does the Error Log Capture?

The error log is the primary diagnostic channel of the MySQL server. It records messages about the server lifecycle and notable events, for example:

- Server startup, configuration reading, and port binding.
- Plugin/component load failures or invalid configuration.
- InnoDB recovery, rollback, or storage errors.
- Server warnings about configuration, resources, or internal state.
- Normal server shutdown or termination due to errors.
- Events related to replication, internal connections, or subsystems emitting error messages.

Error log entries typically include a timestamp, severity level, and message text. The exact format depends on the error-log component, sink, and MySQL version. It is not designed to record all SQL from every application or individual OLD/NEW row values.

Not every error caused by a client's SQL statement necessarily appears in the error log. Many statement-level errors are returned directly to the client; to know which statement a client sent, check the general log during an investigation window or application logs. The error log focuses on server events and diagnostics, not a complete log of every business error.

## 3. Identifying Where the Error Log Is Written

Check the current configuration variables:

```sql
SHOW GLOBAL VARIABLES LIKE 'log_error';
SHOW GLOBAL VARIABLES LIKE 'log_error_services';
SHOW GLOBAL VARIABLES LIKE 'log_error_verbosity';
SHOW GLOBAL VARIABLES LIKE 'log_timestamps';
```

`log_error` shows the error log file path if the server uses a file sink. Depending on the platform, service manager, or container, messages may also be routed to standard error, the system journal, or another sink. Do not assume every installation writes to the same `hostname.err` file.

On Linux using systemd, you may need to check the service journal; in containers, logs may be collected from stdout/stderr. On Windows, check the file path configured by `log_error` and the corresponding Windows Service configuration.

## 4. Message Verbosity Levels in the Error Log

`log_error_verbosity` controls the detail level of error log messages in configurations using the internal log filter:

| Value | Content |
| --- | --- |
| `1` | Errors only |
| `2` | Errors and warnings |
| `3` | Errors, warnings, and notes |

Check it:

```sql
SHOW GLOBAL VARIABLES LIKE 'log_error_verbosity';
```

Lowering verbosity can drop useful diagnostic information during investigations. Raising verbosity can generate more logs. Choose a level based on operational policy and monitor disk usage; do not use verbosity changes to hide an error that needs to be addressed.

## 5. Error-Log Components and Sinks

In MySQL 8.0, error logging is organized around components. `log_error_services` specifies the filter and sink components involved in processing messages. The default configuration typically includes the internal filter and internal sink; installations can change this to integrate other log destinations.

Check it:

```sql
SHOW GLOBAL VARIABLES LIKE 'log_error_services';
```

A filter can modify or suppress messages before a sink writes them. A sink determines where the log is output. When changing the component chain, you must use valid available component names and an order supported by the version's documentation. Misconfiguration can lose a critical logging channel; test on staging and keep rollback capability.

## 6. Log Timestamps and Time Zones

`log_timestamps` controls the time zone of timestamps written in the error log, general query log, and slow query log:

```sql
SHOW GLOBAL VARIABLES LIKE 'log_timestamps';
```

Common values are `UTC` and `SYSTEM`. Using UTC helps aggregate logs from multiple servers across different time zones and correlate them with centralized systems. If set to `SYSTEM`, timestamps follow the host operating system's time zone.

When investigating an incident, verify the log time zone before correlating with application logs, traces, or metrics. Do not guess hour offsets; document the time zone and keep host clocks synchronized with NTP or an equivalent mechanism.

## 7. Error Log in Performance Schema

On versions supporting the `performance_schema.error_log` table (MySQL 8.0.22 and later), you can query a portion of the error log via SQL:

```sql
SELECT
    LOGGED,
    PRIO,
    ERROR_CODE,
    SUBSYSTEM,
    DATA
FROM performance_schema.error_log
ORDER BY LOGGED DESC
LIMIT 100;
```

This table is useful for centralized querying and diagnostics, but do not assume it holds infinite history or replaces log files/journals and log aggregation systems. Available data scope depends on version, components, and configuration. For long-term history, configure forwarding logs to a centralized storage system with appropriate retention.

## 8. What Does the General Query Log Capture?

The general query log broadly captures client activity received by the server, including:

- When a client connects and disconnects.
- Associated user/host and thread/connection ID.
- The command type sent.
- The statement text or command text received by the server.

This log helps investigate whether a client is repeatedly sending abnormal SQL, whether an account connected at a given time, or whether a statement reached the server.

The general log records commands as the server receives them, before statement success can be determined. With multiple concurrent connections, the order in which commands appear in the log is not necessarily the order in which statements complete or transactions commit. The log does not capture result sets returned to clients, is not a before/after snapshot of each row, and does not itself provide full execution times or execution plans. A statement appearing in the general log means the server received the command; do not infer that the statement definitely committed successfully.

## 9. Enabling and Disabling the General Query Log

Check the status and destination:

```sql
SHOW GLOBAL VARIABLES LIKE 'general_log';
SHOW GLOBAL VARIABLES LIKE 'general_log_file';
SHOW GLOBAL VARIABLES LIKE 'log_output';
```

Enable temporarily:

```sql
SET GLOBAL general_log = ON;
```

Disable after collection completes:

```sql
SET GLOBAL general_log = OFF;
```

The general log is usually off by default because logging every command can generate heavy load and very large data volumes. Enable it only during a short investigation window, record the exact start/stop timestamps, and re-verify the status afterward.

Changing `general_log` is a global change requiring appropriate administrative privileges. To persist the setting across restarts, place the `general_log` option in the server option group, though you should not leave it enabled indefinitely without a clear operational reason.

## 10. Writing the General Log to FILE or TABLE

`log_output` controls the destination for both the general query log and the slow query log:

```sql
SHOW GLOBAL VARIABLES LIKE 'log_output';
```

Options:

| Value | Behavior |
| --- | --- |
| `FILE` | Write to log files |
| `TABLE` | Write to log tables in the `mysql` schema |
| `FILE,TABLE` | Write to both files and tables |
| `NONE` | Do not write general/slow query logs even if the variables are enabled |

Example:

```sql
SET GLOBAL log_output = 'FILE';
```

`log_output` applies to the general and slow query logs; it does not control the error log. The error log has its own component/sink configuration.

If `log_output='NONE'`, the general/slow query logs will not write to FILE or TABLE even if `general_log` or `slow_query_log` is ON. When troubleshooting "enabled the log but no file appeared," check both the log-enable flags and `log_output`.

## 11. Reading the General Log from mysql.general_log

When `log_output` includes `TABLE`, the general query log is written to `mysql.general_log`:

```sql
SELECT
    event_time,
    user_host,
    thread_id,
    command_type,
    argument
FROM mysql.general_log
ORDER BY event_time DESC
LIMIT 100;
```

Typical columns include timestamp, user/host, thread ID, command type, and argument content. Log table schemas depend on the MySQL version. Reading `mysql.general_log` requires privileges; do not grant this privilege broadly to application users.

When log volume is high, querying the log table directly can also be resource-intensive. Filter by time range, select only needed columns, and limit row counts; do not use `SELECT *` to dump the entire log.

## 12. General Log to File

Check the target file:

```sql
SHOW GLOBAL VARIABLES LIKE 'general_log_file';
```

The path can be set via the `general_log_file` startup option or changed at runtime if the variable supports it. The MySQL process needs write permission to the target directory. If the file does not appear, check `log_output`, `general_log`, the path, and filesystem permissions.

File logs are usually read with OS tools or shipped into a log aggregation pipeline. Protect read permissions because SQL text can contain emails, phone numbers, tokens, personal information, or sensitive literals.

## 13. What Does the Slow Query Log Capture?

The slow query log records statements matching configured criteria, typically based on execution time and number of rows examined. It helps identify queries with high latency, excessive row scans, or time-consuming administrative operations.

An entry typically contains:

- Timestamp when the query started.
- User/host, thread ID, and database if applicable.
- `Query_time`: recorded execution duration.
- `Lock_time`: recorded lock wait duration as defined by the log.
- `Rows_sent`: number of rows returned.
- `Rows_examined`: number of rows examined.
- SQL text.

The slow log does not itself explain why a query is slow. After identifying a query, continue using `EXPLAIN`, `EXPLAIN ANALYZE` (when supported by the version), Performance Schema, and statistics to determine the access path, lock waits, I/O, or other causes.

## 14. Enabling the Slow Query Log

Check settings:

```sql
SHOW GLOBAL VARIABLES LIKE 'slow_query_log';
SHOW GLOBAL VARIABLES LIKE 'slow_query_log_file';
SHOW GLOBAL VARIABLES LIKE 'long_query_time';
SHOW GLOBAL VARIABLES LIKE 'min_examined_row_limit';
```

Enable the log:

```sql
SET GLOBAL slow_query_log = ON;
```

Set a one-second threshold for the current session:

```sql
SET SESSION long_query_time = 1;
```

Or set the global default for new sessions:

```sql
SET GLOBAL long_query_time = 1;
```

`long_query_time` has both global and session scope. A global change affects the default inherited by new sessions; existing connections may still retain their old session value. If testing immediately in the current connection, use `SET SESSION` or check `@@SESSION.long_query_time` to confirm.

## 15. long_query_time and min_examined_row_limit

`long_query_time` defines the duration threshold for a statement to be considered slow. The default value is typically 10 seconds; the variable supports sub-second precision. Actual settings should be based on SLAs and workload characteristics.

`min_examined_row_limit` allows skipping statements that examine fewer than a specified number of rows, even if their duration exceeds the threshold. For example:

```sql
SET GLOBAL long_query_time = 0.5;
SET GLOBAL min_examined_row_limit = 100;
```

These two parameters should be evaluated together. If `min_examined_row_limit` is set too high, you may miss a query that is slow due to locks or I/O while examining few rows. If the time threshold is set too low, the log can grow very rapidly.

## 16. Logging Queries Not Using Indexes

`log_queries_not_using_indexes` can request logging queries that do not use an index into the slow query log, even if they do not exceed `long_query_time`:

```sql
SET GLOBAL log_queries_not_using_indexes = ON;
```

Not using an index does not automatically mean a query is problematic. A table scan can be the optimal choice when a table is small or when the query needs most of the rows. Consider row count, selectivity, execution plan, and execution frequency.

Enabling logging for queries not using indexes can cause log volume to spike. You can configure `log_throttle_queries_not_using_indexes` to limit the number of such entries within a time window according to MySQL's rules.

## 17. Logging Slow Administrative Statements

`log_slow_admin_statements` allows logging administrative statements that meet the time threshold to the slow query log, such as certain `ALTER TABLE`, `CREATE INDEX`, `DROP INDEX`, `ANALYZE TABLE`, `OPTIMIZE TABLE`, or `REPAIR TABLE` operations depending on engine and version.

Check and enable when needed:

```sql
SHOW GLOBAL VARIABLES LIKE 'log_slow_admin_statements';
SET GLOBAL log_slow_admin_statements = ON;
```

This is useful when investigating long-running migrations or maintenance. Avoid turning on every extra log option without a defined goal; monitor volume and disable extended logging once the investigation concludes.

## 18. Slow Log to FILE or TABLE

The slow query log shares `log_output` with the general log. If `log_output='FILE'`, check the target file:

```sql
SHOW GLOBAL VARIABLES LIKE 'slow_query_log_file';
```

If `log_output='TABLE'`, query from `mysql.slow_log`:

```sql
SELECT
    start_time,
    user_host,
    query_time,
    lock_time,
    rows_sent,
    rows_examined,
    sql_text
FROM mysql.slow_log
ORDER BY start_time DESC
LIMIT 100;
```

Column names and structure can vary by version. Use `SHOW CREATE TABLE mysql.slow_log` or server metadata before building tools that depend on the schema.

## 19. Data Scope Across the Three Logs

| Data | Error log | General log | Slow query log |
| --- | --- | --- | --- |
| Startup/shutdown and recovery messages | Yes | Not the purpose | Not the purpose |
| Client connections/disconnections | Not primary scope | Yes | Not fully captured |
| Received SQL text | Only when relevant to an error message | Broadly captured | Only statements matching criteria |
| Query time/rows examined | No | No | Has corresponding fields |
| Result sets returned to client | No | No | No |
| Per-row OLD/NEW images | No | No | No |
| Full execution plan | No | No | No |
| Every fast statement | No | Yes, if general log is enabled | No |

Do not use the general or slow query log as a row-based audit trail. If you need to know the exact before-and-after values for each changed row, you need an audit mechanism or CDC/binlog designed for that purpose.

Nor is the general log a complete security audit: it does not automatically associate every SQL statement with the application's end-user identity, does not prove commit, and does not capture full before/after row images. For access traceability or compliance requirements, use a dedicated audit solution with identity management and clear retention policies.

## 20. The General Log Does Not Prove a Transaction Committed

The general log records commands received by the server. An `UPDATE` statement may appear in the general log even if the transaction later rolls back; a statement may fail due to a constraint or privilege error; or the client may disconnect before receiving the result.

Therefore, when investigating "who sent which statement," the general log is useful. When investigating "which changes were committed," cross-check transaction state, binary logs, audit/CDC, or application data according to your system architecture. Do not infer commit solely from seeing SQL in the general log.

## 21. Prepared Statements and Logged Content

Applications may send statements using the prepared statement protocol. Logs represent commands/SQL according to how MySQL records them in each log type and version; do not build tooling assuming every prepared statement will appear as a single SQL string with all parameters fully interpolated.

If you need to investigate parameter values, test driver/server behavior on your specific version in a safe environment. Do not enable the general log in production solely to try to capture all parameters without evaluating data-exposure risks and overhead.

## 22. Costs and Risks of Enabling Logs

The general log can record every command and connection event, so volume scales with QPS and connection count. The slow log is typically more selective, though it can still grow rapidly with low thresholds or when logging queries not using indexes. The error log must remain enabled for diagnostics, while still requiring sink, capacity, and retention management.

Costs to account for:

- CPU to generate/format log entries.
- I/O and file/table storage capacity.
- Additional lock/contention when writing to log tables.
- Network and ingestion cost when shipping to centralized systems.
- Storage, search, and retention costs.
- Risk of exposing SQL literals, personal information, or confidential data.

Do not leave the general log enabled for long periods on high-traffic workloads without measuring impact. Using the slow log with an appropriate threshold is usually more practical for performance investigations.

## 23. Protecting Sensitive Data in Logs

SQL text may contain literals such as emails, phone numbers, addresses, access tokens, or payment data. Anyone able to read general/slow log files or `mysql.general_log`/`mysql.slow_log` tables can access that information.

Operational safeguards:

- Restrict read permissions on log files and tables to required DBA/on-call personnel.
- Do not grant `SELECT` on the `mysql` schema to application accounts merely for convenience.
- Avoid embedding passwords/tokens directly in SQL statements or command lines.
- Use prepared statements and proper secret management; note that logs may still contain statement/parameter context depending on execution path.
- Mask/redact data before sharing logs in tickets, chat, or external services.
- Encrypt logs at rest and in transit if required by data policies.
- Establish retention schedules and purge logs per data protection policy.

Logs can contain sensitive data even when the original goal is purely debugging. Treat logs according to the same data classification as the underlying data source they record.

## 24. Rotating and Managing Log Capacity

For file logs, you can instruct MySQL to close and reopen log files using the appropriate FLUSH command:

```sql
FLUSH ERROR LOGS;
FLUSH GENERAL LOGS;
FLUSH SLOW LOGS;
```

Or use:

```sql
FLUSH LOGS;
```

Flush/reopen commands require appropriate administrative privileges. When using logrotate or an external file management tool, coordinate rename/rotate operations with instructing MySQL to open a new file; if you only delete or move an open file, MySQL may continue writing to the old file descriptor.

If logs write to TABLE, manage log table size and retention appropriately for your version. Before truncating or altering log tables, consult MySQL documentation and disable the corresponding logging if needed; do not arbitrarily modify system tables actively written by the server.

## 25. Reading the Slow Log and Tracing to Root Cause

Slow query investigation workflow:

1. Filter entries by `Query_time`, `Rows_examined`, user/host, and database.
2. Group similar SQL statements to identify recurring patterns rather than looking only at a single entry.
3. Check whether specific query parameters cause significant cardinality differences.
4. Run `EXPLAIN` to inspect access type, key, estimated rows, and join order.
5. Use `EXPLAIN ANALYZE` in an appropriate environment to compare actual rows/time against estimates.
6. Check indexes, statistics, lock waits, I/O, buffer pool, and contention.
7. Adjust the query, index, or data appropriately; re-measure under a representative workload.
8. Tune the slow log threshold after completing the investigation.

A high `Rows_examined` relative to `Rows_sent` is a signal worth investigating, though it does not by itself prove a missing index. Aggregate queries, reports, or queries legitimately reading large datasets can reasonably examine many rows.

## 26. Combining Logs with Performance Schema and sys Schema

The slow query log is useful for finding slow statements above a threshold. Performance Schema provides finer-grained statistics on statements, waits, stages, transactions, and metadata locks depending on enabled instruments/consumers. The `sys` schema presents many of these statistics in a human-readable form.

Example: viewing statement digests by total time and execution count:

```sql
SELECT
    query,
    exec_count,
    total_latency,
    avg_latency,
    rows_examined,
    rows_sent
FROM sys.statement_analysis
ORDER BY total_latency DESC
LIMIT 20;
```

`sys` schema views and columns may vary by version. Performance Schema uses bounded buffers and some consumers/instruments may be disabled; do not treat it as infinite history. Use log files/monitoring platforms for long-term history and Performance Schema to drill down into current/recent state.

## 27. Enabling Logs via Startup Configuration

You can configure logging in the option file:

```ini
[mysqld]
log_error=/var/log/mysql/error.log
log_error_verbosity=3
log_timestamps=UTC

general_log=OFF
slow_query_log=ON
slow_query_log_file=/var/log/mysql/slow.log
long_query_time=1
min_examined_row_limit=100
log_output=FILE
```

Paths are Linux examples; on Windows use appropriate paths and ensure the service account has write permissions. The error log is configured independently of `log_output`. Only enable the general log at startup when an approved investigation/control requirement exists with appropriate retention.

## 28. Symptom-Based Investigation Runbook

| Symptom | Starting Log/Source | Next Steps |
| --- | --- | --- |
| MySQL fails to start | Error log, system journal | Check invalid options, permissions, port, InnoDB recovery, and disk |
| Unexpected server restart | Error log, OS/service manager logs | Identify crash, OOM kill, shutdown signal, or host failure |
| Unclear which SQL a client sent | General log enabled briefly | Filter by user/host/thread and timestamp |
| High API latency | Slow query log, Performance Schema | Analyze digests, EXPLAIN, lock waits, and rows examined |
| Excessive table scans | Slow log + controlled `log_queries_not_using_indexes` | Distinguish justified scans from missing indexes |
| Rapid log growth | Check general/slow settings, `log_output`, QPS | Disable extended logging, throttle, rotate, and apply retention |
| Logs contain sensitive data | Log files/tables and access permissions | Restrict permissions, redact, rotate, and handle per policy |

## 29. Hands-On Exercises

1. Inspect `log_error`, `log_error_verbosity`, `log_timestamps` and locate the actual error log in your lab environment.
2. Introduce a configuration error in a test environment; read the corresponding message in the error log.
3. Enable the general log for a short period; perform connect, SELECT, a failed INSERT, and disconnect; observe the entries.
4. Disable the general log and confirm its global state is OFF.
5. Set `log_output='TABLE'`; query `mysql.general_log` and identify event_time, user_host, thread_id, command_type, and argument.
6. Enable the slow query log with a low `long_query_time` in the lab; run an intentionally slow query.
7. Test changing `long_query_time` globally and per session; compare the value in the current connection versus a new connection.
8. Set `min_examined_row_limit`; observe whether queries examining fewer rows are excluded from the slow log.
9. Enable `log_queries_not_using_indexes` briefly; observe log growth and turn it back off.
10. Enable `log_slow_admin_statements`; perform a maintenance operation in the lab and inspect the slow log.
11. Compare FILE and TABLE output; measure the impact as log volume increases.
12. Use `EXPLAIN` and `EXPLAIN ANALYZE` to analyze a query found in the slow log.
13. Run `FLUSH SLOW LOGS` after rotating the file in a test environment.
14. Audit log read permissions and define rules to redact sensitive data before sharing.

## 30. Key Takeaways

The error log records server events and diagnostic messages such as startup/shutdown, errors, warnings, recovery, and component messages. The general query log broadly records connection events and commands/SQL received by the server, without recording result sets, row images, or proving transaction commits. The slow query log records statements matching thresholds like `long_query_time` and `min_examined_row_limit`, along with metadata such as `Query_time`, `Lock_time`, `Rows_sent`, and `Rows_examined`; it does not record every fast query.

`log_output` controls FILE/TABLE/NONE for the general and slow logs, not the error log. `general_log` and `slow_query_log` are usually off by default; enable the general log only for short windows due to high volume and cost. `long_query_time` has global/session scope, so verify the active session value. Configure error-log verbosity, timestamps, and components purposefully; read logs via files, system journal, or Performance Schema tables depending on version. Protect logs like sensitive data, restrict access, enforce rotation/retention, and use the slow log to identify candidates before analyzing further with EXPLAIN, Performance Schema, and the sys schema. Never treat these three logs as a complete row-level audit system.
