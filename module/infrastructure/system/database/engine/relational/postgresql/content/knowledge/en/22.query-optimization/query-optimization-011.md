# Measuring Performance Regressions After Schema, Data, or Config Changes in PostgreSQL

In PostgreSQL, an unchanged SQL query can still become slower after deployment:

- Adding an index speeds up `SELECT` while slowing down `INSERT`/`UPDATE`.
- Changing column types, constraints, or partitioning layout.
- A table growing from millions to hundreds of millions of rows.
- Skewed data distribution: one tenant accumulates far more rows than all others.
- Updated statistics after `ANALYZE` cause the planner to pick a new plan.
- Tuning `work_mem`, `random_page_cost`, parallelism, JIT, or connection pool settings.
- Upgrading PostgreSQL, the JDBC driver, or changing how prepared statements are used.
- Autovacuum, backups, checkpoints, cache state, or concurrent load creating measurement noise.

When a query jumps from 40 ms to 70 ms, you must distinguish a **true performance regression** from variance caused by cache state, CPU load, data changes, or workload shifts. Conversely, a change might leave average latency flat while spiking **p99 latency**, triggering frequent timeouts for a subset of users.

This lesson, **“Measuring Performance Regressions After Schema, Data, or Config Changes”**, in the **Query Optimization** chapter of the **Database Engine Relational PostgreSQL** module, teaches how to build reproducible measurements: establish a baseline, control the environment, collect execution plans and metrics, compare before vs. after, isolate root causes, and make evidence-based rollout decisions.

It uses reproducible SQL datasets, `EXPLAIN (ANALYZE, BUFFERS)`, `pg_stat_statements`, `pg_stat_database`, `pgbench`, and regression-gate workflow patterns. Data-generation examples are strictly for an **isolated lab database**—never run them in production.

## 1. What Is a Performance Regression?

A **performance regression** is a meaningful degradation in one or more performance characteristics relative to a valid reference baseline after a change.

Symptoms include:

- Increased response time per query, request, or transaction.
- Reduced transactions processed per second.
- Higher CPU, I/O, memory, or WAL usage for identical work.
- Increased lock waits, deadlocks, timeouts, or error rates.
- Less efficient row counts read or table/index access paths.
- Degraded tail latency for specific parameter groups even when mean latency stays flat.

**A regression does not automatically mean the SQL is buggy.** A query can still return accurate results while consuming more resources. Conversely, a query running faster because it accidentally omits rows is **not a successful optimization**.

### 1.1. Metric Example

| Metric | Baseline | Candidate | Signal |
|---|---:|---:|---|
| p50 latency | 12 ms | 13 ms | Minor shift |
| p95 latency | 45 ms | 95 ms | Clear degradation |
| p99 latency | 120 ms | 430 ms | Severe tail latency |
| Throughput | 1500 req/s | 1430 req/s | ~4.7% drop |
| Database CPU | 45% | 75% | Resource load needs checking |
| Timeout rate | 0.1% | 1.8% | Requires investigation |

These are **hypothetical numbers** for illustration, not measured PostgreSQL output.

## 2. Separating Three Categories of Changes

### 2.1. Schema Changes

Examples:

- Adding or dropping B-tree, BRIN, GIN, GiST, or partial indexes.
- Adding `INCLUDE` columns to an index.
- Altering column data types or constraints.
- Converting a table into a partitioned table.
- Changing view or materialized view definitions.
- Table-rewriting migrations or building indexes on very large tables.

An index can accelerate `SELECT` while slowing `INSERT`/`UPDATE` due to index maintenance and extra WAL generation.

### 2.2. Data Changes

Examples:

- Overall table growth.
- One tenant growing dramatically larger than peers.
- `status='active'` share shifting from 20% to 95%.
- Bulk archiving, deletes, or ETL loads.
- Changing correlation between `tenant_id` and `state`.
- Growing partition count or individual partition sizes.

With identical SQL and identical indexes, PostgreSQL can still switch plans because **selectivity and cardinality** changed.

### 2.3. Configuration or Version Changes

Examples:

- `work_mem`, `shared_buffers`, `effective_cache_size`.
- `random_page_cost` or `seq_page_cost`.
- Parallel workers, JIT, `plan_cache_mode`.
- Autovacuum tuning or connection pool sizing.
- PostgreSQL major version, pgJDBC, storage tier, or CPU quotas.

These can affect many queries simultaneously, so measure the **overall workload** rather than just one isolated `SELECT`.

## 3. Choosing the Unit of Measurement: Query, Transaction, or Endpoint

One HTTP request can execute multiple SQL statements:

~~~text
GET /orders
    |
    +--> SELECT access permissions
    +--> SELECT orders list
    +--> SELECT summary totals
    +--> SELECT customer profile
~~~

Layers to distinguish:

| Level | What It Measures |
|---|---|
| SQL query | Planning, execution time, rows, buffers, scan/join plan |
| Transaction | Sum of queries, lock waits, commit overhead, retries |
| Endpoint | DB + network + serialization + application logic |
| Batch job | Completion time and total batch resource consumption |
| Database workload | TPS, concurrency, CPU/I/O/WAL, error rates |

If `EXPLAIN ANALYZE` on a single `SELECT` looks unchanged while the endpoint slows down, the cause may be **N+1 queries, pool waits, network latency, or lock contention**—not that query's plan.

## 4. What Is a Baseline?

A **baseline** is the pre-change metric dataset, measured and recorded with enough context to compare fairly against a candidate.

A useful baseline records:

1. Query or endpoint name.
2. SQL template and parameter cohorts.
3. Schema and index revision.
4. Dataset snapshot, row counts, and data distribution.
5. PostgreSQL version, client driver, and relevant GUCs.
6. Hardware, storage tier, connection pool, and concurrency level.
7. Warm-up and cache policy.
8. Run duration and iteration count.
9. Latency, throughput, errors, and resource metrics.
10. `EXPLAIN` plans and statistics snapshots at measurement time.

Example metadata header:

~~~text
benchmark_id: orders-list-2026-11-14
schema_revision: <migration-id>
postgres_version: <server-version>
dataset_revision: <snapshot-id>
query_template: list_recent_orders
parameter_groups: tenant-small, tenant-medium, tenant-large
clients: 16
warmup_seconds: 60
measure_seconds: 300
cache_policy: warm
isolation: read_committed
baseline_commit: <git-revision>
~~~

The `<...>` tokens above are placeholders to fill with real metadata, not measured results.

### 4.1. Never Treat One Single Timing as a Baseline

~~~text
GET /orders: 32 ms
~~~

reveals nothing about distribution, noise, or parameter cohorts. It cannot support reliable regression detection.

## 5. Metrics Worth Tracking

| Metric | Meaning | Pitfall |
|---|---|---|
| p50 latency | Median | Hides tail latency |
| p95/p99 latency | High percentiles | Requires adequate sample size |
| Average latency | Mean | Skewed by outliers |
| TPS/RPS | Throughput | Only comparable under matching workload |
| Error/timeout rate | Behavior under load | Never exclude failed requests from summary |
| `Planning Time` | Planner cost | Prepared statements behave differently |
| `Execution Time` | Server plan execution time | Excludes full client round-trip |
| `Shared buffers hit/read` | Buffer accesses | `read` does not necessarily mean physical disk I/O |
| `Temp reads/writes` | Sort/hash spills | Not all queries use temp files |
| `WAL bytes/records` | Write amplification | Crucial after adding indexes |
| CPU/memory | Resource load | Only comparable at matching concurrency |
| Lock waits | Blocking by other transactions | Not a plan regression |
| Estimated/actual rows | Cardinality estimation accuracy | Not a latency metric by itself |
| Rows returned/affected | Work volume | Must preserve result semantics |

Timing one query alone does not make a complete performance test.

## 6. Before-and-After Comparison Formulas

For **lower-is-better** metrics like latency:

\[
\Delta_{\%}=\frac{\text{after}-\text{before}}{\text{before}}\times100
\]

For example, if p95 rises from 120 ms to 150 ms:

\[
\Delta_{\%}=\frac{150-120}{120}\times100=25\%
\]

For **higher-is-better** metrics like throughput:

\[
\text{throughput change}_{\%}
=\frac{\text{after}-\text{before}}{\text{before}}\times100
\]

If TPS drops from 1000 to 900, the change is **-10%**.

If the baseline equals 0 (such as zero pre-change errors), standard percentage ratios break down. Report absolute deltas or define explicit rules instead.

### 6.1. Consider Both Percentages and Absolute Deltas

Going from 0.3 ms to 0.6 ms is +100%, yet adds only 0.3 ms. Going from 200 ms to 240 ms is +20%, yet adds 40 ms and can breach an SLO.

A regression gate may combine relative thresholds, absolute thresholds, and reproducibility checks; no single threshold fits every product.

## 7. Controlling Apples-to-Apples Scenarios

To isolate **only schema or configuration impact**, hold steady:

- SQL text and parameter values.
- Dataset snapshot.
- Query result semantics.
- PostgreSQL version (unless testing an upgrade).
- Hardware and storage class.
- Client concurrency and arrival rate.
- Transaction isolation level.
- Driver and connection pool settings.
- Background workload.
- Warm-up and cache policy.

When the variable under test is **data growth**, the dataset cannot stay identical. Document it explicitly:

~~~text
Baseline: 10 million rows, 20% completed
Candidate: 30 million rows, 90% completed
Schema/config: unchanged
~~~

Separate **scale effects** from **plan regressions**, ideally adding an equal-dataset control benchmark.

## 8. Warm Cache vs. Cold Cache

Two runs of the exact same query can yield very different times due to caching:

~~~text
Run 1: 220 ms  (pages not yet in shared buffers)
Run 2: 35 ms   (warmer cache)
Run 3: 32 ms
~~~

Cache layers include:

- PostgreSQL shared buffers.
- OS page cache.
- Storage controller cache.
- Application caches.

### 8.1. Measurement Policies

- **Warm-cache:** dedicated warm-up phase excluded from measured samples.
- **Cold-ish:** isolated test environment with controlled cache reset, never touching production.
- **Steady-state:** realistic traffic mix letting caches behave naturally.

Never restart production or drop OS caches host-wide just to run a “cold” benchmark.

### 8.2. Avoid Order Bias Favoring the Candidate

If baseline always runs first and candidate always runs second, the candidate inherits a warmer cache. Run alternating A/B/A/B rounds or test on twin environments restored from the same snapshot.

## 9. One Fast Query Does Not Guarantee a Healthy Workload

Suppose real traffic looks like:

~~~text
70% SELECT by tenant
20% INSERT
8% UPDATE
2% summary reports
~~~

Benchmarking only the `SELECT` accelerated by a new index ignores write amplification on DML.

Define:

- Query mix.
- Parameter distribution.
- Request frequency.
- Concurrency level.
- Result sizes.
- Transaction boundaries.
- Off-peak, average, and peak load profiles.

Pair **microbenchmarks** (explaining one query) with **workload benchmarks** (showing system-wide impact).

## 10. Building a Reproducible Lab Dataset

In an **empty lab database**, create a 200,000-row `events` table with one very large tenant and many small ones:

~~~sql
CREATE SCHEMA perf_lab;

CREATE TABLE perf_lab.events (
    event_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    state TEXT NOT NULL
        CHECK (state IN ('ok', 'failed')),
    occurred_at TIMESTAMPTZ NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    payload TEXT NOT NULL
);

INSERT INTO perf_lab.events (
    event_id, tenant_id, state,
    occurred_at, amount, payload
)
SELECT
    g::BIGINT,
    CASE
        WHEN g <= 150000 THEN 1
        ELSE 2 + g % 50
    END,
    CASE
        WHEN g % 997 = 0 THEN 'failed'
        ELSE 'ok'
    END,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + g * INTERVAL '1 second',
    (g % 10000 + 1)::NUMERIC(12,2),
    repeat('x', 64)
FROM generate_series(1, 200000) AS g;

CREATE INDEX idx_events_tenant_time
ON perf_lab.events (
    tenant_id,
    occurred_at DESC,
    event_id DESC
);

ANALYZE perf_lab.events;
~~~

Notice the seed avoids `random()`, so running it from a fresh database reproduces exact deterministic rows and distributions:

- Tenant 1 holds 150,000 rows.
- Other tenants share the remaining 50,000 rows.
- `'failed'` appears at roughly 0.1% because `g % 997 = 0`.
- `amount` is not included in the initial index.
- The initial index covers tenant and timestamp ordering, not `state`.

### 10.1. Inspect the Distribution

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (
        WHERE tenant_id = 1
    ) AS tenant_1_rows,
    COUNT(*) FILTER (
        WHERE state = 'failed'
    ) AS failed_rows
FROM perf_lab.events;

SELECT
    tenant_id, state, COUNT(*) AS row_count
FROM perf_lab.events
GROUP BY tenant_id, state
ORDER BY tenant_id, state;
~~~

Do not chase predicted runtime numbers; the goal is comparing changes consistently on your specific environment.

## 11. Target Query for Baseline Collection

~~~sql
SELECT
    event_id,
    occurred_at,
    amount
FROM perf_lab.events
WHERE tenant_id = 1
  AND state = 'failed'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 50;
~~~

For tenant 1, `state='failed'` is rare. The initial index is:

~~~text
(tenant_id, occurred_at DESC, event_id DESC)
~~~

so it supports sort order without directly indexing `state` to narrow matching rows.

The planner might choose Index Scan, Seq Scan, Bitmap Scan, or another strategy depending on stats and cost settings. **Never assume a specific plan appears automatically.**

### 11.1. Small-Tenant Query

~~~sql
SELECT event_id, occurred_at, amount
FROM perf_lab.events
WHERE tenant_id = 2
  AND state = 'failed'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 50;
~~~

Benchmark multiple parameter cohorts because large vs. small tenants can incur vastly different costs. In production tests, reflect real request frequencies instead of picking two arbitrary tenants.

## 12. `EXPLAIN` and Planner Cost Semantics

~~~sql
EXPLAIN
SELECT event_id, occurred_at, amount
FROM perf_lab.events
WHERE tenant_id = 1
  AND state = 'failed'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 50;
~~~

Plain `EXPLAIN` (without `ANALYZE`) reports the chosen plan and estimates:

- Node types.
- Estimated rows.
- Estimated startup and total cost.
- Index and filter conditions.
- Sort, join, aggregate, or parallel nodes.

**Cost is not milliseconds.** Never read `cost=100` as “this query takes 100 ms.”

A lower estimated cost explains planner preference—not proven faster real-world execution.

## 13. `EXPLAIN (ANALYZE, BUFFERS)`

~~~sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS,
    VERBOSE,
    SUMMARY,
    FORMAT TEXT
)
SELECT
    event_id,
    occurred_at,
    amount
FROM perf_lab.events
WHERE tenant_id = 1
  AND state = 'failed'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 50;
~~~

Fields to inspect:

| Field | Meaning |
|---|---|
| `Planning Time` | Time spent planning this execution |
| `Execution Time` | Server time executing the plan |
| `actual rows` | Actual rows emitted by the node |
| `loops` | How many times the node ran |
| `Rows Removed by Filter` | Rows scanned then discarded |
| `Buffers: shared hit/read` | Pages found in shared buffers / read into shared buffers |
| `temp read/written` | Temporary file I/O from sorts/hashes |
| `Sort Method` | In-memory or external sort method |
| `Heap Fetches` | Table heap checks required during Index Only Scan |
| `Workers Planned/Launched` | Parallel workers requested vs. started |
| `Settings` | Non-default GUCs affecting the planner |

### 13.1. `actual rows` Is Per-Loop Average

If a node reports `actual rows=100 loops=10`, do not read `100` as total work; factor in `loops` and child nodes.

### 13.2. `ANALYZE` Executes the Statement

`EXPLAIN (ANALYZE)` really runs the SQL. For `SELECT`, it reads data; for `UPDATE`/`DELETE`/`INSERT`/`MERGE`, it modifies data. Never run uncontrolled `EXPLAIN ANALYZE` on production DML.

### 13.3. `TIMING OFF`

For very short queries, per-node timing adds measurement overhead. Try:

~~~sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    TIMING OFF,
    SUMMARY ON
)
SELECT COUNT(*)
FROM perf_lab.events
WHERE tenant_id = 1;
~~~

This reduces per-node timing overhead while preserving counters and overall summary execution time, depending on PostgreSQL version.

## 14. Reading `BUFFERS` Without Misinterpreting

Hypothetical output:

~~~text
Buffers: shared hit=1500 read=100
~~~

- `shared hit`: page found in PostgreSQL shared buffer cache.
- `shared read`: page read into shared buffers from lower storage/OS layers.

`shared read` **does not necessarily mean physical disk I/O**, as the OS page cache may serve it from RAM.

`temp read/written` generally reflects sort/hash spill files. `shared dirtied/written` reflects modified data pages.

### 14.1. High Cache Hits Do Not Guarantee Speed

Scanning millions of pages even at 100% `shared hit` still consumes heavy CPU. Reading far fewer rows with a few `read`s can easily finish sooner.

Read `BUFFERS` alongside `actual rows` and `Execution Time` to understand **total work done**.

## 15. Saving Execution Plans in JSON

~~~sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS,
    FORMAT JSON
)
SELECT event_id, occurred_at, amount
FROM perf_lab.events
WHERE tenant_id = 1
  AND state = 'failed'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 50;
~~~

JSON format works well for automated pipelines:

- Compare node types, join orders, and index names.
- Compare planned vs. actual rows.
- Compare buffers, loops, timings, and spills.
- Archive before/after artifacts for later investigation.

**Do not byte-diff JSON files** and fail builds on minor runtime drift; timings and counters naturally vary.

Compare **plan structure** separately from **metric distributions**.

## 16. Schema Scenario: Adding a New Index

After capturing the baseline, add an index in the lab database:

~~~sql
CREATE INDEX idx_events_tenant_state_time
ON perf_lab.events (
    tenant_id,
    state,
    occurred_at DESC,
    event_id DESC
)
INCLUDE (amount);

ANALYZE perf_lab.events;
~~~

The new index:

- Narrows directly on both `tenant_id` and `state`.
- Supports the requested timestamp order.
- Includes `amount` to enable index-only scans.

Re-run **the exact same query**:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT event_id, occurred_at, amount
FROM perf_lab.events
WHERE tenant_id = 1
  AND state = 'failed'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 50;
~~~

### 16.1. Never Promise an Index-Only Scan

Even when all columns sit in the index, the planner may pick another scan type. Index-only scans depend on the **visibility map**; unless pages are all-visible, `Heap Fetches` still occur.

If `VACUUM` ran on only one side of the comparison, visibility-map differences—not only the index—can skew results.

### 16.2. Measure DML After Adding an Index

Every new index must be updated on matching `INSERT`/`UPDATE` statements, potentially:

- Increasing WAL volume.
- Increasing index storage footprint.
- Increasing write CPU and I/O.
- Blocking HOT updates when indexed columns are modified.
- Increasing vacuum and buffer-cache pressure.

Never declare a migration a pure win solely because one `SELECT` got faster.

## 17. Checking Index Size

~~~sql
SELECT
    pg_size_pretty(
        pg_relation_size('perf_lab.events'::regclass)
    ) AS heap_size,
    pg_size_pretty(
        pg_indexes_size('perf_lab.events'::regclass)
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size('perf_lab.events'::regclass)
    ) AS total_size;
~~~

Compare before vs. after:

- Heap size.
- Total indexes size.
- Total relation size.
- Write workload WAL and I/O.
- `SELECT` and DML latencies.

A larger index can be worthwhile if read gains clearly outweigh write and storage overhead. Base the trade-off on actual read/write ratios.

## 18. Schema Migrations and Rollout Impact

Measure performance both **during migration** and **after migration**.

Running plain `CREATE INDEX` on a large table can block writes while building. `CREATE INDEX CONCURRENTLY` avoids blocking normal writes during the build, yet:

- Takes longer and uses extra passes.
- Cannot run inside an explicit transaction block.
- Waits on concurrent transactions and snapshots.
- Can leave an `INVALID` index behind if it fails.
- Still consumes CPU and I/O.

### 18.1. Verify Index Validity

~~~sql
SELECT
    c.relname AS index_name,
    x.indisvalid,
    x.indisready
FROM pg_index AS x
JOIN pg_class AS c
    ON c.oid = x.indexrelid
WHERE x.indrelid = 'perf_lab.events'::regclass
ORDER BY c.relname;
~~~

If `indisvalid` is false, the planner cannot use the index as expected. Never blame a “planner regression” when an index build never finished validly.

## 19. Changing Column Types, Constraints, or Partitioning

Beyond indexes, other schema changes shift performance too:

**Data types:** change available operators, implicit casts, row widths, index eligibility, and conversion overhead.

**Constraints:** `CHECK`, `UNIQUE`, and `FOREIGN KEY` add validation checks on writes, while some constraints also assist planner optimizations.

**Partitioning:** queries filtering the partition key benefit from pruning; queries missing it scan many partitions and increase planning cost.

**Views/materialized views:** changing joins, refresh logic, or predicate pushdown alters resulting plans.

Distinguish migration duration from steady-state performance, and verify result correctness across any non-intentional changes.

## 20. Data Growth and Data Skew

A query rising from 10 ms to 100 ms as a table grows from 100,000 to 100 million rows can be a **scale effect**, not necessarily a code or planner regression.

Key diagnostic questions:

- How much did row count grow?
- Did a skewed value become dominant?
- Did a giant new tenant appear?
- Does the query now return more rows?
- Is the index still selective?
- Do statistics reflect the new distribution?
- Did partition counts or partition sizes surge?
- How did CPU/I/O per unit of work shift?

### 20.1. Two Complementary Tests

**A — Same-data test:** identical snapshot, vary only schema or config to isolate causes.

**B — Scale test:** identical schema and config, scale data across 1M / 5M / 20M / 100M rows to measure growth curves and throughput.

Never mix both experiments into one ambiguous single conclusion.

## 21. Analyzing `pg_stats` and `ANALYZE`

~~~sql
SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'perf_lab'
  AND tablename = 'events'
  AND attname IN ('tenant_id', 'state');
~~~

`most_common_vals` and `most_common_freqs` expose the frequent values and shares the planner relies on.

If an ETL shifts `'failed'` from 0.1% to 60% without updated statistics, the old plan can perform poorly.

~~~sql
ANALYZE perf_lab.events;
~~~

`ANALYZE` refreshes stats without modifying row data. It **can alter chosen plans**. When benchmarking before vs. after, record exactly when `ANALYZE` runs—never update stats only on the candidate and credit the entire difference to a schema change.

### 21.1. Extended Statistics for Correlated Columns

~~~sql
CREATE STATISTICS st_events_tenant_state
    (mcv, dependencies)
ON tenant_id, state
FROM perf_lab.events;

ANALYZE perf_lab.events;
~~~

This can improve multi-column estimates when `tenant_id` and `state` correlate. It does not guarantee optimizing every query or join automatically.

Treat it as a **separate change to benchmark separately**, not bundled silently with a new index if you need clear attribution.

## 22. Estimated Rows Diverging from Actual Rows

Illustrative example:

~~~text
Nested Loop  (cost=... rows=10 ...)
             (actual ... rows=50000 ...)
~~~

The planner expected 10 rows yet processed 50,000. Cardinality errors like this can trigger:

- Excessively looping Nested Loops.
- Sort/hash spills.
- Choosing Index Scan where Seq Scan would win.
- Join orders inflating intermediate row counts.

Even so, an estimated/actual mismatch **alone** does not prove a regression. Check runtime, buffers, loops, and whether a better alternative plan exists.

### 22.1. Checklist for Estimation Mismatches

1. Are statistics up to date?
2. Did data distribution shift?
3. Are columns correlated?
4. Does one parameter cohort skew sharply from others?
5. Do casts or functions obscure selectivity/indexes?
6. Is a prepared statement stuck on a poor generic plan?
7. Which join node inflates cardinality?

## 23. Measuring Configuration Changes

Commonly adjusted GUCs:

| Setting | Benchmark Relevance |
|---|---|
| `work_mem` | Sort/hash budget; spills vs. RAM pressure |
| `shared_buffers` | Shared page cache, usually requires restart |
| `effective_cache_size` | Planner cache hint, does not allocate RAM |
| `random_page_cost` | Random I/O cost weight |
| `seq_page_cost` | Sequential I/O cost weight |
| `max_parallel_workers_per_gather` | Parallelism ceiling per gather node |
| `jit` | JIT compilation overhead vs. benefit |
| `plan_cache_mode` | Generic vs. custom prepared plan preference |
| Autovacuum settings | MVCC cleanup and statistics freshness |

Inspect values and configuration sources:

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'work_mem',
    'shared_buffers',
    'effective_cache_size',
    'random_page_cost',
    'seq_page_cost',
    'max_parallel_workers_per_gather',
    'jit',
    'plan_cache_mode'
)
ORDER BY name;
~~~

`pending_restart` flags changes not yet active until a server restart—preventing false conclusions when a test runs under old values.

## 24. Scoped Experimentation with `SET LOCAL`

In the lab database:

~~~sql
BEGIN;

SET LOCAL work_mem = '32MB';

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT tenant_id, state, COUNT(*)
FROM perf_lab.events
GROUP BY tenant_id, state
ORDER BY COUNT(*) DESC;

ROLLBACK;
~~~

`SET LOCAL` applies only inside the current transaction, isolating experiments without polluting pooled sessions afterward.

### 24.1. Not All GUCs Support `SET LOCAL`

Some GUCs require config file changes, superuser privileges, or restarts. Never assume `shared_buffers` took effect after a rejected `SET LOCAL`.

### 24.2. Raising `work_mem` Does Not Always Improve Workloads

A query can run multiple sort/hash operators, and concurrent queries plus parallel workers multiply memory demand. Large `work_mem` may speed one query while triggering RAM pressure or OOM under load.

Test both **single-query latency** and **multi-client concurrency**.

## 25. Testing Cost Parameters Safely

~~~sql
BEGIN;

SET LOCAL random_page_cost = 1.5;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT event_id, occurred_at, amount
FROM perf_lab.events
WHERE tenant_id = 1
  AND state = 'failed'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 50;

ROLLBACK;
~~~

If the plan flips to an Index Scan, the cost model is sensitive to that parameter. Still compare **actual times, buffers, and full workloads** before rolling it out.

Never disable `enable_seqscan` or force Nested Loops globally merely to make one plan look prettier.

## 26. Prepared Statements: Generic vs. Custom Plans

Parameterized query:

~~~sql
PREPARE event_lookup(integer, text) AS
SELECT event_id, occurred_at, amount
FROM perf_lab.events
WHERE tenant_id = $1
  AND state = $2
ORDER BY occurred_at DESC, event_id DESC
LIMIT 50;
~~~

Under `plan_cache_mode=auto`, PostgreSQL can pick parameter-specific **custom plans** or a reusable **generic plan**. Under heavy tenant skew, one generic plan may perform poorly for certain tenants.

Compare using the same prepared statement:

~~~sql
SET plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE event_lookup(1, 'failed');

SET plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE event_lookup(1, 'failed');

RESET plan_cache_mode;

DEALLOCATE event_lookup;
~~~

### 26.1. Literal `EXPLAIN` May Not Represent JDBC Traffic

~~~sql
WHERE tenant_id = 1 AND state = 'failed'
~~~

gives the planner literal constants at plan time, whereas a generic plan with `$1`/`$2` lacks concrete runtime values.

If regressions appear only after repeated API calls, verify using `EXPLAIN EXECUTE` and check connection/driver/pool behavior. Never claim PostgreSQL “always switches to generic after 5 runs”; it evaluates cost heuristics dynamically.

## 27. Tracking Cumulative SQL Metrics with `pg_stat_statements`

When installed and loaded appropriately, `pg_stat_statements` aggregates normalized SQL statistics.

Enabling it can require `shared_preload_libraries` and a restart; never alter production config casually just to test an example.

~~~sql
-- Only in an environment already configured for it:
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

Query it:

~~~sql
SELECT
    queryid,
    calls,
    rows,
    ROUND(total_exec_time::NUMERIC, 2) AS total_exec_ms,
    ROUND(mean_exec_time::NUMERIC, 3) AS mean_exec_ms,
    ROUND(stddev_exec_time::NUMERIC, 3) AS stddev_exec_ms,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_read,
    temp_blks_written
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

### 27.1. Calls vs. Total Time

A query taking 5 seconds once vs. one running 100,000 times at 5 ms consume vastly different total system resources.

`calls`, `mean_exec_time`, and `total_exec_time` help prioritize by total impact vs. single-execution latency.

### 27.2. `pg_stat_statements` Is Cumulative

To measure an interval `t1 → t2`, capture two snapshots and compute deltas:

\[
\mathrm{calls}_{interval}=\mathrm{calls}_{t2}-\mathrm{calls}_{t1}
\]

\[
\mathrm{mean}_{interval}=
\frac{\mathrm{totalExec}_{t2}-\mathrm{totalExec}_{t1}}
{\mathrm{calls}_{t2}-\mathrm{calls}_{t1}}
\]

when call delta is positive and no reset occurred. Never subtract cumulative `mean_exec_time` at `t2` minus `t1`.

### 27.3. View Limitations

- Does not store raw samples needed for exact **p95/p99** from mean/stddev alone.
- `queryid` is not guaranteed stable across major upgrades or schema changes.
- Counters can be reset or evicted.
- `pg_stat_statements.track_planning` may be off, leaving planning metrics incomplete.
- Normalized SQL hides latency differences across distinct parameter cohorts.

To capture p99 and parameter skew, pair with application tracing or load-test histograms.

## 28. Checking Database-Level Statistics

~~~sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    temp_files,
    temp_bytes,
    deadlocks,
    blk_read_time,
    blk_write_time
FROM pg_stat_database
WHERE datname = current_database();
~~~

You can take before/after snapshots and compute deltas, keeping in mind these cover **the entire database**, not one isolated benchmark query.

### 28.1. `track_io_timing`

`blk_read_time` and `blk_write_time` record real durations only when I/O timing tracking is enabled.

Check:

~~~sql
SHOW track_io_timing;
~~~

Never conclude I/O takes 0 ms if tracking is simply turned off.

### 28.2. `pg_stat_io` in PostgreSQL 16+

On supported versions:

~~~sql
SELECT
    backend_type,
    object,
    context,
    SUM(reads) AS reads,
    SUM(hits) AS hits,
    SUM(writes) AS writes
FROM pg_stat_io
GROUP BY backend_type, object, context
ORDER BY backend_type, object, context;
~~~

This breaks down I/O by backend, object, and context, though it does not replace `EXPLAIN BUFFERS` for debugging one query.

## 29. Lock Waits Mistaken for Plan Regressions

A query with an identical fast plan still stalls from the client's perspective if blocked on a lock.

~~~sql
SELECT
    pid,
    usename,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    left(query, 160) AS query_excerpt
FROM pg_stat_activity
WHERE datname = current_database()
  AND state <> 'idle'
ORDER BY query_start;
~~~

If `wait_event_type='Lock'`, investigate blocking sessions, open transactions, and competing DDL/DML.

**Plan regression:** worse scan/join path, cardinality, I/O, or CPU plan cost.

**Lock regression:** requests waiting longer on other transactions despite an unchanged plan.

Never add indexes trying to cure lock waits caused by migrations or long-running transactions.

## 30. Measuring WAL and DML Overhead After Index Changes

For write statements, `EXPLAIN` supports the `WAL` option on modern PostgreSQL versions:

~~~sql
-- Run only in the lab database:
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE perf_lab.events
SET amount = amount + 1
WHERE event_id BETWEEN 1 AND 100;

ROLLBACK;
~~~

**The statement really performs the `UPDATE`** prior to rollback. Rollback reverts database state, yet:

- Generated WAL and I/O still happened.
- External side effects from triggers may not roll back.
- Sequence increments in other examples do not roll back.
- Never treat this pattern as a zero-impact production benchmark trick.

Measure WAL bytes, runtime, affected rows, and write TPS across **identical DML row counts** for a fair comparison.

## 31. Running Custom Read Workloads with `pgbench`

`pgbench` runs custom SQL script files. On the benchmark client, create `queries.sql`:

~~~text
\set tenant_id random(1, 51)

SELECT event_id, occurred_at, amount
FROM perf_lab.events
WHERE tenant_id = :tenant_id
ORDER BY occurred_at DESC, event_id DESC
LIMIT 20;
~~~

Run against the **lab database**:

~~~bash
pgbench -n -M prepared -c 8 -j 2 -T 120 -P 10 -r \
  -f queries.sql postgres_lab
~~~

Flags:

- `-n`: skips `pgbench`'s default vacuum step for custom runs.
- `-M prepared`: uses extended prepared protocol.
- `-c 8`: 8 concurrent clients.
- `-j 2`: 2 worker threads.
- `-T 120`: run for 120 seconds.
- `-P 10`: print progress every 10 seconds.
- `-r`: report per-statement latencies.
- `-f`: custom script path.
- `postgres_lab`: sample database name.

### 31.1. Warning on Parameter Mix

`random(1,51)` draws tenants almost uniformly, whereas our dataset puts 75% of rows in tenant 1. If production sends 70% of traffic to tenant 1, a uniform draw misrepresents workload behavior.

Model parameter distributions after real traffic or test large and small tenants separately.

### 31.2. Never Generate Uncontrolled Load on Production

Even read-only `SELECT` loops from multiple clients consume CPU/I/O, evict caches, and threaten SLOs. Run against equivalent test/staging environments or tightly approved, controlled production tests.

## 32. Reading `pgbench`: Throughput and Latency

`pgbench` reports output such as:

~~~text
number of transactions actually processed: ...
latency average = ... ms
tps = ... (without initial connection time)
~~~

Inspect together:

- TPS.
- Average latency.
- Client concurrency.
- Failed/errored transactions.
- Test duration.
- Per-command latencies.
- Server CPU, I/O, and locks.

For exact p95/p99 percentiles, use a load generator with histograms or log per-transaction latencies cleanly; do not assume `pgbench` prints full p99 percentiles out of the box in all modes.

### 32.1. Sweeping Concurrency Levels

| Clients | TPS | p95 | Error Rate |
|---:|---:|---:|---:|
| 1 | measure | measure | measure |
| 8 | measure | measure | measure |
| 16 | measure | measure | measure |
| 32 | measure | measure | measure |
| 64 | measure | measure | measure |

Compare baseline vs. candidate **at the same concurrency level**. Never compare 64-client TPS directly against 8-client TPS to claim one setting is superior.

## 33. Repeating Runs and Analyzing Noise

Suppose 5 baseline trials show p95:

~~~text
101, 103, 99, 100, 102 ms
~~~

Candidate:

~~~text
128, 130, 127, 133, 129 ms
~~~

Here separation is clear. Yet if candidate produces:

~~~text
98, 115, 101, 109, 103 ms
~~~

noise overlaps heavily with baseline; collect more samples and inspect environmental interference.

Sound practices:

- Separate warm-up phase.
- Run multiple sufficiently long trials.
- Alternate A/B run order when feasible.
- Record background load.
- Evaluate percentiles and full distributions.
- Consider bootstrap confidence intervals or appropriate statistical checks.
- Slice metrics by parameter cohort, not just global averages.

**Statistical significance** differs from **practical impact**. A +0.1 ms shift may be detectable yet trivial; +40 ms on a critical path demands action.

## 34. Regression Thresholds and Gates

Example policy rules:

| Level | Illustrative Rule | Action |
|---|---|---|
| Pass | Variance within historical noise band | Record |
| Warning | p95 up >10% and >5 ms | Re-run, inspect plans |
| Block | p95 up >20% and >20 ms on critical query | Investigate before deploy |
| Correctness fail | Output or row mismatch | Block deployment |
| Resource fail | CPU/WAL/IO exceeds budget at equal load | Investigate capacity |

These are **not official PostgreSQL standards**. Thresholds depend on SLOs, criticality, current headroom, and test stability.

### 34.1. Never Ignore Rare Errors

A p99 spike can reflect noise or a real edge-case failure. Gates should encourage reproduction and never overlook rising error/timeout rates simply because not every run hits them.

## 35. CI/CD Regression Pipelines

A structured pipeline flow:

~~~text
Commit / migration
       |
       v
Provision test DB on matching hardware class
       |
       v
Restore representative data snapshot
       |
       v
Run baseline revision or fetch comparable baseline
       |
       v
Apply candidate change
       |
       v
Run ANALYZE under fixed policy
       |
       v
Warm-up
       |
       v
Microbenchmark + workload benchmark
       |
       v
Archive EXPLAIN JSON, latency samples, resource metrics
       |
       v
Compare p50/p95/p99, TPS, buffers, CPU, WAL, errors
       |
       v
PASS / WARN / BLOCK
~~~

### 35.1. Yesterday's Baseline May Not Be Comparable

If yesterday's run used different hardware, a different snapshot, or different cache warmth, comparing today's candidate against it invites false alarms.

Whenever possible, run baseline and candidate revisions **in the same test environment on the same snapshot**, or on identical cloned environments for irreversible migrations.

## 36. Archiving Artifacts for Reproducibility

Suggested artifact bundle:

~~~text
perf-report/
  metadata.txt
  postgres-version.txt
  settings.txt
  schema-revision.txt
  dataset-summary.txt
  query-templates.sql
  parameter-groups.txt
  explain-before.json
  explain-after.json
  latency-before.csv
  latency-after.csv
  pgbench-before.txt
  pgbench-after.txt
  metrics-before.csv
  metrics-after.csv
  conclusions.md
~~~

This is a **recommended layout**, not files generated by the lab SQL.

`metadata.txt` should record timestamps, commits/migrations, PostgreSQL/driver versions, hardware class, concurrency, warm-up rules, cache policy, and query mix.

You do not need raw PII to prove a regression—use synthetic or properly anonymized snapshots.

## 37. Case Study A: New Index Speeds `SELECT` Yet Cuts Write TPS

Suppose you add:

~~~sql
CREATE INDEX idx_orders_customer_created
ON orders(customer_id, created_at DESC);
~~~

Afterward:

- The order-list endpoint speeds up.
- `INSERT` TPS drops.
- Write p95 rises.
- WAL volume climbs.
- Index storage grows.
- Autovacuum/index maintenance overhead increases.

How to analyze:

1. Confirm `SELECT` actually uses the new index.
2. Compare `actual rows`, buffers, and latency on `SELECT`.
3. Measure `INSERT`/`UPDATE` at matching concurrency.
4. Record WAL bytes, index size, CPU, and I/O.
5. Factor in real read/write mix.
6. Check whether the new index duplicates or overlaps an existing index.
7. Weigh net SLO impact overall.

Never conclude “this index made `SELECT` 80% faster so it must stay” without checking write costs.

## 38. Case Study B: Data Load Triggers a Switch to `Seq Scan`

Before ETL:

~~~text
2 million rows
state='failed': 0.1%
Query uses Index Scan
~~~

After ETL:

~~~text
20 million rows
state='failed': 60%
Query switches to Seq Scan
~~~

This is not automatically a planner bug. If `WHERE` matches 60% of the table, `Seq Scan` can beat random index lookups.

Check:

- How many rows does the query return post-ETL?
- Are statistics current?
- Which is genuinely faster—`Seq Scan` or `Index Scan`?
- Does the query use selective `LIMIT`/`ORDER BY`?
- Would another index or status-partitioned query make more sense?
- Do SLOs account for data growth?

Never force `enable_seqscan=off` merely to cling to the old plan.

## 39. Case Study C: Raising `work_mem` Hurts Overall Concurrency

Bumping `work_mem` can stop one sort from spilling. Under high concurrency, however, aggregate memory consumption surges.

Possible symptoms:

- Rising p95/p99 latencies.
- OS swapping or OOM kills.
- Falling throughput.
- Lower `temp_bytes` paired with worse CPU wait / memory pressure.

Lesson: cutting temp I/O is not a victory if host stability suffers. Test both single-query behavior and concurrent load.

## 40. Case Study D: JDBC Prepared Query Slows Down Over Time

An application runs:

~~~sql
WHERE tenant_id = $1
~~~

After repeated executions, PostgreSQL considers a generic plan. Heavy tenant skew can make that generic plan poor for small tenants.

Diagnose:

~~~sql
PREPARE tenant_lookup(integer) AS
SELECT event_id, occurred_at, amount
FROM perf_lab.events
WHERE tenant_id = $1
ORDER BY occurred_at DESC, event_id DESC
LIMIT 50;

SET plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE tenant_lookup(2);

SET plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE tenant_lookup(2);

RESET plan_cache_mode;
DEALLOCATE tenant_lookup;
~~~

Distinguish pgJDBC's `prepareThreshold` from PostgreSQL's server-side generic/custom plan selection. Do not assume PostgreSQL switches blindly on call 6; it compares estimated costs.

If custom wins cleanly:

- Inspect statistics.
- Review index choices.
- Inspect query mix and parameter skew.
- Consider scoped `plan_cache_mode` or separate query templates.
- Measure planning CPU vs. total latency before deciding.

## 41. Case Study E: PostgreSQL Major Upgrade

A major upgrade can alter:

- Planner cost model and plan strategies.
- Cardinality estimation logic.
- Partition pruning, parallelism, and JIT.
- Index/access method internals.
- Statistics views and metrics formats.
- Driver and connection-pool compatibility.

Recommended workflow:

1. Clone a representative snapshot.
2. Run the baseline on the old version.
3. Provision the new version on matching hardware.
4. Restore/upgrade data cleanly.
5. Refresh statistics appropriately.
6. Replay the query mix and parameter cohorts.
7. Compare correctness, plan shapes, latencies, and resource metrics.
8. Investigate per-query regressions.
9. Prepare rollback/cutover plans.
10. Monitor closely post-upgrade.

`queryid` and plan output fields are not guaranteed identical across major versions; correlate by SQL/endpoint mapping and observed metrics.

## 42. Faster Query, Wrong Result

Example:

~~~sql
SELECT event_id, amount
FROM perf_lab.events
LIMIT 50;
~~~

Without `ORDER BY`, PostgreSQL **does not guarantee the same 50 rows** across plan changes or new indexes.

If business logic expects deterministic top rows, specify:

~~~sql
SELECT event_id, amount
FROM perf_lab.events
ORDER BY event_id
LIMIT 50;
~~~

When validating correctness, never check only row count—verify key sets, ordering, and business values. A faster query returning missing or wrong data is never an optimization.

## 43. Watching Autovacuum and the Visibility Map

An Index-Only Scan can incur surging `Heap Fetches` after updates even with unchanged SQL and indexes because modified pages lose their all-visible bits.

Meanwhile:

- Dead tuples accumulate.
- Long transactions block `VACUUM` cleanup.
- Statistics go stale.
- Heap/index bloat grows.

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze,
    n_tup_ins,
    n_tup_upd,
    n_tup_del
FROM pg_stat_user_tables
WHERE schemaname = 'perf_lab'
  AND relname = 'events';
~~~

`n_dead_tup` is an **estimate**, not an exact `COUNT(*)`.

If `VACUUM (ANALYZE)` ran only before the candidate benchmark, index-only scans can improve simply from cleaner visibility maps. Record maintenance actions between runs.

## 44. Investigation Checklists by Change Type

### 44.1. Schema

- Which indexes, constraints, or partitions changed?
- Which nodes changed between before/after plans?
- Are new indexes valid and usable?
- Did WAL volume, locks, or DML costs climb?
- Did migration block concurrent writes?
- Do new indexes overlap existing ones?

### 44.2. Data

- How much did rows/bytes grow?
- Did distributions, MCVs, or tenant skew shift?
- Did `ANALYZE` refresh statistics?
- Did dead tuples or bloat increase?
- Does the query emit more rows now?
- Did the query slow from larger result volume or a worse plan?

### 44.3. Configuration

- Which GUCs actually changed and took effect?
- Did a server restart clear warm caches?
- How did parallelism, JIT, or `work_mem` change?
- Is RAM/CPU/I/O saturating under concurrency?
- Did global settings impact unrelated queries?
- Is there a clean rollback path?

## 45. Common Misconceptions

### Misconception 1 — `EXPLAIN` cost is milliseconds

False. Cost is a relative planner unit; measure actual execution time.

### Misconception 2 — `EXPLAIN ANALYZE` only estimates

False. It **executes** the statement.

### Misconception 3 — `shared read` always means physical disk I/O

Not necessarily; the OS page cache can satisfy reads from RAM.

### Misconception 4 — One slower run proves a regression

False. Caches, background load, locks, and stats introduce noise.

### Misconception 5 — If mean latency is flat, users are fine

False. p95/p99 latencies and timeouts can degrade severely.

### Misconception 6 — Adding an index helps with zero downside

False. Indexes increase storage, DML latency, WAL, and maintenance cost.

### Misconception 7 — `ANALYZE` never alters plans

False. Fresh statistics can lead the planner to choose a different strategy.

### Misconception 8 — Slower speed when returning more rows is an optimizer bug

Not necessarily; it can simply reflect a larger workload.

### Misconception 9 — `pg_stat_statements` gives exact p99

You cannot compute true p99 accurately from aggregate mean/stddev alone; use histograms or samples.

### Misconception 10 — `queryid` stays identical across every migration and upgrade

Never rely on that assumption.

### Misconception 11 — A 1-client benchmark predicts 100-client throughput

False. Concurrency introduces contention and memory pressure.

### Misconception 12 — Setting huge `work_mem` is always faster

False. Concurrent operators and queries can exhaust server memory.

### Misconception 13 — Running `VACUUM` only on the candidate does not skew results

False. Visibility maps and dead-tuple cleanup directly impact index-only scans.

### Misconception 14 — Identical plans guarantee identical latency

False. Cache warmth, I/O load, locks, and runtime parameters still vary.

### Misconception 15 — A plan change always indicates a regression

False. The planner may switch to a better plan as data evolves.

### Misconception 16 — Restarting the app fixes generic plan regressions

That may only clear prepared caches briefly; the root cause stays.

### Misconception 17 — Higher throughput is always better

Not if tail latency, error rate, or resource consumption worsens unacceptably.

### Misconception 18 — A faster query returning different rows is acceptable

Never, unless the semantic change was deliberate and verified.

### Misconception 19 — DML `EXPLAIN ANALYZE` inside a transaction is always harmless

Rollback does not undo WAL generation, locks, or external trigger side effects.

### Misconception 20 — A GUC that helps one query should be set cluster-wide

It can harm other workloads; scope changes carefully.

## 46. End-to-End Regression Measurement Workflow

**Step 1 — Define the change.** Record migration, config, or data snapshot details, goals, and scope.

**Step 2 — Specify queries and workload.** Include SQL templates, parameter mix, concurrency, and correctness checks.

**Step 3 — Capture baseline.** Use matching hardware/dataset and document version and GUCs.

**Step 4 — Warm up.** Run an explicit warm-up phase and record cache policy.

**Step 5 — Measure baseline across iterations.** Capture latency samples/histograms, TPS, error rates, buffers, and JSON plans.

**Step 6 — Apply candidate.** Isolate one change group when possible; log every migration, `VACUUM`, and `ANALYZE`.

**Step 7 — Verify correctness.** Validate key sets, row counts, ordering, and business constraints.

**Step 8 — Measure candidate identically.** Keep parameters, duration, arrival rates, concurrency, and warm-up matched.

**Step 9 — Analyze plan drift.** Compare scan/join/sort nodes, estimates, actual rows, loops, and buffers.

**Step 10 — Analyze resources.** Inspect CPU, I/O, WAL, memory, temp spills, locks, and errors.

**Step 11 — Verify reproducibility.** Repeat runs or execute A/B/A testing when possible.

**Step 12 — Evaluate thresholds.** Check absolute and relative deltas against noise and SLOs.

**Step 13 — Decide.** Mark PASS, WARN, BLOCK, or roll back / tune further.

**Step 14 — Archive artifacts.** Store baseline, candidate, SQL, plans, stats, and conclusions.

**Step 15 — Monitor post-deployment.** Real production workloads differ from staging; track regressions and maintain rollback readiness.

## 47. Practice Exercises

### Exercise 1 — Relative Regression

Baseline p95 is 100 ms; candidate p95 is 130 ms. What is the percentage increase?

**Hint:** 30%.

### Exercise 2 — Throughput

TPS drops from 2000 to 1800. What is the percentage change?

**Hint:** -10%.

### Exercise 3 — Latency Metrics

Mean latency stays flat, yet users report sporadic slow requests. What should you inspect?

**Hint:** p95/p99 latency, timeouts, wait events.

### Exercise 4 — `EXPLAIN` Cost

Does `cost=1000` mean 1000 ms?

**Hint:** No.

### Exercise 5 — `EXPLAIN ANALYZE`

Why shouldn't you run it casually on production `UPDATE`/`DELETE` statements?

**Hint:** It actually executes the DML statement.

### Exercise 6 — Shared Buffers

Is `shared read` always a physical disk read?

**Hint:** No; the OS page cache can serve it.

### Exercise 7 — JSON Plans

Why is saving `EXPLAIN FORMAT JSON` better than screenshots for automated comparison?

**Hint:** Machine-readable structure enabling automated node/row/buffer diffs.

### Exercise 8 — Query After Adding Index

Which query in the lab can benefit from `(tenant_id, state, occurred_at DESC, event_id DESC) INCLUDE(amount)`?

**Hint:** Queries fetching failed events by tenant ordered newest-first.

### Exercise 9 — Index Overhead

List three costs that can increase after adding an index.

**Hint:** WAL volume, DML write latency, storage/maintenance overhead.

### Exercise 10 — Data Growth

A table grows 10x and a query gets 3x slower. Is that definitely a planner regression?

**Hint:** Not necessarily; check the scale effect.

### Exercise 11 — `pg_stats`

Write SQL retrieving `most_common_vals` and `most_common_freqs` for `state`.

**Hint:** Query `pg_stats` filtering schema, table, and `attname`.

### Exercise 12 — `ANALYZE`

Why should you log whenever `ANALYZE` runs between benchmark phases?

**Hint:** Updated statistics can cause plans to change.

### Exercise 13 — Parameter Skew

Why test both tenant 1 and small tenants?

**Hint:** Row counts differ dramatically, yielding different plans and latencies.

### Exercise 14 — `pg_stat_statements`

If `calls` rises from 1000 to 1600 with no stats reset, how many calls occurred in the interval?

**Hint:** 600.

### Exercise 15 — Interval Mean

`total_exec_time` increases by 3000 ms while `calls` increases by 600. What is the interval mean?

**Hint:** 5 ms.

### Exercise 16 — Tail Latency

Can you compute exact p99 from `mean_exec_time` and `stddev_exec_time` alone?

**Hint:** No.

### Exercise 17 — `queryid`

Is relying solely on `queryid` as a permanent identifier across major upgrades safe?

**Hint:** No; map via SQL templates and endpoints too.

### Exercise 18 — `pending_restart`

What does `pg_settings.pending_restart=true` indicate?

**Hint:** The setting change awaits a server restart to take effect.

### Exercise 19 — `work_mem`

Why can a large `work_mem` speed up one query while hurting 100 concurrent sessions?

**Hint:** Memory usage multiplies across operators, concurrent sessions, and workers.

### Exercise 20 — WAL

Which metrics evaluate write cost after adding a new index?

**Hint:** DML TPS/latency, WAL volume, and index size.

### Exercise 21 — `pg_stat_database`

Can database-wide `blks_read` isolate which single query started reading more blocks?

**Hint:** No; it aggregates across all workloads.

### Exercise 22 — `pgbench`

Can you compare 8-client baseline TPS directly with 64-client candidate TPS?

**Hint:** No; concurrency levels are unequal.

### Exercise 23 — Generic vs. Custom Plans

A prepared query runs slow while literal values run fast. How do you test it?

**Hint:** Run `EXPLAIN EXECUTE` under `force_generic_plan` and `force_custom_plan`.

### Exercise 24 — Sort Spill

`EXPLAIN` shows `Sort Method: external merge Disk`. What does that point to?

**Hint:** Sorting spilled to temporary files; inspect row volume and `work_mem`.

### Exercise 25 — Parallelism

Why might adding parallel workers speed up a lone query without increasing TPS under heavy concurrency?

**Hint:** CPU/worker contention and coordination overhead.

### Exercise 26 — Lock Waits

Plan and buffers look identical, yet an endpoint slows down waiting on locks. Is this primarily a plan regression?

**Hint:** No; investigate blocking transactions/locks.

### Exercise 27 — Caching

The candidate always runs right after the baseline. What is the risk?

**Hint:** Warm caches bias results in favor of the candidate.

### Exercise 28 — Result Correctness

Two queries both return 50 rows, yet with different primary-key sets. Is comparing their timings valid?

**Hint:** First validate semantic equivalence and ordering.

### Exercise 29 — CI Gate

Why shouldn't a CI gate BLOCK deployment simply because one run was 2 ms slower?

**Hint:** Noise variance, absolute/relative thresholds, and reproducibility matter.

### Exercise 30 — Mixed Workload

An index speeds up `SELECT` while cutting `INSERT` TPS. What evidence decides whether to keep the index?

**Hint:** Read/write query mix, SLOs, WAL/I/O/CPU cost, DML p95, and `SELECT` benefit.

## 48. Frequently Asked Questions

### Does a new index always improve performance?

No. It can speed up specific `SELECT`s while increasing write overhead, WAL, and storage—and the planner is not forced to use it.

### Should you run `VACUUM`/`ANALYZE` before every benchmark?

Running `ANALYZE` for representative stats is often reasonable, provided **both baseline and candidate use the same policy**. `VACUUM` also alters visibility maps and cleans dead tuples. Never run maintenance solely on the candidate and credit the speedup to schema changes.

### Is `EXPLAIN` without `ANALYZE` enough to verify latency?

No. It shows estimated plan cost; you must run controlled benchmarks to observe real runtime.

### Can you derive p99 from `pg_stat_statements`?

Not accurately from totals, means, and standard deviations alone. Collect request samples or histograms from client/tracing telemetry.

### If one query improves after a GUC change, should we apply it cluster-wide?

Not without broader testing. Evaluate other queries, concurrency, CPU/memory/I/O budgets, and rollback procedures.

### Can you compare baselines across two machines with different hardware?

Only as a rough trend, never as an exact apples-to-apples benchmark. Normalize hardware or record differences explicitly and run baseline/candidate on matched hardware whenever possible.

### What if production data cannot be copied directly?

Generate synthetic datasets matching scale and skew or use controlled anonymized snapshots. Document every gap explicitly instead of claiming synthetic tests mirror production perfectly.

### If a query is slow on its first run after deploy, is it definitely a regression?

No. Cold caches, JIT warmup, prepared-statement warmup, background jobs, or plan invalidation all affect initial runs. Measure both cold-start and steady-state behavior when SLOs care about both.

## 49. Summary

- **Performance regressions** must be measured against a **comparable baseline and workload**, not guessed from one slow run.
- Changes to **schema, data, configuration, or PostgreSQL version** can shift execution plans and resource usage even when SQL stays identical.
- Track **p50/p95/p99, throughput, error rates, planning/execution times, buffers, CPU/IO/WAL, memory, and lock waits** where appropriate.
- `EXPLAIN` shows the plan and estimates; `EXPLAIN ANALYZE` runs it to report actual rows and timings; `BUFFERS` reveals page access volume.
- **Planner cost is not milliseconds**, and `shared read` is not guaranteed physical disk I/O.
- `pg_stat_statements` provides **cumulative** SQL stats; compute interval metrics using **deltas**, never raw cumulative differences on averages.
- Exact p99 cannot be computed from aggregate mean/stddev; use real samples or histograms.
- `pg_stats`, `ANALYZE`, and extended statistics explain **data skew/cardinality** and plan shifts.
- New indexes can help `SELECT` yet add DML/WAL/storage overhead; always benchmark a **mixed workload**.
- GUCs like `work_mem`, `random_page_cost`, or parallelism must be scoped tightly and tested under realistic concurrency.
- Caching, autovacuum, checkpoints, long transactions, and replication add noise—document full test context.
- For JDBC/prepared statements, **generic vs. custom plans** and parameter skew vary latency; inspect `EXPLAIN EXECUTE` carefully.
- `pgbench` helps replay workloads, provided **parameter mix mirrors production** and tests never hammer production uncontrollably.
- CI pipelines can archive **EXPLAIN JSON, latency samples, query mappings, and resource metrics**, evaluating PASS/WARN/BLOCK gates against defined thresholds.
- **Correctness is non-negotiable:** a faster query returning wrong or incomplete data is never an optimization.
- `EXPLAIN ANALYZE` on DML genuinely modifies rows; rollback does not erase WAL or external side effects.

The core principle is: **“Measure the exact same question under controlled conditions, then explain every difference using observable plans and metrics.”** With baselines, parameter cohorts, noise controls, and execution artifacts recorded systematically, catching PostgreSQL regressions after migrations or tuning becomes a **repeatable, data-driven practice**.
