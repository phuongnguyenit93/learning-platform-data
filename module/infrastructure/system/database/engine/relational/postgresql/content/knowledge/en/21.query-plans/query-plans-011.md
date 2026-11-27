# Column Statistics, Histograms, Most-Common Values, and Correlation in PostgreSQL

Two queries with nearly identical syntax can receive completely different execution plans:

```sql
SELECT *
FROM orders
WHERE status = 'paid';

SELECT *
FROM orders
WHERE status = 'cancelled';
```

If `'paid'` accounts for 90% of orders while `'cancelled'` accounts for only 0.2%, PostgreSQL should not assume both queries return the same number of rows. The first may fit a *sequential scan*; the second may use an index to fetch a small subset of rows. Similarly, a predicate like `created_at >= ...` can return almost every row or only a handful, depending on the **distribution of timestamp values**. Even a well-structured index may go unused if PostgreSQL estimates accessing it would cost more than scanning the table.

To make these decisions, the **query planner/optimizer** relies on statistics about the data. PostgreSQL collects metrics such as NULL fraction, estimated number of distinct values, **most-common values (MCVs)**, **histogram bounds**, and **correlation** between value order and physical row placement. These form the basis for estimating *selectivity* (the fraction of rows matching a condition), *cardinality* (expected row counts at each step), and access-method costs.

This lesson explains each statistic, how to read `pg_stats`, how statistics affect `EXPLAIN`, why estimates break down when two columns are correlated, how to use `CREATE STATISTICS`, and a diagnostic workflow for when shifting data causes the planner to pick poor plans.

> **Important Distinction:** `correlation` in `pg_stats` describes the **correlation between a column's value ordering and the physical ordering of rows in the table**. It is **not** a metric indicating whether two columns like `tenant_id` and `status` depend on each other. Inter-column correlation or dependency is a separate problem, addressed using *extended statistics*.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe the role of column statistics in cardinality and cost estimation.
2. Explain how `ANALYZE` samples data and why statistics are not exact real-time row counters.
3. Read `null_frac`, `avg_width`, `n_distinct`, `most_common_vals`, `most_common_freqs`, `histogram_bounds`, and `correlation` in `pg_stats`.
4. Distinguish MCV lists from histograms and understand why MCV entries do not belong inside the histogram.
5. Reason qualitatively about `=`, `IN`, range comparisons, and `IS NULL` based on data distributions.
6. Understand negative `n_distinct` values and how distinct estimates scale with row count.
7. Understand how physical correlation affects index scan cost, as distinct from cross-column dependencies.
8. Recognize when `CREATE STATISTICS ... (dependencies, ndistinct, mcv)` is needed.
9. Diagnose stale statistics, data skew, prepared-statement generic plans, and misestimated queries.
10. Evaluate plans with `EXPLAIN (ANALYZE, BUFFERS)`, maintain statistics properly, and avoid blind configuration changes.

## 2. What Does the Planner Need to Know Before Choosing a Plan?

Suppose the `events` table has 10 million rows. Consider the query:

```sql
SELECT event_id, created_at
FROM events
WHERE tenant_id = 10
  AND status = 'paid'
  AND created_at >= TIMESTAMPTZ '2026-11-01 00:00+00'
ORDER BY created_at DESC
LIMIT 20;
```

The planner must decide among strategies such as:

- Sequentially scanning the entire table and filtering.
- Using a B-tree index to locate matching keys.
- Combining multiple indexes via bitmap scans.
- Exploiting index order to avoid a `Sort`, especially with `LIMIT`.
- In join queries, picking hash join, merge join, or nested loop, and choosing join order.

To compare costs, the planner needs estimates for:

| Planner Question | Relevant Statistics |
| --- | --- |
| Roughly how many rows does the table have? | `pg_class.reltuples` and relation size metadata. |
| How frequent is `status='paid'`? | `most_common_vals` / `most_common_freqs`; `n_distinct` when needed. |
| How many rows have `status IS NULL`? | `null_frac`. |
| What fraction matches `created_at >= cutoff`? | Histograms, MCVs if present, distribution stats, and planner estimators. |
| Do predicates on tenant and region depend on each other? | Extended statistics may be required. |
| Will index access read the heap randomly or nearly sequentially? | `correlation`, page counts, cost constants, and plan properties. |
| How wide is an average row? | `avg_width`, relation size metadata, and expression widths. |
| How many rows remain after filter/JOIN? | Combined selectivity estimates and supporting metadata. |

### 2.1. Selectivity and Cardinality

**Selectivity** of a predicate is the estimated fraction of rows expected to satisfy the condition. In the simplest case:

\[
\operatorname{selectivity} \approx
\frac{\text{number of qualifying rows}}{\text{total rows}}
\]

If a table has 100,000 rows and 2% are expected to match:

\[
\operatorname{estimated\_rows}
\approx 100000 \times 0.02 = 2000
\]

This is only an intuitive model. On real queries, PostgreSQL also incorporates relation sizes, join clauses, limits, function/operator properties, multi-column stats, and optimizer transformations.

### 2.2. Estimates vs. Actuals

`EXPLAIN` might show:

```text
Seq Scan on events  (cost=... rows=500 width=...)
  Filter: (status = 'paid')
```

`rows=500` is the **planner's estimate** for that node. PostgreSQL did not scan and count 500 exact rows when running plain `EXPLAIN`.

With:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM events
WHERE status = 'paid';
```

PostgreSQL **executes the query** and then reports actual row counts, timings, and buffer accesses. When data is heavily skewed or statistics are stale, estimated rows and actual rows can diverge sharply.

Do not swap `EXPLAIN` for `EXPLAIN ANALYZE` carelessly on write statements: `ANALYZE` inside `EXPLAIN` actually runs the statement.

## 3. PostgreSQL Statistics Sources

PostgreSQL stores planner statistics in internal catalogs, notably `pg_statistic`. The user-friendly view is **`pg_stats`**.

```sql
SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    avg_width,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds,
    correlation
FROM pg_stats
WHERE schemaname = 'public'
  AND tablename = 'events'
ORDER BY attname;
```

Here `public.events` is purely illustrative for the overview; from Section 4 onward, we build a concrete lab table.

### 3.1. pg_stats Is Not pg_stat_user_tables

Two view families are frequently confused:

| Source | Purpose |
| --- | --- |
| `pg_stats` | **Per-column** value distribution: `null_frac`, MCVs, histograms, correlation, etc. |
| `pg_stats_ext` | **Multi-column** statistics from statistics objects, where supported by the version. |
| `pg_stat_user_tables` | Table activity stats: scan counts, tuple changes, last ANALYZE/vacuum timestamps, etc. |
| `pg_class` | Relation metadata, including estimated `reltuples` and `relpages`. |
| `pg_statistic` | Internal statistics catalog, not the starting point for learners. |

Having a `pg_stat` prefix does not mean every view updates on every query. `pg_stats` exposes snapshots collected by `ANALYZE`, while runtime activity views have their own collection cycles and mechanics.

### 3.2. Statistics Are Not SQL Invariants

Seeing `n_distinct=100` is an **estimate**, not a unique constraint. When many rows are inserted after ANALYZE, stored statistics may lag even though indexes and underlying data have changed.

### 3.3. Access Permissions

`pg_stats` is designed so users only see statistics for tables they have appropriate privileges on, avoiding leaks from restricted tables. Conversely, monitoring administrators must still be cautious: MCV lists on sensitive columns can expose **real data values** if copied verbatim into logs or public tickets.

## 4. Building a Skewed and Correlated Lab Dataset

We generate 50,000 synthetic events with these characteristics:

- `tenant_id=1` appears far more often than other tenants.
- `region='north'` correlates tightly with `tenant_id=1`.
- `status` distribution differs sharply across tenants/regions.
- `promo_code` is mostly NULL.
- `amount` consists mostly of low values with a small tail of large values.
- `created_at` increases in insertion order, producing observable physical correlation.

Run this only in a **practice database**; never insert test data into production tables.

### 4.1. Create Schema and Table

```sql
CREATE SCHEMA IF NOT EXISTS query_stats_lab;

CREATE TABLE query_stats_lab.events (
    event_id bigint PRIMARY KEY,
    tenant_id integer NOT NULL,
    region text NOT NULL,
    status text NOT NULL,
    customer_id bigint NOT NULL,
    amount numeric(12, 2) NOT NULL,
    created_at timestamptz NOT NULL,
    promo_code text
);
```

### 4.2. Populate Deterministic Synthetic Data

```sql
INSERT INTO query_stats_lab.events
    (event_id, tenant_id, region, status,
     customer_id, amount, created_at, promo_code)
SELECT
    g::bigint AS event_id,
    CASE
        WHEN g % 10 < 7 THEN 1
        ELSE 2 + (g % 9)
    END AS tenant_id,
    CASE
        WHEN g % 10 < 7 THEN 'north'
        ELSE 'south'
    END AS region,
    CASE
        WHEN g % 10 < 7 THEN
            CASE WHEN g % 5 < 4 THEN 'paid'
                 ELSE 'pending' END
        ELSE
            CASE WHEN g % 3 = 0 THEN 'paid'
                 ELSE 'cancelled' END
    END AS status,
    100000 + (g % 30000) AS customer_id,
    CASE
        WHEN g % 100 < 3 THEN 5000 + (g % 3000)
        ELSE 50 + (g % 500)
    END::numeric(12, 2) AS amount,
    TIMESTAMPTZ '2025-01-01 00:00+00'
        + (g * INTERVAL '1 minute') AS created_at,
    CASE
        WHEN g % 20 = 0 THEN 'PROMO-' || (g % 11)::text
        ELSE NULL
    END AS promo_code
FROM generate_series(1, 50000) AS series(g);
```

Run once on an empty table. Re-running it will fail on the `event_id` primary key. Values follow artificial formulas for reproducibility; **do not extrapolate real business behavior from this synthetic distribution**.

### 4.3. Verify Logical Data Counts

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE tenant_id = 1) AS tenant_1_rows,
    COUNT(*) FILTER (WHERE region = 'north') AS north_rows,
    COUNT(*) FILTER (WHERE promo_code IS NULL) AS no_promo_rows,
    MIN(created_at) AS earliest_event,
    MAX(created_at) AS latest_event
FROM query_stats_lab.events;
```

From `generate_series(1,50000)`, the designed totals are:

| Metric | Row Count |
| --- | ---: |
| Total events | 50,000 |
| `tenant_id=1` | 35,000 (70%) |
| `region='north'` | 35,000 (70%) |
| `promo_code IS NULL` | 47,500 (95%) |

The fact that `tenant_id=1` and `region='north'` coincide **on the exact same rows** is central to the extended statistics section later.

### 4.4. Inspect Actual Distribution via GROUP BY

```sql
SELECT
    status,
    COUNT(*) AS actual_rows,
    ROUND(
        COUNT(*)::numeric * 100
            / SUM(COUNT(*)) OVER (),
        2
    ) AS actual_percent
FROM query_stats_lab.events
GROUP BY status
ORDER BY actual_rows DESC;
```

This counts the actual table data, **unlike** reading sampled MCV estimates.

Inspect the joint distribution:

```sql
SELECT
    tenant_id,
    region,
    status,
    COUNT(*) AS actual_rows
FROM query_stats_lab.events
GROUP BY tenant_id, region, status
ORDER BY actual_rows DESC, tenant_id, region, status;
```

### 4.5. Add Indexes for Plan Experiments

```sql
CREATE INDEX idx_events_tenant_status_time
ON query_stats_lab.events
    (tenant_id, status, created_at DESC);

CREATE INDEX idx_events_created
ON query_stats_lab.events (created_at);

CREATE INDEX idx_events_amount
ON query_stats_lab.events (amount);
```

Indexes provide **access paths**; statistics provide **information to choose among access paths**. Creating an index does not replace `ANALYZE`, and raising statistics targets does not create an index.

### 4.6. ANALYZE the Lab Table

```sql
ANALYZE query_stats_lab.events;
```

This step is essential so PostgreSQL gathers statistics once data is loaded. Without `ANALYZE`, the planner relies on very limited metadata or default/initial estimates; depending on when autovacuum runs, stats may be gathered automatically later, but in a lab we trigger `ANALYZE` explicitly for clean observation.

## 5. How Does ANALYZE Gather Statistics?

`ANALYZE` samples table rows and estimates distributions. For huge tables, PostgreSQL normally **does not scan and retain every value from every row** just to compute histograms or MCVs. Sampling algorithms, sample sizes, and internal details can evolve across PostgreSQL major versions.

### 5.1. ANALYZE Is Not VACUUM

```sql
ANALYZE query_stats_lab.events;
```

Its primary purpose is refreshing optimizer statistics.

```sql
VACUUM (ANALYZE) query_stats_lab.events;
```

Runs VACUUM and collects statistics. Still:

- `ANALYZE` does **not** remove dead tuples like VACUUM.
- `VACUUM` is not a prerequisite for gathering column distributions.
- Match the command to the goal: estimation errors point to checking `ANALYZE` first, while bloat or MVCC cleanup calls for dedicated VACUUM analysis.

### 5.2. ANALYZE Uses Sampling, Not Exact Guarantees

For `status` with only three values, a sample captures ratios quite accurately. For rare values, extreme skew, or high cardinality, sampling can miss important values. Estimates across two separate `ANALYZE` runs can differ slightly.

Never build business logic on `pg_stats.most_common_freqs` to compute **exact** sales or customer shares. Use proper `SELECT COUNT(*)` / aggregations on the data itself when exact business numbers are needed.

### 5.3. Observing ANALYZE Progress

```sql
ANALYZE VERBOSE query_stats_lab.events;
```

`VERBOSE` causes PostgreSQL to emit extra details on statistics collection depending on version and client. Do not treat a single log line format as identical across all PostgreSQL major versions.

### 5.4. ANALYZE Changes Plans, Not Table Data

Running `ANALYZE` never alters business data in the table. Yet the very same `SELECT` can switch execution plans afterward because the planner computes **different row estimates and costs**.

This explains why a query sometimes “suddenly speeds up” after `ANALYZE` without adding any indexes. Conversely, when sampling cannot represent a severely skewed or correlated distribution, plain `ANALYZE` alone may not suffice.

## 6. Core Fields of pg_stats

Sample query:

```sql
SELECT
    attname,
    null_frac,
    avg_width,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds,
    correlation
FROM pg_stats
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'events'
ORDER BY attname;
```

Interpretation table:

| Field | Meaning | Notes |
| --- | --- | --- |
| `attname` | Name of the analyzed column. | A column may lack a row before ANALYZE or if stats were not collected. |
| `null_frac` | Estimated fraction of NULL values. | Typically between 0 and 1. |
| `avg_width` | Estimated average column value width in bytes per stats mechanics. | Not character length for Unicode strings. |
| `n_distinct` | Estimated distinct count or negative fraction of total rows. | Negative does not mean a negative count of distinct values. |
| `most_common_vals` | Array of frequently occurring values. | May be NULL if no MCV list is stored. |
| `most_common_freqs` | Estimated frequencies matching `most_common_vals` element-for-element. | Fraction of total relation rows, not only non-NULL rows. |
| `histogram_bounds` | Bucket boundaries dividing **non-MCV** values into roughly equal-frequency bins. | Not present for every column. |
| `correlation` | Correlation between column value ordering and physical row ordering. | Not inter-column dependency. |

`pg_stats` also exposes `inherited` and specialized fields for arrays/ranges or other statistics depending on data type and PostgreSQL version.

### 6.1. pg_stats Columns Themselves Can Be NULL

Seeing `histogram_bounds IS NULL` does not mean a column lacks a distribution. PostgreSQL may skip building a histogram when a column has few distinct values mostly captured by MCVs, when the statistics target limits it, when the type/operator class lacks ordering support, or before statistics are gathered.

Likewise, `correlation` can be NULL if the data type lacks suitable ordering operators or sufficient data.

### 6.2. Estimated Ratios Are Not Constraints

Seeing `null_frac=0` does **not** mean the column has a `NOT NULL` constraint; the sample simply contained no NULLs. Only `NOT NULL`, proper constraints, or schema definitions enforce database invariants.

Seeing `n_distinct=-1` does **not** guarantee `UNIQUE`; it is a distinctness estimate, not an enforced uniqueness rule.

## 7. null_frac: Fraction of Missing Values

In the lab table, `promo_code` is NULL in ~95% of rows. After `ANALYZE`:

```sql
SELECT
    attname,
    null_frac
FROM pg_stats
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'events'
  AND attname IN ('promo_code', 'status', 'amount');
```

Expected observations:

- `promo_code` shows `null_frac` close to **0.95**.
- `status` and `amount` are declared `NOT NULL`, so lab data contains no NULLs.

The planner uses this information when estimating:

```sql
SELECT COUNT(*)
FROM query_stats_lab.events
WHERE promo_code IS NULL;
```

and:

```sql
SELECT COUNT(*)
FROM query_stats_lab.events
WHERE promo_code IS NOT NULL;
```

### 7.1. Intuitive Formulas

If a table has \(N\) rows and `null_frac=f`:

\[
\operatorname{rows}(col\ IS\ NULL) \approx Nf
\]

\[
\operatorname{rows}(col\ IS\ NOT\ NULL) \approx N(1-f)
\]

With 50,000 rows and `f≈0.95`:

```text
IS NULL     ~47,500 rows
IS NOT NULL ~ 2,500 rows
```

Actual row counts may vary due to sampling error, stale stats, MVCC snapshots, and other transformations.

### 7.2. NULL Is Not Stored in MCV Like an Ordinary Value

The proportion of SQL NULLs is tracked separately in `null_frac`. Never look for a `'NULL'` string in `most_common_vals` and mistake it for SQL NULL: `'NULL'` is an ordinary text value, whereas SQL `NULL` denotes a missing/unknown value.

Likewise, `WHERE promo_code = NULL` does not match NULLs in SQL; you must use `IS NULL`.

## 8. avg_width: Why Row Width Affects Plans

Consider two queries both expected to return 100,000 rows:

```sql
SELECT event_id
FROM query_stats_lab.events;

SELECT *
FROM query_stats_lab.events;
```

The second transfers and processes wider tuples; operators like Sort, Hash Join, and HashAggregate are sensitive to intermediate tuple width. `avg_width` helps the planner estimate memory and data-volume costs accordingly.

### 8.1. avg_width Is Not On-Disk Table Size

For `text` or `numeric` columns, `avg_width` in statistics does not translate 1-to-1 into heap tuple storage, TOAST storage, page-header overhead, or index footprint. You cannot sum `avg_width` across columns and expect it to match `pg_relation_size(table)`.

To measure physical storage size, use dedicated size functions:

```sql
SELECT
    pg_size_pretty(
        pg_relation_size('query_stats_lab.events')
    ) AS heap_size,
    pg_size_pretty(
        pg_total_relation_size('query_stats_lab.events')
    ) AS total_size;
```

### 8.2. Column Projection Matters Too

`SELECT *` generally incurs more network and deserialization cost than selecting only needed columns. However, do not jump to claiming every `SELECT *` forces a Seq Scan; the planner still considers filters, indexes, row counts, and row width.

## 9. n_distinct: Estimated Distinct Value Count

`n_distinct` is one of the most commonly misunderstood statistics because it can be negative.

### 9.1. Positive Values

If `n_distinct = 5`, PostgreSQL estimates roughly **5 distinct values** in that column. This is not an invariant guarantee; data and statistics evolve over time.

In our lab, `status` takes only three values (`paid`, `pending`, `cancelled`). With a representative sample, `n_distinct` is typically 3.

### 9.2. Negative Values

PostgreSQL uses negative `n_distinct` to represent **distinct values as a fraction of total rows** when distinctness is expected to grow proportionally with table size.

Illustrative examples:

| `n_distinct` | Practical Meaning on a Table of N Rows |
| ---: | --- |
| `100` | Roughly 100 distinct values. |
| `-1` | Roughly N distinct values. |
| `-0.5` | Roughly 0.5 × N distinct values. |
| `-0.1` | Roughly 0.1 × N distinct values. |

This encodes an **estimate scaling with relation size**, not a negative count.

### 9.3. Comparing Against Actual Data

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT tenant_id) AS actual_tenants,
    COUNT(DISTINCT status) AS actual_statuses,
    COUNT(DISTINCT customer_id) AS actual_customers,
    COUNT(DISTINCT created_at) AS actual_timestamps
FROM query_stats_lab.events;
```

And statistics:

```sql
SELECT attname, n_distinct
FROM pg_stats
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'events'
  AND attname IN (
      'tenant_id', 'status', 'customer_id', 'created_at'
  )
ORDER BY attname;
```

The two queries measure via **different mechanisms**: `COUNT(DISTINCT ...)` scans live data, whereas `pg_stats` returns sampled estimates from the last `ANALYZE`.

### 9.4. n_distinct and Equality Selectivity

When `col = value` is **not** in the MCV list, the planner estimates selectivity using the remaining non-MCV frequency mass, `n_distinct`, and supporting metadata. Under a uniform non-NULL distribution, intuition gives:

\[
P(col=x) \approx \frac{1}{\text{number of distinct values}}
\]

Under skewed data, however, using `1 / n_distinct` for every value fails badly—which is why PostgreSQL maintains MCVs.

## 10. Most-Common Values (MCVs)

MCVs are values occurring frequently enough to store individually alongside a matching frequency array.

```sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'events'
  AND attname IN ('tenant_id', 'region', 'status', 'promo_code')
ORDER BY attname;
```

### 10.1. Pairing Values and Frequencies

Illustrative example (not guaranteed sampling output):

```text
most_common_vals  = {paid,pending,cancelled}
most_common_freqs = {0.70,0.10,0.20}
```

Elements at the same array index correspond to the same value:

- `paid` → 70%.
- `pending` → 10%.
- `cancelled` → 20%.

For non-NULL `status`, frequencies sum near 1 if all three values fit in MCV. When only a subset of distinct values are kept in MCV or NULLs exist, the sum of `most_common_freqs` can be **less than 1**.

### 10.2. Frequencies Are Fractions of Total Rows

Suppose a hypothetical table has:

| Value | Row Count |
| --- | ---: |
| `paid` | 600 |
| `pending` | 200 |
| `cancelled` | 100 |
| `NULL` | 100 |
| **Total** | **1000** |

Then:

- `null_frac = 0.1`.
- If all statuses appear in MCV, frequencies are approximately `0.6`, `0.2`, `0.1`.
- Sum of MCV frequencies = `0.9`, plus `null_frac` = `1`.

**Do not divide frequencies by `(1 - null_frac)`** when you want total table share. Only normalize by `(1 - null_frac)` when explicitly computing conditional proportions among non-NULL rows—and state that denominator clearly.

### 10.3. Equality Lookup for a Common Value

```sql
SELECT event_id, created_at
FROM query_stats_lab.events
WHERE status = 'paid';
```

If `'paid'` has a very high frequency, PostgreSQL estimates a large row count. Using an index to retrieve most of a table can incur far more random heap I/O than a sequential scan, so the planner may choose Seq Scan even if an index exists on `status`.

### 10.4. Equality Lookup for a Rare Value

```sql
SELECT event_id, created_at
FROM query_stats_lab.events
WHERE status = 'cancelled';
```

When `'cancelled'` is much rarer, an index becomes far more attractive. Still, low frequency alone does not guarantee an Index Scan: projected columns, table size, cache state, index layout, and estimated cost all factor in.

### 10.5. MCVs Do Not Contain Every Value

If a column has millions of distinct values, PostgreSQL only stores the most frequent ones allowed by the statistics target and sampling; **values absent from the MCV list do not automatically have frequency zero**.

When a value is missing from MCV, the planner falls back on remaining-frequency / histogram / `n_distinct` estimators.

### 10.6. Newly Introduced Values May Not Be Represented Yet

Suppose an application inserts millions of rows with a new status `'queued'` after the last `ANALYZE`. Stale `pg_stats` knows nothing about `'queued'`, so plans built on outdated stats can misestimate severely. Always verify `ANALYZE` freshness and data churn rather than reading MCVs once.

## 11. Histograms: Quantile Bounds of the Remainder

An MCV list works well for repeated discrete values. For columns like `amount` or `created_at` with many distinct values, the planner also needs a map of **how values are spread along the numeric or time axis** to estimate range predicates.

That is the role of **`histogram_bounds`**.

```sql
SELECT
    attname,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds
FROM pg_stats
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'events'
  AND attname IN ('created_at', 'amount')
ORDER BY attname;
```

### 11.1. Histograms Do Not Use Equal-Width Intervals

Suppose 1,000 values cluster tightly between 0–10 with very few in 100–1000.

An **equi-depth (quantile) histogram** places closely spaced bounds in dense regions and wider gaps in sparse regions:

```text
Ascending value axis

0  1  2  3  4    8       100                  1000
|--|--|--|--|----|--------|---------------------|
  ^ closer boundaries in dense data region
                        ^ wider spacing in sparse data region
```

Never read `histogram_bounds` as “every bucket has equal numeric width.” Its goal is dividing observations into buckets of roughly equal probability mass, **not equal arithmetic intervals**.

### 11.2. PostgreSQL Histograms Normally Exclude MCVs

This is a critical detail:

> **`histogram_bounds` is built from values NOT in the MCV list and NOT NULL.**

Very frequent values live in MCV so they do not skew the histogram buckets. When estimating a range condition, the planner combines:

1. Frequencies of qualifying MCV values.
2. Estimates over the remainder from the histogram.
3. `null_frac` and other relevant metadata.

Therefore, **do not sum histogram bucket shares as if they cover 100% of rows**. The histogram covers only the non-NULL, non-MCV remainder.

### 11.3. Number of Histogram Bounds

With a default statistics target of 100, a histogram can have up to roughly `target + 1` bounds where applicable. Not every column has exactly 101 bounds:

- Low-cardinality columns may have all values captured in MCV.
- Certain data types or operators lack histogram support.
- Sampling and target settings can yield shorter lists.
- Exact mechanics can vary across PostgreSQL versions.

Inspect actual table metadata instead of assuming a hardcoded bound count in `pg_stats`.

### 11.4. Point-Bound Example

Suppose an illustrative histogram has 6 bounds:

```text
histogram_bounds = {10, 20, 30, 60, 120, 400}
```

The five intervals between consecutive bounds hold roughly equal counts of **non-NULL, non-MCV observations**:

```text
[10,20], [20,30], [30,60], [60,120], [120,400]
```

Numeric span grows wider toward the right, while observation count per bucket stays balanced. These numbers **illustrate the principle only**, not actual lab output.

### 11.5. Estimating Range Predicates

Query:

```sql
SELECT event_id, amount
FROM query_stats_lab.events
WHERE amount >= 1000;
```

In our lab dataset, most amounts are under 550 while a small slice starts at 5000+. Histograms and MCVs let the planner recognize that high amounts are rare, avoiding a naive uniform min-to-max guess.

Another query:

```sql
SELECT event_id, created_at
FROM query_stats_lab.events
WHERE created_at >= TIMESTAMPTZ '2025-02-01 00:00+00';
```

The histogram on `created_at` lets the planner estimate what share of timestamps fall past the cutoff—without counting actual rows at planning time.

### 11.6. Interpolation and Error

When a predicate boundary falls **between two histogram bounds**, the planner interpolates or applies type/operator-specific selectivity estimators. Exact formulas vary by operator and type.

Large errors arise when:

- Values spike tightly inside a single bucket gap.
- Narrow spikes miss MCV inclusion.
- Predicates correlate with other columns.
- New data arrives after the last `ANALYZE`.
- A partitioned table has varying distributions across partitions.

**A histogram is a probabilistic summary—neither an index nor a copy of the data.**

## 12. Distinguishing Histograms from width_bucket and Percentiles

A planner histogram differs from an analytical SQL histogram you query directly.

### 12.1. Building Equal-Width Buckets in SQL

```sql
SELECT
    width_bucket(
        amount,
        0::numeric,
        8000::numeric,
        8
    ) AS bucket,
    COUNT(*) AS observations
FROM query_stats_lab.events
WHERE amount >= 0
  AND amount < 8000
GROUP BY bucket
ORDER BY bucket;
```

Here `width_bucket` slices `[0, 8000)` into eight **equal-width intervals**. Bucket row counts will be heavily skewed because most amounts sit in `0–1000`.

By contrast, `pg_stats.histogram_bounds` chooses cut points so each interval holds roughly equal numbers of **non-MCV** observations.

### 12.2. Percentiles Are a Different Problem

```sql
SELECT
    percentile_cont(0.5)
        WITHIN GROUP (ORDER BY amount::double precision)
        AS median_amount,
    percentile_cont(0.95)
        WITHIN GROUP (ORDER BY amount::double precision)
        AS p95_amount
FROM query_stats_lab.events;
```

`percentile_cont` computes exact quantiles from **live queried rows**; it does not read `pg_stats.histogram_bounds` as official business reporting metrics.

Never report a bound from `pg_stats` as an “official p95” without stating definitions, cohorts, NULL handling, and sampling variance.

### 12.3. MCV vs. Histogram vs. Percentile

| Tool | Question Answered | Typical Purpose |
| --- | --- | --- |
| `most_common_vals` | Which values occur most frequently? | Planner equality/range estimation. |
| `most_common_freqs` | How common is each frequent value? | Planner selectivity estimation. |
| `histogram_bounds` | How are non-MCV values spread along the axis? | Planner range estimation. |
| `width_bucket` | Which fixed-width bin does a row belong to? | Custom SQL reporting histograms. |
| `percentile_cont/disc` | What is the exact quantile threshold computed by a query? | Business analytics. |

## 13. Correlation: Physical Order vs. Value Order

In `pg_stats`, `correlation` typically ranges from **-1 to +1**:

- Near **+1**: column values tend to increase alongside physical heap row order.
- Near **-1**: column values tend to decrease alongside physical heap row order.
- Near **0**: physical row order and column values have little linear/monotonic alignment under this measure.

PostgreSQL uses this to estimate how much *random heap page access* an index range scan will incur.

### 13.1. Why Physical Correlation Matters

Suppose there is a B-tree index on `created_at`.

**Case A: rows inserted in ascending timestamp order**

```text
Heap page 1: Jan 01 -> Jan 02
Heap page 2: Jan 03 -> Jan 04
Heap page 3: Jan 05 -> Jan 06
...

Index scan by time:
  hits nearby heap pages
```

**Case B: rows inserted in random timestamp order**

```text
Heap page 1: Jan 08, Jan 01, Jan 15
Heap page 2: Jan 03, Jan 20, Jan 02
Heap page 3: Jan 11, Jan 05, Jan 17
...

Index scan by time:
  may have to jump across many heap pages
```

When consecutive index entries point to clustered heap pages, an index range scan triggers far less random I/O. When heap placement is scrambled, the planner prices index heap fetches higher relative to sequential or bitmap scans.

### 13.2. Observing Correlation in the Lab

```sql
SELECT
    attname,
    correlation
FROM pg_stats
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'events'
  AND attname IN (
      'event_id', 'tenant_id', 'status', 'amount', 'created_at'
  )
ORDER BY attname;
```

Because the generator inserts in ascending `g`, `event_id` and `created_at` rise together and typically show correlation near **+1** right after loading and analyzing the fresh lab table.

Conversely, `status` and `tenant_id` are assigned via modulo/CASE, so heap placement is non-monotonic in those columns and their correlation is typically low.

**Never promise an exact `1.0000`:** existing rows, updates, sampling, and real insertion order can affect the exact number.

### 13.3. Demonstrating Negative Correlation

To observe timestamps **decreasing with physical position**, create a reverse-ordered lab table:

```sql
CREATE TABLE query_stats_lab.reverse_events AS
SELECT event_id, created_at
FROM query_stats_lab.events
ORDER BY created_at DESC;

ANALYZE query_stats_lab.reverse_events;

SELECT
    attname,
    correlation
FROM pg_stats
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'reverse_events'
  AND attname IN ('event_id', 'created_at');
```

On this newly rewritten table stored in descending order, `created_at` and `event_id` usually show correlation **near -1**, subject to page writes and sampling.

A value of **-1 does not mean indexes are useless**. B-trees scan efficiently forward or backward; what matters is strong physical clustering of matching rows, simply in reverse order.

### 13.4. Creating an Index Does Not Reorder Heap Rows

Creating:

```sql
CREATE INDEX idx_reverse_events_created
ON query_stats_lab.reverse_events (created_at);
```

**does not reorder heap tuples to match the index**. Indexes maintain their own sorted structure, while physical heap layout reflects write history, rewrites, or `CLUSTER`.

`CLUSTER` can rewrite a table physically in index order, at the cost of heavy locks and ongoing maintenance (subsequent inserts/updates drift over time). Never run `CLUSTER` solely to “make correlation look nicer” without weighing lock and workload trade-offs.

### 13.5. High Correlation Does Not Guarantee Index Scan

Correlation near +1 or -1 lowers estimated random heap-fetch cost for range index scans, yet the planner still weighs:

- Qualifying row count.
- Heap and index page counts.
- Width/number of projected columns.
- Index-only scan viability and visibility map state.
- `random_page_cost`, `seq_page_cost`, and cache assumptions.
- `ORDER BY` / `LIMIT`.
- Joins and the full execution tree.

Never turn `correlation=0.99` into a rule that “Seq Scan cannot happen.”

## 14. pg_stats Correlation Is Not Cross-Column Dependency

A common misreading:

> “`pg_stats.correlation` of `region` is near 0, so `region` and `tenant_id` are unrelated.”

That conclusion is **false**. `pg_stats.correlation` of `region` measures alignment with physical tuple order—not with `tenant_id`.

In our lab, we intentionally engineered:

```text
tenant_id = 1  <=> region = 'north'
tenant_id != 1 <=> region = 'south'
```

So `tenant_id` and `region` have a **very strong data dependency**, even though neither rises monotonically with heap position.

### 14.1. Comparing Three Concepts

| Concept | What Is Compared | Meaning |
| --- | --- | --- |
| `pg_stats.correlation` | **One column's values** vs. **physical tuple order**. | Affects estimated heap I/O for index scans. |
| Functional dependencies | **Columns against each other** (e.g., `tenant_id` determines `region`). | Fixes estimates for dependent equality predicates. |
| Multivariate MCV | **Frequent multi-column value combinations**. | Helps estimate skewed, correlated multi-column filters. |

Because the word “correlation” is overloaded in statistics, always ask: **“Correlation of what with what?”**

### 14.2. Proving Dependency via GROUP BY

```sql
SELECT
    tenant_id,
    COUNT(DISTINCT region) AS regions_per_tenant
FROM query_stats_lab.events
GROUP BY tenant_id
ORDER BY tenant_id;
```

In our generator, every tenant belongs to a single region; `COUNT(DISTINCT region)` is 1 for every `tenant_id`.

Conversely, `region='south'` spans multiple tenants, showing dependency is directional: `tenant_id` determines `region`, whereas `region='south'` does not uniquely determine `tenant_id`.

### 14.3. Why Does This Cause Planner Misestimation?

Consider the query:

```sql
SELECT COUNT(*)
FROM query_stats_lab.events
WHERE tenant_id = 1
  AND region = 'north';
```

Actual proportions in the lab:

```text
P(tenant_id = 1)            = 0.70
P(region = 'north')         = 0.70
P(both)                     = 0.70
```

An estimator assuming complete independence between the two predicates computes:

\[
P(A\cap B) \approx P(A)\times P(B)
= 0.7\times 0.7=0.49
\]

predicting roughly **24,500 rows** instead of **35,000 rows**. This **illustrates the independence assumption**; PostgreSQL plans may differ once extended statistics or other signals apply.

### 14.4. Errors Can Amplify Across JOINs

A single filter error can cascade into:

- Wrong JOIN order.
- Wrong join method (Nested Loop vs. Hash vs. Merge).
- Undersized or oversized hash tables.
- Poor Index Scan vs. Seq Scan choices.
- Skewed Sort/Aggregate row and memory estimates.

Across multi-way joins, compounding selectivity errors can push the planner onto a dramatically slower plan.

## 15. Single Column: Selectivity for =, IN, Ranges, and NULL

To reason cleanly about statistics, examine each predicate form.

### 15.1. Equality

```sql
SELECT COUNT(*)
FROM query_stats_lab.events
WHERE status = 'paid';
```

If `'paid'` is in MCV, the planner has a direct frequency estimate. For values outside MCV, it allocates remaining non-MCV probability mass using `n_distinct` and supporting assumptions.

### 15.2. IN and OR

```sql
SELECT COUNT(*)
FROM query_stats_lab.events
WHERE status IN ('paid', 'pending');
```

For distinct constants on the same column, intuition sums the individual selectivities. The planner also handles operators, NULLs, and internal rewrites; avoid assuming every arbitrary `OR` query is estimated by simple addition.

### 15.3. Ranges

```sql
SELECT COUNT(*)
FROM query_stats_lab.events
WHERE amount >= 5000;
```

Histograms and MCVs estimate what fraction falls into high ranges. In the lab, high amounts are rare; real query plans still depend on indexes and projected columns.

### 15.4. IS NULL

```sql
SELECT COUNT(*)
FROM query_stats_lab.events
WHERE promo_code IS NULL;
```

`null_frac` directly informs this estimate. Comparisons like `promo_code = 'PROMO-1'` evaluate only non-NULL rows per SQL semantics.

### 15.5. Expressions and Functions

```sql
SELECT COUNT(*)
FROM query_stats_lab.events
WHERE date_trunc('month', created_at)
    = TIMESTAMPTZ '2025-02-01 00:00+00';
```

When a predicate wraps a column in a function, base column stats are **often insufficient** to estimate expression selectivity accurately. Options include:

- Rewriting to a range condition on the bare column when semantically equivalent and index-friendly.
- Creating an expression index or expression statistics where supported.
- Adding a generated column if the workload benefits consistently.

Remember `date_trunc` on `timestamptz` is timezone-sensitive depending on usage/version; never replace it with a range without pinning exact timezone boundaries.

## 16. Multi-Column Statistics: CREATE STATISTICS

PostgreSQL provides **extended statistics** to capture multi-column relationships that single-column stats cannot express.

Example:

```sql
CREATE STATISTICS stats_events_tenant_region
    (dependencies, ndistinct, mcv)
ON tenant_id, region
FROM query_stats_lab.events;

ANALYZE query_stats_lab.events;
```

Primary statistics kinds:

| Kind | Purpose |
| --- | --- |
| `dependencies` | Captures functional dependencies between columns, fixing combined equality/`IN` selectivity estimates. |
| `ndistinct` | Estimates distinct value combinations across columns, useful for `GROUP BY` row counts. |
| `mcv` | Stores frequent **value combinations**, improving skewed/correlated multi-column filters. |

### 16.1. Difference from Single-Column Statistics

Single-column `pg_stats.most_common_vals` on `tenant_id` knows `tenant_id=1` is 70%; on `region`, it knows `'north'` is 70%.

Neither single-column list knows **those two 70% slices share the exact same 35,000 rows**.

Multivariate MCV records:

```text
(tenant_id=1, region='north') occurs very frequently
```

And `dependencies` captures directional determination resembling `tenant_id -> region`.

### 16.2. CREATE STATISTICS Only Defines the Object

After `CREATE STATISTICS`, you must run `ANALYZE` to populate it:

```sql
ANALYZE query_stats_lab.events;
```

Never expect `CREATE STATISTICS` by itself to scan the table and populate MCVs immediately without `ANALYZE`.

### 16.3. Version Support

Extended statistics evolved across PostgreSQL major releases. `dependencies`/`ndistinct` arrived earlier than multivariate `mcv` (added in PostgreSQL 12). On older major versions, check supported syntax and statistics kinds first.

### 16.4. Not Applied Automatically to Arbitrary JOINs

Extended statistics help single-table filters and groupings, yet PostgreSQL has **planner limitations**—notably around complex cross-table JOIN estimates. Never claim `CREATE STATISTICS` fixes every poor nested loop or join cardinality estimate.

Always verify row estimates on **every plan node** before and after, judging on actual queries.

## 17. Inspecting Extended Statistics in pg_stats_ext

After `ANALYZE`:

```sql
SELECT
    schemaname,
    tablename,
    statistics_name,
    attnames,
    kinds,
    n_distinct,
    dependencies,
    most_common_vals,
    most_common_freqs
FROM pg_stats_ext
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'events'
ORDER BY statistics_name;
```

Available columns vary slightly by PostgreSQL major version (especially for expression statistics). On modern versions supporting `pg_stats_ext`, this reveals:

- Statistics object name.
- Referenced attributes.
- Enabled statistics kinds.
- Distinct combination estimates.
- Dependency coefficients.
- Multivariate MCV combinations and frequencies.

### 17.1. Directional Dependencies

When each tenant belongs to exactly one region:

```text
tenant_id -> region  : strong dependency
region -> tenant_id  : may be weaker
```

Because `region='south'` covers many tenants. Dependency coefficients indicate directional predictive strength; **never read them as causal relationships**.

### 17.2. MCV Combinations vs. Product of Marginals

Consider a distribution:

| tenant_id | region | Assumed Share |
| ---: | --- | ---: |
| 1 | north | 70% |
| 2 | south | 10% |
| 3 | south | 10% |
| 4 | south | 10% |

From single-column stats:

```text
P(tenant=1) = 0.70
P(north)    = 0.70
```

Independent multiplication predicts `0.49`; joint MCV knows `(1, 'north')` occurs at `0.70`, bringing estimates in line with reality.

This 4-tenant table is simplified for arithmetic clarity; our lab dataset spreads south across multiple tenants via modulo.

### 17.3. Sampled MCVs Still Have Error

Multivariate MCV lists cannot record every rare combination. If filters target new combinations inserted after `ANALYZE`, planner estimates can still miss.

Adding dozens of statistics objects never replaces timely `ANALYZE` runs and real workload benchmarking.

## 18. Experiment: Comparing Plans Before and After Extended Stats

### 18.1. Before Extended Stats

If you have not created the object from Section 16 yet, run:

```sql
EXPLAIN
SELECT *
FROM query_stats_lab.events
WHERE tenant_id = 1
  AND region = 'north';
```

Note the estimated `rows` on the scan/filter node.

### 18.2. Create Extended Stats and ANALYZE

```sql
CREATE STATISTICS IF NOT EXISTS stats_events_tenant_region
    (dependencies, ndistinct, mcv)
ON tenant_id, region
FROM query_stats_lab.events;

ANALYZE query_stats_lab.events;
```

Re-check:

```sql
EXPLAIN
SELECT *
FROM query_stats_lab.events
WHERE tenant_id = 1
  AND region = 'north';
```

### 18.3. Check Actual Rows

```sql
SELECT COUNT(*)
FROM query_stats_lab.events
WHERE tenant_id = 1
  AND region = 'north';
```

On the unmodified lab table, the exact count is **35,000 rows**.

Compare estimate vs. actual. If the plan shape stayed the same, do not rush to say extended stats are useless: either the estimate became more accurate without changing which plan wins, or Seq Scan already won either way. **Row accuracy** and **execution plan switch** are related but distinct questions.

### 18.4. Why Lower Estimated Cost Is Not the Only Success Metric

When extended stats raise an underestimate closer to reality, **estimated cost often increases** because the planner realizes more rows must be processed. That can be a major win—preventing an unsuitable Nested Loop or Index Scan. Never assume “smaller predicted cost is always better.”

### 18.5. Limitations of This Experiment

A 50,000-row synthetic table generated with modulo patterns is small and artificial compared to production workloads. `EXPLAIN ANALYZE`, cache warmth, and host hardware will yield varying timings. The lesson goal is **reading estimates and diagnosing discrepancies**, not forcing PostgreSQL into one specific scan type.

## 19. Multi-Column n_distinct and GROUP BY

Consider a grouping query:

```sql
SELECT
    tenant_id,
    region,
    COUNT(*)
FROM query_stats_lab.events
GROUP BY tenant_id, region;
```

The planner needs to estimate the **number of `(tenant_id, region)` groups**. Knowing only distinct tenants and distinct regions separately under independence can badly distort group-count estimates.

Extended `ndistinct` statistics supply distinct combination counts across those columns.

### 19.1. Exact Count via SQL

```sql
SELECT COUNT(*) AS actual_groups
FROM (
    SELECT tenant_id, region
    FROM query_stats_lab.events
    GROUP BY tenant_id, region
) AS groups;
```

Compare against:

```sql
EXPLAIN
SELECT tenant_id, region, COUNT(*)
FROM query_stats_lab.events
GROUP BY tenant_id, region;
```

Aggregate nodes show estimated group counts in `rows`. When estimated groups diverge sharply from actuals, HashAggregate sizing and disk-spill risk are directly affected.

### 19.2. Multi-Column n_distinct Is Not a UNIQUE Constraint

Recording distinct combination counts in a statistics object never prevents duplicate combinations on insert. Guaranteeing uniqueness of `(tenant_id, region)` requires a `UNIQUE` constraint/index—which would be invalid here anyway since 35,000 lab rows share `(1, 'north')`.

Statistics describe existing data; constraints enforce database invariants.

## 20. Statistics Target: Tuning Granularity

PostgreSQL has a cluster/session default:

```sql
SHOW default_statistics_target;
```

The typical default is **100**. Statistics target governs histogram/MCV granularity and the sample size read by `ANALYZE`. It does not mean each column holds 100 values or `ANALYZE` reads 100 rows.

### 20.1. Raising the Target on Specific Columns

Example:

```sql
ALTER TABLE query_stats_lab.events
    ALTER COLUMN amount SET STATISTICS 500;

ALTER TABLE query_stats_lab.events
    ALTER COLUMN created_at SET STATISTICS 500;

ANALYZE query_stats_lab.events;
```

This directs PostgreSQL to collect finer-grained histograms/MCVs on `amount` and `created_at` when helpful. Still, raising the target does not promise faster queries: samples change, plans may or may not switch, and `ANALYZE` uses more CPU/I/O.

### 20.2. Checking Configured Targets

```sql
SELECT
    attname,
    attstattarget
FROM pg_attribute
WHERE attrelid = 'query_stats_lab.events'::regclass
  AND attnum > 0
  AND NOT attisdropped
ORDER BY attnum;
```

`attstattarget = -1` indicates using `default_statistics_target`; positive numbers are per-column overrides.

### 20.3. Resetting to Default

```sql
ALTER TABLE query_stats_lab.events
    ALTER COLUMN amount SET STATISTICS -1;

ALTER TABLE query_stats_lab.events
    ALTER COLUMN created_at SET STATISTICS -1;

ANALYZE query_stats_lab.events;
```

Changing the target **without running `ANALYZE`** leaves stored statistics unchanged until the next collection.

### 20.4. Does a Higher Target Fix Multi-Column Correlation?

No. Raising individual targets on `tenant_id` and `region` refines single-column distributions, yet two separate single-column lists **still do not encode that `tenant_id=1` and `'north'` occur together**.

When divergence comes from joint distributions, use extended MCV/dependencies rather than merely raising per-column targets.

### 20.5. Never Raise the Global Default Blindly

Raising `default_statistics_target` system-wide slows down `ANALYZE`, inflates `pg_statistic` storage, and adds planning overhead across every table. When errors trace to specific skewed columns, adjust targets locally and measure.

## 21. Stale Statistics

Even with sound estimation algorithms, the planner can pick a poor plan when statistics reflect **yesterday's data instead of today's**.

### 21.1. A Common Scenario

```text
Day 1:
  100,000 orders
  80% paid, 20% pending
  ANALYZE

Day 2:
  Import 2,000,000 additional pending orders
  No timely ANALYZE

Day 2, afternoon:
  SELECT ... WHERE status = 'pending'

Planner may still estimate using the old distribution
instead of the new post-import pending share.
```

When a table shifts rapidly, MCVs, histograms, `null_frac`, and `n_distinct` all go stale.

### 21.2. Monitoring Table ANALYZE History

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze,
    analyze_count,
    autoanalyze_count
FROM pg_stat_user_tables
WHERE schemaname = 'query_stats_lab'
  AND relname = 'events';
```

Interpretation:

| Field | Meaning |
| --- | --- |
| `n_live_tup` | Estimated live tuples per runtime stats collector. |
| `n_mod_since_analyze` | Estimated tuple modifications since the last ANALYZE. |
| `last_analyze` | Timestamp of the last recorded manual ANALYZE. |
| `last_autoanalyze` | Timestamp of the last recorded autoanalyze. |
| `analyze_count` | Count of manual ANALYZE runs recorded. |
| `autoanalyze_count` | Count of autoanalyze runs recorded. |

These are approximate runtime counters, not exact transactional counts; stats updates can lag or reset. Never use `n_mod_since_analyze` as an audit counter for modified rows.

### 21.3. When Should You Run Manual ANALYZE?

Consider manual `ANALYZE` after:

- Large bulk loads.
- ETL imports that markedly alter column distributions.
- Introducing heavily used new status/category values.
- Mass updates shifting `tenant_id`/`status` shares.
- Creating a new statistics object.
- Raising a column's statistics target.
- Truncate/reload operations or major migrations.

Example:

```sql
ANALYZE query_stats_lab.events;
```

You do not need manual `ANALYZE` after routine small inserts, since autovacuum/autoanalyze handles gradual churn based on thresholds. After major bulk imports followed immediately by plan-sensitive queries, explicit `ANALYZE` is often worthwhile.

### 21.4. More Frequent ANALYZE Is Not Always Better

`ANALYZE` consumes CPU and I/O. Running it constantly will not make estimates exact or fix every planning issue.

If the discrepancy stems from **correlated columns** tracked only individually, repeating `ANALYZE` cannot synthesize dependency stats without an appropriate statistics object.

## 22. How Does Autoanalyze Trigger?

PostgreSQL's autovacuum launcher/workers perform **automatic `ANALYZE`** in addition to `VACUUM` once a table accumulates enough modifications.

The basic trigger threshold formula is:

\[
\text{autoanalyze threshold}
\approx
\text{autovacuum\_analyze\_threshold}
+
\text{autovacuum\_analyze\_scale\_factor}
\times \text{estimated relation rows}
\]

Illustrative example:

- `autovacuum_analyze_threshold = 50`.
- `autovacuum_analyze_scale_factor = 0.1`.
- Table has 100,000 rows.

The baseline threshold is `50 + 0.1 × 100000 = 10050` modifications, subject to operational conditions.

### 22.1. Inspecting Current Settings

```sql
SHOW autovacuum;
SHOW autovacuum_analyze_threshold;
SHOW autovacuum_analyze_scale_factor;
SHOW autovacuum_naptime;
```

These are configuration parameters. Tables can override them via storage parameters, while actual execution timing also depends on worker availability, server load, and PostgreSQL version.

### 22.2. Why Can Large Tables Autoanalyze Slowly?

With a proportional scale factor, the **raw number of modified rows** required grows linearly with table size. A 100-million-row table may need millions of changes before a 10% scale factor triggers autoanalyze.

If workloads are sensitive to shifting distributions on large tables, monitor `n_mod_since_analyze`, stats freshness, and post-ETL query plans, tuning thresholds thoughtfully where warranted.

### 22.3. Per-Table Overrides

Lab example:

```sql
ALTER TABLE query_stats_lab.events
SET (
    autovacuum_analyze_threshold = 100,
    autovacuum_analyze_scale_factor = 0.02
);
```

This makes the table eligible for autoanalyze at a lower threshold when workers check it, **without guaranteeing immediate execution**. Nor does it replace multi-column extended statistics.

### 22.4. Resetting Storage Parameters in the Lab

```sql
ALTER TABLE query_stats_lab.events
RESET (
    autovacuum_analyze_threshold,
    autovacuum_analyze_scale_factor
);
```

This DDL alters relation storage parameters; never apply it in production without operational authorization and change control.

### 22.5. ANALYZE and VACUUM Solve Different Problems

Keep them distinct:

```text
n_mod_since_analyze increases
   -> data changed, planner statistics may be stale

n_dead_tup increases
   -> many dead tuples, consider VACUUM for MVCC cleanup
```

A table can need both `ANALYZE` (for accurate estimates) and `VACUUM` (to reclaim dead tuples), yet tuning one threshold does not fulfill the other's job.

## 23. How Estimation Errors Change JOIN Plans

Suppose our large `events` table joins against a `customers` table:

```sql
CREATE TABLE query_stats_lab.customers (
    customer_id bigint PRIMARY KEY,
    customer_group text NOT NULL
);

INSERT INTO query_stats_lab.customers (
    customer_id, customer_group
)
SELECT
    100000 + g,
    CASE WHEN g % 10 = 0 THEN 'vip'
         ELSE 'regular' END
FROM generate_series(0, 29999) AS series(g);

ANALYZE query_stats_lab.customers;
```

The lab assigns `customer_id` from `100000` to `129999`, matching the modulo IDs generated in `events`.

Query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.customer_group,
    COUNT(*) AS events_count
FROM query_stats_lab.events AS e
JOIN query_stats_lab.customers AS c
    ON c.customer_id = e.customer_id
WHERE e.tenant_id = 1
  AND e.region = 'north'
  AND e.status = 'paid'
GROUP BY c.customer_group;
```

### 23.1. Bad Filter Estimates Distort Joins

If the planner drastically underestimates `events` rows matching `tenant_id + region + status`, it may select a join method tuned for dozens of rows when tens of thousands arrive at runtime.

Other critical factors include:

- Size of `customers`.
- Index availability on `customer_id`.
- Number of distinct `customer_id` values.
- Heap/index layout and buffer cache state.
- Concurrent workload.

Do not claim any estimation error automatically forces a bad Nested Loop; it creates **cost-model risk** that must be confirmed by reading the actual plan.

### 23.2. Checking Estimates Step by Step

Read the plan bottom-up:

1. How many rows are estimated vs. actual from scanning `events`?
2. Are `customers` row estimates accurate?
3. How many rows are estimated vs. actual leaving the JOIN?
4. How many groups does Aggregate predict?
5. Do Sort or Hash nodes show high memory use or disk spills?

Fixing scan-level estimates helps plan selection, though extended stats cannot fix every join estimate due to planner scope limits.

### 23.3. EXPLAIN ANALYZE Measures Execution, Not Just Row Counts

Example:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    c.customer_group,
    COUNT(*)
FROM query_stats_lab.events AS e
JOIN query_stats_lab.customers AS c
    ON c.customer_id = e.customer_id
WHERE e.tenant_id = 1
  AND e.region = 'north'
GROUP BY c.customer_group;
```

`VERBOSE` adds target lists and node details; `BUFFERS` counts block hits and reads, keeping in mind runtime timings vary with cache warmth and concurrency.

## 24. Reading EXPLAIN Systematically

Consider an illustrative output:

```text
Hash Join  (cost=... rows=250 width=...)
           (actual time=... rows=12000 loops=1)
  Hash Cond: (e.customer_id = c.customer_id)
  -> Seq Scan on events e
       (cost=... rows=300 ...)
       (actual ... rows=14000 loops=1)
       Filter: (...)
  -> Hash
       -> Seq Scan on customers c
```

**This is a synthetic illustration of reading mechanics**, not measured lab output. The key point is comparing planner `rows` with `actual rows`.

### 24.1. Distinguishing Metrics

| Metric | Explanation |
| --- | --- |
| `cost=startup..total` | Planner relative cost units, never milliseconds. |
| `rows=N` | Estimated rows returned per execution of that node. |
| `width=W` | Estimated average row width in bytes. |
| `actual time` | Measured execution duration when running with `ANALYZE`. |
| `actual rows` | Actual rows returned per invocation, averaged across loops. |
| `loops` | Number of times the node was executed. |
| `Buffers: shared hit/read` | Shared buffer hits and reads recorded at that node. |

### 24.2. Watch loops Closely

If an `Index Scan` inside a nested loop shows:

```text
actual rows=2 loops=1000
```

total rows emitted across all calls are roughly **2,000**. Never compare `actual rows=2` directly against `rows=2000` elsewhere while ignoring `loops`.

Likewise, `actual time` is reported per loop; total query time cannot be computed by adding parent and child times mechanically because parent time already wraps child execution.

### 24.3. Why Estimated Rows Matter More Than Raw Cost Numbers

If an estimate is 100× too low, suspect statistics first. If row estimates are accurate yet the query remains slow, investigate:

- Expensive storage I/O.
- Unsuitable or missing indexes.
- Genuinely large result/aggregation sets.
- Lock waits.
- Sort/hash spills.
- Memory/cost parameters misaligned with hardware.

Never treat `ANALYZE` as a magic “fix all slow queries” button; it mainly refreshes **optimizer input data**.

### 24.4. Queries with LIMIT

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, created_at
FROM query_stats_lab.events
WHERE tenant_id = 1
  AND status = 'paid'
ORDER BY created_at DESC
LIMIT 10;
```

Row counts and costs on scans/filters must be read alongside **early termination** caused by `LIMIT`. An index scan may stop after grabbing 10 qualifying rows quickly despite many matching rows overall—or it may scan deeply if post-index filters reject many candidates.

Histograms, MCVs, and `correlation` shape how many index entries and heap pages the planner expects to touch before hitting `LIMIT`.

## 25. Data Skew and Prepared Statement Plans

Java/JDBC applications frequently issue parameterized SQL:

```sql
SELECT event_id, created_at
FROM query_stats_lab.events
WHERE tenant_id = $1
ORDER BY created_at DESC
LIMIT 100;
```

In our lab:

- Tenant 1 owns ~70% of rows.
- Other tenants own tiny fractions.

Thus the very same SQL query has **vastly different optimal execution costs depending on parameter values**.

### 25.1. Custom Plans vs. Generic Plans

PostgreSQL chooses between:

- **Custom plan:** planned specifically for the bound parameter values, able to leverage MCVs and skew.
- **Generic plan:** a reusable plan independent of specific runtime parameter values.

Generic plans save repeated planning overhead, but under extreme parameter skew, one shared plan rarely fits both massive and tiny tenants equally well.

### 25.2. Experimenting with PREPARE

```sql
PREPARE events_by_tenant(integer) AS
SELECT event_id, created_at
FROM query_stats_lab.events
WHERE tenant_id = $1
ORDER BY created_at DESC
LIMIT 100;
```

Inspect custom plans for two tenants:

```sql
BEGIN;
SET LOCAL plan_cache_mode = force_custom_plan;

EXPLAIN EXECUTE events_by_tenant(1);
EXPLAIN EXECUTE events_by_tenant(10);

ROLLBACK;
```

Inspect the generic plan:

```sql
BEGIN;
SET LOCAL plan_cache_mode = force_generic_plan;

EXPLAIN EXECUTE events_by_tenant(1);
EXPLAIN EXECUTE events_by_tenant(10);

ROLLBACK;
```

Clean up when finished:

```sql
DEALLOCATE events_by_tenant;
```

`plan_cache_mode` is available in PostgreSQL 12+. Using `SET LOCAL` limits the override strictly to the practice transaction so session defaults stay intact afterward.

### 25.3. Do Not Assume Generic Plans Are Always Bad

If tenants are balanced or a single generic plan runs fast enough for all of them, generic planning saves planning CPU and works well. Never force custom plans globally just because of one skewed query.

In real systems, weigh:

- Request split between huge and tiny tenants.
- Execution frequency.
- Planning time vs. execution time.
- Available indexes.
- Generic vs. custom plans on the real SQL.
- PostgreSQL version and driver prepared-statement behavior.

### 25.4. MCVs Aid Custom Plans, Not Parameter-Blind Generic Plans

MCVs on `tenant_id` know tenant 1 is dominant. Inside a generic plan, however, the planner cannot assume `$1` equals `1`. That is a **parameter-visibility boundary**, not missing statistics.

Consequently, raising statistics targets will not help a generic plan specialize for an unknown parameter value.

## 26. Expression Statistics and Expression Indexes

Consider a common query pattern:

```sql
SELECT COUNT(*)
FROM query_stats_lab.events
WHERE lower(region) = 'north';
```

Although `region` is already lowercase in our lab, real systems often normalize text.

### 26.1. Expression Index

```sql
CREATE INDEX idx_events_lower_region
ON query_stats_lab.events (lower(region));

ANALYZE query_stats_lab.events;
```

An expression index accelerates queries using matching expressions, and `ANALYZE` collects statistics on index expression columns automatically.

Still, do not wrap `lower(region)` everywhere just to force an index if `region` is already normalized and `region = 'north'` preserves exact semantics—unnecessary function wrappers complicate SQL and planning.

### 26.2. Extended Statistics on Expressions

On PostgreSQL 14+ supporting expression statistics, you can define:

```sql
CREATE STATISTICS stats_events_tenant_lower_region
ON tenant_id, (lower(region))
FROM query_stats_lab.events;

ANALYZE query_stats_lab.events;
```

This helps estimate predicates involving those expressions without building a physical index. PostgreSQL version and query structure govern when the optimizer uses it.

### 26.3. One Expression Statistic Does Not Cover Arbitrary Functions

`lower(region)` differs from `upper(region)` or `substr(region, 1, 3)`. One statistics object does not automatically cover every transformation written over a column.

For timestamps, watch timezone immutability rules carefully: only expressions meeting the index method's immutability rules are valid inside index definitions.

## 27. Partitioned Tables: Local Stats and Inherited Stats

In large databases, event tables are often **partitioned by day or month**:

- Each partition can hold a distinct data distribution.
- Partition pruning changes which partitions remain in scope.
- Depending on the plan, the optimizer uses per-partition statistics or parent/inherited statistics.

### 27.1. Why Parent Stats Matter

Suppose tenant 1 generated most October events while tenant 2 generated most November events. Global parent statistics look very different from individual monthly partitions, so a query restricted to November sees different selectivity than a year-wide query.

When partitioned query plans look off, check:

1. Is partition pruning firing properly?
2. Are statistics on touched partitions up to date?
3. Are parent/inherited statistics updated?
4. Have newly attached/created partitions been analyzed?

### 27.2. Run ANALYZE on the Parent When Needed

For partitioned tables, autoanalyze running on child partitions does not necessarily trigger `ANALYZE` on the partitioned parent; explicit **`ANALYZE parent`** is often needed to maintain parent-level statistics.

Syntax illustration for a partitioned table:

```sql
-- If public.events_partitioned were a real partitioned table:
-- ANALYZE public.events_partitioned;
```

Do not run this snippet in the lab since `public.events_partitioned` was not created. The takeaway is that **statistics maintenance must cover the whole partition hierarchy**, not just individual leaf partitions.

### 27.3. pg_stats.inherited

`pg_stats` provides an `inherited` boolean distinguishing whole-tree inherited stats from local relation stats:

```sql
SELECT
    schemaname,
    tablename,
    attname,
    inherited,
    n_distinct
FROM pg_stats
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'events'
ORDER BY attname, inherited;
```

On our regular non-partitioned lab table, do not expect a separate inherited aggregate row. This column is shown so you know how to inspect partition/inheritance statistics when needed.

## 28. Specialized Array and Range Statistics

Beyond scalar fields, `pg_stats` includes specialized statistics for certain data types:

- `most_common_elems`: common element values inside arrays and supported types.
- `most_common_elem_freqs`: frequencies of those common elements.
- `elem_count_histogram`: histogram of array element counts per row.
- Range fields like `range_length_histogram` and `range_empty_frac` where applicable.

Array tags example:

```sql
CREATE TABLE query_stats_lab.tagged_events (
    event_id bigint PRIMARY KEY,
    tags text[] NOT NULL
);

INSERT INTO query_stats_lab.tagged_events (event_id, tags)
VALUES
    (1, ARRAY['postgres', 'sql']),
    (2, ARRAY['postgres', 'index']),
    (3, ARRAY['java']),
    (4, ARRAY['postgres', 'sql']),
    (5, ARRAY['java', 'sql']),
    (6, ARRAY['postgres']);

ANALYZE query_stats_lab.tagged_events;
```

Inspect element stats where supported:

```sql
SELECT
    attname,
    most_common_elems,
    most_common_elem_freqs,
    elem_count_histogram
FROM pg_stats
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'tagged_events'
  AND attname = 'tags';
```

Do not force these into the **scalar MCV + scalar histogram** mental model. Array containment and range operators have specialized selectivity estimators.

### 28.1. Array Element Occurrence vs. Row Occurrence

If an array repeats the same element within one row, “how many rows contain element X” differs from “total token occurrences across all arrays.” Array statistics serve operator selectivity estimation—not exact business reporting counts.

For exact counts, query the underlying rows directly using `unnest` and explicit aggregation rules.

## 29. Planner Statistics vs. Execution Statistics

Keep these metadata groups clearly separated:

| Category | Example | Question Answered |
| --- | --- | --- |
| **Column statistics** | `pg_stats` | How are values in a column distributed? |
| **Multivariate statistics** | `pg_stats_ext` | How are column/expression combinations distributed? |
| **Relation metadata** | `pg_class.reltuples`, `relpages` | Roughly how many rows/pages are in the relation? |
| **Runtime/activity statistics** | `pg_stat_user_tables` | How many scans/writes/analyzes occurred, and when? |
| **Per-query execution evidence** | `EXPLAIN (ANALYZE, BUFFERS)` | Which plan ran, and how many rows/buffers/ms did it take? |

### 29.1. reltuples Is Also an Estimate

```sql
SELECT
    c.relname,
    c.reltuples,
    c.relpages
FROM pg_class AS c
WHERE c.oid = 'query_stats_lab.events'::regclass;
```

`reltuples` and `relpages` are not incremented accurately on every single INSERT. During planning, PostgreSQL can also scale `reltuples` dynamically using current physical page counts.

### 29.2. Runtime Statistics Views May Cache Within a Transaction

When checking `pg_stat_*` activity views repeatedly inside a transaction, snapshot caching can hold earlier numbers depending on PostgreSQL version and setup. Calling `pg_stat_clear_snapshot()` clears the current session's stats snapshot:

```sql
SELECT pg_stat_clear_snapshot();
```

This is **not** an `ANALYZE` command, does not update histograms/MCVs, and does not alter MVCC snapshots for business `SELECT` queries.

## 30. Runbook: Investigating a Slow Query Caused by Misestimation

Suppose a query that used to finish in 100 ms suddenly takes several seconds after an ETL batch. A controlled investigation workflow:

### Step 1. Capture Exact SQL and Parameter Values

Never stop at:

```sql
SELECT ... WHERE tenant_id = $1 AND status = $2;
```

Identify which parameter values run slowly—huge vs. small tenant, common vs. rare status, wide vs. narrow time window.

Without concrete parameter examples, you will miss data skew and generic/custom plan effects.

### Step 2. Inspect Plan and Row Estimates

In an authorized environment:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, created_at, amount
FROM query_stats_lab.events
WHERE tenant_id = 1
  AND status = 'paid'
  AND created_at >= TIMESTAMPTZ '2025-01-15 00:00+00'
ORDER BY created_at DESC
LIMIT 100;
```

Walk upward from scans to parents, spotting where estimated rows diverge farthest from actual rows. Record `loops` and `BUFFERS` metrics too.

### Step 3. Inspect Column Statistics

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
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'events'
  AND attname IN ('tenant_id', 'status', 'created_at');
```

Questions to ask:

- Do MCVs capture dominant tenants and statuses?
- Does the `created_at` histogram cover recently loaded dates?
- How many distinct values are estimated?
- Does the timestamp column still show strong physical correlation?
- Do predicates wrap columns in expressions/functions?

### Step 4. Check Statistics Freshness

```sql
SELECT
    last_analyze,
    last_autoanalyze,
    n_mod_since_analyze,
    n_live_tup
FROM pg_stat_user_tables
WHERE schemaname = 'query_stats_lab'
  AND relname = 'events';
```

If large batches arrived and stats are stale, run `ANALYZE` after evaluating runtime cost.

### Step 5. Check for Multi-Column Dependencies

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (
        WHERE tenant_id = 1
    ) AS tenant_1_rows,
    COUNT(*) FILTER (
        WHERE region = 'north'
    ) AS north_rows,
    COUNT(*) FILTER (
        WHERE tenant_id = 1 AND region = 'north'
    ) AS both_rows
FROM query_stats_lab.events;
```

If joint occurrence diverges sharply from the independent product, inspect `pg_stats_ext` and test extended statistics tailored to the query.

### Step 6. Evaluate Column-Level Statistics Targets

For complex distributions or important rare values, raise the target **on that specific column**, run `ANALYZE`, and re-check estimates and plans.

Avoid bumping `default_statistics_target` cluster-wide for one query.

### Step 7. Check Indexes, Caching, and Access Cost

Even with spot-on row estimates, a query can remain slow because of:

- Missing or misaligned indexes.
- Indexes not matching `ORDER BY` / `LIMIT`.
- Heavy random heap page fetches.
- Overly wide projected rows (`SELECT *`).
- Simply much larger data volume than before.
- Bloat, I/O contention, or lock waits.

`pg_stats.correlation` helps explain index heap-access costs, backed up by `BUFFERS` and plan timings.

### Step 8. Inspect Prepared Queries and Generic Plans

When a giant tenant lags while small tenants stay fast, compare custom vs. generic plans for the prepared statement. Do not rely on one literal `EXPLAIN` to judge parameterized application queries.

### Step 9. Measure After Each Change

After `ANALYZE` or adding a statistics object:

- Compare estimated vs. actual rows.
- Compare latency and buffers against baseline.
- Test across diverse representative parameter values.
- Measure planning overhead and write impact.
- Document rollback steps.

### Step 10. Document the Root Cause

A clear incident report distinguishes causes such as:

```text
Root cause A: stale statistics after bulk load
Root cause B: tenant and region dependency lacking extended stats
Root cause C: generic plan poorly suited to giant tenant
Root cause D: index misaligned with filter/range/order
Root cause E: physical correlation degraded after heavy UPDATE churn
Root cause F: resource contention, I/O, or locks outside the planner
```

Multiple causes can coexist. Never treat “query got faster after ANALYZE” as proof that no index or SQL issues remain.

## 31. Case Study: Same SQL with Very Different Parameter Values

An admin dashboard loads recent events for a tenant:

```sql
SELECT event_id, created_at, status
FROM query_stats_lab.events
WHERE tenant_id = 1
ORDER BY created_at DESC
LIMIT 100;
```

and:

```sql
SELECT event_id, created_at, status
FROM query_stats_lab.events
WHERE tenant_id = 10
ORDER BY created_at DESC
LIMIT 100;
```

### 31.1. Why Selectivity Differs

In our lab, tenant 1 holds ~70% of events while tenant 10 holds a tiny share. With an index on `(tenant_id, status, created_at DESC)`, these queries filter only by `tenant_id` equality, leaving `status` positioned before `created_at`—so the index **does not provide global `created_at DESC` ordering across all statuses of a tenant**. The planner may pick another index, a Sort, or a Seq Scan.

### 31.2. Challenge for Generic Plans

A generic plan cannot specialize between tenant 1 and tenant 10 the way custom plans do. Even when MCV captures skew, a **parameter-blind generic plan** falls back on average selectivity assumptions.

### 31.3. Designing the Index for the Real Query

If the hot query always pulls “newest events for a tenant,” consider:

```sql
CREATE INDEX idx_events_tenant_created
ON query_stats_lab.events (tenant_id, created_at DESC);
```

This adds write maintenance overhead and only pays off when justified by real query frequency, volume, and measured speedup.

Conversely, if `WHERE status='paid'` is always present, the existing `(tenant_id, status, created_at DESC)` index matches better. Statistics and index design **work together**—neither replaces the other.

## 32. Case Study: Recent Dates on Growing Time-Series Data

An append-heavy event table constantly receives newer `created_at` timestamps. A reporting query asks:

```sql
SELECT event_id
FROM query_stats_lab.events
WHERE created_at >= TIMESTAMPTZ '2025-01-30 00:00+00';
```

### 32.1. When Histograms Lag Behind Ingestion

If the last `ANALYZE` ran when `max(created_at)` was January 20 and new batches pushed data through January 30, the old histogram stops at January 20. A cutoff past the top bound distorts selectivity estimates.

### 32.2. Do Not Expect Correlation to Fix Missing Range Stats

`created_at` correlation stays near +1 since rows append chronologically. Yet **correlation measures heap locality**, not how many rows arrived past the new cutoff.

Fixing row-count estimates requires **fresh/representative distribution stats** (or partitioning), not assuming high correlation lets an old histogram predict future rows.

### 32.3. When Tables Are Partitioned by Date

Time-range partitioning lets partition pruning eliminate older partitions cleanly, though partitions still require current statistics. Never treat partitioning as a complete substitute for distribution statistics.

## 33. Case Study: A Very Rare Event Type

Suppose a monitoring system has `event_type='critical'` in 0.001% of rows, yet alerting hot queries look for it constantly.

### 33.1. MCVs Can Miss Very Rare Values

If sampling skips `'critical'` or it fails to make the MCV cutoff, the planner has no dedicated frequency estimate and uses non-MCV fallback estimates, causing misestimation.

### 33.2. Can You Raise the Statistics Target?

You can try raising the target on `event_type`, though there is no guarantee an extremely rare 0.001% value enters the MCV list—it depends on frequency, sample size, distinct count, and planner rules.

### 33.3. Partial Indexes Are Another Option

When queries consistently target critical events and schema policy permits:

```sql
-- Standalone example, since the lab table does not have an event_type column:
-- CREATE INDEX idx_critical_time
-- ON monitoring_events (created_at DESC)
-- WHERE event_type = 'critical';
```

A dedicated partial index works very well for rare, high-value predicates, evaluated against workload frequency, bind parameters, and write cost.

**Good statistics pick the right plan; good indexes supply the right access path.** They complement each other.

## 34. Case Study: Multi-Column Distributions Varying by Tenant

In a multi-tenant SaaS system:

```text
Tenant A: 90% paid, 10% pending
Tenant B: 10% paid, 90% pending
```

Single-column stats might see:

```text
P(status='paid') ~50%
```

without knowing:

```text
P(status='paid' | tenant='A') = 90%
P(status='paid' | tenant='B') = 10%
```

### 34.1. Why Two-Column Predicates Matter

```sql
SELECT *
FROM query_stats_lab.events
WHERE tenant_id = 1
  AND status = 'paid';
```

Separate stats on `tenant_id` and `status` cannot capture joint combination frequencies; multivariate MCV excels when dominant pairs recur heavily.

### 34.2. Build Stats for the Exact Column Pair Needed

```sql
CREATE STATISTICS stats_events_tenant_status
    (mcv, dependencies, ndistinct)
ON tenant_id, status
FROM query_stats_lab.events;

ANALYZE query_stats_lab.events;
```

Never expect a statistics object on `(tenant_id, region)` to model correlation between `(tenant_id, status)`. Each statistics object covers only its listed columns/expressions and enabled kinds.

### 34.3. When Combinations Are Sparse

With millions of sparse `(tenant_id, status)` pairs, a finite multivariate MCV list cannot record every pair. Under extreme multi-column skew, estimates fall back to remainder logic, sometimes requiring adjusted indexes, partitioning, or query restructuring.

## 35. Common Misconceptions

### Misconception 1. “ANALYZE counts every single row accurately”

False. `ANALYZE` samples data to estimate planner statistics; exact counts require `COUNT(*)` on live data.

### Misconception 2. “pg_stats shows per-query runtime statistics”

False. `pg_stats` stores column distributions for planning; `EXPLAIN ANALYZE` measures single-query execution.

### Misconception 3. “MCV lists contain all distinct values”

False. MCV stores only frequent values; excluded values can still account for significant table volume.

### Misconception 4. “most_common_freqs are percentages of non-NULL rows”

False by default. Frequencies represent fractions of total table rows; `null_frac` is stored separately.

### Misconception 5. “The histogram includes MCV values too”

False. PostgreSQL histograms normally model **non-NULL, non-MCV values only**.

### Misconception 6. “Histograms split values into equal-width numeric bins”

False. Histogram bounds seek **roughly equal numbers of observations** per bucket, not equal arithmetic widths.

### Misconception 7. “histogram_bounds always has target + 1 entries”

False. Actual bound counts depend on data, data type, sampling, and target; low-cardinality columns may have no histogram at all.

### Misconception 8. “n_distinct=-1 means negative one distinct values”

False. Negative values express distinctness proportional to table size (`-1` means roughly one distinct value per row).

### Misconception 9. “n_distinct=-1 guarantees uniqueness”

False. Only `UNIQUE` or `PRIMARY KEY` constraints enforce uniqueness in PostgreSQL.

### Misconception 10. “null_frac=0 guarantees no NULLs can exist”

False. It reflects only sampled statistics; `NOT NULL` enforces the schema rule.

### Misconception 11. “Correlation on tenant_id measures dependence on status”

False. `pg_stats.correlation` measures alignment between one column's values and physical heap position.

### Misconception 12. “Correlation=-1 means data is uncorrelated and indexes fail”

False. `-1` indicates strong reverse physical clustering; B-tree indexes scan backward efficiently and remain helpful.

### Misconception 13. “Correlation=+1 guarantees Index Scan”

False. The planner still checks selectivity, row counts, page costs, query structure, indexes, and `LIMIT`.

### Misconception 14. “Repeated ANALYZE creates extended statistics automatically”

False. You must explicitly create them with `CREATE STATISTICS` and then run `ANALYZE`.

### Misconception 15. “Extended stats fix every JOIN cardinality estimate”

False. `dependencies`, `ndistinct`, and multivariate `mcv` have strict planner scope limits across joins.

### Misconception 16. “CREATE STATISTICS works like CREATE INDEX”

False. Statistics inform cost estimation; indexes provide physical access paths and constraints.

### Misconception 17. “Multivariate MCV records every combination”

False. It is finite and sample-based, omitting rare combinations.

### Misconception 18. “n_mod_since_analyze is an exact DML audit counter”

False. It is an approximate stats counter, not a row-level audit log.

### Misconception 19. “Lowering autovacuum_analyze_scale_factor switches plans immediately”

False. It changes eligibility thresholds; it does not run `ANALYZE` instantaneously or rebuild plans on the spot.

### Misconception 20. “Every slow query just needs ANALYZE”

False. Slowness may stem from missing indexes, I/O bottlenecks, lock contention, bloat, query shape, or genuinely huge datasets.

### Misconception 21. “Seq Scan means the planner ignored statistics”

False. Statistics may prove Seq Scan is genuinely the cheapest option (e.g., matching 85% of rows).

### Misconception 22. “Lower estimated cost is always an improvement”

False. Fixing an underestimate from 1,000 to 100,000 rows raises estimated cost while helping the planner pick a far better plan.

### Misconception 23. “EXPLAIN ANALYZE does not execute SQL”

False. The `ANALYZE` option executes the statement—making it unsafe on unchecked production DML.

### Misconception 24. “pg_stats has per-tenant histograms automatically”

False. Table-wide `pg_stats` describes the **entire relation**, not per-tenant histograms. Use extended MCV or partitioning where needed.

### Misconception 25. “A generic plan knows tenant_id=$1 will be tenant 1”

False. Generic plans cannot specialize to unknown runtime parameters the way custom plans do.

### Misconception 26. “Once extended stats are created, ANALYZE is optional”

False. Statistics objects remain empty until populated by `ANALYZE`.

### Misconception 27. “Column stats eliminate the need for indexes”

False. Knowing only 0.1% of rows qualify does not give PostgreSQL a fast jump without an index.

### Misconception 28. “Raising statistics targets cluster-wide is a free optimization”

False. It increases `ANALYZE` time, catalog storage, and planning time; tune selectively where real queries suffer.

### Misconception 29. “Partition parents auto-update perfectly whenever children change”

False. Parent/inherited stats maintenance often requires explicit `ANALYZE parent` alongside child stats checks.

### Misconception 30. “pg_stats histograms double as official dashboard percentiles”

False. They are planner sampling summaries; official analytics require dedicated SQL queries with clear definitions.

## 36. Practice Exercises

Exercises use `query_stats_lab.events` from Section 4 on a PostgreSQL major version supporting the listed features. Perform statistics/config experiments only in a **lab database**, never production. `EXPLAIN` exercises ask you to reason about possible behaviors rather than forcing one fixed scan type.

### Exercise 1. Identifying Statistics Sources

Contrast the purposes of `pg_stats`, `pg_stats_ext`, `pg_stat_user_tables`, and `pg_class.reltuples`. Which provides a single column's histogram, and which records `last_autoanalyze`?

### Exercise 2. Manual null_frac Calculation

A table has 10,000 rows, 1,500 of which have `promo_code IS NULL`. Compute `null_frac` and predict the count of `promo_code IS NOT NULL`.

### Exercise 3. null_frac in the Lab

Write SQL to read `null_frac` for `promo_code` and count exact NULL rows in `query_stats_lab.events`. Roughly what number do you expect?

### Exercise 4. MCV and Frequencies

Suppose:

```text
null_frac         = 0.10
most_common_vals  = {paid,pending,cancelled}
most_common_freqs = {0.60,0.20,0.10}
```

On a 100,000-row table, estimate rows with `status='paid'` and rows with `NULL`. Should those frequencies be interpreted as normalized over non-NULL rows?

### Exercise 5. Equality Without MCV

If a column has 1,000 distinct values and no MCV list, why can a uniform assumption for `col='x'` fail badly on a rare or dominant value?

### Exercise 6. Histograms and Quantile Bounds

Explain why a histogram with bounds `{10,20,30,60,120,400}` does not use equal numeric intervals. Is this fixed PostgreSQL output or an illustration?

### Exercise 7. MCV and Histogram Overlap

Suppose `status='paid'` accounts for 80% of rows and sits in MCV. When reading `histogram_bounds`, should you assume the histogram spans those 80% uniformly too?

### Exercise 8. Numeric Range

Write a query fetching all events with `amount >= 5000`. Which statistics can PostgreSQL use to estimate its selectivity?

### Exercise 9. Negative n_distinct

A 200,000-row table reports `n_distinct=-0.25` for `customer_id`. Interpret this value and estimate the distinct count.

### Exercise 10. n_distinct and UNIQUE

Explain why `n_distinct=-1` never substitutes for a `UNIQUE` constraint, even if all current `event_id` values are distinct.

### Exercise 11. Physical Correlation

A `created_at` column has correlation near `+1`; in a reverse-loaded copy it has correlation near `-1`. What do both values say about physical storage order? Does `-1` make a B-tree index useless?

### Exercise 12. Correlation Between tenant_id and region

In the lab, `tenant_id=1` always implies `region='north'`. Can you inspect that relationship via `pg_stats.correlation` on `tenant_id`? What should you use instead?

### Exercise 13. Probabilistic Independence

Given `P(tenant=1)=0.7`, `P(north)=0.7`, and `P(tenant=1 AND north)=0.7`, compute the naive independent estimate on a 50,000-row table and compare it with actuals.

### Exercise 14. CREATE STATISTICS

Write SQL to create extended statistics with `dependencies`, `ndistinct`, and `mcv` on `(tenant_id, region)`, then collect the statistics.

### Exercise 15. Distinguishing Extended Statistics Kinds

Which kind captures functional dependence between columns? Which helps estimate `GROUP BY` distinct group counts? Which stores frequent combinations?

### Exercise 16. Reading pg_stats_ext

Write a query retrieving statistics object names, included columns, statistics kinds, and MCV frequencies for `query_stats_lab.events`.

### Exercise 17. Statistics Target

Raise `amount`'s target to 300, run `ANALYZE`, then reset it back to default afterward. Does raising the target guarantee faster queries?

### Exercise 18. Autoanalyze Threshold

Assuming `autovacuum_analyze_threshold=100`, `autovacuum_analyze_scale_factor=0.05`, and an estimated 200,000-row table, compute the baseline threshold. Does hitting it guarantee autoanalyze runs immediately at that exact instant?

### Exercise 19. Stale Stats

A table just loaded 1,000,000 rows after the last `ANALYZE`. Write SQL checking analyze timestamps and `n_mod_since_analyze`, and recommend next steps.

### Exercise 20. EXPLAIN Estimated vs. Actual

A node shows `rows=300` in `EXPLAIN` yet `actual rows=30000 loops=1` in `EXPLAIN ANALYZE`. By what factor is the planner off, and what root-cause categories should you investigate?

### Exercise 21. Loops

A nested-loop inner index scan reports `actual rows=3 loops=1000`. Roughly how many total rows did that node emit across all calls? Should you treat 3 as the total?

### Exercise 22. Generic vs. Custom Plans

Why can a prepared query `WHERE tenant_id=$1` perform very differently between giant and tiny tenants even though single-column stats know the giant tenant is common? Outline how to test using `plan_cache_mode`.

### Exercise 23. Statistics and Indexes

A column contains a rare 0.01% value, yet the table lacks a suitable index. Will raising the statistics target enable an Index Scan? Why or why not?

### Exercise 24. Histogram vs. width_bucket

Write a query using `width_bucket(amount, 0, 8000, 8)` to count rows per bin. Is this identical to `pg_stats.histogram_bounds`?

### Exercise 25. Partitioned Tables

A monthly partitioned parent table ingests new data into child partitions. Why monitor both parent and child statistics instead of checking only one child's `last_autoanalyze`?

### Exercise 26. Grouping Correlation Error

A `GROUP BY tenant_id, region` query produces far fewer actual groups than the planner estimated from single-column stats. Which extended statistics kind directly addresses this?

### Exercise 27. Time-Series Data Churn

`created_at` increases cleanly with insertion order, yet the histogram was collected before a new import batch. Is high `correlation` enough to estimate `created_at >= yesterday` accurately?

### Exercise 28. Designing a Diagnostic Runbook

Describe the first five steps for diagnosing a query that regressed after deployment: how to inspect SQL/parameters, plans, column distributions, stats freshness, and multi-column relationships.

## 37. Solution Hints

### Answer 1. Statistics Sources

- `pg_stats`: per-column distributions (MCV, histogram, correlation).
- `pg_stats_ext`: multi-column/expression statistics from statistics objects.
- `pg_stat_user_tables`: table activity stats, including `last_autoanalyze`.
- `pg_class.reltuples`: estimated relation row count.

Never confuse `pg_stats` with per-query runtime statistics views.

### Answer 2. null_frac

\[
\text{null\_frac}=\frac{1500}{10000}=0.15
\]

Non-NULL rows: `10000 - 1500 = 8500`.

### Answer 3. promo_code

```sql
SELECT attname, null_frac
FROM pg_stats
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'events'
  AND attname = 'promo_code';

SELECT COUNT(*) AS actual_null_rows
FROM query_stats_lab.events
WHERE promo_code IS NULL;
```

The lab dataset has 47,500 NULL rows (~95%); `null_frac` after `ANALYZE` will sit close to `0.95` subject to sampling.

### Answer 4. MCV

With 100,000 rows:

- `'paid'` ≈ 60,000 rows.
- SQL `NULL` ≈ 10,000 rows.

`most_common_freqs` expresses fractions of **total table rows**, not solely non-NULL rows—so 60% applies to the entire relation.

### Answer 5. Non-MCV Values

Uniform `1 / n_distinct` is only a fallback heuristic. Real data can skew heavily: one value may occur once while another occurs tens of thousands of times, leading to poor estimates for unrepresented literals.

### Answer 6. Histogram

Intervals can vary widely in numeric width so each bin contains roughly equal counts of non-NULL, non-MCV observations. `{10,20,30,60,120,400}` is an illustrative example, not guaranteed lab output.

### Answer 7. MCV and Histogram Overlap

No. PostgreSQL separates MCV entries from the histogram, which covers only the **non-NULL, non-MCV remainder**. Assuming the histogram covers all 100% would double-count frequencies.

### Answer 8. Range

```sql
SELECT event_id, amount
FROM query_stats_lab.events
WHERE amount >= 5000;
```

The planner uses `histogram_bounds` and `most_common_vals`/`most_common_freqs` on `amount` to estimate qualifying rows; actual scan cost also depends on indexes and projected columns.

### Answer 9. n_distinct

`-0.25` estimates distinct values at ~25% of table rows. On 200,000 rows:

\[
200000\times0.25=50000
\]

This is an estimate, not a live exact count.

### Answer 10. Unique

`n_distinct=-1` is purely statistical metadata and never blocks duplicate inserts. Enforcing uniqueness on `event_id` requires a `PRIMARY KEY` or `UNIQUE` constraint/index (which our lab table declares on `event_id`).

### Answer 11. Correlation

Near `+1`: values rise with physical heap order. Near `-1`: values fall with physical heap order—still a very strong ordering alignment, only reversed. B-tree indexes remain useful since PostgreSQL evaluates scan direction, locality, and cost.

### Answer 12. Two-Column Correlation

No. `pg_stats.correlation` does not measure tenant–region relationships. Check via:

```sql
SELECT tenant_id, COUNT(DISTINCT region)
FROM query_stats_lab.events
GROUP BY tenant_id;
```

Then create `CREATE STATISTICS ... (dependencies, mcv, ndistinct)` and inspect `pg_stats_ext` to model multi-column relationships.

### Answer 13. Independent Estimate

\[
0.7 \times 0.7 = 0.49
\]

\[
50000 \times 0.49 = 24500
\]

Actual count is 35,000 rows—an error of **10,500 rows**. This illustrates the independence assumption rather than guaranteeing what every PostgreSQL plan displays.

### Answer 14. Creating Stats

```sql
CREATE STATISTICS IF NOT EXISTS stats_exercise_tenant_region
    (dependencies, ndistinct, mcv)
ON tenant_id, region
FROM query_stats_lab.events;

ANALYZE query_stats_lab.events;
```

Without `ANALYZE`, the new statistics object holds no collected data for the planner.

### Answer 15. Kinds of Extended Statistics

- `dependencies`: functional dependencies.
- `ndistinct`: distinct combination counts.
- `mcv`: frequent multi-column combinations and their frequencies.

Each serves a different need; avoid enabling all kinds blindly if unnecessary.

### Answer 16. pg_stats_ext

```sql
SELECT
    statistics_name,
    attnames,
    kinds,
    most_common_vals,
    most_common_freqs
FROM pg_stats_ext
WHERE schemaname = 'query_stats_lab'
  AND tablename = 'events'
ORDER BY statistics_name;
```

MCV columns populate only when `mcv` was requested and supported by the data/version.

### Answer 17. Target

```sql
ALTER TABLE query_stats_lab.events
    ALTER COLUMN amount SET STATISTICS 300;

ANALYZE query_stats_lab.events;

ALTER TABLE query_stats_lab.events
    ALTER COLUMN amount SET STATISTICS -1;

ANALYZE query_stats_lab.events;
```

Higher targets refine distributions without guaranteeing faster execution and carry collection/storage costs.

### Answer 18. Autoanalyze Threshold

\[
100 + 0.05\times 200000 = 10100
\]

This is the baseline threshold; autovacuum workers are not guaranteed to trigger at the exact moment modifications cross 10,100.

### Answer 19. Stale Stats

```sql
SELECT
    relname,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'query_stats_lab'
  AND relname = 'events';
```

If distributions shifted heavily and stats are stale, consider running:

```sql
ANALYZE query_stats_lab.events;
```

then re-check estimates and plans for sensitive queries rather than assuming autoanalyze already ran immediately post-load.

### Answer 20. Row Error

`30000 / 300 = 100×` underestimate. Check stale stats, MCV/histograms, missing extended statistics, parameter skew, unindexed/unmodeled expressions, and partition stats.

### Answer 21. Loops

`3 × 1000 ≈ 3,000` rows emitted across 1,000 executions, since `actual rows` averages per loop. Never treat `3` as the cumulative total.

### Answer 22. Generic vs. Custom Plans

Giant and tiny tenants have wildly different row counts. A generic plan cannot specialize to `$1` the way custom plans can. Test via:

```sql
BEGIN;
SET LOCAL plan_cache_mode = force_custom_plan;
-- EXPLAIN EXECUTE <prepared statement name> with large/small tenant
ROLLBACK;

BEGIN;
SET LOCAL plan_cache_mode = force_generic_plan;
-- EXPLAIN EXECUTE the same statement with both values
ROLLBACK;
```

Ensure you `PREPARE` the statement first as shown in Section 25, and avoid changing `plan_cache_mode` globally for one query.

### Answer 23. Statistics vs. Index

No. Statistics tell the planner the value is rare, yet cannot create an index access path. Without an index, PostgreSQL may still have to perform a sequential scan.

### Answer 24. width_bucket

```sql
SELECT
    width_bucket(
        amount, 0::numeric, 8000::numeric, 8
    ) AS bucket,
    COUNT(*) AS n
FROM query_stats_lab.events
WHERE amount >= 0
  AND amount < 8000
GROUP BY 1
ORDER BY 1;
```

This builds **equal-width intervals** as written in SQL, whereas `pg_stats.histogram_bounds` chooses bounds so non-MCV intervals hold roughly equal observation counts.

### Answer 25. Partitioned Tables

Each partition has its own data distribution and analyze schedule, while parent/inherited stats guide cross-partition planning. Autoanalyze on children does not necessarily update parent stats. Inspect pruning, partition stats, and run `ANALYZE parent` when appropriate.

### Answer 26. Group Counts

Extended statistics with `ndistinct` on `(tenant_id, region)` directly improves distinct combination estimates for that `GROUP BY`.

### Answer 27. Correlation Does Not Replace Histograms

No. Correlation near `+1` only says timestamps increase with physical heap order—not **what share of rows fall after `yesterday`**. If the histogram predates the import, refresh statistics (and consider partitioning if applicable).

### Answer 28. Runbook

1. Collect SQL text, actual bind parameters, call frequency, and real latency.
2. Run `EXPLAIN (ANALYZE, BUFFERS)` safely to pinpoint nodes with largest estimated/actual gaps.
3. Inspect `pg_stats` on filter/order columns (MCVs, histograms, `null_frac`, `n_distinct`, `correlation`).
4. Check `last_analyze`, `last_autoanalyze`, and `n_mod_since_analyze`.
5. Check multi-column dependencies and `pg_stats_ext`; only adjust stats, targets, or indexes once the divergence source is clear.

## 38. Checklist for Designing, Diagnosing, and Maintaining Statistics

1. **Identify the real query:** exact `SELECT`, `JOIN`, `ORDER BY`, `LIMIT`, and concrete bind values.
2. **Locate the core error:** which node shows the biggest estimated vs. actual row divergence?
3. **Do not confuse cost with time:** cost uses relative units; actual timing requires `ANALYZE`.
4. **Never forget `loops`:** per-loop `actual rows` is not always the cumulative row count.
5. **Check freshness:** when did `ANALYZE` last run, and how much data changed since?
6. **Read NULLs properly:** check `null_frac`; never write `= NULL`.
7. **Read MCVs properly:** match values and frequencies positionally; frequencies scale over total rows.
8. **Read histograms properly:** excludes MCVs/NULLs; bounds balance observation counts, not arithmetic width.
9. **Read negative `n_distinct` properly:** distinct share relative to total rows.
10. **Never confuse stats with constraints:** `n_distinct=-1` is not `UNIQUE`; `null_frac=0` is not `NOT NULL`.
11. **Read `correlation` properly:** physical heap alignment of one column, not cross-column dependency.
12. **Watch for skew:** do hot tenants or statuses need different plans from rare values?
13. **Check dependencies:** do correlated predicates break the independence assumption?
14. **Use multivariate MCV when needed:** do recurring pairs/tuples drive selectivity?
15. **Use multi-column `ndistinct` appropriately:** are `GROUP BY` group estimates off?
16. **Run `ANALYZE` after `CREATE STATISTICS`:** definition alone does not populate stats.
17. **Tune targets locally:** raise only on columns where finer granularity measurably helps.
18. **Check expressions:** do functions or casts blind base-column statistics?
19. **Inspect generic vs. custom plans:** is parameter skew extreme?
20. **Check partitions:** verify child/parent stats and partition pruning together.
21. **Check indexes:** selectivity awareness still needs an index access path when helpful.
22. **Inspect actual runtime metrics:** buffers, I/O, memory spills, locks, cache, and concurrency.
23. **Measure before and after:** validate across diverse representative parameter values.
24. **Protect sensitive stats:** MCV lists can contain real data values; guard logs accordingly.

## 39. Summary

**Column statistics bridge physical data reality and the PostgreSQL query planner's decisions.** Without accurate distribution metadata, the optimizer misprices access paths even when optimal indexes already exist.

Key takeaways:

- **`ANALYZE`** samples rows to populate planner statistics—it is not an exact full-table count.
- **`null_frac`** tracks NULL share, while **`avg_width`** informs intermediate tuple sizing.
- **`n_distinct`** captures distinctness: positive values estimate exact counts, while negative values express proportions of table size.
- **`most_common_vals` / `most_common_freqs`** capture skewed high-frequency values critical for equality predicates.
- **`histogram_bounds`** partitions the **non-NULL, non-MCV** remainder into roughly equal-observation buckets for range estimation.
- **`correlation`** in `pg_stats` tracks alignment between one column's order and physical heap placement, shaping random I/O estimates for index scans; it **does not measure cross-column dependency**.
- **`CREATE STATISTICS`** models **multi-column** relationships (`dependencies`, `ndistinct`, multivariate `mcv`), though it does not fix all join estimates automatically.
- **Stale statistics and data skew** frequently separate estimated rows from actuals; weigh autoanalyze thresholds, column targets, and generic vs. custom plans against your workload.
- **`EXPLAIN (ANALYZE, BUFFERS)`** verifies plan reality—read `loops`, costs, inclusive timings, and buffer counters carefully, and avoid running `ANALYZE` carelessly on production DML.
- **Statistics never replace indexes, constraints, or good SQL design.** They guide choices among available options; true performance still depends on data layout, I/O, cache, concurrency, and architecture.

A habit worth keeping:

> Whenever PostgreSQL picks a surprising plan, first check **how many rows it expected at each step, which statistics backed that estimate, and where the true distribution diverges**. Only then decide between `ANALYZE`, extended statistics, new indexes, or rewriting the query.

That turns PostgreSQL tuning from “adding random indexes until it looks faster” into an evidence-backed, explainable, repeatable engineering discipline.
