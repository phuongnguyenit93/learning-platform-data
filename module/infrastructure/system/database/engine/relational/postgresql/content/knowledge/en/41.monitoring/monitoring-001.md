# Selecting Metrics by Latency, Throughput, Errors, and Resources in PostgreSQL

Monitoring PostgreSQL is not just about looking at CPU, RAM, or connection counts. A database can have low CPU usage while queries are still slow because they are waiting on locks; replication can be streaming while replay lag is growing; a disk can have plenty of free space while I/O latency is high; a transaction rate can look steady while the error rate is rising. To understand whether a system is healthy or having trouble, you need to select metrics around operational questions.

The four primary signal groups:

- **Latency:** how long an operation takes from start to completion.
- **Throughput:** how much work the system processes per unit of time.
- **Errors:** how many operations fail, time out, get retried, or fail to return the expected result.
- **Resources:** how CPU, memory, storage, I/O, network, and connection capacity are being utilized or saturated.

These four groups must be read together. Rising throughput can mean healthy growth, or it can mean a retry storm. Low average latency can hide a very slow p99 request tail. High CPU can come from useful workload or from a poor query plan. A rising error rate can originate from the database, the application, the network, or an external dependency.

```text
                  Users / applications
                         |
                         v
                  PostgreSQL service
                         |
       +-----------------+-----------------+
       |                 |                 |
       v                 v                 v
    Latency           Throughput         Errors
  p50/p95/p99       tx/s, rows/s       SQLSTATE, timeout
       |                 |                 |
       +-----------------+-----------------+
                         |
                         v
                     Resources
            CPU / memory / disk / I/O / network
                         |
                         v
                 SLO, alerts, runbooks
```

This lesson belongs to the **Database Engine Relational PostgreSQL** module, chapter **Monitoring**, on the topic **“Selecting Metrics by Latency, Throughput, Errors, and Resources”**. Its goal is to build an approach for choosing meaningful metrics, understanding PostgreSQL data sources, designing actionable dashboards and alerts, and connecting metrics to SLOs and operational root causes.

---

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish metrics, logs, traces, events, and profiles.
2. Explain the four signal groups: latency, throughput, errors, and resources.
3. Use the RED model to observe rate, errors, and duration.
4. Use the USE model to observe resource utilization, saturation, and errors.
5. Choose latency percentiles p50, p95, and p99 appropriate for an SLO.
6. Distinguish application-side, connection, query execution, and transaction latency.
7. Measure throughput using transaction rate, query rate, rows, and WAL generation.
8. Distinguish counters, gauges, histograms, and summaries.
9. Compute rates from cumulative counters and handle stats resets.
10. Track error rates, SQLSTATE, deadlocks, timeouts, and cancellations.
11. Analyze CPU, memory, disk capacity, IOPS, throughput, and I/O latency.
12. Monitor connection usage, pool saturation, and transaction age.
13. Use pg_stat_activity, pg_stat_database, and pg_stat_statements.
14. Use pg_stat_replication, pg_stat_wal_receiver, and pg_replication_slots.
15. Use pg_stat_user_tables, pg_stat_user_indexes, and progress views.
16. Understand version differences in pg_stat_io, pg_stat_bgwriter, and pg_stat_checkpointer.
17. Combine PostgreSQL statistics with OS/cloud metrics.
18. Design dashboards around workloads, service objectives, and failure modes.
19. Create alerts based on symptoms, trends, duration, and impact.
20. Distinguish alert thresholds, warnings, critical alerts, and SLO burn rate.
21. Avoid high cardinality, sensitive labels, and ownerless metrics.
22. Build baselines, capacity forecasts, and diagnostic runbooks.
23. Evaluate the impact of changes using before/after metrics.

**Scope:** Modern PostgreSQL. Some statistics views and columns change across major versions. pg_stat_io is available from PostgreSQL 16; checkpoint/background writer statistics changed significantly in PostgreSQL 17. Always verify against the catalogs of the deployed version. The examples use common columns and require verifying access permissions.

---

## 2. What Questions Should Monitoring Answer?

A metric is only useful when it helps answer a concrete question.

| Question | Signal Group | Example |
| --- | --- | --- |
| Are users waiting too long? | Latency | p95 query/transaction latency |
| How much work is the system processing? | Throughput | transactions/s, queries/s |
| How many operations are failing? | Errors | error rate, timeout, deadlock |
| Which resource is running out? | Resources | CPU, disk free, connections |
| Is the standby keeping up? | Latency + throughput | replay lag, WAL rate |
| Is vacuum keeping up? | Throughput + resources | dead tuples, vacuum duration |
| Is the backup still usable? | Errors + freshness | last successful backup, restore test |
| Is there a risk of data loss? | Errors + resources | archive failures, slot retention |
| Why is a specific query slow? | Latency + waits | query duration, wait_event, plan |

### 2.1. Start from the service, then move to the database

Users care about response time and business outcomes. PostgreSQL metrics explain part of the cause, while application metrics are needed to show which requests are slow, which endpoints are failing, and what the user impact is.

### 2.2. Metrics must have context

90% CPU usage may be normal during a batch window, yet concerning if API latency is rising and queue backlog is accumulating. A connection count of 500 may be normal with a large pool, yet dangerous if it is close to max_connections and many sessions are idle in transaction.

### 2.3. No single metric represents health

Combine latency, throughput, errors, resource saturation, and data state. Use multiple independent signals to avoid false conclusions.

---

## 3. The RED Model: Rate, Errors, Duration

RED is typically used for services or request paths.

### 3.1. Rate

Rate measures the number of requests/operations per unit of time, such as requests/s or transactions/s.

Questions:
- Is load increasing or decreasing?
- Is there an abnormal spike?
- After a deploy, how did throughput change?
- Are retries artificially inflating request counts?

### 3.2. Errors

Errors measure the number of failed requests or the failure rate.

Questions:
- What percentage of requests are failing?
- Are errors caused by SQL, timeouts, connections, constraints, or dependencies?
- Are errors concentrated on a specific endpoint or query family?
- How quickly is the error budget being consumed?

### 3.3. Duration

Duration measures how long requests take to process. You should track latency distributions and percentiles, not just averages. A small fraction of extremely slow requests can impact critical users even while the average remains low.

### 3.4. RED for PostgreSQL

| RED | Application/service | PostgreSQL |
| --- | --- | --- |
| Rate | Requests/s | Transactions/s, statements/s |
| Errors | HTTP 5xx, failed requests | SQL errors, deadlocks, cancellations, connection failures |
| Duration | Request latency | Query/transaction latency, lock wait, commit latency |

RED helps you start from user impact and drill down to the database.

---

## 4. The USE Model: Utilization, Saturation, Errors

### 4.1. Utilization

The proportion of time or capacity currently in use.

Examples:
- CPU busy percentage.
- Disk utilization.
- Network bandwidth utilization.
- Connection pool usage.
- Buffer/cache behavior must be interpreted properly; not all high cache usage is bad.

### 4.2. Saturation

The amount of work queued waiting because a resource cannot keep up.

Examples:
- CPU run queue.
- I/O queue depth.
- Requests waiting for a connection.
- Lock waiters.
- Disk queue.
- Exhausted worker slots.
- Continuously growing replication backlog.

### 4.3. Errors

Resource-level errors:
- Disk I/O errors.
- Read-only filesystem.
- Connection refused.
- Out-of-memory kill.
- Network retransmits/drops.
- WAL archive failures.

### 4.4. USE for PostgreSQL

| Resource | Utilization | Saturation | Errors |
| --- | --- | --- | --- |
| CPU | CPU busy | run queue, CPU pressure | throttling, steal |
| Memory | working set, cache | reclaim/swap pressure | OOM kill |
| Disk | capacity, busy time | queue depth, latency | I/O errors |
| Network | bandwidth | queue/retransmit | drops, resets |
| Connections | used/max | pool waiters | connection refused |
| WAL | generation/retention | archive/slot backlog | archive failures |
| Locks | lock count | blocked sessions | deadlocks |
| Workers | active/available | waiting jobs | worker launch failures |

### 4.5. Do not look only at utilization

At 40% overall CPU, saturation can still exist on a single core, a specific storage queue, or an individual connection pool. Look for queues and waiters, not just utilization percentages.

---

## 5. Latency: Measuring Time at the Right Layer

Latency is the elapsed time from a start boundary to an end boundary. Always define the measurement boundaries before comparing values.

### 5.1. Application request latency

From when the application receives a request until it returns the response. Includes:
- Queueing inside the application.
- Connection pool wait.
- Network round-trips to the database.
- SQL execution.
- Serialization and business logic.
- External dependencies.

This is usually the metric closest to user experience.

### 5.2. Connection acquisition latency

Time spent waiting to acquire a connection from the pool or establish a new connection. If the pool is exhausted, requests can become slow before a query even starts.

### 5.3. Query latency

Time spent executing a single statement in the database. Distinguish execution time, planning time, and time spent waiting on locks or I/O.

### 5.4. Transaction latency

Time from BEGIN to COMMIT/ROLLBACK. Long transactions can hold locks and snapshots, affecting many other queries.

### 5.5. Commit latency

Time COMMIT spends waiting for WAL flush or synchronous standby acknowledgement. It can increase when storage is slow or a synchronous replica/network is slow.

### 5.6. Lock wait latency

Time a query/session spends waiting on a lock. A query with a fast execution plan can still be slow if blocked.

### 5.7. Replication apply lag

Time delta or WAL position gap between primary and standby. Distinguish receive lag from replay lag.

### 5.8. Storage latency

Time to complete read/write I/O. Increased disk latency can affect checkpoints, WAL flushes, table scans, and vacuum.

---

## 6. Percentiles: p50, p95, and p99

Averages hide tail latency. Percentiles help reveal the distribution of response times.

### 6.1. p50

50% of requests complete at or below the p50 duration. This is the median, representing the middle of the distribution.

### 6.2. p95

95% of requests complete at or below p95. The remaining 5% are slower.

### 6.3. p99

99% of requests complete at or below p99. The remaining 1% are slower. At high workloads, 1% can still be a substantial number of requests.

### 6.4. Example

Suppose 10,000 queries have the following distribution:

| Metric | Time |
| --- | ---: |
| p50 | 8 ms |
| p95 | 70 ms |
| p99 | 900 ms |
| Average | 24 ms |

An average of 24 ms hides the fact that the p99 query group takes nearly a second. Investigating tail latency can uncover lock waits, cache misses, plan variations, or storage stalls.

### 6.5. Percentiles cannot be added arbitrarily

The p95 of query A plus the p95 of query B does not necessarily equal the p95 of a request containing both. To measure end-to-end request latency, instrument at the application boundary.

### 6.6. Histograms and buckets

Histograms record distributions in buckets, enabling approximate quantile calculation when aggregating across multiple instances. Buckets must have sufficient resolution around SLO thresholds.

### 6.7. Summaries and histograms

Summaries can compute quantiles per process, but accurate quantile aggregation across multiple instances is difficult. Histograms are usually better suited for distributed aggregation if buckets are well designed.

### 6.8. Choosing percentiles by goal

- p50: track typical experience.
- p95: detect common tail degradation.
- p99: detect tail latency affecting a smaller but important slice of requests.
- Max: useful for investigation, but highly sensitive to outliers and sample size.

Do not rely on p99 if request volume is too low for the percentile to be statistically meaningful.

---

## 7. Designing Latency SLOs

An SLO (Service Level Objective) is a service quality target over a defined time window.

Examples:
- 99% of read requests complete within 100 ms over a 30-day window.
- 99.9% of write transactions succeed within the agreed latency limit.
- 99.95% availability for write endpoints.

### 7.1. An SLO must define its scope

Specify the endpoint or workload, which requests are counted, whether timeouts/cancellations count as errors, the measurement window, the percentile or compliance ratio, and how maintenance or dependency outages are handled.

### 7.2. Database SLIs and application SLIs

Database query latency does not replace application request latency. Use database SLIs for diagnosis and application SLIs to measure user experience.

### 7.3. Error budget

If an SLO allows a certain fraction of failing requests, that allowance is the error budget. Burn rate indicates how fast the budget is being consumed.

### 7.4. Do not set SLOs around metrics just because they are easy to collect

Set objectives around user needs and business impact, then choose measurable metrics that reflect them.

---

## 8. Throughput: Measuring Work Done

Throughput is the amount of work completed per unit of time. Some metrics count operations; others measure bytes or rows.

### 8.1. Transactions per second

Can be estimated from commit/rollback counters in pg_stat_database:

```sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname IS NOT NULL;
```

These are cumulative counters. To calculate transactions/s, take the difference between two snapshots and divide by the elapsed time, accounting for stats_reset.

### 8.2. Queries per second

Not identical to transactions/s. One transaction can run multiple statements; prepared statements and batches also alter the relationship.

### 8.3. Rows processed

pg_stat_database provides database-level tuples returned/fetched/inserted/updated/deleted. These are aggregated counters and do not identify which specific query processed the rows.

### 8.4. WAL generation rate

pg_stat_wal provides WAL-related counters. The delta of wal_bytes over time helps estimate write workload and archive/replication capacity needs.

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    stats_reset
FROM pg_catalog.pg_stat_wal;
```

Column names and availability can vary by version. Check the target catalog to confirm.

### 8.5. I/O throughput

OS/cloud metrics report bytes read/written per second, IOPS, and queue depth. PostgreSQL-level counters help attribute I/O to databases/backends when supported by the version.

### 8.6. Replication throughput

Track WAL bytes sent/received/flushed/replayed and backlog. High throughput does not imply low lag if the source generates WAL faster than the standby can process it.

### 8.7. Do not use connection count as throughput

Connection count is the number of existing sessions, not the number of processed requests. An idle connection can stay open for hours.

---

## 9. Counter, Gauge, Histogram, and Summary

### 9.1. Counter

A counter only increases over time until a process/server restart or statistics reset.

Examples:
- xact_commit.
- blks_read.
- deadlocks.
- wal_bytes.
- archive failures.

To obtain a rate, compute the delta between two timestamps.

### 9.2. Gauge

A gauge can go up or down.

Examples:
- active connections.
- current sessions.
- disk free space.
- current WAL backlog.
- replication slot retained bytes.

Do not compute a rate from a gauge unless it is meaningful.

### 9.3. Histogram

A histogram places observations into buckets. Well suited for latency distributions, request sizes, or batch durations.

### 9.4. Summary

A summary provides count/sum and optionally quantiles per process/exporter. You must understand its limitations when aggregating across multiple instances.

### 9.5. Stats reset

PostgreSQL statistics can reset on server restart or when a stats reset is invoked. Use stats_reset to avoid computing negative or invalid rates.

### 9.6. Rate calculation

Suppose a counter increases from 1,000,000 to 1,006,000 over 60 seconds:

\[
\text{rate} = \frac{1{,}006{,}000 - 1{,}000{,}000}{60}
= 100 \text{ events/s}
\]

If a counter decreases due to a reset, do not interpret the negative delta as negative workload. Detect the reset and start a new baseline.

### 9.7. Scrape interval

An interval that is too long can miss short spikes; an interval that is too short creates overhead and high cardinality/storage cost. Choose it based on how fast failure modes develop and monitoring cost.

---

## 10. Error Metrics: Classify Instead of Counting Everything Together

Different errors carry very different severities. Classify them by type, source, and impact.

### 10.1. SQL errors

Examples:
- Syntax/invalid input.
- Unique violation.
- Foreign-key violation.
- Permission denied.
- Serialization failure.
- Deadlock detected.
- Query canceled.
- Statement timeout.

Some errors are expected business validations rather than a database outage.

### 10.2. Connection errors

- Connection refused.
- Too many connections.
- Authentication failure.
- TLS handshake failure.
- Connection reset.
- Pool acquisition timeout.

### 10.3. Transaction errors

- Deadlock.
- Serialization retry.
- Lock timeout.
- Statement timeout.
- Transaction rollback.

Track retry rates as well as retry success/failure counts.

### 10.4. Replication errors

- WAL receiver disconnect.
- Requested WAL segment missing.
- Timeline mismatch.
- Replication slot invalidation.
- Replay conflict.
- Replication lag exceeding policy.

### 10.5. Backup/archive errors

- Base backup job failed.
- Archive command failed.
- Restore command could not find segment.
- Checksum mismatch.
- Backup repository full.
- Restore drill failed.

### 10.6. Infrastructure errors

- Disk I/O error.
- Read-only filesystem.
- OOM kill.
- Node restart.
- Network packet loss.
- Cloud storage throttling.

### 10.7. SQLSTATE

PostgreSQL provides SQLSTATE codes for SQL errors. Group by class/code instead of parsing localized error text, while still preserving message/context for investigation.

Example classes:
- 08: connection exception.
- 22: data exception.
- 23: integrity constraint violation.
- 40: transaction rollback.
- 42: syntax/access rule.
- 53: insufficient resources.
- 55: object not in prerequisite state.
- 57: operator intervention.
- 58: system error.

Consult PostgreSQL Error Codes for the exact codes and full classification for your version.

### 10.8. Error rate

\[
\text{Error rate} =
\frac{\text{Failed operations}}{\text{Total operations}}
\]

State the denominator explicitly: requests, transactions, statements, or connections. Do not mix SQL validation error counts with server availability errors.

---

## 11. Deadlocks, Lock Waits, and Blocked Sessions

Lock contention is often why latency spikes even while CPU remains low.

### 11.1. Inspect active sessions and wait events

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    now() - xact_start AS transaction_age,
    left(query, 200) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE state <> 'idle'
ORDER BY query_start NULLS LAST;
```

Appropriate privileges are required to view query text from other sessions; sensitive data may be masked depending on permissions and configuration.

### 11.2. Find blocked sessions

```sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.usename AS blocked_user,
    blocking.pid AS blocking_pid,
    blocking.usename AS blocking_user,
    now() - blocked.query_start AS blocked_for,
    left(blocked.query, 160) AS blocked_query,
    left(blocking.query, 160) AS blocking_query
FROM pg_catalog.pg_stat_activity AS blocked
JOIN LATERAL unnest(pg_catalog.pg_blocking_pids(blocked.pid))
    AS blocker_pid(pid) ON true
JOIN pg_catalog.pg_stat_activity AS blocking
    ON blocking.pid = blocker_pid.pid
ORDER BY blocked.query_start;
```

### 11.3. Deadlock counter

```sql
SELECT
    datname,
    deadlocks,
    stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname IS NOT NULL;
```

This is a cumulative counter; calculate the rate via delta.

### 11.4. Lock wait is not the same as deadlock

A lock wait can clear once the blocking transaction finishes. A deadlock is a dependency cycle, and PostgreSQL selects one transaction to abort.

### 11.5. Alert by duration and impact

One session waiting on a lock for a few milliseconds is very different from an important request blocked for 5 minutes. Alerts should consider the number of affected sessions, wait age, and workload.

---

## 12. Monitoring Queries with pg_stat_statements

pg_stat_statements is a widely used extension for aggregating statement execution statistics by query identity.

### 12.1. Enable the extension

Depending on configuration, add the extension to shared_preload_libraries and restart:

```conf
shared_preload_libraries = 'pg_stat_statements'
compute_query_id = auto
```

After starting the server and creating the extension in the database:

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

### 12.2. Query statements with high total time

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_written,
    left(query, 200) AS query_sample
FROM pg_catalog.pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Column names and semantics vary across versions. Older versions may use different column names, such as total_time/mean_time.

### 12.3. Total time vs. mean time

- High total_exec_time: query family consumes significant cumulative database time.
- High mean_exec_time: each call is slow on average.
- High calls: query is executed very frequently.
- High rows: query returns or processes many rows.
- High temp blocks written: query uses significant temporary files/blocks.

### 12.4. Do not sort only by mean

A 2-second query run once may have less impact than a 20 ms query run hundreds of thousands of times. Inspect calls, total time, and business criticality together.

### 12.5. Query normalization

pg_stat_statements typically groups similar queries by query ID and normalizes constants. This helps with aggregation, though it can hide differences caused by parameter values or plan variations.

### 12.6. Intentional statistics resets

Resetting clears historical baselines. Before resetting, save a snapshot or use a time-series exporter to retain history.

### 12.7. Query text can be sensitive

Queries can reveal table names, schemas, or literals depending on extension/configuration/version. Control permissions and retention on the monitoring store.

---

## 13. Database-Level Workload Monitoring

pg_stat_database provides aggregated counters per database.

```sql
SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    tup_returned,
    tup_fetched,
    tup_inserted,
    tup_updated,
    tup_deleted,
    conflicts,
    deadlocks,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname IS NOT NULL;
```

### 13.1. Cache hit ratio

Can be approximated as:

\[
\text{hit ratio} =
\frac{\text{blks\_hit}}
{\text{blks\_hit}+\text{blks\_read}}
\]

However, this is an aggregate metric and does not capture every I/O path. OS page cache, sequential scans, workload mix, and data size all affect it. Do not tune solely to chase a high hit ratio.

### 13.2. temp_bytes and temp_files

Increases can indicate sort/hash spills to disk, queries needing different memory/work_mem, or workload changes. Avoid raising work_mem globally without analysis, as it can be allocated concurrently by many operations/sessions.

### 13.3. conflicts

On a standby, conflicts can indicate read queries affected by WAL replay. Combine with pg_stat_database_conflicts and logs.

### 13.4. numbackends

This is the count of connected backends at snapshot time, not throughput, and it does not replace connection pool metrics.

### 13.5. Counters over time

Store timestamped snapshots to compute rates. Record stats_reset and handle server restarts.

---

## 14. Connections and Pool Saturation

### 14.1. Connections in use

```sql
SELECT
    state,
    count(*) AS sessions
FROM pg_catalog.pg_stat_activity
GROUP BY state
ORDER BY sessions DESC;
```

### 14.2. By database and application

```sql
SELECT
    datname,
    application_name,
    usename,
    state,
    count(*) AS sessions
FROM pg_catalog.pg_stat_activity
GROUP BY datname, application_name, usename, state
ORDER BY sessions DESC;
```

### 14.3. Compared to max_connections

```sql
SHOW max_connections;
```

Do not treat max_connections as a limit to keep increasing indefinitely. Each backend consumes memory and process resources. Connection pooling usually controls concurrency more effectively.

### 14.4. Idle in transaction

```sql
SELECT
    pid,
    usename,
    application_name,
    now() - xact_start AS xact_age,
    state,
    wait_event_type,
    wait_event,
    left(query, 160) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY xact_start;
```

Idle transactions can hold locks and snapshots and prevent vacuum from reclaiming dead tuples.

### 14.5. Required pool metrics at the application/proxy layer

- Pool size.
- Active/idle connections.
- Waiting clients.
- Acquisition latency.
- Connection creation rate.
- Connection errors.
- Queue timeouts.
- Recycle/reconnect rate.

### 14.6. Distinguish database full from pool full

An application can exhaust its pool connections even while PostgreSQL has spare slots. Conversely, PostgreSQL can run out of backend slots before a pool reaches its configured limit. Monitor both layers.

---

## 15. CPU and Query Execution

### 15.1. CPU utilization

OS/cloud metrics report CPU usage, per-core usage, run queue, steal/throttling, and CPU pressure. PostgreSQL statistics do not replace host metrics.

### 15.2. CPU saturation

A single-threaded query can saturate one core even while aggregate CPU looks low on a multi-core host. Check per-core and process-level CPU during investigation.

### 15.3. Query CPU attribution

pg_stat_statements provides execution time and calls, not exact CPU time for every query. Use appropriate OS profiling/observability tools when deep CPU attribution is needed.

### 15.4. Query plans

Use EXPLAIN to inspect plans. EXPLAIN ANALYZE executes the actual query, so it can cause side effects with DML or heavy load. Use transaction rollback for appropriate tests and avoid running heavy queries in production without assessment.

### 15.5. Plan regression

After a deploy, statistics update, or index change, a query plan can change. Compare calls, mean/total execution time, rows, buffers, and plans before and after.

### 15.6. High CPU is not necessarily bad

High CPU alongside rising throughput and stable latency can indicate efficient resource usage. High CPU accompanied by a growing run queue, rising p99, and flat throughput signals saturation.

---

## 16. Memory and Cache

### 16.1. shared_buffers

This is the shared memory region PostgreSQL uses to cache data pages. Track configuration and workload efficiency, rather than treating high usage as an error.

### 16.2. OS page cache

PostgreSQL also relies on the filesystem cache. Therefore, shared buffer reads do not always correspond to physical disk reads.

### 16.3. work_mem

Memory for operations such as sorts and hashes, typically applied per operation and potentially used concurrently by many sessions. Setting it too high can cause memory pressure.

### 16.4. maintenance_work_mem

Affects maintenance operations such as VACUUM and CREATE INDEX. Track maintenance duration alongside memory capacity.

### 16.5. Memory pressure

Monitor available/used memory, swap-in/swap-out, page faults, OOM kills, container memory limits, PostgreSQL process memory, and temporary file growth.

### 16.6. Do not draw conclusions from one process's RSS

PostgreSQL uses shared memory and multiple processes. Summing RSS across all backends can count shared pages multiple times. Use appropriate OS tools to inspect PSS/cgroup memory and understand shared mappings.

### 16.7. Cache hit ratio is not an independent goal

A high hit ratio can still coincide with slow queries due to CPU, locks, network, or specific cache misses. A large sequential-scan workload can produce a low hit ratio and still perform well.

---

## 17. Disk Capacity and I/O

### 17.1. Disk capacity

Track data filesystem free bytes/percent, WAL filesystem free space, tablespace usage, temporary storage, backup repository capacity, archive repository capacity, growth rate, and estimated time to full.

### 17.2. IOPS

Number of read/write operations per second. High IOPS alone does not tell whether workload behavior is good or bad; check I/O size, latency, and queue depth.

### 17.3. Throughput

Bytes read/written per second. Large sequential workloads produce high throughput with moderate IOPS; random I/O can consume many IOPS with lower byte throughput.

### 17.4. I/O latency

Measures how long I/O operations take to complete. Increasing latency commonly affects WAL flush, checkpoints, scans, vacuum, and temp files.

### 17.5. Queue depth

A growing queue indicates pending I/O requests. Combine with latency and utilization to detect saturation.

### 17.6. Separate WAL volume

If pg_wal is on a separate volume, monitor its capacity, latency, and throughput independently. Slow WAL flushes can increase commit latency.

### 17.7. Temporary files

temp_files/temp_bytes in pg_stat_database and OS disk metrics help detect query spills. Identify the query family before changing work_mem.

### 17.8. Do not alert only when disk is full

Disk growth rate can predict incidents early. Alerting on estimated time to full is more actionable than waiting for free space to drop near zero.

---

## 18. Checkpoints, WAL, and Background Writer

Checkpoints and WAL generation affect write I/O, recovery time, and latency.

### 18.1. WAL generation

Track wal_bytes/s, wal_records/s, and full-page images. Write spikes can increase WAL archiving and replication traffic.

### 18.2. Checkpoint frequency

Checkpoints that run too frequently can increase write pressure; checkpoints spaced too far apart can increase crash recovery work. Monitor checkpoint write/sync time and requested checkpoints.

### 18.3. Checkpoint metrics by version

Before PostgreSQL 17, many checkpoint/background writer counters lived in pg_stat_bgwriter. Starting in PostgreSQL 17, checkpoint statistics are separated into pg_stat_checkpointer, while pg_stat_bgwriter focuses on the background writer. Exact columns depend on version.

### 18.4. Checkpoint write/sync time

If checkpoint write/sync time rises alongside storage latency and query latency, inspect I/O capacity, checkpoint settings, and workload.

### 18.5. full_page_writes/FPI

Full-page images can increase WAL volume after a checkpoint. wal_fpi provides visibility into part of this activity; never disable full_page_writes to shrink WAL without understanding durability and corruption risks.

### 18.6. Background writer

The background writer writes dirty buffers before backends need to flush them. Monitor buffers_clean, buffers_backend, and buffers_backend_fsync as supported by your version.

---

## 19. pg_stat_io in PostgreSQL 16 and Later

pg_stat_io provides I/O statistics broken down by backend type, object, and context on supported versions.

Exploration example:

```sql
SELECT *
FROM pg_catalog.pg_stat_io;
```

### 19.1. Backend type

Allows distinguishing backend groups performing I/O, such as client backend, background writer, checkpointer, and others depending on version.

### 19.2. Object and context

Helps clarify I/O by object and context supported by the view, such as relation or temporary relation. Check the exact schema on the target server.

### 19.3. Counters

The view can report read/write counts, bytes, evictions, reuses, fsyncs, and timing fields depending on version.

### 19.4. Timing is not enabled by default in all configurations

Some timing metrics depend on track_io_timing or configuration conditions. Evaluate overhead before enabling broadly.

### 19.5. Does not replace OS I/O metrics

pg_stat_io helps analyze PostgreSQL activity; OS/cloud metrics are still required to see physical device latency, queues, and throttling.

---

## 20. Vacuum, Autovacuum, and Table Health

Vacuum affects bloat, transaction ID safety, and query performance.

### 20.1. Table activity

```sql
SELECT
    schemaname,
    relname,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_catalog.pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
```

### 20.2. Dead tuples

n_dead_tup is a statistical estimate, not an exact instantaneous count. Continuous growth may indicate vacuum is falling behind or a transaction is holding a snapshot open too long.

### 20.3. Vacuum progress

```sql
SELECT *
FROM pg_catalog.pg_stat_progress_vacuum;
```

Use this to see which phase vacuum is running and its progress on supported versions.

### 20.4. Analyze freshness

Stale statistics can cause the planner to pick poor plans. Track last_autoanalyze and workload shifts.

### 20.5. Transaction ID age

Database and table XID age must be monitored to prevent transaction ID wraparound. Alert before dangerous thresholds rather than waiting for emergency autovacuum.

### 20.6. Long transactions

Long-running transactions hold xmin/snapshots and can block vacuum cleanup. Monitor xact_start, backend_xmin, and idle-in-transaction sessions.

---

## 21. Index Usage and Index Health

### 21.1. Index statistics

```sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_catalog.pg_stat_user_indexes
ORDER BY idx_scan ASC
LIMIT 50;
```

### 21.2. Unused indexes

Low idx_scan may suggest an infrequently used index, but it is not enough on its own to drop it. Statistics may have been reset, workloads can be seasonal, or the index may serve a rare critical query.

### 21.3. Sequential scans

Sequential scans are not inherently bad. For small tables or queries needing most rows, a sequential scan can be optimal.

### 21.4. Index bloat

There is no single built-in metric that accurately measures all forms of bloat. Use catalog estimates or suitable extensions/tools and weigh the measurement cost.

### 21.5. Index build progress

```sql
SELECT *
FROM pg_catalog.pg_stat_progress_create_index;
```

Track CREATE INDEX/REINDEX progress on supported versions.

---

## 22. Replication and Standby Metrics

### 22.1. Primary-side replication

```sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_catalog.pg_stat_replication;
```

### 22.2. Standby receive/replay

```sql
SELECT
    pg_is_in_recovery(),
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();
```

### 22.3. WAL receiver

```sql
SELECT *
FROM pg_catalog.pg_stat_wal_receiver;
```

### 22.4. Replication slots

```sql
SELECT *
FROM pg_catalog.pg_replication_slots;
```

### 22.5. Measure both lag and retention

A standby may have growing lag while the primary still retains enough WAL. Conversely, a standby with low lag while a slot or archive is losing its ability to retain WAL also requires attention.

### 22.6. Sync state

Monitor sync_state and actual topology. If a synchronous standby disappears, commit behavior can change depending on synchronous_standby_names and policy.

### 22.7. Timeline

Record the timeline ID alongside LSN across failover/promotion events. Never compare LSNs across two divergent timelines as if they were on the same history.

---

## 23. Backup and Archive Metrics

### 23.1. Backup freshness

Essential metrics:
- Age of the latest base backup.
- Time of the last successful backup.
- Duration and bytes copied.
- Backup size growth.
- Verification status.
- Restore test age.

### 23.2. WAL archive

```sql
SELECT *
FROM pg_catalog.pg_stat_archiver;
```

Monitor failed_count, last_failed_time, and last_archived_time.

### 23.3. Archive gap

A recent last_archived_time does not prove every segment is continuous. Verify segment/timeline inventory and backup manifests.

### 23.4. Restore metrics

Measure download/copy duration, restore duration, WAL replay duration, startup duration, validation duration, and time to application-ready.

### 23.5. Backup success does not equal recoverability

Only a restore drill proves that the backup + WAL + config + credentials + extensions chain works in practice.

---

## 24. Errors in PostgreSQL Logs

Statistics views do not record every error. Logs must be configured to capture relevant events.

### 24.1. log_min_error_statement

Logs statements associated with errors at or above the configured severity. Be cautious with queries containing sensitive data.

### 24.2. log_min_duration_statement

Logs statements that run longer than the threshold. Can generate high log volume if set too low.

### 24.3. log_lock_waits

Logs information on lock waits exceeding deadlock_timeout. Useful when investigating contention.

### 24.4. log_checkpoints

Useful for observing checkpoint behavior; output details vary by version.

### 24.5. log_connections and log_disconnections

Helpful for investigating connection churn, though they can increase log volume.

### 24.6. log_line_prefix

Should include timestamp, PID/session, user, database, application_name, and appropriate transaction/session identifiers to correlate events.

### 24.7. Structured logging

CSV/JSON logs or a centralized log pipeline allow grouping by SQLSTATE, application_name, host, and time window.

### 24.8. Protecting logs

Logs can contain query text, object names, client IPs, and business data. Apply access control, masking, encryption, and retention according to policy.

---

## 25. Wait Events: Understanding What Queries Are Waiting On

pg_stat_activity exposes wait_event_type and wait_event for waiting sessions.

### 25.1. Lock

Lock wait events can indicate contention caused by another transaction holding a lock.

### 25.2. IO

I/O wait events indicate a backend is waiting on reads or writes. Correlate with OS storage latency to confirm.

### 25.3. Client

A session may be waiting on a client to read results or send data. Slow application consumers can keep backends occupied for long periods.

### 25.4. LWLock

Lightweight locks protect shared internal structures. LWLock waits can point to internal contention and require drilling down to the specific event.

### 25.5. IPC

Waits between processes/background workers can relate to coordination or parallel query execution.

### 25.6. Active does not mean using CPU

A session in state active with a wait_event is waiting. Counting active sessions alone can misjudge CPU demand.

### 25.7. Snapshot query

```sql
SELECT
    wait_event_type,
    wait_event,
    state,
    count(*) AS sessions
FROM pg_catalog.pg_stat_activity
WHERE state <> 'idle'
GROUP BY wait_event_type, wait_event, state
ORDER BY sessions DESC;
```

---

## 26. Progress Views for Long-Running Operations

PostgreSQL provides several progress views to monitor ongoing operations.

Examples:
- pg_stat_progress_vacuum.
- pg_stat_progress_create_index.
- pg_stat_progress_analyze.
- pg_stat_progress_cluster.
- pg_stat_progress_basebackup.
- pg_stat_progress_copy.

Verify view names and columns for your PostgreSQL version.

### 26.1. Why progress metrics matter

A long-running job may be completely normal if it is making steady progress. If progress stalls for a long period, it may have hit a lock, I/O bottleneck, or resource issue.

### 26.2. Do not alert on duration alone

CREATE INDEX on a large table can take hours. Monitor phase, progress, blocking, and the maintenance window.

### 26.3. Backup progress

pg_stat_progress_basebackup tracks running base backups on the source server on supported versions.

### 26.4. Copy progress

pg_stat_progress_copy is useful for bulk imports/exports. Combine bytes/tuples processed with application job state.

---

## 27. Metrics for Connection Pools and Applications

Database views cannot see the application's full request queue.

### 27.1. Application latency

Measure request duration at the API/service boundary. Tag with route, operation class, and outcome.

### 27.2. Pool wait

Measure time spent waiting for a connection. If pool wait increases while database query latency stays flat, the bottleneck may be pool sizing or leaked connections.

### 27.3. Retry rate

Retries can inflate database throughput counters and amplify overload. Track retry attempts and retry success.

### 27.4. Request concurrency

Count in-flight requests and queue depth. A system whose request arrival rate exceeds its service rate will build up a queue.

### 27.5. Query correlation

Attach a meaningful application_name to connections to distinguish services and jobs. Use trace/request identifiers in application logs; avoid putting unique IDs into metric labels.

### 27.6. Connection pooler

If using PgBouncer or a proxy, monitor client connections, server connections, pool waiters, wait time, pool saturation, connection errors, and transaction/statement pooling behavior.

---

## 28. Cardinality and Metric Label Quality

### 28.1. Cardinality is the number of label combinations

A metric with labels such as environment, cluster, instance, database, and state generally has bounded cardinality. Adding user ID, request ID, or raw SQL text can cause series counts to explode.

### 28.2. High cardinality incurs costs

- Increases monitoring backend memory consumption.
- Increases storage/indexing overhead.
- Slows down dashboard queries.
- Makes alert evaluation heavy.
- Makes data harder to manage and increases exposure risk.

### 28.3. Appropriate labels

Commonly used labels include environment, cluster, instance, database (when bounded), normalized application_name, operation class, error class/SQLSTATE class, and region/zone.

### 28.4. Avoid unique labels

Do not use user ID, order ID, session ID, request ID, full SQL, arbitrary exception messages, or unbounded tenant IDs when counts are large.

Place unique values in logs/traces with appropriate retention and access controls.

### 28.5. Normalize application_name

Set application_name by service/job role rather than embedding a per-process UUID. Add an instance label at the exporter layer if needed while keeping cardinality controlled.

---

## 29. Dashboards: Organizing Around Operational Questions

A good dashboard is not a collection of every possible metric. It should help the on-call engineer quickly answer: are users affected, which component is slow, and what action is needed.

### 29.1. Overview

Display service availability, request latency p50/p95/p99, request/transaction rate, error rate, active/queued requests, current primary/standby roles, and SLO/error budget.

### 29.2. Database workload

- Transactions/s.
- Query calls and total execution time.
- Top query families.
- Rows returned/changed.
- WAL bytes/s.
- Temporary bytes/s.
- Connection count by state/application.

### 29.3. Latency and waits

- Query latency distribution.
- Lock waits and blockers.
- Wait event breakdown.
- Commit/WAL flush latency.
- Storage I/O latency.
- Connection pool acquisition latency.

### 29.4. Resources

- CPU per core and run queue.
- Memory available, swap, OOM.
- Disk free bytes and time to full.
- IOPS, throughput, latency, queue depth.
- Network throughput/errors/retransmits.
- Connection pool and backend usage.

### 29.5. Replication and HA

- Primary/standby roles.
- Sync state.
- Sent/write/flush/replay LSN.
- Lag bytes/time.
- Slot retention.
- WAL archive failures.
- Last failover and fencing status.

### 29.6. Backup and recovery

- Last base backup age.
- Last successful archive time.
- Archive continuity.
- Repository capacity.
- Last restore drill.
- Measured RPO/RTO.

### 29.7. Vacuum and maintenance

- Dead tuples.
- Last autovacuum/analyze.
- Long transactions.
- XID age.
- Vacuum/index progress.
- Table/index growth.

### 29.8. Dashboard hierarchy

Overview → service/workload → database → query/instance → host/storage. Operators must be able to drill down from symptom to root cause.

---

## 30. Alerts: From Metrics to Action

An alert should specify the symptom, scope, severity, and first diagnostic step.

### 30.1. Latency alerts

For example, API p95 latency breaching SLO for 10 minutes, p99 query latency spiking relative to baseline, or high commit latency coinciding with rising WAL flush time.

### 30.2. Throughput alerts

Throughput dropping sharply while incoming request rate stays steady; continuously rising queue depth; sudden WAL generation spike exceeding planned capacity.

Low throughput is not always an error; demand may simply be lower. Compare against arrival rate and business schedule.

### 30.3. Error alerts

SQL connection errors exceeding threshold, rapidly rising deadlocks, increasing statement timeouts, consecutive archive failures, failed backup jobs, or HA manager losing quorum.

### 30.4. Resource alerts

Disk time-to-full below threshold, memory pressure/swap/OOM, rising I/O latency and queue depth, connection pool near saturation, or replication slot retained WAL exceeding budget.

### 30.5. Alerts must have a duration

A 10-second spike may not justify paging an engineer. A condition lasting 10 minutes may require escalation. Choose pending durations according to the failure mode.

### 30.6. Warning vs. critical

- Warning: requires observation or planned follow-up.
- Critical: active user impact or major incident risk requiring immediate action.

Do not create critical alerts for every metric crossing an arbitrary threshold.

---

## 31. SLO Burn Rate and Multi-Window Alerts

### 31.1. Error budget

If an SLO permits 0.1% failing requests, the error budget is the maximum allowed errors within the evaluation window.

### 31.2. Burn rate

Burn rate is how fast the error budget is being consumed compared to the sustainable rate allowed by the SLO.

### 31.3. Why multiple windows?

A short window catches outages quickly; a long window confirms the impact is sustained. Combining both reduces false pages from brief spikes while catching real outages.

### 31.4. Conceptual example

A service has a 99.9% SLO over 30 days. If the current error rate is many times higher than allowed and persists across both short and long windows, the burn rate accelerates and triggers a page.

### 31.5. Do not put SLOs on every metric

SLOs should reflect user-visible service behavior. CPU, disk queue, and dead tuples are usually diagnostic or capacity indicators rather than direct SLIs.

---

## 32. Baselines and Anomaly Detection

### 32.1. Time-based baselines

Workloads differ between business hours and night, weekdays and weekends, month-end and normal days, batch windows and interactive traffic, peak season and off-peak periods.

### 32.2. Compare like-for-like time windows

Comparing CPU at 9 a.m. Monday against past Mondays is far more meaningful than comparing against Sunday midnight.

### 32.3. Seasonality

Use schedules for business jobs, ETL, backups, vacuum, and maintenance to explain recurring spikes.

### 32.4. Anomaly detection does not replace runbooks

An anomaly score only flags unusual behavior. Operators still need to know which metric changed, which workload is affected, and how to verify the cause.

### 32.5. Avoid autoscaling on a single metric

Adding CPU/RAM when latency increases will not fix lock contention or a bad query plan. Identify the bottleneck before changing capacity.

---

## 33. Capacity Planning from Throughput and Resources

### 33.1. Growth rate

Track database size, table/index growth, WAL generation, connection growth, and request rate weekly and monthly.

### 33.2. Headroom

Reserve sufficient capacity for peak workloads, failover mode, and maintenance. A primary running at 95% CPU normally has no headroom left to absorb extra traffic after a standby failure.

### 33.3. Failover capacity

When one node goes down, remaining nodes may have to handle the full read/write load. Capacity planning must model degraded modes.

### 33.4. Storage forecast

Estimate time to full from growth rate and free space. Account for data, WAL, temp, logs, backups, and archives.

### 33.5. WAL budget

WAL generation rises during bulk loads, index builds, full-page images, write-heavy workloads, and logical decoding. Use generation rate and slot retention to forecast disk needs.

### 33.6. Connection capacity

Estimate concurrent workload and pool size. Never raise max_connections without accounting for per-backend memory and query concurrency.

### 33.7. A forecast is not a guarantee

Growth shifts with product launches, data retention changes, and workload mix. Update forecasts using actual measurements.

---

## 34. Investigating Incidents Using the Four Signals

### 34.1. Latency rising, throughput flat, errors flat

Likely causes:
- Lock contention.
- Storage latency.
- Query plan regression.
- CPU saturation.
- Connection pool wait.

First steps:
1. Identify affected endpoints or query families.
2. Check wait events and blockers.
3. Inspect top queries, plans, and buffers.
4. Compare CPU, I/O, and pool wait.

### 34.2. Latency rising, throughput falling, errors rising

Likely causes:
- Database overload.
- Connection exhaustion.
- Network outage.
- Storage stall.
- Failover or recovery event.

First steps:
1. Verify service health and primary role.
2. Check connections, errors, and waiters.
3. Check disk/CPU/network.
4. Inspect PostgreSQL logs and HA events.

### 34.3. Throughput rising, latency flat, CPU rising

Often normal growth. Verify headroom, queues, and SLOs before scaling.

### 34.4. Throughput rising, latency spiking, queues growing

Clear sign of saturation. Identify the resource bottleneck, apply rate limits, or throttle workload.

### 34.5. CPU low, latency high

Look for waits: locks, I/O, network, connection pool, or external dependencies. Low CPU does not rule out a bottleneck.

### 34.6. Disk free dropping, WAL rate high

Check replication slots, archive failures, long-running consumers, and WAL generation. Never delete files in pg_wal manually.

### 34.7. Standby lag rising, primary query latency flat

Check network, standby I/O/CPU, replay conflicts, slot retention, and the archive path.

---

## 35. PostgreSQL Versions and Statistics Views

Statistics views evolve across major versions. A monitoring query written for PostgreSQL 13 may fail on PostgreSQL 17 if columns changed or views were split.

### 35.1. Check version

```sql
SELECT version();
SHOW server_version;
SHOW server_version_num;
```

### 35.2. Discover view schemas

```sql
SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'pg_catalog'
  AND table_name IN (
      'pg_stat_database',
      'pg_stat_bgwriter',
      'pg_stat_checkpointer',
      'pg_stat_io',
      'pg_stat_wal',
      'pg_stat_replication',
      'pg_replication_slots'
  )
ORDER BY table_name, ordinal_position;
```

Some views may not exist on older versions; the query returns only columns present in the catalog.

### 35.3. pg_stat_io

Available from PostgreSQL 16. Do not assume older clusters have this view.

### 35.4. Checkpoint statistics

In PostgreSQL 17, checkpoint stats were separated into pg_stat_checkpointer; pg_stat_bgwriter changed scope/columns compared to earlier versions. Exporter queries require version-aware mapping.

### 35.5. pg_stat_statements

Timing and query fields change across versions. Use an extension version matching the server and verify the view schema.

### 35.6. Exporters must be compatible

If using a Prometheus exporter, verify the exporter version, SQL collectors, and PostgreSQL major version. A failing collector can drop an entire group of metrics.

---

## 36. Security and Privileges for Reading Statistics

### 36.1. Statistics can expose workload details

Query text, database names, role names, client addresses, and timings can be sensitive.

### 36.2. Least privilege

Grant appropriate monitoring permissions. Some views/functions require pg_monitor or an equivalent role depending on version. Do not grant superuser solely to collect metrics when unnecessary.

### 36.3. Query text

Restrict who can view query text. Mask literals if supported by your logging/monitoring pipeline and required by policy.

### 36.4. Network metrics

Client addresses and application_name values can expose internal architecture. Protect access to dashboards and logs.

### 36.5. Retention

Retain metrics long enough for trend and capacity analysis without keeping them indefinitely. Logs and traces require separate retention policies because they hold more granular data.

---

## 37. Tools for Collecting and Storing Metrics

### 37.1. PostgreSQL native views

System statistics views are the primary source for many database metrics. They typically expose counters and gauges that require periodic scraping.

### 37.2. Prometheus and exporters

An exporter queries PostgreSQL views and exposes metrics for Prometheus or compatible systems. Select valuable collectors and constrain cardinality.

### 37.3. Grafana

Dashboards present time series, percentiles, rates, alerts, and drill-downs. Dashboards should include deploy, failover, and maintenance annotations to explain shifts.

### 37.4. Centralized logs

Collect PostgreSQL logs and application logs to classify errors, SQLSTATEs, slow queries, and failover events.

### 37.5. Distributed tracing

Traces link application requests to database spans, clarifying whether a slow request spent time in pool wait, network, SQL execution, or an external service.

### 37.6. Cloud provider metrics

Managed databases may expose CPU, memory, storage, IOPS, connections, replica lag, and backup status. Understand how the provider defines each metric before comparing it with native PostgreSQL stats.

### 37.7. Choose tools by question

You do not need to collect every possible metric. Start with SLOs, failure modes, and runbooks; then add only the metrics needed to distinguish root causes.

---

## 38. Process for Designing Metrics for a New Workload

### Step 1: Describe the workload

Identify read/write mix, transaction size, peak concurrency, data volume, batch/interactive schedules, and replication/backup requirements.

### Step 2: Define user-visible SLIs

Examples include request latency, success rate, queue delay, or transaction completion.

### Step 3: Map to RED

Rate, errors, and duration for the service/API.

### Step 4: Map resources to USE

CPU, memory, disk, network, connections, WAL, locks, and worker pools.

### Step 5: Choose PostgreSQL views

Select pg_stat_activity, pg_stat_database, pg_stat_statements, replication, WAL, vacuum, and I/O views based on your questions.

### Step 6: Define metric types

Counter, gauge, histogram, or summary. Decide scrape intervals, labels, and retention.

### Step 7: Build dashboards

Overview first, followed by workload, resource, replication, and backup drill-downs.

### Step 8: Define alerts

Each alert needs symptom, impact, threshold/duration, owner, runbook, and escalation.

### Step 9: Test

Generate controlled lab load or fault injection to confirm metrics actually respond when incidents occur.

### Step 10: Review periodically

Remove unused metrics, reduce cardinality, and update queries when versions or schemas change.

---

## 39. Lab 1: Capturing Baseline Latency and Throughput

Use a dedicated lab database and workload that cannot affect production.

### 39.1. Capture baseline database counters

```sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    tup_returned,
    tup_fetched,
    tup_inserted,
    tup_updated,
    tup_deleted,
    stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname = current_database();
```

### 39.2. Take a second snapshot

After a fixed interval, re-run the query. Compute commit/rollback deltas and divide by elapsed seconds.

### 39.3. Capture query statistics

If pg_stat_statements is enabled:

```sql
SELECT
    queryid,
    calls,
    mean_exec_time,
    total_exec_time,
    rows,
    left(query, 120) AS query_sample
FROM pg_catalog.pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 10;
```

### 39.4. Measure application latency

Send a small workload from an application or benchmark tool and record a duration histogram. Do not substitute database averages for application latency.

### 39.5. Record the baseline

Save timestamp, version, workload size, concurrency, CPU, disk latency, connections, and query mix.

---

## 40. Lab 2: Observing Lock Waits and Error Metrics

### 40.1. Open the first transaction

```sql
BEGIN;
UPDATE public.monitoring_lab
SET value = value + 1
WHERE id = 1;
-- Keep the transaction open in the lab.
```

### 40.2. Second session

Attempt to update the same row and observe the query waiting for the lock. Perform this only in a lab database.

### 40.3. Observe wait events

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    pg_blocking_pids(pid) AS blockers
FROM pg_catalog.pg_stat_activity
WHERE state <> 'idle';
```

### 40.4. End the transaction

Commit or rollback the lock-holding transaction and observe the blocked query proceed.

### 40.5. Deadlock

Create two transactions locking two rows in opposite orders in the lab to observe a deadlock. Inspect SQLSTATE/logs and the deadlocks counter.

### 40.6. Conclusion

Distinguish query execution time, lock wait time, statement timeout, and deadlock error.

---

## 41. Lab 3: Observing I/O and Temporary Files

### 41.1. Capture database temp counters

```sql
SELECT
    datname,
    temp_files,
    temp_bytes,
    blks_read,
    blks_hit,
    stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname = current_database();
```

### 41.2. Generate a large sort workload in the lab

Use a sufficiently large lab table to trigger sort/hash workloads. You can run EXPLAIN (ANALYZE, BUFFERS) in an isolated environment.

### 41.3. Observe counter deltas

Take before/after snapshots and compute temp bytes and file deltas.

### 41.4. Check pg_stat_io

On PostgreSQL 16 and later:

```sql
SELECT *
FROM pg_catalog.pg_stat_io;
```

### 41.5. Compare OS metrics

Track disk throughput, IOPS, latency, and queue depth. Correlate with PostgreSQL query activity.

### 41.6. Conclusion

Identify workload spills, I/O bottlenecks, and why cache hit ratio alone is insufficient.

---

## 42. Lab 4: Replication Lag and WAL Throughput

This lab requires a dedicated primary and standby.

### 42.1. Primary snapshot

```sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_catalog.pg_stat_replication;
```

### 42.2. Standby snapshot

```sql
SELECT
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();
```

### 42.3. Generate a controlled workload

Write batches of rows in the lab. Monitor wal_bytes delta and replication LSN progression.

### 42.4. Induce a controlled replay delay

Only in the lab, use a read workload or well-understood delayed-apply setting. Observe receive and replay diverging.

### 42.5. Inspect slot retention

```sql
SELECT *
FROM pg_catalog.pg_replication_slots;
```

### 42.6. Conclusion

Distinguish WAL generation rate, network throughput, flush lag, replay lag, and retained WAL.

---

## 43. Lab 5: Designing Dashboards and Alerts

### 43.1. Choose a service SLO

For example, p95 request latency under 150 ms and error rate under 0.5% over an agreed measurement window.

### 43.2. Choose RED metrics

Rate, errors, and duration by endpoint/operation class.

### 43.3. Choose USE metrics

CPU, memory pressure, disk latency, free space, connection pool waiters, and network errors.

### 43.4. Choose PostgreSQL metrics

pg_stat_activity, pg_stat_database, pg_stat_statements, replication, WAL, slots, archiver, and vacuum.

### 43.5. Build the dashboard hierarchy

Overview → workload → latency/waits → resources → replication/backup.

### 43.6. Write alerts

For each alert, document name and symptom, threshold and duration, user impact, runbook link, owner/escalation, and recovery verification criteria.

### 43.7. Test alerts

Inject load, lock waits, or replication delay in the lab. Verify alerts fire accurately and do not produce false pages when the workload is idle.

---

## 44. Practice Exercises

### Exercise 1 — Metric taxonomy

Distinguish metric, log, trace, event, and profile using PostgreSQL examples.

### Exercise 2 — RED

Design three groups of RED metrics for an API backed by PostgreSQL.

### Exercise 3 — USE

Build a table of utilization, saturation, and errors for CPU, memory, disk, network, and connections.

### Exercise 4 — Latency layers

Distinguish application latency, pool wait, query latency, transaction latency, and commit latency.

### Exercise 5 — Percentiles

A service has p50 = 10 ms, p95 = 100 ms, and p99 = 2 seconds. Explain why the average is insufficient.

### Exercise 6 — Histograms

Why are histograms better suited for aggregating latency across multiple application instances than per-instance quantile summaries?

### Exercise 7 — SLOs

Write SLOs for a read API and a write API. Specify scope, percentile, window, and error classification.

### Exercise 8 — Throughput

Compute transactions/s from two pg_stat_database snapshots and handle a change in stats_reset.

### Exercise 9 — WAL rate

Compute WAL bytes/s from pg_stat_wal. Explain the impact on archiving, replication, and disk.

### Exercise 10 — Counters and gauges

Classify 12 metrics: deadlocks, active sessions, disk free, wal_bytes, temp_bytes, replication lag bytes, xact_commit, CPU usage, archive failures, slot retained bytes, p95 latency, and pool waiters.

### Exercise 11 — Error rate

Define error rate for SQL statements and for HTTP requests. Why must the two denominators not be mixed?

### Exercise 12 — SQLSTATE

Classify connection exception, constraint violation, transaction rollback, and insufficient resources by SQLSTATE class.

### Exercise 13 — Lock waits

Write a query to find blocked sessions and blocking PIDs. Explain the difference between a lock wait and a deadlock.

### Exercise 14 — pg_stat_statements

Find the top 10 queries by total execution time and explain why calls, mean, and total must be reviewed together.

### Exercise 15 — Database stats

Compute cache hit ratio and list at least three reasons why that ratio can be misleading.

### Exercise 16 — Connection pool

Pool wait is rising while query latency is flat. Propose metrics and investigation steps.

### Exercise 17 — CPU

Total CPU is 35%, yet p99 query latency is rising. What causes are still possible?

### Exercise 18 — Memory

Explain why summing RSS across PostgreSQL backends can double-count shared memory.

### Exercise 19 — Disk

Disk free is 40%, yet query latency is increasing. Which I/O metrics should you check?

### Exercise 20 — Checkpoints

Explain checkpoint write/sync time and the differences in statistics views before and after PostgreSQL 17.

### Exercise 21 — pg_stat_io

State which versions support pg_stat_io and why it must be paired with OS metrics.

### Exercise 22 — Vacuum

n_dead_tup is growing and long transactions are present. Design a vacuum lag investigation procedure.

### Exercise 23 — Indexes

An index has low idx_scan. Why is that insufficient evidence to drop it?

### Exercise 24 — Replication

Distinguish sent/write/flush/replay LSN and design alerts for each type of lag.

### Exercise 25 — Backups

Design a dashboard for backup freshness, archive failures, WAL continuity, and restore drill age.

### Exercise 26 — Wait events

Explain Lock, IO, Client, LWLock, and IPC waits. Describe how to combine them with CPU/I/O metrics.

### Exercise 27 — Progress views

Select the progress views for VACUUM, CREATE INDEX, COPY, and BASE BACKUP.

### Exercise 28 — Cardinality

Why should user ID, request ID, or full SQL not be used as metric labels?

### Exercise 29 — Alert quality

An alert on CPU > 80% for 10 seconds causes frequent false positives. Redesign the alert around saturation and user impact.

### Exercise 30 — SLO burn rate

Explain error budget and burn rate. Why use multiple time windows?

### Exercise 31 — Baselines

Design a baseline for a workload with nightly batch jobs and start-of-month traffic peaks.

### Exercise 32 — Capacity

Database size grows 8% per month. Create a storage forecast and list additional factors to include.

### Exercise 33 — Rising latency, low CPU

Write an investigation sequence covering locks, I/O, pool waits, and external dependencies.

### Exercise 34 — Rising throughput, rising latency

Determine when this indicates healthy growth and when it indicates saturation.

### Exercise 35 — Replication lag

Standby receive LSN is advancing while replay LSN is stalled. Choose metrics and logs to isolate the bottleneck.

### Exercise 36 — Stats reset

An exporter computes a negative rate after a PostgreSQL restart. Explain why and how to handle counter resets.

### Exercise 37 — Version compatibility

Write a procedure to discover columns of pg_stat_bgwriter, pg_stat_checkpointer, and pg_stat_io before deploying an exporter.

### Exercise 38 — Monitoring permissions

Design a least-privilege monitoring role and control access to query text.

### Exercise 39 — Dashboards

Sketch a dashboard hierarchy for a cluster consisting of one primary, two standbys, a backup repository, and API services.

### Exercise 40 — End-to-end incident

After a deploy, API p99 latency increases 5x, throughput drops 20%, error rate rises, CPU is 45%, disk latency rises, and standby replay lag increases. Build an investigation sequence, metrics to check, hypotheses, and incident resolution criteria.

---

## 45. Metric Selection and Operations Checklist

| Group | Metrics to Consider | Question |
| --- | --- | --- |
| Latency | Request p50/p95/p99 | Are users waiting too long? |
| Latency | Query/transaction duration | Which workload is slow? |
| Latency | Pool acquisition wait | Are connections exhausted? |
| Latency | Lock wait duration | Who is blocking? |
| Latency | Commit/WAL flush time | Are commits waiting on storage/standby? |
| Latency | Storage I/O latency | Is disk slow? |
| Throughput | Requests/s | Has incoming load changed? |
| Throughput | xact_commit/xact_rollback rate | What is the transaction rate? |
| Throughput | Query calls/s | Has query volume increased? |
| Throughput | Rows inserted/updated/deleted | What is the write volume? |
| Throughput | wal_bytes/s | Is WAL generation rising? |
| Throughput | IOPS/bytes/s | What is the storage workload? |
| Errors | SQLSTATE/error rate | Which error classes are rising? |
| Errors | Deadlocks | Are transactions conflicting? |
| Errors | Statement/lock timeout | Is there overload or long waits? |
| Errors | Connection failures | Pool, network, or auth issue? |
| Errors | Archive failures | Is the PITR chain at risk? |
| Errors | Backup/restore failures | Is recoverability assured? |
| Resources | CPU per core/run queue | Is CPU saturated? |
| Resources | Memory/swap/OOM | Is there memory pressure? |
| Resources | Disk free/time to full | Is space running out? |
| Resources | I/O queue/latency | Is storage saturated? |
| Resources | Network drops/retransmits | Is there a network bottleneck? |
| Resources | Active/max connections | What is backend capacity? |
| Resources | Pool waiters | Is the pool saturated? |
| Resources | Slot retained WAL | Is WAL retention creating pressure? |
| Resources | Dead tuples/XID age | Is vacuum keeping up? |
| Replication | Sent/write/flush/replay LSN | Which stage is lagging? |
| Replication | Sync state/timeline | Is the standby eligible? |
| Backup | Backup age/WAL continuity | How far can we restore? |
| HA | Leader/quorum/fencing | Is failover safe? |
| Service | Availability/error budget | Are SLOs being met? |

## Conclusion

Effective metric selection starts with operational questions and user impact. RED tracks service rate, errors, and duration; USE identifies utilization, saturation, and errors for each resource. For PostgreSQL, combine statistics views, logs, application metrics, OS/cloud metrics, and tracing to uncover root causes.

Key principles to remember:

1. **Latency requires percentiles and scope.** p50 captures the middle, while p95/p99 expose tail latency; measure both request boundaries and database layers.
2. **Throughput must be computed over time.** Cumulative counters require deltas/rates and stats-reset handling.
3. **Errors must be classified.** SQLSTATEs, deadlocks, timeouts, connection errors, replication issues, and archive failures have different causes and remedies.
4. **Resources require both utilization and saturation.** Low CPU does not rule out lock, I/O, or pool bottlenecks.
5. **Wait events explain non-CPU time.** Combine pg_stat_activity with blockers, logs, and host metrics.
6. **pg_stat_statements helps locate query families.** Evaluate calls, total time, mean time, rows, and buffer/temp activity together.
7. **Replication and backups need dedicated metrics.** Monitor receive/replay lag, slot retention, archive continuity, backup freshness, and restore tests.
8. **Metric type dictates math.** Counters require rates; gauges represent point-in-time values; histograms reveal distributions.
9. **Cardinality must be controlled.** Put request/user identifiers and raw SQL in logs/traces when needed, never in unbounded metric labels.
10. **Alerts must lead to action.** Every alert should define impact, duration, owner, runbook, and clear conditions.
11. **SLOs must reflect user experience.** Database metrics are diagnostic signals; they do not replace application SLIs.
12. **Baselines must account for seasonality.** Compare matching workload windows and annotate deployments, maintenance, and failovers.
13. **Capacity planning requires degraded-mode headroom.** After a failover, surviving nodes may need to carry the entire workload.
14. **Statistics views depend on version.** Pay special attention to pg_stat_io and checkpoint statistics changes in PostgreSQL 17.
15. **Restore and failover drills validate reality.** Metrics only matter when they support a verifiable operational procedure.

A good monitoring system is not the one with the most charts. It is the one that shows operators where users are affected, which workload shifted, which resource is saturated, whether data remains safe, and what action to take next.
# Selecting PostgreSQL Monitoring Metrics by Latency, Throughput, Errors, and Resources

## 1. Why Select Metrics Around Operational Questions?

A PostgreSQL system can emit hundreds of counters, gauges, and timing values. Collecting all of them does not automatically yield good observability. A dashboard packed with graphs that fails to show how users are impacted, where requests are slowing down, or which resource is running out is difficult to use during an incident.

Effective metric selection starts with the questions you need to answer:

- **Latency:** How long does an operation take? How long are users waiting?
- **Throughput:** How much work is the system completing per unit of time?
- **Errors:** How many operations fail, time out, roll back, or return incorrect results?
- **Saturation/resources:** Which resources are nearing limits, and where are queues building up?

These four groups complement one another. Rising latency can stem from saturated CPU, slow storage, lock contention, or connection pool queueing. Falling throughput can result from errors, resource exhaustion, or lower traffic. Rising error rates can appear before latency climbs. High resource utilization is not necessarily an incident if the system still has headroom and meets its SLOs.

```text
                 USER / APPLICATION SLO
                          |
                          v
                 Latency + Errors
                          |
                          v
                    Throughput
                          |
                          v
               Saturation / Resources
                          |
                          v
             Diagnose bottleneck and impact
                          |
                          v
                 Actionable alert / fix
```

This lesson explains how to select a focused, sufficient set of metrics, understand PostgreSQL data sources, build purpose-driven dashboards, and design alerts that lead to concrete actions.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish metrics, logs, traces, and events.
2. Apply RED and USE to select metrics.
3. Define latency, throughput, error rate, and saturation.
4. Select metrics by endpoint, transaction, and workload class.
5. Read key PostgreSQL statistics views.
6. Use pg_stat_statements to identify time-consuming queries.
7. Measure latency percentiles using application instrumentation.
8. Calculate rates from cumulative counters using deltas.
9. Distinguish active connections, idle sessions, and lock waits.
10. Monitor CPU, memory, disk I/O, WAL, checkpoints, and temporary files.
11. Monitor autovacuum, dead tuples, and transaction ID age.
12. Monitor replication, archiving, and connection pools.
13. Build SLIs/SLOs, alert thresholds, and burn-rate alerts.
14. Avoid false positives, high metric cardinality, and overloaded dashboards.
15. Build runbooks mapping metrics to root causes and actions.

---

## 2. The Four Primary Signal Groups

| Group | Question | Example Metrics | Units |
|---|---|---|---|
| Latency | How long does it take? | Query duration, transaction duration, lock wait | ms, s |
| Throughput | How much is processed? | Transactions/s, queries/s, WAL bytes/s | count/s, bytes/s |
| Errors | How many operations fail? | SQL errors, deadlocks, failed connections, rollbacks | count/s, % |
| Saturation/resources | What limit is close? | CPU, memory, disk latency, connection usage, queue depth | %, bytes, ms, count |

### 2.1. Latency reflects user experience

Users care whether requests complete fast or slow. Database query time is one component of request time, alongside application processing, network, queueing, and external dependencies.

### 2.2. Throughput indicates load and processing capacity

Rising TPS can mean higher traffic or batch execution. Falling TPS can mean lower traffic or a database bottleneck. Always interpret throughput alongside latency and errors.

### 2.3. Errors reflect processing quality

Do not count only SQL syntax errors. Track transaction rollbacks, deadlocks, connection failures, statement cancellations, timeouts, and application-level failures.

### 2.4. Saturation shows whether headroom remains

90% CPU can be normal under an optimized workload, yet if run queue, latency, and queue depth rise together, saturation may be imminent. A single utilization metric is rarely enough.

## 3. RED and USE: Two Approaches to Choosing Metrics

**RED** is typically used for requests and services:

- Rate: requests or operations per second.
- Errors: count or rate of failed requests.
- Duration: time taken to process requests.

**USE** is typically used for resources:

- Utilization: fraction of time or resource capacity in use.
- Saturation: queue level or work waiting for service.
- Errors: resource-level errors such as disk or network errors.

### 3.1. RED for a PostgreSQL endpoint

Example for an order-lookup endpoint:
- Rate: SELECT operations/s.
- Errors: timeouts, SQLSTATE errors, failed requests.
- Duration: p50, p95, p99 response/query latency.

### 3.2. USE for storage

- Utilization: disk throughput/IOPS relative to limits.
- Saturation: queue depth, I/O wait, pending operations.
- Errors: I/O errors, filesystem errors, volume throttling.

### 3.3. Combining both

RED shows user-facing symptoms. USE helps locate resource bottlenecks. PostgreSQL metrics supply context on queries, locks, WAL, vacuum, and replication.

### 3.4. Do not apply mechanically

A database cluster often serves multiple workloads. Select metrics according to the service tier, business operation, and resource path under investigation.

## 4. Start with SLIs and SLOs

Before picking alert thresholds, define service-level indicators (SLIs) and objectives (SLOs).

Examples:
- Latency SLI: proportion of read requests completing within 200 ms.
- Availability SLI: proportion of valid requests receiving successful responses.
- Freshness SLI: standby data lag relative to the primary.
- Transaction success SLI: proportion of business transactions committing successfully.

Example SLOs:
- 99% of read requests complete under 200 ms over a rolling 30-day window.
- 99.9% of write transactions succeed over a rolling 30-day window.
- Standby replay lag stays under 5 seconds 99% of the time during active writes.

These are illustrative examples. Targets must match business impact and system architecture.

### 4.1. Technical metrics are not SLOs by themselves

85% CPU utilization is not a business SLO. It is a supporting signal for diagnosis or capacity planning.

### 4.2. Choose the right population

An SLO must specify which requests count, which time periods count, how retries are treated, and which error classes are excluded.

### 4.3. Measure at the right boundary

If the SLO is API latency, measure at the application/API boundary. PostgreSQL query duration aids diagnosis but does not replace end-to-end measurement.

## 5. Choosing Latency Metrics

Latency should be measured across multiple layers:

| Layer | Metric | Meaning |
|---|---|---|
| API | End-to-end request duration | How long the user waits |
| Pool | Acquire/wait duration | Waiting to obtain a connection |
| Database | Query execution duration | How long the query runs |
| Transaction | Transaction duration | Elapsed time from BEGIN to COMMIT/ROLLBACK |
| Lock | Lock wait duration | How long spent waiting on locks |
| Storage | Read/write/fsync latency | How long I/O takes |
| Replication | Commit/replica apply delay | Waiting to sync/apply to standby |

### 5.1. p50, p95, p99

- p50: median; half of observations are faster.
- p95: 95% of observations do not exceed this value.
- p99: captures the tail latency of the slowest 1% of observations.

The mean can mask extremely slow requests. Always examine percentiles alongside request count and sample size.

### 5.2. Percentiles require histograms or raw observations

You cannot compute an accurate p95 from a mean or from total time divided by call count. You need application/APM histograms, metric histograms, or enough stored observations to calculate percentiles.

### 5.3. Avoid relying solely on p99 at low volume

If an endpoint handles only a few requests per minute, p99 can fluctuate wildly. Inspect sample count, rolling windows, and p95/maximum together with context.

### 5.4. Measure queue time as well

A query with a 5 ms execution time still causes high latency if the request waits 500 ms in the connection pool. Separate pool wait, network, query, and application time.

## 6. Measuring Query Latency with pg_stat_statements

The pg_stat_statements extension collects planning and execution statistics for normalized queries grouped by query identity.

Enabling the extension requires adding it to shared_preload_libraries and restarting the server if not already preloaded, then creating the extension in the database per your version's documentation.

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

Example query:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_written
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

### 6.1. total_exec_time

Cumulative execution time for the query entry since the last statistics reset. A query with high total time may run very often, run very slowly, or both.

### 6.2. mean_exec_time

Average time per execution. The mean hides tail latency and can be distorted by skewed distributions.

### 6.3. calls

Number of times the query was executed. Combine calls with mean and total to see whether a query is expensive due to frequency or per-execution cost.

### 6.4. Query identity

queryid groups similar executions together. Do not use query text containing literals or user input as high-cardinality metric labels.

### 6.5. Versions and configuration

Columns such as planning statistics, WAL statistics, and detailed fields vary by PostgreSQL and extension version. Verify the actual pg_stat_statements schema before building dashboard queries.

## 7. pg_stat_statements Does Not Provide p95 Query Latency

A common misconception is that mean_exec_time can substitute for p95. That is incorrect.

Example:
- Query A runs 100 times: 99 executions take 5 ms, and 1 execution takes 2 seconds.
- The mean fails to reflect the tail experience of that slow request.
- p95/p99 require histograms or individual observations.

### 7.1. Capture percentiles in the application

Instrument the database client or ORM to record duration histograms by operation/query class. Use bounded metric labels such as service, operation, database, and outcome.

### 7.2. Use logs selectively

log_min_duration_statement can log queries exceeding a threshold. Weigh log volume, parameter exposure, and overhead. Avoid logging all statements long-term unless necessary.

### 7.3. auto_explain

auto_explain can log execution plans for slow queries, which helps capture plan evidence. Logging, timing, and buffer options add overhead; enable them selectively according to policy.

### 7.4. Query plans and duration

Increased query duration can stem from plan changes, inaccurate row estimates, cache state differences, or I/O. Combine with EXPLAIN (ANALYZE, BUFFERS) in an appropriate environment with representative data.

## 8. Transaction Latency and Long-Running Transactions

Individual queries do not reflect full transaction duration. A transaction can run multiple statements and hold locks and snapshots over an extended period.

Inspect active sessions:

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - xact_start AS transaction_age,
    now() - query_start AS query_age,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 8.1. idle in transaction

A session in the idle in transaction state has an open transaction but is not currently executing a query. It can hold locks and snapshots and block vacuum cleanup.

### 8.2. Query age differs from transaction age

A query may run for 20 ms inside a transaction that has been open for 30 minutes. Monitor both.

### 8.3. Application name

Set a meaningful application_name per service or worker to distinguish workloads. Avoid embedding individual user IDs or request IDs in application_name.

### 8.4. Transaction duration depends on workload

OLTP transactions are typically short; reporting or maintenance transactions may be intentionally long. Alert by workload class and business policy.

## 9. Lock Wait Latency

Lock contention can slow down queries even when CPU and storage have plenty of spare capacity.

A query to inspect sessions waiting on locks:

```sql
SELECT
    pid,
    usename,
    application_name,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    pg_blocking_pids(pid) AS blocking_pids,
    left(query, 250) AS query_sample
FROM pg_stat_activity
WHERE wait_event_type = 'Lock'
ORDER BY query_start;
```

### 9.1. Blocking query

Use pg_blocking_pids to identify the PIDs blocking a session, then inspect those blockers in pg_stat_activity.

### 9.2. Lock wait time

Applications/APMs can measure wait duration per request. PostgreSQL shows sessions waiting at scrape time; not every wait event exposes a convenient cumulative duration.

### 9.3. Deadlocks differ from lock waits

A lock wait can resolve normally when the blocker commits. A deadlock is a wait cycle; PostgreSQL detects it and aborts one transaction.

### 9.4. Alert by age and impact

A 100 ms lock wait can be normal; a blocker stalling thousands of requests for 30 seconds is an incident. Track blocked session count, blocker age, and affected workload.

## 10. Choosing Throughput Metrics

Throughput measures how much work completes per unit of time.

Common metrics:
- Transactions committed/s.
- Transactions rolled back/s.
- Queries/calls per second.
- Rows returned/changed per second.
- WAL bytes generated/s.
- Connections opened/s.
- Replication bytes/s.
- Background job completions/s.

### 10.1. TPS from database counters

pg_stat_database provides xact_commit and xact_rollback counters per database.

```sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    stats_reset
FROM pg_stat_database
ORDER BY datname;
```

These are cumulative counters, not instantaneous TPS.

### 10.2. Computing TPS from deltas

Take two samples separated by a known time interval:

```text
TPS = (commits_2 - commits_1
       + rollbacks_2 - rollbacks_1)
      / elapsed_seconds
```

If you want successful commit throughput only, use the delta of xact_commit. Document the exact metric definition clearly.

### 10.3. Do not compute rates across a stats reset

If a counter decreases due to a stats reset, server restart, or database drop/recreate, a negative delta is not negative throughput. Reset the baseline and start a new window.

### 10.4. TPS is not business throughput

One transaction may create a single order or update thousands of rows. If the business tracks orders/minute, measure that business event in the application.

## 11. Queries per Second and Calls

pg_stat_statements.calls is a counter per query entry. Compute deltas over time to obtain calls/s.

Do not sum calls across all queries and call the total user requests/s: a single API request may run multiple SQL statements, retries, and background queries.

### 11.1. By query class

Group queries by operation/queryid or application service to identify which workloads generate load.

### 11.2. Read/write throughput

You can inspect rows returned/changed and block activity, keeping in mind that a query might return 0 rows while scanning many rows.

### 11.3. Batch workloads

A batch job can generate very high throughput over a short period. Attach workload labels and schedules so dashboards do not misinterpret scheduled batch spikes as abnormal traffic.

## 12. WAL Throughput

WAL generation rate is a key signal for write workload, replication capacity, and archive storage needs.

On PostgreSQL versions with pg_stat_wal:

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    stats_reset
FROM pg_stat_wal;
```

Compute WAL bytes/s from the wal_bytes delta divided by elapsed time.

### 12.1. WAL bytes do not equal data bytes

A small UPDATE can generate substantial WAL due to indexes, full-page images, and page modifications. WAL rate does not translate directly into database size growth rate.

### 12.2. WAL bursts

Bulk loads, index builds, mass updates, and post-checkpoint full-page images can create bursts. Measure peak rates and durations, not just daily averages.

### 12.3. WAL buffers full

The wal_buffers_full counter can help identify WAL buffer pressure depending on version. Read deltas alongside the workload; do not draw conclusions from the raw cumulative total alone.

### 12.4. Archive/replication capacity

High WAL throughput increases demand on network, archive throughput, standby replay, and storage retention. Monitor these paths together.

## 13. Error Metrics: Counting the Right Errors

A good error dashboard distinguishes:
- Application request failures.
- SQL statement errors.
- Transaction rollbacks.
- Deadlocks.
- Lock timeouts.
- Statement timeouts/cancellations.
- Failed connections/authentication.
- Replication apply/archive errors.
- Storage/network errors.

### 13.1. Error rate

```text
Error rate (%) = failed operations / total operations * 100
```

Define failed operations clearly and use the same population as the success rate.

### 13.2. Rollbacks are not always errors

An application may intentionally roll back due to validation or business rules. Separate expected rollbacks from unexpected failures.

### 13.3. SQLSTATE

PostgreSQL error codes can be grouped by class. Capture SQLSTATE from drivers/logs to separate unique violations, serialization failures, deadlocks, connection exceptions, and timeouts.

### 13.4. Error counts need volume context

10 errors/minute out of 100 requests is very different from 10 errors/minute out of 1 million requests. Display both absolute counts and rates/percentages.

## 14. Deadlocks and Conflicts

pg_stat_database provides counters such as deadlocks and conflicts (where conflicts mainly reflect standby recovery conflicts in database statistics).

```sql
SELECT
    datname,
    deadlocks,
    conflicts,
    xact_commit,
    xact_rollback,
    stats_reset
FROM pg_stat_database
ORDER BY datname;
```

### 14.1. Deadlock rate

Take the delta of deadlocks over time. A deadlock aborts one transaction; the application needs retry logic aligned with policy and idempotency.

### 14.2. Recovery conflicts

On a hot standby, conflicts can cancel read queries so WAL replay can proceed. Monitor pg_stat_database_conflicts for details on standbys.

### 14.3. Lock timeout and statement timeout

Timeout errors can indicate that latency guardrails are actively protecting the system. Track timeout types and request impact separately.

### 14.4. Logs add essential context

Counters do not identify the specific queries or transactions involved. Use logs with SQLSTATE, application_name, PID, and timestamps to investigate.

## 15. Connection Failures and Pool Errors

PostgreSQL server statistics do not capture every failed connection attempt. A connection rejected before a backend is created may appear only in server logs, proxy metrics, or application metrics.

Monitor:
- Connection attempts/s.
- Successful connections/s.
- Authentication failures.
- Connection refused/reset.
- Pool acquire wait.
- Pool timeouts.
- Active/idle/idle-in-transaction connections.
- Pool saturation and queue length.

### 15.1. max_connections

This is a configured backend connection limit, not a target to fill up. Too many concurrently active connections can increase memory and CPU contention.

### 15.2. Connection pools

Track pool utilization, idle count, active count, pending waiters, and acquire latency at the application or pooler layer.

### 15.3. Idle connections differ from idle in transaction

An idle session holds no open transaction. An idle-in-transaction session can hold snapshots and locks and requires closer attention.

### 15.4. Connection churn

Frequently opening and closing connections incurs authentication, TLS, backend startup, and resource overhead. Track connection creation rate alongside pool configuration.

## 16. Resource Metrics: CPU

CPU metrics should include:
- Host CPU utilization broken down by user/system/iowait/steal.
- Per-core utilization.
- Run queue/load average.
- PostgreSQL process CPU.
- Container CPU throttling when running in containers.
- Query CPU/plan evidence when needed.

### 16.1. High CPU utilization is not automatically an incident

If latency and throughput remain healthy, high CPU can simply reflect efficient use. Watch headroom, queueing, and trends.

### 16.2. Low CPU with high latency

Queries may be waiting on locks, disk I/O, network, connection pools, or external dependencies. Low CPU does not mean the database is healthy.

### 16.3. CPU steal/throttling

A VM or container can be CPU-constrained even when guest utilization looks moderate. Monitor steal time and cgroup throttling.

### 16.4. Correlate with query stats

Use pg_stat_statements, wait events, and query plans to locate SQL consuming heavy CPU or making excessive calls.

## 17. Resource Metrics: Memory

PostgreSQL memory spans several areas:
- shared_buffers.
- Backend-local memory and work_mem for sort/hash operations.
- maintenance_work_mem.
- WAL buffers.
- OS page cache memory.
- Extension and background process memory.
- Container/cgroup limits.

### 17.1. There is no single simple “PostgreSQL memory used” number

Summing RSS across all backends can double-count shared memory. Use OS/cgroup metrics and understand memory accounting.

### 17.2. work_mem is a per-operation budget

A single query can have multiple sort/hash nodes, multiple workers, and many concurrent sessions. Total memory usage can greatly exceed work_mem.

### 17.3. Swap pressure

Swap-in/swap-out and major page faults can sharply degrade latency. Track available host memory, swap activity, and OOM kills.

### 17.4. Shared buffers hit ratio

Hit ratio can serve as a supporting signal, not an absolute target. Large scan workloads or OS page caching complicate interpretation; prioritize read latency, physical I/O, and workload context.

## 18. Resource Metrics: Disk and I/O

Monitor:
- Free space and growth rate.
- Read/write IOPS.
- Read/write throughput.
- I/O latency.
- Queue depth.
- Filesystem errors.
- Volume throttling or credit balances if used by cloud storage.
- WAL directory usage.
- Temporary files/bytes.
- Data, index, and tablespace growth.

### 18.1. Disk full is a severe failure mode

The database may become unable to write WAL, data, or temporary files. Alert on free space by both bytes and estimated time remaining based on growth rate.

### 18.2. Latency matters more than utilization alone

A volume hitting 100% of its throughput limit with rising latency signals saturation. High utilization with low latency and remaining headroom elsewhere may still be fine.

### 18.3. Separate data and WAL

If the data directory and pg_wal reside on different volumes, monitor each volume separately. Either volume filling up can impact the cluster even if the other still has free space.

### 18.4. Tablespaces

Monitor each filesystem/mount holding tablespaces. Plenty of aggregate host space does not mean a dedicated mount is safe from filling up.

## 19. pg_stat_io for I/O Context

PostgreSQL 16 and later provide pg_stat_io to observe I/O by backend type, object, and context.

```sql
SELECT
    backend_type,
    object,
    context,
    reads,
    read_time,
    writes,
    write_time,
    extends,
    fsyncs,
    fsync_time,
    stats_reset
FROM pg_stat_io
ORDER BY backend_type, object, context;
```

Verify columns on your exact version since the view can evolve.

### 19.1. Counters and timing

Reads/writes/fsyncs are counters; read_time/write_time/fsync_time may depend on track_io_timing. Compute deltas to derive rates and average timings.

### 19.2. track_io_timing

This setting enables I/O timing collection where supported, but it carries overhead depending on platform and workload. Measure the impact before enabling it broadly.

### 19.3. Does not replace OS metrics

pg_stat_io supplies PostgreSQL context. OS/cloud volume metrics are still essential to see queues, throttling, device latency, and system errors.

### 19.4. pg_stat_database block counters

blks_read and blks_hit help track database-level block activity, though they do not fully distinguish physical device paths.

## 20. Temporary Files and Sort/Hash Spills

When a sort or hash operation does not fit within its memory budget, PostgreSQL may write temporary files. This increases disk I/O and query latency.

```sql
SELECT
    datname,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_stat_database
ORDER BY temp_bytes DESC;
```

### 20.1. temp_bytes is a cumulative counter

Compute deltas over time to observe the temp write rate. A large cumulative total built up over months does not prove queries are spilling heavily right now.

### 20.2. Query-level temporary blocks

pg_stat_statements can report temp_blks_read and temp_blks_written depending on version. Use them to find queries generating heavy spills.

### 20.3. work_mem tuning

Increasing work_mem can reduce spills, but it also raises memory consumption per operation and concurrent session. Assess query classes and concurrency first.

### 20.4. Disk headroom

Temporary files can fill a filesystem rapidly. Monitor free space and temp bytes/s during batch windows.

## 21. Checkpoints and WAL

Checkpoints flush dirty buffers and write checkpoint records to WAL. Excessively frequent checkpoints or I/O pressure can degrade write latency.

Monitor:
- Checkpoint counts and timing.
- Buffers written by checkpoints.
- Checkpoint write/sync time.
- WAL bytes generated.
- WAL files retained.
- Backend writes.
- Checkpoint warnings in logs.

### 21.1. Version differences

Checkpoint statistics have changed across major versions. PostgreSQL 17 introduces pg_stat_checkpointer, separating fields previously located in pg_stat_bgwriter. Use the views and columns matching your version.

### 21.2. Do not copy queries blindly across versions

Inspect catalog views before putting checkpoint queries into dashboards. Never assume pg_stat_bgwriter has the same schema across all versions.

### 21.3. checkpoint_timeout and max_wal_size

These settings govern checkpoint scheduling and volume rather than serving as alert thresholds. Tune them based on workload, recovery objectives, and storage performance.

### 21.4. Checkpoint warnings

Log warnings about checkpoints occurring more often than expected can indicate WAL generation exceeding forecasts or a low max_wal_size. Read logs alongside checkpoint stats and WAL rate.

## 22. Vacuum and Bloat

Autovacuum maintains visibility maps and statistics and reclaims dead tuples for reuse. Slow or blocked vacuuming can increase table/index bloat and transaction ID wraparound risk.

Inspect table stats:

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
```

### 22.1. n_dead_tup is an estimate

This is an estimated statistic, not the exact count of dead rows at query time.

### 22.2. Autovacuum activity

Track pg_stat_progress_vacuum and active sessions to see which relations vacuum is currently processing.

### 22.3. Blocked vacuum

Long-running transactions, replication slots, and standby feedback can pin the xmin horizon and prevent cleanup. Monitor oldest transactions, slot xmin, and vacuum progress.

### 22.4. Bloat is not measured directly by dead tuple count

Use appropriate extensions, tools, or size/visibility analysis methods. Never treat n_dead_tup as exact bloat bytes.

## 23. Transaction ID Age and Wraparound Risk

Transaction ID wraparound is a critical risk requiring dedicated monitoring. A database whose datfrozenxid age approaches the limit may trigger urgent vacuuming; PostgreSQL enforces protective mechanisms to prevent wraparound.

Example query:

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
```

### 23.1. XID age is not a latency metric

This is a gauge tracking the age of transaction IDs needing freezing. Watch the trend and distance from autovacuum_freeze_max_age and policy limits.

### 23.2. Distinguish database and table age

A single table with an old relfrozenxid can be problematic even if the database-level summary looks fine. Check per-relation age in the catalogs during investigation.

### 23.3. Alert early

Do not wait until the critical threshold. Configure warning and critical alerts appropriate to your version and operations, paired with autovacuum progress and blockers.

### 23.4. Replication slots

Logical and physical slots can hold xmin, catalog_xmin, or WAL longer, affecting vacuum and retention. Monitor slot states and owners.

## 24. Connections, Backends, and Active Workload

Inspect session distribution:

```sql
SELECT
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    count(*) AS sessions
FROM pg_stat_activity
GROUP BY
    datname, usename, application_name,
    state, wait_event_type, wait_event
ORDER BY sessions DESC;
```

### 24.1. Active

Active sessions are executing a query or in the active state. Not every active session is burning CPU; it may be waiting on I/O or locks.

### 24.2. Idle

Idle sessions are not running a query. Pools keeping idle connections open can be normal within limits.

### 24.3. Idle in transaction

Pay close attention to these, because open transactions can hold locks and snapshots and delay vacuum cleanup.

### 24.4. Max connections headroom

Track current connections against max_connections, reserved slots, and pool capacity. Set warnings before running out of slots for admin or replication connections.

## 25. Locks and the Blocking Tree

When latency spikes, identify the blocking chain:

```sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.application_name AS blocked_app,
    now() - blocked.query_start AS blocked_for,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    now() - blocker.xact_start AS blocker_xact_age,
    left(blocker.query, 200) AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS p(blocker_pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = p.blocker_pid
ORDER BY blocked.query_start;
```

### 25.1. Lock count is insufficient

A high count of held locks does not automatically mean contention. What matters is lock waits, wait duration, and how many requests are blocked.

### 25.2. Blocking transactions

A long-open transaction can block many sessions. Locate the root blocker rather than looking only at sessions waiting at the end of the chain.

### 25.3. DDL locks

Migrations and ALTER TABLE statements can request strong locks and block traffic. Monitor lock waits before and during deployments.

### 25.4. Deadlock metrics

Combine the deadlock counter, server logs, and application retry behavior.

## 26. Replication and Archive Metrics

For HA setups, choose metrics by replica role:
- Connection state.
- Sent/write/flush/replay LSN.
- Byte lag and time lag.
- WAL generation/replay rate.
- Synchronous state.
- Replication slot retained WAL.
- Archive success/failure.
- Standby recovery conflicts.

On the primary:

```sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
```

Archive stats:

```sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
```

### 26.1. Do not treat time lag as actual RPO

Lag fields are observational signals. Actual RPO depends on failover/restore evidence and acknowledged transaction durability markers.

### 26.2. Archiving and streaming are separate paths

Healthy standby streaming does not prove WAL archiving is healthy. PITR readiness requires archive continuity and restore tests.

### 26.3. Slot retention

A lagging consumer can cause WAL retention to grow and fill disk. Track retained distance alongside filesystem free space.

### 26.4. Read freshness

When standbys serve reads, measure read-after-write wait or token-based freshness if required by the business.

## 27. Cache Hit Ratio: Using It Properly

A commonly seen formula:

```text
shared buffer hit ratio
  = blks_hit / (blks_hit + blks_read)
```

Computing this from counter deltas within a time window is usually more meaningful than using cumulative totals since stats reset.

### 27.1. Do not set a blanket 99% target for all workloads

Sequential scans, data warehouses, and large working sets can have lower ratios while still achieving good performance.

### 27.2. PostgreSQL shared buffers are not the entire cache

The OS page cache can satisfy reads after PostgreSQL requests blocks from the filesystem. blks_read does not guarantee that the physical storage device actually performed a media read.

### 27.3. Latency and I/O matter more than a standalone ratio

Inspect query latency, pg_stat_io, OS device latency, and working set behavior.

### 27.4. Rising ratio while queries stay slow

CPU, locks, query plans, or network may be the bottleneck. Cache hit ratio is not an SLO.

## 28. Metric Types: Counter, Gauge, and Histogram

| Type | Meaning | Examples | How to Use |
|---|---|---|---|
| Counter | Monotonically accumulating | xact_commit, deadlocks, wal_bytes | Compute rates via deltas |
| Gauge | Point-in-time value | active connections, free disk, replay LSN | Track current values and trends |
| Histogram | Distribution of observations | request duration buckets | Compute quantiles and SLOs |
| Summary | Quantiles/aggregates from instrumentation | Client latency summary | Watch aggregation limitations |

### 28.1. Counter resets

Counters can reset after restarts, stats resets, or object lifecycles. Exporters must handle resets correctly.

### 28.2. Do not sum gauges over time like counters

70% CPU utilization across two samples does not mean 140%. Use averages or maxima over a window.

### 28.3. Histogram buckets

Place buckets around SLO boundaries and tail ranges. Overly coarse buckets produce inaccurate quantiles.

### 28.4. Labels and cardinality

Use labels with bounded value sets. Avoid raw SQL, user IDs, order IDs, request IDs, or arbitrary tenant IDs as labels.

## 29. Stats Resets and Accurate Rate Calculation

PostgreSQL statistics views often contain cumulative counters. To calculate a rate:
1. Sample the counter at time T1.
2. Sample the counter at T2.
3. Compute the delta.
4. Divide by elapsed time.
5. Check stats_reset and counter resets.
6. Attach server/database identity to each sample.

```text
rate_per_second = (counter_T2 - counter_T1)
                  / (T2 - T1)
```

### 29.1. Do not assume independent query timestamps give exact elapsed time

Record sample timestamps in the monitoring collector and use monotonic time to measure elapsed duration.

### 29.2. Stats consistency

Statistics collectors/caches can exhibit snapshot semantics. Within a long transaction, stats snapshots may not update as expected. Use short transactions or refresh snapshots appropriately for your version.

### 29.3. stats_reset

Store stats_reset alongside metrics to detect resets. After a reset, start a new baseline.

### 29.4. Server restarts

Some counters reset on restart or have version-dependent behavior. Exporters should distinguish restart generations.

## 30. Selecting Metrics by Workload Type

| Workload | Latency | Throughput | Errors | Resources |
|---|---|---|---|---|
| OLTP | p95/p99 transaction/query, lock wait | TPS, calls/s | deadlocks, timeouts, rollback | CPU, connections, I/O |
| Reporting | query duration, queue time | queries/s, rows scanned | cancellations, statement timeout | I/O, memory, temp files |
| Batch/ETL | job duration, stage duration | rows/s, WAL bytes/s | failed batches, retries | CPU, disk, WAL, temp |
| Logical subscriber | apply freshness, lag | changes/s, WAL/logical bytes | apply errors, sync errors | slot retention, CPU, disk |
| Physical standby | replay freshness | WAL receive/replay rate | disconnects, archive failures | network, disk, recovery CPU |
| Connection pool | acquire latency | checkouts/s | acquire timeout | active/idle/waiters |

### 30.1. OLTP

Prioritize tail latency, lock waits, transaction success, and connection pooling. Average TPS alone is insufficient.

### 30.2. Reporting

Prioritize long query duration, I/O, temp spills, cancellations, and impact on replay and vacuum.

### 30.3. Batch

Prioritize job completion time, rows processed, WAL generation, checkpoint/temporary I/O, and resource headroom.

### 30.4. HA/replication

Prioritize replay freshness, acknowledged durability, archive continuity, slot retention, and failover readiness.

## 31. Workload Attribution

With only cluster-wide metrics, it is hard to tell which service generates the load. Collect context:
- application_name.
- database/user.
- Query ID.
- Application endpoint/operation class.
- Background job name.
- Tenant tier if cardinality is bounded.

### 31.1. application_name

Assign stable names like api-orders, worker-billing, and reporting. Avoid unique per-request names.

### 31.2. Query ID

pg_stat_statements queryid helps group query shapes. Protect query text because it can reveal sensitive schemas, tables, or logic.

### 31.3. Tenant labels

If tenant-level visibility is needed, use bounded tiers/cohorts or sampled logs. Never create millions of time series keyed by tenant ID.

### 31.4. Attribution does not replace isolation

Metrics show which workload is driving load; resource quotas, pool limits, and workload isolation actually contain its impact.

## 32. Dashboards: Service Overview

The primary dashboard should answer:
- Is the service meeting its SLOs?
- Is the request rate rising or falling?
- What are p50/p95/p99 latencies?
- What are the error and timeout rates?
- What is commit/rollback throughput?
- What are primary/standby roles and health?
- How much CPU, memory, and disk headroom remain?
- What is connection pool utilization?
- Which alerts are currently firing?

### 32.1. Put user-facing metrics at the top

Do not force operators to scan 20 CPU panels before knowing whether users are impacted.

### 32.2. Expose time range and resolution

A 5-minute dashboard cannot answer a 30-day trend question. Support both short- and long-term views with appropriate sample resolution.

### 32.3. Annotate deployments and incidents

Mark releases, migrations, failovers, vacuum maintenance, and configuration changes to make correlation straightforward.

### 32.4. Do not cram every metric onto one page

Separate overview, query performance, locks, storage, vacuum, replication, and capacity views.

## 33. Dashboards: Query Performance

Recommended panels:
1. p50/p95/p99 query/API duration.
2. Top queries by total_exec_time.
3. Top queries by mean_exec_time/calls.
4. Calls/s by query class.
5. Rows and block reads/hits.
6. Temporary blocks written.
7. Planning vs. execution time when enabled.
8. Query timeouts/cancellations.
9. Lock wait duration/blockers.
10. Long-running transactions.

### 33.1. Top total time

Finds queries consuming the largest cumulative share of database time.

### 33.2. Top mean time

Finds queries that are slow on every execution, even at low frequency.

### 33.3. Top calls

Finds small queries called excessively often, such as N+1 patterns.

### 33.4. Top temp writes

Finds queries spilling heavily to disk.

## 34. Dashboards: Resources and Saturation

Recommended panels:
- CPU user/system/iowait/steal.
- Memory available, swap, OOM, cgroup throttling.
- Disk free bytes/growth, IOPS, throughput, latency, queue depth.
- WAL bytes/s and pg_wal size.
- Temporary files/bytes/s.
- Connections active/idle/idle in transaction.
- Pool waiters/acquire latency.
- Lock waits/blocker age.
- Checkpoint timing.
- Autovacuum progress/dead tuples/XID age.
- Replication slot retention.

### 34.1. Saturation means queueing

70% CPU may not be saturated. If the run queue and latency climb together, CPU may be becoming a bottleneck.

### 34.2. Disk headroom over time

Do not look only at 100 GB free. If usage is growing at 20 GB/hour, only 5 hours remain. Calculate time-to-full from the trend.

### 34.3. Memory pressure

Track swap/OOM and available memory, not just PostgreSQL shared_buffers.

### 34.4. Connection saturation

When a pool runs out of connections, requests wait before queries even begin. Database query latency can look low while API latency is high.

## 35. Alerting: Alert on Symptoms and Causes

A well-defined alert typically includes:
- Metric and threshold.
- Duration/window.
- Severity.
- Affected service/database.
- User impact/SLO.
- Likely cause.
- Runbook link.
- Owner/escalation.

### 35.1. Symptom alerts

For example, API p95 latency breaching SLO and rising error rate. These signal direct user impact.

### 35.2. Cause alerts

For example, disk free below 10%, rapidly growing replication slot retained WAL, or XID age approaching threshold. These signal technical risk.

### 35.3. Do not alert on every metric at every threshold

Alerts that require no action create alert fatigue. Use dashboards for context and alerts for situations requiring intervention.

### 35.4. Duration/hysteresis

Use evaluation windows to filter out brief spikes. For disk-full, connection exhaustion, or replication loss, faster alerting may be appropriate.

## 36. Error Budgets and Burn Rate

If an SLO defines 99.9% success, the error budget is the allowed error margin over the measurement window.

Burn rate indicates how quickly the error budget is being consumed relative to the sustainable rate.

### 36.1. Fast burn

A sharp error-rate spike over a few minutes can exhaust the budget rapidly and calls for a high-priority alert.

### 36.2. Slow burn

A small but persistent error rate may not justify an immediate page, yet over time it accumulates into an SLO breach. Use longer-window alerts to catch slow burns.

### 36.3. Do not use resource utilization as error budget

95% CPU does not automatically mean an SLO has been breached. Measure request success and latency directly.

### 36.4. Exclusions must be explicit

Maintenance windows, synthetic checks, and expected client errors must follow published SLO policies.

## 37. Correlation: Finding Root Causes Across Metrics

A sample diagnostic matrix:

| Symptom | Related Metrics | Investigation Path |
|---|---|---|
| p95 rising, CPU rising | CPU, query total time, plans | Query plan / CPU saturation |
| p95 rising, CPU low | lock waits, I/O latency, pool wait | Locks, storage, or connection queue |
| TPS falling, WAL lag rising | WAL rate, replay rate, sender state | Replication pressure |
| Errors rising, latency rising | SQLSTATE, deadlocks, timeouts | Transaction failures / locks |
| Disk free dropping fast | temp bytes, WAL, table growth | Temp spills, slot retention, workload growth |
| Vacuum slow, dead tuples rising | long transactions, xmin, slots | Vacuum horizon / blockers |
| API slow, DB queries fast | pool wait, network, app traces | Pooling / network / application |
| High connection count | active/idle, pool waiters, backend CPU | Pool sizing / churn / leaked sessions |

### 37.1. Correlation is not causation

Two metrics rising together do not prove one caused the other. Use timelines, traces, query evidence, and controlled changes.

### 37.2. Compare against baselines

Compare with the same hour/day and workload class. Traffic patterns often follow business-hour or seasonal cycles.

### 37.3. Deployment annotations

A query plan regression immediately after a release can explain a latency spike. Keep deployment markers visible on dashboards.

### 37.4. Follow the critical path

Find where requests spend most of their time: queueing, network, database execution, locks, I/O, or external services.

## 38. Sampling Intervals and Metric Overhead

Sampling too frequently adds overhead; sampling too infrequently misses spikes and hurts percentile accuracy.

Considerations:
- 5–15 seconds for critical alert metrics, depending on scale.
- 30–60 seconds for many resource and counter metrics.
- 1–5 minutes for capacity trends.
- Application histograms for continuous latency capture.
- Event/log-based collection for rare but critical errors.

These are reference ranges, not rigid rules.

### 38.1. Monitoring queries also generate load

Periodically querying pg_stat_activity or pg_stat_statements has small but non-zero overhead. Avoid running complex catalog queries every second on large clusters.

### 38.2. Scrape timeouts

Collectors must never hold connections or transactions open for long. Enforce timeouts and use an appropriate monitoring role.

### 38.3. Avoid synchronized scrapes

Multiple exporters scraping simultaneously can cause periodic spikes. Use jitter or staggered schedules.

### 38.4. Metric cardinality

Query text, raw IDs, and unbounded labels can drive up memory and storage costs in the monitoring backend. Normalize query classes.

## 39. Security and Privacy in Monitoring

Monitoring data can contain:
- SQL text.
- Table/schema names.
- User/database names.
- Client addresses.
- Error details.
- Parameter values if logging is overly broad.

### 39.1. Do not log secrets

Never log passwords, tokens, personal data, or sensitive payloads in query logs or metric labels.

### 39.2. Monitoring role

Follow least privilege, such as a role granted only the required monitoring permissions. Never grant superuser to an exporter just to read stats.

### 39.3. Retention and access control

Metrics and logs can reveal workload patterns and business activity. Enforce appropriate retention, access policies, and redaction.

### 39.4. Query text exposure

pg_stat_statements query text can contain literals depending on normalization, version, and configuration. Restrict access and avoid exporting raw text unnecessarily.

## 40. Version-Aware Metric Collection

PostgreSQL statistics views change across major versions:
- pg_stat_io appeared in PostgreSQL 16.
- Checkpoint statistics evolved, with PostgreSQL 17 adding pg_stat_checkpointer.
- pg_stat_statements fields depend on extension version and options.
- Several columns in replication and subscription views change across versions.

### 40.1. Check server version

```sql
SELECT version();
```

Or retrieve the numeric version:

```sql
SHOW server_version_num;
```

### 40.2. Inspect view columns

Query information_schema.columns for supported views or inspect view definitions in pg_catalog. Verify exporter queries against the live server version.

### 40.3. Multi-version dashboards

Use version-aware exporters, version-specific queries, or a compatibility layer. Never assume one SQL query works across every cluster.

### 40.4. Mark missing metrics explicitly

If a version lacks a metric, display unavailable/unsupported rather than showing 0.

## 41. Minimum Metric Set by Layer

A pragmatic baseline:

**Service/application**
- Request rate.
- Success/error rate.
- p50/p95/p99 latency.
- Connection pool acquire wait.
- Business operation throughput.

**PostgreSQL**
- TPS commits/rollbacks.
- Top query total/mean/calls.
- Active/idle/idle-in-transaction sessions.
- Lock waits/deadlocks.
- Temporary bytes/files.
- Database size and growth.

**Host/storage**
- CPU/run queue.
- Memory available/swap/OOM.
- Disk free, latency, IOPS, throughput, queue.
- WAL filesystem usage.

**Maintenance/HA**
- Autovacuum progress/dead tuples/XID age.
- Checkpoint/WAL metrics.
- Replication positions/lag/state.
- Slot retained WAL.
- Archive success/failure.

### 41.1. Start small

Enable a core set of metrics and expand based on observed incident patterns. Avoid deploying hundreds of alerts before knowing who handles each one.

### 41.2. Every alert needs an owner

Alerts need an owner and on-call path. Without an owner, alerts rarely produce action.

### 41.3. Critical alerts need runbooks

At minimum, document diagnostic queries, verification steps, stop conditions, escalation paths, and rollback/mitigation steps.

## 42. Example: Rising Latency with Unchanged Throughput

Scenario:
- TPS is steady.
- p95 query latency rises from 40 ms to 900 ms.
- CPU is 45%.
- Disk latency is rising.
- Lock waits are not rising.

Investigation path:
1. Check pg_stat_statements for queries with rising mean/total time.
2. Check pg_stat_io and OS disk latency.
3. Check volume throttling and queue depth.
4. Check temp bytes and query spills.
5. Check checkpoint and backup activity.
6. Compare against recent deployments or storage changes.

Do not conclude CPU is the bottleneck simply because the database is slow.

## 43. Example: Falling Throughput and Rising Errors

Scenario:
- Commit TPS drops.
- Rollback/error rate rises.
- Deadlocks increase.
- Active sessions show many lock waits.
- CPU is low.

Investigation path:
1. Find blocking sessions with pg_blocking_pids.
2. Read deadlock logs.
3. Identify transactions holding locks for long periods.
4. Compare with recent application deployments or transaction ordering changes.
5. Check for retry storms amplifying load.
6. Fix lock ordering, shorten lock durations, and add jittered backoff to retries.

Low CPU here is likely because backends are blocked waiting on locks, not because traffic disappeared.

## 44. Example: Disk Growing Rapidly While Database Size Barely Changes

Scenario:
- Data directory grows.
- Table sizes remain mostly stable.
- pg_wal grows.
- A replication slot is inactive.
- Archive failures appear.

Investigation path:
1. Check pg_replication_slots restart_lsn and active state.
2. Identify the slot owner/consumer.
3. Check pg_stat_archiver and logs.
4. Check archive storage credentials and capacity.
5. Calculate retained WAL distance and disk headroom.
6. Repair the consumer or archive path; only drop a slot when a resync plan is in place.

## 45. Example: Slow API While PostgreSQL Queries Are Fast

Scenario:
- API p95 = 1.2 seconds.
- Database query p95 = 20 ms.
- Pool acquire wait = 900 ms.
- Active pool connections are near their limit.
- Database CPU remains low.

The likely cause is pool saturation or a connection leak. Raising max_connections immediately may increase backend pressure. Investigate pool sizing, request concurrency, connection lifetimes, and transaction leaks first.

## 46. Problem-to-Metric Checklist

| Question | Metrics to Check |
|---|---|
| Are users experiencing slowness? | API p95/p99, DB query duration |
| How many operations are running? | Request rate, TPS, query calls/s |
| Are operations failing? | Error rate, SQLSTATE, rollbacks, deadlocks |
| Waiting for a connection? | Pool acquire latency, waiters |
| Waiting on a lock? | Lock waits, blocker age, blocked sessions |
| Is CPU saturated? | CPU, run queue, throttling |
| Is storage slow? | I/O latency, queue depth, IOPS, throughput |
| Is memory under pressure? | Available memory, swap, OOM |
| Is disk running out of space? | Free bytes, growth rate, WAL/temp usage |
| Are queries spilling to disk? | temp_files/temp_bytes, temp blocks |
| Is vacuum blocked? | dead tuples, long transactions, xmin, slots |
| Is the standby stale? | replay LSN, lag, freshness token |
| Is PITR archiving failing? | archiver counters, WAL inventory |
| Which queries consume the most time? | pg_stat_statements total/mean/calls |
| Which queries have slow tails? | Application/APM histograms, slow logs |

## 47. Official PostgreSQL Documentation

- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring.html) — activity statistics, views, and progress reporting.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_database, pg_stat_activity, replication, and statistics behavior.
- [pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html) — query planning and execution statistics.
- [Monitoring I/O](https://www.postgresql.org/docs/current/monitoring-stats.html) — I/O statistics and pg_stat_io.
- [Monitoring Progress](https://www.postgresql.org/docs/current/progress-reporting.html) — vacuum, analyze, copy, create index, and other progress views.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — autovacuum, dead tuples, and freezing.
- [Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html) — memory, worker, and resource settings.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html) — WAL, checkpoint, and durability settings.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html) — replication slots/senders/receivers.
- [Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html) — SQLSTATE classes and codes.

View columns, counters, and extensions can differ across PostgreSQL major versions. Consult documentation for your exact version, inspect pg_settings and view definitions, and test exporter queries on live servers.

## 48. Practice Exercises with Answers

### Exercise 1. What are the four primary signal groups in this lesson?

**Answer:** Latency, throughput, errors, and saturation/resources.

### Exercise 2. What does RED stand for?

**Answer:** Rate, Errors, Duration.

### Exercise 3. What does USE stand for?

**Answer:** Utilization, Saturation, Errors.

### Exercise 4. Why are both RED and USE needed?

**Answer:** RED reveals user-facing symptoms; USE helps locate resource bottlenecks and saturation.

### Exercise 5. What does p95 mean?

**Answer:** 95% of observations have latency at or below the p95 value within the defined window and population.

### Exercise 6. Can mean latency replace p99?

**Answer:** No. The mean can hide tail latency; histograms or raw observations are needed.

### Exercise 7. Does pg_stat_statements provide p95 query latency?

**Answer:** No. It provides aggregate statistics such as calls and total/mean execution time; percentiles require other instrumentation.

### Exercise 8. Why might a query have a high total_exec_time?

**Answer:** It runs frequently, each execution is slow, or both; inspect calls and mean together.

### Exercise 9. What might a query with very high calls but low mean indicate?

**Answer:** An N+1 pattern or a small query called excessively often.

### Exercise 10. How do query age and transaction age differ?

**Answer:** Query age measures the current statement; transaction age measures from when the transaction began.

### Exercise 11. Why is idle in transaction dangerous?

**Answer:** It can hold locks and snapshots and block autovacuum cleanup.

### Exercise 12. Is TPS from pg_stat_database a counter or a gauge?

**Answer:** xact_commit and xact_rollback are cumulative counters; you must compute delta over time.

### Exercise 13. What happens if a counter drops between two samples?

**Answer:** A stats reset or restart likely occurred; reset the baseline and do not compute a negative rate.

### Exercise 14. Does TPS equal business orders/s?

**Answer:** Not necessarily; a single transaction may create multiple orders or none at all.

### Exercise 15. What does WAL bytes/s measure?

**Answer:** The rate at which WAL is generated, useful for planning replication, archiving, and storage capacity.

### Exercise 16. Does WAL bytes equal data growth?

**Answer:** No. WAL also includes index updates, page changes, full-page images, and internal records.

### Exercise 17. What denominator does error rate require?

**Answer:** The total number of operations in the same population and time window.

### Exercise 18. Is every rollback an error?

**Answer:** No. Some rollbacks are intentional business or validation flows.

### Exercise 19. How does SQLSTATE help?

**Answer:** It classifies PostgreSQL errors by code/class, such as unique violations, deadlocks, and serialization failures.

### Exercise 20. Is pg_stat_database.deadlocks a counter or a gauge?

**Answer:** A cumulative counter; take the delta to compute deadlocks/s.

### Exercise 21. Are connection failures prior to backend creation always visible in pg_stat_activity?

**Answer:** No. They may appear only in server logs, proxy metrics, or application metrics.

### Exercise 22. Is high CPU utilization automatically an incident?

**Answer:** No. Evaluate latency, throughput, run queue, headroom, and workload context.

### Exercise 23. What can cause low CPU with high latency?

**Answer:** Lock waits, disk I/O, network delays, pool queueing, or external dependencies.

### Exercise 24. Why can summing RSS across all PostgreSQL backends be misleading?

**Answer:** Shared memory gets counted multiple times across processes.

### Exercise 25. Is work_mem the maximum total memory a single query can use?

**Answer:** No. A query can allocate work_mem per sort/hash node and per worker, and concurrent sessions multiply total usage.

### Exercise 26. Should disk free bytes be alerted by growth rate?

**Answer:** Yes. Time-to-full can be far more informative than a fixed percentage threshold.

### Exercise 27. Which version introduced pg_stat_io?

**Answer:** PostgreSQL 16 and later.

### Exercise 28. Can track_io_timing introduce overhead?

**Answer:** Yes; benchmark its impact on your platform and workload before enabling it widely.

### Exercise 29. Is temp_bytes in pg_stat_database a counter or a gauge?

**Answer:** A cumulative counter; compute the delta to obtain the temp write rate.

### Exercise 30. What risk comes from increasing work_mem?

**Answer:** Memory usage grows across operations, workers, and concurrent sessions, risking memory pressure or OOM.

### Exercise 31. What checkpoint statistics change arrived in PostgreSQL 17?

**Answer:** pg_stat_checkpointer was introduced, separating checkpoint statistics that were previously part of pg_stat_bgwriter.

### Exercise 32. Is n_dead_tup an exact count of dead rows?

**Answer:** No. It is a statistical estimate.

### Exercise 33. Does rising dead tuples always prove bloat is growing at the same rate?

**Answer:** No. Bloat depends on page reuse, visibility, indexes, and workload; analyze it separately.

### Exercise 34. What does age(datfrozenxid) track?

**Answer:** Transaction ID age and wraparound/freezing risk.

### Exercise 35. Can a replication slot affect vacuum?

**Answer:** Yes. xmin/catalog_xmin or retained WAL can hold back data cleanup and WAL removal longer.

### Exercise 36. How do active connections differ from pool waiters?

**Answer:** Active connections are occupying database backends; pool waiters are waiting for the pool to grant a connection.

### Exercise 37. Does a high lock count always mean contention?

**Answer:** No. Measure lock wait duration, blocked sessions, and impact.

### Exercise 38. What does pg_blocking_pids help identify?

**Answer:** The PIDs currently blocking a specific backend.

### Exercise 39. Does healthy archiving prove standby streaming is healthy?

**Answer:** No. Archiving and streaming are two separate data paths.

### Exercise 40. Does a 99% cache hit ratio guarantee fast queries?

**Answer:** No. CPU, locks, query plans, network, and storage can still bottleneck execution.

### Exercise 41. Why distinguish counters from gauges?

**Answer:** Counters require deltas/rates; gauges represent point-in-time values and require trend/window analysis.

### Exercise 42. What are histograms used for?

**Answer:** Recording distributions of observations and calculating quantiles and SLO latencies.

### Exercise 43. What are the risks of labeling metrics with raw query text?

**Answer:** High cardinality, heavy storage/memory cost, and potential exposure of sensitive data.

### Exercise 44. Why use a stable application_name?

**Answer:** To attribute workload by service or worker without creating unique labels per request.

### Exercise 45. API is slow while DB queries are fast; which metrics should you inspect?

**Answer:** Connection pool acquire wait, network, application traces, and external dependency durations.

### Exercise 46. TPS drops, deadlocks rise, and CPU is low; what does this suggest?

**Answer:** Transactions are likely blocked or deadlocking; investigate the lock graph and deadlock logs.

### Exercise 47. Disk usage grows quickly, pg_wal grows, and a slot is inactive; what does this suggest?

**Answer:** A replication slot may be retaining WAL; identify its owner/consumer and verify archive health before intervening.

### Exercise 48. Why do alerts need a duration/window?

**Answer:** To avoid paging on brief spikes and separate transient noise from sustained incidents.

### Exercise 49. Why do dashboards need deployment annotations?

**Answer:** They help correlate latency, error, and resource shifts with releases, migrations, or configuration changes.

### Exercise 50. What components belong in a good metric alert?

**Answer:** Metric/threshold/window, severity, affected service, user impact, owner, likely cause, and runbook/action.

## 49. Metric Selection and Operations Checklist

| Step | What to Verify |
|---|---|
| Business | Which user-facing operations and SLOs must be protected? |
| Latency | Measured at API, pool, query, transaction, or lock boundaries? |
| Percentiles | Are histograms/sample counts available for p95/p99? |
| Throughput | Defined as operations/s, TPS, or business events/s? |
| Errors | Are expected rollbacks separated from unexpected failures? |
| Resources | Is there headroom in CPU, memory, I/O, disk, and connections? |
| Saturation | Are queues, pool waiters, or lock waits present? |
| Queries | Is pg_stat_statements enabled and version-compatible? |
| Stats | Do counters handle stats_reset and restarts? |
| Vacuum | Are dead tuples, long transactions, XID age, and slots tracked? |
| HA | Are replication lag, archive health, and failover freshness tracked? |
| Cardinality | Are labels bounded and safe? |
| Security | Are SQL text, parameters, and secrets protected? |
| Alerts | Do alerts have thresholds, durations, severities, and owners? |
| Runbooks | Are queries, diagnosis, mitigation, and verification documented? |
| Review | Are baselines and deployment/incident annotations maintained? |

## 50. Summary: Measure Experience, Explain Load, and Locate Saturation

```text
USER / BUSINESS SLO
        |
        v
  LATENCY + ERRORS
        |
        v
     THROUGHPUT
        |
        v
 SATURATION / RESOURCES
        |
        v
 PostgreSQL views + OS + APM
        |
        v
 Correlate -> Diagnose -> Act -> Verify
```

Key takeaways:

1. **Start from user impact and SLOs.** Metrics are only useful when they answer an operational question.
2. **RED measures request rate, errors, and duration.** It forms the foundation of service-facing dashboards.
3. **USE measures resource utilization, saturation, and errors.** Use it to uncover CPU, memory, disk, network, or queue bottlenecks.
4. **Track p50/p95/p99, not just the mean.** Tail latency is usually where degraded user experience shows up first.
5. **pg_stat_statements provides aggregate query statistics.** Obtaining p95/p99 query latency requires histograms or observations at the instrumentation layer.
6. **Cumulative counters must be converted via delta/time.** Always account for stats resets and server restarts.
7. **Combine database metrics with OS, pool, and application metrics.** No single layer explains the entire request path.
8. **Evaluate errors alongside volume.** Rollbacks can be expected; SQLSTATE enables proper classification.
9. **High resource utilization must be read next to queues and latency.** Saturation shows up as work forced to wait.
10. **Monitor vacuum, XID age, WAL, replication, and disk retention.** They can trigger incidents even while query dashboards look normal.
11. **Use bounded-cardinality labels and protect query text.** Monitoring systems also require capacity and security discipline.
12. **Alerts must have owners and actions.** Dashboards explain; alerts signal conditions that require intervention.

**One sentence to remember:** *Select metrics around operational questions—where requests are slow, how much work is processed, which operations fail, and which resources are saturating—then align those signals on a shared timeline to find the root cause.*
