# Avoiding Plan Forcing Before Identifying the Root Cause in PostgreSQL

A PostgreSQL query is slow. You run `EXPLAIN` and see a `Seq Scan` over a multi-million-row table, or a `Nested Loop` iterating hundreds of thousands of times. The knee-jerk reaction is often **disabling `enable_seqscan`**, **disabling `enable_nestloop`**, **cranking `work_mem` sky-high**, **forcing an index**, or looking for a tool to “pin” a query plan.

Sometimes those tweaks speed up a single test run. Yet if the real culprit is **stale statistics**, **wrong row estimates**, **parameter skew**, **a mismatched index**, **type casts preventing index usage**, **I/O saturation**, **lock waits**, or a **suboptimal query shape**, forcing a plan only hides the defect, slows down other parameter values, and triggers regressions as data evolves.

**Core principle of this lesson: optimize from evidence, never out of dislike for an `EXPLAIN` node name.** A good plan returns correct results at an execution cost well suited to the workload—not necessarily one featuring `Index Scan`, `Hash Join`, or `Parallel Scan`.

In the **Query Optimization** chapter, this lesson presents a practical methodology: measure the query in proper context, read **estimated vs. actual** metrics, locate the first node where statistics or cost estimates go wrong, verify a hypothesis with an isolated experiment, fix the **root cause**, and validate across multiple parameters and loads before rollout.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Distinguish between **query plan**, **planner estimates**, and **runtime evidence**.
2. Read `EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS)` without mistaking `cost` for elapsed time.
3. Spot mismatches between estimated `rows` and `actual rows`, factoring in `loops`.
4. Explain why **`Seq Scan` can be optimal** while `Index Scan` can perform poorly.
5. Recognize a `Nested Loop` slowed by **bad cardinality estimates** rather than assuming `Nested Loop` is inherently bad.
6. Inspect `ANALYZE`, `pg_stats`, `reltuples`, `n_distinct`, most-common-values, and **extended statistics**.
7. Recognize differences between **generic** and **custom plans** for prepared statements under skewed parameter distributions.
8. Rewrite predicates to be index-usable (*sargable*) instead of turning off planner nodes.
9. Separate plan issues from **locks, I/O, temp spills, cache warmth, JIT, parallel worker starvation**, or application overhead.
10. Use `SET LOCAL enable_seqscan=off`, `enable_nestloop=off`, and similar knobs **strictly as scoped diagnostic experiments**.
11. Assess the risks of hints, plan pinning, and cluster-wide planner parameter changes.
12. Execute a query-regression runbook: baseline → hypothesis → controlled test → root-cause fix → rollback plan.

## 2. How Does PostgreSQL Choose a Plan?

A SQL statement declares **what result to return**, not which physical access method must be used.

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'paid';
~~~

PostgreSQL may evaluate:

- `Seq Scan`: reading heap blocks sequentially and filtering rows;
- `Index Scan`: traversing a B-tree to find TIDs, then fetching heap tuples;
- `Index Only Scan`: reading directly from the index when all columns are covered and visibility permits;
- `Bitmap Index Scan + Bitmap Heap Scan`: collecting heap block locations and reading blocks in physical order;
- Parallel access paths when safe and cost-effective;
- Other variants depending on table structure, indexes, partitions, and version.

The planner constructs **candidate paths**, estimates row counts and processing costs at every step, and chooses **one plan with the lowest estimated cost**. It does not run all candidate plans to measure real execution times.

~~~mermaid
flowchart TD
    A["SQL + parameters"] --> B["Parser / rewrite"]
    B --> C["Planner: candidate paths"]
    S["Table / column / extended stats"] --> C
    G["Cost settings + index definitions"] --> C
    C --> D["Select plan by cost estimate"]
    D --> E["Executor runs against live data"]
    E --> F["Actual rows / time / buffers / waits"]
    F --> H{"Slow or regressed?"}
    H -->|Yes| I["Investigate root cause"]
    I --> S
    I --> G
    I --> A
    H -->|No| J["Monitor; do not force plan"]
~~~

### 2.1. Estimated Cost Is Not a Wall-Clock Timer

In `EXPLAIN` output:

~~~text
Seq Scan on orders (cost=0.00..12000.00 rows=50000 width=32)
~~~

`cost=12000` is a **relative internal cost unit**, not 12 seconds or 12,000 ms. Parameters such as `seq_page_cost`, `random_page_cost`, `cpu_tuple_cost`, `cpu_index_tuple_cost`, and `cpu_operator_cost` feed into that model.

The runtime section:

~~~text
(actual time=0.012..145.321 rows=48000 loops=1)
~~~

appears only with `EXPLAIN ANALYZE`; these are actual timings observed during that execution. Never subtract `cost` and `actual time` directly as matching units.

### 2.2. Two Distinct Ways the Planner Goes Wrong

**Cardinality error:** the planner predicts 100 rows when reality holds 100,000 rows. It may pick an expensive Nested Loop thinking the inner scan iterates just 100 times.

**Accurate cardinality, unexpected cost/runtime:** row counts match fairly well, yet execution drags due to random I/O, cold caches, disk spills, lock waits, CPU saturation, or hardware characteristics differing from cost-model assumptions.

These two scenarios require different investigations. **Never tweak `random_page_cost` to mask a 1,000x cardinality estimation error.**

### 2.3. A Node Name Alone Does Not Prove Good or Bad

| Node | Can Be Fast When | Can Be Slow When |
| --- | --- | --- |
| `Seq Scan` | Filtering a large share of the table, small table, data cached | Fetching tiny slice of a huge table lacking an index |
| `Index Scan` | Selective filter, few heap fetches | Scanning most of the table via random heap I/O |
| `Index Only Scan` | Index covers columns and pages are all-visible | Heavy `Heap Fetches`, oversized index |
| `Bitmap Heap Scan` | Many scattered rows grouped cleanly by heap page | Lossy bitmap causing heavy rechecks or extra sort |
| `Nested Loop` | Tiny outer input, fast inner index lookup | Outer underestimated severely, driving millions of inner loops |
| `Hash Join` | Suitable inputs, hash table fits in memory | Hash spills/batches, inputs far larger than estimated |
| `Merge Join` | Both inputs already ordered properly | Huge explicit sorts or misestimated join selectivity |
| `Gather/Gather Merge` | Heavy scan/aggregate/sort parallelizes well | Worker startup overhead, tuple transfer, leader bottleneck |

The goal is not **removing suspicious-looking node names**, but understanding **why the planner picked the node and where time is actually spent**.

## 3. Five Sources of Slowness to Separate Before Blaming the Plan

A slow query may stem from:

1. **Suboptimal plan:** bad cardinality/cost estimates, unusable index, poor join order.
2. **Data or SQL design:** returning too many rows, vague filters, N+1 queries, deep `OFFSET`.
3. **System resources:** I/O, shared-buffer misses, temp spills, CPU, memory pressure, competing autovacuum.
4. **Concurrency:** lock waits, long transactions, blocked backends, serialization retries.
5. **Outside the database:** connection pool waits, network latency, client fetching, JSON serialization, ORM hydration.

For example, an endpoint takes 8 seconds while `EXPLAIN ANALYZE` on its SQL finishes in 35 ms. **Do not touch the join planner** when the remaining six seconds sit inside connection pooling or downstream API calls.

### 3.1. Define the Exact Timing Scope

~~~text
HTTP request latency
  = connection acquisition wait
  + round-trip to PostgreSQL
  + SQL execution time
  + row fetch / network transfer
  + ORM mapping / JSON serialization
  + other application work
~~~

Time **inside PostgreSQL** differs from **end-user latency**. Capture both whenever possible.

### 3.2. First Question: Which Exact Query Is Slow?

- Verbatim SQL or normalized query template;
- Bind parameter values and parameter data types;
- Database, role, `search_path`, and `TimeZone` when affecting semantics;
- Rows returned;
- Execution duration and call frequency;
- Differences between fast runs and slow runs;
- System load and concurrency contention;
- Execution plans captured during both fast and slow runs.

If all you know is “the orders screen is slow” without knowing which SQL is slow, flipping `enable_hashjoin` is wildly premature.

## 4. Evidence-Based Investigation Workflow

### Step 1 — Reproduce the Exact SQL and Parameters

Prioritize capturing the SQL alongside the **exact bind parameter types** sent by the application. `tenant_id=1` and `tenant_id=487` can have completely different data profiles.

**Never benchmark one arbitrary literal** and generalize across all tenants.

### Step 2 — Record a Safe Baseline

~~~sql
EXPLAIN (VERBOSE, SETTINGS)
SELECT ...
~~~

`EXPLAIN` without `ANALYZE` builds the plan without running it—ideal for statements you cannot safely execute yet. If the query is a side-effect-free `SELECT` in an appropriate environment, expand to:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS)
SELECT ...
~~~

**Caution:** `EXPLAIN ANALYZE` **executes the SQL statement**. Running it on `UPDATE`, `DELETE`, `INSERT`, or side-effecting functions mutates real data. Never run it in production without authorization and safeguards.

### Step 3 — Read the Plan Tree Bottom-Up

Inspect:

- How many rows leaf nodes read;
- Estimated `rows` vs. `actual rows`;
- `loops` multiplying inner-path cost;
- `Rows Removed by Filter` and `Rows Removed by Join Filter`;
- `Index Cond` vs. residual `Filter`;
- `Sort Method`, `Disk`, `Hash Batches`, and temp buffers;
- `Workers Planned`/`Launched`;
- Where execution time and buffer I/O spike.

### Step 4 — Formulate a Concrete Hypothesis

Example:

> The planner estimated 150 rows for this tenant, yet actual rows are 160,000; Nested Loop performed far too many inner index lookups. Suspect stale `tenant_id` distribution stats or a generic prepared plan mismatched to a large tenant.

That hypothesis is **testable**, unlike claiming “PostgreSQL picked a dumb Nested Loop.”

### Step 5 — Run a Single-Variable Experiment

Example:

~~~sql
BEGIN;
SET LOCAL enable_nestloop = off;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT ...;

ROLLBACK;
~~~

A **faster result** proves an **alternative path runs faster under test conditions**—it does **not prove** Nested Loop was the root cause or that it should be disabled globally.

### Step 6 — Fix the Root Cause

Fixes may include:

- `ANALYZE` or per-column statistics target;
- Extended statistics for correlated columns;
- Proper composite, partial, or expression indexes;
- Rewriting predicates to be sargable;
- Fixing parameter types, casts, time zones, or collations;
- Refining schema, constraints, or join logic;
- Selective custom planning where skew justifies it;
- Resolving locks, I/O bottlenecks, memory limits, or temp spills;
- Tuning cost parameters only with **system-wide evidence**.

### Step 7 — Re-Measure and Deploy with Rollback

Test across common and outlier parameters, warm and cold caches, light and peak load, and post-`ANALYZE` / data growth where feasible. Document findings and prepare rollback steps.

## 5. Lab Dataset: Reproducing Divergent Plan Choices

In the lab, we create an `orders` table containing one **giant tenant** and **many small tenants**, then test queries with competing access paths.

**Note:** The SQL below inserts hundreds of thousands of rows, generates WAL, and uses disk space. Run strictly on a lab PostgreSQL instance; on constrained environments, shrink `generate_series`, noting plans may vary. Never seed millions of test rows in production to “try indexes.”

### 5.1. Create Schema and Tables

~~~sql
CREATE SCHEMA plan_lab_291;

CREATE TABLE plan_lab_291.customers (
    customer_id INTEGER PRIMARY KEY,
    region TEXT NOT NULL
        CHECK (region IN ('north', 'south', 'central')),
    customer_type TEXT NOT NULL
        CHECK (customer_type IN ('regular', 'vip'))
);

CREATE TABLE plan_lab_291.orders (
    order_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL
        REFERENCES plan_lab_291.customers(customer_id),
    status TEXT NOT NULL
        CHECK (status IN ('paid', 'pending')),
    ordered_at TIMESTAMPTZ NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0),
    payload TEXT NOT NULL DEFAULT ''
);
~~~

### 5.2. Load 10,000 Customers

~~~sql
INSERT INTO plan_lab_291.customers
    (customer_id, region, customer_type)
SELECT
    g::integer,
    CASE g % 3
        WHEN 0 THEN 'north'
        WHEN 1 THEN 'south'
        ELSE 'central'
    END,
    CASE
        WHEN g % 10 = 0 THEN 'vip'
        ELSE 'regular'
    END
FROM generate_series(1, 10000) AS s(g);
~~~

### 5.3. Load 400,000 Skewed Orders

~~~sql
INSERT INTO plan_lab_291.orders (
    order_id,
    tenant_id,
    customer_id,
    status,
    ordered_at,
    total_amount,
    payload
)
SELECT
    g::bigint,
    CASE
        WHEN g % 10 < 8 THEN 1
        ELSE (g % 500) + 2
    END::integer,
    ((g % 10000) + 1)::integer,
    CASE
        WHEN g % 10 < 8 THEN 'paid'
        ELSE 'pending'
    END,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + ((g * 97) % 31536000) * INTERVAL '1 second',
    ((g % 100000)::numeric / 100)::numeric(12, 2),
    repeat('x', 80)
FROM generate_series(1, 400000) AS s(g);
~~~

This dataset is intentionally designed:

- **80%** of orders have `tenant_id=1` and `status='paid'`.
- The remaining **20%** have `status='pending'` and `tenant_id` ≠ 1 across smaller tenant IDs (`g % 500`).
- `tenant_id` and `status` are **strongly correlated**.
- `customer_id` repeats cleanly for testing joins.
- Roughly 400,000 rows with padding make access-path costs diverge meaningfully.

### 5.4. Verify Distribution

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE tenant_id = 1) AS big_tenant_rows,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_rows,
    COUNT(*) FILTER (
        WHERE tenant_id = 1 AND status = 'pending'
    ) AS big_tenant_pending_rows
FROM plan_lab_291.orders;
~~~

Expected logical counts:

| Metric | Value |
| --- | ---: |
| `all_orders` | 400,000 |
| `big_tenant_rows` | 320,000 |
| `paid_rows` | 320,000 |
| `big_tenant_pending_rows` | 0 |

By construction, zero `'pending'` orders exist for tenant 1—ideal for illustrating how **column-independence assumptions** produce wildly wrong estimates.

### 5.5. Gather Statistics

~~~sql
ANALYZE plan_lab_291.customers;
ANALYZE plan_lab_291.orders;
~~~

`ANALYZE` collects **sampled statistics** for the planner. Samples aren't infallible—especially under skew or multi-column correlation—yet refreshing stats is a far better starting point than disabling scan nodes.

## 6. First Test: Is `Seq Scan` Actually Wrong?

### 6.1. Query Reading Most of the Table

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM plan_lab_291.orders
WHERE tenant_id = 1;
~~~

80% of rows belong to tenant 1. If the planner selects `Seq Scan` or `Parallel Seq Scan`, **that can be a completely rational choice**: streaming table pages sequentially beats hundreds of thousands of random heap lookups via an index.

### 6.2. Query Reading a Small Tenant

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, total_amount
FROM plan_lab_291.orders
WHERE tenant_id = 500;
~~~

This query is far more selective than tenant 1. Without an index on `tenant_id`, a `Seq Scan` reads the entire table just to return a handful of rows.

### 6.3. Adding the Needed Index

~~~sql
CREATE INDEX idx_orders_tenant_291
ON plan_lab_291.orders (tenant_id);

ANALYZE plan_lab_291.orders;
~~~

Re-run both queries. PostgreSQL **may**:

- Keep `Seq Scan` for tenant 1 due to its huge row share.
- Pick `Index Scan` or `Bitmap Scan` for the small tenant because selectivity is high.

**This is desirable behavior:** the optimizer chooses different paths per parameter selectivity. Forcing `Index Scan` on tenant 1 could easily make it slower.

### 6.4. Do Not Grade by One Predicted Node Name

Lab tables, cache state, visibility maps, statistics, and settings can lead PostgreSQL to choose different nodes than shown here. **This lesson does not require printing one exact node name.** Record rows, buffers, and elapsed times rather than scoring by node type.

## 7. Distinguishing `Index Cond` from `Filter`

Consider this index:

~~~sql
CREATE INDEX idx_orders_ordered_at_291
ON plan_lab_291.orders (ordered_at);
~~~

Sargable query:

~~~sql
EXPLAIN
SELECT order_id, ordered_at
FROM plan_lab_291.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-05-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-06-01 00:00:00+00';
~~~

An `Index Cond` on `ordered_at` bounds the index range scanned. Compare that against:

~~~sql
EXPLAIN
SELECT order_id, ordered_at
FROM plan_lab_291.orders
WHERE ordered_at::date = DATE '2026-05-01';
~~~

Casting `timestamptz::date` wraps the column in an expression differing from the indexed B-tree key and depends on session `TimeZone`. The planner cannot trivially rewrite it into a raw column range.

### 7.1. Rewriting as a Half-Open Range

For a **calendar day in a known business time zone**, compute exact start/end boundaries and filter directly:

~~~sql
SELECT order_id, ordered_at
FROM plan_lab_291.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-05-01 00:00:00+07'
  AND ordered_at <  TIMESTAMPTZ '2026-05-02 00:00:00+07';
~~~

Resolving midnight boundaries in the true time zone handles DST transitions safely; never assume every local day lasts 24 hours.

### 7.2. Why Not Disable `Seq Scan` Immediately?

When a query lacks an `Index Cond` due to a function or cast on the column, disabling `enable_seqscan` may push PostgreSQL toward an awkward full index scan without **making the predicate sargable**. Fixing the predicate itself addresses the root cause.

### 7.3. Frequently Queried Expressions

If business logic genuinely filters on `lower(email)` or a truly **`IMMUTABLE`** expression, build a matching **expression index**. Never wrap `timestamptz::date` inside a bogus `IMMUTABLE` helper function to bypass restrictions—session time zone shifts would corrupt index keys.

## 8. Bad Cardinality: The Hidden Driver Behind Slow `Nested Loop`s

Suppose a plan reports:

~~~text
Nested Loop
  (cost=... rows=100 ...)
  (actual ... rows=180000 loops=1)
  -> Index Scan on orders o
       (estimated rows=100, actual rows=180000)
  -> Index Scan on customers c
       Index Cond: (customer_id = o.customer_id)
       (actual rows=1 loops=180000)
~~~

Shallow diagnosis:

> `Nested Loop` is terrible; set `enable_nestloop=off`.

Sound diagnosis:

> The planner estimated only 100 outer orders when reality returned 180,000. Believing 100 inner index lookups would be cheap, it picked Nested Loop—which then executed 180,000 times. First investigate **the outer relation's row estimate**, not merely the `Nested Loop` label.

### 8.1. When `Nested Loop` Shines

~~~sql
SELECT o.order_id, c.region
FROM plan_lab_291.orders AS o
JOIN plan_lab_291.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.order_id = 12345;
~~~

The outer side finds one order, and looking up its customer by primary key is instant. `Nested Loop` is ideal here.

### 8.2. When the Outer Side Is Large

~~~sql
SELECT o.order_id, c.region
FROM plan_lab_291.orders AS o
JOIN plan_lab_291.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.tenant_id = 1;
~~~

The outer input emits hundreds of thousands of rows; Hash Join, Nested Loop, or Merge Join may be considered. Never crown one join type universal without real cardinality and cost data.

### 8.3. `loops` Is a Critical Multiplier

~~~text
Index Scan on customers
  actual time=0.003..0.004 rows=1 loops=180000
~~~

One microsecond-scale index probe looks tiny alone, yet multiplied across **180,000 loops** it dominates runtime. Reading `actual rows` while ignoring `loops` misdiagnoses the bottleneck.

### 8.4. Choosing the Right Fix

- Outer estimate wrong → investigate statistics, column correlations, parameter skew, or query rewrites.
- Estimate accurate yet inner lookups I/O-bound → check indexes, caching, and join access path.
- Alternative Hash Join runs much faster → determine why planner mispriced costs and fix the cause.
- Join multiplies rows due to missing filter/key → **fix SQL semantics**, never force join algorithms.

## 9. Stale or Insufficient Statistics

PostgreSQL does not scan whole tables during planning. It relies on **collected statistics** and relation/index size estimates. When tables grow sharply without updated stats, the planner can assume vastly fewer rows than exist.

### 9.1. Check Table Statistics Status

~~~sql
SELECT
    s.relid::regclass AS table_name,
    s.n_live_tup,
    s.n_dead_tup,
    s.last_analyze,
    s.last_autoanalyze,
    s.analyze_count,
    s.autoanalyze_count
FROM pg_catalog.pg_stat_user_tables AS s
WHERE s.schemaname = 'plan_lab_291'
ORDER BY s.relname;
~~~

**Note:** `n_live_tup` and `n_dead_tup` are **statistical estimates**, not live `COUNT(*)` values. A recent `last_analyze` alone also fails to guarantee good estimates under strong data skew or multi-column correlation.

### 9.2. Inspect Catalog Row Estimates

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    c.reltuples::bigint AS estimated_rows,
    c.relpages AS estimated_pages,
    pg_catalog.pg_size_pretty(
        pg_catalog.pg_total_relation_size(c.oid)
    ) AS total_size
FROM pg_catalog.pg_class AS c
WHERE c.oid IN (
    'plan_lab_291.orders'::regclass,
    'plan_lab_291.customers'::regclass
);
~~~

`reltuples` and `relpages` are updated by maintenance/stats passes and adjusted by the planner against current file size. Never treat them as exact business row counts.

### 9.3. Run `ANALYZE` on the Target Table

~~~sql
ANALYZE plan_lab_291.orders;
~~~

Re-run **the exact same SQL, bind parameters, and load conditions**. If estimated rows adjust significantly and the plan improves, stale stats were a key driver.

**Never run `VACUUM FULL` or `REINDEX` solely to fix missing statistics.** `ANALYZE` is the proper tool for planner stats; those heavier commands solve other problems and carry heavy locking/rewrite costs.

### 9.4. When Default Sampling Misses Distribution Tails

On columns with thousands of distinct values—a few huge tenants plus many tiny ones—default sampling may lack resolution. Consider raising the **per-column statistics target**:

~~~sql
ALTER TABLE plan_lab_291.orders
ALTER COLUMN tenant_id SET STATISTICS 500;

ANALYZE plan_lab_291.orders;
~~~

Do not confuse `SET STATISTICS 500` with “500 workers” or “500% more RAM.” It increases sample granularity and histogram/MCV buckets during `ANALYZE`, trading slightly more analyze/stats-storage/planning work for better estimates.

Never crank every column in production to `10000` over one slow query. Target only columns driving misestimates.

### 9.5. Per-Column Statistics Fields

~~~sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds,
    correlation
FROM pg_catalog.pg_stats
WHERE schemaname = 'plan_lab_291'
  AND tablename = 'orders'
  AND attname IN ('tenant_id', 'status', 'ordered_at')
ORDER BY attname;
~~~

Explanation:

| Attribute | Role |
| --- | --- |
| `null_frac` | Fraction of `NULL` values in sample |
| `n_distinct` | Estimated distinct values; negative numbers represent fraction of total rows |
| `most_common_vals` | Most common values (MCVs) |
| `most_common_freqs` | Estimated frequencies of MCVs |
| `histogram_bounds` | Distribution bucket bounds for range estimates |
| `correlation` | Correlation between value order and physical heap order, affecting Index Scan I/O cost |

In the lab dataset, `tenant_id=1` dominates heavily. `most_common_vals` and `most_common_freqs` capture that skew.

### 9.6. `pg_stats.correlation` Is Not Cross-Column Dependence

`pg_stats.correlation` measures alignment between **one column's values and physical row order**—useful for pricing index heap I/O. It does **not** capture correlation between `tenant_id` and `status`.

To model **multi-column correlation** for the planner, create **extended statistics**.

## 10. Extended Statistics: Fixing Independence-Assumption Errors

In the lab dataset:

~~~text
tenant_id = 1         → 320,000 rows
status = 'pending'    →  80,000 rows
tenant_id=1 AND pending →     0 rows
~~~

Knowing only single-column frequencies and assuming independence yields a naive combined probability estimate:

\[
P(\text{tenant}=1 \land \text{pending})
\approx 0.8 \times 0.2 = 0.16
\]

Multiplied by 400,000 rows, that yields roughly **64,000**, when the truth is **0**. This illustrates why **independence assumptions fail on correlated columns** (PostgreSQL's exact estimate depends on MCVs, predicate forms, and statistics, so it won't always equal literally 64,000).

### 10.1. Reproducing a Correlated-Columns Query

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM plan_lab_291.orders
WHERE tenant_id = 1
  AND status = 'pending';
~~~

The query logically returns **0**, yet without dependency stats the planner can estimate far higher. Scanning many pages to emit 0 rows does not mean PostgreSQL “lacks index support”—it reflects wrong row estimates.

### 10.2. Creating Multi-Column Extended Statistics

~~~sql
CREATE STATISTICS st_orders_tenant_status_291
    (dependencies, mcv, ndistinct)
ON tenant_id, status
FROM plan_lab_291.orders;

ANALYZE plan_lab_291.orders;
~~~

Statistics kinds:

- **`dependencies`:** functional dependency degrees between columns, helping equality filters in supported cases.
- **`mcv`:** multi-column most-common-value combinations, directly informing combinations like `(tenant_id=1, status='pending')`.
- **`ndistinct`:** distinct multi-column combinations, useful for estimates such as `GROUP BY`.

Do not view these as magic erasers for all estimation error. Complex predicates, joins, and expressions still challenge planners—verify estimated vs. actual rows afterward.

### 10.3. Inspecting Extended Statistics

~~~sql
SELECT
    statistics_name,
    attnames,
    kinds,
    n_distinct,
    dependencies,
    most_common_vals,
    most_common_freqs
FROM pg_catalog.pg_stats_ext
WHERE schemaname = 'plan_lab_291'
  AND tablename = 'orders'
ORDER BY statistics_name;
~~~

`pg_stats_ext` exposes extended stats visible to permitted roles. Exact columns and details vary slightly by PostgreSQL major version; check docs matching your version.

### 10.4. Limits of Extended Statistics

They do not turn the planner into an omniscient cross-table inference engine. In particular, **single-table extended statistics do not solve cross-table join selectivity misestimates**. Nor do they replace:

- Joining on proper keys;
- Foreign key and unique constraints;
- Indexes aligned with predicates;
- Sound data modeling;
- Workload-representative data and statistics passes.

### 10.5. Why Is This a Better Root Fix Than Forcing Joins?

When estimates fail because `tenant_id` and `status` correlate, turning off `enable_nestloop` forces an alternative plan **while leaving the planner equally blind about row counts**. Adding MCV stats gives the planner **accurate cardinality knowledge**, improving scans, joins, and aggregates across related queries.

## 11. Prepared Statements: Generic Plan vs. Custom Plan

A subtle regression occurs when **identical SQL runs with skewed parameter values** through a **prepared statement**. PostgreSQL chooses between:

- **Custom plan:** planned specifically for the **concrete parameter values** of that `EXECUTE`.
- **Generic plan:** a reusable parameter-independent plan cached to reduce planning overhead.

This distinction becomes critical under strong skew such as `tenant_id=1` (320,000 rows) vs. `tenant_id=500` (~800 rows).

### 11.1. Two Parameters, Two Optimal Access Paths

~~~sql
SELECT order_id, total_amount
FROM plan_lab_291.orders
WHERE tenant_id = 1;
~~~

versus:

~~~sql
SELECT order_id, total_amount
FROM plan_lab_291.orders
WHERE tenant_id = 500;
~~~

Tenant 1 favors `Seq Scan` / `Parallel Seq Scan`; tenant 500 favors `Index Scan`. A generic plan unaware of `tenant_id` at planning time can end up as a bad compromise for one or the other.

### 11.2. `PREPARE` and `EXECUTE`

~~~sql
PREPARE get_orders_by_tenant(integer) AS
SELECT order_id, total_amount
FROM plan_lab_291.orders
WHERE tenant_id = $1;

EXPLAIN EXECUTE get_orders_by_tenant(1);
EXPLAIN EXECUTE get_orders_by_tenant(500);
~~~

`PREPARE` defines a parameterized statement; PostgreSQL picks custom vs. generic plans on execution per its caching heuristics. Never assume seeing `PREPARE` means a generic plan is used from execution 1.

### 11.3. Controlled Comparison via `plan_cache_mode`

**Force custom plan:**

~~~sql
BEGIN;
SET LOCAL plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE get_orders_by_tenant(1);

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE get_orders_by_tenant(500);

ROLLBACK;
~~~

**Force generic plan:**

~~~sql
BEGIN;
SET LOCAL plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE get_orders_by_tenant(1);

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE get_orders_by_tenant(500);

ROLLBACK;
~~~

Here `plan_cache_mode` is used **strictly for diagnosis** inside a transaction. `force_custom_plan` helps skewed parameters at the cost of extra **planning CPU** on high-QPS traffic. `force_generic_plan` saves planning overhead at the risk of bad runtime plans for outlier parameters.

### 11.4. Inspecting Session Prepared Statements

~~~sql
SELECT
    name,
    parameter_types,
    generic_plans,
    custom_plans
FROM pg_catalog.pg_prepared_statements
WHERE name = 'get_orders_by_tenant';
~~~

`generic_plans` and `custom_plans` counters show how PostgreSQL planned executions in the current session. **Prepared statements are session-local**, not a cluster-wide registry across all client sessions.

### 11.5. Clean Up State

~~~sql
DEALLOCATE get_orders_by_tenant;
~~~

`ROLLBACK` ended the `SET LOCAL` transaction blocks, yet did not drop the prepared statement created **before** those transactions. `DEALLOCATE` releases the lab statement cleanly.

### 11.6. Key Production Lesson

When a query flies in `psql` with hardcoded literals yet crawls in the application:

1. Capture the exact SQL and bind parameter types;
2. Inspect prepared/generic-plan behavior across driver and connection pool;
3. Compare custom vs. generic plans on both giant and tiny parameter values;
4. Weigh planning CPU overhead against execution savings;
5. Evaluate query rewrites, indexes, and stats before forcing `force_custom_plan` everywhere.

## 12. Sargability: Fix the SQL Before Reaching for Hints

A *sargable predicate* can be exploited effectively by an index access method—typically as a direct equality or range condition on an indexed column.

### 12.1. Wrapping Indexed Columns in Functions

~~~sql
-- Cannot directly leverage a plain B-tree on ordered_at:
WHERE date_trunc('day', ordered_at) =
      TIMESTAMPTZ '2026-05-01 00:00:00+00'
~~~

Beyond blocking plain indexes, `date_trunc(text, timestamptz)` depends on session time zone semantics. Proper date filtering starts from the **business time zone** and translates into a range predicate on `ordered_at`.

### 12.2. Arithmetic Offsets on Columns

~~~sql
-- Transformed expression mismatches a B-tree key on total_amount:
SELECT order_id
FROM plan_lab_291.orders
WHERE total_amount + 100 >= 500;
~~~

When semantically equivalent to filtering `total_amount >= 400` without overflow or type quirks:

~~~sql
SELECT order_id
FROM plan_lab_291.orders
WHERE total_amount >= 400;
~~~

Now an index on `total_amount` (if present) applies directly. **Only apply algebraic rewrites when semantics hold identically**, watching `NULL`s, overflows, floating-point rounding, and numeric types.

### 12.3. `LIKE` and Leading Wildcards

~~~sql
WHERE email LIKE '%example.com'
~~~

behaves very differently from:

~~~sql
WHERE email LIKE 'anh%'
~~~

Standard B-trees cannot optimize arbitrary trailing-substring patterns; even prefix `LIKE` requires an appropriate operator class when non-C collations are used. For substring search, evaluate `pg_trgm` with GIN/GiST indexes—**never disable `Seq Scan`** trying to force a B-tree onto an unsupported pattern.

### 12.4. Type Casting Columns

~~~sql
WHERE customer_id::text = '123'
~~~

turns the left-hand side into a text expression incompatible with an integer B-tree on `customer_id`. Whenever the application passes valid integers, write:

~~~sql
WHERE customer_id = 123
~~~

**Never slap random casts onto columns or binds** that alter precision or semantics; align **column types, JDBC/ORM parameter types, and operators**.

### 12.5. `OR`, `IN`, and `UNION ALL`

With `OR` predicates spanning distinct columns, PostgreSQL may use `BitmapOr` over indexes or fall back to `Seq Scan`. Sometimes splitting into two `UNION ALL` branches helps, **only if duplicate semantics are preserved**:

~~~sql
-- Illustrative example:
SELECT order_id
FROM plan_lab_291.orders
WHERE tenant_id = 1
   OR customer_id = 42;
~~~

Splitting that into `UNION ALL` emits rows matching **both** conditions **twice**. Never break correctness just to alter a plan. `UNION` deduplicates yet adds sort/hash overhead—benchmark rather than blindly rewriting.

## 13. A Well-Designed Index Beats Any Hint

Instead of forcing scan operators, ask **which access path satisfies the predicate, ordering, and `LIMIT` together**.

### 13.1. Composite Index for Multi-Tenant Queries

~~~sql
CREATE INDEX idx_orders_tenant_status_time_291
ON plan_lab_291.orders (
    tenant_id,
    status,
    ordered_at DESC,
    order_id DESC
);
~~~

Target query:

~~~sql
SELECT
    order_id,
    ordered_at,
    total_amount
FROM plan_lab_291.orders
WHERE tenant_id = 500
  AND status = 'pending'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
~~~

This index can support:

- Equality predicates on `tenant_id` and `status`;
- Ordering by `ordered_at DESC, order_id DESC`;
- Early stop after 20 rows via `LIMIT 20`.

### 13.2. Why Does Index Column Order Matter?

Multi-column B-tree indexes primarily serve conditions along **leading key prefixes**. `(tenant_id, status, ordered_at DESC)` is rarely optimal for:

~~~sql
WHERE ordered_at >= ...
~~~

without predicates on the leading two columns; the planner must choose another path. Design indexes from **actual query patterns**, not merely lists of popular columns.

### 13.3. Partial Indexes for Stable Predicates

~~~sql
CREATE INDEX idx_orders_paid_tenant_time_291
ON plan_lab_291.orders (
    tenant_id,
    ordered_at DESC
)
WHERE status = 'paid';
~~~

This index includes only `'paid'` orders. It pays off when queries routinely filter `status='paid'` and that subset is selective; **in our lab dataset `'paid'` makes up 80%**, so this partial index wouldn't be dramatically smaller. Never create a partial index solely because “partial” sounds fast.

Moreover, the planner must prove a query's predicate **implies** `status='paid'`. In generic plans using `status=$1` unknown at plan time, literal partial index predicates **cannot be matched safely across arbitrary values**.

### 13.4. Covering Indexes Are Not Free

~~~sql
CREATE INDEX idx_orders_tenant_cover_291
ON plan_lab_291.orders (tenant_id, ordered_at DESC)
INCLUDE (total_amount);
~~~

`INCLUDE` can enable `Index Only Scan` when columns match and heap pages are visible, yet:

- The index grows larger;
- `INSERT`/`UPDATE` pay higher maintenance overhead;
- `Heap Fetches` still happen on unvacuumed pages;
- Covering columns do not fix arbitrary predicates.

Avoid piling up near-duplicate indexes just for prettier plans.

### 13.5. Auditing Index Usage

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_catalog.pg_stat_user_indexes
WHERE schemaname = 'plan_lab_291'
ORDER BY idx_scan DESC, indexrelname;
~~~

`idx_scan=0` over a short window does not automatically prove an index useless—especially `UNIQUE` indexes enforcing constraints on writes. Stats also reset; always verify observation window and workload coverage.

## 14. Sort and Hash Spills: Memory Problems, Not Always Plan Bugs

A query can have **fairly accurate row estimates** yet crawl because sorting or hashing runs out of memory and spills to temp files.

### 14.1. Inspecting `Sort Method`

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    total_amount
FROM plan_lab_291.orders
ORDER BY total_amount DESC, order_id DESC;
~~~

Illustrative plan:

~~~text
Sort
  Sort Key: total_amount DESC, order_id DESC
  Sort Method: external merge  Disk: 16000kB
  -> Seq Scan on orders
~~~

`external merge` and `Disk` indicate temporary storage was required. If you see:

~~~text
Sort Method: quicksort  Memory: 24000kB
~~~

that node used in-memory sorting with a different footprint.

**Never conclude that seeing a `Sort` means the planner messed up.** If the query sorts all rows without an ordered index, sorting is required work.

### 14.2. `work_mem` Is Not Total Query RAM

`work_mem` sets the memory budget per **eligible sort or hash operator** before spilling—not a cap for the entire SQL statement.

~~~sql
BEGIN;

SET LOCAL work_mem = '64MB';

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT order_id, total_amount
FROM plan_lab_291.orders
ORDER BY total_amount DESC, order_id DESC;

ROLLBACK;
~~~

This is an isolated experiment. If raising `work_mem` stops the sort spill and speeds execution, you found evidence of **sort memory pressure**. Yet raising global `work_mem` to gigabytes across hundreds of connections invites OOM/swapping, especially when single plans run multiple sorts/hashes and parallel workers.

### 14.3. Ordered Indexes Are Another Option

~~~sql
CREATE INDEX idx_orders_amount_desc_291
ON plan_lab_291.orders (
    total_amount DESC,
    order_id DESC
);
~~~

For:

~~~sql
SELECT order_id, total_amount
FROM plan_lab_291.orders
ORDER BY total_amount DESC, order_id DESC
LIMIT 20;
~~~

the index lets PostgreSQL return the **top 20 rows** far faster than sorting the whole table. Yet for returning **all 400,000 rows**, scanning in index order can actually underperform `Seq Scan + Sort` due to random heap access and payload fetches.

**Never build an index on intuition alone**; test matching `LIMIT`s and write overhead.

### 14.4. `Hash Join` Spills

In `EXPLAIN ANALYZE` for a `Hash Join`, you may observe:

~~~text
Hash
  Buckets: ...
  Batches: 16
  Memory Usage: ...
Buffers: temp read=... written=...
~~~

`Batches > 1` shows the hash table spilled into multiple batch partitions. If the real build input far exceeded estimates, the root issue may still be **cardinality estimation**; if estimates match reality yet memory falls short, test scoped per-operation memory cautiously.

### 14.5. Do Not Disable `Hash Join` Just Because It Spilled

~~~sql
SET LOCAL enable_hashjoin = off;
~~~

pushes the planner toward Merge Join or Nested Loop, yet if the true cause is tight `work_mem`, bad row estimates, or missing sort indexes, the alternative join may run even slower. Evaluate **memory**, **cardinality**, and **join keys** together.

## 15. Parallel Queries: Fewer Workers Launched Is Not a Planner Error

For large aggregations:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT COUNT(*), SUM(total_amount)
FROM plan_lab_291.orders
WHERE status = 'paid';
~~~

Plan example:

~~~text
Finalize Aggregate
  -> Gather
       Workers Planned: 3
       Workers Launched: 1
       -> Partial Aggregate
            -> Parallel Seq Scan on orders
~~~

When fewer workers launch than planned, total runtime exceeds expectations. **Toggling `enable_seqscan`** does nothing to fix worker availability.

### 15.1. Worker Limits to Inspect

~~~sql
SHOW max_parallel_workers_per_gather;
SHOW max_parallel_workers;
SHOW max_worker_processes;
SHOW parallel_setup_cost;
SHOW parallel_tuple_cost;
SHOW parallel_leader_participation;
~~~

Also monitor CPU saturation and concurrency. Raising `max_parallel_workers_per_gather` creates zero physical CPU cores; speeding one query under idle load can hurt **overall throughput** when concurrent traffic fights over workers.

### 15.2. `Gather` Passing Too Many Rows

If `Gather` must funnel millions of tuples for `SELECT *`, the leader and client network transfer become the bottleneck. `Partial Aggregate` or proper `LIMIT`/pagination trims tuple volume far better than adding workers.

### 15.3. `Gather Merge` and `ORDER BY`

`Gather Merge` preserves **sorted order** across parallel streams; plain `Gather` does not preserve global order. For:

~~~sql
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20
~~~

a composite B-tree index and single-process Index Scan often beat a parallel scan + `Gather Merge`. Never force parallelism merely because cores appear idle.

### 15.4. Small Tables and Short Queries

On tables with hundreds of rows, worker spawn overhead exceeds the entire `Seq Scan`. Not seeing `Parallel Seq Scan` when latency is tiny is **not a regression**.

## 16. JIT Compilation: Startup Overhead Can Outweigh Gains

PostgreSQL supports **JIT (Just-in-Time compilation)** for expensive queries based on cost thresholds. JIT accelerates CPU-heavy analytical expressions while adding **compilation startup time**.

### 16.1. Inspect JIT Settings

~~~sql
SHOW jit;
SHOW jit_above_cost;
SHOW jit_inline_above_cost;
SHOW jit_optimize_above_cost;
~~~

### 16.2. JIT Output in `EXPLAIN`

When JIT fires, `EXPLAIN ANALYZE` reports `Generation`, `Inlining`, `Optimization`, and `Emission` timings. If total runtime is a few milliseconds and JIT compilation consumes most of it, review your JIT thresholds.

### 16.3. Isolated Test

~~~sql
BEGIN;

SET LOCAL jit = off;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT SUM(total_amount * 1.05)
FROM plan_lab_291.orders;

ROLLBACK;
~~~

Compare against the same query with JIT active and triggered. **Never blame JIT when JIT didn't activate or test data isn't representative.** Disabling JIT server-wide to save milliseconds on one short query can slow down heavy analytical queries elsewhere.

## 17. Lock Waits: A Single `EXPLAIN` May Not Catch Them

A query can have an optimal plan yet stall on a lock held by another transaction:

~~~text
Session A:
  BEGIN;
  UPDATE one row;
  ... holds transaction open without COMMIT ...

Session B:
  UPDATE same row;
  ... waits on row lock ...
~~~

If Session B takes 20 seconds waiting for A, forcing Index Scan vs. Seq Scan changes nothing about lock blocking.

### 17.1. Inspect Wait Events and Blockers

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.xact_start,
    now() - a.xact_start AS transaction_age,
    pg_catalog.pg_blocking_pids(a.pid) AS blocking_pids,
    a.query
FROM pg_catalog.pg_stat_activity AS a
WHERE a.wait_event_type = 'Lock'
ORDER BY a.xact_start NULLS LAST;
~~~

Visibility of other sessions' query text depends on role privileges. Inspect **what query holds the lock**, long open transactions, and application transaction boundaries.

### 17.2. `idle in transaction`

~~~sql
SELECT
    pid,
    datname,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    backend_xmin
FROM pg_catalog.pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY xact_start;
~~~

Sessions stuck `idle in transaction` hold row locks and snapshots, stalling concurrent writes and blocking `VACUUM`. Tuning Session B's plan does not substitute for **committing Session A promptly**.

### 17.3. Distinguishing Timeouts

`lock_timeout` and `statement_timeout` serve distinct roles:

- `lock_timeout` caps time spent waiting to acquire a lock;
- `statement_timeout` caps total statement execution time;
- `idle_in_transaction_session_timeout` terminates sessions left idle inside open transactions.

**Timeouts are operational guardrails**, not fixes for join orders or cardinality estimates. Address the contention root cause rather than merely raising timeouts.

### 17.4. Never Blindly Kill Blockers

`pg_cancel_backend`/`pg_terminate_backend` disrupt active transactions and clients. Before invoking them in production, confirm the owner, business operation, rollback behavior, and authorization. Never kill a payment or migration transaction just to benchmark a plan.

## 18. Cache, I/O, and Correlation: Same Plan, Different Runtime

An `Index Scan` runs fast when heap pages sit in shared buffers or OS cache, and slows dramatically when reading random cold blocks from disk.

### 18.1. `BUFFERS`

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, total_amount
FROM plan_lab_291.orders
WHERE tenant_id = 500;
~~~

Fields:

- `shared hit`: buffer lookups served from PostgreSQL shared buffers;
- `shared read`: blocks loaded into shared buffers, though **not every read hits slow physical disk** due to the OS page cache;
- `shared dirtied/written`: pages dirtied or flushed when applicable;
- `temp read/written`: temporary files used during operations like sort/hash.

### 18.2. Why Ignore Cache State at Your Peril?

~~~text
Run 1: cold data → many shared reads
Run 2: cached data → mostly shared hits
~~~

If cache warmth differed before vs. after toggling a planner setting, **you cannot credit the speedup to the planner knob**. Run multiple rounds and record cache/load state.

### 18.3. B-Tree vs. `Seq Scan` Across Many Rows

An Index Scan performs many random heap visits. When a filter matches most of the table, sequential reading via `Seq Scan` can still win even on SSDs. Lowering `random_page_cost` just because you run on SSD **does not prove** every `Index Scan` should win.

### 18.4. Correlation and Physical Layout

High absolute `pg_stats.correlation` indicates index order aligns cleanly with physical heap order, reducing random heap I/O. As data mutates over time, correlation drifts. Still, `CLUSTER` or full table rewrites carry heavy locking and I/O costs—never run them reflexively simply because a plan shows `Seq Scan`.

### 18.5. Looking Beyond `EXPLAIN` for I/O

Where permitted and supported, `pg_stat_io` (modern PostgreSQL), OS disk metrics, cloud volume latency, checkpoints, and autovacuum telemetry help distinguish hardware contention from plan problems. **`EXPLAIN BUFFERS` is one diagnostic signal—not an exact disk hardware profiler.**

## 19. Partitioning, Pruning, and Hidden Causes Behind `Append`

If a table is partitioned by `ordered_at` or `tenant_id`, queries may scan unnecessary partitions whenever predicates block **partition pruning**.

Conceptual plan:

~~~text
Append
  -> Seq Scan on orders_2026_01
  -> Seq Scan on orders_2026_02
  -> Seq Scan on orders_2026_03
  ...
~~~

If a query needs only March yet scans all 12 partitions, the first question is:

> Does the filter match the partition key and operator class so planner/executor pruning can fire?

Not:

> Turn off `Seq Scan` so every partition runs an `Index Scan`.

### 19.1. Filtering with a Sargable Range

~~~sql
WHERE ordered_at >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-04-01 00:00:00+00'
~~~

generally enables partition pruning on compatible range partitions. Wrapping the partition key in arbitrary functions prevents PostgreSQL from pruning skipped partitions.

### 19.2. Runtime Execution Pruning

Parameterized prepared queries can prune partitions either at **planning time** or **execution time** depending on plan mode and PostgreSQL pruning rules. `EXPLAIN ANALYZE` may display unexecuted subplans or `Subplans Removed`. Never assume a generic plan listing multiple partitions actually scanned every one at runtime.

### 19.3. Per-Partition Statistics

Each partition maintains its own statistics and size. Under heavy skew, parent stats, child stats, autovacuum/analyze timing, and total partition count all shape planner decisions. Pinpoint **which exact partitions consume time and buffers**.

## 20. Understanding What Planner Switches Truly Do

PostgreSQL exposes plan-method switches:

~~~sql
SHOW enable_seqscan;
SHOW enable_indexscan;
SHOW enable_indexonlyscan;
SHOW enable_bitmapscan;
SHOW enable_nestloop;
SHOW enable_hashjoin;
SHOW enable_mergejoin;
SHOW enable_sort;
SHOW enable_material;
SHOW enable_hashagg;
SHOW enable_memoize;
~~~

Availability varies by major version. These `enable_*` switches nudge the planner to **discourage** specific operators.

### 20.1. `"off"` Is Not an Absolute Ban

Specifically, PostgreSQL cannot ban every `Seq Scan` or `Nested Loop` completely because sometimes no other valid path exists. Setting `enable_seqscan=off` primarily **adds a massive penalty cost to `Seq Scan`**—it does not guarantee zero `Seq Scan` nodes in every query.

### 20.2. Proper Use: Counterfactual Diagnosis

Suppose you hypothesize:

> The planner chose `Nested Loop` because it priced `Hash Join` too high.

Test inside a rolled-back transaction:

~~~sql
BEGIN;

SET LOCAL enable_nestloop = off;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT
    o.order_id,
    c.region
FROM plan_lab_291.orders AS o
JOIN plan_lab_291.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.tenant_id = 1;

ROLLBACK;
~~~

This experiment reveals **whether a better alternative path exists**, not **why the original path was chosen**. Answering why requires inspecting row estimates, stats, query patterns, and cost assumptions.

### 20.3. Testing Without `Seq Scan`

~~~sql
BEGIN;

SET LOCAL enable_seqscan = off;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT order_id
FROM plan_lab_291.orders
WHERE tenant_id = 500;

ROLLBACK;
~~~

If the plan switches to `Index Scan` and finishes faster, investigate:

- Were tables and indexes recently `ANALYZE`d?
- Do predicate types align cleanly with index columns?
- How many rows did the planner estimate?
- Does that index stay selective across other parameters?
- Were cache warmth and system load comparable?

### 20.4. Never Run Session `SET` and Forget to Reset

~~~sql
SET enable_seqscan = off;
~~~

persists for the session and can contaminate pooled connections if the pool or app does not reset state. **For diagnostic tests, always prefer `SET LOCAL` inside `BEGIN ... ROLLBACK`** so settings vanish automatically afterward.

### 20.5. Never Edit `postgresql.conf` Before Establishing a Baseline

Setting `enable_nestloop=off` or tweaking `random_page_cost` cluster-wide impacts every query and parameter distribution—including queries that previously ran well. Any server-wide tuning demands change management, tight scope, timed validation, and rollback readiness.

## 21. Adjusting Cost Parameters: Only with Environment-Wide Evidence

Key cost constants:

| Parameter | What It Models |
| --- | --- |
| `seq_page_cost` | Relative cost of sequential page reads |
| `random_page_cost` | Relative cost of random page reads |
| `cpu_tuple_cost` | CPU cost per tuple processed |
| `cpu_index_tuple_cost` | CPU cost per index entry processed |
| `cpu_operator_cost` | CPU cost per operator/function call |
| `effective_cache_size` | Expected available cache footprint—**not a RAM allocation** |
| `effective_io_concurrency` | Hint governing concurrent storage prefetch/I/O |
| `parallel_setup_cost` | Estimated setup cost for parallel plans |
| `parallel_tuple_cost` | Estimated cost per tuple transferred from workers |

### 21.1. Do Not Blindly Copy `random_page_cost = 1.1` as an “SSD Trick”

Fast SSDs lower random read latency relative to HDDs, yet planner costs also reflect caching, table correlation, concurrency, and true I/O patterns. Making random I/O look arbitrarily cheap can push heavy analytical queries toward Index Scans with massive heap fetches.

### 21.2. `effective_cache_size` Allocates Zero Memory

~~~sql
SHOW effective_cache_size;
~~~

This setting tells the planner **how much OS + PostgreSQL cache is likely available** when costing index usage; it allocates zero RAM. Raising it neither expands `shared_buffers` nor grows the OS page cache.

### 21.3. Must Cost Constants Match Exact Milliseconds?

No. Cost constants form a relative model. Validating changes requires comparing plans across a **broad suite of representative queries** without skewing system-wide decisions unfairly.

### 21.4. Scoped Cost Sensitivity Test

~~~sql
BEGIN;

SET LOCAL random_page_cost = 1.5;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT order_id, total_amount
FROM plan_lab_291.orders
WHERE tenant_id = 500;

ROLLBACK;
~~~

If the plan flips, record it strictly as a **cost-sensitivity finding**. Applying it globally demands broader evidence across production-representative workloads.

## 22. Join Order, `FROM` Collapse, and GEQO: Do Not Force by Intuition

On multi-table joins, PostgreSQL chooses:

- Join ordering;
- Join algorithm per pair;
- Scan type per base relation;
- Filter and aggregate placement;
- Materialization, sort, and hash points.

Parameters like `join_collapse_limit` and `from_collapse_limit` govern join-order search space. For queries touching many tables, the planner may invoke `GEQO` (Genetic Query Optimizer) past configured thresholds.

### 22.1. SQL `FROM` Order Is Not Execution Order

~~~sql
SELECT ...
FROM a
JOIN b ON ...
JOIN c ON ...
WHERE ...;
~~~

For associative/commutative inner joins, the planner freely reorders tables. **Never “fix” a plan by rearranging `JOIN` clauses in SQL assuming the executor must obey text order.**

### 22.2. Testing `join_collapse_limit`

~~~sql
BEGIN;
SET LOCAL join_collapse_limit = 1;

EXPLAIN
SELECT ...
FROM ...
JOIN ... ON ...;

ROLLBACK;
~~~

This is **illustrative syntax to adapt to your real query**, not runnable standalone SQL. Lowering `join_collapse_limit` constrains planner reordering of explicit joins, yet cannot override outer-join semantics or cure bad row estimates.

### 22.3. Why Avoid Locking Down Join Orders Too Fast?

A join order tailored to small table A today can collapse once A grows 100x or another tenant sees heavy skew. If the root defect is **missing indexes, stale stats, or poor predicates**, locking join order masks the issue temporarily while storing up future trouble.

## 23. Hints, Plan Pinning, and Extension Dependencies

Core PostgreSQL **does not include inline query hint syntax like `/*+ INDEX(...) */`** as a built-in forcing mechanism unlike some other RDBMSs. Third-party extensions such as **`pg_hint_plan`** exist in environments that permit them, yet:

- They are not installed or permitted everywhere on managed services;
- They introduce version and upgrade dependencies;
- Hints couple tightly to table/index names and query structure;
- They go stale whenever schemas, stats, data distributions, or versions evolve;
- They restrict planner adaptability;
- A hint cannot fix wrong cardinality estimates or broken SQL semantics;
- Hints never replace observability and regression testing.

### 23.1. When Might a Scoped Hint or Plan Control Be Justified?

Specialized incidents may warrant a temporary workaround only when:

1. Exact SQL and plans have been measured;
2. An actual planner limitation or proven regression is documented;
3. Reasonable stats, index, and query rewrites were attempted;
4. Incident deadlines demand mitigation while awaiting a root-cause fix;
5. Blast radius is bounded and a **hint removal plan** exists;
6. Testing covers diverse parameter values and data growth.

Treat it as a **controlled exception**, never step one upon spotting a `Seq Scan`.

### 23.2. From Quick Workaround to Technical Debt

~~~text
Day 1:   pin Index Scan for a small-tenant query → fast.
Day 60:  tenant grows huge → Index Scan drowns in random heap I/O.
Day 120: index or schema changes → hint silently stops matching
         or forces an even slower plan.
~~~

An unowned workaround without an expiration date or verification plan turns into **operational debt** worse than the original slow query.

### 23.3. Never Confuse Plan Pinning with Output Correctness

A query plan is solely **how** PostgreSQL computes the answer. It cannot rescue wrong data caused by missing `JOIN ON` predicates, faulty `NULL` logic, undefined time zones, or mismatched transaction isolation. **SQL correctness always comes before execution speed.**

## 24. Production Observability: Finding High-Impact Queries

Before tuning any planner knob, identify which queries dominate **cluster-wide resource consumption**—not merely one query you happened to notice once.

### 24.1. `pg_stat_statements`

The `pg_stat_statements` extension aggregates normalized SQL metrics once installed and configured by an administrator (not every cluster or managed tier enables it out of the box).

Where available and permitted:

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    stddev_exec_time,
    rows
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

This highlights:

- Queries burning the most **total time**;
- Queries with high **mean execution time**;
- Queries with high runtime variance;
- High-frequency tiny queries costing heavily in aggregate;
- Call counts vs. rows processed.

**Watch out:** one normalized statement mixes `tenant_id=1` and `tenant_id=500`; averages hide long tails. Capture representative bind parameters safely and compliantly when investigating skew.

### 24.2. Never Rely Solely on Means

~~~text
Query A:
  99% of calls: 5 ms
   1% of calls: 9,000 ms

Query B:
  100% of calls: 70 ms
~~~

Looking solely at averages obscures A's extreme tail latency and distorts priorities. Query A causes severe p99 spikes and timeouts despite fast typical runs.

`pg_stat_statements` does not record per-call histograms or bind-value breakdowns. Combine with **application tracing**, logs, and monitoring as needed.

### 24.3. `auto_explain` for Slow Production Plans

PostgreSQL's `auto_explain` module logs actual plans for statements exceeding configured duration thresholds. It shines when slow plans trigger only inside real application traffic and resist reproduction in `psql`.

Key operational notes:

- Usually requires preload configuration and admin rights;
- `auto_explain.log_analyze=on` adds **runtime timing overhead**;
- Configure thresholds and sampling carefully to avoid log floods, leaking sensitive bind values, or degrading throughput;
- Logged plans record plan-time reality—still verify parameters and wait events.

Never turn on verbose plan logging across 100% of production traffic without assessing overhead and privacy rules.

### 24.4. `log_min_duration_statement`

When tuned properly by DBAs, `log_min_duration_statement` logs slow statements exceeding a duration threshold. Raw SQL logs may expose sensitive values—enforce security, retention, and access controls.

**Duration logs alone do not separate CPU, I/O, and lock waits.** Pair them with `pg_stat_activity`, `EXPLAIN ANALYZE`, and resource telemetry.

### 24.5. `queryid` Across Schema and Version Changes

A `queryid` groups structurally normalized statements, yet is not immutable across major PostgreSQL versions, config shifts, schema edits, or environments. For release comparisons, also log SQL fingerprints, migration versions, and application call sites.

## 25. Fair Measurement: Benchmarking a Planner Change

### 25.1. Control Independent Variables

Clean experiment:

~~~text
Baseline A:
  same SQL
  same parameters
  same data
  same role/schema
  multiple measured iterations

Experiment B:
  change one variable only
  (ANALYZE, index, SQL rewrite, or SET LOCAL...)
  re-measure under matching conditions
~~~

If you add an index, raise `work_mem`, and lower `random_page_cost` all at once, you cannot tell which change produced the result.

### 25.2. Verify Equivalent SQL Results

Rewriting a `LEFT JOIN` to `INNER JOIN` may run faster by dropping unmatched rows. Adding `LIMIT` trims output while breaking API contracts. **Faster with wrong results is not optimization.**

### 25.3. Record Both Baseline and Candidate

| Field to Record | Baseline | Candidate |
| --- | --- | --- |
| SQL / query ID | Current statement | Semantically equivalent |
| Bind parameters / types | Record explicitly | Keep identical |
| PostgreSQL version | Record explicitly | Keep identical |
| Dataset / stats | Record explicitly | Log any refresh |
| Planner GUCs | Current defaults | Vary only tested knob |
| Plan root & join order | Capture | Capture |
| Estimated vs. actual rows | Capture | Capture |
| Execution Time | Multiple runs | Multiple runs |
| Buffers hit/read | Capture | Capture |
| Temp I/O | Capture | Capture |
| Workers Launched | Capture if parallel | Capture if parallel |
| Lock waits / I/O load | Monitor | Monitor |
| Result / row count | Verify | Must stay equivalent |
| Throughput impact | Test under realistic load | Test under realistic load |

### 25.4. Never Judge from One Run

Execution times fluctuate due to:

- Warm vs. cold shared buffers and OS page cache;
- Competing vacuum, checkpoint, or backup activity;
- Parallel worker availability;
- Network and client fetch delays;
- CPU contention;
- Cloud storage burst credits or I/O throttling;
- JIT warmup;
- Parameter and row-count variance.

Run multiple trials, alternate A/B order sensibly, report medians and p95/p99 where appropriate, and explain observed variance.

### 25.5. Validate on Production-Scale Data

A query using `Index Scan` on 400,000 rows may switch to `Seq Scan` at 40 million rows; tenant skew and physical correlation may differ too. Lab benchmarks teach mechanics—they do not replace testing on realistic scale and skew.

### 25.6. Isolating Tests with `SET LOCAL`

~~~sql
BEGIN;

SET LOCAL enable_nestloop = off;
SET LOCAL work_mem = '32MB';

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT
    c.region,
    COUNT(*)
FROM plan_lab_291.orders AS o
JOIN plan_lab_291.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.tenant_id = 1
GROUP BY c.region;

ROLLBACK;
~~~

`ROLLBACK` ends the transaction and drops the `SET LOCAL` overrides; because the lab query is a read-only `SELECT`, no business writes occur. In production, even heavy `SELECT`s burn CPU and I/O—test only within authorized bounds.

### 25.7. `EXPLAIN ANALYZE` on DML

Do not run directly without safeguards:

~~~sql
-- WARNING: uncommented, this really executes an UPDATE.
-- EXPLAIN (ANALYZE, BUFFERS)
-- UPDATE plan_lab_291.orders
-- SET status='paid'
-- WHERE tenant_id=1;
~~~

When benchmarking real DML in a lab, wrap in explicit transactions with rollback while remembering sequences, external side effects, lock contention, and write I/O are not magically erased. **Never treat `ROLLBACK` as blanket permission to test DML in production.**

## 26. Prioritizing Root-Cause Fixes by Risk Level

Rather than chasing a list of “parameters to tweak,” classify remedies systematically:

| Symptom | Diagnostic Check | Likely Sound Root Fix | Risk If Forcing Plan Hastily |
| --- | --- | --- | --- |
| Big `estimated` vs. `actual rows` gap | Compare actuals, check `pg_stats` | `ANALYZE`, extended stats, statistics target | Forcing join method on wrong counts |
| Function/cast on indexed column | Check `Index Cond` vs. `Filter` | Sargable rewrite or valid expression index | Index still mismatches condition |
| Big vs. small tenants diverge | Compare custom vs. generic plans | Stats, indexes, branching logic, scoped custom plan | Small-tenant plan wrecks big tenant |
| `Seq Scan` reading 80% of table | Compare buffers/I/O vs. Index Scan | Often keep `Seq Scan` | Heavy random heap reads |
| `Nested Loop` running 200,000 loops | Check outer estimate and inner loops | Fix estimate, index, or join predicate | Forced Hash Join may spill badly |
| `Sort` external merge | Check `Disk` and temp buffers | Query shape, index, `LIMIT`, scoped `work_mem` | Disabling `Sort` won't satisfy `ORDER BY` |
| High Hash `Batches` | Check memory and temp I/O | Shrink join/rows or tune scoped `work_mem` | Disabling Hash Join moves bottleneck |
| Planned 4 workers, Launched 0 | Inspect limits and concurrency | Coordinate worker pools/workload | Raising `per_gather` creates zero CPUs |
| `WaitEvent=Lock` | Find blocking PIDs | Fix transaction scope or lock order | Changing plan won't clear lock wait |
| DB query fast, API slow | Measure pool, network, serialization | Fix application path | Tuning planner fixes wrong layer |
| Sequential run already very fast | Check latency and throughput | Often no change needed | Adding parallel startup overhead |
| `Index Only Scan` has high `Heap Fetches` | Check `VACUUM`/visibility map | Tune autovacuum, cut churn | Forcing index-only skips nothing on dirty pages |
| Partitions fail to prune | Inspect partition key & predicate | Rewrite range/predicate/stats | Scans unnecessary partitions regardless |

### 26.1. Recommended Priority Order

1. **Correct results and clear SQL semantics.**
2. **Identify exact SQL and bind parameter types.**
3. **Measure estimated vs. actual rows, waits, and I/O.**
4. **Fix SQL, schema, stats, or indexes based on evidence.**
5. **Re-benchmark across multiple parameters and workloads.**
6. **Consider planner GUCs or hints only for proven residual issues**, tightly scoped with rollback ready.

No single hammer solves every problem: `ANALYZE` will not cure lock waits, and tweaking GUCs will not supply a missing selective index.

## 27. Classic Scenarios and Root-Cause Reasoning

### Scenario A — PostgreSQL Picks `Seq Scan` Even Though an Index Exists

~~~text
Seq Scan on orders
  Filter: tenant_id = 1
  actual rows: 320000
~~~

In our lab, tenant 1 owns 80% of the table. `Seq Scan` may be **the optimal choice**, needing no “fix.” Compare table size, `shared read/hit`, and rows returned against an `Index Scan` inside an **isolated experiment**.

### Scenario B — `Seq Scan` on a Tiny Tenant

~~~text
Seq Scan on orders
  Filter: tenant_id = 500
  actual rows: ~800
~~~

If no index covers `tenant_id` and this query runs frequently, evaluate a `tenant_id` or composite index. If an index already exists yet the planner sticks with `Seq Scan`, inspect row estimates, `random_page_cost`/cache, selectivity, and column stats.

### Scenario C — `Nested Loop` Estimates 1 Row, Actually Loops 100,000 Times

~~~text
Nested Loop
  -> ... (estimated rows=1, actual rows=100000)
  -> Index Scan ... (loops=100000)
~~~

Inspect the outer branch producing rows; multi-column stats, parameter skew, or join predicates usually matter far more than flipping `enable_nestloop`.

### Scenario D — Identical SQL Fast vs. Slow Depending on Tenant

~~~text
tenant_id=1   → 320000 rows
tenant_id=500 → ~800 rows
~~~

If the app uses shared prepared statements, investigate **generic vs. custom plans**. Never optimize solely around a tiny tenant and impose its plan on the giant tenant.

### Scenario E — `EXPLAIN` Shows Accurate Row Estimates Yet Query Is Slow

When `estimated rows ≈ actual rows`, check:

- `shared read` volume and storage wait times;
- Sort/Hash temp spills;
- Parallel worker contention;
- CPU and JIT startup cost;
- Network transfer and client row fetching;
- Lock waits;
- Expensive per-row functions inside `Filter` or `Output`.

**Accurate cardinality does not prove the cost model matches every hardware detail**, yet it sharply narrows where to investigate.

### Scenario F — Query Slows Down Right After Adding an Index

A new index can tempt the planner away from a `Seq Scan` into an `Index Scan` hitting heavy random heap I/O when costs or skew diverge from estimates. Inspect:

- Post-migration statistics;
- Actual selectivity;
- `Heap Fetches`, `Buffers`, and table correlation;
- Both large and small query parameters;
- Exact before/after plans;
- Write amplification, WAL, and index maintenance costs.

Never assume “more indexes” always equals faster queries.

### Scenario G — Query Speeds Up After `SET enable_hashjoin=off`

That indicates an alternative Merge Join or Nested Loop ran faster in that trial. Dig deeper:

- Inspect estimated vs. actual hash input size;
- Check `Batches`, `Memory Usage`, and temp I/O;
- Verify join keys and predicate pushdown;
- Test across varied parameters;
- Check whether the join unexpectedly multiplies rows.

Leaving `enable_hashjoin=off` globally across an entire application can cripple hundreds of other queries.

### Scenario H — Query Regresses After a PostgreSQL Major Upgrade

Major upgrades update planner capabilities, cost weights, cardinality estimators, collation details, and internal behaviors. Structured response:

1. Compare saved pre-upgrade and post-upgrade plans;
2. Run required post-upgrade `ANALYZE`/statistics rebuilds per upgrade docs;
3. Verify index and collation health where relevant;
4. Test across parameter cohorts and workloads;
5. Isolate specific regressed queries;
6. Apply targeted SQL/index/scoped setting fixes;
7. Keep rollback/fix-forward procedures aligned with release processes.

Never disable major planner features cluster-wide over one regressed query.

## 28. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| `Seq Scan` is always slow | Rational when reading small tables or large shares of rows |
| If an index exists, the planner must use it | The planner picks based on estimated total cost |
| `enable_seqscan=off` bans every `Seq Scan` | It penalizes `Seq Scan` heavily rather than making it impossible |
| `enable_nestloop=off` fixes every slow join | Never fixes bad row estimates or SQL semantics |
| `cost=10000` means 10 seconds | Cost is a relative unit, not milliseconds |
| `estimated rows=1` means PostgreSQL counted rows | It is a statistical estimate, not an exact runtime count |
| `actual rows` is always total node rows | Must account for `loops` and tree position |
| A plan fast in `psql` is fast in an ORM | Bind params, generic plans, client fetches, and load differ |
| `ANALYZE` guarantees perfect estimates | Sampling still struggles with extreme skew or hidden correlations |
| `pg_stats.correlation` measures tenant/status correlation | It measures physical row-order alignment of a single column |
| Extended stats solve every join estimate | Bounded utility, especially across multi-table joins |
| A `Nested Loop` with many loops is always wrong | Ideal when outer is small and inner lookup is indexed |
| `Hash Join` never spills | Uses multi-batch temp files whenever memory runs short |
| Raising `work_mem` fixes every slow `Sort` | Can trigger server RAM exhaustion under concurrency |
| `effective_cache_size` allocates cache RAM | Strictly a planner hint for costing |
| `shared read` always hits physical disk | Frequently served by OS page cache |
| A 20s query needs an index fix | It may have spent 19s waiting on a lock |
| Planned parallel workers always launch | Runtime pools may launch fewer or zero |
| `Gather` distributes work across read replicas | Parallelism runs strictly inside one PostgreSQL instance |
| `EXPLAIN ANALYZE` only previews plans | It really executes SQL, including DML |
| Generic plans are always bad | Save planning CPU when data distribution is uniform |
| `force_custom_plan` is always better | Adds heavy planning CPU overhead on high-frequency queries |
| Partial indexes always fire when SQL looks similar | Planner must prove implication; generic `$1` parameters block that |
| `UNION ALL` is a free `OR` rewrite | Emits duplicates whenever branches overlap |
| `ORDER BY` needs no tie-breaker if an index feels stable | Keyset pagination requires deterministic ordering on tied keys |
| One benchmark after a config change is conclusive | Caching, concurrency, and worker variance distort single runs |
| `pg_stat_statements` mean reflects every tenant | Skew and p99 tails get averaged away |
| A good hint today stays optimal forever | Data, schemas, stats, and versions drift—pinning turns stale |
| Once tuned, no rollback plan is needed | Every production change needs a clean recovery path |

## 29. Practice Exercises

These exercises use `plan_lab_291` and its 400,000-row dataset. Exact node names are not graded—focus on **analytical reasoning** backed by measured numbers. On tight hardware, scale down row counts and observe any resulting plan differences.

### Exercise 1 — Why Not Force Against `Seq Scan`?

For a query reading 80% of a table, explain why `Seq Scan` can outperform `Index Scan`. Discuss page reads, random heap access, and CPU work.

### Exercise 2 — Querying the Giant Tenant

~~~sql
SELECT COUNT(*)
FROM plan_lab_291.orders
WHERE tenant_id = 1;
~~~

**Expected count:** 320,000. Run `EXPLAIN` and justify the chosen plan without calling it broken merely by node name.

### Exercise 3 — Querying a Small Tenant

~~~sql
SELECT COUNT(*)
FROM plan_lab_291.orders
WHERE tenant_id = 500;
~~~

**Expected count:** 800 rows by data formula. Compare plans before and after indexing `tenant_id`.

### Exercise 4 — Reading Cost vs. Actual

Given:

~~~text
cost=0.00..20000.00 rows=1000
actual time=0.1..150.0 rows=200000 loops=1
~~~

**Question:** Which values reveal a cardinality error? Why can't you say the planner predicted 20 seconds?

### Exercise 5 — Multiplying by `loops`

A `Nested Loop` reports an inner `Index Scan` with `actual rows=1 loops=250000`.

**Question:** How many times did the inner node run? Even if each iteration is tiny, why does total runtime grow large?

### Exercise 6 — `Index Cond` vs. `Filter`

Compare `WHERE ordered_at::date = DATE '2026-05-01'` against a half-open range on `ordered_at`.

**Question:** Which form leverages a B-tree on `ordered_at` directly while preserving exact time-zone semantics?

### Exercise 7 — Two Correlated Columns

In the lab data, explain why:

~~~sql
WHERE tenant_id = 1 AND status = 'pending'
~~~

returns 0 rows despite each predicate matching tens or hundreds of thousands of rows individually.

### Exercise 8 — Broken Independence Assumption

Given `P(tenant=1)=0.8` and `P(pending)=0.2`, how many rows out of 400,000 does an independence model predict?

**Illustrative answer:** 64,000. Why is the actual count 0?

### Exercise 9 — Extended Statistics

Run `CREATE STATISTICS ... (dependencies, mcv, ndistinct)` on `(tenant_id,status)`, followed by `ANALYZE`.

**Question:** How does the estimated row count change for the combined query? Will it stay nailed to one static magic figure?

### Exercise 10 — `pg_stats`

Inspect `pg_stats` for `tenant_id` and read `most_common_vals`, `most_common_freqs`, and `n_distinct`.

**Question:** Does tenant 1 appear in the MCV list? Why don't histogram bounds replace MCV metadata completely?

### Exercise 11 — `correlation` vs. `dependencies`

Explain the difference between `pg_stats.correlation` and extended stats `dependencies`. Which captures the link between `tenant_id` and `status`?

### Exercise 12 — Statistics Target

Run `ALTER COLUMN tenant_id SET STATISTICS 500`, run `ANALYZE`, and compare stats and plans.

**Question:** Does raising the target automatically speed up every SQL query? What extra costs does it introduce?

### Exercise 13 — Custom vs. Generic Plans

Prepare `PREPARE get_orders_by_tenant(integer)` and compare `force_custom_plan` vs. `force_generic_plan` for tenants `1` and `500`.

**Task:** Record estimated/actual rows, plan nodes, and runtimes; explain why a generic plan struggles with skewed data.

### Exercise 14 — Planning Overhead

A query executes 10 million times daily: 1 ms execution, plus 1 ms extra for custom planning.

**Question:** If `force_custom_plan` is enforced app-wide, how does planning CPU shift? Which workload metrics must guide that trade-off?

### Exercise 15 — Composite Index Design

Write an index tailored to:

~~~sql
WHERE tenant_id = 500 AND status = 'pending'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20
~~~

**Suggested key:** `(tenant_id,status,ordered_at DESC,order_id DESC)`.

### Exercise 16 — Partial Indexes with Generic Plans

Why might a partial index `WHERE status='paid'` fail to apply in a generic plan using `status=$1`? Outline how to verify this behavior.

### Exercise 17 — `UNIQUE` Is Not a Hint

A query joins on `customers.customer_id PRIMARY KEY`. How does this constraint simultaneously enforce data integrity and inform planner uniqueness assumptions?

### Exercise 18 — External Merge Sort

`EXPLAIN ANALYZE` shows:

~~~text
Sort Method: external merge Disk: 600MB
~~~

**Question:** Name at least three angles to investigate before raising `work_mem`. Why does `work_mem` multiply across operators and parallel workers?

### Exercise 19 — Hash Batches

A `Hash Join` reports `Batches: 32` alongside high temp I/O. Distinguish **underestimated input size** from **insufficient `work_mem`**, and design an experiment to tell them apart.

### Exercise 20 — Zero Parallel Workers Launched

The planner expected 4 parallel workers yet launched 0. Which GUCs should you inspect, and why doesn't `SET max_parallel_workers_per_gather=8` cure global worker exhaustion?

### Exercise 21 — Lock Waits

An `UPDATE` stalls for 30 seconds. Write a `pg_stat_activity` query using `pg_blocking_pids` to locate the blocker.

**Question:** When must you fix transaction scope rather than indexes or query plans?

### Exercise 22 — Warm vs. Cold Cache

The exact same plan runs in 500 ms first and 35 ms second, with `shared read` dropping and `shared hit` climbing.

**Question:** Does that prove a planner improvement?

**Answer:** No; caching state almost certainly differed.

### Exercise 23 — JIT

Compare `EXPLAIN ANALYZE` with default JIT against `SET LOCAL jit=off` where supported.

**Question:** When can JIT startup exceed execution benefit? Why shouldn't you disable JIT globally over one tiny query?

### Exercise 24 — Partition Pruning

An `Append` scans 12 monthly partitions even though the query needs one month. Rewrite the filter as a partition-key range and explain why pruning can activate.

### Exercise 25 — Sound `Nested Loop`

A query filters `order_id=12345` and joins `customers` on PK. Why is `Nested Loop` usually ideal here, and when does a growing outer set make it slow?

### Exercise 26 — `enable_nestloop=off`

Test `SET LOCAL enable_nestloop=off` in a transaction for a lab join query.

**Question:** If `Hash Join` wins in this run, what did you prove—and what did you **not** prove yet?

### Exercise 27 — `enable_seqscan=off`

Test disabling `Seq Scan` locally for both tenant 1 and tenant 500.

**Question:** Which tenant might benefit, which might regress, and why must it stay off production defaults?

### Exercise 28 — Index-Only Scans and Visibility

An `Index Only Scan` reports high `Heap Fetches`. How do the visibility map, `VACUUM`, and update churn interact here?

### Exercise 29 — Tuning `effective_cache_size`

Explain why:

~~~sql
SET effective_cache_size = '32GB';
~~~

does not allocate 32 GB of RAM to PostgreSQL. How does it influence planner estimates instead?

### Exercise 30 — Rewriting `OR` via `UNION ALL`

For `tenant_id=1 OR customer_id=42`, prove a single row can satisfy both predicates. Why can rewriting as `UNION ALL` inflate result counts?

### Exercise 31 — `auto_explain` and Production Evidence

If a query crawls inside the app yet flies in `psql`, what diagnostic artifacts must you gather? Include at least SQL fingerprints, bind types, generic/custom plans, app traces, wait events, and sampled logged plans.

### Exercise 32 — `pg_stat_statements` and Parameter Skew

A normalized query averages 50 ms yet the endpoint's p99 hits 6 seconds.

**Question:** Why is the mean misleading? How do you slice telemetry by tenant/status/rowcount safely without leaking sensitive data?

### Exercise 33 — Biased Before/After Benchmarks

Team A changed `random_page_cost` right after an initial cold run warmed caches, claiming a “10x optimization.”

**Task:** Point out confounding variables and design a multi-round A/B benchmark logging buffer stats.

### Exercise 34 — Prerequisites for Hints

List the minimum conditions before introducing a scoped hint: verified root cause, proven regression, prior attempts with stats/indexes/rewrites, narrow scope, rollback path, multi-parameter validation, owner, and review date.

### Exercise 35 — One Query, Multiple Parameter Cohorts

Build a minimal test matrix covering tenants 1, 500, and a nonexistent tenant:

| Case | Expected Rows | Custom Plan | Generic Plan | Latency / Buffers |
| --- | ---: | --- | --- | --- |
| Tenant 1 | 320,000 | Measure | Measure | Measure |
| Tenant 500 | 800 | Measure | Measure | Measure |
| Tenant 999 | 0 | Measure | Measure | Measure |

**Task:** Explain why tuning solely for the giant tenant or solely for small tenants fails overall.

### Exercise 36 — Faster Plan, Wrong Output

A developer changes `LEFT JOIN` to `INNER JOIN`, eliminating a `Sort` and slashing runtime by 70%.

**Question:** If business rules require customers with zero orders, why is this **not** a valid optimization? How do you verify semantic equivalence prior to benchmarking?

### Exercise 37 — Slow API, Fast SQL

An endpoint returning 100,000 orders takes 12 seconds; `EXPLAIN ANALYZE` takes 150 ms.

**Task:** Propose checking connection pools, pagination, network transfer, JSON serialization, ORM hydration, client fetch behavior, and N+1 calls before touching the planner.

### Exercise 38 — Indexing Without Query Analysis

A team puts individual single-column B-tree indexes on every column of `orders`.

**Question:** Why can that slow down `INSERT`/`UPDATE` without helping key queries? Compare standalone single-column indexes against a composite index matching `WHERE + ORDER BY + LIMIT`.

### Exercise 39 — Post-Migration Bind-Type Regression

A release changes `customer_id` binds from integer to text, introducing `customer_id::text` on the indexed column side.

**Task:** Explain why the integer index stops matching cleanly; propose fixing JDBC/ORM parameter mapping and verifying the new plan.

### Exercise 40 — Writing an Optimization Report

Draft a structured report containing:

1. SQL fingerprint and reproduction parameters;
2. Baseline p50/p95 latencies, buffers, and plan;
3. Estimated vs. actual row gap and first misbehaving node;
4. Root-cause hypothesis;
5. Controlled experiment (`SET LOCAL` or SQL rewrite);
6. Confirming or refuting evidence;
7. Root-cause fix;
8. Benchmark coverage across alternative parameters;
9. Risk assessment, rollback, and post-deploy monitoring.

**Goal:** Peer-reviewable, reversible engineering decisions—not “turned off `Seq Scan` and it went fast.”

## 30. Reusable Diagnostic Queries

These queries focus strictly on **read-only inspection**. They do not build indexes, mutate server configuration, or terminate sessions. Respect access permissions and avoid hammering stressed systems with heavy `EXPLAIN ANALYZE` runs during incidents.

### 30.1. Inspect Active Planner Settings

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context
FROM pg_catalog.pg_settings
WHERE name IN (
    'enable_seqscan',
    'enable_nestloop',
    'enable_hashjoin',
    'enable_mergejoin',
    'random_page_cost',
    'seq_page_cost',
    'effective_cache_size',
    'work_mem',
    'max_parallel_workers_per_gather',
    'plan_cache_mode',
    'jit'
)
ORDER BY name;
~~~

If you spot `source='session'` or unexpected overrides, check whether **prior experiments or pooled connections leaked session settings**.

### 30.2. Check Table `ANALYZE` Freshness

~~~sql
SELECT
    relid::regclass AS relation_name,
    n_live_tup,
    last_analyze,
    last_autoanalyze,
    analyze_count,
    autoanalyze_count
FROM pg_catalog.pg_stat_all_tables
WHERE relid = 'plan_lab_291.orders'::regclass;
~~~

### 30.3. Inspect Per-Column MCVs and Histograms

~~~sql
SELECT
    attname,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds
FROM pg_catalog.pg_stats
WHERE schemaname = 'plan_lab_291'
  AND tablename = 'orders'
  AND attname IN ('tenant_id', 'status')
ORDER BY attname;
~~~

### 30.4. Inspect Existing Extended Statistics

~~~sql
SELECT
    statistics_name,
    attnames,
    kinds,
    dependencies,
    most_common_vals
FROM pg_catalog.pg_stats_ext
WHERE schemaname = 'plan_lab_291'
  AND tablename = 'orders';
~~~

### 30.5. Inspect Index Definitions

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'plan_lab_291'
  AND tablename = 'orders'
ORDER BY indexname;
~~~

### 30.6. Inspect Index Scan Counts

~~~sql
SELECT
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_catalog.pg_stat_user_indexes
WHERE schemaname = 'plan_lab_291'
  AND relname = 'orders'
ORDER BY idx_scan DESC, indexrelname;
~~~

### 30.7. Find Sessions Waiting on Locks

~~~sql
SELECT
    pid,
    datname,
    state,
    wait_event_type,
    wait_event,
    pg_catalog.pg_blocking_pids(pid) AS blockers,
    now() - query_start AS query_age
FROM pg_catalog.pg_stat_activity
WHERE wait_event_type = 'Lock'
ORDER BY query_start;
~~~

### 30.8. List Prepared Statements in Current Session

~~~sql
SELECT
    name,
    parameter_types,
    generic_plans,
    custom_plans
FROM pg_catalog.pg_prepared_statements
ORDER BY name;
~~~

### 30.9. Check Table and Index Footprint

~~~sql
SELECT
    'plan_lab_291.orders'::regclass AS relation_name,
    pg_catalog.pg_size_pretty(
        pg_catalog.pg_relation_size(
            'plan_lab_291.orders'::regclass
        )
    ) AS table_heap_size,
    pg_catalog.pg_size_pretty(
        pg_catalog.pg_indexes_size(
            'plan_lab_291.orders'::regclass
        )
    ) AS indexes_size,
    pg_catalog.pg_size_pretty(
        pg_catalog.pg_total_relation_size(
            'plan_lab_291.orders'::regclass
        )
    ) AS total_size;
~~~

### 30.10. Verify True Row Counts Across Parameter Values

~~~sql
SELECT
    tenant_id,
    COUNT(*) AS rows_for_tenant,
    COUNT(*) FILTER (WHERE status = 'paid')
        AS paid_rows,
    COUNT(*) FILTER (WHERE status = 'pending')
        AS pending_rows
FROM plan_lab_291.orders
WHERE tenant_id IN (1, 500)
GROUP BY tenant_id
ORDER BY tenant_id;
~~~

When `EXPLAIN` predicts identical rows for both tenants while actual data differs by orders of magnitude, investigate **generic plans, data skew, statistics, and selective paths**.

## 31. Production Runbook for Query Regressions

### Phase A — Capture Incident Context

Collect:

- Query or query ID plus application/ORM release;
- Database, PostgreSQL version, role, and environment;
- Affected parameter values, bind types, and request rate;
- Exact start time of the slowdown;
- End-to-end app latency vs. DB execution time;
- CPU, RAM, I/O, lock waits, vacuum/checkpoint activity;
- Any recent migrations, index builds, `ANALYZE`, config edits, or upgrades.

**Never immediately run `ALTER SYSTEM SET enable_seqscan=off`.** Cluster-wide planner switches mid-incident can regress healthy queries and obscure the real failure.

### Phase B — Isolate the Cause

<escape>**If the query is blocked:**</escape> query `pg_stat_activity` / `pg_blocking_pids` to locate holding transactions.

<escape>**If the query runs yet outputs huge sets:**</escape> review pagination, projections, row counts, and client fetches.

<escape>**If estimated rows diverge sharply:**</escape> inspect `ANALYZE`, MCVs, correlations, extended stats, and prepared parameters.

<escape>**If row estimates match yet I/O drags:**</escape> inspect buffers, cache state, access paths, index selectivity, and storage health.

<escape>**If Sort/Hash spills:**</escape> examine temp I/O, query shape, supporting indexes, scoped `work_mem`, and concurrency.

<escape>**If workers fail to launch:**</escape> inspect parallel worker caps, concurrent load, CPU usage, and leader bottlenecks.

### Phase C — Pick the Lowest-Risk Root Fix

Evaluate in priority order backed by evidence:

1. Semantic-preserving query rewrites;
2. Refreshing or refining statistics;
3. Indexes balancing read predicates/sorting against write cost;
4. Fixing bind types or prepared-plan behavior when proven;
5. Refining transaction/lock scope or I/O capacity;
6. Narrowly scoped memory, parallel, or cost tuning;
7. Temporary hints/plan pinning only under compelling necessity.

### Phase D — Benchmark Across Parameter Cohorts

Never test solely the one tenant that paged on-call. Cover:

- Giant tenants;
- Small tenants;
- Rare or nonexistent keys;
- Very recent and very old date ranges;
- Small and large `LIMIT`s;
- Realistic concurrent load.

Verify SQL correctness, estimated vs. actual rows, buffers, spills, workers, and latencies.

### Phase E — Roll Out and Monitor

For production changes:

- Assign clear ownership and blast radius;
- Execute schema/index/stats steps safely;
- Track error rates, slow-query counts, p95/p99, CPU, and I/O;
- Monitor unrelated queries too—not only the target SQL;
- Maintain tested rollback or fix-forward steps;
- Document hypotheses and outcomes to prevent cargo-cult “tricks.”

### Phase F — Retire Temporary Workarounds

Whenever `plan_cache_mode` overrides, `enable_*` toggles, cost GUCs, or temporary hints were applied:

1. Record exact scope and rationale;
2. Set a firm review/expiration date;
3. Land the permanent root-cause fix;
4. Re-verify performance **without** the workaround;
5. Remove overrides and confirm pools/sessions return to defaults;
6. Monitor closely for regressions afterward.

**A workaround with no retirement plan becomes long-term risk.**

## 32. Decision Flow: Should You Force a Plan?

~~~mermaid
flowchart TD
    A["Slow query / regression"] --> B{"Have exact SQL + bind values?"}
    B -->|No| C["Collect traces / logs / queryid"]
    B -->|Yes| D["Safe EXPLAIN / EXPLAIN ANALYZE"]
    D --> E{"Slow due to locks / network / client?"}
    E -->|Yes| F["Fix locks or application path"]
    E -->|No| G{"Estimated rows way off?"}
    G -->|Yes| H["ANALYZE, MCV, extended stats, generic/custom"]
    G -->|No| I{"I/O, sort/hash spill, workers, JIT?"}
    I -->|Yes| J["Fix SQL / index / resources from evidence"]
    I -->|No| K["Test alternative plan with SET LOCAL"]
    H --> L["Re-measure across params & load"]
    J --> L
    K --> L
    L --> M{"Root fix sufficient?"}
    M -->|Yes| N["Deploy with rollback + monitoring"]
    M -->|No| O["Investigate planner bug / scoped cost or hint"]
    O --> N
~~~

This flowchart depicts a **reasoning workflow**, not an automated script. Every production action still requires appropriate DBA privileges, security reviews, and change management.

## 33. Key Terminology

| Term | Meaning in This Lesson |
| --- | --- |
| **Query plan** | Execution operator tree chosen by PostgreSQL for a SQL query |
| **Cardinality estimate** | Planner's predicted row count at a plan node |
| **Actual rows** | Rows observed by the executor at a node; interpret alongside `loops` |
| **Cost model** | Relative cost model across scans, joins, sorts, and parallel steps |
| **`Seq Scan`** | Sequential scan reading eligible heap pages |
| **`Nested Loop`** | Iterates inner path for each outer row |
| **`Hash Join`** | Builds a hash table to match join keys |
| **Sargable predicate** | Predicate structured so indexes/access paths can exploit it directly |
| **MCV** | Most Common Values: frequent values or tuples tracked in statistics |
| **Extended statistics** | Multi-column/expression statistics aiding correlated estimates |
| **Custom plan** | Plan tailored to concrete bind parameter values |
| **Generic plan** | Reusable plan cached across varying parameter values |
| **`Index Cond`** | Predicate pushed into the index scan itself |
| **`Filter`** | Residual predicate evaluated outside index matching |
| **Spill** | Writing temporary files when sort/hash exceeds memory budget |
| **JIT** | Runtime compilation carrying startup cost for potential CPU gains |
| **Plan hint** | Directive steering plan selection without fixing bad estimates |
| **Plan regression** | Plan shift degrading workload performance |
| **Root cause** | True underlying cause of slowness—not merely a suspect node name |
| **`SET LOCAL`** | Transaction-scoped setting expiring automatically at commit/rollback |

## 34. Official PostgreSQL Documentation

The references below provide deeper reading. Always consult documentation matching your **exact PostgreSQL major version** rather than copying defaults blindly across environments.

- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): reading plans, estimated costs/rows, actual rows/loops, joins, and scans.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): `ANALYZE`, `BUFFERS`, `VERBOSE`, `SETTINGS`, and output options.
- [Planner Statistics](https://www.postgresql.org/docs/current/planner-stats.html): how optimizer statistics work.
- [Multivariate Statistics Examples](https://www.postgresql.org/docs/current/multivariate-statistics-examples.html): extended stats, dependencies, `ndistinct`, MCVs, and estimation gaps.
- [ANALYZE](https://www.postgresql.org/docs/current/sql-analyze.html): statistics collection, privileges, and sampling behavior.
- [CREATE STATISTICS](https://www.postgresql.org/docs/current/sql-createstatistics.html): syntax, statistic kinds, and applicability.
- [pg_stats](https://www.postgresql.org/docs/current/view-pg-stats.html): single-column planner statistics view.
- [pg_stats_ext](https://www.postgresql.org/docs/current/view-pg-stats-ext.html): inspecting extended statistics.
- [Planner Method Configuration](https://www.postgresql.org/docs/current/runtime-config-query.html#RUNTIME-CONFIG-QUERY-ENABLE): the `enable_*` planner switches.
- [Planner Cost Constants](https://www.postgresql.org/docs/current/runtime-config-query.html#RUNTIME-CONFIG-QUERY-CONSTANTS): `random_page_cost`, `seq_page_cost`, CPU costs, and parallel costs.
- [PREPARE](https://www.postgresql.org/docs/current/sql-prepare.html): generic vs. custom plan selection behavior.
- [Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html): `work_mem`, parallel workers, and memory resources.
- [Indexes](https://www.postgresql.org/docs/current/indexes.html): B-tree, multicolumn, partial, expression, and index-only scans.
- [Partition Pruning](https://www.postgresql.org/docs/current/ddl-partitioning.html#DDL-PARTITION-PRUNING): planning-time and execution-time pruning.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity`, `pg_stat_all_tables`, and index usage stats.
- [pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html): cumulative SQL workload tracking when enabled.
- [auto_explain](https://www.postgresql.org/docs/current/auto-explain.html): logging execution plans for slow statements automatically.
- [JIT Compilation](https://www.postgresql.org/docs/current/jit.html): JIT overhead and benefits.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): lock waits and deadlocks distinct from plan problems.

`pg_hint_plan` is an external extension outside core PostgreSQL—never assume it is pre-installed or behaves identically across versions. Check its documentation and your managed PostgreSQL policies if ever required.

## 35. Summary

When a query slows down, **never start by asking “How do I force Index Scan / Hash Join / Parallel Scan?”** Start by asking **“What evidence shows the current plan is suboptimal, and where does the error begin?”**

Common underlying causes include: **mismatched estimated vs. actual rows**, missing or stale **statistics**, unmodeled multi-column correlations, skewed parameters trapped in a **generic plan**, non-sargable predicates, indexes misaligned with `WHERE + ORDER BY`, sort/hash spills, parallel worker starvation, CPU/I/O contention, lock waits, or bottlenecks entirely outside PostgreSQL.

Switches like `enable_seqscan`, `enable_nestloop`, `enable_hashjoin`, `plan_cache_mode`, and cost GUCs shine in **controlled experiments** comparing alternative paths. Yet an alternative running faster once **never proves** it should be forced permanently. As tenant skew, data volumes, schemas, or concurrency shift, a pinned plan can turn into a severe outage.

The sustainable workflow is: **measure exact SQL and bind parameters → read `EXPLAIN ANALYZE` → pinpoint where estimates or runtime evidence diverge → test minimal hypotheses safely with `SET LOCAL` in a lab → fix true root causes in statistics, SQL, indexes, or resources → validate across workloads → deploy with monitoring and rollback**.

**Key takeaway:** *a plan change is an outcome of sound optimization, never a goal in itself*. PostgreSQL plans best when given **accurate SQL semantics, representative statistics, workload-aligned indexes, and realistic cost assumptions**. Avoiding blind plan forcing keeps systems predictable, minimizes technical debt, and preserves performance as data and traffic evolve.
