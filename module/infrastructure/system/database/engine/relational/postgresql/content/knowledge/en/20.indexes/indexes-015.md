# Measuring Index Benefits with Real Data and Workloads in PostgreSQL

**Creating an index does not automatically mean faster queries or a healthier system.** A B-tree index might slash order lookup latency from hundreds of milliseconds down to a few milliseconds, yet that same index also adds overhead to every `INSERT`, certain `UPDATE`s, and `VACUUM` work. Conversely, a query scanning nearly the entire table may still be better served by a `Seq Scan` even with an index present.

Therefore, the question to answer in a PostgreSQL project is rarely “should we index `customer_id`?”, but rather:

> **Under realistic data volumes, parameter distributions, read–write ratios, concurrency levels, and latency targets, does the candidate index deliver enough benefit to outweigh its operational cost?**

This lesson in the **Indexes** chapter of the **Database Engine Relational PostgreSQL** module focuses on **how to measure**, not just how to type `CREATE INDEX`. You will learn to design baseline-driven experiments, prepare representative datasets, model mixed read–write workloads, pick meaningful metrics, avoid false conclusions from a single `EXPLAIN ANALYZE`, and make defensible keep-or-drop decisions.

Capabilities covered:

- Identifying **which queries actually cause pain** before proposing indexes.
- Preparing test data matching production **row counts, selectivity, skew, correlation, tuple width, and update rates**.
- Reading `EXPLAIN (ANALYZE, BUFFERS)` and distinguishing `Index Cond`, `Filter`, `Rows Removed by Filter`, `Heap Fetches`, and `Sort`.
- Measuring **`INSERT` / `UPDATE` / `DELETE`** costs, WAL generation, HOT ratios, and index storage footprint.
- Using `pg_stat_statements`, `pg_stat_user_indexes`, `pg_stat_user_tables`, and `pgbench` appropriately.
- Designing **fair A/B experiments** controlling cache state, statistics, concurrency, prepared/generic plans, and trial order.
- Making decisions grounded in **SLOs and total workload impact**, rather than celebrating a single faster query.

## 1. A Good Index Must Prove Its Value

Suppose an e-commerce service runs three main database operations:

1. 2,000 lookups per second fetching a customer's newest orders.
2. 500 inserts per second creating new orders.
3. 300 updates per second transitioning order statuses.

A composite index `(customer_id, created_at DESC)` helps the first query. Leaving `status` out of the index allows status updates to retain HOT update eligibility; adding `status` to serve another query shifts the write cost profile.

Conversely, indexing `updated_at` might speed up an hourly dashboard once an hour while forcing index maintenance on every single `UPDATE` continuously.

Both are completely “valid SQL” indexes. **Workload measurements determine whether an index earns its keep.**

### Three Required Pillars of Evidence

| Pillar | Core Question | Suggested Metrics |
| --- | --- | --- |
| **Read performance** | Does the target query drop in cost? | p50/p95/p99 latency, execution time, shared block hits/reads, rows, sorts |
| **Write penalty** | Does maintaining the index degrade other paths? | `INSERT`/`UPDATE` throughput, write latency, WAL bytes, HOT ratio, lock waits |
| **Operations and resources** | What does it consume and require to maintain? | Index size, table/index bloat, replica lag, `VACUUM`, build/rebuild time |

An experiment proving only that one `SELECT` got faster while ignoring writes and storage is **insufficient** to justify keeping an index.

## 2. Start from a Testable Hypothesis

Vague goal:

> Order queries feel slow. Add an index.

Measurable hypothesis:

> Under an 80% read / 20% write workload on a 30-million-row orders table, does adding `(tenant_id, status, created_at DESC, order_id DESC)` cut p95 latency on the “25 newest orders for typical tenants” API from 120 ms below 40 ms **without raising write p95 by more than 15% or pushing replica lag past threshold**?

The second framing forces explicit decisions on:

- **Exact SQL templates** and parameter shapes.
- **Realistic data profile**: row counts and heavy-hitter tenants.
- **SLOs**: acceptable latency and throughput targets.
- **Cost budgets**: writes, WAL, storage, replication.
- **Comparison method**: baseline without candidate vs. candidate enabled.

Without predefined acceptance criteria, it is too easy afterward to cherry-pick whichever chart flatters a preferred design.

## 3. Never Benchmark on Tiny Datasets

Example:

~~~sql
CREATE TABLE tiny_orders (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL
);

INSERT INTO tiny_orders
SELECT g, g % 10 FROM generate_series(1, 100) AS g;
~~~

A 100-row table fits in just a handful of pages. PostgreSQL rightly prefers `Seq Scan` because reading all table pages beats traversing B-tree levels plus heap fetches.

That **never proves an index is useless on 100 million rows**.

Conversely, an index winning on 100 rows proves nothing about 100 million rows under heavy updates and concurrent clients.

### What Must Representative Data Capture?

| Dimension | Impact on Index Selection |
| --- | --- |
| Row and page count | Shifts `Seq Scan` vs. `Index Scan` cost ratio |
| Distinct value counts (`n_distinct`) | Determines predicate selectivity |
| Skew (non-uniform distribution) | Huge tenants vs. tiny tenants often draw different plans |
| `NULL` fraction | Impacts predicates, selectivity, and partial indexes |
| Physical heap correlation | Controls scattered random page reads |
| Row width | Determines heap page counts, cache fit, and covering gains |
| `INSERT`/`UPDATE`/`DELETE` rates | Drives index maintenance overhead and HOT eligibility |
| Aged / updated / deleted history | Shapes bloat, visibility map, and index-only scan fetches |
| Actual API parameter types | Governs generic/custom plans and partial index matching |
| Concurrency level | Drives lock waits, buffer contention, WAL, and I/O saturation |

**Uniform random synthetic data misleads badly** when production has one tenant owning 60% of rows while 99 other tenants split the remaining 40%.

## 4. Workloads Are Mixed Queries, Not a Single SELECT

A realistic service mixes operations:

| Label | Operation | Illustrative Share |
| --- | --- | ---: |
| Q1 | Fetch 25 newest orders for a tenant and status | 35% |
| Q2 | Point lookup by primary key | 20% |
| Q3 | Fetch orders for a specific customer | 15% |
| Q4 | Aggregate order counts/totals for dashboards | 10% |
| W1 | `INSERT` new order | 10% |
| W2 | `UPDATE` status or order details | 8% |
| W3 | Conditional `DELETE` / cleanup | 2% |

These percentages are **strictly illustrative**, not universal templates.

An index can dramatically speed up Q1 while slowing W2. If Q1 represents 0.1% of load and W2 represents 70%, that index may hurt overall performance.

### Weighting and Non-Linear Tail Latency

A rough summary indicator might look like:

\[
T_{\mathrm{weighted}} = \sum_i w_i \times T_i
\]

where `w_i` is the operation weight and `T_i` is average duration of operation group `i`.

However, **weighted means never replace p95/p99 or SLOs**. Tail latency spikes on one critical API hurt users even if system-wide averages improve. Solid benchmarks report **both aggregate workload impact and individual key operation metrics**.

## 5. Measurement Workflow: Baseline → Change One Index → Re-Measure

~~~mermaid
flowchart TD
    A["Collect queries, workload mix, and SLOs"] --> B["Prepare representative data and environment"]
    B --> C["Baseline: without candidate index"]
    C --> D["Record plans, latency, buffers, WAL, and writes"]
    D --> E["Add a single candidate index"]
    E --> F["ANALYZE / establish matching starting state"]
    F --> G["Re-measure reads and writes under identical load"]
    G --> H["Compare p50/p95/p99, TPS, size, HOT, and WAL"]
    H --> I{"Gains outweigh costs and stay stable?"}
    I -->|"Yes"| J["Plan rollout and post-deploy monitoring"]
    I -->|"No"| K["Revise or discard candidate index"]
~~~

For trustworthy conclusions:

1. Capture a **pre-change baseline**.
2. Change **one primary variable** per comparison.
3. Keep query shapes, parameters, volumes, read/write mix, and concurrency identical.
4. Record PostgreSQL major version, settings, statistics state, and cache warm-up.
5. Run enough iterations/duration to observe variance—never trust a single run.
6. Separate **single-query microbenchmarks** from **mixed workload benchmarks**.
7. Verify write correctness so gains never stem from skipped work.

## 6. Preparing an Isolated Lab Database

Commands below use schema `measure_idx_lab` for demonstration. **`DROP SCHEMA ... CASCADE` wipes everything in that schema.** Run strictly in a private lab database, never on production or shared databases.

Dataset characteristics deliberately include:

- **5,000 customers**.
- **300,000 orders**.
- **100 tenants** with heavy skew: tenant 1 holds roughly 60% of orders; remaining tenants split the rest.
- Rare `failed` status (~0.5%), `paid` (~19.5%), and `pending` (~80%).
- `created_at` rising alongside `order_id` to introduce physical correlation on initial insert.
- Frequently updated columns (`status`, `note`, `updated_at`) to measure write amplification.

This is **deterministic synthetic data** built for repeatable exercises—not automatically “production-like” just because it has 300k rows. In real projects, substitute sanitized production snapshots or distributions matching measured telemetry.

### 6.1. Creating Schema and Tables

~~~sql
-- RUN IN LAB DATABASE ONLY.
DROP SCHEMA IF EXISTS measure_idx_lab CASCADE;
CREATE SCHEMA measure_idx_lab;

CREATE TABLE measure_idx_lab.customers (
    customer_id integer PRIMARY KEY,
    display_name text NOT NULL,
    email text NOT NULL UNIQUE
);

CREATE TABLE measure_idx_lab.orders (
    order_id bigint PRIMARY KEY,
    tenant_id integer NOT NULL CHECK (tenant_id BETWEEN 1 AND 100),
    customer_id integer NOT NULL
        REFERENCES measure_idx_lab.customers(customer_id),
    status text NOT NULL CHECK (
        status IN ('pending', 'paid', 'failed', 'cancelled')
    ),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    total numeric(12,2) NOT NULL CHECK (total >= 0),
    note text,
    payload text NOT NULL
);

INSERT INTO measure_idx_lab.customers (
    customer_id, display_name, email
)
SELECT
    g,
    'Customer ' || g,
    'customer' || g || '@example.test'
FROM generate_series(1, 5000) AS s(g);
~~~

Both tables start with **`PRIMARY KEY`** indexes and `customers.email UNIQUE`, with no secondary indexes yet on `orders.tenant_id`/`status`/`created_at`/`customer_id`. That provides a more realistic baseline than an index-free table.

### 6.2. Loading 300,000 Orders

~~~sql
INSERT INTO measure_idx_lab.orders (
    order_id,
    tenant_id,
    customer_id,
    status,
    created_at,
    updated_at,
    total,
    note,
    payload
)
SELECT
    g::bigint,
    CASE
        WHEN g % 10 < 6 THEN 1
        ELSE 2 + (g % 99)
    END,
    1 + ((g * 37) % 5000),
    CASE
        WHEN g % 200 = 0 THEN 'failed'
        WHEN g % 5 = 0 THEN 'paid'
        ELSE 'pending'
    END,
    timestamptz '2026-01-01 00:00:00+00'
        + g * interval '1 minute',
    timestamptz '2026-01-01 00:00:00+00'
        + g * interval '1 minute',
    (50 + g % 950)::numeric(12,2),
    CASE
        WHEN g % 100 = 0 THEN 'review requested'
        ELSE NULL
    END,
    repeat('x', 80)
FROM generate_series(1, 300000) AS s(g);

VACUUM (ANALYZE) measure_idx_lab.orders;
VACUUM (ANALYZE) measure_idx_lab.customers;
~~~

**Note:** `VACUUM` must run **outside explicit transaction blocks**. Running `VACUUM (ANALYZE)` updates planner stats and visibility map bits cleanly for the lab. In production, never run unplanned heavy `VACUUM` passes solely to stage benchmarks.

### 6.3. Checking Row Counts and Skew

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status = 'pending') AS pending_orders,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'failed') AS failed_orders,
    MIN(created_at) AS earliest_created,
    MAX(created_at) AS latest_created
FROM measure_idx_lab.orders;

SELECT tenant_id, COUNT(*) AS orders_count
FROM measure_idx_lab.orders
GROUP BY tenant_id
ORDER BY orders_count DESC, tenant_id
LIMIT 10;
~~~

Expect `300000` total rows distributed approximately as:

| Status | Row Count |
| --- | ---: |
| pending | 240,000 |
| paid | 58,500 |
| failed | 1,500 |

These counts follow directly from the generator expressions rather than live timing.

`tenant_id = 1` holds roughly 60% of rows while others hold small slices—creating **sharply different selectivity between those parameter groups**.

## 7. Define Read Workloads Before Creating Indexes

Document the exact **query templates** and parameter types your app sends. Our lab tracks four queries.

### Q1 — 25 Newest Pending Orders for a Typical Tenant

~~~sql
SELECT
    order_id,
    created_at,
    total
FROM measure_idx_lab.orders
WHERE tenant_id = 27
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 25;
~~~

Combines **tenant + status filters + ordering + `LIMIT`**, making it a strong composite B-tree candidate.

### Q2 — 25 Newest Pending Orders for the Largest Tenant

~~~sql
SELECT
    order_id,
    created_at,
    total
FROM measure_idx_lab.orders
WHERE tenant_id = 1
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 25;
~~~

Though structurally identical to Q1, tenant 1 owns far more rows. Never test only a small tenant and declare SLO compliance across every customer.

### Q3 — Lookup Orders by Customer

~~~sql
SELECT
    order_id,
    created_at,
    status
FROM measure_idx_lab.orders
WHERE customer_id = 1250
ORDER BY created_at DESC
LIMIT 50;
~~~

Represents a distinct access pattern from Q1. An index keyed by tenant/status **does not cleanly serve** lookups starting on `customer_id`.

### Q4 — Full-Table Status Aggregation

~~~sql
SELECT
    status,
    COUNT(*) AS total_orders,
    SUM(total) AS sum_total
FROM measure_idx_lab.orders
GROUP BY status
ORDER BY status;
~~~

Reads all rows to aggregate sums; a B-tree on `status` **rarely helps here**. Including it keeps benchmarks honest rather than stacking queries rigged to make candidate indexes shine.

### Assign Weights Before Measuring

Illustrative read mix:

| Query | Weight |
| --- | ---: |
| Q1 (small tenant) | 40% |
| Q2 (giant tenant) | 10% |
| Q3 (`customer_id` lookup) | 30% |
| Q4 (aggregation) | 20% |

Production weights must come from real telemetry. Never cite sample weights as evidence for real systems.

## 8. Recording the Baseline with EXPLAIN

Run before adding candidate indexes:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, SUMMARY ON)
SELECT order_id, created_at, total
FROM measure_idx_lab.orders
WHERE tenant_id = 27
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 25;
~~~

Repeat for tenant 1, Q3, and Q4. Record:

- Plan shape: `Seq Scan` / `Index Scan` / `Bitmap Heap Scan` / `Sort`.
- `actual rows` and `Rows Removed by Filter`.
- `Buffers: shared hit/read`.
- `Execution Time`.
- `Sort Method` and temporary disk/memory usage if any.
- Planner estimated rows per node.

`TIMING OFF` strips per-node instrumentation overhead while keeping overall `Execution Time`. Turn per-node timing back on only when isolating slow subtrees diagnostically.

### Never Assume Plans Match Across Machines

Plans vary with PostgreSQL version, `work_mem`, `random_page_cost`, parallelism, stats, cache, and storage speed. The skill is **interpreting plans and proving why they behave as they do**, not memorizing one static text dump.

## 9. Reading Index Cond vs. Filter

These two lines mean very different things:

~~~text
Index Cond: (tenant_id = 27)
Filter: (status = 'pending')
~~~

`Index Cond` reflects predicates evaluated cleanly via index bounds. `Filter` checks residual predicates **after retrieving candidate entries/rows**.

With an index on `tenant_id` alone, PostgreSQL still fetches tenant 27 rows, filters `status`, and sorts by `created_at`.

A composite index can turn that into:

~~~text
Index Cond: ((tenant_id = 27) AND (status = 'pending'))
~~~

and simultaneously supply ordered traversal to skip `Sort`. Confirm real gains through buffer counts, scanned rows, and execution latency.

### Rows Removed by Filter

If a query returns 25 rows after discarding 100,000 via `Rows Removed by Filter`, ask:

- Does a fitting index exist?
- Are predicates selective?
- Did planner cardinality estimates miss badly?
- Did expressions or type mismatches block index usage?

Never jump straight to “large `Rows Removed by Filter` always demands an index”: queries touching most of a table or write-heavy tables may still legitimately favor sequential scans.

## 10. Add One Candidate Index and Re-Measure

For Q1/Q2, test:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON measure_idx_lab.orders (
    tenant_id,
    status,
    created_at DESC,
    order_id DESC
);

ANALYZE measure_idx_lab.orders;
~~~

Leading equality keys narrow the slice while trailing sort keys satisfy `ORDER BY created_at DESC, order_id DESC`.

Re-measure:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, SUMMARY ON)
SELECT order_id, created_at, total
FROM measure_idx_lab.orders
WHERE tenant_id = 27
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 25;
~~~

and:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, SUMMARY ON)
SELECT order_id, created_at, total
FROM measure_idx_lab.orders
WHERE tenant_id = 1
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 25;
~~~

A well-aligned plan walks just 25 entries in order and **stops early**—often a bigger win than shrinking full table scans down to a few thousand rows.

### Do Not Test Only the Query Expected to Win

After creating the index, re-run **Q3 and Q4 as well**. Confirming they do not regress or improve matters just as much. If most traffic matches Q3, you are testing the wrong candidate index.

## 11. Calculating Percentage Improvements Accurately

Suppose an illustrative table (not measured lab output) shows:

| Metric | Before | After |
| --- | ---: | ---: |
| p95 Q1 | 85 ms | 12 ms |
| p95 Q2 | 190 ms | 15 ms |
| p95 Q3 | 70 ms | 71 ms |
| p95 W2 `UPDATE` | 8 ms | 10 ms |

For latency reduction:

\[
\text{Latency reduction} =
\frac{T_{\text{before}}-T_{\text{after}}}
{T_{\text{before}}}\times100\%
\]

Q1 dropping from 85 ms to 12 ms is roughly an 85.9% reduction.

For throughput gain, the denominator flips:

\[
\text{Throughput gain} =
\frac{X_{\text{after}}-X_{\text{before}}}
{X_{\text{before}}}\times100\%
\]

**Never say “86% faster” without specifying latency vs. throughput.** Cutting latency 50% doubles unit rate in a single-thread model, yet multi-client throughput depends on concurrency, contention, and saturation points.

Figures above illustrate formulas only—**never quote them as observed benchmarks**.

## 12. Measure Repeatedly and Report Variance

Single `EXPLAIN ANALYZE` runs fluctuate due to:

- Cold vs. warm buffer cache.
- Checkpoints or autovacuum runs.
- Competing queries consuming CPU or I/O.
- JIT compilation and parallel worker startup.
- Plan flips.
- Background tasks or noisy host neighbors.

Every test scenario needs:

1. Consistent cache warm-up.
2. Multiple trials per parameter set.
3. Trials across representative parameter distributions—not one lucky ID.
4. **Median/p50**, **p95/p99** where sample size permits, plus spread.
5. Buffer hit/read counts, disk I/O, temp spill, and cache state.
6. Recorded PostgreSQL version, major settings, and dataset size.

### p95 Is Not the Slowest Single Sample

Across 1,000 calls, **p95** is the threshold below which ~95% of latencies fall—neither the maximum nor `AVG * 1.95`. **p99** exposes worse tail spikes given enough samples.

When benchmarking APIs, capture **client end-to-end latency** if SLOs include networking, pool checkout, serialization, and auth—server-side `EXPLAIN` execution time never covers full API latency.

## 13. Warm Cache vs. Cold Cache Are Separate Regimes

PostgreSQL maintains **`shared_buffers`** alongside the OS page cache. First-run reads pull pages from storage; subsequent runs enjoy cache hits.

In `EXPLAIN (ANALYZE, BUFFERS)`:

~~~text
Buffers: shared hit=...
Buffers: shared read=...
~~~

- `hit`: block already found in PostgreSQL `shared_buffers`.
- `read`: block read into `shared_buffers`, **not proof of physical disk I/O**, as OS page cache often serves it.

### Classic Trap

~~~text
Before index: run once (cold cache) → 100 ms
Create index: run second time (warm cache) → 10 ms
Claim: index gave a 90% speedup
~~~

That claim is invalid because **cache warmth changed alongside the index**.

### Rigorous Practice

- Warm up **both baseline and candidate** identically.
- Compare repeated trials at identical load.
- Record execution times alongside buffer hits/reads.
- When production workloads stay hot in cache, benchmark warm-cache behavior.
- When cold reads matter, reproduce them safely in isolated test environments without disrupting live clusters.

**Never flush OS caches or restart production servers to “measure cold cache.”**

## 14. Parameter Skew: Giant Tenants vs. Small Tenants

Our lab table deliberately gives tenant 1 most orders while other tenants stay small.

~~~sql
SELECT
    tenant_id,
    COUNT(*) AS order_count
FROM measure_idx_lab.orders
WHERE tenant_id IN (1, 27, 58, 99)
GROUP BY tenant_id
ORDER BY order_count DESC;
~~~

Benchmarking only `tenant_id = 27` looks snappy thanks to high selectivity. Tenant 1, however, matches huge row counts and can flip query plans when `LIMIT` is absent or stats vary.

### Designing Parameter Test Buckets

| Parameter Bucket | Example | Purpose |
| --- | --- | --- |
| Giant tenant | 1 | Detect skewed-distribution plan flips |
| Medium/small tenants | 27, 58, 99 | Measure typical customer behavior |
| High-frequency status | `pending` | Test low-selectivity filters |
| Rare status | `failed` | Evaluate partial/selective indexes |
| Customer with zero orders | Out-of-range ID | Measure miss lookups |
| Narrow/wide time windows | 1 day / 6 months | Test range selectivity |

Weight runs to reflect production call mix while still testing giant tenants explicitly because they often dominate p99.

## 15. Prepared Statements and Generic Plans Can Flip Results

Java/JDBC applications rarely execute fresh ad-hoc SQL literals every time; they rely on `PreparedStatement`s and server-side prepared plan caches.

Illustration:

~~~sql
PREPARE latest_orders(integer, text) AS
SELECT order_id, created_at, total
FROM measure_idx_lab.orders
WHERE tenant_id = $1
  AND status = $2
ORDER BY created_at DESC, order_id DESC
LIMIT 25;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE latest_orders(27, 'pending');

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE latest_orders(1, 'pending');

DEALLOCATE latest_orders;
~~~

PostgreSQL chooses between **custom plans** tailored to bound parameters and reusable **generic plans** depending on planning heuristics and cost.

### Why Does This Affect Index Benchmarks?

- Small and huge tenants yield starkly different selectivities.
- A partial index `WHERE status = 'failed'` is skipped by generic plans when `$2` is unknown at planning time.
- Ad-hoc literal runs (`tenant_id = 27`) can pick different plans than parameterized JDBC executions.
- Bind parameter types sent by drivers can differ from literal SQL constants in `psql`.

### Controlled Diagnostic Test

In versions supporting `plan_cache_mode`, compare inside a **lab session**:

~~~sql
SET plan_cache_mode = force_custom_plan;

PREPARE latest_orders_test(integer, text) AS
SELECT order_id, created_at, total
FROM measure_idx_lab.orders
WHERE tenant_id = $1
  AND status = $2
ORDER BY created_at DESC, order_id DESC
LIMIT 25;

EXPLAIN EXECUTE latest_orders_test(27, 'pending');
EXPLAIN EXECUTE latest_orders_test(1, 'pending');

SET plan_cache_mode = force_generic_plan;

EXPLAIN EXECUTE latest_orders_test(27, 'pending');
EXPLAIN EXECUTE latest_orders_test(1, 'pending');

DEALLOCATE latest_orders_test;
RESET plan_cache_mode;
~~~

Use this strictly as a **diagnostic probe**. Never apply `force_custom_plan` or `force_generic_plan` globally just to flatter a benchmark; weigh planning CPU vs. execution gains on real workloads.

## 16. Partial Indexes Shine on Rare Queries—Test with Exact SQL

If `failed` rows make up 0.5% of orders and queries search by tenant, evaluate a partial index in an **isolated alternative candidate test**:

~~~sql
CREATE INDEX idx_orders_failed_by_tenant
ON measure_idx_lab.orders (
    tenant_id,
    created_at DESC,
    order_id DESC
)
WHERE status = 'failed';
~~~

Literal-predicate query:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM measure_idx_lab.orders
WHERE tenant_id = 27
  AND status = 'failed'
ORDER BY created_at DESC, order_id DESC
LIMIT 25;
~~~

Containing only failed rows keeps this index tiny compared to a full composite index.

### Three Questions Before Keeping It

1. Do production queries actually filter `failed` frequently?
2. Does production SQL expose literals/constants letting the planner prove the partial predicate holds?
3. How much index-membership churn do `pending` ↔ `failed` status transitions create on `UPDATE`?

A partial index easily wins microbenchmarks on failed queries yet **still loses overall** if failed-order queries run rarely while statuses churn constantly.

## 17. Index Only Scans Require Checking Heap Fetches

To return `total` from the index without automatically reading the heap:

~~~sql
CREATE INDEX idx_orders_tenant_cover
ON measure_idx_lab.orders (
    tenant_id,
    status,
    created_at DESC,
    order_id DESC
)
INCLUDE (total);
~~~

This carries search/sort keys plus `total` as payload.

A resulting plan might show:

~~~text
Index Only Scan using idx_orders_tenant_cover ...
  Index Cond: (...)
  Heap Fetches: ...
~~~

**Never assume `Heap Fetches = 0`.** MVCC visibility rules force PostgreSQL to consult the visibility map and visit the heap whenever target pages are not all-visible.

### Why Measure After Write Churn?

Immediately after `VACUUM` on static tables, `Index Only Scan` looks spotless. Under continuous production `UPDATE`s, modified heap pages clear their all-visible bits and trigger heap fetches.

Fair evaluation includes:

- Low-churn baseline phase.
- Active `UPDATE` phase mimicking production writes.
- Tracking `Heap Fetches` alongside buffer hits/reads.
- Measuring extra index size and `UPDATE total` overhead.

**Never keep both the plain composite index and the overlapping covering index** merely because both look good; pick the net-best option.

## 18. INSERT Cost: Every Eligible Index Must Be Maintained

Inserting a row into `orders`:

~~~sql
INSERT INTO measure_idx_lab.orders (
    order_id, tenant_id, customer_id, status,
    created_at, updated_at, total, note, payload
)
VALUES (
    300001, 27, 1250, 'pending',
    '2026-10-01 12:00:00+00',
    '2026-10-01 12:00:00+00',
    199.00,
    NULL,
    repeat('x', 80)
);
~~~

writes the heap tuple and maintains every matching index. Moving from 1 PK to 6 indexes touches substantially more structures per write.

Costs do not scale strictly linearly, yet tend to raise:

- B-tree/GIN page reads and dirty writes.
- WAL bytes and full-page images.
- Index page splits.
- Buffer cache churn.
- Key extraction and expression evaluation CPU.
- Concurrent buffer/lock contention.
- Replication WAL replay overhead.

### How to Measure INSERT Overhead Properly

Do not time a single 1 ms `INSERT`. Compare:

- Rows inserted per second at target concurrency.
- p50/p95/p99 commit latency.
- WAL bytes per transaction where observable.
- CPU, I/O, and replica lag.
- Index size growth after equal insert counts.

**Both baseline and candidate must start from identical snapshots** (or balance table-growth/cache bias carefully). Testing baseline at 300k rows and candidate after 10M inserted rows is not an A/B comparison.

## 19. UPDATE Cost: Indexes Can Eliminate HOT Updates

Under PostgreSQL MVCC, `UPDATE` allocates a new tuple version. When sufficient free space remains on the heap page and no indexed attribute changes, **HOT (Heap-Only Tuple)** skips adding new index entries.

Compare two updates:

~~~sql
-- W2a: modifies note; not in the candidate tenant/status/time index.
UPDATE measure_idx_lab.orders
SET note = 'reviewed'
WHERE order_id = 10001;
~~~

~~~sql
-- W2b: modifies status; status is a key in the candidate index.
UPDATE measure_idx_lab.orders
SET status = 'paid'
WHERE order_id = 10001
  AND status = 'pending';
~~~

W2b updates keys inside `(tenant_id, status, created_at, order_id)`. Without that index, status transitions could often stay HOT; adding it eliminates HOT eligibility whenever `status` changes.

### Measuring via pg_stat_user_tables

~~~sql
SELECT
    schemaname,
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    n_dead_tup
FROM pg_stat_user_tables
WHERE schemaname = 'measure_idx_lab'
  AND relname = 'orders';
~~~

Reference ratio:

\[
\mathrm{HOT\ ratio} =
\frac{\mathrm{n\_tup\_hot\_upd}}
{\mathrm{n\_tup\_upd}}
\]

Compute only when `n_tup_upd > 0`. Because counters accumulate with reporting lag, capture **deltas over each test window** rather than reading stale historical totals.

### Never Diagnose Solely from HOT Ratio

HOT eligibility also depends on heap page free space, `fillfactor`, tuple width, and sibling indexes. Dropping HOT ratio signals a trade-off, not automatic proof that one index explains all write latency shifts.

## 20. DELETE Cost and VACUUM Overhead

`DELETE` carries two sides:

- Indexes help locate rows targeted for deletion.
- Dead tuples and index pointers are not reclaimed immediately upon `COMMIT`; MVCC visibility and `VACUUM` reclaim them later.

Safe syntax test in a **lab database** using rollback to protect seed counts:

~~~sql
BEGIN;

DELETE FROM measure_idx_lab.orders
WHERE order_id BETWEEN 200001 AND 200100
RETURNING order_id;

ROLLBACK;
~~~

To benchmark real `DELETE` workloads, use a **disposable cloned dataset** letting transactions commit realistically—rolling back skips committed dead-tuple churn, autovacuum pressure, and bloat.

### Why Rollback Benchmarks Distort Production Writes

Even when rolled back, `UPDATE`/`INSERT` still generate tuples, WAL, and cleanup work, yet diverge from sustained commit behavior, index growth, and autovacuum cycles.

Use rollback for **safe syntax exploration**; use disposable databases, real commits, and clean restores for **rigorous write benchmarks**.

## 21. Measuring WAL with EXPLAIN Where Supported

In PostgreSQL 13+, `EXPLAIN` accepts `WAL` alongside `ANALYZE`. Inside a lab database:

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL, TIMING OFF)
UPDATE measure_idx_lab.orders
SET status = 'paid',
    updated_at = clock_timestamp()
WHERE order_id BETWEEN 120001 AND 120100
  AND status = 'pending';

ROLLBACK;
~~~

Inspect reported WAL records, full-page images (`fpi`), and bytes.

**Two cautions:**

1. `EXPLAIN ANALYZE UPDATE` **actually executes the `UPDATE`**, not a dry-run estimate.
2. Wrapping in a rolled-back transaction still emits write work and diverges from live committed churn; full-page writes after checkpoints heavily skew single-statement WAL byte counts.

On older PostgreSQL releases lacking `EXPLAIN (WAL)`, omit it. On PostgreSQL 14+, you can also inspect `pg_stat_wal` where permissions allow.

## 22. Measuring WAL Bytes Across a Workload Window

`pg_stat_wal` (on supported versions) reports instance-wide WAL counters including `wal_bytes`.

~~~sql
-- PostgreSQL 14+; columns/access depend on server version and privileges.
SELECT
    wal_records,
    wal_fpi,
    wal_bytes
FROM pg_stat_wal;
~~~

Procedure:

1. Sample counters **before** starting the workload.
2. Run the fixed transaction workload.
3. Sample counters **after** completion.
4. Compute window deltas.
5. Account for concurrent traffic from sibling databases, autovacuum, or checkpoints.

**Important:** `pg_stat_wal` is **instance-global**, never scoped to one query, table, or tenant. Never blame a new index for all WAL delta observed on a busy multi-tenant cluster.

On an isolated dedicated benchmark instance, deltas stay far cleaner. In production, rely on additional instance/WAL diagnostics.

## 23. Measuring Index Size and Total Relation Footprint

Check cumulative sizes across candidate tests:

~~~sql
SELECT
    pg_size_pretty(
        pg_table_size('measure_idx_lab.orders'::regclass)
    ) AS table_size,
    pg_size_pretty(
        pg_indexes_size('measure_idx_lab.orders'::regclass)
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size('measure_idx_lab.orders'::regclass)
    ) AS total_size;
~~~

Break down per index:

~~~sql
SELECT
    i.relname AS index_name,
    pg_size_pretty(pg_relation_size(i.oid)) AS index_size
FROM pg_class AS t
JOIN pg_namespace AS n
    ON n.oid = t.relnamespace
JOIN pg_index AS x
    ON x.indrelid = t.oid
JOIN pg_class AS i
    ON i.oid = x.indexrelid
WHERE n.nspname = 'measure_idx_lab'
  AND t.relname = 'orders'
ORDER BY pg_relation_size(i.oid) DESC;
~~~

Compare footprints only under equivalent row counts and `VACUUM` states.

### Why Does Unnecessary Storage Footprint Matter?

- Increases backup and restore times.
- Consumes SSD/disk and memory cache.
- Lengthens index builds and rebuilds.
- Increases replication/recovery overhead.
- Evicts hotter pages of useful indexes from `shared_buffers`.

**A 3 GB index is not automatically bad** if it protects critical API p99 targets; a 50 MB index is still waste if nothing relies on it.

## 24. Inspecting Index Scans via pg_stat_user_indexes

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'measure_idx_lab'
ORDER BY relname, indexrelname;
~~~

These columns summarize scan activity over the stats window:

- `idx_scan`: index scan count recorded.
- `idx_tup_read`: index entries returned during scans.
- `idx_tup_fetch`: live heap tuples fetched in tracked scan types.

### Why Never Interpret idx_scan = 0 as “Redundant”?

An index with zero recent scans may:

- Enforce `PRIMARY KEY` / `UNIQUE` invariants despite rare reads.
- Power month-end or quarterly batch jobs outside the observation window.
- Have been created recently after stats reset.
- Participate in access paths whose counters behave subtly.
- Prevent severe tail-latency spikes in rare high-priority cases.

**Never drop a production index simply because `idx_scan = 0` over one afternoon.** Observe across full business cycles and audit constraints first.

## 25. Capturing Real Workload Queries with pg_stat_statements

`pg_stat_statements` aggregates runtime statistics across normalized SQL statements.

### Prerequisites

Most deployments require `shared_preload_libraries` configuration and a **PostgreSQL restart**, followed by `CREATE EXTENSION` with appropriate privileges.

~~~sql
-- Run only when preloading is already enabled, privileges permit,
-- and database administrators approve.
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

**Never modify `shared_preload_libraries` or restart production servers for a lab.** Without the extension, rely on `EXPLAIN`, app logs/telemetry, and benchmark harnesses.

### Querying Statement Stats

~~~sql
SELECT
    queryid,
    calls,
    round(total_exec_time::numeric, 2) AS total_exec_ms,
    round(mean_exec_time::numeric, 2) AS mean_exec_ms,
    round(stddev_exec_time::numeric, 2) AS stddev_exec_ms,
    rows,
    shared_blks_hit,
    shared_blks_read,
    left(query, 180) AS query_template
FROM pg_stat_statements
WHERE dbid = (
    SELECT oid
    FROM pg_database
    WHERE datname = current_database()
)
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

`pg_stat_statements` groups structurally similar queries by normalizing constants. Exact column names depend on version (`total_exec_time` in PG13+), and viewing texts across roles can be permission-restricted.

### Picking Queries to Optimize

Never rank solely by `mean_exec_time`. A 2 ms query called 2 million times consumes far more total DB time than a 200 ms query called 5 times.

Focus on:

- **High total execution time** (`calls * mean`).
- **High API p95/p99** (sourced from APM, as `pg_stat_statements` omits per-request percentiles).
- **High rows/buffers per call** relative to rows returned.
- **Queries spilling temp files or causing heavy I/O**.
- **Slow write queries** dragging down TPS or replica lag.
- **Infrequent yet strict-SLO queries**.

`pg_stat_statements.mean_exec_time` never equates to p95/p99 API latency.

## 26. pg_stat_statements Aggregates Stats—It Is Not Per-Request Tracing

Key limitations:

1. Merges small and huge tenants sharing one `queryid`.
2. Provides no per-call latency distribution for exact percentiles.
3. Counters can reset, hit entry limits (`pg_stat_statements.max`), or shift across configs.
4. Normalized SQL may be truncated depending on `track_activity_query_size`.
5. Excludes pool checkout, network serialization, and client overhead.
6. Multi-statement transactions experience lock waits and commit sync overhead outside one statement timer.

Combine **`pg_stat_statements` + application tracing + `EXPLAIN` + controlled benchmarks**—never treat it as an automated index grader.

## 27. Client-Side Benchmarking with pgbench

`pgbench` ships with PostgreSQL and accepts **custom SQL scripts** via `-f` to simulate realistic workloads.

**Run strictly against lab or dedicated staging databases.** Multi-threaded benchmarks flood I/O, emit heavy WAL, and mutate tables.

### Example Read-Only Script: latest-orders.sql

~~~text
\set tenant_id random(2, 100)
SELECT order_id, created_at, total
FROM measure_idx_lab.orders
WHERE tenant_id = :tenant_id
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 25;
~~~

Save `latest-orders.sql` locally and execute:

~~~bash
pgbench -n -c 8 -j 4 -T 60 -M prepared \
  -f latest-orders.sql \
  "postgresql://bench_user@localhost:5432/bench_db"
~~~

Flag reference:

| Flag | Meaning |
| --- | --- |
| `-n` | Skip default pgbench vacuum step before running |
| `-c 8` | 8 concurrent client connections |
| `-j 4` | 4 worker threads inside `pgbench` |
| `-T 60` | Run benchmark for 60 seconds |
| `-M prepared` | Use extended prepared query protocol |
| `-f` | Custom SQL script file |
| URI | Target **lab database**, never production |

`pgbench` reports TPS and latency summaries. Adding `-l` writes per-transaction logs for exact percentile computation—bearing in mind log size and sensitive parameters.

### Why Random Tenant 2–100 Is Insufficient

It **omits giant tenant 1**. If production routes heavy traffic to tenant 1, that script produces overly rosy numbers.

Write a weighted mix combining a tenant-1 script alongside small-tenant scripts matching measured telemetry rather than relying on uniform `random(1, 100)`.

## 28. Mixed Weighted Workloads in pgbench

Supported `pgbench` versions accept multiple `-f` scripts with **weights** (`@weight`) to control execution mix:

~~~bash
pgbench -n -c 16 -j 4 -T 120 -M prepared \
  -f latest-orders.sql@8 \
  -f update-order.sql@2 \
  "postgresql://bench_user@localhost:5432/bench_db"
~~~

Check `@weight` syntax against your exact `pgbench` version. This models an **80% read / 20% write** ratio.

Sample `update-order.sql`:

~~~text
\set order_id random(1, 300000)
UPDATE measure_idx_lab.orders
SET note = 'seen by benchmark',
    updated_at = clock_timestamp()
WHERE order_id = :order_id;
~~~

### Why You Cannot Run Back-to-Back A/B Tests on the Same Mutated Table

Run 1 leaves behind updated tuples, dead rows, cleared visibility-map bits, and altered `note` distributions. Run 2 starts from a dirty state.

Proper A/B setup:

- Restore **identical initial dataset snapshots** before A and B.
- Option A lacks the candidate index; Option B creates it cleanly.
- Run identical cache warm-up phases.
- Keep script weights, variables, and client concurrency identical.
- Measure long enough and log total completed transactions.
- Never run both trials simultaneously on shared hardware.

Even using separate databases on one host requires verifying the previous run stopped flushing I/O/checkpoints before starting the next.

### Target Load vs. Saturation Load

Two distinct regimes:

- **Fixed offered load:** hold constant requests/sec (e.g., `-R`) to test whether latency and SLO compliance improve.
- **Saturation test:** push maximum concurrency until throughput plateaus or latency blows past limits.

When comparing saturation runs where one option completes more transactions/sec, never compare p95 latency without quoting matching throughput.

## 29. Designing Realistic Write SQL Scripts

If production writes are 30% `INSERT` and 70% `UPDATE`, benchmark scripts must mirror real domain behavior:

- `INSERT` fresh unique keys referencing valid FKs.
- `UPDATE` realistic target states matching actual transitions.
- Match service transaction boundaries.
- Never induce massive constraint errors to skip real write paths.
- Never submit duplicate idempotency keys hitting `DO NOTHING` repeatedly.
- Avoid updating one single hot row constantly unless testing hot-row contention intentionally.

### Safe Sequential INSERT Generation in the Lab

On a dedicated benchmark database, create a **sequence** supplying unique IDs:

~~~sql
CREATE SEQUENCE measure_idx_lab.bench_order_id_seq
START WITH 1000000;
~~~

Sample `INSERT`:

~~~sql
INSERT INTO measure_idx_lab.orders (
    order_id, tenant_id, customer_id, status,
    created_at, updated_at, total, note, payload
)
VALUES (
    nextval('measure_idx_lab.bench_order_id_seq'),
    27,
    1250,
    'pending',
    clock_timestamp(),
    clock_timestamp(),
    199.00,
    NULL,
    repeat('x', 80)
);
~~~

Sequential B-tree PK inserts avoid random contention yet **do not mimic every ID scheme** (random UUIDv4, ULID, UUIDv7, tenant prefixes, or partitioned keys behave differently).

Across A and B, keep **ID generation, inserted row counts, tenant/status ratios, and transaction boundaries identical**.

## 30. Measure Write Overhead via Throughput and p95—Not Just EXPLAIN UPDATE

Running:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE measure_idx_lab.orders
SET status = 'paid'
WHERE order_id = 12345;
~~~

shows a single statement's plan, yet hides:

- Concurrent lock contention across sessions.
- Group commit and WAL flush latency at scale.
- Triggers and surrounding transaction logic.
- Sustained replication lag.
- Autovacuum pressure across millions of updates.
- Connection-pool tail delays.
- Shared CPU/cache/I/O contention.

Include at least these write metrics:

| Metric | Source |
| --- | --- |
| Committed TPS | `pgbench` / workload client |
| p50/p95/p99 transaction latency | Client tracing / `pgbench` `-l` logs |
| WAL bytes per window | `pg_stat_wal` / `EXPLAIN (WAL)` |
| HOT ratio | Window delta from `pg_stat_user_tables` |
| Buffer hits/reads/dirtied/written | `EXPLAIN BUFFERS` and stats |
| Index size growth | `pg_relation_size` |
| Dead tuples & vacuum activity | `pg_stat_user_tables` |
| CPU / disk saturation | Host / OS telemetry |
| Replica lag | `pg_stat_replication` |
| Lock waits | `pg_stat_activity`, `pg_locks`, app timeouts |

**Never compare an unloaded baseline `SELECT` against a saturated `UPDATE` run**—benchmark under matching workload profiles.

## 31. Measuring Only Read Latency Hides Write Amplification

Suppose a candidate index yields:

- Q1 p95 drops from 120 ms to 20 ms.
- `UPDATE status` p95 climbs from 10 ms to 14 ms.
- `INSERT` TPS falls 12%.
- WAL volume climbs 35%.
- Index size adds 6 GB.
- Replica lag stays under 1 second.

Keep or drop?

**You still cannot decide from these numbers alone**, because you must ask:

- What fraction of traffic is Q1, and is it SLO-critical?
- Are writes already near peak throughput saturation?
- Which SLOs are hard limits?
- Does 6 GB fit comfortably in budget and memory?
- Will +35% WAL saturate replication or backups at peak traffic?
- Could a leaner partial index or query tweak capture 90% of gains for far less cost?

Good measurement produces **conditional trade-off decisions**, never knee-jerk “queries got faster, keep it.”

## 32. Warm/Cold Cache Drift and A/B Ordering Bias

Running strictly:

~~~text
A (no index) → B (with index)
~~~

biases toward B if caches warmed up, or against B if autovacuum/drift kicks in. Stronger trials alternate:

~~~text
A → B → A → B
~~~

restoring identical clean snapshots and warm-ups before every trial.

### Why Re-Test A?

If the second A run finishes faster than the first A run, cache warmth or background state changed—preventing false attribution of every gain to index B.

### Never Run Heavy Destructive A/B Tests Directly in Production

In production:

- Traffic and skew shift hour by hour.
- Repeatedly building/dropping huge indexes strains locks and I/O.
- Warm caches, autovacuum, and replica lag shift dynamically.
- Two time windows never share identical client traffic.

Better flow:

1. Profile production telemetry for exact query shapes and parameters.
2. Restore sanitized snapshots to dedicated staging.
3. Run controlled A/B tests in staging.
4. Roll out incrementally to production with monitoring and abort/rollback paths.
5. Verify post-deploy SLOs against live traffic without running artificial load stress on production.

## 33. Seeing “Index Scan” Does Not Prove Meaningful Benefit

Suppose baseline `Seq Scan` took 4.0 ms and candidate `Index Scan` takes 3.5 ms. The plan switched to `Index Scan`, saving 0.5 ms in lab—hardly worth a 10% `INSERT` slowdown and extra gigabytes of index storage.

Warning signs:

- Plan flips from `Seq Scan` to `Index Scan` with negligible `Buffers` reduction.
- Index scan visits excessive heap rows due to low selectivity.
- High `Heap Fetches` during `Index Only Scan`.
- New query plans incur expensive `Sort`s because index ordering mismatches.
- Gains evaporate on giant tenants or generic plans.
- Write amplification degrades update paths.

**The goal is never forcing the planner to print “Index Scan.” The goal is reducing overall workload cost.**

## 34. When Must You Update Statistics Before Comparing Plans?

PostgreSQL relies on planner stats (`n_distinct`, histograms, most common values, physical correlation). Loading 300k rows without running `ANALYZE` leaves stale estimates that skew plan selection.

In the lab:

~~~sql
ANALYZE measure_idx_lab.orders;
~~~

Inspect column statistics:

~~~sql
SELECT
    attname,
    null_frac,
    n_distinct,
    correlation,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'measure_idx_lab'
  AND tablename = 'orders'
  AND attname IN (
      'tenant_id', 'status', 'created_at', 'customer_id'
  )
ORDER BY attname;
~~~

### Interpreting Selectivity from pg_stats

- `n_distinct`: estimated distinct count (negative values represent fraction of rows).
- `most_common_vals` & `most_common_freqs`: expose heavy skew cleanly.
- `correlation`: measures alignment between logical value order and physical heap page order.

Looking solely at `COUNT(DISTINCT tenant_id) = 100` hides the fact tenant 1 owns 60% of rows. **Frequency distributions and MCV lists govern plan quality.**

### Do Not Crank Up Statistics Targets Blindly Everywhere

Higher `STATISTICS` targets help skewed columns when planner estimates fail, yet raise `ANALYZE` time and `pg_statistic` bloat. Target specific problematic columns and measure plan changes before/after.

## 35. Multi-Column Correlation and Extended Statistics

Sometimes `tenant_id` and `status` correlate strongly (e.g., enterprise tenant mostly `paid`, trial tenant mostly `pending`). Assuming independence causes poor row estimates for:

~~~sql
WHERE tenant_id = 1
  AND status = 'paid'
~~~

PostgreSQL offers **extended statistics** to improve correlated multi-column estimates:

~~~sql
CREATE STATISTICS st_orders_tenant_status (
    dependencies,
    mcv
)
ON tenant_id, status
FROM measure_idx_lab.orders;

ANALYZE measure_idx_lab.orders;
~~~

### Does Extended Statistics Replace Indexes?

No. Statistics help the planner **estimate row counts accurately**, whereas indexes provide **fast physical access paths**. Fixing terrible cardinality estimates can fix bad plans without adding indexes—or work alongside them.

Verify estimates and plans before and after; extended statistics target specific multi-column filter combinations rather than every complex join automatically.

## 36. Never Use enable_seqscan = off as Proof of a Good Index

Testers sometimes run:

~~~sql
SET enable_seqscan = off;
~~~

That **penalizes sequential scans heavily so the planner picks alternatives**, without proving the index scan is actually faster in real life.

If an index only appears when `Seq Scan` is disabled, look for:

- Insufficient predicate selectivity.
- Stale or inaccurate statistics.
- Parameterized generic plan mismatches.
- High random I/O cost assumptions.
- A table small enough that `Seq Scan` genuinely wins.

Use planner overrides **strictly in isolated diagnostic sessions**, then restore:

~~~sql
RESET enable_seqscan;
~~~

Never change planner GUC flags globally just to claim “the index works.” Evaluate indexes under production planner settings.

## 37. Fair Comparison Across Single, Composite, and Partial Indexes

Consider three candidates for status queries:

**A — Single-column index:**

~~~sql
CREATE INDEX idx_candidate_status
ON measure_idx_lab.orders(status);
~~~

**B — Composite index:**

~~~sql
CREATE INDEX idx_candidate_tenant_status_created
ON measure_idx_lab.orders(
    tenant_id, status, created_at DESC, order_id DESC
);
~~~

**C — Partial index for failed:**

~~~sql
CREATE INDEX idx_candidate_failed
ON measure_idx_lab.orders(
    tenant_id, created_at DESC, order_id DESC
)
WHERE status = 'failed';
~~~

**Never create all three simultaneously and claim you benchmarked each one.** With all three present, the planner mixes choices while writes maintain triple overhead.

Controlled procedure:

1. Keep only baseline required indexes.
2. Benchmark baseline.
3. Reset dataset cleanly.
4. Build Candidate A only; benchmark reads + writes.
5. Reset cleanly.
6. Build Candidate B only; benchmark reads + writes.
7. Reset cleanly.
8. Build Candidate C only; benchmark reads + writes.
9. Compare across full workloads.

Never run repeated index drop/create loops like this in production—use staging clones.

## 38. Choosing Sufficiently Long Measurement Windows

A 2-second test completely misses:

- Checkpoints.
- Autovacuum runs.
- Cache eviction once working sets exceed RAM.
- WAL replay lag accumulation.
- B-tree page splits and growth.
- Sustained `UPDATE`/`DELETE` bloat.
- Connection-pool queuing spikes.

Layer test durations purposefully:

| Tier | Goal | Typical Scope |
| --- | --- | --- |
| **Single-query `EXPLAIN`** | Inspect plans and buffer I/O | 1 query × multiple parameter buckets |
| **Microbenchmark** | Compare isolated query latency | 1–5 minutes depending on system |
| **Mixed workload** | Measure read–write trade-offs under concurrency | 10–30 minutes or fixed transaction count |
| **Soak test** | Observe stability, bloat, WAL, `VACUUM`, replicas | Long enough to span maintenance cycles |
| **Production observation** | Confirm gains post-rollout | Spanning peak traffic and batch windows |

Durations are **illustrative guidelines**, not rigid quotas—run long enough to trigger the phenomena relevant to your system.

## 39. Pick a Safe Rollout Strategy with Rollback Prepared

Once benchmarks confirm value on a large busy table, deploy via `CREATE INDEX CONCURRENTLY` to avoid stalling concurrent writers:

~~~sql
-- Illustrative DDL; never run in production without a rollout plan.
CREATE INDEX CONCURRENTLY idx_orders_tenant_status_created
ON measure_idx_lab.orders (
    tenant_id, status, created_at DESC, order_id DESC
);
~~~

Key reminders:

- `CONCURRENTLY` cannot execute inside explicit transaction blocks.
- Performs multiple scans and waits on active writers and old snapshots.
- Still consumes substantial CPU, I/O, and WAL.
- Leaves an `INVALID` index behind if interrupted or failed.
- Requires progress monitoring and cleanup runbooks.

Inspect progress with `pg_stat_progress_create_index` (on supported versions):

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    phase,
    blocks_total,
    blocks_done
FROM pg_stat_progress_create_index;
~~~

### Measure Again After Production Rollout

A candidate winning in staging can still behave differently in production due to:

- Prepared statements and generic plan caching.
- Differently populated partitions.
- Higher real update rates.
- Unseen tenant skew distributions.
- Replica lag or WAL bandwidth saturation.
- Peak traffic bursts absent in staging.

Post-rollout, verify **your predefined SLOs and cost metrics**—not merely index creation success.

## 40. Post-Deploy Evaluation with pg_stat_statements

Comparing the same normalized `queryid` before and after rollout tracks:

- `calls`.
- `total_exec_time`.
- `mean_exec_time` and `stddev_exec_time`.
- `shared_blks_hit` / `shared_blks_read`.
- Rows processed.
- Application-side p95/p99 and per-tenant telemetry.

Compare **deltas across equivalent time-of-day windows** while controlling for:

- Request volume shifts.
- Giant-vs-small tenant mix shifts.
- Buffer cache hit rate shifts.
- Simultaneous code, parameter, or GUC changes.
- Concurrent migrations or background batch jobs.

If traffic surged from 1,000 req/min to 10,000 req/min after deploy, `total_exec_time` rises even if each query got dramatically faster. Never judge a rollout from one raw cumulative counter.

## 41. When Should You Drop an Index?

Candidates for removal typically satisfy:

- Not enforcing required `PRIMARY KEY` / `UNIQUE` / exclusion constraints.
- Unused by important queries across a full observation window.
- Subsumed cleanly by another index at lower combined cost.
- Write/WAL/storage maintenance outweighs marginal read benefits.
- Left over as a duplicate from migrations.
- Queries evolved away from its key columns.

Double-check first:

- Do parent `DELETE`s or FKs depend on it?
- Do month-end or annual jobs need it?
- Does a rare security/compliance query rely on it?
- How long will concurrent rebuild take if rollback is required?
- Was removal tested cleanly in staging first?

For non-constraint indexes, evaluate `DROP INDEX CONCURRENTLY` carefully respecting its restrictions—never drop production indexes automatically from context-free alert scripts.

## 42. Illustrative Decision Matrix

Suppose hypothetical fair mixed-workload results (illustrative numbers only) show:

| Criterion | No Candidate | Full Composite | Partial (`failed`) |
| --- | ---: | ---: | ---: |
| p95 latest-orders (ms) | 120 | 22 | 115 |
| p95 failed-orders (ms) | 140 | 23 | 18 |
| `INSERT` TPS | 3,000 | 2,750 | 2,940 |
| `UPDATE status` p95 (ms) | 9 | 12 | 10 |
| Added storage | 0 | 160 MB | 12 MB |

If 70% of traffic targets latest-orders, the full composite likely delivers superior overall value despite write overhead. If latest-orders is 1% of traffic while failed-orders hits strict-SLO incident triage APIs, the partial index makes far better sense.

**Never pick a winner simply by counting greener table cells.** Weigh SLOs, traffic weights, storage limits, and operational safety explicitly.

Again, these figures strictly illustrate decision methodology—**never treat them as real measured data**.

## 43. Traps When Comparing Variants Across Unequal States

Unfair bias creeps in whenever:

- Baseline ran before `VACUUM` while candidate ran right after `VACUUM`.
- Candidate ran on warm `shared_buffers` while baseline ran cold.
- Baseline tested 300k rows while candidate ran after inserting to 350k rows.
- One trial had fresh `ANALYZE` stats while the other held stale stats.
- Baseline queried tenant 1 while candidate queried tenant 27.
- One side ran SQL literals while the other hit a prepared generic plan.
- Autovacuum or checkpoints collided with only one run.
- One side ran 1 client while the other ran 32 concurrent clients.
- One side committed writes while the other rolled back.
- Triggers or FK checks differed between setups.
- An analytical batch job ran concurrently during one trial.

Real systems drift. Document conditions explicitly, equalize everything controllable, and never claim precision exceeding experimental rigor.

## 44. Never Sacrifice Correctness for Benchmark Speed

A benchmark showing faster `UPDATE status` after dropping constraints or triggers compares different business semantics. Likewise, a script executing:

~~~sql
INSERT INTO measure_idx_lab.orders (...)
VALUES (...)
ON CONFLICT DO NOTHING;
~~~

where every client submits colliding keys actually **inserts almost zero rows**, inflating TPS artificially.

Non-negotiable rules:

1. Verify actual inserted, updated, and deleted row counts match intent.
2. Mirror realistic conflict and retry rates.
3. On UPSERT benchmarks, measure both insert paths and update/conflict paths in realistic ratios.
4. Never strip permissions, constraints, or triggers just to win benchmarks.
5. Never alter column types, `fillfactor`, or payload width silently between A and B.
6. Match production role permissions and transaction boundaries when modeling applications.

**Fast throughput executing the wrong workload proves zero real-world performance gain.**

## 45. Hands-On Exercises with Suggested Answers

Exercises use `measure_idx_lab` from Section 6. When testing candidate indexes, reset/clean between designs instead of accumulating duplicate indexes. Never run write exercises in production; restrict rollbacks to syntax exploration.

### Exercise 1. Diagnose the Pain Before Indexing

**Prompt:** Query A takes 2 ms and runs 1 million times/day; Query B takes 250 ms and runs 20 times/day. Which deserves attention first?

**Answer:** Never pick from a single metric alone. Query A burns substantial total DB CPU/time (~2,000 seconds/day); Query B may violate tight interactive p95 SLOs. Inspect total execution time, p95/p99, and business impact together before prioritizing.

### Exercise 2. Why Uniform Seeds Fail Tenant Skew Tests

**Prompt:** Why does uniform data across 100 tenants misrepresent a system where tenant 1 owns 60% of rows?

**Answer:** Uniform generation masks cardinality skew, causing planner row estimates, I/O volume, and per-tenant p95 latencies to diverge dramatically from production. Seed realistic skewed distributions instead.

### Exercise 3. Capture Baseline for Q1

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT order_id, created_at, total
FROM measure_idx_lab.orders
WHERE tenant_id = 27
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 25;
~~~

**Answer:** Record plan shape, execution time, `shared hit/read`, rows scanned/removed, and `Sort` steps before creating candidate indexes—never invent timings before running.

### Exercise 4. Create an Index Targeting Q1

~~~sql
CREATE INDEX idx_exercise_latest
ON measure_idx_lab.orders (
    tenant_id, status, created_at DESC, order_id DESC
);
~~~

**Answer:** Equality keys narrow the slice while trailing sort keys align with `ORDER BY ... LIMIT 25` to stop early. Measure afterward—never assume planner selection unconditionally.

### Exercise 5. Why May Q4 Still Use Seq Scan?

~~~sql
SELECT status, COUNT(*), SUM(total)
FROM measure_idx_lab.orders
GROUP BY status;
~~~

**Answer:** Aggregating sums across the entire table reads every row anyway; scanning the heap sequentially often beats random index-assisted heap fetches.

### Exercise 6. Compute Latency Reduction Percentage

A query drops from 100 ms to 25 ms.

**Answer:** Latency reduction = `(100 - 25) / 100 = 75%`. Do not claim overall system throughput climbed 75%.

### Exercise 7. Did Index Scan Actually Pay Off?

Before: `Seq Scan` 4.0 ms; after: `Index Scan` 3.8 ms, while `INSERT` TPS fell 20%.

**Answer:** Plan change alone never justifies keeping an index. A tiny 0.2 ms read gain rarely offsets a 20% write throughput hit unless read frequency/SLOs are extreme; check stability and total workload cost.

### Exercise 8. Why Do Heap Fetches Matter?

**Answer:** `Index Only Scan` still verifies MVCC visibility; whenever heap pages lack the all-visible bit, PostgreSQL visits the heap anyway. Monitor `Heap Fetches` after real `UPDATE` churn, not just right after `VACUUM`.

### Exercise 9. Measure HOT Ratio

~~~sql
SELECT n_tup_upd, n_tup_hot_upd
FROM pg_stat_user_tables
WHERE schemaname = 'measure_idx_lab'
  AND relname = 'orders';
~~~

**Answer:** Compute `delta(n_tup_hot_upd) / delta(n_tup_upd)` across the benchmark window—never use stale cumulative totals.

### Exercise 10. Why Can Composite Indexes Slow Status Updates?

**Answer:** Because `status` sits in the index key, mutating `status` forces index maintenance, breaks HOT updates on those mutations, and increases WAL and I/O. Quantify exact write impact under realistic load.

### Exercise 11. Measure Total Index Footprint

~~~sql
SELECT
    pg_size_pretty(
        pg_indexes_size('measure_idx_lab.orders'::regclass)
    ) AS indexes_size;
~~~

**Answer:** Returns combined physical size across all indexes on `orders` at execution time.

### Exercise 12. Why Does shared read Not Equal Physical Disk I/O?

**Answer:** `shared read` counts blocks loaded into PostgreSQL `shared_buffers`, which are frequently served from OS page cache without hitting physical disk.

### Exercise 13. Should You Restart Production to Benchmark Cold Cache?

**Answer:** Never. Use isolated staging/lab environments with controlled warm-up and data snapshots rather than disrupting production caches or uptime.

### Exercise 14. Does pg_stat_statements Supply API p95 Directly?

**Answer:** No; it tracks aggregated totals, counts, means, and standard deviations. Capture p95/p99 from application APM tracing or benchmark client transaction logs.

### Exercise 15. Does a Partial Index on failed Help Every Query?

**Answer:** No; it only assists queries whose predicates prove `status = 'failed'` is implied. Queries filtering `status = 'pending'` cannot use it.

### Exercise 16. Why Might Generic Plans Skip Partial Indexes?

**Answer:** For parameterized `WHERE status = $1`, a generic plan cannot assume `$1 = 'failed'` holds across every future call, so it cannot prove the partial index predicate matches.

### Exercise 17. Spot the Heaviest Tenants

~~~sql
SELECT tenant_id, COUNT(*) AS n
FROM measure_idx_lab.orders
GROUP BY tenant_id
ORDER BY n DESC, tenant_id
LIMIT 5;
~~~

**Answer:** Exposes skew clearly so benchmarks test both giant and typical tenants instead of picking one arbitrary ID.

### Exercise 18. Why Avoid Measuring Write Performance Inside Always-Rolled-Back Transactions?

**Answer:** Rolled-back writes still emit WAL and dead tuples yet skip sustained commit sync, index growth, bloat, and autovacuum overhead. Use disposable clones and committed writes for true write benchmarking.

### Exercise 19. Change One Index at a Time or Many?

**Answer:** Change **one candidate at a time** against a reset baseline so read gains and write costs are isolated clearly; piling up multiple indexes confuses attribution.

### Exercise 20. Does idx_scan = 0 Justify Dropping an Index?

**Answer:** No; zero scans may reflect constraints (`PK`/`UNIQUE`), quarterly jobs, read replicas, or recent stats resets. Audit roles and observation windows first.

### Exercise 21. Is pg_stat_wal Scoped to One Table?

**Answer:** No; it reports instance-wide WAL counters spanning all databases, sessions, and background tasks. Isolate benchmark clusters before attributing WAL deltas to one index.

### Exercise 22. Why Does LIMIT Make Ordered Composite Indexes Compelling?

**Answer:** Matching filter + sort keys allow an ordered index scan to stop immediately after returning 25 rows instead of reading and sorting huge sets.

### Exercise 23. Evaluating an INCLUDE(total) Index

**Answer:** Inspect `Index Only Scan` eligibility and `Heap Fetches` during realistic write churn, check extra disk size, and verify whether updating `total` harms HOT ratios—never judge solely from one post-`VACUUM` `SELECT`.

### Exercise 24. When Do You Need CREATE INDEX CONCURRENTLY?

**Answer:** On large live production tables to avoid blocking concurrent writes during builds, respecting its rules: cannot run in explicit transactions, takes longer and burns I/O/WAL, and can leave `INVALID` indexes if aborted.

## 46. Minimal Index Benchmark Report Template

A concise, verifiable report captures:

| Section | Required Evidence |
| --- | --- |
| Objective | Target queries/SLOs and acceptable write/storage budgets |
| Environment | PostgreSQL version, CPU, RAM, storage, `shared_buffers`, `work_mem`, connections |
| Dataset | Row counts, table sizes, tenant/status skew, `NULL`/correlation profile |
| Workload | SQL templates, weights, concurrency, parameter buckets, transaction boundaries |
| Baseline | Plans, latency percentiles, TPS, buffers, HOT/WAL, index sizes |
| Candidate | Exact `CREATE INDEX` DDL, storage delta, build method |
| Protocol | Warm-up, duration, iteration count, A/B ordering, reset steps |
| Read results | Per-query and overall p50/p95/p99, buffer hits/reads, sorts |
| Write results | `INSERT`/`UPDATE`/`DELETE` TPS, latency, WAL, HOT ratio, locks |
| Operations | Storage growth, replica lag, autovacuum, build duration |
| Risks | Skew, generic plans, cache drift, workload evolution, data privacy |
| Decision | Keep / revise / drop; rollout schedule, monitoring, and rollback triggers |

Example conditional conclusion:

> Across 30M orders and our representative mixed workload, the candidate kept latest-orders p95 well below the 40 ms SLO across repeated trials while keeping write p95 overhead under 15%, replica lag within budget, and disk usage comfortable. Recommend scheduled concurrent rollout followed by p95, TPS, and WAL/replica lag monitoring with automated rollback triggers if thresholds breach.

That stands miles ahead of “`EXPLAIN` showed `Index Scan`, so it works.”

## 47. Common Mistakes When Measuring Index Value

1. **Checking index existence only**, never measuring real queries.
2. **Running a single `EXPLAIN`** and generalizing to the whole workload.
3. **Extrapolating from hundreds of rows** to millions of rows.
4. **Seeding uniform random data**, hiding skew and `NULL` patterns.
5. **Testing one lucky tenant**, ignoring heavy or empty parameter buckets.
6. **Skipping pre-change baselines**.
7. **Adding multiple candidate indexes at once**, muddying attribution.
8. **Measuring baseline cold and candidate warm**.
9. **Forcing `enable_seqscan = off`** and declaring victory on the resulting plan.
10. **Forgetting `ANALYZE`** after large data loads.
11. **Ignoring prepared statements/generic plans** when apps bind parameters.
12. **Reading only the scan node label**, ignoring `Sort`, `Index Cond`, `Filter`, and `Heap Fetches`.
13. **Benchmarking reads while ignoring `INSERT`/`UPDATE`/`DELETE` TPS**.
14. **Benchmarking writes inside rolled-back transactions**, masking commit/vacuum effects.
15. **Ignoring WAL volume and replica lag** on replicated clusters.
16. **Ignoring index size, backup, and rebuild duration**.
17. **Equating `shared read` directly with physical disk I/O**.
18. **Treating `pg_stat_statements` mean time as p95**.
19. **Blaming instance-global `pg_stat_wal` deltas on one query** on shared clusters.
20. **Dropping `idx_scan = 0` indexes**, breaking `UNIQUE`/`PK` or seasonal batch jobs.
21. **Benchmarking colliding `ON CONFLICT DO NOTHING` no-ops** as an `INSERT` workload.
22. **Comparing A and B under different client concurrency**.
23. **Running trials shorter than autovacuum/checkpoint intervals**.
24. **Forgetting data correctness checks** after benchmark runs.
25. **Running production `CREATE INDEX` without lock/I/O analysis or rollback steps**.
26. **Confusing database execution time with end-to-end API latency**.
27. **Omitting hardware, config, and PostgreSQL major version metadata**.
28. **Optimizing rare edge queries at heavy cost to hot write paths**.

## 48. Practical Checklist

- [ ] Identify slow queries/APIs from telemetry, never guesswork.
- [ ] Document SLOs and write/storage budgets upfront.
- [ ] Inventory existing `PRIMARY KEY`/`UNIQUE`/composite indexes first.
- [ ] Prepare datasets matching production scale, skew, correlation, and row width.
- [ ] Document SQL templates and realistic parameter buckets.
- [ ] Define read/`INSERT`/`UPDATE`/`DELETE` mix and target concurrency.
- [ ] Capture clean baselines with known data and stats state.
- [ ] Test one candidate change at a time without accumulating overlaps.
- [ ] Inspect safe `SELECT` queries via `EXPLAIN (ANALYZE, BUFFERS)`.
- [ ] Examine `Index Cond`, `Filter`, `Rows Removed`, `Sort`, and `Heap Fetches`.
- [ ] Test both giant and tiny tenants, common and rare statuses.
- [ ] Test prepared/generic plans whenever apps bind parameters.
- [ ] Equalize warm-up and trial counts across A and B.
- [ ] Record p50/p95/p99, TPS, buffers, and tail latency.
- [ ] Benchmark committed writes in disposable environments.
- [ ] Track HOT ratios, WAL deltas, index size, vacuum, and replica lag.
- [ ] Never run disruptive stress tests against production.
- [ ] Plan production builds thoughtfully, evaluating `CONCURRENTLY`.
- [ ] Verify post-rollout telemetry with clear rollback triggers.
- [ ] Summarize **measured benefits alongside real costs** in a short decision record.

## 49. Official PostgreSQL Documentation

Consult version-accurate official docs matching your PostgreSQL server major version:

- [Indexes](https://www.postgresql.org/docs/current/indexes.html) — index concepts and trade-offs.
- [Examining Index Usage](https://www.postgresql.org/docs/current/indexes-examine.html) — checking planner index choices.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — plans, `ANALYZE`, and `BUFFERS`.
- [EXPLAIN command](https://www.postgresql.org/docs/current/sql-explain.html) — options including `WAL` by version.
- [Statistics Used by the Planner](https://www.postgresql.org/docs/current/planner-stats.html) — single-column and extended statistics.
- [Index-Only Scans and Covering Indexes](https://www.postgresql.org/docs/current/indexes-index-only-scans.html) — `INCLUDE` and the visibility map.
- [Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html) — predicates and generic plan caveats.
- [Multicolumn Indexes](https://www.postgresql.org/docs/current/indexes-multicolumn.html) — key ordering and selection.
- [HOT Updates](https://www.postgresql.org/docs/current/storage-hot.html) — Heap-Only Tuples and index interactions.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — `pg_stat_user_tables`, `pg_stat_user_indexes`, `pg_stat_wal`.
- [pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html) — query statistics extension.
- [pgbench](https://www.postgresql.org/docs/current/pgbench.html) — custom scripts, latency logs, and client load generation.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — `CONCURRENTLY`, build phases, and constraints.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — MVCC cleanup and autovacuum.
- [System Information Functions](https://www.postgresql.org/docs/current/functions-admin.html) — table and index size functions.

`/current/` points to the latest release on the PostgreSQL site. When targeting older servers, switch to the exact major-version docs—especially for `pg_stat_wal`, `EXPLAIN WAL`, `pgbench`, and planner options.

## 50. Summary

**Measuring index benefits means measuring total workload impact—never a single isolated `SELECT`.**

A trustworthy discipline follows seven steps:

1. **Define query/API goals and SLOs** before optimizing.
2. **Stage representative data** capturing volume, skew, correlation, nulls, MVCC state, and parameter distribution.
3. **Record clean baselines**, then test one candidate index at a time under fair conditions.
4. **Read `EXPLAIN` and `BUFFERS`** to understand *why* plans improve rather than chasing node names.
5. **Measure both reads and writes**: latency percentiles, TPS, WAL, HOT ratios, storage growth, locks, vacuum, and replica lag.
6. **Verify with realistic parameterized workloads** rather than cherry-picked literals or uniform synthetic rows.
7. **Roll out carefully and verify live telemetry**, ready to drop or revise indexes if benefits fail to outweigh costs.

The indexes worth keeping are those helping PostgreSQL meet **latency, throughput, and correctness targets** while write overhead, WAL, storage, and operational tax **stay well within acceptable limits**. Sound conclusions always rest on measurements **under conditions mirroring real applications**, never raw index counts or isolated microbenchmarks.
