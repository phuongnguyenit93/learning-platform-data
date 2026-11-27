# Sudden Query Slowdowns Due to Plan, Data, or Statistics

A PostgreSQL query that ran reliably for weeks and suddenly becomes several times—or hundreds of times—slower rarely has a single cause. Data may have grown, data distribution may have shifted, statistics may no longer reflect reality, the planner may have chosen a different execution plan, parameter values may be skewed, an index may no longer fit, or the query may be waiting on locks or I/O rather than spending CPU executing.

Effective troubleshooting begins by determining **what changed and when**. Compare the query with the same parameters, environment, and workload state; read the execution plan with actual rows and buffer usage; inspect statistics, locks, waits, and resources across both the database and the operating system. Only after gathering evidence should you change queries, statistics, indexes, or planner settings.

This lesson presents a structured investigation workflow for sudden query slowdowns in PostgreSQL. It focuses on distinguishing three major root-cause categories: **execution plan changes**, **data/workload changes**, and **stale statistics or inaccurate cardinality estimates**. Related factors such as lock contention, caching, I/O, memory, prepared statements, autovacuum, and configuration are also examined because they frequently occur together.

~~~text
                  Sudden query slowdown
                            |
                            v
                 Determine incident scope
                            |
             +--------------+--------------+
             |              |              |
             v              v              v
        Plan changed   Data changed   Stats skewed
             |              |              |
             +--------------+--------------+
                            |
                            v
               EXPLAIN (ANALYZE, BUFFERS)
                            |
               +------------+------------+
               |            |            |
               v            v            v
            CPU/plan    I/O/cache    Lock/wait
               |            |            |
               +------------+------------+
                            |
                            v
              Choose evidence-based mitigation
                            |
                            v
             Re-measure and monitor for regression
~~~

This lesson belongs to the **Database Engine Relational PostgreSQL** module, **Troubleshooting** chapter, covering **“Sudden Query Slowdowns Due to Plan, Data, or Statistics”**.

---

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Distinguish a truly slow query from a query waiting on locks, I/O, or the network.
2. Identify the scope, onset time, and impact of an incident.
3. Use `pg_stat_statements` to find queries with increased latency.
4. Use `pg_stat_activity`, `pg_locks`, and `pg_blocking_pids` to investigate waits and blockers.
5. Collect `EXPLAIN` and `EXPLAIN ANALYZE` safely and accurately.
6. Read actual rows, estimated rows, loops, buffers, temp blocks, and rows removed.
7. Recognize sequential scans, index scans, bitmap scans, nested loops, hash joins, and sorts.
8. Distinguish plan regression from data growth or selectivity shifts.
9. Explain why stale statistics cause the planner to choose suboptimal plans.
10. Use `ANALYZE` and monitor autovacuum/autoanalyze.
11. Read `pg_stats` and understand MCVs, histograms, `n_distinct`, and correlation.
12. Use extended statistics for correlated columns.
13. Recognize parameter skew and generic/custom prepared plans.
14. Evaluate the impact of indexes, partition pruning, and table bloat.
15. Analyze lock waits, long transactions, and deadlocks.
16. Inspect cache, disk I/O, temporary files, memory, and CPU pressure.
17. Assess the impact of `work_mem`, parallelism, JIT, and cost settings.
18. Use `auto_explain` and logging to capture evidence in production.
19. Choose safe, reversible, and measurable mitigations.
20. Design baselines, regression monitoring, and incident runbooks.
21. Avoid risky actions such as `VACUUM FULL`, `REINDEX`, or restarts without evidence.
22. Build a post-mitigation verification and re-testing plan.

**Scope:** Modern PostgreSQL, including standard catalog views and statistics tools. Certain views, columns, and options depend on the major version; for example, `pg_stat_io` is only available on versions that support it. Always check documentation for your exact version and verify granted permissions in production environments.

---

## 2. First Question: Is the Query Slow or Waiting?

User-perceived latency does not necessarily equal the time PostgreSQL spends on CPU execution. A request may take 20 seconds waiting on a lock, disk, remote service, or connection pool while the plan itself takes only a few milliseconds.

### 2.1. Types of Latency

| Type | Common Symptoms | Where to Check |
| --- | --- | --- |
| CPU-bound | High CPU, active query, few waits | Plan, joins/aggregates, functions, parallelism |
| I/O-bound | High read latency, many physical reads | Buffers, storage metrics, cache, plan |
| Lock-bound | `wait_event_type = Lock` | `pg_blocking_pids`, `pg_locks`, transactions |
| Memory/temp-bound | Temp blocks/files, sort/hash spill | `work_mem`, cardinality, query shape |
| Network-bound | Waiting for client/remote response, large row counts | Application, FDW, network, result size |
| Connection-bound | Requests waiting for a connection from pool | Pool metrics, connection count |
| Planning-bound | High planning time, very complex query | Parse/rewrite/plan, statistics, remote estimates |
| Resource contention | Many unrelated queries slow together | CPU, I/O, memory, checkpoints, concurrency |

### 2.2. Do Not Start by Creating an Index

If a query is waiting on another transaction holding a row lock, adding an index usually will not solve the root cause. If the bottleneck is the connection pool, rewriting SQL may not help either.

### 2.3. Identify the Onset Time

Record:
- The last time the query ran normally.
- When latency began rising.
- The most recent deployment or application release.
- Any migration or index change.
- Data imports or batch jobs.
- `ANALYZE`/autovacuum/`VACUUM` activity.
- PostgreSQL configuration changes.
- Failovers, restarts, or storage/network incidents.
- Traffic and concurrency shifts.

### 2.4. Determine the Scope

Ask:
- One `queryid` or multiple queries?
- One table/schema or the entire database?
- One tenant/parameter value or all of them?
- Only one application instance or all clients?
- Only during peak hours or continuously?
- Slow from the start or only when the result set is large?

If multiple unrelated queries slow down together, investigate resources, locks, storage, and connection pools before tuning individual SQL statements.

### 2.5. Preserve Evidence Before Making Changes

Collect normalized query text, representative parameters, plans, statistics, waits, logs, and timestamps. Do not reset `pg_stat_statements`, restart the server, or clear caches before saving diagnostic data.

---

## 3. Structured Investigation Workflow

An incident should be handled through repeatable steps.

### Step 1: Confirm Symptoms

Measure current latency and compare it with the baseline. Identify `queryid`, endpoint, tenant, parameter class, and call frequency.

### Step 2: Check Whether the Query Is Waiting

Use `pg_stat_activity` and `pg_blocking_pids` to find locks and waits. If blocked, identify the blocker and its transaction age.

### Step 3: Capture the Execution Plan

Collect `EXPLAIN VERBOSE` and, when safe, `EXPLAIN ANALYZE` with `BUFFERS`. Compare estimated rows against actual rows.

### Step 4: Inspect Data and Statistics

Check row counts, modifications, `last_autoanalyze`, `pg_stats`, partition sizes, indexes, and data distribution.

### Step 5: Check Plan History and Parameters

Compare old and new plans, query parameters, prepared statements, generic vs. custom plans, and changes in query text.

### Step 6: Check Resources

Check CPU, I/O, memory, temp files, checkpoints, WAL, network, connection pools, and concurrency.

### Step 7: Choose One Mitigation

Make a small, reversible change. Examples include running `ANALYZE` on a table, adjusting a query, adding a planned index, or resolving a blocker per runbook.

### Step 8: Re-Measure

Test with the same parameter class and comparable workload. Compare latency, rows, buffers, temp usage, CPU, and impact on other queries.

### Step 9: Document the Root Cause

Distinguish direct cause, triggering condition, exacerbating factors, and preventive measures.

---

## 4. Finding Slow Queries with pg_stat_statements

`pg_stat_statements` collects execution statistics for normalized SQL statements. It is usually the best starting point for identifying which queries consume the most time or have increased latency.

### 4.1. Installing the Extension

On the server, `pg_stat_statements` typically needs to be added to `shared_preload_libraries`. This is a startup setting and normally requires restarting PostgreSQL after changing it.

Check:

~~~sql
SHOW shared_preload_libraries;
~~~

If `pg_stat_statements` is not present, configure it via `postgresql.conf`, a parameter group, or your managed service mechanism:

~~~conf
shared_preload_libraries = 'pg_stat_statements'
~~~

If other libraries are already listed, preserve the existing list and append `pg_stat_statements` using the proper syntax.

After restarting the server, inside the target database:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

### 4.2. Finding Queries with High Total Time

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    min_exec_time,
    max_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_read,
    temp_blks_written,
    left(query, 500) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Exact column names depend on the PostgreSQL and extension version. Adjust the query to match the schema of your running version.

### 4.3. Finding Queries with High Mean Latency

~~~sql
SELECT
    queryid,
    calls,
    mean_exec_time,
    max_exec_time,
    rows,
    left(query, 500) AS query_sample
FROM pg_stat_statements
WHERE calls > 10
ORDER BY mean_exec_time DESC
LIMIT 20;
~~~

A query executed very few times may have a high mean latency yet low overall impact. Combine call count, total time, and business impact.

### 4.4. Finding Queries with High Temp Block Usage

~~~sql
SELECT
    queryid,
    calls,
    temp_blks_read,
    temp_blks_written,
    mean_exec_time,
    left(query, 400) AS query_sample
FROM pg_stat_statements
ORDER BY temp_blks_written DESC
LIMIT 20;
~~~

Temp blocks may indicate sort or hash operations spilling to disk. By themselves, they do not prove `work_mem` is too low; the query may simply be processing an unusually large amount of data.

### 4.5. Reading shared_blks_hit and shared_blks_read

- `shared_blks_hit`: blocks found in PostgreSQL shared buffers.
- `shared_blks_read`: blocks PostgreSQL had to read into shared buffers from lower storage or cache layers.

`shared_blks_read` does not necessarily mean physical disk reads because the OS page cache can satisfy them. Correlate with OS I/O metrics and `track_io_timing` if enabled.

### 4.6. Queryid and Normalized Statements

Multiple executions with different literal values can be grouped under the same `queryid`. This is useful for aggregation but can hide parameter skew: the same query shape having vastly different selectivities across values.

### 4.7. Statistics Time Window

`pg_stat_statements` typically accumulates since the last reset or across the relevant server lifecycle. Without periodic snapshots, it is hard to know whether latency spiked in the last 10 minutes or has been elevated for days.

Take periodic snapshots in your monitoring system, compute deltas between snapshots, and record reset timestamps clearly.

### 4.8. Do Not Reset During an Investigation

Resetting statistics destroys the baseline you need. Only reset intentionally, with documentation, and after saving a snapshot.

### 4.9. Access Permissions

The view may require appropriate privileges or a monitoring role. Do not grant broad superuser rights solely to read query stats; use monitoring roles in line with policy.

---

## 5. Checking Running Queries with pg_stat_activity

`pg_stat_activity` shows what each backend is doing at the moment of observation.

### 5.1. Long-Running Active Queries

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS query_age,
    clock_timestamp() - xact_start AS transaction_age,
    left(query, 1000) AS query_sample
FROM pg_stat_activity
WHERE state = 'active'
  AND pid <> pg_backend_pid()
ORDER BY query_start;
~~~

### 5.2. Distinguishing State and Wait Event

- `active`: backend is executing a query, though it may currently be waiting.
- `idle`: backend is not executing a query.
- `idle in transaction`: a transaction is open, but the session is not executing a statement.
- `wait_event_type`/`wait_event`: describes the type of resource the backend is waiting on.

An active query with `wait_event_type = Lock` is likely blocked rather than running slowly due to its plan.

### 5.3. Finding Long Transactions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    clock_timestamp() - xact_start AS xact_age,
    wait_event_type,
    wait_event,
    left(query, 500) AS last_query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Long transactions can hold locks and old snapshots, preventing vacuum from removing dead tuples and increasing bloat.

### 5.4. Finding Idle-in-Transaction Sessions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    clock_timestamp() - xact_start AS xact_age,
    state_change,
    left(query, 500) AS last_query
FROM pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY xact_start;
~~~

Investigate application code, connection pools, and transaction boundaries. Do not terminate a session just because it is idle; determine its owner and impact first.

### 5.5. Do Not Confuse Query Age with CPU Time

`query_age` is elapsed wall-clock time since `query_start`. It includes wait time. To separate execution from waiting, inspect wait events, plans, and OS metrics.

---

## 6. Investigating Blocking and Lock Contention

Lock contention is a common cause of “a query suddenly got slow” after a deployment or batch job.

### 6.1. Finding Blockers

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.usename AS blocked_user,
    blocked.application_name AS blocked_app,
    clock_timestamp() - blocked.query_start AS blocked_query_age,
    blocker.pid AS blocker_pid,
    blocker.usename AS blocker_user,
    blocker.application_name AS blocker_app,
    clock_timestamp() - blocker.xact_start AS blocker_xact_age,
    left(blocked.query, 500) AS blocked_query,
    left(blocker.query, 500) AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS p(blocker_pid)
JOIN pg_stat_activity AS blocker
    ON blocker.pid = p.blocker_pid
ORDER BY blocker.xact_start NULLS LAST;
~~~

### 6.2. Inspecting Lock Details

~~~sql
SELECT
    a.pid,
    a.usename,
    a.state,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation,
    l.page,
    l.tuple,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 400) AS query_sample
FROM pg_locks AS l
JOIN pg_stat_activity AS a
    ON a.pid = l.pid
ORDER BY a.pid, l.granted, l.locktype;
~~~

Not every existing lock is a problem. Granted locks are normal; focus on ungranted waits and the blocker chain.

### 6.3. Lock Chains

One backend may block another while itself being blocked by a third transaction. Trace the full blocker chain before acting.

### 6.4. Slowdowns Caused by DDL

`ALTER TABLE`, `CREATE INDEX`, `DROP INDEX`, `VACUUM FULL`, and certain other DDL statements require strong locks. A DDL statement waiting for a lock can queue up a long line of queries behind it.

### 6.5. Long Transactions

Long-running transactions can hold row/table locks and snapshots. Check `xact_start`, `state`, and `application_name`.

### 6.6. Handling a Blocker

Before canceling or terminating:
1. Identify the session owner and application.
2. Check what the transaction is doing.
3. Assess what data might roll back or what side effects exist.
4. Notify stakeholders per incident procedure.
5. Prefer canceling the query when appropriate.
6. Terminate the backend only with explicit approval and understanding of transaction rollback.
7. Monitor the lock queue afterward.

### 6.7. Lock Timeout and Deadlocks

`lock_timeout` caps how long a statement waits for a lock; `deadlock_timeout` controls when PostgreSQL checks for deadlocks. `log_lock_waits` can log lock waits exceeding the configured threshold.

Do not increase timeouts just to mask lock contention if the system needs to fail fast.

---

## 7. Reading EXPLAIN and EXPLAIN ANALYZE

The execution plan shows what operations PostgreSQL intends to perform or actually performed.

### 7.1. EXPLAIN

~~~sql
EXPLAIN
SELECT *
FROM orders
WHERE customer_id = 42;
~~~

`EXPLAIN` only plans the query without executing the `SELECT`. It shows estimated rows, costs, and plan nodes.

### 7.2. EXPLAIN ANALYZE

~~~sql
EXPLAIN (ANALYZE)
SELECT *
FROM orders
WHERE customer_id = 42;
~~~

`ANALYZE` executes the query and collects actual row counts and timings. Running it in production requires understanding that the query consumes resources just like a real execution.

### 7.3. EXPLAIN with Buffers

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    order_id,
    total_amount
FROM orders
WHERE customer_id = 42;
~~~

`BUFFERS` shows shared, local, and temp buffer activity per plan node. This is essential for telling whether a query reads many pages or is mostly CPU-bound.

### 7.4. Adding WAL and SETTINGS

~~~sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS,
    VERBOSE,
    SUMMARY
)
SELECT
    order_id,
    total_amount
FROM orders
WHERE customer_id = 42;
~~~

Some options and fields depend on the PostgreSQL version. `WAL` is useful for write statements; `SETTINGS` displays planner-related settings that differ from defaults. Do not include options unsupported by your target version.

### 7.5. EXPLAIN ANALYZE Executes the Query

For `SELECT`, the query can still read large volumes of data and consume CPU, I/O, memory, and locks. For `INSERT`/`UPDATE`/`DELETE`, it performs real data modifications.

Even if you test DML inside a transaction and `ROLLBACK`, do not assume all side effects are undone: sequence increments and external side effects from functions or triggers may not roll back like table rows. Prefer staging or a data copy for risky tests.

### 7.6. Do Not Run Test Plans Against Arbitrary Production Queries

Choose a representative query, limit concurrency, set timeouts and cancellation safeguards, and have a stop plan. `EXPLAIN ANALYZE` is not a free observation command.

---

## 8. Reading Estimated Rows and Actual Rows

Discrepancies in cardinality estimates are a key indicator of statistics or data-distribution issues.

### 8.1. Estimated Rows

`rows` in a plan without `ANALYZE` is the number of rows the planner predicts a node will return.

### 8.2. Actual Rows

`EXPLAIN ANALYZE` shows the actual rows returned by a node. When `loops` > 1, `actual rows` and `actual time` are typically averages per loop in the output; total work for the node must be considered alongside `loops`.

### 8.3. Example of a Misestimate

~~~text
Index Scan using orders_customer_idx on orders
  (cost=0.42..12.50 rows=5 width=48)
  (actual time=0.040..85.000 rows=85000 loops=1)
~~~

The planner estimated 5 rows, but the node actually returned 85,000 rows. That is a massive discrepancy. A Nested Loop above it can become extremely expensive if the planner relied on the tiny estimate.

### 8.4. Measuring Discrepancy

You can use the `actual/estimated` ratio as a heuristic to locate nodes with large errors. There is no single threshold that fits every query; a 10x error on a small node may matter far less than a 2x error on a node processing millions of rows.

### 8.5. Inspect Bottom-Up

Start at the leaf scans:
- Seq Scan.
- Index Scan.
- Bitmap Heap Scan.
- Foreign Scan.
- Function Scan.

If row estimates at the leaves are wrong, join order and aggregate estimates above them can be wrong as well.

### 8.6. Rows Removed by Filter

A high value means the node read many rows only to discard most of them after filtering. This can indicate a predicate is not effectively supported by an index or a filter is applied after a join.

### 8.7. Rows Removed by Join Filter

This can indicate a join generated many candidate pairs and then discarded most of them. Check the join condition, cardinality estimates, and indexes.

### 8.8. Loops

An Index Scan returning 100 rows with `loops=1000` can perform roughly 100,000 row visits in total. Never read `actual rows` while ignoring `loops`.

### 8.9. Timing

`actual time` on a node is cumulative along that node's execution subtree—do not simply sum times across all plan lines because parent nodes include child execution times. Never add plan node timings together to compute query duration.

---

## 9. Reading Buffers, I/O, and Temporary Files

### 9.1. shared hit

Block was already in PostgreSQL shared buffers. High hit counts can still consume significant CPU processing many tuples.

### 9.2. shared read

PostgreSQL had to load the block into shared buffers. The OS page cache may satisfy this, so it does not automatically mean a physical disk read occurred.

### 9.3. dirtied and written

`dirtied` blocks were modified in shared buffers; `written` blocks were written out to storage during the execution path as accounted for by `EXPLAIN`. Analyze these alongside WAL and checkpoint metrics.

### 9.4. temp read/write

Sort and hash operations can spill to temporary files when data exceeds the memory budget. Heavy temp usage typically slows queries noticeably.

### 9.5. I/O Timing

`track_io_timing` adds read/write timing to statistics and `EXPLAIN` on supported versions. Enabling it carries overhead depending on platform; benchmark first and follow operational policy.

### 9.6. Cache Effects

A first run may be slow because pages are not yet in cache. A faster second run does not necessarily mean the plan improved.

Compare queries under equivalent cache states or use long-term workload monitoring. Do not attempt to clear OS caches or shared buffers on production just to force a “cold run”.

### 9.7. pg_stat_io

On PostgreSQL versions that include `pg_stat_io`, this view provides server-wide I/O statistics by backend, object, and context. Use it to complement server-wide visibility, not to replace `EXPLAIN BUFFERS`.

### 9.8. Distinguishing Storage Bottlenecks from Overly Broad Scans

A query reading 10 GB because its plan scans too many rows differs from a query reading 10 GB under abnormal storage latency. Look at both block counts and I/O timing.

---

## 10. How PostgreSQL Statistics Work

The planner uses statistics to estimate selectivity, row counts, distinct values, and data distribution. From those estimates, it chooses scan types, join orders, join algorithms, aggregations, and parallelism.

### 10.1. ANALYZE

`ANALYZE` samples rows and updates column statistics. PostgreSQL runs `ANALYZE` either manually or via autovacuum/autoanalyze.

### 10.2. Statistics Are Not Exact Per-Row Data

Statistics are an approximation built from samples. They do not store every value in a table and may poorly represent extreme skew or correlations across multiple columns.

### 10.3. pg_stats

~~~sql
SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds,
    correlation
FROM pg_stats
WHERE schemaname = 'public'
  AND tablename = 'orders';
~~~

This view presents column statistics in a more readable form. Access depends on privileges.

### 10.4. null_frac

Estimated fraction of `NULL` values. If the `NULL` fraction shifts sharply, `IS NULL`/`IS NOT NULL` predicates can change selectivity.

### 10.5. n_distinct

Estimated number of distinct values. Negative values represent a fraction of total rows rather than an absolute count. Read according to catalog semantics rather than treating every value as a positive integer cardinality.

### 10.6. most_common_vals and most_common_freqs

Most Common Values (MCVs) and their frequencies help the planner estimate popular values. If a single tenant or status makes up a very large share, MCVs strongly influence plan selection.

### 10.7. histogram_bounds

The histogram describes the distribution of values not included in the MCV list. The planner uses it to estimate range predicates.

### 10.8. correlation

Correlation measures how closely physical row order matches column value order. It affects cost estimates for index scans that might read heap pages with poor locality.

### 10.9. Statistics Target

The statistics target controls sample size and MCV/histogram detail for a column. Raising the target can help complex distributions but makes `ANALYZE` heavier and increases catalog size.

~~~sql
ALTER TABLE orders
ALTER COLUMN status SET STATISTICS 500;

ANALYZE orders (status);
~~~

`500` is only an example. Increase it only for columns with evidence of misestimation.

---

## 11. Stale Statistics and Autoanalyze

A table can grow rapidly or shift distribution after bulk loads or updates. Outdated statistics cause the planner to misestimate.

### 11.1. Checking Analyze Timestamps

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze,
    last_vacuum,
    last_autovacuum
FROM pg_stat_user_tables
WHERE relname = 'orders';
~~~

### 11.2. n_mod_since_analyze

This estimates the number of rows modified since the last `ANALYZE` on versions providing this column. A large value relative to table size indicates statistics may need updating.

### 11.3. Autoanalyze Thresholds

Autovacuum triggers autoanalyze based on a threshold, a scale factor, and other conditions. On large tables, the default scale factor can allow a huge number of rows to change before autoanalyze runs.

### 11.4. Partitioned Tables

Statistics for a partitioned parent and its partitions have version-specific nuances. Review your `ANALYZE` strategy on both the parent and individual partitions. Do not assume autoanalyzing one partition automatically resolves all parent-level estimates.

### 11.5. Bulk Loads

After a large bulk load or data migration, run `ANALYZE` appropriately so the planner sees the new distribution. Do not wait for autovacuum if the workload needs accurate plans immediately.

### 11.6. Manual ANALYZE

~~~sql
ANALYZE orders;
~~~

You can analyze specific tables or columns:

~~~sql
ANALYZE orders (customer_id, status, created_at);
~~~

`ANALYZE` is far lighter than `VACUUM FULL`, though it still reads sample pages and consumes I/O and CPU. Time it appropriately for your workload.

### 11.7. ANALYZE Does Not Clean Dead Tuples

`ANALYZE` updates statistics; `VACUUM` handles dead tuples, visibility, and related maintenance tasks. The two operations serve different purposes.

### 11.8. When Autoanalyze Fails to Run

Investigate:
- Whether autovacuum is disabled globally or at the table level.
- Worker capacity.
- Long transactions or old snapshots.
- I/O saturation.
- Table-level settings.
- Autovacuum logs.
- Table churn rate.

Do not simply increase worker count without checking CPU and I/O capacity.

---

## 12. Extended Statistics for Correlated Columns

Single-column statistics may fall short when a query filters on multiple interdependent columns.

### 12.1. Example of Correlated Columns

Suppose `orders` has `region` and `postal_code`. Each postal code belongs to only one region. If the planner assumes the two predicates are independent, it multiplies their selectivities and underestimates rows badly.

### 12.2. Dependencies

Functional dependency statistics capture dependency relationships between columns.

~~~sql
CREATE STATISTICS orders_region_postal_dep (dependencies)
ON region, postal_code
FROM orders;

ANALYZE orders;
~~~

### 12.3. MCV Statistics

~~~sql
CREATE STATISTICS orders_region_status_mcv (mcv)
ON region, status
FROM orders;

ANALYZE orders;
~~~

MCV extended statistics record common value combinations across multiple columns.

### 12.4. N-Distinct Statistics

~~~sql
CREATE STATISTICS orders_region_status_nd (ndistinct)
ON region, status
FROM orders;

ANALYZE orders;
~~~

N-distinct helps estimate group counts when running `GROUP BY` on multiple columns.

### 12.5. Combining Kinds

~~~sql
CREATE STATISTICS orders_region_status_stats
    (dependencies, mcv, ndistinct)
ON region, status
FROM orders;

ANALYZE orders;
~~~

Not every type of extended statistics applies to every SQL clause. Check the documentation and plans for your running PostgreSQL version.

### 12.6. Extended Statistics Do Not Fix Every Correlation

They do not replace schema design, indexes, or data modeling. Create statistics for column combinations where there is evidence of planner misestimation.

### 12.7. Statistics Target

Extended statistics also have a target/size and collection overhead. Raise the target when MCV combinations need larger samples, then re-measure.

---

## 13. Data Growth and Distribution Shifts

A query can slow down even when the plan has not changed because data volume or selectivity shifted.

### 13.1. Table Growth

A table grows from 100 thousand to 100 million rows. A sequential scan that used to be cheap becomes expensive; an index may also become insufficiently selective if a query matches most rows.

### 13.2. Data Skew

A status that once accounted for 1% of rows now represents 70%. The same predicate now has different selectivity and may need a different plan.

### 13.3. Tenant Skew

A multi-tenant table can contain one massive tenant and thousands of tiny ones. A query shape that works well for small tenants may perform poorly for the large tenant.

### 13.4. Hot Values

MCV distribution shifts as business states evolve—for example, many orders transitioning to `archived` or `pending`.

### 13.5. Partition Growth

A newly created partition might lack the statistics, indexes, or constraints of older partitions. Check partition pruning and metadata.

### 13.6. Data Age

Queries targeting recent data can slow down if the recent range grows to dominate the table or if index correlation degrades.

### 13.7. Deleted Rows and Dead Tuples

`UPDATE`/`DELETE` operations generate dead tuples. If vacuum falls behind, scans read more pages and bloat grows.

### 13.8. Table Bloat vs. Table Growth

Large relation size can stem from genuine data growth or dead space/bloat. Compare live/dead tuples, relation size, vacuum history, and workload churn. Never conclude bloat solely from `pg_relation_size`.

### 13.9. Checking Relation Size

~~~sql
SELECT
    relid::regclass AS relation,
    pg_size_pretty(pg_relation_size(relid)) AS heap_size,
    pg_size_pretty(pg_indexes_size(relid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_catalog.pg_statio_user_tables
WHERE relid = 'public.orders'::regclass;
~~~

### 13.10. Checking Table Activity

~~~sql
SELECT
    relname,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch,
    n_live_tup,
    n_dead_tup
FROM pg_stat_user_tables
WHERE relname = 'orders';
~~~

Counters accumulate since stats reset; use deltas over time rather than relying on a single snapshot.

---

## 14. Execution Plan Changes

The same SQL text can produce a different execution plan after changes in data, statistics, PostgreSQL version, configuration, or parameter context.

### 14.1. Sequential Scan to Index Scan or Vice Versa

A sequential scan is not always bad. If a query needs most of the rows, a sequential scan can be cheaper than an index scan plus random heap fetches.

An index scan can become slow when:
- The predicate returns many rows.
- Heap accesses are scattered.
- Cache is cold.
- The index/table is large.
- Correlation is low.
- The visibility map does not support index-only scans.

### 14.2. Nested Loop

A Nested Loop works well when the outer side is small and the inner side has a suitable index. If outer row estimates are too low, the inner scan may execute millions of times.

### 14.3. Hash Join

A Hash Join suits many joins that do not require ordering. If the hash table exceeds the memory budget, it splits into batches and spills to disk.

### 14.4. Merge Join

A Merge Join requires suitably ordered inputs, which may require a Sort. If sorting spills or input cardinalities are misestimated, the query can slow down.

### 14.5. Sort

A Sort can switch from in-memory to external merge when it exceeds `work_mem`. `EXPLAIN ANALYZE` shows `Sort Method` and `Disk` usage.

### 14.6. Aggregate

`HashAggregate` can spill/batch when groups or the hash table are large. `GroupAggregate` may require sorted input. Compare estimated groups against actual groups.

### 14.7. Parallel Plans

The planner enables or disables parallel scans/joins/aggregates based on costs, table size, and settings. Actual worker availability at runtime also affects execution.

### 14.8. JIT

JIT compilation has startup overhead. For short queries, compile cost can outweigh the benefit. For long CPU-intensive queries, JIT can help. Compare JIT timing in the plan and check settings.

### 14.9. A Plan Change Does Not Prove Root Cause by Itself

A plan change can be a reasonable response to new data. If latency rises, inspect both the new plan and workload metrics to determine whether the plan caused the slowdown or merely coincided with it.

---

## 15. Prepared Statements and Parameter-Sensitive Plans

A subtle cause of slowdowns is identical query text paired with drastically different parameter value distributions.

### 15.1. Skew Example

~~~sql
SELECT *
FROM orders
WHERE customer_id = $1;
~~~

Customer 10 has 3 rows; customer 99 has 2 million rows. A single plan may not suit both.

### 15.2. Custom Plan

A custom plan is built for specific parameter values, allowing the planner to pick an index scan for a small tenant and a sequential scan for a large tenant.

### 15.3. Generic Plan

A generic plan is generated without optimizing for a specific parameter value. It reduces planning overhead but performs poorly under parameter skew.

### 15.4. PostgreSQL Plan Cache

Prepared statements switch between custom and generic plans according to PostgreSQL's heuristics. Actual behavior depends on the driver, server-side prepare settings, and execution count.

### 15.5. Inspecting Prepared Statements

~~~sql
SELECT
    name,
    statement,
    prepare_time,
    parameter_types,
    from_sql,
    generic_plans,
    custom_plans
FROM pg_prepared_statements;
~~~

Columns such as `generic_plans` and `custom_plans` depend on PostgreSQL version. This view only displays prepared statements in the current session.

### 15.6. EXPLAIN EXECUTE

Create a prepared statement in a session and examine plans across different parameter values:

~~~sql
PREPARE order_lookup(bigint) AS
SELECT *
FROM orders
WHERE customer_id = $1;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE order_lookup(10);

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE order_lookup(99);

DEALLOCATE order_lookup;
~~~

Use `ANALYZE` only when the query is safe and workload is controlled.

### 15.7. plan_cache_mode

You can test in a session or transaction:

~~~sql
SET plan_cache_mode = force_custom_plan;
~~~

Or:

~~~sql
SET plan_cache_mode = force_generic_plan;
~~~

This is an intentional diagnostic/tuning knob. Do not set it globally right away because it may help one query while hurting others or increasing planning CPU.

### 15.8. Driver Prepare Thresholds

JDBC drivers may have settings controlling server-side prepared statements and prepare thresholds. Check driver version and configuration before assuming PostgreSQL chose a generic plan on its own.

### 15.9. Evidence-Based Solutions

- Tune indexes and statistics for skew.
- Split query paths by parameter class if business logic allows.
- Adjust prepared statement behavior with narrow scope.
- Use partitioning or an appropriate data model.
- Never assume `force_custom_plan` is a universal fix.

---

## 16. Indexes: Present Yet Still Slow

A slow query does not mean an index is missing. An existing index may be unsuitable, insufficiently selective, or intentionally skipped by the planner in favor of a sequential scan.

### 16.1. Inspecting Index Definitions

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'orders'
ORDER BY indexname;
~~~

### 16.2. Index Scans Are Not Always Fast

If a query needs 60% of a table's rows, an index scan can trigger massive random heap fetches. A sequential scan is usually cheaper.

### 16.3. Multicolumn Indexes

In B-tree indexes, column order matters. Equality conditions on leading columns are typically critical; range conditions and sort orders should be designed around the actual query workload.

~~~sql
CREATE INDEX orders_customer_created_idx
ON orders (customer_id, created_at DESC);
~~~

This is only an example for queries filtering by `customer_id` and ranging/ordering by `created_at`. Do not apply this column order blindly to every query.

### 16.4. Partial Indexes

~~~sql
CREATE INDEX orders_open_customer_idx
ON orders (customer_id, created_at)
WHERE status = 'open';
~~~

The query predicate must prove the partial index condition holds. A generic prepared plan or parameterized predicate may fail to prove that implication at planning time.

### 16.5. Covering Indexes and INCLUDE

~~~sql
CREATE INDEX orders_customer_created_cover_idx
ON orders (customer_id, created_at)
INCLUDE (status, total_amount);
~~~

`INCLUDE` can enable index-only scans when required columns reside in the index, though index-only scans also depend on the visibility map. `INCLUDE` enlarges the index and increases write overhead.

### 16.6. Index-Only Scans and Heap Fetches

If a plan uses `Index Only Scan` yet reports high `Heap Fetches`, the visibility map may not have enough pages marked all-visible. Appropriate vacuuming helps update the visibility map, though it may not eliminate fetches on continuously updated tables.

### 16.7. Bitmap Scans

`Bitmap Index Scan` combines multiple index conditions or batches heap page visits. `Bitmap Heap Scan` is often effective at moderate selectivity.

### 16.8. BRIN

BRIN suits large tables where physical row order correlates with timestamp or sequence values. If data order degrades or ranges are too broad, effectiveness drops.

### 16.9. GIN/GiST

JSONB, full-text, arrays, ranges, and spatial predicates often require specialized index methods. B-tree cannot replace every access method.

### 16.10. Index Bloat and Write Amplification

Too many indexes slow down `INSERT`/`UPDATE`/`DELETE`, consume storage, and add vacuum work. Add indexes only when workload and plans prove the benefit.

### 16.11. CREATE INDEX CONCURRENTLY

In production, `CREATE INDEX CONCURRENTLY` avoids blocking writes compared to a standard index build, though it has limitations and can leave an invalid index behind if it fails. Plan for locks, disk space, I/O, and migration behavior.

### 16.12. Do Not Force the Planner with enable_seqscan=off

Disabling scan methods to force index usage is not a valid production solution. It can be used in a lab session to inspect alternative plans, but never distort the cost model without finding the root cause.

---

## 17. Partitioning and Partition Pruning

### 17.1. Queries Failing to Prune Partitions

If predicates cannot determine partition bounds, PostgreSQL may scan many or all partitions.

### 17.2. Suitable Predicates

For range partitioning on `created_at`, use explicit typed range predicates:

~~~sql
SELECT count(*)
FROM orders
WHERE created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00';
~~~

### 17.3. Casts on the Partition Key

Wrapping the partition key in a function or cast can block pruning in some cases. Inspect the plan and keep predicates sargable whenever possible.

### 17.4. Runtime Pruning

Prepared statements or parameters can enable runtime partition pruning. Check the plan for `Subplans Removed`, `loops`, and actual execution details to confirm.

### 17.5. New Partitions

Verify that new partitions have the matching indexes, constraints, statistics, and permissions. A large new partition missing an index can suddenly make current-month queries slow.

### 17.6. Partition Count

Too many partitions increase planning overhead and catalog work. Partitioning does not automatically speed up every query.

---

## 18. Vacuum, Dead Tuples, and the Visibility Map

### 18.1. VACUUM

`VACUUM` marks dead tuple space for reuse, updates the visibility map, and helps freeze transaction IDs. It does not necessarily return disk space to the OS.

### 18.2. ANALYZE

`ANALYZE` updates planner statistics. `VACUUM` and `ANALYZE` can run together as `VACUUM ANALYZE`, but they address different goals.

### 18.3. Checking Vacuum History

~~~sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

### 18.4. High Dead Tuples

Causes include high update/delete churn, autovacuum falling behind, long-running snapshots, or blocked vacuum runs.

### 18.5. Per-Table Autovacuum Settings

High-churn tables may need custom scale factors or thresholds. Tune based on table size, write rate, and vacuum capacity.

### 18.6. Long Snapshots

Long transactions or replication slots can hold back `xmin` and prevent vacuum from removing old tuples. Check transaction age and replication slot retention.

### 18.7. VACUUM FULL Is Not the First Reflex

`VACUUM FULL` rewrites the entire table and acquires an exclusive lock, causing downtime and blocking. Never run it solely because a query is slow or a table is large.

### 18.8. REINDEX Is Not a Default Fix

Index bloat can exist, but it must be measured first. `REINDEX` has I/O, disk, and lock implications; use `REINDEX CONCURRENTLY` where supported by version/operation and backed by a runbook.

---

## 19. Workload and Resource Pressure

An unchanged plan can still slow down if the server is under competing workload pressure.

### 19.1. CPU Saturation

Check CPU utilization, run queue length, parallel workers, background jobs, and query concurrency. CPU-bound queries suffer higher latency when many queries contend for CPU.

### 19.2. Storage Latency

Check read/write latency, throughput, queue depth, cloud volume throttling, and disk capacity. High shared buffer hits do not rule out CPU bottlenecks.

### 19.3. Memory Pressure

`work_mem` is a per-sort/hash operation budget, not a single server-wide pool. One query with multiple operations across many concurrent sessions can consume substantial memory.

### 19.4. Hash/Sort Spill

`EXPLAIN` may reveal:
- `Sort Method: external merge`.
- `Disk` usage.
- `Hash` batches > 1.
- `temp` blocks read/written.

### 19.5. Checkpoints and WAL

Checkpoint pressure, heavy WAL generation, or storage write saturation can degrade overall workload performance. Correlate checkpoint statistics/logs, WAL rate, and write latency.

### 19.6. Autovacuum Contention

Autovacuum consumes I/O and CPU. It is vital for database health, yet heavy workloads can compete with it for resources. Do not disable autovacuum to speed up queries without an alternative maintenance plan.

### 19.7. Connection Count

Too many active backends increase context switching and memory usage. Review pool sizing, connection leaks, and workload concurrency.

### 19.8. Network

If a query returns many rows over the network, transfer and serialization time can dominate latency. Inspect row count, row width, client consumption speed, and network RTT.

### 19.9. Replicas

If a query runs against a read replica, check replay lag, recovery conflicts, recovery waits, and replica resource contention. A slow query on a replica may have a different root cause than on the primary.

---

## 20. Planner Cost Settings and Configuration

Planner cost constants form a relative model, not real wall-clock timings. Misconfiguring them can degrade plans across many queries.

### 20.1. Viewing Settings

~~~sql
SHOW random_page_cost;
SHOW seq_page_cost;
SHOW effective_cache_size;
SHOW work_mem;
SHOW maintenance_work_mem;
SHOW max_parallel_workers_per_gather;
SHOW jit;
SHOW plan_cache_mode;
~~~

Not every setting is relevant to an incident. Record current values and any recent changes.

### 20.2. random_page_cost

Estimates the cost of a random page fetch relative to a sequential page fetch. Adjust to reflect storage/cache characteristics, but never lower it merely to force index scans.

### 20.3. effective_cache_size

Provides an estimate of total cache available to a query; it does not allocate memory. Setting it too low or too high can skew planner cost choices.

### 20.4. work_mem

Raising `work_mem` can reduce sort/hash spills, but memory scales per operation and concurrent query. Test at session/query scope first and measure peak memory usage.

### 20.5. Parallelism

`max_parallel_workers_per_gather` and related settings govern parallel plans. Parallel execution adds overhead; small queries can slow down if parallelism is unwarranted.

### 20.6. JIT

Inspect JIT compilation time versus execution time. Disabling JIT in a test session helps isolate overhead, though it is not a universal fix.

### 20.7. SET LOCAL for Testing

~~~sql
BEGIN;
SET LOCAL work_mem = '64MB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT ...
FROM orders
WHERE ...;

ROLLBACK;
~~~

Use illustrative values suitable for your environment. `SET LOCAL` applies only to the current transaction.

### 20.8. SETTINGS in EXPLAIN

`EXPLAIN SETTINGS` (when supported by your version) displays planner-related parameters that differ from defaults, aiding environment comparisons.

### 20.9. Do Not Change Global Settings Mid-Incident Without Measuring

Global settings alter behavior across every session and query. Prefer session-scoped testing, canary changes, or controlled rollouts.

---

## 21. Query Text and Application Changes

A query's performance can degrade after an application release even when its `queryid` looks similar.

### 21.1. SQL Text Changed

Check for:
- Added or removed predicates.
- Changed join order or join conditions.
- `SELECT *` replacing explicit column lists.
- Type casts.
- Functions applied to columns.
- CTE materialization changes.
- `ORDER BY`/`DISTINCT` changes.
- Pagination strategy shifts.
- Parameter type changes.

### 21.2. Bind Parameter Types

JDBC may bind a value with a different type than before, forcing PostgreSQL to apply a cast or pick a different operator. Check `PreparedStatement` setters and inferred parameter types.

### 21.3. CTE Behavior

CTEs can be inlined or materialized depending on query shape, version, and explicit `MATERIALIZED`/`NOT MATERIALIZED`. Materialization can block predicate pushdown across query levels.

### 21.4. Function Changes

Changes to a function's body, volatility, cost, or SQL definition can affect estimates and plans. Review `CREATE OR REPLACE FUNCTION` deployments.

### 21.5. search_path and Object Resolution

Changing `search_path` can cause SQL to resolve to a different function, operator, or table. In security-sensitive code, schema-qualify objects where appropriate.

### 21.6. ORM Changes

Upgrading Hibernate, Spring Data, or jOOQ can generate different SQL:
- JOIN strategy.
- N+1 query behavior.
- Pagination count queries.
- Parameter binding.
- Fetch size.
- Batching behavior.

Capture the actual SQL emitted by the application and compare it with pre-release queries.

### 21.7. N+1 Is Not a Plan Regression

If an endpoint jumps from 2 queries to 500 queries, each individual query may be fast while total request latency becomes slow. Use application tracing and `pg_stat_statements` call counts to spot this.

---

## 22. Logging and auto_explain

When an issue is hard to reproduce on demand, logging provides evidence captured at actual runtime.

### 22.1. log_min_duration_statement

Logs statements exceeding a duration threshold. Choose the threshold according to workload and log volume.

~~~conf
log_min_duration_statement = 1000
~~~

`1000` milliseconds is an example only.

### 22.2. log_lock_waits

Enable to log waits exceeding `deadlock_timeout`. Useful when lock contention is suspected.

### 22.3. log_temp_files

Logs temporary files larger than the threshold. Useful for diagnosing sort/hash spills.

### 22.4. auto_explain

`auto_explain` logs execution plans for queries exceeding a duration threshold. It must be preloaded and configured per version and policy.

Illustrative settings:

~~~conf
shared_preload_libraries = 'pg_stat_statements,auto_explain'
auto_explain.log_min_duration = '1s'
auto_explain.log_analyze = on
auto_explain.log_buffers = on
auto_explain.log_timing = off
auto_explain.log_nested_statements = off
~~~

If `shared_preload_libraries` already contains other modules, keep the existing list and add the needed modules. `auto_explain` adds overhead; `log_analyze` can add execution time and increase log volume.

### 22.5. Sampling

Use a sampling rate or appropriate threshold under heavy workloads. Do not log plans for every short query if log volume becomes unmanageable.

### 22.6. Sensitive Values

Query text, parameters, and plans can contain sensitive identifiers or literals. Enforce access controls, retention limits, and redaction.

### 22.7. Do Not Enable Every Instrumentation Simultaneously

Each instrumentation layer carries overhead. Start with existing metrics, then enable scoped logging or `auto_explain` to gather targeted evidence.

---

## 23. Distinguishing Root-Cause Categories

| Symptom | Plan Regression | Data Growth/Skew | Stale Stats | Resource/Lock |
| --- | --- | --- | --- | --- |
| Different plan nodes | Usually yes | Possible | Usually yes | Not necessarily |
| Actual rows increased | Possible | Usually yes | Possible | Not necessarily |
| Estimated vs. actual mismatch | Possible | Possible | Very common | Not necessarily |
| Buffers increased | Possible | Usually yes | Possible | Possible |
| Wait event Lock | Not primary sign | Not primary sign | No | Very clear |
| Many queries slow together | Less common | By table/workload | By table | Common |
| ANALYZE helps | Possible if stats caused it | Possible | Common | No |
| Query text changed | Possible | No | No | No |
| Latency varies by parameter | Possible | Very common | Possible | Possible |

This table is an investigative guide, not a rigid classifier. A single incident can involve multiple causes at once.

---

## 24. Process for Comparing Old and New Plans

### 24.1. Keep the Same Query

Ensure SQL text, parameter types, parameter values, and session settings match.

### 24.2. Account for Data Context

If data changed, record row counts and distribution. Do not expect an old plan to remain optimal on new data.

### 24.3. Compare the Node Tree

Look for:
- Changed scan method.
- Changed join order or algorithm.
- Changed aggregation strategy.
- Newly introduced Sort nodes.
- Changes in parallelism.
- Different partition pruning.
- Materialize/Memoize nodes.
- Filters pushed or pulled to different positions.

### 24.4. Compare Cardinalities

At each node, compare estimated rows against actual rows. Find the first node where estimates diverge significantly.

### 24.5. Compare Buffers and Timing

A plan with fewer rows that touches far more buffers can perform worse. Inspect temp blocks, heap fetches, I/O timing, and loops.

### 24.6. Compare Planner Settings

Check PostgreSQL version, extensions, cost constants, `work_mem`, parallelism, JIT, `plan_cache_mode`, and `search_path`.

### 24.7. Plan Hash Alone Is Insufficient

Plan text or hashes can change due to cost numbers, aliases, or version differences without meaningful performance impact. Compare node semantics and actual execution.

### 24.8. Do Not Hardcode Plan Strings in Tests

The planner can change plans as statistics, versions, and datasets evolve. If regression tests are needed, assert appropriate performance or behavioral characteristics and keep test datasets and conditions deterministic.

---

## 25. Mitigation: Choose the Least Risky Action First

### 25.1. When Statistics Are Stale

- Run `ANALYZE` on the affected table/columns.
- Re-measure the query with the same parameters.
- Monitor autoanalyze and table churn.
- Increase statistics target or add extended statistics only if estimates remain inaccurate.

### 25.2. When Data Distribution Shifted

- Identify skewed parameter classes or tenants.
- Inspect MCVs and histograms.
- Review indexes and query paths.
- Consider partitioning or query specialization if workload is stable and justified.

### 25.3. When Plan Regression Comes from Prepared Plans

- Compare generic vs. custom plans.
- Test `plan_cache_mode` at session scope.
- Verify driver prepare behavior.
- Pick a narrowly scoped change and test across other parameter classes.

### 25.4. When an Index Is Missing

- Identify predicate, join, and ordering patterns.
- Check existing indexes and selectivity.
- Design the index with appropriate column ordering.
- Estimate write and storage overhead.
- Use `CREATE INDEX CONCURRENTLY` when appropriate for production operations.
- Verify the index is valid and confirm the new query plan.

### 25.5. When Lock Contention Occurs

- Trace the blocker chain.
- Contact the owner or incident commander.
- Cancel or terminate per policy.
- Shorten transactions or standardize lock acquisition order.
- Review application-side retry behavior.

### 25.6. When I/O or Memory Pressure Occurs

- Check storage and host metrics.
- Inspect query buffers and temp usage.
- Reduce concurrency or non-essential workloads if incident procedures allow.
- Adjust query or `work_mem` within a bounded scope.
- Do not modify global memory settings without calculating peak concurrency.

### 25.7. When an Application Release Caused SQL Regression

- Compare pre-release and post-release SQL.
- Roll back or adjust canary traffic if evidence and process support it.
- Fix ORM or query shape.
- Preserve migration and schema compatibility.
- Monitor `queryid` and endpoint latency.

### 25.8. When Data Growth Is the True Cause

- Optimize indexes and queries for the new scale.
- Partition or archive according to retention policy.
- Pre-aggregate or materialize where appropriate.
- Adjust capacity.
- Do not try forcing a sequential scan into an index scan if the query genuinely needs most of the table.

---

## 26. Actions Not to Rush Into

| Action | Why It Is Risky | When to Consider |
| --- | --- | --- |
| Restart PostgreSQL | Does not fix stats/SQL; destroys evidence, disrupts connections | Server/process issue per runbook |
| VACUUM FULL | Heavy locking, rewrites table, requires extra disk | Measured bloat and planned maintenance window |
| Database-wide REINDEX | Heavy I/O, disk, locks, wide blast radius | Confirmed index corruption/bloat with a plan |
| Disable autovacuum | Dead tuple buildup, transaction ID wraparound risk | Special operations only, with clear replacement |
| Global `SET enable_seqscan=off` | Distorts planner for all queries | Testing alternative plans in a diagnostic session |
| Large global `work_mem` increase | Memory multiplies by operations and concurrency | After calculating peak memory and workload |
| Terminate all long queries | May roll back valid work, trigger retry storms | After identifying blocker, owner, and impact |
| Reset `pg_stat_statements` | Erases needed investigation baseline | Intentionally after saving a snapshot |
| Create many indexes immediately | Increases write cost, storage, vacuum overhead | When workload evidence clearly supports it |
| Raise timeouts indefinitely | Masks waits/locks or hung requests | Not a default mitigation |

---

## 27. Designing More Stable Queries

### 27.1. Sargable Predicates

Avoid wrapping an indexed column in a function when the predicate can be expressed equivalently as a range or supported by an appropriate expression index.

### 27.2. Type-Safe Parameters

Bind parameters with the correct JDBC types. Avoid implicit casts that prevent the planner from using the intended operator or index.

### 27.3. Explicit Projections

`SELECT` only the columns needed to reduce heap fetches, network transfer, and application mapping overhead.

### 27.4. Pagination

Deep `OFFSET` scans and discards many rows. Keyset pagination using a last-seen key and suitable index scales much better.

### 27.5. LIMIT Requires Deterministic ORDER BY

Do not rely on implicit ordering. Include a unique tie-breaker for deterministic pagination.

### 27.6. Join Keys

Ensure compatible data types and appropriate indexes where workload demands. Avoid one-sided casts in join predicates when possible.

### 27.7. CTEs

Use `MATERIALIZED` only when an optimization fence or materialization is intentionally desired. Let the planner inline when appropriate or use `NOT MATERIALIZED` per version semantics.

### 27.8. Avoid N+1

Use join fetching, batch fetching, or consolidated queries appropriately. Monitor call counts in `pg_stat_statements` and application traces.

### 27.9. Stable Query Paths

Under extreme parameter skew, a single query plan may never fit every case. Splitting query paths by business case or parameter class can help, provided maintenance cost and correctness are verified.

---

## 28. Monitoring to Catch Regressions Early

### 28.1. Query-Level Metrics

Track:
- Calls.
- Total execution time.
- Mean/median/p95/p99 latency if your metrics system computes them.
- Rows.
- Shared block reads/hits.
- Temp blocks.
- WAL generated.
- Planning time when available.
- `queryid` and normalized query sample.

### 28.2. Table-Level Metrics

Track:
- Relation size.
- `n_live_tup`/`n_dead_tup`.
- `n_mod_since_analyze`.
- Last autoanalyze/autovacuum.
- Sequential/index scans.
- Index usage.
- Partition sizes.

### 28.3. Server-Level Metrics

Track:
- CPU.
- Memory.
- Storage latency/IOPS/throughput.
- Connections.
- Lock waits.
- Checkpoints/WAL.
- Temp files.
- Replication lag.
- Autovacuum workers.

### 28.4. Baselines by Parameter Class

If query behavior depends on tenant, customer, or date range, store metrics by class or masked endpoint context. A single overall mean can hide a slow tail.

### 28.5. Alerting

Alert on:
- p95/p99 rising above baseline.
- Unusual increases in total query time.
- Spikes in temp files or reads.
- Blocking duration.
- Connection pool saturation.
- Autovacuum lag or growing dead tuples.
- Replica lag if queries read from replicas.

### 28.6. Do Not Alert on a Single Max Latency Spike

A single outlier may come from a cache miss or OS scheduling. Combine duration, call count, percentiles, rate, and impact.

### 28.7. Query Text Privacy

Query monitoring can expose sensitive literals. Use normalized statements, parameter masking, and role-based access control.

---

## 29. Runbook: Sudden Query Slowdown

### Step 1: Log the Incident

Record `queryid`, endpoint, database, start time, current latency, baseline, call frequency, and user impact.

### Step 2: Check Active Queries

Use `pg_stat_activity`. Check `state`, `wait_event`, transaction age, and `application_name`.

### Step 3: Check Blockers

Use `pg_blocking_pids` and `pg_locks`. If blocked, resolve the lock path before tuning the plan.

### Step 4: Capture Statistics Snapshot

Capture the `pg_stat_statements` row and table/index stats. Do not reset counters.

### Step 5: Capture the Plan

Run `EXPLAIN`. When safe, run `EXPLAIN ANALYZE BUFFERS` on a representative query. Save parameters and settings.

### Step 6: Find the First Misestimated Node

Read bottom-up from leaf scans. Inspect actual vs. estimated rows, loops, and rows removed.

### Step 7: Check Data and Statistics

Inspect row growth, MCVs, histograms, `last_autoanalyze`, `n_mod_since_analyze`, partition stats, and extended stats.

### Step 8: Check Plan Context

Inspect generic vs. custom plans, driver settings, query changes, PostgreSQL version, configuration, and indexes.

### Step 9: Check Resources

Check CPU, I/O, memory, temp files, network, connections, and concurrent workload.

### Step 10: Apply the Smallest Mitigation

Examples: `ANALYZE`, query rewrite, session-scoped setting, blocker handling, or reviewed index change.

### Step 11: Verify and Monitor

Compare latency, plan, rows, and buffers against baseline; watch other queries for side effects.

### Step 12: Post-Incident Review

Document root cause, detection gap, mitigation, long-term fix, owner, and needed alerts/runbooks.

---

## 30. Walkthrough Example: Stale Statistics Make a Nested Loop Too Expensive

Suppose a query joins `customers` with `orders`. The planner assumes a customer has only a few orders, whereas a large customer actually has hundreds of thousands of orders.

### 30.1. Unfavorable Plan

~~~text
Nested Loop
  -> Index Scan on customers
       (rows=1) (actual rows=1)
  -> Index Scan on orders
       (rows=10) (actual rows=250000 loops=1)
~~~

Underestimating the inner side or misestimating outer cardinality can push the planner into an unsuitable nested loop.

### 30.2. Inspecting Statistics

~~~sql
SELECT
    attname,
    n_distinct,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'public'
  AND tablename = 'orders'
  AND attname = 'customer_id';
~~~

### 30.3. Updating Statistics

~~~sql
ANALYZE orders (customer_id);
~~~

### 30.4. Re-Measuring

Run `EXPLAIN` with the same parameters. The planner may switch to a hash join or another plan once estimates update. Do not insist on one specific join algorithm; verify better latency and lower total work.

### 30.5. If Skew Persists

Raise the statistics target for `customer_id`, check parameter skew, and consider a separate query path for very large customers.

---

## 31. Walkthrough Example: Correlated Predicates and Extended Statistics

Suppose an `events` table has `tenant_id` and `region`. Certain regions appear only within a subset of tenants. Single-column statistics can misestimate when filtering on both.

### 31.1. Query

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT count(*)
FROM events
WHERE tenant_id = 42
  AND region = 'north';
~~~

### 31.2. Comparing Estimates

Locate the scan node and compare estimated rows with actual rows.

### 31.3. Creating MCV/Dependencies Statistics

~~~sql
CREATE STATISTICS events_tenant_region_stats
    (mcv, dependencies)
ON tenant_id, region
FROM events;

ANALYZE events;
~~~

### 31.4. Re-Running the Plan

Compare estimated rows and actual rows. If estimates improve, the planner can pick a better plan.

### 31.5. Limitations

Extended statistics do not help every query shape or every expression. Evaluate with real plans and workloads.

---

## 32. Walkthrough Example: Generic Plan Unsuited to Parameter Skew

### 32.1. Prepared Query

~~~sql
PREPARE find_orders(bigint) AS
SELECT order_id, total_amount
FROM orders
WHERE customer_id = $1;
~~~

### 32.2. Testing Values with Different Selectivities

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE find_orders(10);

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE find_orders(99);
~~~

### 32.3. Testing Custom Plan in Session

~~~sql
SET plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE find_orders(99);
~~~

### 32.4. Interpretation

Compare estimated/actual rows and execution times. If a custom plan helps one parameter class but increases planning overhead or hurts other values, evaluate the overall trade-off.

### 32.5. Cleaning Up the Prepared Statement

~~~sql
DEALLOCATE find_orders;
~~~

Do not set `force_custom_plan` globally based on a single test.

---

## 33. Walkthrough Example: Query Slow Due to Sort Spill

### 33.1. Plan

~~~text
Sort
  Sort Key: created_at DESC
  Sort Method: external merge  Disk: ...
  Buffers: temp read=... written=...
  -> Seq Scan on orders
~~~

### 33.2. Identifying Causes

- How many rows does the query need to sort?
- Is there a selective predicate?
- Is there an index matching the filter/order?
- Is row width inflated by `SELECT *`?
- Is `work_mem` appropriate for concurrency?
- Did data volume grow unexpectedly?

### 33.3. Testing Session work_mem

~~~sql
BEGIN;
SET LOCAL work_mem = '64MB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC
LIMIT 1000;

ROLLBACK;
~~~

### 33.4. Comparing Alternatives

If the query has `WHERE customer_id = ?`, an index on `(customer_id, created_at)` may outperform increasing `work_mem`. Verify the plan against real workloads.

### 33.5. Conclusion

Sort spills signal that memory, dataset size, or query shape needs examination; they do not automatically prove global `work_mem` must be raised.

---

## 34. Walkthrough Example: Index Scan Slower Than Sequential Scan

### 34.1. Scenario

A query filters `status='processed'` and matches most of the table. An index exists, yet the planner selects `Seq Scan`.

### 34.2. Investigation

- Percentage of rows matching the predicate.
- MCV frequency for `status`.
- Heap page locality.
- Index size.
- Table size.
- Shared buffers/cache state.
- Estimated vs. actual rows.

### 34.3. Do Not Force the Index

If 80% of rows match, `Seq Scan` may be the right plan. Adding another index will not necessarily help.

### 34.4. Optimizing the Query

Select fewer columns, partition workload by time/tenant, use partitioning if appropriate, or create a partial index for rare statuses where queries are truly selective.

### 34.5. Conclusion

An index is an access path, not a guarantee of speed. The planner must pick the cheapest path for current selectivity and storage behavior.

---

## 35. Lab 1: Observing Query Statistics and Execution Plans

Use a development or staging database with synthetic data.

### 35.1. Installing pg_stat_statements

Configure `shared_preload_libraries` for your environment, restart when needed, and create the extension in the test database.

### 35.2. Creating the Table

~~~sql
CREATE TABLE orders_lab (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    amount NUMERIC(12,2) NOT NULL
);
~~~

### 35.3. Loading Data

~~~sql
INSERT INTO orders_lab (customer_id, status, created_at, amount)
SELECT
    (g % 10000) + 1,
    CASE WHEN g % 100 = 0 THEN 'rare'
         WHEN g % 5 = 0 THEN 'pending'
         ELSE 'paid'
    END,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + (g % 365) * INTERVAL '1 day',
    (g % 100000) / 100.0
FROM generate_series(1, 500000) AS g;
~~~

### 35.4. Running Queries Multiple Times

~~~sql
SELECT count(*)
FROM orders_lab
WHERE status = 'paid';

SELECT count(*)
FROM orders_lab
WHERE status = 'rare';
~~~

### 35.5. Viewing pg_stat_statements

Find the normalized statements and compare calls, mean, and total execution time. Save a snapshot before resetting any statistics.

### 35.6. EXPLAIN ANALYZE

Run `EXPLAIN (ANALYZE, BUFFERS)` for both predicates and compare actual rows, buffers, and plans.

### 35.7. Conclusion

The same query shape can have very different selectivity depending on parameter or value distribution.

---

## 36. Lab 2: Stale Statistics and ANALYZE

### 36.1. Capturing Initial Statistics

~~~sql
ANALYZE orders_lab;

SELECT
    attname,
    n_distinct,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE tablename = 'orders_lab';
~~~

### 36.2. Changing Data Distribution

Insert a large batch of rows with `status='rare'` or update many rows from `paid` to `rare`.

### 36.3. Viewing Table Statistics

~~~sql
SELECT
    relname,
    n_live_tup,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE relname = 'orders_lab';
~~~

### 36.4. Running the Plan Before ANALYZE

Compare estimated rows against actual rows for `status='rare'`. Small datasets may autoanalyze on their own; adjust lab thresholds or generate enough data to observe stale stats rather than assuming statistics are guaranteed to be stale.

### 36.5. Running ANALYZE

~~~sql
ANALYZE orders_lab;
~~~

### 36.6. Re-Running the Plan

Compare estimates and actual rows. Observe whether the planner picks a different scan method.

### 36.7. Conclusion

`ANALYZE` updates the distribution model; plans can change once estimates improve.

---

## 37. Lab 3: Extended Statistics

### 37.1. Creating Correlated Columns

~~~sql
CREATE TABLE customer_events_lab AS
SELECT
    g AS event_id,
    (g % 100) + 1 AS tenant_id,
    CASE
        WHEN (g % 100) < 50 THEN 'north'
        ELSE 'south'
    END AS region
FROM generate_series(1, 500000) AS g;
~~~

### 37.2. Analyze

~~~sql
ANALYZE customer_events_lab;
~~~

### 37.3. Checking the Plan

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT count(*)
FROM customer_events_lab
WHERE tenant_id = 1
  AND region = 'north';
~~~

### 37.4. Creating Extended Stats

~~~sql
CREATE STATISTICS customer_events_tenant_region
    (dependencies, mcv)
ON tenant_id, region
FROM customer_events_lab;

ANALYZE customer_events_lab;
~~~

### 37.5. Comparing

Compare estimated rows before and after. Lab data might not trigger strong correlation for every statistics kind; test multiple distributions and explain the results.

### 37.6. Conclusion

Extended statistics help the planner model relationships between columns instead of always assuming independence.

---

## 38. Lab 4: Prepared Plans and Parameter Skew

### 38.1. Creating Skewed Data

Create one customer with many orders and many customers with only a few orders.

### 38.2. Creating an Index

~~~sql
CREATE INDEX orders_lab_customer_idx
ON orders_lab(customer_id);
~~~

### 38.3. Preparing the Statement

~~~sql
PREPARE orders_by_customer(bigint) AS
SELECT order_id, amount
FROM orders_lab
WHERE customer_id = $1;
~~~

### 38.4. Comparing Parameters

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_by_customer(1);

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_by_customer(9999);
~~~

### 38.5. Testing plan_cache_mode

Test `force_custom_plan` and `force_generic_plan` in the session. Record plans and timings for each parameter class.

### 38.6. Cleaning Up the Statement

~~~sql
DEALLOCATE orders_by_customer;
~~~

### 38.7. Conclusion

Prepared plan behavior can make identical SQL text behave differently across skewed parameters.

---

## 39. Lab 5: Lock Contention and Sort Spill

### 39.1. Lock Test

Open two `psql` sessions:
- Session A: `BEGIN; SELECT ... FOR UPDATE` on a row.
- Session B: `UPDATE` the same row.
- Observe `pg_stat_activity`, `pg_locks`, and `pg_blocking_pids`.
- Commit or roll back Session A and watch Session B proceed.

### 39.2. Lock Timeout

In Session B, test `SET LOCAL lock_timeout` inside a transaction and observe the SQLSTATE when it times out.

### 39.3. Sort Test

Write a query sorting a large number of rows with a wide projection. Run `EXPLAIN (ANALYZE, BUFFERS)` and inspect `Sort Method` and `temp` blocks.

### 39.4. Testing an Index/Order Path

Create an index matching the filter/order in the lab, re-run, and compare buffers and latency.

### 39.5. Testing Session-Scoped work_mem

Use `SET LOCAL work_mem` in a test transaction. Compare temp usage and memory risk.

### 39.6. Conclusion

A slow query may be blocked on locks or spilling to disk; identify waits and resource usage before tweaking the planner.

---

## 40. Practice Exercises

### Exercise 1 — Incident Triage

An endpoint's latency jumped from 100 ms to 8 seconds. List the information you should collect before modifying the query.

### Exercise 2 — Query vs. Wait

Distinguish CPU-bound, I/O-bound, lock-bound, and connection-pool-bound queries.

### Exercise 3 — pg_stat_statements

Write a query to find the top 20 statements by `total_exec_time` and `mean_exec_time`.

### Exercise 4 — Queryid

Why can a normalized `queryid` hide parameter skew? Propose a safe way to observe parameter classes.

### Exercise 5 — Stats Reset

Explain why you should not reset `pg_stat_statements` right as an incident begins.

### Exercise 6 — pg_stat_activity

Write a query to find long-running active queries and display `wait_event_type` and `wait_event`.

### Exercise 7 — Idle in Transaction

A backend has been `idle in transaction` for 30 minutes. What risks must you check before terminating it?

### Exercise 8 — Blocking

Write a query using `pg_blocking_pids` to identify blocked PIDs and blocker PIDs.

### Exercise 9 — Lock Details

Use `pg_locks` and `pg_stat_activity` to identify lock mode, relation, and granted status.

### Exercise 10 — EXPLAIN

Distinguish `EXPLAIN` from `EXPLAIN ANALYZE`. Why can `ANALYZE` impact production?

### Exercise 11 — DML Plan

Why does `BEGIN; EXPLAIN ANALYZE UPDATE; ROLLBACK;` not guarantee all side effects are undone?

### Exercise 12 — Actual vs. Estimated

A scan estimates 10 rows but actually returns 100,000 rows. How can this affect join selection?

### Exercise 13 — Loops

An Index Scan returns 20 rows with `loops=5000`. Estimate total row visits and explain why reading `loops` is essential.

### Exercise 14 — Buffers

Distinguish `shared hit`, `shared read`, `dirtied`, `written`, and `temp` blocks.

### Exercise 15 — Cache

The first query run is slow, and the second run is fast. How do you distinguish cache warming from a plan improvement?

### Exercise 16 — Statistics

Explain `null_frac`, `n_distinct`, MCVs, `histogram_bounds`, and `correlation`.

### Exercise 17 — Autoanalyze

Write a query to inspect `n_mod_since_analyze`, `last_autoanalyze`, and `n_dead_tup` for a table.

### Exercise 18 — Manual ANALYZE

When should you run `ANALYZE` after a bulk load? How does `ANALYZE` differ from `VACUUM`?

### Exercise 19 — Statistics Target

A rare status does not appear in MCVs. When can increasing the statistics target help?

### Exercise 20 — Extended Statistics

Create dependencies, MCV, and ndistinct statistics for two correlated columns.

### Exercise 21 — Data Skew

One tenant owns 60% of rows in a multi-tenant table. Why might the same query need different plans for this tenant versus a small tenant?

### Exercise 22 — Nested Loop

Explain why a Nested Loop can become slow if the outer row estimate is far too low.

### Exercise 23 — Hash Spill

Identify a Hash Join or HashAggregate spill in `EXPLAIN` and outline how to investigate it.

### Exercise 24 — Sort Spill

A Sort uses external merge and writes temp blocks. What factors should you check before raising `work_mem`?

### Exercise 25 — Generic/Custom Plan

Explain the difference and use `EXPLAIN EXECUTE` to compare parameter values.

### Exercise 26 — plan_cache_mode

Test `force_custom_plan` and `force_generic_plan` at session scope. Why shouldn't you set them globally immediately?

### Exercise 27 — JDBC Prepare

Which PostgreSQL JDBC driver settings can affect server-side prepared statements?

### Exercise 28 — Index Selectivity

Why can an index scan be slower than a sequential scan when a predicate matches most of the table?

### Exercise 29 — Multicolumn Index

Design an index for a query filtering on `customer_id` and a range on `created_at`; explain the column order.

### Exercise 30 — Partial Index

A partial index `WHERE status='open'` is not used by the planner for a prepared query. Analyze predicate implication and generic plans.

### Exercise 31 — Index-Only Scan

Why can an `Index Only Scan` still have high `Heap Fetches`? How does the visibility map relate?

### Exercise 32 — Partition Pruning

A query scans all partitions even though it only needs one month. Check predicates, casts, and partition bounds.

### Exercise 33 — Vacuum

`n_dead_tup` rises sharply and `last_autovacuum` is old. List possible causes and data to check.

### Exercise 34 — Long Snapshots

Explain why a long transaction or replication slot can prevent vacuum from cleaning up tuples.

### Exercise 35 — Resource Pressure

Many unrelated queries slow down simultaneously. Build a checklist covering CPU, I/O, memory, connections, checkpoints, and network.

### Exercise 36 — auto_explain

Configure `auto_explain` with thresholds and buffers. State the trade-offs of `log_analyze` and `log_timing`.

### Exercise 37 — Application Regression

After upgrading Hibernate, query count jumps from 3 to 200. Distinguish N+1 from plan regression using `pg_stat_statements` and tracing.

### Exercise 38 — Safe Mitigation

A blocker has held a lock for 20 minutes. Outline the procedure to verify owner, transaction, and impact before canceling or terminating.

### Exercise 39 — Incident Postmortem

Write a root-cause report template distinguishing trigger, direct cause, contributing factors, mitigation, and prevention.

### Exercise 40 — End-to-End Diagnosis

A reporting query suddenly slows down after a bulk import and an application deployment. Build a plan to collect `pg_stat_statements`, `pg_stat_activity`, blockers, `EXPLAIN ANALYZE BUFFERS`, stats, indexes, parameter plans, and resource metrics; select a mitigation, verify it, and monitor for regression.

---

## 41. Slow Query Investigation Checklist

| Item | What to Confirm |
| --- | --- |
| Impact | Which queries, endpoints, or tenants are affected |
| Start time | When latency began increasing |
| Baseline | p50/p95/p99 and call rates before/after |
| Query identity | `queryid`, normalized SQL, parameter class |
| Application release | SQL/ORM/driver changes |
| `pg_stat_statements` | total/mean/max time, rows, buffers, temp |
| Active sessions | `state`, `wait_event`, `query_age`, `xact_age` |
| Blocking | `pg_blocking_pids` and lock chain |
| Plan | Appropriate `EXPLAIN`/`EXPLAIN ANALYZE` |
| Cardinality | Estimated vs. actual rows at every node |
| Loops | Nested Loops and repeated scans |
| Buffers | hit/read/dirtied/written/temp |
| Sort/hash | spills, batches, disk usage |
| Statistics | `last_analyze`/`autoanalyze`, `n_mod_since_analyze` |
| Distribution | MCV, histogram, `null_frac`, `n_distinct` |
| Correlation | Whether extended statistics are needed |
| Table growth | live/dead tuples, relation size |
| Indexes | definitions, selectivity, usage, validity |
| Partitions | pruning, partition stats/indexes |
| Prepared plans | generic/custom, driver prepare behavior |
| Settings | `work_mem`, costs, parallelism, JIT, `plan_cache_mode` |
| Resource | CPU, memory, I/O latency, temp, WAL/checkpoints |
| Connections | pool saturation, active/idle sessions |
| Autovacuum | worker activity, lag, blockers |
| Logs | duration, lock waits, temp files, `auto_explain` |
| Safety | `EXPLAIN ANALYZE` impact and data sensitivity |
| Mitigation | smallest reversible change |
| Validation | same parameters/workload and result correctness |
| Regression | monitor query and collateral workloads |
| Documentation | root cause, owner, follow-up, and alert |

## Conclusion

Sudden query slowdowns usually stem from changes in the execution plan, data volume/distribution, or statistics; at other times, the query is waiting on locks, I/O, or shared resources. The PostgreSQL planner can only choose good plans when estimates closely match actual data and the cost model reflects the environment. Therefore, an investigation must combine query statistics, active sessions, locks, execution plans, table statistics, and host metrics.

Principles to remember:

1. **Determine whether the query is running or waiting.** Wait events and blockers prevent optimizing the wrong cause.
2. **Preserve evidence before changing anything.** Save `queryid`, parameters, plans, statistics, and timestamps.
3. **Use `pg_stat_statements` to find impactful workloads.** Combine calls, total time, mean/max, and buffers.
4. **Read `EXPLAIN ANALYZE` with `BUFFERS`.** Compare actual rows against estimates, loops, temp usage, and rows removed.
5. **Find the first misestimated node.** Cardinality errors at the leaves lead to poor join orders and algorithms.
6. **Run `ANALYZE` after major data changes.** Check autoanalyze and `n_mod_since_analyze` instead of assuming stats updated.
7. **Use extended statistics when columns correlate.** MCV, dependencies, and ndistinct model relationships single-column stats miss.
8. **Check parameter skew and prepared plans.** One generic plan may not fit all parameter values.
9. **An index is not always better than a Seq Scan.** Selectivity, heap locality, cache, and row width govern the access path.
10. **Distinguish bloat from data growth.** `VACUUM`, `ANALYZE`, and `REINDEX` solve different problems.
11. **Do not tune global settings by guesswork.** Test session-scoped changes and measure concurrency/resource impact.
12. **Do not rush restarts, `VACUUM FULL`, or session termination.** These can destroy evidence or cause severe disruption.
13. **Compare the same parameter class and workload.** A single faster run does not prove a regression is fixed.
14. **Monitor both the database and the application.** N+1 queries, connection pools, networks, and remote services can slow endpoints despite good query plans.
15. **Document root cause and prevention.** Add baselines, alerts, migration checks, and runbooks to detect recurrences early.

A reliable troubleshooting workflow starts with observation, locates the node or resource introducing latency, checks statistics and data distribution, and tests a reversible mitigation. Confirm the incident is resolved only when query results remain correct, latency improves across representative parameter classes, and other workloads do not regress.

## References

- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html)
- [PostgreSQL — Planner Statistics](https://www.postgresql.org/docs/current/planner-stats.html)
- [PostgreSQL — Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html)
- [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [PostgreSQL — pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html)
- [PostgreSQL — auto_explain](https://www.postgresql.org/docs/current/auto-explain.html)
- [PostgreSQL — CREATE STATISTICS](https://www.postgresql.org/docs/current/sql-createstatistics.html)
- [PostgreSQL — Planner Configuration](https://www.postgresql.org/docs/current/runtime-config-query.html)
