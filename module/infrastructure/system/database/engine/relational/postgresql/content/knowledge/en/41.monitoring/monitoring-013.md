# Saving Baselines and Comparing Pre/Post-Change Metrics in PostgreSQL

## 1. Why Do We Need a Baseline?

A PostgreSQL change can make a system faster in one dimension while making it slower in another. Adding an index may reduce read latency while increasing INSERT/UPDATE overhead and storage usage. Increasing memory for one workload may reduce physical reads while shrinking available RAM for the OS or co-located services. Tuning autovacuum may lower dead tuples while increasing peak-hour I/O.

Looking at a single chart after deployment makes it hard to tell whether a change actually made a difference. You need to record a baseline: a representative set of measurements capturing system state before the change, along with capture window, workload, configuration, and operational context. After the change, collect the same metrics in an equivalent way and compare them.

A baseline helps answer concrete questions:

- Did throughput increase or decrease?
- How did p50, p95, and p99 latencies change?
- Did error rates, timeouts, and failed transactions increase?
- How did CPU, memory, disk I/O, network, and connection pressure shift?
- Which queries changed the most?
- Did replication lag, WAL generation, or vacuum behavior degrade?
- Do findings still hold after normalizing for request/transaction volume?
- Can differences be attributed to the deployed change or to another factor?
- Which thresholds require a rollback?

A baseline is not merely a static snapshot of numbers. It is a repeatable measurement with a clear scope and well-defined conditions.

```text
        CHANGE PROPOSAL
              |
              v
     Define expected outcome
              |
              v
     Capture PRE-CHANGE baseline
              |
              v
       Apply one controlled change
              |
              v
     Capture POST-CHANGE metrics
              |
              v
   Normalize for workload and duration
              |
              v
   Compare outcomes and guardrails
          /             \
         v               v
      Accept           Roll back
         |
         v
   Save evidence and new baseline
```

## 2. Learning Objectives

After this lesson, you will be able to:

1. Explain what a baseline is and its role in PostgreSQL operations.
2. Distinguish cumulative counters, instantaneous gauges, rates, and percentiles.
3. Define the scope, duration, and workload to measure.
4. Record PostgreSQL version, configuration, topology, and environment metadata.
5. Collect database, query, connection, lock, vacuum, and replication metrics.
6. Monitor WAL generation, checkpoints, and I/O.
7. Use `pg_stat_statements` to compare workloads by query fingerprint.
8. Normalize metrics per transaction, request, or unit of work.
9. Distinguish cache hit ratio from actual physical disk I/O.
10. Read `pg_stat_activity` and wait events.
11. Detect statistics resets and changes that invalidate comparisons.
12. Compare pre/post periods using equivalent time windows and load conditions.
13. Evaluate query plan changes with `EXPLAIN`.
14. Combine PostgreSQL metrics with OS, application, and infrastructure metrics.
15. Establish guardrails and rollback criteria.
16. Store baselines with metadata and change history.
17. Avoid false conclusions caused by workload seasonality or traffic mix shifts.
18. Build comparison dashboards and change-impact reports.
19. Interpret regressions, improvements, and trade-offs.
20. Organize a repeatable measurement workflow after every significant change.

## 3. What Is a Baseline and What Should Be Recorded?

### 3.1. A Baseline Describes a Comparable State

A useful baseline records not just metric values, but also the conditions that produced them. For instance, 65% CPU has little standalone meaning without knowing requests/second, query mix, connection count, and time of day.

Each capture should include metadata:

- Cluster/database identity and environment.
- PostgreSQL major/minor version.
- Start/end timestamps and timezone.
- Primary/standby role, timeline, and replication topology.
- CPU, RAM, storage type/capacity, and network placement.
- Key settings from `pg_settings`.
- Application version, schema migration, and release ID.
- Workload profile: requests, transactions, batch jobs, concurrency.
- Concurrent maintenance: `VACUUM`, `ANALYZE`, backups, index builds.
- Statistics reset time and server restart timestamps.
- Other changes occurring inside the measurement window.
- Operator and change ticket.

### 3.2. Baselines Have Multiple Layers

You can organize a baseline into four layers:

| Layer | Contents | Examples |
| --- | --- | --- |
| Business/application | Users and workload | requests/s, transactions/s, p95 latency, error rate |
| PostgreSQL | Database behavior | commits, rollbacks, query time, cache, WAL, locks |
| Host/infrastructure | Resources | CPU, RAM, disk latency, IOPS, network |
| Configuration/topology | System conditions | version, settings, replicas, storage, pool size |

A change can have indirect effects. For example, faster queries may shift connection pool behavior so connections are held longer elsewhere, raising total active sessions. Inspect all layers together.

### 3.3. A Pre-Change Baseline Is Not a Single Value

A snapshot at 02:00 does not represent peak hours. Measure across multiple equivalent windows and store distributions, peaks, and trends.

### 3.4. Create a New Baseline After Accepting a Change

Once a change is verified stable, the post-change measurements become the new baseline for future changes. Retain older baselines for historical traceability instead of overwriting them.

## 4. Design Measurements Before Collecting

### 4.1. Write a Hypothesis

Every change should carry a testable hypothesis.

Examples:

- Adding an index on `orders` will lower p95 latency for order lookup queries.
- Tuning pool size will reduce connection wait time.
- Adjusting autovacuum thresholds will reduce dead tuple accumulation.
- Changing synchronous replication will increase commit latency while lowering RPO.
- Optimizing a query will reduce shared buffer reads and total execution time.

The hypothesis should name both the primary metric and guardrail metrics that could worsen.

### 4.2. Choose Primary Metrics and Guardrails

Example for a new index:

| Role | Metric |
| --- | --- |
| Primary outcome | Query p95 latency, execution time/request |
| Guardrail | INSERT/UPDATE latency, WAL bytes, index size |
| Capacity | CPU, I/O latency, free disk |
| Correctness | Row counts, query result consistency |
| Availability | Error rate, connection failures |

Do not pick only metrics likely to improve. Record metrics that might degrade beforehand.

### 4.3. Choose Equivalent Measurement Windows

Pre- and post-change windows must match across:

- Time of day and day of week.
- Traffic volume and request mix.
- Batch/cron jobs.
- Data size and cache warmness.
- Client counts and concurrency.
- Maintenance activities.
- Replica state and network conditions.

If workload shifts substantially, normalize per request/transaction or run a controlled load test with a fixed script.

### 4.4. Keep Windows Long Enough

A short measurement may miss checkpoints, autovacuum runs, batch jobs, or traffic peaks. Window duration depends on workload cycles; systems with daily batches need longer windows than steady-state API services.

### 4.5. Change One Major Variable When Possible

Changing indexes, PostgreSQL memory settings, connection pools, and application releases simultaneously makes attribution difficult. Split changes into smaller steps or design experiments with control/canary groups.

## 5. Classify Metrics to Avoid Misreading

### 5.1. Cumulative Counters

Counters generally increase since the last reset, for example:

- `xact_commit` and `xact_rollback`.
- `blks_read` and `blks_hit`.
- `wal_bytes`.
- `shared_blks_read` in `pg_stat_statements`.
- `confl_snapshot` in `pg_stat_database_conflicts`.

Never compare raw cumulative counters directly across two intervals of different lengths. Take the delta and compute a rate.

Formulas:

```text
delta = counter_after - counter_before
rate_per_second = delta / elapsed_seconds
rate_per_transaction = delta / committed_transactions
```

If a counter decreases, statistics may have been reset, the server may have restarted, or view/identity scope changed. Check reset timestamps before computing deltas.

### 5.2. Instantaneous Gauges

Gauges capture state at a single point in time:

- `numbackends`.
- Active session count.
- Disk free space.
- Current replication lag.
- Memory usage.
- Waiting lock count.

Sample periodically to compute min/median/max and percentiles; a single snapshot cannot describe peaks within a window.

### 5.3. Rates

A rate measures change per unit time, such as transactions/s, WAL MB/s, reads/s, or requests/s. Rates allow comparisons across windows of different lengths, though you must still account for workload mix.

### 5.4. Percentiles and Histograms

p50/p95/p99 latencies describe the response time distribution. Averages can hide tail latency: most requests may be fast while a small subset is extremely slow.

PostgreSQL statistics views do not provide full percentile latencies for arbitrary queries. Collect histograms from application tracing, APM, proxies, or metrics systems. `pg_stat_statements` offers totals and means per query fingerprint, not a substitute for histograms.

### 5.5. Ratios

Cache hit ratio, error percentage, and replication success ratio are ratios. Compute them from numerator/denominator deltas within the same window whenever possible. Avoid naively averaging ratios from intervals with vastly different request volumes.

### 5.6. Snapshots and Deltas Must Be Properly Paired

Every snapshot requires a timestamp and metadata. Pair snapshots from the same instance, database, role, and metric definition. Never subtract counters taken from two different servers or across two separate reset epochs.

## 6. Recording PostgreSQL Metadata and Configuration

### 6.1. Version and Identity

```sql
SELECT
    version() AS server_version,
    current_setting('server_version_num') AS server_version_num,
    current_database() AS database_name,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    pg_postmaster_start_time() AS server_started_at,
    clock_timestamp() AS captured_at;
```

Over Unix sockets, `inet_server_addr()` may be NULL. Store cluster identity from inventory/backup metadata when distinguishing instances sharing the same database name.

### 6.2. Key Settings

```sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    sourcefile,
    sourceline,
    pending_restart
FROM pg_catalog.pg_settings
WHERE name IN (
    'shared_buffers',
    'work_mem',
    'maintenance_work_mem',
    'effective_cache_size',
    'max_connections',
    'max_worker_processes',
    'max_parallel_workers',
    'max_parallel_workers_per_gather',
    'autovacuum',
    'autovacuum_max_workers',
    'checkpoint_timeout',
    'checkpoint_completion_target',
    'max_wal_size',
    'min_wal_size',
    'wal_level',
    'synchronous_commit',
    'synchronous_standby_names',
    'effective_io_concurrency'
)
ORDER BY name;
```

Not every setting exists on every major version. Add other relevant settings depending on the change under evaluation. `sourcefile` may be NULL if the role lacks permission to view configuration paths or if the setting does not originate from a file.

### 6.3. Distinguish Active Runtime Settings from Edited Config Files

`pg_settings.setting` shows the effective runtime value. `pending_restart = true` indicates changes not yet active because a restart is required. Never treat edited config files alone as proof that the running server uses the new values.

### 6.4. Record Configuration per Role

In HA setups, record settings separately for the primary and each standby. Some settings have role-specific semantics or apply only on one node. Record topology and synchronous standby state alongside the baseline.

### 6.5. Protect Sensitive Metadata

Never export passwords, connection strings containing secrets, private keys, or tokens into baseline artifacts. Record secret reference names and versions if traceability is required.

## 7. Database-Level Metrics from `pg_stat_database`

### 7.1. Basic Snapshot

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
    temp_files,
    temp_bytes,
    deadlocks,
    stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname IS NOT NULL
ORDER BY datname;
```

These columns represent cumulative counters or gauges since the last statistics reset, depending on each column's semantics. Capture snapshots before and after the measurement window.

### 7.2. Transactions per Second

Divide the delta of `xact_commit + xact_rollback` by elapsed time to estimate transaction completion rate. If applications open empty transactions or batch multiple statements per transaction, TPS does not equal request rate.

### 7.3. Rollback Rate

```text
rollback_ratio = delta_xact_rollback
                 / (delta_xact_commit + delta_xact_rollback)
```

A rising rollback ratio can indicate application errors, retry loops, or transaction conflicts. Classify SQLSTATE codes and application logs before drawing conclusions.

### 7.4. Cache Hit Ratio

```sql
SELECT
    datname,
    round(
        100.0 * blks_hit
        / NULLIF(blks_hit + blks_read, 0),
        2
    ) AS shared_buffer_hit_pct
FROM pg_catalog.pg_stat_database
WHERE datname IS NOT NULL;
```

This reflects hit ratio within PostgreSQL shared buffers according to database counters. `blks_read` does not guarantee physical disk reads: the OS page cache may serve those reads. Never rely on a single hit-ratio threshold alone to justify increasing `shared_buffers`.

### 7.5. Temporary Files

Rising `temp_files` and `temp_bytes` can signal sorts, hashes, or materializations spilling to disk. Normalize deltas per transaction/request and inspect `pg_stat_statements` to identify which queries generate temp blocks.

### 7.6. Database Conflicts

On standbys, `pg_stat_database_conflicts` tracks recovery conflict counters. Capture separate snapshots when changes involve hot standby behavior, `VACUUM`, DDL, or replay delays.

## 8. Query-Level Baselines with `pg_stat_statements`

### 8.1. Why Track Query Fingerprints?

Database-level TPS may stay flat while a single critical query regresses sharply. `pg_stat_statements` aggregates normalized statements by query identity, helping pinpoint queries dominating execution time or I/O.

### 8.2. Installation and Prerequisites

The extension typically loads via `shared_preload_libraries`, followed by a server restart and extension creation in the target database:

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

Follow your standard change process for setup. Check `pg_stat_statements.track`, `pg_stat_statements.max`, `track_planning`, and reset/deallocation behavior for your version. Tracking adds some overhead, so align configuration with measurement goals.

### 8.3. Snapshot Expensive Queries

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    shared_blks_dirtied,
    shared_blks_written,
    temp_blks_read,
    temp_blks_written,
    wal_bytes,
    left(query, 300) AS query_sample
FROM pg_catalog.pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 50;
```

Available columns depend on PostgreSQL and extension versions. If a column is missing, inspect the server's view schema rather than assuming all clusters share identical columns.

### 8.4. Compare Deltas by `queryid`

Save pre- and post-change snapshots. Join matching `queryid` values within the same database/user context, then compute:

- Delta `calls`.
- Delta `total_exec_time`.
- Delta `rows`.
- Delta `shared_blks_read`/`hit`.
- Delta temp blocks.
- Delta `wal_bytes`.

From deltas, calculate window-specific mean execution time:

```text
window_mean_exec_ms = delta_total_exec_time / NULLIF(delta_calls, 0)
```

Never subtract pre and post `mean_exec_time` values directly, because `mean_exec_time` is cumulative since reset rather than scoped to your window.

### 8.5. `queryid` Can Change

Query fingerprints can shift across PostgreSQL versions, normalization updates, or query text changes. Save `query_sample`, database, user, and version alongside `queryid`. Never join solely on `queryid` across differing clusters or versions without verification.

### 8.6. Total Time and Mean Time Answer Different Questions

A query with a low mean called millions of times can dominate total CPU. A rare query with a high mean can drive tail latency. Rank by total time, calls, and mean simultaneously.

### 8.7. `pg_stat_statements` Does Not Provide p95

Mean execution time cannot substitute for p95/p99. Use APM, distributed tracing, or application histograms for end-to-end and tail latencies, then correlate with query-level stats to locate causes.

### 8.8. Resets and Deallocation

Calling `pg_stat_statements_reset()` clears stats and invalidates delta comparisons lacking a pre-reset snapshot. On supported versions, `pg_stat_statements_info` tracks resets and deallocations. Store reset timestamps with your baseline data.

## 9. Connection and Transaction Metrics

### 9.1. Connection State Distribution

```sql
SELECT
    datname,
    state,
    wait_event_type,
    wait_event,
    count(*) AS sessions
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname, state, wait_event_type, wait_event
ORDER BY datname, sessions DESC;
```

Common states include `active`, `idle`, and `idle in transaction`. Many `idle` connections can be normal behind a pooler; compare against pool settings and `max_connections`.

### 9.2. Active Queries and Wait Events

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    query_start,
    clock_timestamp() - query_start AS query_age,
    xact_start,
    clock_timestamp() - xact_start AS transaction_age,
    left(query, 300) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'client backend'
  AND state = 'active'
ORDER BY query_start;
```

Wait events distinguish queries burning CPU from queries waiting on locks, I/O, clients, or other resources. Event names and classifications can change across PostgreSQL versions.

### 9.3. Idle in Transaction

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    xact_start,
    clock_timestamp() - xact_start AS xact_age,
    state_change,
    clock_timestamp() - state_change AS state_age,
    backend_xmin,
    left(query, 200) AS last_query
FROM pg_catalog.pg_stat_activity
WHERE state LIKE 'idle in transaction%'
ORDER BY xact_start;
```

Long-open transactions pin snapshots, locks, and vacuum horizons. Compare before and after changing connection pools or application transaction boundaries.

### 9.4. Connection Saturation

Compare `numbackends`, `max_connections`, pool active/idle/waiting counts, and connection establishment rate. Do not simply raise `max_connections` because sessions look high; each backend adds memory and scheduling overhead.

### 9.5. Track Connection Churn

A pooler constantly opening and closing connections increases authentication overhead and backend startup cost. Track new connections/second, pool wait time, and PostgreSQL connection failures from application telemetry.

## 10. Lock and Blocking Metrics

### 10.1. Count Waiting Locks

```sql
SELECT
    locktype,
    mode,
    relation::regclass AS relation,
    count(*) AS waiting_locks
FROM pg_catalog.pg_locks
WHERE NOT granted
GROUP BY locktype, mode, relation
ORDER BY waiting_locks DESC;
```

### 10.2. Find Blockers and Blocked Sessions

```sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.application_name AS blocked_app,
    blocked.wait_event_type,
    blocked.wait_event,
    clock_timestamp() - blocked.query_start AS blocked_query_age,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    clock_timestamp() - blocker.xact_start AS blocker_xact_age,
    left(blocked.query, 200) AS blocked_query,
    left(blocker.query, 200) AS blocker_query
FROM pg_catalog.pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(pg_catalog.pg_blocking_pids(blocked.pid)) AS b(pid)
JOIN pg_catalog.pg_stat_activity AS blocker
  ON blocker.pid = b.pid
ORDER BY blocked.query_start;
```

A single lock snapshot cannot capture contention over time. Record blocking frequency, wait durations, and query identities across the measurement window.

### 10.3. Deadlocks

Use `deadlocks` deltas from `pg_stat_database`, alongside PostgreSQL logs with `log_lock_waits`/deadlock logging per policy. Rising deadlock counts are a crucial guardrail during schema, index, or transaction boundary changes.

### 10.4. Lock Timeout and Statement Timeout

When modifying timeout settings, also track timed-out or canceled query counts in application logs. A lower p95 caused by aborting slow queries is not a real improvement.

## 11. Vacuum, Analyze, and Table Health

### 11.1. Table Statistics

```sql
SELECT
    schemaname,
    relname,
    seq_scan,
    idx_scan,
    n_live_tup,
    n_dead_tup,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_catalog.pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 50;
```

Tuple counts are estimates. Compare trends and relation sizes rather than treating estimates as exact row counts.

### 11.2. VACUUM Progress

```sql
SELECT
    p.pid,
    p.relid::regclass AS relation,
    p.phase,
    p.heap_blks_total,
    p.heap_blks_scanned,
    p.heap_blks_vacuumed,
    a.query_start,
    clock_timestamp() - a.query_start AS runtime,
    a.wait_event_type,
    a.wait_event
FROM pg_catalog.pg_stat_progress_vacuum AS p
JOIN pg_catalog.pg_stat_activity AS a
  ON a.pid = p.pid
ORDER BY a.query_start;
```

### 11.3. Analyze Freshness

After data distribution shifts or bulk loads, planner statistics may not yet be refreshed by `ANALYZE`. Query plans can change because of stale stats rather than a new index or config. Record analyze timestamps and `last_autoanalyze`.

### 11.4. XID Age and Freeze Safety

Monitor database/table transaction age, autovacuum progress, and anti-wraparound warnings. Changes that pin old snapshots longer or increase write churn can elevate freeze pressure.

### 11.5. VACUUM Does Not Always Shrink Files

Standard `VACUUM` generally marks dead space for reuse inside PostgreSQL; relation files may stay the same size on the filesystem. When evaluating storage, inspect free space, relation growth, and bloat properly rather than concluding `VACUUM` failed simply because file sizes did not shrink.

## 12. WAL, Checkpoints, and Write Workload

### 12.1. `pg_stat_wal`

On PostgreSQL versions providing this view, collect:

```sql
SELECT *
FROM pg_catalog.pg_stat_wal;
```

Useful counters include WAL records, full-page images, bytes, and WAL buffers full. Record reset context when provided by the view.

### 12.2. WAL Bytes per Second

Compute `wal_bytes` delta divided by elapsed seconds. Compare per transaction or per request to detect whether a change increases write amplification.

### 12.3. Full-Page Images

Rising `wal_fpi` can relate to checkpoint cadence, page modification patterns, and full-page write behavior. Do not interpret it in isolation; correlate WAL volume, checkpoint activity, and workload.

### 12.4. Checkpoint Metrics

Checkpoint and background writer views evolve across major versions. Newer versions split `pg_stat_checkpointer` out of `pg_stat_bgwriter`. Check exact view and column definitions on your target server before building dashboards.

Track checkpoint counts, write/sync duration, buffers written, backend writes, and checkpoint warnings if present, comparing across matched windows and workloads.

### 12.5. WAL Volume as a Guardrail for Index/Schema Changes

Index creation, bulk updates, or altered application write patterns can drive up WAL generation. Monitor archive bandwidth, replication lag, backup storage, and disk headroom concurrently.

## 13. I/O and Storage Metrics

### 13.1. PostgreSQL Shared Buffer Metrics

`blks_read` and `blks_hit` in `pg_stat_database` reflect shared buffer accesses. They do not measure physical disk reads completely because the OS cache and storage layers can satisfy reads.

### 13.2. `pg_stat_io`

PostgreSQL 16 and later provide `pg_stat_io` breaking down I/O by backend type, object, and context:

```sql
SELECT
    backend_type,
    object,
    context,
    reads,
    writes,
    extends,
    op_bytes,
    hits,
    evictions,
    reuses,
    fsyncs,
    read_time,
    write_time,
    extend_time,
    fsync_time
FROM pg_catalog.pg_stat_io
ORDER BY backend_type, object, context;
```

Columns and timing behavior depend on version and configuration; some timing columns require `track_io_timing` to be enabled. Verify your actual server schema.

### 13.3. `track_io_timing`

```sql
SHOW track_io_timing;
```

Enabling timing can introduce platform-dependent overhead. If comparing I/O timings, keep the setting consistent between pre and post runs and document its state.

### 13.4. OS-Level Metrics

Combine database stats with OS or cloud storage monitoring:

- Device read/write latency.
- IOPS and throughput.
- Queue depth.
- CPU iowait.
- Disk utilization.
- Filesystem free space.
- Network throughput and packet retransmits.
- Memory pressure, swap activity, and OOM events.

### 13.5. Storage Latency Can Be Masked by Cache

A query enjoying high shared buffer hits can still suffer from WAL `fsync`, temp file I/O, or write-path storage latency. Track read and write latencies separately.

## 14. Replication and Standby Metrics

### 14.1. Primary: `pg_stat_replication`

```sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag,
    reply_time
FROM pg_catalog.pg_stat_replication
ORDER BY application_name;
```

### 14.2. Standby: Receive and Replay

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit_time;
```

### 14.3. WAL Receiver

```sql
SELECT *
FROM pg_catalog.pg_stat_wal_receiver;
```

An empty view typically means no active WAL receiver connection exists at snapshot time. Corroborate with logs and recovery state.

### 14.4. LSN Span Is Not Lag Time

`pg_wal_lsn_diff()` measures byte distance between two LSNs on the same WAL timeline. Do not convert bytes directly to seconds when WAL generation rates fluctuate.

### 14.5. Lag Metrics Can Appear Stale When Idle

Replication lag intervals do not always express catch-up time under all conditions. When no new WAL arrives, timestamps or lag columns may reflect the last processed message rather than a growing backlog. Always combine LSNs, WAL generation rate, and workload context.

### 14.6. Logical Subscriptions

When changes touch logical replication, include `pg_stat_subscription`, `pg_subscription_rel`, replication origins, and apply error counters per version. Physical replication metrics alone cannot describe logical apply progress.

## 15. Application and Infrastructure Metrics

### 15.1. The Database Does Not See the Entire User Experience

PostgreSQL may report low query execution time while the application remains slow due to connection pool waits, network latency, serialization, queueing, or external dependencies. Always capture end-to-end latency.

### 15.2. Metrics to Collect from Application/APM

- Request rate and transaction rate.
- p50/p95/p99 latency.
- Error/timeout rate.
- Retry count and retry success rate.
- Connection pool active/idle/waiting counts.
- Connection acquisition latency.
- Queue depth and worker utilization.
- Application-layer cache hit/miss ratios.
- External dependency latency.

### 15.3. Infrastructure Metrics

Record CPU utilization, load average, available memory, swap, disk latency, IOPS, throughput, network throughput, and packet drops. For cloud volumes, collect provider storage metrics.

### 15.4. Synchronize Clocks

Ensure PostgreSQL, application, monitoring, and host clocks are synchronized using UTC or explicit offsets. Clock skew can align events to the wrong measurement windows.

### 15.5. Correlation IDs

If tracing emits request/trace IDs, correlate slow requests with database query logs and query fingerprints where feasible. Never store sensitive data or raw SQL parameters inside unsecured baselines.

## 16. Query Plan Baselines with `EXPLAIN`

### 16.1. Capture Execution Plans of Key Queries

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT order_id, created_at, status
FROM public.orders
WHERE customer_id = 42001
ORDER BY created_at DESC
LIMIT 50;
```

`EXPLAIN ANALYZE` executes the query. Use safe read queries or test environments. For DML statements, execution causes side effects; never run DML `EXPLAIN ANALYZE` in production solely to capture plans without safe containment.

### 16.2. Compare Actual vs. Estimated Rows

Large mismatches between estimated and actual row counts can trigger poor join or sort strategies. Record plan nodes, actual time, loops, and buffers.

### 16.3. BUFFERS

`BUFFERS` reports shared/local/temp buffer activity within a plan. It illuminates PostgreSQL internal I/O without equaling raw physical device I/O.

### 16.4. SETTINGS

`SETTINGS` displays non-default planner-relevant settings affecting the plan on supported versions. Store PostgreSQL version and effective settings alongside plans.

### 16.5. WAL Option

Supported versions allow adding `WAL` to `EXPLAIN` options to report WAL generated by a statement. Verify version support before using it.

### 16.6. Do Not Compare Plans Under Differing Conditions

Plans can vary with statistics, parameter values, prepared statement generic/custom plan choices, cache warmth, and planner settings. Use representative inputs and record parameter distributions.

## 17. Capturing Snapshots and Computing Deltas

### 17.1. Store Two Labeled Snapshots

Example filenames or record keys:

```text
2026-11-14T09:00:00Z_pre_change_release_42
2026-11-14T10:00:00Z_post_change_release_42
```

Production identifiers should capture cluster, environment, change ID, and phase. Keep structured metadata so tooling can pair snapshots reliably.

### 17.2. Do Not Arbitrarily Reset Statistics for Baselines

Resetting stats destroys historical trend visibility for other consumers and breaks dashboards. Prefer capturing snapshots and computing deltas. Reset stats only in isolated test labs or under planned procedures, always logging the reset timestamp.

### 17.3. Computing Rates

```text
rate = (counter_after - counter_before) / seconds_between_snapshots
```

Calculate separately for WAL bytes, commits, rollbacks, blocks, query calls, and temp bytes.

### 17.4. Normalizing by Workload

```text
per_request_cost = delta_metric / completed_requests
per_transaction_cost = delta_metric / completed_transactions
error_rate = failed_requests / total_requests
```

Normalize only with an appropriate denominator. For instance, one transaction may span multiple requests; pick business units that accurately reflect real workload.

### 17.5. Comparing Matching Query Fingerprints

With `pg_stat_statements`, compute deltas per `queryid` and normalize by call count. A query whose total execution time doubles because `calls` doubled has not necessarily gotten slower.

### 17.6. Handling Missing or Reset Counters

If the post-snapshot counter is lower than the pre-snapshot counter:

1. Check `stats_reset` or server restart timestamps.
2. Check extension resets or entry deallocations.
3. Verify `queryid` and database identity.
4. Mark the window incomparable if a clean pre/post pair after reset is unavailable.
5. Never clamp negative deltas to zero to mask a reset.

## 18. Fair Pre/Post Comparisons

### 18.1. Match Workload

Compare similar request types and transaction mixes. If the post-change window has fewer heavy reporting queries, overall p95 may improve even though the target query stayed unchanged.

### 18.2. Match Duration

Never compare raw counters from a 10-minute window directly against a 2-hour window. Compare rates/deltas and percentiles over equivalent samples.

### 18.3. Match Time-of-Day

Traffic patterns and cache behavior shift by hour and weekday. Capture baselines over equivalent calendar windows or run fixed load tests.

### 18.4. Warm-Up

After restarts, index builds, cache invalidations, or deployments, systems often go through a warm-up phase. Separate warm-up from steady state. If cold-start behavior matters, measure it explicitly rather than discarding it silently.

### 18.5. Maintenance Overlap

Backups, `VACUUM`, `ANALYZE`, checkpoints, autovacuum, or index creation shift I/O profiles. Document overlaps and compare equivalent conditions; do not exclude events if they are regular parts of production workloads.

### 18.6. Use Control Groups When Appropriate

For canary-capable changes, comparing a canary instance against a concurrent control eliminates much seasonality bias. Ensure the control shares equivalent workload and hardware resources.

## 19. Interpreting Results: Improvements, Regressions, and Trade-Offs

### 19.1. Improvement

A change qualifies as an improvement when the primary outcome improves meaningfully, guardrails stay within limits, correctness holds, and results prove repeatable.

### 19.2. Regression

Regressions may appear as:

- Rising p95/p99 latencies.
- Rising error or timeout rates.
- Increased CPU or I/O saturation.
- Sharp increases in WAL bytes/request.
- Replication lag breaching SLA.
- Growing connection pool waits.
- Increased deadlocks or lock wait times.
- Disk growth exceeding capacity plans.

### 19.3. Trade-Offs

For example, synchronous replication raises commit latency while improving durability; adding an index accelerates `SELECT` queries while raising write cost; enabling `hot_standby_feedback` lowers query cancellations while increasing tuple retention. Always report both benefits and costs.

### 19.4. Never Conclude from One Metric Alone

A higher cache hit ratio does not prove faster queries. Higher TPS is bad news if error rates also climb. Lower CPU is no victory if throughput collapsed simultaneously. Evaluate metrics together.

### 19.5. Check Sample Size

A p99 computed from 100 requests is far less stable than one from millions of requests. Record sample counts and variability/confidence. If samples are sparse, extend the window or run load tests.

## 20. Comparison Example: Adding an Index for `orders` Queries

Suppose a change creates an index on `orders(customer_id, created_at DESC)` to optimize recent-order lookups.

### 20.1. Pre-Change

Capture:

- Query fingerprint and execution plan.
- Calls, total execution time, mean execution time.
- Shared buffer reads/hits.
- Application p95/p99 latency.
- Request volume and concurrency.
- CPU, disk reads, WAL rate.
- Table/index sizes.
- `INSERT`/`UPDATE` latencies.

### 20.2. Post-Change

Collect the identical metrics under equivalent workload. Never inspect only the target `SELECT` query while ignoring the write path.

### 20.3. Example Comparison Table

| Metric | Before | After | Interpretation |
| --- | ---: | ---: | --- |
| Query p95 | 180 ms | 55 ms | Target query improved |
| Query calls/min | 1,000 | 1,020 | Roughly equivalent workload |
| Mean execution | 90 ms | 28 ms | Decreased per query stats |
| INSERT p95 | 12 ms | 15 ms | Slight write overhead increase |
| WAL MB/min | 40 | 44 | Additional write amplification |
| Index size | 0 | 2.4 GB | Storage growth |
| Error rate | 0.1% | 0.1% | Unchanged in this example |

These numbers merely illustrate reporting structure, not universal targets. Base acceptance on SLAs, capacity, and business value.

### 20.4. Verify Correctness

Compare query outputs pre- and post-change for identical parameters. Indexes must never alter logical results. Verify constraints and application behavior.

## 21. Comparison Example: Changing Connection Pool Settings

### 21.1. Hypothesis

Increasing pool size may reduce connection acquisition waits, while increasing PostgreSQL backend count and memory pressure.

### 21.2. Baseline

Record pool active/idle/waiting counts, acquisition latency, PostgreSQL `numbackends`, active sessions, CPU, memory, and query latency.

### 21.3. Post-Change

Compare:

- Pool wait time.
- New connections opened/second.
- Backend count and active query count.
- CPU and context switching.
- Query p95/p99.
- Lock waits and database errors.
- Memory consumption.

### 21.4. Interpretation

If pool wait drops while PostgreSQL CPU surges and query latency worsens, the larger pool likely pushed database concurrency past its sweet spot. Never tune pools solely from application-side metrics.

## 22. Comparison Example: Tuning Autovacuum

### 22.1. Hypothesis

Lowering scale factor/thresholds may trigger vacuum earlier on high-churn tables.

### 22.2. Baseline

Record `n_dead_tup` estimates, relation size, `last_autovacuum`, vacuum runtime/progress, transaction rate, XID age, disk I/O, and query latency.

### 22.3. Post-Change

Observe long enough for tables to cycle through representative workloads. Compare dead tuple trends, vacuum frequency/runtime, I/O, and XID age.

### 22.4. Interpretation

Fewer dead tuples accompanied by higher peak-hour I/O and latency may represent an explicit trade-off. If dead tuples fail to drop, check `xmin` horizons, long transactions, and replication slots; adding vacuum workers cannot reclaim tuples still pinned by active snapshots.

## 23. Recommended Baseline Dashboard

A comparison dashboard should feature these panels:

| Panel | Metrics | Type |
| --- | --- | --- |
| Workload | requests/s, transactions/s, rows changed | Rate |
| Latency | p50/p95/p99, pool wait | Percentile/gauge |
| Errors | failed requests, SQLSTATE, rollbacks, timeouts | Rate/counter delta |
| Query cost | calls, total/mean execution, buffers, temp, WAL | Counter delta |
| Connections | active/idle/waiting, max utilization | Gauge |
| Locks | blocked sessions, wait duration, deadlocks | Gauge/rate |
| Vacuum | dead tuple estimates, autovacuum, XID age | Gauge/trend |
| WAL/checkpoint | `wal_bytes/s`, checkpoint duration, FPI | Rate/counter delta |
| I/O | read/write latency, IOPS, throughput, queue | Gauge/rate |
| Replication | send/write/flush/replay LSN, lag, sync state | Gauge/trend |
| Storage | `pg_wal` size, relation size, free disk | Gauge/trend |
| Configuration | settings diff, version, restart pending | Metadata |

### 23.1. Overlay Pre/Post on Shared Time Axes

Mark change deployment timestamps with annotations. Display pre/post periods side-by-side or overlaid using identical scales and units.

### 23.2. Display Workload Alongside Latency

Latency charts without request rates can mislead. Always place traffic volume and error rates beside latency panels.

### 23.3. Drill Down from Overview to Queries

Database dashboards should let responders drill straight into top query fingerprints, wait events, relation stats, and logs over matching time ranges.

### 23.4. Do Not Spawn Excessive Alerts from a Single Measurement

Baselines inform alert thresholds, yet alerts must still account for seasonality, noise, and business impact. Apply persistence durations and multi-signal conditions appropriately.

## 24. Pre-Change Baseline Workflow

### Step 1. Record Change ID and Objective

State exactly what change will be applied, why, and the target outcome to improve.

### Step 2. Select Primary Metrics and Guardrails

Pick metrics directly measuring the goal alongside metrics that might degrade.

### Step 3. Capture Configuration and Topology

Record version, `pg_settings`, role, replication topology, hardware/storage, and application release.

### Step 4. Choose Representative Windows

Select windows covering normal load and critical peak periods. Note overlapping batches or maintenance.

### Step 5. Capture Start/End Snapshots

Save counters, gauges, and query stats with timestamps while collecting OS and application metrics concurrently.

### Step 6. Validate Resets and Sample Quality

Verify `stats_reset`, server start time, extension resets, and request sample counts. Flag windows as invalid if counters reset mid-capture.

### Step 7. Store an Immutable Baseline

Store raw snapshots and metadata with retention and access controls. Never keep dashboard screenshots alone.

## 25. Post-Change Measurement Workflow

### Step 1. Record Change Completion Time

Log the exact moment settings or deployments take effect. If restarts occurred, record restart start and end times.

### Step 2. Separate Warm-Up from Steady State

Measure startup/cache warm-up separately if applicable. Compare steady state only against baseline steady state.

### Step 3. Verify Equivalent Workload

Check request mix, concurrency, and batch activity. If workload diverged, normalize carefully or run a controlled load test.

### Step 4. Collect Identical Metric Definitions

Use identical SQL queries, labels, units, and scrape intervals. Never alter metric formulas between pre and post runs.

### Step 5. Compute Deltas, Rates, and Normalized Costs

Calculate counter deltas, per-second rates, per-request/transaction costs, and percentiles from consistent sources.

### Step 6. Evaluate Guardrails

Check errors, latency, storage, WAL, replication, vacuum, locks, and correctness.

### Step 7. Decide

Accept, keep observing, or roll back according to predefined criteria. Record supporting evidence and rationale.

## 26. Rollback Criteria and Change Decisions

### 26.1. Define Before Deployment

Illustrative criteria:

- Roll back if application error rate exceeds the agreed threshold for 5 consecutive minutes.
- Roll back if p95 latency rises more than 25% under equivalent workload with no external cause.
- Halt rollout if replication lag breaches SLA or disk headroom falls below the safety margin.
- Halt if deadlocks, failed transactions, or data validation errors spike unexpectedly.

Derive real thresholds from your SLAs and baselines rather than adopting illustrative numbers universally.

### 26.2. Distinguish Warning vs. Stop Conditions

A warning flags metric drift from baseline without demanding immediate rollback. A stop condition is severe enough to halt rollout or roll back. Document who holds rollback authority.

### 26.3. Rollbacks Can Carry Cost

Dropping a new index may still require locks or maintenance; rolling back configs may force a restart; schema migrations may not be directly reversible. Assess the rollback path prior to making the change.

### 26.4. Do Not Wait Out the Measurement Window If a Guardrail Breaches

If data correctness, availability, or storage safety is threatened, intervene immediately per incident response procedures. Measurement windows never justify delaying protective action.

### 26.5. Capture Post-Rollback Evidence

Collect metrics verifying the system returned to stability. Document rollback duration and side effects.

## 27. Common Causes of Invalid Comparisons

| Issue | Why It Distorts Results | Mitigation |
| --- | --- | --- |
| Differing traffic | Counters/latency reflect different workloads | Match or normalize workload |
| Peak vs. off-peak | Cache warmth and concurrency differ | Compare matching time-of-day |
| Stats reset | Negative or artificially tiny deltas | Inspect reset timestamps |
| Server restart | Counter scope or cache warmth shifts | Separate restart and warm-up |
| Query fingerprint shift | Fails to pair identical queries | Store query text, version, user, db |
| Cold vs. warm cache | I/O and latency behavior differ | Measure cold and warm phases separately |
| Background jobs | Compete for CPU/I/O | Document or align batch schedules |
| Data volume growth | Planner, cache, and storage shift | Record table/index sizes and row counts |
| Unrelated config changes | Prevents clean attribution | Save `pg_settings` diffs |
| Network/storage events | External latency outside PostgreSQL | Correlate infrastructure telemetry |
| Small sample size | Unstable percentiles | Lengthen window or run load tests |
| Mean masking tail | Slow outlier queries hidden | Track p95/p99 histograms |
| Cumulative counters | Different window durations | Compute deltas and rates |
| Multiple simultaneous changes | Ambiguous attribution | Isolate changes or use controls |
| Dashboard aggregation flaws | Average-of-averages errors | Aggregate raw counts and histograms |

## 28. Baseline Storage and Governance

### 28.1. Version Your Baselines

Index baselines by change ID, release, cluster, and timestamp. Every record should specify data sources, metric query/versions, and capture windows.

### 28.2. Preserve Raw Data

Keep raw snapshots or exported time series so metrics can be recomputed if formulas evolve. Dashboard screenshots serve only as visual summaries.

### 28.3. Maintain a Metric Dictionary

Document for every metric:

- Name and definition.
- Unit.
- Type (counter/gauge/rate/percentile).
- Source view/system.
- Scrape interval.
- Reset semantics.
- Scope (`cluster`/`database`/`query`/`host`/`application`).
- Version availability.
- Owner.

### 28.4. Retention and Access Control

Baselines may contain query samples, schema names, and operational metadata. Enforce appropriate retention policies and access controls, while excluding secrets and sensitive literal parameters.

### 28.5. Never Overwrite Historical Baselines

When adopting a new baseline, create a new version linked to the corresponding change. This creates an audit trail showing how system behavior evolved across releases.

## 29. Practice Exercises with Answers

These exercises assume a PostgreSQL lab or staging instance. Never reset production statistics or modify production configuration solely for practice.

### Exercise 1. What is a baseline?

**Answer:** A collection of metrics and metadata representing system state prior to a change, gathered under conditions suitable for fair comparison.

### Exercise 2. Why record metadata alongside metrics?

**Answer:** To document the workload, version, configuration, topology, and timing under which those metrics were produced.

### Exercise 3. How does a counter differ from a gauge?

**Answer:** Counters accumulate over time since reset; gauges represent values at an instant in time.

### Exercise 4. Why shouldn't raw `xact_commit` be compared directly pre/post?

**Answer:** It is a cumulative counter; you must compute deltas and normalize by elapsed time or workload.

### Exercise 5. What is the counter rate formula?

**Answer:** `(counter_after - counter_before)` divided by elapsed seconds.

### Exercise 6. What does p95 latency tell you?

**Answer:** 95% of requests completed with latency at or below the p95 value during the measured window.

### Exercise 7. Can mean latency replace p95?

**Answer:** No. Mean latency can hide severe tail latency.

### Exercise 8. What metrics does `pg_stat_database` provide?

**Answer:** Per-database transactions, block accesses, tuple activity, temporary files, deadlocks, and related counters.

### Exercise 9. What is `stats_reset` used for?

**Answer:** It records when statistics were last reset, defining the valid baseline scope for counters.

### Exercise 10. Does `blks_read` guarantee physical disk reads?

**Answer:** No. The OS page cache can satisfy reads after a PostgreSQL shared buffer miss.

### Exercise 11. Is cache hit ratio sufficient to evaluate performance?

**Answer:** No. You also need query latency, I/O, workload context, and storage metrics.

### Exercise 12. What can rising `temp_bytes` indicate?

**Answer:** Sorts, hashes, or materializations spilling into temporary disk files.

### Exercise 13. What is `pg_stat_statements` used for?

**Answer:** Aggregating execution statistics grouped by normalized query fingerprint.

### Exercise 14. Does `pg_stat_statements` provide p95 latency?

**Answer:** No. Use APM, tracing, or application histograms for percentiles.

### Exercise 15. Why compute window mean from deltas?

**Answer:** `mean_exec_time` is cumulative since reset; dividing delta total time by delta calls yields the mean for the target window.

### Exercise 16. Can `queryid` change?

**Answer:** Yes, across PostgreSQL versions, query edits, and normalization behavior. Store query samples and metadata too.

### Exercise 17. Which view shows active queries and wait events?

**Answer:** `pg_stat_activity`.

### Exercise 18. Why does `idle in transaction` matter?

**Answer:** It can hold snapshots, locks, and vacuum horizons open even while running no active query.

### Exercise 19. Which view displays locks?

**Answer:** `pg_locks`.

### Exercise 20. What does `pg_blocking_pids()` do?

**Answer:** Identifies process IDs blocking a given backend.

### Exercise 21. Which view tracks vacuum progress?

**Answer:** `pg_stat_progress_vacuum`.

### Exercise 22. Is `n_dead_tup` an exact count?

**Answer:** No. It is a statistics estimate.

### Exercise 23. Why monitor XID age?

**Answer:** To ensure vacuum/freeze progress keeps pace and prevent transaction ID wraparound.

### Exercise 24. What does `pg_stat_wal` provide?

**Answer:** Tracking for WAL records, full-page images, bytes, and related WAL activity counters on supported versions.

### Exercise 25. What might rising WAL bytes/request indicate?

**Answer:** Higher write amplification or a shifted workload mix; verify against transaction mix.

### Exercise 26. Which PostgreSQL version introduced `pg_stat_io`?

**Answer:** PostgreSQL 16 and newer.

### Exercise 27. How does `pg_stat_io` categorize I/O?

**Answer:** By backend type, object, and context, along with associated operation counters.

### Exercise 28. What does `track_io_timing` do?

**Answer:** Enables timing collection for certain I/O operations; account for overhead and keep it consistent across comparisons.

### Exercise 29. Where is `pg_stat_replication` queried?

**Answer:** On the primary, to inspect connected WAL senders and standbys.

### Exercise 30. How do receive LSN and replay LSN differ?

**Answer:** Receive LSN tracks WAL received by the standby; replay LSN tracks WAL actually applied on the standby.

### Exercise 31. Is `replay_lag` always an exact catch-up time?

**Answer:** No. Under idle workloads or paused WAL flow, lag intervals can go stale; include LSNs and workload context.

### Exercise 32. Why record the PostgreSQL version?

**Answer:** System views, columns, and metric semantics evolve across major versions.

### Exercise 33. What does `pending_restart` mean?

**Answer:** A setting has been modified but awaits a server restart to take effect.

### Exercise 34. Why save `source` from `pg_settings`?

**Answer:** To see whether the effective value came from a config file, role/database override, command line, or elsewhere.

### Exercise 35. Why match time-of-day?

**Answer:** Workloads, cache state, and concurrency fluctuate across hours and days.

### Exercise 36. Why separate a warm-up window?

**Answer:** Caches and background initialization after restarts or deploys cause early metrics to differ from steady state.

### Exercise 37. One query speeds up while `INSERT` slows down — what is happening?

**Answer:** A trade-off, such as adding an index that lowers read cost while adding write overhead.

### Exercise 38. Why avoid changing multiple variables at once?

**Answer:** It becomes unclear which change caused the observed effect.

### Exercise 39. Why normalize per request?

**Answer:** To compare resource cost per unit of work when request volumes differ.

### Exercise 40. Why not average precomputed averages?

**Answer:** Windows have different sample sizes; aggregate raw counts/histograms or apply proper weights.

### Exercise 41. Does `EXPLAIN ANALYZE` execute the query?

**Answer:** Yes. Assess side effects carefully and only run safe statements in appropriate environments.

### Exercise 42. What does `BUFFERS` report?

**Answer:** Shared, local, and temp buffer activity in the plan, which does not directly equate to physical device reads.

### Exercise 43. Why pair application p95 with database query time?

**Answer:** Application latency includes pool waits, networking, serialization, and external calls.

### Exercise 44. Why document batch jobs?

**Answer:** Batch jobs compete for CPU/I/O and skew baselines if present in only one window.

### Exercise 45. How does a control group help?

**Answer:** Comparing a canary against a concurrent control isolates change effects from seasonality and traffic shifts.

### Exercise 46. When should post-change measurements become the new baseline?

**Answer:** Once the change is accepted and system behavior has stabilized across a representative window.

### Exercise 47. Why avoid resetting statistics casually?

**Answer:** Resetting erases historical trends and disrupts other dashboards/consumers; snapshotting and differencing is safer.

### Exercise 48. What should you do if the post-snapshot counter is smaller than pre-snapshot?

**Answer:** Check for stats resets, server restarts, extension resets, and identity changes; flag the window incomparable if needed.

### Exercise 49. When should rollback criteria be defined?

**Answer:** Before deployment, anchored to SLAs and baselines.

### Exercise 50. Error rate rises while p95 drops — is that a success?

**Answer:** No; latency often falls simply because requests fail fast. Always verify correctness and error rates.

### Exercise 51. Free disk shrinks after adding an index — what should you inspect?

**Answer:** Index size, WAL volume, tablespace capacity, backup/storage headroom, and write cost.

### Exercise 52. Why can't you draw conclusions from a single snapshot?

**Answer:** A snapshot misses trends, peaks, rates, and workload variability.

### Exercise 53. Should baselines archive raw data?

**Answer:** Yes. Raw snapshots or time series allow recomputation when metric formulas change.

### Exercise 54. What belongs in a metric dictionary?

**Answer:** Definition, unit, type, source, scope, scrape interval, reset semantics, and version availability.

### Exercise 55. Why synchronize clocks?

**Answer:** To align PostgreSQL, application, and infrastructure events accurately in time.

### Exercise 56. When should a fixed load test be used?

**Answer:** When production traffic is too noisy or when isolating the exact impact of a specific change.

### Exercise 57. Is p99 from 100 requests reliable?

**Answer:** No, it is noisy; collect a larger sample size and always report sample counts.

### Exercise 58. Why monitor replication and WAL during index changes?

**Answer:** Index builds and extra write overhead can raise WAL generation and replication lag.

### Exercise 59. Is a baseline a fixed alert threshold?

**Answer:** No. A baseline is reference data; alert thresholds also incorporate SLAs, seasonality, and persistence rules.

### Exercise 60. Build a PostgreSQL pre/post change comparison checklist

**Suggested Answer:**

1. Record change ID, objective, and hypothesis.
2. Select primary metrics, guardrails, and rollback thresholds.
3. Record version, topology, `pg_settings`, and application release.
4. Choose equivalent pre/post windows.
5. Capture raw snapshots and metadata.
6. Log workload volume, mix, concurrency, and batch jobs.
7. Verify `stats_reset`, restarts, and extension resets.
8. Compute deltas, rates, per-request costs, and percentiles.
9. Compare query plans, query fingerprints, locks, vacuum, WAL, replication, and OS metrics.
10. Decide accept/observe/roll back and archive evidence as the new baseline version.

## 30. Production Checklist

| Check | Requirement |
| --- | --- |
| Change ID | Linked to release or ticket |
| Hypothesis | States a measurable outcome |
| Primary metrics | Directly reflect the objective |
| Guardrails | Cover latency, errors, capacity, and correctness |
| PostgreSQL version | Recorded |
| Cluster identity | No confusion between primary/standby or environments |
| Topology | Replicas, DCS, routing, and storage documented |
| `pg_settings` | Runtime values and `pending_restart` captured |
| Application release | Recorded per snapshot |
| Workload | Rate, mix, concurrency, and batch jobs captured |
| Measurement window | Equivalent pre/post periods |
| Clock | UTC/offset and synchronized |
| Stats reset | Reset timestamps verified |
| Counter deltas | Computed from valid paired snapshots |
| Rates | Normalized by elapsed time |
| Per-request cost | Uses appropriate denominator |
| Percentiles | Includes sample count and histogram source |
| `pg_stat_database` | Transactions, blocks, temp, deadlocks |
| `pg_stat_statements` | Query fingerprints and deltas |
| `pg_stat_activity` | Sessions, waits, long transactions |
| `pg_locks` | Blocking and deadlocks |
| Vacuum | Dead tuples, progress, XID age |
| WAL/checkpoint | Bytes, FPI, and checkpoint activity |
| I/O | PostgreSQL and OS/storage metrics |
| Replication | LSNs, lag, sync state |
| Application | p50/p95/p99, errors, pool waits |
| Query plans | Representative `EXPLAIN` evidence |
| Dashboard | Pre/post annotations and matching units |
| Rollback | Thresholds, owner, and procedure defined |
| Evidence | Raw snapshots and logs archived |
| New baseline | Created only after change acceptance |
| Data protection | Excludes unnecessary secrets/sensitive data |

## 31. Summary

Baselines and pre/post comparisons form the measurement discipline that proves whether a PostgreSQL change achieved its intended outcome. Reliable conclusions require combining workload, database metrics, query behavior, infrastructure, configuration, and correctness.

Core principles:

1. **Baselines require context.** Record version, topology, workload, configuration, and capture windows.
2. **Distinguish counters, gauges, rates, and percentiles.** Each requires its own comparison method.
3. **Use deltas for cumulative counters.** Check resets and restarts before computing.
4. **Match pre/post workloads.** Align time-of-day, traffic mix, and concurrency, or normalize appropriately.
5. **Track both primary outcomes and guardrails.** Better latency fails if errors, WAL, or storage degrade.
6. **`pg_stat_database` gives the database view.** Pair with `pg_stat_statements` to isolate query fingerprints.
7. **Application metrics remain essential.** PostgreSQL cannot observe full pool waits or end-to-end latency.
8. **Cache hit ratio is not disk I/O ratio.** Interpret alongside OS and storage telemetry.
9. **Monitor locks, vacuum, WAL, and replication.** Read optimizations can still impact writes and HA.
10. **`EXPLAIN ANALYZE` executes queries.** Use only safe statements in suitable environments.
11. **Avoid arbitrary stats resets.** Capture snapshots and compute deltas to preserve history.
12. **One snapshot is not a baseline.** Cover representative windows with sufficient sample sizes.
13. **Set rollback criteria before deployment.** Never wait out a window once critical guardrails breach.
14. **Preserve raw evidence and a metric dictionary.** Enable future recomputation and auditing.
15. **Promote a new baseline only after acceptance.** Maintain history for full traceability.

Decision flow:

```text
Is the change objective measurable?
          |
          v
Do baselines share equivalent workloads?
          |
          v
Are stats and snapshots valid?
          |
          v
Did the primary outcome improve?
          |
          v
Do guardrails and correctness pass?
       /              \
     Yes               No
      |                  |
      v                  v
Accept/observe        Roll back or
      |               investigate further
      v
Save post-change as new baseline
```

**Final review question:** "If an index change halves query p95 latency while increasing WAL volume, write latency, and disk consumption, do we have sufficient baseline data to quantify the trade-off? Do pre- and post-change metrics share the same workload, metric definitions, and duration? If statistics reset between two snapshots, will we immediately recognize that the comparison is invalid?" A sound baseline workflow answers every one of these questions using raw metrics, metadata, and pre-agreed decision criteria.
