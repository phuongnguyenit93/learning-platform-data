# Query Testing with Skewed Data and Representative Volumes

A query that runs fast on a few thousand rows is not guaranteed to perform well when a table holds tens of millions of rows with uneven data distribution. In PostgreSQL, the query planner relies on statistics to estimate row counts and choose table access methods, join order, join algorithms, sorting strategies, and parallelism. If test data is too small, overly uniform, or lacks realistic correlations, query plans can diverge sharply from production.

Meaningful performance testing must reproduce **data volume**, **distribution shape**, **query patterns**, **input parameters**, and **concurrency levels**. The goal is not to chase a pretty single-run timing number, but to determine whether queries meet requirements as data and load grow, and to understand why performance degrades when it does.

## 1. Why Must Test Data Be Representative?

Suppose an application manages orders by tenant. A few large tenants generate most of the orders, while hundreds of other tenants have only a few thousand records each. Status `paid` is far more common than `refunded`, and most orders fall within the most recent few weeks.

The following query might power a tenant dashboard:

```sql
SELECT
    id,
    created_at,
    total_amount
FROM sales.orders
WHERE tenant_id = $1
  AND status = 'paid'
  AND created_at >= now() - interval '30 days'
ORDER BY created_at DESC
LIMIT 100;
```

If a test dataset distributes orders evenly across every tenant, every status, and every date, the query is tested under far more predictable conditions than production. In reality, a large tenant might match millions of rows if the time filter is omitted; a small tenant has only a few dozen rows. The condition `status = 'paid'` can also be very common for one tenant yet rare for another.

Those differences impact:

- Row counts estimated by the planner for each filter predicate.
- Whether an index is chosen over a sequential scan.
- Join ordering and choices among nested loop, hash join, or merge join.
- Hash table size, sort size, and disk spill risk.
- Number of blocks read, cache hit ratio, and actual I/O volume.
- Latency of common parameters compared to rare parameters.
- CPU, memory, WAL, and lock contention when multiple sessions run concurrently.

Therefore, a strong test dataset must preserve the characteristics that shape query behavior, rather than merely matching production's total row count.

## 2. Understanding Forms of Data Skew

### Value frequency skew

A column can contain a few very frequent values alongside many rare values. For example, 70% of orders belong to tenant `1`, while the remaining 30% scatter across 999 tenants. Similarly, status `paid` might make up 80%, while `pending`, `cancelled`, and `refunded` account for small shares.

This is value skew. If tests only pick tenants uniformly at random, they will likely miss the hot tenant and the long tail of small tenants.

### Temporal skew

Transactional systems typically exhibit temporal locality. Recent data is accessed far more often than older data; promotional campaigns create write spikes; monthly data can surge at period end. A table with 500 million historical rows where most queries read only the last 7 days behaves differently from one whose rows are spread uniformly over years.

### Cross-column correlation

Columns are not always independent. For example:

- Large tenants have a higher proportion of `paid` orders than small tenants.
- Newer orders have a higher probability of `pending` than older orders.
- A region carries only a specific subset of products.
- `country_code` and `currency_code` have a nearly functional dependency.

If the planner assumes predicates are independent when they are strongly correlated, combined selectivity estimates can be far off. That skews join choices and access paths.

### Row width and data size skew

Two tables with identical row counts can have vastly different physical sizes. A table with a few narrow integer columns differs from one packed with large `text`, `jsonb`, `bytea`, arrays, or TOASTed values. Heap size, index size, blocks read, and memory consumption all change.

### Key skew and duplicate distribution

Unique keys have high selectivity, whereas status codes or event types have few distinct values. If test data lacks realistic duplication rates, planners and indexes are evaluated under false assumptions.

## 3. Identifying What Data Is Representative

Before generating data, identify the properties that queries actually rely on. You do not need to copy every column if it does not affect access paths, joins, row width, or filter predicates. However, never omit properties that influence execution plans.

A data profile should capture:

| Property | Question to answer | Measurement method or source |
|---|---|---|
| Volume | How many rows are in each table? | `count(*)`, catalogs, and operational metrics |
| Physical size | How much space do heap and indexes take? | `pg_total_relation_size`, `pg_relation_size` |
| Cardinality | How many distinct values does each column have? | `count(DISTINCT ...)`, `pg_stats.n_distinct` |
| Frequency | What percentage does the most common value hold? | `GROUP BY`, `pg_stats.most_common_freqs` |
| Nulls | What is the `NULL` fraction? | `count(*) FILTER (WHERE col IS NULL)` |
| Correlation | Are columns dependent or co-occurring? | Grouped multi-column queries, extended statistics |
| Time | Which periods concentrate the data? | Daily/monthly histograms and real queries |
| Relationships | Valid foreign-key ratio and child rows per parent? | Joins, key cardinality distributions |
| Width | Typical lengths of text/JSON values? | `avg(octet_length(...))`, percentiles |
| Access | Which parameters occur most often and how frequently? | Query logs, `pg_stat_statements`, app traces |

Collect profiles at multiple times—such as an ordinary day, peak day, and period close. A single snapshot can miss seasonal surges or historical data purged by retention policies.

## 4. Data Scale and Physical Size

### Choosing test tiers

Instead of building only one dataset, test across multiple tiers:

1. **Small:** for query development, result verification, and catching logic bugs.
2. **Medium:** to observe trends as row and index sizes grow.
3. **Current target:** close to current production scale.
4. **Growth target:** simulates projected volume over a horizon such as 6 or 12 months.
5. **Peak load:** combines target data volume with peak concurrency and query rates.

Do not extrapolate large-scale runtimes by linearly scaling small-dataset runtimes by row count. Indexes, caches, joins, sorts, partitioning, checkpoints, and I/O behave nonlinearly.

### Measuring table and index sizes

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    pg_size_pretty(pg_relation_size(relid)) AS heap_size,
    pg_size_pretty(pg_indexes_size(relid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
```

`n_live_tup` and `n_dead_tup` are statistics estimates rather than exact point-in-time counts. The size functions report physical relation and index footprint. Use them to confirm whether the test dataset approximates the target physical size.

### Physical size matters too

The planner estimates costs from page counts, statistics, and cost parameters. A dataset with the same row count that fits far more easily in cache produces overly optimistic test results. Compare heap and index sizes against available memory, and check buffer hit/read ratios during workloads.

## 5. Generating Skewed Test Data

The example below creates an orders table with one very large tenant, frequent `paid` status, and recent timestamp concentration. Run it in a dedicated test database.

```sql
CREATE SCHEMA IF NOT EXISTS bench;

CREATE TABLE bench.orders (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL,
    total_amount numeric(12, 2) NOT NULL
);

SELECT setseed(0.42);

INSERT INTO bench.orders (
    tenant_id,
    status,
    created_at,
    total_amount
)
SELECT
    CASE
        WHEN random() < 0.70 THEN 1
        ELSE 2 + floor(random() * 999)::integer
    END,
    CASE
        WHEN random() < 0.80 THEN 'paid'
        ELSE (ARRAY['pending', 'cancelled', 'refunded'])[
            1 + floor(random() * 3)::integer
        ]
    END,
    CASE
        WHEN random() < 0.85
            THEN now() - random() * interval '14 days'
        ELSE now() - random() * interval '3 years'
    END,
    (10 + random() * 990)::numeric(12, 2)
FROM generate_series(1, 5000000);
```

With this generator, roughly 70% of rows belong to tenant `1`, roughly 80% have status `paid`, and most timestamps fall within the last 14 days. The remainder spreads out to form the tail and historical data. `setseed` seeds the session's PRNG for better repeatability across trial runs; if you need completely immutable fixtures across test runs, save a snapshot of the generated dataset and version the snapshot.

This is illustrative data. In real systems, tune ratios to measured metrics, add realistic correlations, and preserve foreign-key relationships. Generating each column independently as in this snippet does not yet model correlations across tenant, status, and time.

### Generating parent-child relationships

When testing joins, reproduce realistic child-per-parent row distributions. For instance, one major customer may have many orders while most customers have only a few. Creating exactly one order per customer can make nested loop joins look artificially better than reality.

```sql
CREATE TABLE bench.customers (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL,
    region_code text NOT NULL
);

INSERT INTO bench.customers (tenant_id, region_code)
SELECT
    CASE
        WHEN random() < 0.70 THEN 1
        ELSE 2 + floor(random() * 999)::integer
    END,
    (ARRAY['north', 'south', 'central', 'west'])[
        1 + floor(random() * 4)::integer
    ]
FROM generate_series(1, 500000);
```

To generate `orders` with valid relationships to `customers`, sample `customer_id` from existing keys or use a controlled mapping table. Never draw independent random numbers over an ID range if that can create invalid foreign keys.

### Generating correlated distributions

If tenant `1` has a higher payment rate than other tenants, encode that rule in the generator. Illustrative idea:

```sql
SELECT
    CASE WHEN random() < 0.70 THEN 1 ELSE 2 END AS tenant_id,
    CASE
        WHEN random() < 0.70 THEN 'paid'
        ELSE 'pending'
    END AS status;
```

The short query above only illustrates the intent and does not actually create correlation because the two `random()` calls are independent. To introduce real correlation, derive the tenant first and select the status probability conditioned on that tenant inside the same expression or controlled generation step. Example:

```sql
WITH generated AS (
    SELECT
        CASE WHEN random() < 0.70 THEN 1 ELSE 2 END AS tenant_id,
        random() AS status_roll
    FROM generate_series(1, 100000)
)
SELECT
    tenant_id,
    CASE
        WHEN tenant_id = 1 AND status_roll < 0.95 THEN 'paid'
        WHEN tenant_id <> 1 AND status_roll < 0.35 THEN 'paid'
        ELSE 'pending'
    END AS status
FROM generated;
```

Here, tenant `1` has a higher `paid` rate than tenant `2`. When turning this into an `INSERT`, extend the CTE to generate timestamps, customers, and remaining columns. Retain the seed, generation rules, and snapshot so subsequent tests compare equivalent data.

## 6. Building a Test Parameter Matrix

Do not test only the largest tenant or the rarest value. Select parameter groups representing how users and applications actually query the database.

| Data group | Example parameter | Purpose |
|---|---|---|
| Hot value | Tenant holding 70% of rows | Test queries returning large result sets |
| Cold value | Tenant with only a few hundred rows | Test highly selective queries |
| Median value | Tenant near the median | Test typical cases |
| Common enum value | `paid` | Test low-selectivity predicates |
| Rare value | `refunded` | Test high-selectivity predicates |
| Recent time window | 1 day, 7 days | Test hot data and temporal locality |
| Long time window | 1 year, full history | Test scans, partitions, and large aggregations |
| Correlated combination | Large tenant + `paid` | Test multi-column estimates |
| Rare combination | Small tenant + `refunded` | Test very low cardinality |

For each group, record actual rows, estimated rows, timing, buffers, and results. Parameters must come from real distributions or defined datasets rather than arbitrarily picking favorable values.

## 7. Updating Planner Statistics

PostgreSQL uses `ANALYZE` to gather statistics on data distribution. After loading or modifying many rows, run `ANALYZE` before measuring query plans:

```sql
ANALYZE bench.orders;
```

`VACUUM (ANALYZE)` can be appropriate after large loads or bulk updates/deletes in a test environment:

```sql
VACUUM (ANALYZE) bench.orders;
```

`VACUUM` cleans up dead tuples and updates the visibility map; `ANALYZE` updates planner statistics. They solve different problems. Do not use `VACUUM FULL` as a default prep step for every benchmark because it rewrites the table, acquires a heavy lock, and alters physical layout.

### Inspecting single-column statistics

```sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds,
    correlation
FROM pg_stats
WHERE schemaname = 'bench'
  AND tablename = 'orders'
  AND attname IN ('tenant_id', 'status', 'created_at');
```

Key fields:

- `null_frac`: estimated fraction of `NULL` values.
- `n_distinct`: estimated number of distinct values; negative values express a fraction of total rows.
- `most_common_vals` and `most_common_freqs`: most frequent values and their corresponding frequencies.
- `histogram_bounds`: histogram bucket boundaries for values not in the most-common list.
- `correlation`: correlation between the column's value order and the physical row order in the table, used to estimate index access cost. This is not a correlation between two columns.

### Increasing statistics targets when needed

By default, the planner samples a subset of rows. For heavily skewed columns or columns with many common values, the default sample may lack detail. You can raise the statistics target on key columns:

```sql
ALTER TABLE bench.orders
    ALTER COLUMN tenant_id SET STATISTICS 1000;

ALTER TABLE bench.orders
    ALTER COLUMN status SET STATISTICS 1000;

ANALYZE bench.orders;
```

Higher targets produce finer statistics at the cost of slower `ANALYZE` runs, higher resource usage, and larger statistics metadata. Raise targets only on columns that need them and compare before/after plans.

### Multi-column statistics

When the planner must estimate predicates over multiple correlated columns, create extended statistics:

```sql
CREATE STATISTICS bench.orders_tenant_status_stats
    (mcv, dependencies, ndistinct)
ON tenant_id, status
FROM bench.orders;

ANALYZE bench.orders;
```

- `mcv` stores multi-column most-common value combinations.
- `dependencies` stores functional dependency statistics across columns.
- `ndistinct` helps estimate distinct multi-column combinations.

Extended statistics apply to columns within the same table and improve only the estimation patterns supported by the planner. They do not replace realistic data generation or testing actual plans.

## 8. Reading Plans with `EXPLAIN`

### Distinguishing `EXPLAIN` and `EXPLAIN ANALYZE`

`EXPLAIN` shows the estimated plan without executing the query. `EXPLAIN ANALYZE` executes the query and adds actual runtime metrics. Use `ANALYZE` to compare estimates against actual row counts, keeping in mind that the query runs for real and can consume resources or modify data.

Example:

```sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, SUMMARY ON)
SELECT
    id,
    created_at,
    total_amount
FROM bench.orders
WHERE tenant_id = 1
  AND status = 'paid'
  AND created_at >= now() - interval '30 days'
ORDER BY created_at DESC
LIMIT 100;
```

Key details to read:

- **Estimated rows:** row count predicted by the planner at each node.
- **Actual rows:** actual rows returned by the node; when `loops` > 1, the displayed row count is typically the average per loop, so always read it alongside `loops`.
- **Startup cost / total cost:** planner cost units, not milliseconds.
- **Actual time:** measured execution time when timing is enabled; `TIMING OFF` reduces per-node timing overhead.
- **Buffers:** shared/local/temp blocks hit, read, dirtied, or written.
- **Planning Time / Execution Time:** overall planning and execution times.
- **Rows Removed by Filter:** rows discarded by the filter condition at that node.
- **Sort Method / Hash Batches:** how sorting or hashing executed and signs of spilling out of memory.

Parent node buffer counters generally include child node work. Do not sum buffer counts across all nodes as independent quantities.

### Detecting cardinality misestimates

If the planner estimates 100 rows while a node actually returns 500,000 rows, the misestimate is severe. Errors in lower nodes can cause the planner to pick the wrong join order, an inappropriate nested loop, or insufficient memory for hashes/sorts.

A practical reading workflow:

1. Find the lowest node where `estimated rows` diverges sharply from `actual rows`.
2. Inspect statistics for the columns used in filters or joins.
3. Check data skew, `NULL` ratios, common values, and column correlations.
4. Run `ANALYZE`, raise statistics targets, or add extended statistics when justified.
5. Re-measure on the same dataset and parameters.

Do not inspect only the root node. Misestimates often originate at a small lower scan and propagate upward into joins or aggregates.

### Sequential scans are not always bad

When a predicate matches a large share of rows, a sequential scan can be cheaper than traversing an index and fetching heap pages repeatedly. Conversely, for rare parameters, an index scan or bitmap scan may win. Testing aims to verify that the planner picks suitable plans for each parameter group, not to force every query onto an index.

You can temporarily disable a planner strategy in a test session to inspect alternatives, but `enable_*` settings are diagnostic tools only. Never use them as default production workarounds without broad evidence and impact evaluation.

## 9. Measuring Buffers, I/O, and Disk Spills

Wall time alone does not tell you whether a query is CPU-bound, cache-bound, or storage-bound. `BUFFERS` separates blocks already in shared buffers from blocks read from lower storage.

```sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT
    tenant_id,
    status,
    count(*) AS order_count,
    sum(total_amount) AS amount
FROM bench.orders
WHERE created_at >= now() - interval '90 days'
GROUP BY tenant_id, status;
```

What to observe:

- `shared hit`: blocks already present in PostgreSQL shared buffers.
- `shared read`: blocks read into shared buffers from underlying storage; they may still be served from the OS page cache.
- `temp read`/`temp written`: temporary data read/written, typically from sorts or hashes exceeding memory limits.
- `local`: blocks belonging to session-local temporary relations.

`shared read` does not guarantee a physical disk read; the operating system may satisfy it from page cache. When I/O timing needs measurement, consider `track_io_timing` in test environments alongside OS-level metrics.

### Detecting sort and hash spills

A large sort may show `Sort Method: external merge` along with disk usage. Hash joins or hash aggregates can split into multiple batches when the hash table exceeds memory. This signals a need to review data volume, predicates, indexes, and `work_mem`.

Never increase `work_mem` globally just to eliminate a spill on one test query. Each query can allocate memory for multiple sort/hash nodes, and concurrent sessions multiply total memory usage. Measure concurrency and consider session- or role-scoped tuning for suitable workloads.

## 10. Testing Common and Rare Parameters

A parameterized query can have a great plan for a small tenant and a terrible plan for a large tenant, or vice versa. Run the exact same SQL across multiple parameter groups:

```sql
PREPARE tenant_orders(integer, timestamptz) AS
SELECT id, created_at, total_amount
FROM bench.orders
WHERE tenant_id = $1
  AND created_at >= $2
ORDER BY created_at DESC
LIMIT 100;

EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
EXECUTE tenant_orders(1, now() - interval '30 days');

EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
EXECUTE tenant_orders(777, now() - interval '30 days');

DEALLOCATE tenant_orders;
```

Tenant `1` represents a hot value in the illustrative dataset; `777` represents a tail tenant. Exact results depend on generated data, and you may want to verify that the sampled tenant actually exists.

### Generic plans vs. custom plans

For prepared statements, PostgreSQL can choose a custom plan tailored to specific parameter values or a generic plan independent of specific values. Selection depends on execution history and estimated costs. When parameter distributions are heavily skewed, a single generic plan may not be optimal for all parameter groups.

In a test session, you can compare:

```sql
SET plan_cache_mode = force_custom_plan;
-- Run EXPLAIN EXECUTE with hot and cold parameters.

SET plan_cache_mode = force_generic_plan;
-- Re-run the same statement with similar parameters.

RESET plan_cache_mode;
```

This is a diagnostic test. Never force custom or generic plans system-wide based on a single query. Check whether your driver uses prepared statements, how the pooler manages sessions, and prepared statement lifetimes in the real environment.

## 11. Testing Indexes with Skewed Data

Indexes vary in effectiveness depending on selectivity, column order, row width, and access distribution. For example:

```sql
CREATE INDEX orders_tenant_created_idx
    ON bench.orders (tenant_id, created_at DESC);

CREATE INDEX orders_tenant_status_created_idx
    ON bench.orders (tenant_id, status, created_at DESC);

ANALYZE bench.orders;
```

Compare queries for large vs. small tenants, common vs. rare statuses, and short vs. long time windows. An index with more columns is not automatically better than one with fewer columns. Column order dictates which predicates can use the index and how entries are ordered in the B-tree.

### Testing index-only scans

An index-only scan avoids heap fetches efficiently only when the visibility map marks the relevant pages all-visible. After bulk loads, updates, or deletes, this condition may differ from production. Run appropriate vacuuming in the test environment and inspect `Heap Fetches` in the plan. Never infer that an index-only scan never touches the heap solely from the node name.

### Measuring write overhead

Indexes speed up certain reads while increasing work on inserts/updates/deletes, consuming storage, and adding maintenance overhead. Run a mixed write workload when comparing indexes. Do not benchmark only `SELECT`s and add every index imaginable.

## 12. Testing Joins with Realistic Cardinality

A join depends on row counts on both sides, key distributions, duplication rates, and matched row counts. For example:

```sql
SELECT
    o.tenant_id,
    c.region_code,
    count(*) AS order_count,
    sum(o.total_amount) AS total_amount
FROM bench.orders AS o
JOIN bench.customers AS c
  ON c.tenant_id = o.tenant_id
WHERE o.created_at >= now() - interval '30 days'
GROUP BY o.tenant_id, c.region_code;
```

This example joins on tenant and can match many rows on both sides, multiplying output rows. In real models, joins usually target a specific customer key. When generating fixtures, ensure join keys reflect real business relationships and cardinality.

When reading the plan, inspect:

- Row counts at each join input.
- Post-join row counts and row multiplication.
- Whether `Nested Loop`, `Hash Join`, or `Merge Join` was chosen.
- Whether hash tables spilled into multiple batches.
- Whether join-key indexes exist and are used.
- Whether filters can be pushed down to scans before joining.

A nested loop can perform wonderfully when the outer side has only a few rows and the inner side has a matching index. That same plan can perform terribly when the outer side actually yields millions of rows due to a misestimate.

## 13. Testing Partitions

If a production table is partitioned by time or tenant, the test dataset must match the expected partition count, per-partition size, and boundaries. A tiny table with two partitions does not represent a table with hundreds of partitions.

Example creating a monthly partitioned table:

```sql
CREATE TABLE bench.events (
    id bigint NOT NULL,
    occurred_at timestamptz NOT NULL,
    tenant_id integer NOT NULL,
    payload jsonb
) PARTITION BY RANGE (occurred_at);

CREATE TABLE bench.events_2026_01
    PARTITION OF bench.events
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE bench.events_2026_02
    PARTITION OF bench.events
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
```

Queries filtering on the partition key can eliminate irrelevant partitions (partition pruning):

```sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT count(*)
FROM bench.events
WHERE occurred_at >= timestamptz '2026-02-01 00:00:00+00'
  AND occurred_at <  timestamptz '2026-03-01 00:00:00+00';
```

Test both literals and bind parameters, because pruning can happen at planning or execution time depending on the plan and parameters. Evaluate partitions scanned, planning overhead, per-partition indexes, default partition data, and queries lacking a partition-key filter.

## 14. Generating Workloads with Representative Concurrency

A query running alone can be fast, while many concurrent sessions contend for CPU, I/O, buffers, locks, and connections. Test workloads should include read/write ratios, short/long queries, think times between operations, and parameter distributions.

### Using `pgbench`

`pgbench` is bundled with PostgreSQL to generate concurrent load. You can use custom SQL scripts:

```text
\set p random(1, 100)
\if :p <= 70
  \set tenant_id 1
\else
  \set tenant_id random(2, 1000)
\endif

SELECT count(*)
FROM bench.orders
WHERE tenant_id = :tenant_id
  AND status = 'paid';
```

This script directs roughly 70% of queries to hot tenant `1` and the rest across tail tenants. Meta-command syntax can depend on your `pgbench` version; verify against the installed tool version. If a version lacks the desired expressions, generate a parameter file or custom workload driver with the required distribution.

Run 32 clients and 8 workers for 5 minutes:

```bash
pgbench -M prepared \
  -f tenant_lookup.sql \
  -c 32 \
  -j 8 \
  -T 300 \
  -P 10 \
  -r \
  -l \
  benchmark_db
```

Key flags:

- `-f`: SQL script file.
- `-M prepared`: use prepared statements for the script.
- `-c`: concurrent client count.
- `-j`: `pgbench` worker thread count.
- `-T`: run duration in seconds.
- `-P`: periodic progress interval.
- `-r`: report per-statement latency inside the script.
- `-l`: write transaction logs for deeper analysis.

Run against a dedicated test database. Never run `pgbench -i` on a database holding data you need to keep, as initialization creates/drops standard benchmark tables.

### Reproducing query mix ratios

Not all queries occur at equal rates. Use `pg_stat_statements`, application traces, or sanitized logs to determine:

- Top queries by total execution time and call count.
- Query shares by SQL pattern.
- Hot/cold parameter ratios.
- Read/write ratios and short/long transaction mixes.
- Peak periods and concurrent client counts.

A workload running only simple `SELECT` queries cannot represent a system running dashboards, ETL batches, transaction writes, and CDC concurrently. Build a mixed workload matching realistic proportions.

## 15. Measuring Latency, Throughput, and Stability

Measure these metrics together:

- **Throughput:** transactions or queries completed per unit of time.
- **Latency:** time to complete a transaction or query.
- **p50:** median latency.
- **p95/p99:** latency not exceeded by 95%/99% of operations; reflects tail latency.
- **Error rate:** rate of timeouts, SQL errors, connection errors, and retries.
- **Resource use:** CPU, RAM, I/O, WAL, connections, and lock waits.

Higher throughput does not mean a better experience if p99 spikes sharply or error rates rise. Once concurrency exceeds capacity, queueing and lock contention can drive tail latency up abruptly.

### Defining acceptance criteria before running

Example criteria for a dashboard:

| Metric | Illustrative threshold |
|---|---:|
| Key query p95 | Below 500 ms |
| Key query p99 | Below 1.5 s |
| Query errors | Below 0.1% |
| Replication lag | Below 10 seconds |
| Average CPU under load test | Below 70% |

These numbers merely illustrate how criteria are written. Real thresholds must come from SLAs, query types, infrastructure, and application criticality. Record test conditions as well so results remain comparable.

## 16. Warm Cache vs. Cold Cache

The first run may read many blocks from storage; subsequent runs are faster once data sits in shared buffers or OS page cache. Measuring only the second run can give an overly optimistic picture compared to a workload that continually shifts across working sets.

Distinguish:

- **Warm-cache test:** run multiple rounds on the same data slice to measure steady warm-cache workloads.
- **Cold-ish test:** use a dataset larger than memory or touch varying data ranges to reduce cache reuse.
- **Mixed test:** combine hot data and historical data in realistic proportions.

There is no simple, safe, portable way to purge both shared buffers and OS page cache simultaneously across every environment. Never clear OS page caches or restart a production database just to create a cold cache. Use a dedicated test instance, a fresh snapshot, or a sufficiently large dataset to model the target condition.

## 17. Ensuring Comparable Test Environments

Benchmark results are meaningful only when conditions across runs are recorded. Variables to control include:

- PostgreSQL and extension versions.
- CPU, RAM, storage type, IOPS, and filesystem.
- `shared_buffers`, `work_mem`, `effective_cache_size`, `maintenance_work_mem`.
- `max_connections`, parallel workers, and autovacuum configuration.
- Indexes, partitions, constraints, and vacuum/analyze state.
- Client count, worker count, query ratios, and input parameters.
- Cache state, warm-up duration, and measurement duration.
- Background jobs, backups, checkpoints, and active replication.

Never change multiple variables at once and attribute improvements to one of them. When comparing two options, change only the variable under study or clearly document every other difference.

### Recording server configuration

```sql
SELECT name, setting, unit, source
FROM pg_settings
WHERE name IN (
    'shared_buffers',
    'work_mem',
    'effective_cache_size',
    'maintenance_work_mem',
    'max_connections',
    'max_parallel_workers',
    'max_parallel_workers_per_gather',
    'random_page_cost',
    'effective_io_concurrency'
)
ORDER BY name;
```

Archive this output alongside the benchmark report to compare across environments and deployments.

## 18. Observing Workloads with `pg_stat_statements`

The `pg_stat_statements` extension collects statistics on executed SQL statements. It must be installed and configured per PostgreSQL version instructions, typically involving `shared_preload_libraries` and creating the extension in the database.

Example query for the statements consuming the most total time:

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
    left(query, 250) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Column names can differ across PostgreSQL and extension versions; the example uses modern column names. Inspect the actual schema before automating monitoring queries.

`pg_stat_statements` helps spot expensive query patterns, though it normalizes literals and thus does not directly reveal hot/cold parameter distributions. To test parameters, sample values from sanitized application traces or construct a parameter set with an explicit distribution.

## 19. Testing Write Queries and Side Effects

`EXPLAIN ANALYZE` on `INSERT`, `UPDATE`, or `DELETE` executes the statement for real. A transaction rollback can revert transactional data changes in a test environment:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL, TIMING OFF)
UPDATE bench.orders
SET status = 'refunded'
WHERE tenant_id = 1
  AND status = 'paid'
  AND created_at < now() - interval '2 years';

ROLLBACK;
```

This example can update many rows, so run it only on a test database. Rollback does not undo every effect: sequences do not roll back allocated values, triggers may invoke external systems, and extensions or functions may have non-transactional side effects. Inspect related triggers and functions before running.

`WAL` in `EXPLAIN` shows the WAL generated by the measured operation on versions supporting that option. If the goal is testing transaction durability and checkpoints, run a longer workload and measure at the system level rather than relying on a single statement.

## 20. Re-Testing After Index or Schema Changes

Whenever adding indexes, changing partitions, altering column types, or upgrading PostgreSQL versions, re-run the exact same benchmark suite:

1. Keep the dataset and workload constant.
2. Record plans before the change.
3. Apply the migration in the test environment.
4. Run `ANALYZE` or appropriate vacuum procedures.
5. Re-run each parameter group and concurrency level.
6. Compare latency, throughput, buffers, I/O, CPU, WAL, and errors.
7. Also test write workloads to surface overhead from new indexes or schemas.

If results change substantially, determine whether the shift came from planner statistics, plan shape, cache, data, configuration, or workload. Never conclude a migration is better just because one sample query ran faster.

## 21. Query Performance Testing Workflow

A workflow you can adopt in a project:

1. **Select critical queries:** from dashboards, APIs, ETL, or `pg_stat_statements`.
2. **Define criteria:** p95/p99, throughput, error rate, batch duration, and acceptable resource levels.
3. **Profile the data:** scale, skew, cardinality, correlations, nulls, row widths, and time distributions.
4. **Generate or anonymize data:** use permitted snapshots or reproducible generators; preserve relationships and distribution properties.
5. **Load to target scale:** create indexes/partitions/constraints matching production and run `ANALYZE`.
6. **Run single-query checks:** use `EXPLAIN (ANALYZE, BUFFERS)` with hot, cold, and median parameters.
7. **Run concurrent load:** reproduce query mix ratios, client counts, and read/write patterns.
8. **Measure multiple iterations:** include warm-up, sufficient run duration, p50/p95/p99, and error rates.
9. **Analyze plans:** check nodes with cardinality misestimates, scans, joins, sort/hash spills, and buffers/I/O.
10. **Iterate with controlled changes:** update statistics, indexes, or settings one step at a time and re-benchmark.
11. **Archive results:** version, dataset, seed/snapshot, configuration, scripts, parameters, plans, and metrics.
12. **Set regression thresholds:** alert automatically when latency or resource usage exceeds agreed thresholds.

## 22. Benchmark Report Template

A report should contain enough detail for someone else to reproduce it:

| Field | What to record |
|---|---|
| Test ID | Query or workload name |
| Commit/migration | Code and schema version |
| PostgreSQL | Server version, relevant extensions |
| Dataset | Snapshot/seed, row counts, and heap/index sizes |
| Distribution | Hot/cold ratios, enums, time, nulls, and correlations |
| Statistics | `ANALYZE` timestamp, statistics targets, extended statistics |
| Configuration | CPU, RAM, storage, and key settings |
| Parameters | Parameter value groups tested and their weights |
| Load | Client count, worker count, duration, read/write ratio |
| Results | p50/p95/p99, throughput, errors, CPU, I/O, buffers, WAL |
| Plans | Before/after `EXPLAIN` and estimation discrepancies |
| Conclusion | Pass/fail thresholds, root causes, and next actions |

Never save only screenshots or a single aggregate number. Archive the scripts, SQL, configuration, text/JSON plans, and input datasets needed to reproduce the results.

## 23. Common Testing Mistakes

- Using a few thousand rows and extrapolating results to multi-million-row tables.
- Generating every value uniformly when production has hot values.
- Failing to reproduce cross-column correlations.
- Skipping `ANALYZE` after bulk loading or major data transformations.
- Comparing two plans under different cache states, parameters, or concurrency levels.
- Measuring once and reporting only the fastest runtime.
- Benchmarking only `SELECT` while ignoring index impact on writes.
- Summing buffers across all `EXPLAIN` nodes even though parent nodes include child nodes.
- Interpreting `shared read` as guaranteed physical disk I/O.
- Forcing the planner to use an index instead of investigating why a sequential scan was cheaper.
- Using a prepared statement while testing only one parameter value.
- Measuring only throughput while ignoring p95/p99 and error rates.
- Running `EXPLAIN ANALYZE` on write statements in production without impact assessment.
- Failing to archive dataset, configuration, scripts, and plans, making reproduction impossible.
- Using data with real personal information in unprotected test environments.

## 24. Practice Exercises

### Exercise 1: Create tenant-skewed data

Create an orders table with at least one million rows where one tenant accounts for roughly 70% of rows and the rest spreads across many tenants. Count rows per tenant and verify the distribution before benchmarking.

### Exercise 2: Compare hot and cold values

Run the same query with a hot tenant and a small tenant. Save `EXPLAIN (ANALYZE, BUFFERS)` and compare estimated rows, actual rows, scan nodes, and buffers.

### Exercise 3: Inspect single-column statistics

Inspect `pg_stats` before and after `ANALYZE`. Increase the statistics target on a skewed column, re-run `ANALYZE`, and record changes in row estimates.

### Exercise 4: Inspect multi-column correlation

Generate data where a large tenant has a higher `paid` rate than small tenants. Compare estimates before and after creating `mcv`/`dependencies` extended statistics.

### Exercise 5: Measure multiple data scales

Create datasets of 100 thousand, 1 million, and 5 million rows with the same distribution. Measure runtime, buffers, index size, and plans. Explain why speed does not scale linearly.

### Exercise 6: Test prepared statements

Create a prepared statement and run it with hot/cold parameters. Compare `force_custom_plan` against `force_generic_plan` in a test session.

### Exercise 7: Inspect spills

Run a grouping/sorting query on large data. Observe sort methods, hash batches, and temp blocks. Experiment with tuning `work_mem` per session and re-measure under concurrency.

### Exercise 8: Test concurrent load

Write a `pgbench` script with hot/cold parameter ratios. Run with 1, 8, 32, and 64 clients; record throughput, p95/p99, and error rates.

### Exercise 9: Compare warm cache and mixed workloads

Run the same workload repeatedly to measure warm cache. Then vary the accessed data ranges or use a dataset larger than cache to simulate a mixed workload.

### Exercise 10: Check regressions after adding an index

Benchmark before and after adding an index using both read and write queries. Evaluate read gains, insert/update overhead, storage footprint, and maintenance cost.

## 25. Review Questions

**1. Why is matching row count alone insufficient for a representative test dataset?**

Because value distributions, cardinality, correlations, null ratios, row widths, index sizes, and temporal locality all shape planner estimates and access costs.

**2. How can skewed data alter a query plan?**

A filter predicate might return most rows for a hot value yet only a few rows for a cold value. The planner may rightly pick a sequential scan in the first case and an index scan in the second.

**3. What does `ANALYZE` do?**

It collects statistics about data distribution so the planner can estimate cardinalities and costs. After loading or modifying substantial data, stale statistics may no longer be representative.

**4. What does `pg_stats.correlation` describe?**

It describes the correlation between a column's value order and the physical row order in the table. It is not the correlation coefficient between two columns.

**5. When should extended statistics be used?**

When predicates across multiple columns of the same table are correlated and the planner misestimates value combinations. `mcv`, `dependencies`, and `ndistinct` assist with different estimation patterns.

**6. Why test both hot and cold parameters with prepared statements?**

Because a generic plan may not be optimal for every value when parameter distributions are strongly skewed. You need to observe custom/generic plan behavior and how the driver actually sends queries.

**7. Is `EXPLAIN ANALYZE` safe for all statements?**

No. It executes the statement. For DML, data can be modified; rollbacks also do not undo non-transactional side effects. Always use a test environment.

**8. Why measure p95 and p99?**

Averages can hide a subset of very slow requests. Tail percentiles reflect the experience of slow requests and reveal stability under load.

**9. Does `shared read` always mean reading from physical disk?**

Not necessarily. PostgreSQL had to read the block into shared buffers, but the OS page cache may satisfy that request without hitting the storage device.

**10. Why must benchmarks include concurrent workloads?**

Because multiple sessions contend for CPU, I/O, memory, locks, and connections. A plan that runs fast in isolation may fail p95/p99 targets under realistic load.

**11. When is a sequential scan a reasonable choice?**

When a predicate returns a large fraction of the table or sequential reading is cheaper than repeated random heap lookups through an index. Not every query should use an index.

**12. Why archive snapshots or data seeds?**

So subsequent benchmarks run on equivalent data, separating performance shifts caused by code/configuration changes from shifts caused by dataset changes.

## 26. Conclusion

Testing PostgreSQL queries with skewed data and representative volumes requires reproducing the factors that govern the planner and workload: table scale, physical size, hot/cold values, column correlations, temporal distribution, cardinality, query parameters, and concurrency. Use `ANALYZE`, `pg_stats`, extended statistics, and `EXPLAIN (ANALYZE, BUFFERS)` to understand gaps between estimates and reality; then benchmark latency, throughput, tail latency, and resources under repeatable conditions. Results are trustworthy only when datasets, configurations, parameters, and execution methods are clearly documented.
