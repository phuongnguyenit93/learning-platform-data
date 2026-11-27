# Health Checks and Building Repeatable Operational Runbooks

A MySQL server that accepts connections is not necessarily ready to serve business traffic. Connections can succeed while the connection pool is nearly exhausted, queries are blocked by locks, replicas are lagging, disk space is running out, or the latest backup has never been restore-tested. A health check is meaningful when it evaluates multiple layers of the system and indicates the next action.

A good operational runbook turns incident response experience into a procedure someone else can repeat: knowing when to start, what privileges are needed, which commands to run, what normal output looks like, when to stop, how to verify post-remediation, and when to escalate. Runbooks should be grounded in the system's own metrics, versioned, and rehearsed periodically.

This lesson belongs to the **Configuration and Operations** chapter of the **DATABASE_MYSQL** module. Within the scope of mastering MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control, health-checking and runbook authoring skills enable consistent database operations, early anomaly detection, and reduced risk during configuration changes.

## 1. MySQL Health Spans Multiple Layers

No single command confirms the entire system is healthy. Split checks into layers to avoid blind spots:

| Layer | Question to Answer | Example Signals |
|---|---|---|
| Process and connectivity | Is `mysqld` running and accepting connections? | `mysqladmin ping`, `SELECT 1`, `Uptime` |
| Role and serving capability | Is this a primary or replica? Are writes permitted? | `read_only`, `super_read_only`, replication status |
| Connection resources | Is there a risk of connection exhaustion? | `Threads_connected`, `Threads_running`, `Max_used_connections` |
| Queries and load | Are queries increasing in latency or scanning too much data? | digest statistics, slow log, rows examined |
| Transactions and locks | Are there long-running transactions or lock waits? | `innodb_trx`, `data_lock_waits`, deadlocks |
| InnoDB and storage | Do buffer pool, redo, tables, and indexes show anomalies? | InnoDB status, buffer pool counters, table statistics |
| Infrastructure | Are CPU, RAM, filesystems, and network sufficient? | OS metrics, disk free, I/O latency |
| Replication and availability | Are replicas keeping up? Can failover be performed? | Replica status, GTID, group replication status |
| Backup and recovery | Do valid, restore-tested backups exist? | backup age, restore test, binlog coverage |
| Security and configuration | Do privileges, TLS, auditing, and config match standards? | users/grants, variables, error log |

Check outcomes should classify into at least three states:

- **OK**: signals lie within agreed thresholds with no abnormal conditions.
- **WARN**: a negative trend exists or a limit is approaching; monitoring or investigation is required.
- **CRITICAL**: service is already impacted or at risk of data loss, required reads/writes are failing, or essential resources are nearing exhaustion.

Do not use one universal threshold for every system. For example, 70% of `max_connections` may be normal under steady workloads yet dangerous if connections are surging rapidly and pools are retrying aggressively. Thresholds must tie to baselines, growth rates, SLOs, and spare headroom.

## 2. Confirming the Server Is Alive and in the Expected Role

You can check the process using `mysqladmin`:

~~~bash
mysqladmin --host=db01.example.internal --user=healthcheck --password ping
~~~

`mysqladmin ping` checks whether `mysqld` responds. A successful ping does not prove business users have access, queries can complete, or replicas are caught up. Notably, `mysqladmin ping` can return a success exit code even when the server is running yet rejects authentication; therefore check the message as well, then verify with an authenticated SQL connection.

Verify through an authenticated SQL connection:

~~~sql
SELECT
    NOW(6) AS checked_at,
    VERSION() AS mysql_version,
    @@version_comment AS distribution,
    @@hostname AS server_host,
    @@port AS server_port,
    @@server_id AS server_id,
    @@server_uuid AS server_uuid,
    @@global.read_only AS read_only,
    @@global.super_read_only AS super_read_only;
~~~

The output confirms which server the session is talking to and whether the server allows writes. On MySQL 8.0, `read_only` and `super_read_only` are critical variables for distinguishing primary and replica roles. When operating older versions, verify variable availability and documentation for that exact version.

Never infer role solely from hostname or DNS name. An endpoint may have shifted to another node after failover. Runbooks must verify `server_uuid`, `server_id`, `read_only`/`super_read_only`, and replication status before running writes or configuration changes.

Check uptime:

~~~sql
SHOW GLOBAL STATUS LIKE 'Uptime';
~~~

`Uptime` is the number of seconds since server startup. Low uptime may reflect a planned restart, crash, failover, or recent deployment. Cross-reference change schedules, the error log, and incident start times. High uptime does not automatically prove stability; a server can stay up for a long time while accumulating stale transactions or leaked resources.

## 3. Verifying Connectivity and Query Execution

A minimal readiness check should execute an actual query:

~~~sql
SELECT 1 AS database_ready, NOW(6) AS checked_at;
~~~

If the application needs to confirm access to business schemas, read a dedicated health-check table or a small configuration table using the application account. Never run a heavy query solely for a readiness check.

Distinguish:

- **Liveness**: the MySQL process is alive and able to respond.
- **Readiness**: this node can serve the intended traffic type with proper connectivity, privileges, and state.
- **Business health**: critical business operations can complete within acceptable time bounds.

For example, a replica may pass liveness and readiness for read queries yet not be ready for writes because `read_only` is enabled. A primary may still return `SELECT 1` while the connection pool is nearly exhausted or write queries are waiting on locks.

If using a load balancer or proxy, test both the proxied path and direct node path when permitted by the runbook. The two paths may have different DNS, TLS, routing, and connection limits.

## 4. Capturing Connection State and Utilization

The following status variables are typically useful:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Threads_connected',
    'Threads_running',
    'Max_used_connections',
    'Connections',
    'Aborted_connects',
    'Aborted_clients',
    'Uptime'
);
~~~

Meaning:

- **Threads_connected**: number of currently open connections.
- **Threads_running**: number of active threads not sleeping; this is not an exact count of CPU-bound queries.
- **Max_used_connections**: peak concurrent connections since server startup or status reset.
- **Connections**: total connection attempts to the server since startup.
- **Aborted_connects**: count of failed connection attempts.
- **Aborted_clients**: count of connections closed improperly after connecting.
- **Uptime**: seconds since the most recent startup.

Read these alongside `max_connections`:

~~~sql
SELECT
    @@global.max_connections AS max_connections,
    @@global.max_user_connections AS max_user_connections;
~~~

Instantaneous utilization can be approximated as `Threads_connected / max_connections`. Sustained high levels or rapid increases warrant investigation. `Max_used_connections` shows the historical peak, though historical stats reset after restarts, so snapshots must be stored in external monitoring.

View open connections:

~~~sql
SHOW FULL PROCESSLIST;
~~~

Or use Performance Schema:

~~~sql
SELECT
    PROCESSLIST_ID AS connection_id,
    PROCESSLIST_USER AS user_name,
    PROCESSLIST_HOST AS client_host,
    PROCESSLIST_DB AS current_schema,
    PROCESSLIST_COMMAND AS command_name,
    PROCESSLIST_TIME AS command_seconds,
    PROCESSLIST_STATE AS process_state,
    PROCESSLIST_INFO AS current_sql
FROM performance_schema.threads
WHERE TYPE = 'FOREGROUND'
  AND PROCESSLIST_ID IS NOT NULL
ORDER BY PROCESSLIST_TIME DESC;
~~~

`PROCESSLIST_INFO` can contain sensitive literals, personal data, or tokens embedded directly in SQL by applications. When saving snapshots to tickets or logs, redact sensitive data and retain only what is necessary. Monitoring accounts need appropriate privileges to view other users' connections.

A connection in `Sleep` state is not necessarily harmless. It can hold open transactions and InnoDB locks. When seeing long-sleeping connections, cross-check with `information_schema.innodb_trx` instead of looking only at `PROCESSLIST_COMMAND`.

## 5. Tracking Counters Over Time Intervals

Many `SHOW GLOBAL STATUS` variables are cumulative counters since server startup or reset. Absolute values do not show current rates. Capture two snapshots separated by a known time interval and compute deltas.

Example snapshot query:

~~~sql
SELECT
    NOW(6) AS captured_at,
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.global_status
WHERE VARIABLE_NAME IN (
    'Connections',
    'Questions',
    'Slow_queries',
    'Created_tmp_tables',
    'Created_tmp_disk_tables',
    'Innodb_buffer_pool_reads',
    'Innodb_buffer_pool_read_requests',
    'Innodb_row_lock_time',
    'Bytes_received',
    'Bytes_sent'
)
ORDER BY VARIABLE_NAME;
~~~

Suppose two snapshots are 60 seconds apart. For a monotonically increasing counter, the average rate over the interval is:

\[
\text{Rate} = \frac{\text{Counter}_{t2} - \text{Counter}_{t1}}{t2 - t1}
\]

For example, if `Connections` increased by 120 in 60 seconds, the average connection rate is 2 connections/second. If `Uptime` dropped or `server_uuid` changed between snapshots, the server may have restarted or the endpoint may have moved to another node; never subtract counters across two different nodes as though they were the same counter.

Useful ratios to monitor:

- **New connection rate**: delta `Connections` / seconds.
- **On-disk temporary table ratio**: delta `Created_tmp_disk_tables` / delta `Created_tmp_tables`, when the denominator is greater than 0.
- **Relative buffer pool read miss ratio**: delta `Innodb_buffer_pool_reads` / delta `Innodb_buffer_pool_read_requests`, when the denominator is greater than 0.
- **Query rate**: delta `Questions` / seconds; note `Questions` does not map 1:1 to business requests.
- **Network throughput**: delta `Bytes_received` and `Bytes_sent` / seconds.

Ratios are only indicators. On-disk temporary tables can be normal for certain queries; rising buffer pool misses do not automatically mean the buffer pool must be enlarged. Correlate with latency, workload, RAM, I/O, and query plans.

## 6. Checking Long Transactions and Lock Waits

Long-open transactions can hold row locks, retain undo history, and increase purge pressure. Start with the list of InnoDB transactions:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
    trx_wait_started,
    trx_mysql_thread_id AS connection_id,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Correlate `connection_id` with the process list to find user, host, command, and current SQL. If `trx_query` is NULL while the transaction still exists, the session may be waiting for the application to send the next statement or sleeping between statements in the transaction.

On MySQL 8.0, inspect lock waits via Performance Schema:

~~~sql
SELECT
    REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx,
    REQUESTING_THREAD_ID AS waiting_thread,
    BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx,
    BLOCKING_THREAD_ID AS blocking_thread,
    REQUESTING_ENGINE_LOCK_ID AS requested_lock_id,
    BLOCKING_ENGINE_LOCK_ID AS blocking_lock_id
FROM performance_schema.data_lock_waits;
~~~

If the `sys` schema is installed and corresponding views are available, `sys.innodb_lock_waits` can offer a more readable view of waiters, blockers, and wait durations. Exact column layouts vary by version; check `DESCRIBE` or documentation for your exact version before embedding queries in runbooks.

Never automatically `KILL` every transaction older than a fixed threshold. Identify the owner, business operation, modified row count, rollback impact, and blast radius before terminating a connection. Rolling back a large transaction can take a long time and continue consuming I/O.

## 7. Inspecting Queries and Performance Statistics

Performance Schema stores statement statistics by digest when appropriate instrumentation and consumers are enabled. You can query statements with high total execution time:

~~~sql
SELECT
    SCHEMA_NAME,
    DIGEST_TEXT,
    COUNT_STAR AS execution_count,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_seconds,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_seconds,
    SUM_ROWS_EXAMINED AS rows_examined,
    SUM_ROWS_SENT AS rows_sent,
    SUM_NO_INDEX_USED AS executions_without_index,
    SUM_CREATED_TMP_DISK_TABLES AS disk_tmp_tables
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST_TEXT IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

Timers in Performance Schema are stored in picoseconds; dividing by 1,000,000,000,000 converts to seconds. Digest stats aggregate across multiple executions, so high total time can come from a frequently executed query rather than only one with high per-execution latency.

Read together:

- `COUNT_STAR` for frequency.
- `AVG_TIMER_WAIT` for average duration.
- `SUM_TIMER_WAIT` for total impact.
- `SUM_ROWS_EXAMINED` vs. `SUM_ROWS_SENT` to spot queries scanning many rows yet returning few.
- `SUM_NO_INDEX_USED` and `SUM_CREATED_TMP_DISK_TABLES` as signals for deeper investigation.

Columns and support levels can vary across versions. If the query returns no data, check whether Performance Schema is enabled, statement instrumentation/consumers are enabled, and the account has read privileges. Never enable broad instrumentation in production without evaluating overhead.

To diagnose a specific query, grab representative SQL and use `EXPLAIN` or `EXPLAIN ANALYZE` under safe conditions. Never run `EXPLAIN ANALYZE` on a heavy SELECT in production merely for numbers; that command actually executes the query.

## 8. Checking InnoDB, Buffer Pool, and Tables

Retrieve the InnoDB report:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

In the `mysql` client, you can append `\G` for vertical display:

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

Key sections to review include TRANSACTIONS, LATEST DETECTED DEADLOCK, FILE I/O, INSERT BUFFER AND ADAPTIVE HASH INDEX, BUFFER POOL AND MEMORY, and ROW OPERATIONS. This is a diagnostic snapshot, not a complete log of all past events. LATEST DETECTED DEADLOCK retains only the single most recent deadlock captured in that output.

Check buffer pool configuration:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_buffer_pool_size';
~~~

Track counters such as `Innodb_buffer_pool_reads` and `Innodb_buffer_pool_read_requests` via deltas rather than relying solely on cumulative ratios since startup. Consider actual RAM, workload, working set size, and I/O latency before deciding to resize the buffer pool.

Estimate table and index sizes from Information Schema:

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH,
    DATA_FREE,
    UPDATE_TIME
FROM information_schema.tables
WHERE TABLE_SCHEMA NOT IN (
    'mysql',
    'information_schema',
    'performance_schema',
    'sys'
)
ORDER BY DATA_LENGTH + INDEX_LENGTH DESC
LIMIT 30;
~~~

For InnoDB, `TABLE_ROWS`, `DATA_LENGTH`, `INDEX_LENGTH`, and `DATA_FREE` can be estimates. `UPDATE_TIME` does not always accurately reflect when InnoDB data was modified. Use them to identify candidate tables for inspection, not as a replacement for filesystem disk-usage tools or dedicated storage telemetry.

MySQL SQL does not provide full filesystem information such as free space on the volumes holding `datadir`, binary logs, relay logs, redo logs, or backups. Runbooks must include OS or cloud-platform checks for free disk space, inodes, I/O latency, CPU, memory, and networking.

## 9. Checking Error Logs and Server Events

The error log is a critical source for finding crashes, restarts, initialization errors, InnoDB errors, replication errors, TLS issues, and configuration warnings.

View related configuration:

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'log_error',
    'log_error_verbosity',
    'log_timestamps',
    'log_error_services'
);
~~~

Not every version shares the same variable set or log service architecture. Verify actual variables with `SHOW VARIABLES` and read the error log at the path or sink currently configured. On managed services, logs may be routed to the provider's logging platform instead of a local file.

During investigations, record:

- Incident start and end timestamps, including time zone.
- Server UUID, hostname, and version.
- The first relevant error line and errors immediately preceding/following it.
- Restarts, failovers, configuration changes, or deployments around that time.
- Repeated warnings and their frequency.

Do not search only for the keyword `ERROR`. Repeated warnings about disk space, expiring certificates, replication, or thread creation can be early warning signs before a service outage.

Error logs and process lists may contain usernames, hostnames, internal paths, or SQL statements. Share only necessary excerpts, redact credentials, and follow log retention policies.

## 10. Checking Replication and Serving State

If the server is a replica, check replication state using version-appropriate syntax. On MySQL 8.0.22 and later, use:

~~~sql
SHOW REPLICA STATUS\G
~~~

Older MySQL versions may use `SHOW SLAVE STATUS`. Do not mix old and new status variable names in the same runbook without clearly noting supported versions.

Key fields to inspect in the output include:

- `Replica_IO_Running` and `Replica_SQL_Running`: status of the threads receiving and applying relay logs.
- `Seconds_Behind_Source`: lag estimate under certain conditions; `NULL` or `0` does not prove the replica is completely synchronized.
- `Last_IO_Error` and `Last_SQL_Error`: most recent errors on the I/O or SQL threads.
- `Retrieved_Gtid_Set` and `Executed_Gtid_Set`: GTID ranges received and executed when GTID is enabled.
- `Source_Host`, `Source_Port`, and `Channel_Name`: replication source and channel under inspection.

Never use `Seconds_Behind_Source` alone as the sole criterion for failover decisions. Inspect thread states, GTIDs, errors, freshness of readable data, and the topology's failover procedure.

For Group Replication or InnoDB Cluster, use the corresponding group views/statuses and MySQL Shell for your deployed version. Runbooks must specify the topology type; never apply simple replica commands to a cluster managed by a different orchestration mechanism.

Before write operations, confirm the node is primary according to topology management and that `read_only`/`super_read_only` match expected state. Before read operations requiring fresh data, define the business's tolerable replication lag.

## 11. Checking Backups and Recoverability

A technically successful backup does not prove the system can recover at the required point in time. Health checks must verify both the backup creation pipeline and restore capability.

Questions to answer:

- When did the latest backup complete, and which server/schema does it cover?
- Does the backup have an identifier, checksum, or manifest to verify integrity?
- Does the backup include required data, metadata, users/grants, and configuration needed for recovery?
- If point-in-time recovery is needed, are binary logs continuous and retained long enough?
- Is the backup encrypted and access-restricted?
- When was the most recent restore test, how long did it take, and did it meet RTO/RPO?

Periodically restore into an isolated environment, verifying schemas, critical row counts, privileges, and application connectivity. Never test a backup by restoring over production.

Backup runbooks must distinguish physical snapshots, logical dumps, managed-service backups, and backups combined with binary logs. Each method has different consistency requirements, locking windows, capacity needs, version compatibility, and recovery steps.

Never treat enabling the binary log as a complete backup. Binary logs support replication and point-in-time recovery, yet you still need valid base backups, proper retention, secure storage, and recovery drills.

## 12. Building Baselines and Alert Thresholds

A baseline describes normal system behavior across representative workload cycles. Collect data during peak hours, off-peak hours, weekdays, weekends, and batch runs when impactful.

A practical baseline should include:

| Group | Metrics to Retain |
|---|---|
| Connections | `Threads_connected`, `Threads_running`, `Max_used_connections`, `Connections` rate |
| Queries | application p50/p95/p99 latency, digest counts, rows examined |
| InnoDB | buffer pool reads, row lock time, deadlocks, transaction age |
| Storage | data/index size, disk free, I/O latency, binary log growth |
| Replication | thread states, GTID gaps, lag, and apply duration |
| Backup | backup timestamp, duration, size, restore test results |
| Infrastructure | CPU, RAM, swap, network, filesystems, and inodes |

Select thresholds based on impact:

- Early warning thresholds when growth rates indicate limits will be reached soon.
- Critical thresholds when SLOs are breached, connections near exhaustion, or replicas exceed business lag limits.
- Storage thresholds based on growth rate and the time needed to expand volumes, not merely current free percentage.
- Transaction/lock wait thresholds based on workload type and business wait tolerance.

For cumulative counters, base alerts on rates or deltas. For gauges like `Threads_connected`, measure current values and trends. For latency, use percentiles instead of averages alone, since a small group of very slow queries can be masked by an average.

Every alert must have an owner, severity, runbook link, closing criteria, and deduplication/anti-flap rules. An alert with no follow-up action only creates noise.

## 13. Structure of a Repeatable Runbook

Every runbook should follow a consistent structure so on-call engineers never have to guess the next step:

1. **Runbook name and ID**: stable identifier for linking from alerts and tickets.
2. **Purpose**: the incident or change the runbook addresses.
3. **Scope**: environments, clusters, MySQL versions, topologies, and related services.
4. **Trigger conditions**: alerts, symptoms, thresholds, or change requests.
5. **Impact level**: how to assess severity, user impact, and data risk.
6. **Required roles and privileges**: operator, approver, monitoring or administrative accounts.
7. **Preconditions**: confirming node, backup, timing, privileges, and change window.
8. **Execution steps**: exact commands, order, parameters, and how to capture output.
9. **Expected results**: pass/fail criteria after each step.
10. **Decision branches**: if result A, what to do; if B, stop or escalate.
11. **Post-action verification**: checking service, data, replication, and metrics.
12. **Rollback or recovery**: conditions, commands, and rollback limits.
13. **Escalation**: contacts/teams, handoff data required, and time limits.
14. **Evidence and history**: timestamps, server UUID, commands run, outputs, changes, and operator.
15. **Owner and review date**: maintainer, version, and most recent rehearsal date.

A runbook containing only commands without expected outputs forces the operator to improvise interpretation. A runbook without stop conditions can cause someone new to keep executing after entering a dangerous state.

## 14. Example Runbook: Connection Surge

**Objective:** identify the cause of rising connections, protect availability, and relieve pressure in a controlled manner.

**Trigger:** `Threads_connected` rises near `max_connections`, applications report `too many connections` errors, or latency rises alongside connection churn.

**Step 1 — Verify node and record timestamp**

~~~sql
SELECT
    NOW(6) AS checked_at,
    @@hostname AS server_host,
    @@server_uuid AS server_uuid,
    @@global.read_only AS read_only,
    @@global.super_read_only AS super_read_only;

SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Threads_connected',
    'Threads_running',
    'Max_used_connections',
    'Connections',
    'Aborted_connects'
);

SHOW GLOBAL VARIABLES LIKE 'max_connections';
~~~

Record output and compare with prior snapshots. If the endpoint shifted nodes or `Uptime` recently reset, verify topology before comparing counters.

**Step 2 — Find top connection consumers**

~~~sql
SELECT
    PROCESSLIST_USER AS user_name,
    PROCESSLIST_HOST AS client_host,
    PROCESSLIST_DB AS current_schema,
    PROCESSLIST_COMMAND AS command_name,
    COUNT(*) AS connection_count
FROM performance_schema.threads
WHERE TYPE = 'FOREGROUND'
  AND PROCESSLIST_ID IS NOT NULL
GROUP BY
    PROCESSLIST_USER,
    PROCESSLIST_HOST,
    PROCESSLIST_DB,
    PROCESSLIST_COMMAND
ORDER BY connection_count DESC;
~~~

If one user/host holds most connections, reconcile with connection pools, application instance counts, pool limits, and retry policies. Check whether many `Sleep` connections are holding open transactions.

**Step 3 — Check open transactions**

~~~sql
SELECT
    trx_mysql_thread_id AS connection_id,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
    trx_state,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

If long-open transactions exist, identify the owner and impact before asking the application to commit/roll back or terminating the connection. Never bulk-`KILL` solely to lower `Threads_connected`.

**Step 4 — Choose action**

- If applications create connections too quickly: inspect pool max size, connection leaks, retry storms, and timeouts; adjust at the application tier via deployment procedures.
- If `Sleep` connections are accumulating: identify owning pools/workers and open transactions; ensure transactions close properly in code.
- If long-running queries exist: inspect plans, lock waits, I/O, and load; fix the query root cause.
- If `max_connections` genuinely needs increasing: verify RAM per connection, workload, OS limits, and proxies; change via approved config procedures.
- If the node has lost serving capability: escalate per failover/incident runbooks; never alter node roles ad hoc inside a connection runbook.

**Step 5 — Verify**

Repeat snapshots after action. Confirm `Threads_connected` drops or stabilizes, connection errors stop climbing, p95/p99 latency recovers, and applications process requests. Record recovery time and root cause once identified.

## 15. Safe and Verifiable Configuration Changes

Before changing a variable, verify current value, GLOBAL/SESSION scope, dynamicity, configuration source, and version support.

View current values:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL VARIABLES LIKE 'innodb_buffer_pool_size';
~~~

On MySQL 8.0, view the setting source in Performance Schema:

~~~sql
SELECT
    VARIABLE_NAME,
    VARIABLE_SOURCE,
    VARIABLE_PATH,
    SET_TIME,
    SET_USER,
    SET_HOST
FROM performance_schema.variables_info
WHERE VARIABLE_NAME IN (
    'max_connections',
    'innodb_buffer_pool_size'
);
~~~

Columns in `variables_info` help identify configuration sources and when a variable was set. If the table is empty or the version differs, use `SHOW VARIABLES` and check configuration files per server administration procedures.

Different ways to apply changes:

~~~sql
-- Changes runtime only; does not persist across restarts.
SET GLOBAL max_connections = 500;
~~~

~~~sql
-- Changes runtime and persists configuration for subsequent startups.
SET PERSIST max_connections = 500;
~~~

~~~sql
-- Saves value for the next startup without changing current runtime.
SET PERSIST_ONLY max_connections = 500;
~~~

~~~sql
-- Removes the saved override for this variable.
RESET PERSIST IF EXISTS max_connections;
~~~

Use only syntax appropriate for your version and granted privileges. `SET PERSIST` and `SET PERSIST_ONLY` require appropriate system variable administration privileges. Some variables take effect only at startup; others can change at runtime. Never assume all variables are dynamic.

`SET GLOBAL` does not write values into regular configuration files; changes can be lost after restart. `SET PERSIST` writes overrides into MySQL's persisted configuration store, typically `mysqld-auto.cnf`. Never edit `mysqld-auto.cnf` directly with a text editor. `RESET PERSIST` deletes persisted values; deleting an override does not necessarily revert the current runtime value to its default immediately.

Before applying:

1. Record the current value and configuration source.
2. Document the reason for change and impact on RAM, CPU, connections, I/O, or replication.
3. Check dynamic/startup-only status and version compatibility.
4. Test on staging or an appropriate replica.
5. Prepare rollback steps and approvers.
6. Change one variable or one clearly coupled group at a time.
7. Verify runtime, persisted value, and metrics after the change.
8. Log the outcome in the change record.

Never raise `max_connections` to cope with a connection leak without finding the root cause. Each connection can consume memory for threads, buffers, and session state; raising the limit can exhaust server RAM even faster under rising load.

## 16. Distinguishing Routine Checks from Incident Handling

Routine health checks should be short, automatable, and favor low-impact read commands. Incident runbooks can go deeper and execute only upon specific triggers.

| Activity | Suggested Frequency | Examples |
|---|---|---|
| Liveness/readiness | Continuous or every minute | `mysqladmin ping`, `SELECT 1`, role check |
| Connections and resources | Every 1–5 minutes | `Threads_connected`, `Threads_running`, disk free |
| Queries/locks/transactions | Continuous or every few minutes | digests, lock waits, transaction age |
| Replication | Continuous or per topology | thread status, GTID, lag |
| Backup jobs | After every run | exit status, checksum, manifest |
| Restore tests | Per recovery schedule | restore into isolated environment |
| Configuration drift | On deploy and periodically | variables, source, persisted settings |
| Runbook exercises | Scheduled or after major changes | incident, failover, and restore drills |

Intervals are starting points only. Tune based on load, metric collection cost, detection latency, and required response time.

Automated health checks must never automatically `KILL` connections, restart MySQL, toggle `read_only`, promote a replica, or edit configuration. Those actions require runbooks with explicit conditions, role checks, and appropriate approvals.

## 17. Recording Evidence and Maintaining Runbooks

Every runbook execution should record:

- Runbook ID and version.
- Operator, approver, and related ticket/incident.
- Start/end timestamps in UTC or designated time zone.
- Hostname, `server_uuid`, `server_id`, version, and node role.
- Commands executed alongside sanitized outputs.
- Before/after values for any changes.
- Pass/fail conditions and decision branches taken.
- Rollback, escalation, or follow-up actions.
- Final outcome and time to service recovery.

Runbooks must be re-validated after changes to MySQL version, topology, proxies, monitoring, schemas, backup workflows, and administrative privileges. A command valid on MySQL 8.0 may be renamed or behave differently on another version; explicitly state tested versions.

Rehearse runbooks in non-production environments before relying on them in real incidents. Time each step, confirm required privileges, check outputs, catch obsolete commands, and refine decision branches. After an incident, add any missed conditions and explicitly document commands that must not be run in specific situations.

## 18. Common Operational Mistakes

**Checking only `mysqladmin ping`.** Ping proves the process responds; it does not prove business queries, privileges, replication, or connection pools are healthy.

**Alerting on a raw cumulative counter value.** `Connections` or `Slow_queries` growing over time is normal. Use deltas/rates and correlate with uptime.

**Using `Threads_connected` in place of `Threads_running`.** A large number of `Sleep` connections may represent a normal pool or a connection leak; a small number of `Threads_running` stalled on slow I/O can still severely degrade service.

**Killing every long-sleeping connection.** A `Sleep` session can hold transactions and locks. Identify the transaction, owner, and rollback impact before terminating.

**Treating `Seconds_Behind_Source = 0` as absolute proof of replica sync.** Inspect I/O/SQL states, GTIDs, errors, and topology. This single value does not replace failover procedures.

**Verifying backups solely by exit code.** Verify checksums/manifests and run restore tests. An untested backup is an unverified assumption.

**Changing configuration without recording the source.** After a restart, values can revert to config files or other overrides. Check `variables_info`, persisted settings, and startup config.

**Using identical alert thresholds across all environments.** Baselines and SLOs differ by workload. Base thresholds on actual data and rate of approach to limits.

**Writing runbooks without stop conditions.** Operators may keep going when targeting the wrong node role, lacking backups, or exceeding impact boundaries. Every runbook must state clearly when to stop and escalate.

**Saving raw output containing sensitive data.** SQL text, hosts, usernames, and literals can expose secrets. Sanitize data before placing it in tickets or widely accessible log stores.

## 19. Hands-On Exercise: Creating a Health Snapshot and Runbook

Use a test MySQL instance or an environment authorized for observation. Never perform configuration changes on production solely to complete an exercise.

**Part A — Collect a health snapshot**

Run and save the results of the following groups:

~~~sql
SELECT
    NOW(6) AS captured_at,
    VERSION() AS mysql_version,
    @@hostname AS server_host,
    @@server_uuid AS server_uuid,
    @@global.read_only AS read_only,
    @@global.super_read_only AS super_read_only;

SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Uptime',
    'Threads_connected',
    'Threads_running',
    'Max_used_connections',
    'Connections',
    'Aborted_connects',
    'Slow_queries'
);

SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'max_connections',
    'innodb_buffer_pool_size',
    'performance_schema',
    'log_error'
);
~~~

Record the timestamp, server UUID, version, and role. Capture a second snapshot after a known interval; compute deltas for counters and explain which variables are gauges and which are counters.

**Part B — Inspect transactions and queries**

~~~sql
SELECT
    trx_mysql_thread_id AS connection_id,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
    trx_state,
    trx_rows_locked,
    trx_rows_modified
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

If Performance Schema statement summaries are available, retrieve the top digests by total time and compare against execution counts. Identify which queries have high total impact versus high average latency.

**Part C — Write a one-page runbook**

Pick one symptom such as rising connections, long-open transactions, replica lag, or nearly full disk. Write sections for: trigger, scope, preconditions, read commands, expected output, decision branches, permitted actions, stop conditions, verification, rollback/escalation, and evidence to record.

**Part D — Rehearse**

Have one person act as the on-call operator while another reads the runbook and verifies each step. Provide no verbal hints outside the document. Record missing privileges, missing commands, unclear outputs, or incomplete decision branches. Revise the runbook and rehearse again until someone else can execute it safely.

## 20. Checklist Before Concluding MySQL Is Healthy

- Have you verified the exact server UUID, version, and node role?
- Were liveness and readiness checked separately?
- Do `read_only`/`super_read_only` match the expected role?
- Are connection count, running threads, and new connection rate stable?
- Are there any unusual long transactions, lock waits, or deadlocks?
- Have query latency, rows examined, and digest workloads shifted?
- Do buffer pool, InnoDB, and table statistics show signals needing investigation?
- Have CPU, RAM, disk free, inodes, I/O latency, and networking been checked at the infrastructure layer?
- Is the error log free of crashes, restarts, TLS, InnoDB, or replication errors?
- Are replicas in the right state, with GTIDs and lag within business bounds?
- Is the latest backup valid and was a recent restore test successful?
- Do runtime and persisted configurations match change records?
- Do alerts have owners, baseline-grounded thresholds, and linked runbooks?
- Do runbooks include stop conditions, post-action verification, rollback, and escalation?
- Does evidence include timestamps, server identity, and redaction of sensitive data?

A reliable health check must show what state the system is in, which signals led to that conclusion, and who needs to take the next action. A good runbook enables someone else to repeat the process under pressure while staying within safe boundaries. When combining baselines, time-series metrics, backup/replication verification, and rehearsed runbooks, MySQL operations become observable, explainable, and continuously improvable.
