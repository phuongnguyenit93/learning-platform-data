# Scoping Timeframe, Blast Radius, Recent Changes, and Evidence

When MySQL encounters an incident, the initial symptom rarely points directly to the root cause. An application reporting timeouts could be caused by slow queries, lock waits, connection pool exhaustion, network errors, or an overloaded server. A lagging replica could be caused by increased write load on the source, an SQL applier error, slow I/O, or a large transaction. If you change configuration or restart the server immediately before collecting data, critical traces may vanish and the impact scope becomes much harder to determine.

An effective troubleshooting approach starts with four questions: **when did the incident start, what is the blast radius, what changed recently, and what evidence confirms the hypothesis?** This lesson belongs to the **Troubleshooting** chapter of the **DATABASE_MYSQL** module. On the path to mastering MySQL—from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, access control, backup, and operations—scoping skills turn scattered symptoms into a verifiable line of investigation.

## 1. The Four Axes of Investigation

Do not start by guessing a single cause. Record the four axes first:

| Axis | Questions | Example Evidence |
|---|---|---|
| Timeframe | When did it start? Is it continuous or intermittent? When was the last known good state? | Timeline, timestamp logs, deploy time, server uptime |
| Scope | Who and which components are affected? All queries or a specific endpoint, tenant, node, or operation type? | Error request rate, host, connection ID, query digest |
| Recent Changes | What changed right before the error occurred? | Deploy, DDL, index, configuration, traffic, failover, driver |
| Evidence | What data can be directly observed and re-verified? | Error log, metrics, Performance Schema, EXPLAIN, replication status |

Each hypothesis should be documented separately with supporting evidence, contradicting evidence, and the next verification check. For example, "p95 increased after adding an index" is a temporal correlation; you need to inspect the query plan, rows examined, I/O, and workload before concluding that the index caused the slowdown.

## 2. Recording Symptoms and Timeframe

Open a brief incident record as soon as you receive an alert. At a minimum, record:

- Detection time and estimated start time.
- The most recent time the system was confirmed healthy (last known good).
- Timestamp timezone; prefer normalizing the timeline to UTC.
- Specific symptom: connection refused, timeout, SQL error, incorrect data, slow query, replica lag, or loss of write capability.
- Impact rate: number of failed requests out of total requests, number of affected tenants or users.
- Components: application, MySQL instance, primary/replica, Router, proxy, connection pool, or network.
- Person/process that performed changes or remediation actions, along with timestamps.

Do not write "database has been slow since morning" when you can write "p95 for the order creation endpoint increased from 120 ms to 2.4 s between 09:12–09:18 UTC; read requests remain normal while write request timeouts increased". A quantitative description helps other teams verify the exact same phenomenon.

### Normalizing Time

The application, MySQL, operating system, proxy, and monitoring tools may use different timezones. Check the MySQL timezone:

~~~sql
SELECT
  UTC_TIMESTAMP(6) AS observed_utc,
  NOW(6) AS session_now,
  @@GLOBAL.time_zone AS global_time_zone,
  @@SESSION.time_zone AS session_time_zone,
  @@system_time_zone AS system_time_zone;
~~~

Record the timezone when exporting logs from each system. If host clocks drift apart, the timeline may make a change appear to occur after the incident even though it actually happened before. Verify time synchronization across hosts and log services.

### Identifying the Last Known Good State

Compare monitoring data against the most recent deployment timestamp. Find the first inflection point in latency, error rate, throughput, CPU, I/O, connection count, or replication lag. Do not rely solely on when the first user reported an error; the incident may have started earlier before crossing alert thresholds.

## 3. Determining Blast Radius

Scope often narrows down the root cause faster than a single error message. Ask across each layer:

| Scope | How to Distinguish |
|---|---|
| System-wide vs. single application | Are multiple services failing together or only one service using MySQL? |
| All users vs. one group | Is it concentrated by tenant, region, account, or data type? |
| All databases vs. one schema | Are queries to other schemas behaving normally? |
| Reads vs. writes | Are SELECTs running while INSERT/UPDATEs time out? |
| One query vs. many queries | Did a single digest increase in duration or did overall query latency rise together? |
| One node vs. entire topology | Is the primary failing, a replica failing, Router failing, or are all members affected? |
| New connections vs. existing connections | Authentication error on connect, or are active sessions timing out? |
| Continuous vs. periodic | Do errors coincide with batch jobs, backups, reporting, or traffic peaks? |

Examples:

- Only write requests are slow while reads are normal: check locks, long-running transactions, index maintenance, binlog, and I/O.
- Only one tenant is failing: check that tenant's data, unique keys, partitioned queries, privileges, or parameters.
- All services cannot open new connections while old sessions still run: check network, DNS, TLS, authentication, `max_connections`, and pool settings.
- Only a replica is lagging: check receiver/applier, relay log, large transactions, and replica resources.
- Many unrelated queries increase in latency together: suspect shared resources or contention before tuning individual SQL statements.

Do not overstate the conclusion beyond the evidence. If only one endpoint was measured, say "this endpoint is affected"; there is not yet enough basis to say "all of MySQL is slow".

## 4. Building a Timeline of Recent Changes

Create a timeline combining application and database events. Changes to inspect include:

- Application deployments, ORM updates, JDBC driver, or Connector/J changes.
- DDL migrations: adding/dropping columns, indexes, constraints, partitions, or changing data types.
- Changes to SQL, query plans, prepared statements, or batch sizes.
- Changes to SQL mode, timezone, isolation level, charset/collation, or optimizer settings.
- Connection pool changes: maximum pool size, timeout, lifetime, init SQL.
- Changes to MySQL version, patches, plugins, authentication, or server configuration.
- Failover, restart, primary switchover, adding/removing replicas, or Router changes.
- Backups, restores, `ANALYZE TABLE`, import/export, log purging, or batch jobs.
- Sudden spikes in traffic, data volume, connection count, or transaction size.
- Infrastructure changes: CPU, RAM, disk, filesystem, network, DNS, firewall, TLS certificates, and secrets.

Example timeline table:

| Time (UTC) | Event | Scope | Verification Source |
|---|---|---|---|
| 08:55 | Deployed new API version | orders service | deployment record |
| 09:02 | Write p95 increased | create-order endpoint | APM |
| 09:04 | Lock waits increased | MySQL primary | Performance Schema |
| 09:06 | Deploy rollback started | orders service | deployment record |
| 09:12 | Lock waits and p95 dropped | create-order endpoint | APM + DB metrics |

This table is only an example format. Do not enter assumed events into a real incident record; every milestone must have a log entry or human confirmation. Temporal correlation helps prioritize checks, but technical evidence is still required to establish causality.

### Changes That May Not Appear in Deploy Logs

Manual changes in production, cron jobs, the event scheduler, DBA scripts, or console actions may not appear in CI/CD history. Ask explicitly who ran the command, on which instance, with which account, and at what time. Cross-check audit logs if enabled and within the retention policy.

## 5. Preserving Evidence Before Changing State

Before restarting, killing sessions, purging logs, resetting replication, or changing optimizer settings, collect existing evidence. Those actions can erase state needed to identify the root cause.

A baseline evidence bundle should include:

1. Timeline and blast radius.
2. MySQL version, relevant configuration, and uptime.
3. Error log along with application/proxy logs within the incident window.
4. Snapshot metrics and status counters.
5. Active sessions, query digests, and lock waits.
6. InnoDB status if locks/deadlocks are suspected.
7. Replication status if replicas exist.
8. Query plan and representative parameters if a specific query is slow.
9. Recent changes and results of each mitigation step.

Record timestamp, source, host/instance, and collection method for each sample. Mask passwords, tokens, emails, personal data, and sensitive literals before sharing logs. `SQL_TEXT` may contain user-supplied values; retain only what is necessary per security policy.

## 6. Initial Instance State Inspection

Start with read-only statements:

~~~sql
SELECT
  VERSION() AS mysql_version,
  @@version_comment AS version_comment,
  @@hostname AS hostname,
  @@port AS port,
  @@server_id AS server_id,
  @@server_uuid AS server_uuid;

SHOW GLOBAL STATUS LIKE 'Uptime';
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Max_used_connections';
SHOW GLOBAL STATUS LIKE 'Aborted_connects';
SHOW GLOBAL STATUS LIKE 'Connections';
SHOW GLOBAL STATUS LIKE 'Slow_queries';
~~~

Status values are typically cumulative counters since startup or the last status reset. A single value does not show the rate of increase. Take two snapshots separated by a known interval and compute the delta; also check `Uptime` to detect recent server restarts.

For example, if `Connections` increases by 12,000 in 5 minutes, that is roughly 40 connection attempts per second during that window. Cross-check with pool behavior and traffic before concluding abnormal connection churn.

### Process List

~~~sql
SHOW FULL PROCESSLIST;
~~~

Or inspect sessions via Performance Schema:

~~~sql
SELECT
  PROCESSLIST_ID,
  PROCESSLIST_USER,
  PROCESSLIST_HOST,
  PROCESSLIST_DB,
  PROCESSLIST_COMMAND,
  PROCESSLIST_TIME,
  PROCESSLIST_STATE,
  LEFT(PROCESSLIST_INFO, 300) AS statement_sample
FROM performance_schema.threads
WHERE TYPE = 'FOREGROUND'
ORDER BY PROCESSLIST_TIME DESC;
~~~

Look for long-running sessions, lock waits, I/O waits, or abnormal states. A session with a high `TIME` is not necessarily an error; it may be running a valid batch query or sitting idle in a transaction. Read `STATE`, the SQL statement, transaction state, and blocker before acting.

## 7. Finding Errors in the Error Log and Slow Query Log

Get the error log location:

~~~sql
SHOW VARIABLES LIKE 'log_error';
~~~

The path and access method depend on the MySQL installation or managed service. On cloud services, logs may be exported via console/monitoring instead of reading files directly. Look for messages within the incident window such as crash recovery, InnoDB errors, disk full, access denied, aborted connections, replication errors, plugin/TLS failures, or shutdown/restart.

Check the slow query log configuration:

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'slow_query_log',
  'long_query_time',
  'log_output',
  'log_queries_not_using_indexes'
);
~~~

The slow log helps identify queries exceeding the logging threshold, but it does not capture every kind of application latency. A request can be slow waiting on the connection pool, DNS, TLS, network, or locks before the SQL statement executes. Therefore, correlate the slow log with APM and Performance Schema.

Do not enable `log_queries_not_using_indexes` or set `long_query_time` too low in production without evaluating log volume, disk space, and overhead. If temporary enabling is needed, define the window, owner, log destination, and time to disable/restore the configuration.

## 8. Isolating Slow Queries with Performance Schema

Digest tables aggregate similar statements by SQL structure. Example to retrieve digests consuming the most total time:

~~~sql
SELECT
  SCHEMA_NAME,
  DIGEST,
  LEFT(DIGEST_TEXT, 200) AS query_sample,
  COUNT_STAR,
  ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_seconds,
  ROUND(MAX_TIMER_WAIT / 1000000000000, 6) AS max_seconds,
  SUM_ROWS_EXAMINED,
  SUM_ROWS_SENT,
  SUM_ERRORS,
  SUM_WARNINGS
FROM performance_schema.events_statements_summary_by_digest
WHERE SCHEMA_NAME IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

Timers in Performance Schema are expressed in picoseconds; divide by (10^{12}) to convert to seconds. Summaries are cumulative figures since server startup or the last summary reset. Take start/end snapshots and compute deltas if you need to analyze a specific window.

How to read the output:

- High `COUNT_STAR`: the digest is executed frequently.
- High `AVG_TIMER_WAIT`: high average execution time per call.
- High `SUM_ROWS_EXAMINED` relative to `SUM_ROWS_SENT`: may be scanning many rows to return few rows.
- Increasing `SUM_ERRORS` or `SUM_WARNINGS`: SQL errors or warnings requiring classification.
- High `MAX_TIMER_WAIT`: anomalous execution outlier; find the exact timestamp and request in more detailed logs/telemetry.

Digest summaries do not provide per-request p95/p99. Use APM or application-layer histograms for percentiles; use digests to identify high-cost SQL statement groups.

If Performance Schema consumers/instruments are not enabled or the table has no data, note that limitation. Do not reset all summaries in production just to restart measurements if other operations teams rely on the current metrics.

## 9. Checking Lock Waits and Deadlocks

If write requests are slow or timing out, inspect waiting transactions and blocking transactions.

~~~sql
SELECT
  w.REQUESTING_ENGINE_TRANSACTION_ID,
  w.BLOCKING_ENGINE_TRANSACTION_ID,
  r.OBJECT_SCHEMA,
  r.OBJECT_NAME,
  r.INDEX_NAME,
  r.LOCK_TYPE,
  r.LOCK_MODE AS requesting_lock_mode,
  b.LOCK_MODE AS blocking_lock_mode
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS r
  ON r.ENGINE = w.ENGINE
 AND r.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS b
  ON b.ENGINE = w.ENGINE
 AND b.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
~~~

Join with `performance_schema.threads`, `events_transactions_current`, and `events_statements_current` to identify the connection, SQL statement, and transaction involved. Exact column structures should be verified against the running MySQL version.

Retrieve InnoDB status:

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

The `TRANSACTIONS` section shows active transactions and lock waits; `LATEST DETECTED DEADLOCK` records the most recent deadlock detected by InnoDB. This is a point-in-time snapshot, not a full history of all deadlocks. If history is needed, use error logs/monitoring or appropriate deadlock logging configuration.

A deadlock detected by InnoDB usually causes one transaction to be rolled back to break the wait cycle. The application must handle deadlock errors with bounded retries and appropriate backoff. Do not infinitely retry a transaction guaranteed to conflict.

**Do not kill a session solely because `PROCESSLIST_TIME` is high.** Before intervening, identify whether the session is blocking or waiting, its owner, statement, what data the transaction has modified, and the impact of rollback. Killing the wrong session can prolong rollback time or cause further disruption.

## 10. Checking Connections and Connection Pools

If the application reports inability to acquire a connection, distinguish the layers:

1. Application cannot resolve hostname or reach the port.
2. TLS handshake or certificate failure.
3. Authentication/authorization rejected.
4. MySQL reached its connection limit.
5. Connection pool exhausted because requests hold connections too long or leak them.
6. Connection is established, but the query waits on locks/resources.

Status variables to inspect:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Threads_connected',
  'Threads_running',
  'Max_used_connections',
  'Aborted_connects',
  'Connections'
);

SHOW VARIABLES LIKE 'max_connections';
~~~

Compare `Max_used_connections` with `max_connections`, track `Threads_connected` over time, and inspect pool active/idle/pending counts on the application side. `Threads_connected` is the number of currently connected sessions; `Threads_running` is the number of threads not sleeping. They do not replace pool wait or request latency measurements.

If `Threads_connected` is high while `Threads_running` is low, the application may be holding many idle connections or have an oversized pool. If pool pending increases while MySQL still has plenty of free connections, inspect pool sizing, leaks, timeouts, and proxy limits. If MySQL hits `max_connections`, find the source opening connections and its growth rate before raising the limit; increasing `max_connections` can increase memory usage and contention.

On the application side, collect HikariCP metrics such as active, idle, pending, maximum pool size, and connection acquisition time. Do not look only at MySQL connection counts to conclude the pool is healthy.

## 11. Checking Replication When Scope Only Affects Replicas

For MySQL 8.0.22 and later, use:

~~~sql
SHOW REPLICA STATUS\G
~~~

On older versions, the syntax is `SHOW SLAVE STATUS\G`. Record at minimum:

- Receiver and applier thread states.
- `Last_IO_Error` and `Last_SQL_Error`.
- Received and executed GTIDs.
- Pending relay logs.
- `Seconds_Behind_Source` if provided.
- Timestamp of the last received/applied transaction.

Do not rely solely on `Seconds_Behind_Source` to conclude a replica is in sync. The value can be `NULL` or fail to reflect the full state when receiver/applier threads are stopped, when the source is idle, or when there are timestamp issues. Cross-check GTIDs, relay logs, worker status, and specific errors.

With parallel appliers, inspect workers and the coordinator in Performance Schema. A single failed worker can stop the applier or cause a backlog. Identify the failing transaction before skipping or resetting replication; skipping a transaction can cause replica data to diverge from the source.

## 12. Checking Query Plans When Only One Query Is Affected

If a single digest or endpoint stands out, obtain a representative SQL statement with the parameter set that triggered the issue. Inspect the plan:

~~~sql
EXPLAIN FORMAT=JSON
SELECT
  id,
  customer_id,
  created_at,
  total_amount
FROM orders
WHERE customer_id = 1001
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
~~~

Inspect access type, key, estimated rows, join order, temporary table, filesort, and partition pruning. If actual rows and iterator timings are needed, use `EXPLAIN ANALYZE` in a safe environment or on an evaluated `SELECT` query:

~~~sql
EXPLAIN ANALYZE
SELECT
  id,
  total_amount
FROM orders
WHERE customer_id = 1001
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
~~~

`EXPLAIN ANALYZE` executes the query. Do not run it blindly on very heavy queries or on an overloaded production server. Compare estimated rows with actual rows, inspect index/histogram statistics, and check parameter values. Do not add indexes or force the optimizer before knowing the read, write, and storage cost of that change.

## 13. Categorizing Symptoms and First Investigation Paths

| Symptom | Priority Investigation Path |
|---|---|
| Cannot connect to MySQL | DNS, network, TLS, auth, port, `max_connections`, pool pending |
| Many queries slow together | CPU, RAM, disk I/O, network, connection pool, backup/batch, global lock |
| Single query slow | Digest, parameters, EXPLAIN, rows examined, index, statistics |
| Slow writes, normal reads | Lock waits, long transactions, index maintenance, redo/binlog, I/O |
| Deadlocks increasing | Transaction boundaries, row update order, indexes, and retry logic |
| Replica lag | Receiver/applier, worker errors, relay log, large transactions, I/O |
| Incorrect or missing data | Migration/import, transaction boundaries, duplicate handling, timezone/collation, replication |
| Only one tenant failing | Tenant data and cardinality, parameters, privileges, unique keys, and partitioned queries |
| Errors after deploy | Code diff, SQL, driver, migration, config, and rollout timing |
| Errors after restart | Error log, crash recovery, config/plugin, connection pool reconnect, replication rejoin |

This table is a starting point, not an automatic conclusion. One symptom can have multiple causes; always verify with data from the affected instance and requests.

## 14. Controlled Hypothesis Testing

After gathering evidence, rank hypotheses by likelihood and impact. Each hypothesis needs a test that distinguishes it from other causes.

Examples:

| Hypothesis | Evidence to Look For | Next Verification Check |
|---|---|---|
| A new index slowed the query | Plan changed, rows examined or I/O increased after migration | Compare EXPLAIN and benchmark on before/after snapshots |
| Long transaction causing lock waits | Long-running blocker, long open transaction, write requests waiting | Identify blocker owner and SQL; cross-check transaction log |
| Pool connection exhaustion | Hikari pending/active hitting limit, acquisition time increasing | Cross-check pool metrics with `Threads_connected`/`Threads_running` |
| Replica cannot keep up | Relay log backlog, busy or errored workers | Inspect replica status, worker status, and resources |
| SQL mode changed | `@@SESSION.sql_mode` differs from baseline, new conversion errors | Compare config and session state on failing connections |

Change one factor at a time in a test environment whenever possible. If mitigation is required in production, record the pre-change value, operator, timestamp, scope, and evaluation criteria. Do not simultaneously change indexes, pool size, isolation level, and optimizer settings, as it becomes hard to tell which change had an effect.

## 15. Choosing Mitigation Actions

Clearly separate **evidence collection**, **mitigation**, and **root cause fix**. Mitigation aims to restore service; it does not by itself prove the root cause.

Common actions to consider:

- Throttle or pause competing batch/reporting jobs after confirming the owner and business impact.
- Rate-limit traffic or enable backpressure if the connection pool or server is overloaded.
- Roll back the application or migration only when schema compatibility holds and a clear data plan exists.
- Shift traffic to another replica/primary only via a tested failover procedure.
- Kill a blocking transaction only after verifying the owner, SQL statement, modified data, and potential rollback duration.
- Raise resource limits only when metrics prove that limit is the bottleneck and the host has headroom.

Avoid reflexive destructive actions such as `RESET MASTER`, deleting relay logs, skipping transactions, dropping indexes, deleting data, flushing/resetting status, or repeated restarts. Some actions destroy evidence or alter replication state and data. Perform them only when the goal, consequences, backup/restore path, and approver are clearly established per operational procedures.

## 16. Incident Record and Handoff Template

You can use the following template in a ticket or incident channel:

~~~text
Incident ID:
Environment / cluster / instance:
Start time (UTC):
Detection time (UTC):
Last known good (UTC):

Observed symptoms:
Blast radius:
- Application / endpoint:
- Tenant / user group:
- Read / write:
- Primary / replica / Router:
- Error rate and latency:

Recent changes:
- Deploy / migration / config:
- Traffic / batch / backup:
- Infrastructure / network / certificate:
- Operator and timestamp:

Evidence:
- Error/application log:
- MySQL version, uptime, and status delta:
- Processlist / digest:
- Lock wait / InnoDB status:
- Replication status:
- Query plan:
- Host and pool metrics:

Hypothesis:
Supporting evidence:
Contradicting evidence:
Next verification check:

Mitigation performed:
Result after mitigation:
Remaining risk / owner:
~~~

During handoff, clearly distinguish three types of information:

- **Fact:** direct observation with timestamp and source.
- **Hypothesis:** explanation currently under investigation.
- **Decision/action:** action already taken or decision confirmed by an authorized person.

Do not write a hypothesis as though it were the root cause. If data is insufficient, write "undetermined" and state the exact missing data sample.

## 17. Ordered Triage Procedure

1. **Describe the symptom:** write it in terms of metrics, SQL errors, or observed user behavior.
2. **Normalize the timeline:** UTC, first seen, last known good, server uptime, and deploy times.
3. **Define the blast radius:** application, tenant, schema, query, read/write, node, and new/existing connections.
4. **List recent changes:** deploy, DDL, config, traffic, backup, failover, infrastructure.
5. **Preserve evidence:** logs, status snapshots, processlist, digests, lock waits, and replication state.
6. **Categorize the symptom:** connectivity, resource, query, locking, replication, correctness, or compatibility.
7. **Form testable hypotheses:** state supporting/contradicting evidence and the next verification step.
8. **Mitigate with control:** record before/after state and impact.
9. **Verify recovery:** latency, error rate, throughput, data, and replica state return within thresholds.
10. **Document root cause and prevention:** conclude only with sufficient evidence; add missing alerts, tests, or runbooks.

## 18. Key Takeaways

- The first four questions are timeframe, blast radius, recent changes, and evidence.
- Normalize timestamps to UTC and identify the last known good state.
- Distinguish system-wide failures from issues isolated to an endpoint, tenant, node, or operation type.
- A deploy/migration/config timeline helps prioritize investigation but does not by itself prove causality.
- Preserve error logs, status deltas, processlist, digests, lock waits, and replication state before making changes.
- Status counters are cumulative; take snapshots and deltas, and check `Uptime`.
- Performance Schema digests help identify notable SQL groups; APM is required to measure p95/p99.
- Lock waits require identifying both the requester and the blocker; do not kill sessions based solely on execution time.
- Replica lag requires cross-checking receiver, applier, GTIDs, relay logs, and worker errors.
- Test hypotheses one step at a time, clearly separate facts/hypotheses/actions, and verify after mitigation.

A good MySQL investigation produces a handoff-ready chain of evidence: quantified symptoms, a normalized timeline, a clear scope, relevant changes, and tests performed. When every action is grounded in evidence and followed by measured outcomes, the operations team can restore service while preserving the ability to find the root cause.

## References

- [MySQL 8.0 Reference Manual: MySQL Server Logs](https://dev.mysql.com/doc/refman/8.0/en/server-logs.html)
- [MySQL 8.0 Reference Manual: The Slow Query Log](https://dev.mysql.com/doc/refman/8.0/en/slow-query-log.html)
- [MySQL 8.0 Reference Manual: SHOW PROCESSLIST](https://dev.mysql.com/doc/refman/8.0/en/show-processlist.html)
- [MySQL 8.0 Reference Manual: Performance Schema Statement Summary Tables](https://dev.mysql.com/doc/refman/8.0/en/performance-schema-statement-summary-tables.html)
- [MySQL 8.0 Reference Manual: InnoDB Standard Monitor and Lock Monitor](https://dev.mysql.com/doc/refman/8.0/en/innodb-standard-monitor.html)
- [MySQL 8.0 Reference Manual: InnoDB Locking](https://dev.mysql.com/doc/refman/8.0/en/innodb-locking.html)
- [MySQL 8.0 Reference Manual: Replication Monitoring](https://dev.mysql.com/doc/refman/8.0/en/replication-monitoring.html)
