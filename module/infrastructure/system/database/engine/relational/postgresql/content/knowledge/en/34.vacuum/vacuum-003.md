# ANALYZE and Updating Planner Statistics in PostgreSQL

## 1. Why Does PostgreSQL Need Statistics?

A SQL query can be executed in many ways. For example:

~~~sql
SELECT order_id, total_amount
FROM app.orders
WHERE customer_id = 1024;
~~~

PostgreSQL can choose a **Sequential Scan** (reading the table sequentially), an **Index Scan**, a **Bitmap Index Scan**, or another access path. If the query also joins `customers` and `order_items`, the planner must also pick the join order, join method, sorting/hashing strategy, and whether to parallelize.

To make these decisions, the planner needs estimates of:

- Roughly how many rows are in the table?
- How many distinct values exist in a column?
- How many rows contain NULL?
- Which values appear most frequently?
- How many rows will remain after a WHERE filter?
- Are two predicates on the same table correlated or roughly independent?
- How closely does the physical row order match the index order?
- Roughly how many groups is a GROUP BY expected to produce?
- How wide is the data in bytes, affecting sorts, hashes, and memory?

PostgreSQL cannot deduce all of this accurately from SQL syntax alone. It maintains **data statistics** (planner statistics), primarily via the `ANALYZE` command and the automatic **autovacuum/autoanalyze** mechanism.

If statistics are stale or fail to represent the current distribution, the planner can pick poor plans: scanning the entire table when an index would help, using a nested loop over a huge set, hash-joining with a table estimated to be far smaller than reality, spilling sorts/hashes, or picking the wrong join order. Queries can become drastically slower even though the SQL and indexes did not change.

**ANALYZE collects statistics so the planner can estimate data.** It does not modify business data, does not remove dead tuples, and does not replace VACUUM.

### 1.1. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish `ANALYZE`, `VACUUM`, `VACUUM ANALYZE`, and autoanalyze.
2. Read statistics fields in `pg_stats`: `null_frac`, `n_distinct`, MCV, histogram, correlation, and average width.
3. Understand how the planner uses statistics to estimate selectivity, cardinality, join order, and scan type.
4. Choose a default or per-column statistics target.
5. Use extended statistics to describe correlations across multiple columns and expressions.
6. Refresh statistics after bulk loads, backfills, data skew, or distribution changes.
7. Monitor analyze timestamps and autoanalyze progress.
8. Diagnose cases where `EXPLAIN` row estimates diverge from actual rows.
9. Handle statistics for partitioned tables, inheritance, foreign tables, and special objects.
10. Schedule analyze without causing unnecessary impact to active workloads.

### 1.2. Scope

This lesson focuses on statistics for the **PostgreSQL planner**. Examples use PostgreSQL SQL syntax and standard catalogs/views. Certain views, statistics columns, expression statistics features, and autoanalyze details vary by major version; check the documentation for the exact server version you run.

---

## 2. What Does ANALYZE Do?

### 2.1. Basic Command

~~~sql
ANALYZE app.orders;
~~~

PostgreSQL samples the table's data and collects statistics for eligible columns. Results are stored in system catalogs—primarily `pg_statistic`—and exposed through the `pg_stats` view.

You can analyze the entire database:

~~~sql
ANALYZE;
~~~

Or specific schemas/tables:

~~~sql
ANALYZE app.orders;
ANALYZE app.customers;
~~~

### 2.2. Specifying Specific Columns

~~~sql
ANALYZE app.orders (customer_id, order_status, created_at);
~~~

This is useful when only a few critical columns recently changed distribution or when focusing stats collection. Other unspecified columns are not refreshed by that command. Remember any relevant extended statistics objects and planner requirements.

### 2.3. Displaying Progress Details

~~~sql
ANALYZE VERBOSE app.orders;
~~~

`VERBOSE` prints additional information about statistics collection, including version-specific sampling details. This is helpful for observing manual runs in test or maintenance environments.

### 2.4. ANALYZE Does Not Read Every Single Row

PostgreSQL normally uses **sampling** rather than scanning and retaining every value of every row. Statistics are statistically grounded estimates, not exact counts.

Therefore:

- Running `ANALYZE` twice can produce slightly different numbers.
- Concurrent table modifications can make the sample reflect a point in time rather than every future transaction.
- Very large tables can still be analyzed at far lower cost than tracking every value of every row.
- Increasing the statistics target generally increases sample size/detail collected, at higher time and resource cost.

### 2.5. ANALYZE Does Not Modify Business Rows

`ANALYZE` does not UPDATE or DELETE rows in the table. It updates statistical metadata used by the planner. It is not a bloat-cleanup command, does not return data-file space to the OS, and does not alter business values.

### 2.6. ANALYZE Can Run While Serving Queries

ANALYZE is designed to run concurrently with normal read/write activity; it does not require an exclusive lock blocking all DML like some DDL statements. Even so, it still consumes I/O/CPU, reads pages, updates catalogs, and can compete with workloads for resources. On very large tables or many high-target columns, pick an appropriate time and measure impact.

---

## 3. Distinguishing ANALYZE and VACUUM

The two commands are often mentioned together, but their objectives differ.

| Command | Primary Purpose | Typical Effect |
|---|---|---|
| `ANALYZE table` | Collect planner statistics | Updates column/extended stats |
| `VACUUM table` | Clean/reclaim dead tuples when safe, update visibility/freeze metadata | Supports space reuse and MVCC |
| `VACUUM ANALYZE table` | Perform both goals | Cleans dead tuples then collects statistics |
| `VACUUM FULL table` | Rewrite table to reclaim physical disk space | Takes a strong lock, needs temp space, high cost |

### 3.1. When Is ANALYZE Alone Enough?

- Bulk importing many new rows.
- Data distribution shifted significantly.
- A backfill changed values across many rows.
- Skew/hot-value changes caused misestimates.
- Creating or updating an extended statistics object.
- The planner misestimates cardinality even though dead tuples are not an issue.

### 3.2. When Is VACUUM Needed?

- UPDATE/DELETE created many dead tuples.
- The table risks bloat or needs space reclaimed for reuse.
- The visibility map needs updating and tuples need freezing under MVCC.
- Autovacuum is falling behind the workload.

### 3.3. When to Use VACUUM ANALYZE?

After a large UPDATE/DELETE batch, you may need both dead-tuple cleanup and updated stats:

~~~sql
VACUUM (ANALYZE) app.orders;
~~~

Do not run `VACUUM ANALYZE` reflexively after every small INSERT. INSERTs can make cardinality/distribution stats stale, yet do not necessarily create significant dead tuples. `ANALYZE` alone may suffice.

### 3.4. VACUUM Alone Does Not Guarantee Optimal Stats

VACUUM and ANALYZE can be coordinated by autovacuum in certain situations, yet their functions remain distinct. If a table's distribution shifts sharply before reaching the autoanalyze threshold, the planner may need a manual `ANALYZE` even when vacuum is not needed.

### 3.5. ANALYZE Does Not Shrink a Table

If the issue is a table/index file occupying huge space after DELETEs, `ANALYZE` does not shrink the file. Understand that standard VACUUM reclaims space for reuse; `VACUUM FULL` rewrites and carries trade-offs. Do not confuse "planner stats updated" with "bloat resolved".

---

## 4. Where Does the Planner Use Statistics?

### 4.1. From SQL to Plan

~~~text
SQL statement
     |
     v
Parse / Rewrite
     |
     v
Planner / Optimizer
     |
     +--> Read catalogs, indexes, constraints
     |
     +--> Read statistics from ANALYZE
     |
     +--> Estimate selectivity/cardinality/cost
     |
     v
Choose execution plan
     |
     v
Executor runs plan
~~~

Statistics are one input to the planner, alongside schema, indexes, constraints, cost settings, parameter values, and other metadata.

### 4.2. Cardinality Estimation

**Cardinality** is the number of rows the planner predicts a plan node will return. For example:

~~~sql
SELECT *
FROM app.orders
WHERE order_status='paid';
~~~

If the table has 10 million rows and 20% are `paid`, the planner may estimate roughly 2 million rows. This estimate drives sequential vs. index scan choices, join choices, and memory sizing.

### 4.3. Selectivity

Selectivity is the fraction of rows satisfying a predicate. In the example above:

\[
\text{selectivity} \approx \frac{\text{matching rows}}{\text{total rows}}
\]

When selectivity is low, an index can be helpful; when high, a sequential scan can be cheaper. There is no rule that "if an index exists, it is always used".

### 4.4. Join Order

A multi-table join query has many possible join orders. Bad estimates on one table can mislead the planner into a poor join order, such as putting a huge table into an unsuitable nested loop outer/inner position.

### 4.5. Join Method

The planner can choose:

- **Nested Loop:** often effective when the outer side is small and the inner lookup has an efficient index.
- **Hash Join:** often effective for sufficiently large inputs where a hash table fits memory well.
- **Merge Join:** can be effective when inputs are already sorted or sort cost is reasonable.

Statistics affect cardinality and cost, which in turn decide the join method.

### 4.6. Sort, Aggregate, and Parallelism

Bad estimates can make the planner mispredict row/group counts, affecting sorts, hash aggregates, hash memory, disk spills, and parallel plan decisions. Good statistics do not guarantee a perfect plan, but they are essential for realistic planner estimates.

### 4.7. ANALYZE Does Not Create Indexes

If a query needs an access path that lacks an index, `ANALYZE` will not create one. It only helps the planner evaluate existing access paths. Likewise, ANALYZE does not rewrite SQL or raise `work_mem`.

---

## 5. Core Statistics Sources in pg_stats

### 5.1. Viewing Column Statistics

~~~sql
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
WHERE schemaname='app'
  AND tablename='orders'
ORDER BY attname;
~~~

`pg_stats` is a more readable view over the internal `pg_statistic` catalog. Some fields are populated only when supported by the column's data type and statistics configuration. If a column is missing, verify the relation, privileges, and whether ANALYZE has run.

### 5.2. null_frac

`null_frac` is the estimated fraction of NULL values in the column.

| Column | null_frac | Interpretation |
|---|---:|---|
| `customer_id` | 0.00 | Virtually no NULLs |
| `coupon_code` | 0.75 | Roughly 75% NULL rows |
| `shipped_at` | 0.40 | Roughly 40% NULL rows |

The planner uses this to estimate predicates such as `IS NULL`, `IS NOT NULL`, and other clauses.

### 5.3. avg_width

`avg_width` is the estimated average stored size (in bytes) of the column's values. It helps the planner estimate row width and the cost of operations that store or pass rows.

For `text`, `jsonb`, `bytea`, or variable-length columns, average width can swing sharply with workload changes. If payload sizes grow, stale stats can cause the planner to misjudge memory/I/O.

### 5.4. n_distinct

`n_distinct` is the estimated number of distinct values:

- Positive value: estimated absolute count of distinct values.
- Negative value: magnitude represents a fraction of total rows in the table.

Examples:
- `n_distinct = 100`: roughly 100 distinct values.
- `n_distinct = -1`: column is nearly unique; distinct count approximates row count.
- `n_distinct = -0.1`: distinct count is roughly 10% of table rows.

This value is especially important for GROUP BY, DISTINCT, and equality selectivity when a value is not in the MCV list.

### 5.5. most_common_vals (MCV)

MCV is the list of **Most Common Values**—the most frequently occurring values in the sample/stats—paired with their frequencies in `most_common_freqs`.

For example, `order_status` might have:

| Value | Frequency |
|---|---:|
| `paid` | 0.60 |
| `new` | 0.20 |
| `cancelled` | 0.15 |
| Other values | 0.05 |

If `paid` is an MCV, the planner can use its specific frequency instead of assuming all distinct values have equal probability.

### 5.6. histogram_bounds

The histogram describes the distribution of remaining non-NULL values, typically after MCV values are separated out. Boundaries represent buckets with roughly equal sample counts (equidepth) under the statistics algorithm.

The planner uses histograms to estimate range predicates such as:

~~~sql
WHERE created_at >= TIMESTAMPTZ '2026-01-01'
  AND created_at <  TIMESTAMPTZ '2026-02-01'
~~~

A histogram is not a list of every value and does not guarantee each interval holds the exact same number of rows as data evolves.

### 5.7. correlation

`correlation` describes the statistical correlation between the **physical order of rows in the heap** and the logical order of column values (typically ascending), ranging from -1 to +1.

- Near +1: heap order aligns closely with column value order.
- Near -1: heap order is closely reversed relative to column value order.
- Near 0: physical order is largely uncorrelated with value order.

This is **not** a correlation coefficient between two business columns, such as `customer_id` and `region`. It helps the planner estimate index and heap page access costs.

### 5.8. Statistics for Arrays and Special Data Types

`pg_stats` also includes fields such as `most_common_elems`, `most_common_elem_freqs`, and `elem_count_histogram` for eligible types. These support the planner for specific operators and array predicates. Not every data type populates every field.

### 5.9. Statistics Are Estimates, Not Exact Counts

`pg_stats.n_distinct`, MCV frequencies, and histograms come from sampling. Do not use them as exact business reports like `COUNT(DISTINCT ...)`. When exact figures are required, run an appropriate query while accounting for its cost.

---

## 6. How MCV and Histograms Work Together to Estimate Selectivity

### 6.1. Equality with a Common Value

~~~sql
SELECT *
FROM app.orders
WHERE order_status='paid';
~~~

If `paid` appears in `most_common_vals`, the planner can use its matching frequency from `most_common_freqs` to estimate row count.

### 6.2. Equality with a Rare/Non-MCV Value

If the value is absent from MCV, the planner typically estimates using the distinct count and remaining non-MCV frequency share. With heavily skewed data, estimates can suffer if the MCV list lacks sufficient detail.

### 6.3. Range Predicates

~~~sql
SELECT *
FROM app.orders
WHERE total_amount BETWEEN 100 AND 200;
~~~

The histogram helps the planner estimate the fraction of rows falling inside the interval. If the data has a very narrow spike or many empty gaps that the histogram cannot capture adequately, estimates can still be off.

### 6.4. NULL Predicates

`null_frac` provides selectivity for:

~~~sql
WHERE coupon_code IS NULL
~~~

and

~~~sql
WHERE coupon_code IS NOT NULL
~~~

NULL is not treated as an ordinary value inside the histogram; the planner tracks it separately.

### 6.5. Why Can a Low MCV Target Cause Bad Estimates?

Suppose a table has millions of rows, a handful of `customer_id` values are extremely hot, and the rest have low frequency. If those hot values are not captured in the MCV list, the planner may treat an equality predicate on a hot customer just like an ordinary distinct value.

Raising the statistics target for that column can make the MCV list more detailed, at the cost of extra sampling/metadata overhead. Verify with `EXPLAIN` before and after.

---

## 7. ANALYZE and Data Sampling

### 7.1. Why Sample?

On a billion-row table, scanning every row just to compute planner statistics would be prohibitively expensive. Sampling allows distribution estimation at dramatically lower cost.

### 7.2. Sampling Can Miss Rare Values

If a value appears only rarely, the sample may not pick representative rows for it. Consequently, MCV/histograms cannot accurately describe every tail value.

### 7.3. Sampling Target

`default_statistics_target` controls the default level of statistical detail. A higher target generally increases sample size and statistical resolution, at the cost of more time, I/O, and catalog space. The target is not literally "the number of rows to analyze".

### 7.4. Statistics Needs Vary by Column

A single table might have:
- `status`: few values, heavy skew.
- `customer_id`: many distinct values, a few extremely hot customers.
- `created_at`: time-ordered distribution.
- `payload`: wide, diverse JSONB.

Each column has different statistics target needs. Do not set an extreme target on every column just because one query has a bad estimate.

### 7.5. Analyzing While Data Changes

ANALYZE samples at the time it runs; concurrent transactions may insert, update, or delete rows. Once finished, stats are a best-effort snapshot and can go stale quickly under heavy write rates. Autovacuum/autoanalyze continues refreshing them per thresholds.

### 7.6. Small Tables

For small tables, PostgreSQL can sample most or all rows depending on limits and sampling mechanics. On tiny tables, raising the target from 100 to 1,000 may bring no noticeable improvement.

### 7.7. No Need to ANALYZE Every INSERT

Running ANALYZE after every handful of rows is wasteful. Let autoanalyze handle normal churn, and run it manually after major changes or when evidence shows planner stats are stale.

---

## 8. Statistics Target

### 8.1. Default Target

~~~sql
SHOW default_statistics_target;
~~~

The common default is 100, though it can vary by PostgreSQL version/distribution or cluster configuration.

### 8.2. Per-Column Target

~~~sql
ALTER TABLE app.orders
ALTER COLUMN customer_id
SET STATISTICS 1000;

ANALYZE app.orders (customer_id);
~~~

This requests more detailed statistics for `customer_id`. The number 1000 is an **example for testing**, not a universal recommendation.

### 8.3. Reverting to the Default Target

~~~sql
ALTER TABLE app.orders
ALTER COLUMN customer_id
SET STATISTICS -1;
~~~

`-1` means use the default target. A value of `0` disables statistics collection for the column where appropriate; do not do this on query-critical columns without evaluation.

### 8.4. Changing the Default in a Session

~~~sql
SET default_statistics_target = 300;
ANALYZE app.orders;
~~~

This is a current-session setting; it affects ANALYZE commands executed in that session per config rules. For persistent system/role/database configuration, manage it through proper configuration mechanisms and permitted privileges.

### 8.5. Higher Targets Are Not Always Better

Trade-offs:

- ANALYZE takes more time and resources.
- Statistics catalog footprint grows.
- MCV/histograms are finer-grained, which can improve estimates for skewed distributions.
- Some queries still see no benefit if their predicates/joins are not helped by those stats.
- Sampling remains an estimate; raising the target does not turn stats into exact full-table counts.

### 8.6. Choosing Targets Based on Evidence

Process:

1. Identify the query with bad estimates.
2. Identify the column/predicate causing the error.
3. Read `pg_stats`.
4. Check whether MCV/histogram captures the distribution.
5. Raise the target only on the needed column.
6. Run ANALYZE.
7. Compare `EXPLAIN` estimates/plans and runtimes on a representative workload.
8. Keep the higher target if there is measurable gain and acceptable overhead; otherwise revert to an appropriate level.

### 8.7. A Table's Target Does Not Mean Uniform Sampling Effort for Every Column

A few columns with high targets can raise sampling effort for the relation, yet exact cost and statistics size also depend on column count, data types, and extended statistics objects. Do not predict exact ANALYZE duration from a single target number.

---

## 9. Extended Statistics: Describing Multi-Column Relationships

### 9.1. The Problem with Assuming Column Independence

Suppose `app.users` has two columns: `country` and `currency`. In real data, most users in Vietnam use VND, and users in Japan use JPY. The two columns are strongly correlated.

~~~sql
SELECT *
FROM app.users
WHERE country='VN'
  AND currency='VND';
~~~

If the planner only has single-column stats and assumes independence, it multiplies the two selectivities. The result can severely misrepresent the true distribution of value pairs.

### 9.2. CREATE STATISTICS

PostgreSQL provides **extended statistics** to collect metadata across multiple columns or expressions on the same table.

~~~sql
CREATE STATISTICS app.users_country_currency_stats
    (dependencies, ndistinct, mcv)
ON country, currency
FROM app.users;

ANALYZE app.users;
~~~

Available statistics kinds:

- **dependencies:** functional dependencies between columns.
- **ndistinct:** estimated count of distinct combinations.
- **mcv:** most common combinations.

You do not need all three for every column pair. Choose based on query patterns and the type of estimation error.

### 9.3. Functional Dependencies

For instance, if `zip_code` nearly determines `city`, the condition:

~~~sql
WHERE zip_code='700000'
  AND city='Ho Chi Minh City'
~~~

can be strongly correlated. If the planner assumes independence, it may underestimate selectivity far below reality.

Extended dependency statistics help the planner recognize such relationships in eligible predicates.

### 9.4. Limitations of Dependencies

Functional dependency statistics are not a general correlation model. The planner uses them mainly for simple clauses such as equality with constants and certain eligible `IN` forms; do not expect them to cover arbitrary range predicates, `LIKE`, complex expressions, column-to-column comparisons, or join selectivity.

If a query still misestimates, verify whether its predicates are supported by that extended stats kind.

### 9.5. Multivariate ndistinct

A multi-column GROUP BY query:

~~~sql
SELECT country, currency, count(*)
FROM app.users
GROUP BY country, currency;
~~~

The number of groups is not necessarily `distinct(country) × distinct(currency)`. Multivariate ndistinct statistics help the planner estimate the number of distinct multi-column combinations, improving group-count and aggregate-cost predictions.

### 9.6. Multivariate MCV

MCV statistics for common combinations capture skew at the tuple-of-columns level. For example, certain country/currency pairs occur heavily while others are very rare or nonexistent.

The planner can apply this when query predicates match. MCV is not an exhaustive lookup table of all combinations; it stores only common combinations within statistical bounds.

### 9.7. Viewing Extended Statistics

~~~sql
SELECT
    stxname,
    stxkeys,
    stxkind
FROM pg_statistic_ext
WHERE stxnamespace='app'::regnamespace;
~~~

`stxkind` shows the requested statistics types. Collected data is stored in an associated catalog such as `pg_statistic_ext_data`, where direct access has privilege limits and internal representations. Prefer `pg_stats_ext` or `pg_stats_ext_exprs` when your version provides those views.

### 9.8. Extended Statistics Apply Within a Single Relation

Extended statistics are defined on columns/expressions of **one table**. They are not a mechanism to declare arbitrary cross-table correlations to fix join cardinality automatically. If join estimates are off, examine per-table stats, join keys, uniqueness/FK constraints, data distribution, and query shape.

---

## 10. Extended Statistics for Expressions

### 10.1. Queries on Expressions

An application may frequently run:

~~~sql
SELECT *
FROM app.customers
WHERE lower(email)='alice@example.com';
~~~

Statistics on `email` alone may not describe the distribution of `lower(email)`, especially with mixed-case variations.

### 10.2. CREATE STATISTICS on an Expression

In PostgreSQL versions supporting expression statistics:

~~~sql
CREATE STATISTICS app.customers_lower_email_stats
ON (lower(email))
FROM app.customers;

ANALYZE app.customers;
~~~

The planner can then use expression statistics for matching queries. Support and syntax for expression statistics depend on version; verify before deploying migrations to production.

### 10.3. Combining Columns and Expressions in Extended Statistics

~~~sql
CREATE STATISTICS app.customer_region_lower_name_stats
    (mcv, dependencies)
ON region, (lower(customer_name))
FROM app.customers;

ANALYZE app.customers;
~~~

This captures relationships between `region` and `lower(customer_name)` on the same table, within what the planner supports.

### 10.4. Statistics Do Not Replace an Expression Index

If queries look up by `lower(email)` and need fast access, an expression index may be required:

~~~sql
CREATE INDEX ix_customers_lower_email
ON app.customers (lower(email));
~~~

- **Expression statistics** help the planner estimate distribution.
- **Expression indexes** provide the access path to locate rows.

They solve two different problems and complement each other.

### 10.5. Do Not Create Stats for Every Expression

Every statistics object adds metadata and analyze overhead. Creating objects for expressions that never appear in workloads yields no meaningful benefit. Prioritize high-frequency/high-cost expressions with documented misestimates.

---

## 11. Building a Distribution Statistics Lab

This section creates a test dataset to observe differences in value counts and skew. Run only in a lab database where you have privileges to create schemas and tables.

### 11.1. Create Schema and Table

~~~sql
CREATE SCHEMA IF NOT EXISTS analyze_lab;

CREATE TABLE analyze_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_id integer NOT NULL,
    region text NOT NULL,
    order_status text NOT NULL,
    total_amount numeric(12,2) NOT NULL,
    created_at timestamptz NOT NULL,
    coupon_code text
);
~~~

### 11.2. Generate Skewed Data

~~~sql
INSERT INTO analyze_lab.orders
    (order_id,customer_id,region,order_status,
     total_amount,created_at,coupon_code)
SELECT
    g,
    CASE
      WHEN g % 100 < 40 THEN 1
      ELSE 2 + (g % 9998)
    END,
    CASE
      WHEN g % 100 < 60 THEN 'north'
      ELSE 'south'
    END,
    CASE
      WHEN g % 100 < 70 THEN 'paid'
      WHEN g % 100 < 90 THEN 'new'
      ELSE 'cancelled'
    END,
    (10 + (g % 50000))::numeric / 10,
    timestamptz '2025-01-01 00:00:00+00'
       + (g % 365) * interval '1 day',
    CASE
      WHEN g % 4 = 0 THEN NULL
      WHEN g % 100 < 5 THEN 'VIP'
      ELSE 'STANDARD'
    END
FROM generate_series(1,200000) AS g;
~~~

This dataset deliberately introduces uneven distributions: `customer_id = 1` is hot, `paid` is common, and `coupon_code` has many NULLs. This is lab data, not representative of a real production system.

### 11.3. Create Indexes to Compare Access Paths

~~~sql
CREATE INDEX ix_analyze_orders_customer
ON analyze_lab.orders(customer_id);

CREATE INDEX ix_analyze_orders_status
ON analyze_lab.orders(order_status);

CREATE INDEX ix_analyze_orders_region_status
ON analyze_lab.orders(region,order_status);
~~~

### 11.4. Inspect Stats Before Analyzing

A newly loaded table may not yet have full column statistics. Check:

~~~sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname='analyze_lab'
  AND tablename='orders'
ORDER BY attname;
~~~

Results depend on whether stats already appeared from autoanalyze or prior operations. Do not assume they are always NULL.

### 11.5. Run ANALYZE

~~~sql
ANALYZE VERBOSE analyze_lab.orders;
~~~

### 11.6. Read the Statistics

~~~sql
SELECT
    attname,
    null_frac,
    avg_width,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    correlation
FROM pg_stats
WHERE schemaname='analyze_lab'
  AND tablename='orders'
ORDER BY attname;
~~~

Observations:
- `customer_id` has an MCV hot value.
- `order_status` has MCVs matching its frequencies.
- `coupon_code` has a substantial NULL fraction.
- `correlation` reflects physical order per individual column, not the relationship between `region` and `status`.

### 11.7. Check Exact Counts to Compare with Estimates

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE customer_id=1) AS hot_customer_rows,
    COUNT(*) FILTER (WHERE order_status='paid') AS paid_rows,
    COUNT(*) FILTER (WHERE coupon_code IS NULL) AS null_coupon_rows
FROM analyze_lab.orders;
~~~

This query computes exact numbers on the lab table. It requires a full scan; do not run full-table `COUNT` queries continuously on massive production tables just to substitute for planner statistics.

### 11.8. Compare Estimates Against Actuals

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM analyze_lab.orders
WHERE customer_id=1;

EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM analyze_lab.orders
WHERE customer_id=9999;
~~~

The planner can choose different access paths due to selectivity. If the hot customer owns many rows, a sequential scan can be cheaper than an index lookup; for a rare customer, an index fits well.

`EXPLAIN ANALYZE` actually executes the query. For SELECT in a lab, it reads data and consumes resources without modifying rows. For DML, it executes the DML and triggers for real; run only in a lab or inside a rolled-back transaction while understanding side effects.

---

## 12. Reading EXPLAIN: Estimated Rows vs. Actual Rows

### 12.1. Simplified Output Example

~~~text
Seq Scan on orders  (cost=0.00..4500.00 rows=80000 width=64)
                    (actual time=0.050..28.000 rows=140000 loops=1)
  Filter: (order_status = 'paid')
  Rows Removed by Filter: 60000
Planning Time: 0.300 ms
Execution Time: 32.000 ms
~~~

This is illustrative output, not from a real dataset run.

- **rows=80000** in the cost section: planner's **estimated** row count.
- **actual rows=140000**: rows actually returned by the executor per loop.
- **loops=1**: node executed once.
- **width=64**: planner's estimated row width.
- **Rows Removed by Filter**: rows read and discarded by the filter.
- **cost**: internal relative cost units, not milliseconds.

### 12.2. Actual Rows When loops Exceeds 1

For an inner nested loop node with `loops=1000`, `actual rows` is displayed by EXPLAIN as the average rows per loop. To understand total rows processed, multiply `actual rows × loops`, keeping in mind displayed numbers may be rounded.

Never compare estimated rows and actual rows while ignoring `loops`.

### 12.3. Planning Time and Execution Time

- **Planning Time:** time spent by the planner generating the plan.
- **Execution Time:** time spent by the executor running the query as measured by EXPLAIN.

ANALYZE statistics can affect plan choice and planning cost, yet slow queries can also stem from I/O, locks, cache, network, row width, memory, concurrency, and many other factors.

### 12.4. Estimation Error

A quick check is the ratio of actual to estimated rows, but avoid jumping to conclusions from a single node. Upper nodes inherit compounding errors from child nodes; a large misestimate at a base scan can distort join order across the entire query.

### 12.5. Finding the First Node That Diverges Badly

When a plan is bad, read from the leaves upward:
1. Which scan node has estimated rows far off from actual rows?
2. Which predicate is causing the error?
3. Are column stats up to date?
4. Does the column have skew or missing MCV coverage?
5. Do multi-column predicates need extended stats?
6. Is there an expression/cast/function preventing stats from matching the query expression?
7. Is a prepared generic plan ignoring specific parameter values?
8. Did data distribution change after ANALYZE?

### 12.6. EXPLAIN Alone Does Not State the Root Cause

If the planner chooses Seq Scan, do not immediately assume stats are wrong. A sequential scan may genuinely be cheaper, the index may not be selective, the table may be small, the query may request most columns, or visibility/cache/I/O/cost parameters may drive the choice.

### 12.7. Do Not Force Planner Flags to Mask Bad Stats

Disabling Seq Scan, forcing join methods, or tweaking cost parameters might speed up one sample query while causing plan regressions elsewhere. First understand cardinality and data distribution; use planner enable flags primarily as diagnostic tools in a test session, not as a global fix.

---

## 13. Stale Stats After Bulk Loads and Data Changes

### 13.1. When Is Manual ANALYZE Needed?

- COPY/INSERT of a large batch of rows into a previously small or empty table.
- A backfill altering value proportions.
- Importing a data partition with a distribution very different from prior partitions.
- Deleting a large share of rows or bulk-transitioning states.
- Distribution shifts in hot keys, tenants, or statuses.
- Query plan regressions occurring right after a data migration.

### 13.2. Why Might Autoanalyze Not Have Run Yet?

Autoanalyze relies on thresholds/scale factors and recorded modification counts. Right after a bulk load, the table may still be waiting for a worker, workers may be busy, table settings may differ from defaults, or a partitioned parent lacks tuple counters like a regular table.

If critical queries run right after an import, run manual ANALYZE before opening traffic or new read paths.

### 13.3. After CREATE INDEX

Creating an index does not automatically guarantee all column statistics are freshly updated. If workload/query plans depend on recently altered distributions, run an explicit ANALYZE after the migration step as appropriate.

### 13.4. After Restore/Clone

Restoring may or may not carry over stats depending on the restore method/version. After importing a large dataset, stats may not yet represent the new dataset. Include an analyze step in your runbook before routing traffic.

### 13.5. Analyze in Online Migrations

When adding a column and backfilling, stats on the new column may not exist yet or may lag behind the backfill. A deployment sequence should include:
- Schema addition.
- Deploying code that writes the new data.
- Batch backfilling.
- ANALYZE on critical columns/expressions.
- Verifying plans and latency.
- Switching read paths / cutover.

Do not cut over query-critical traffic right after a bulk load without reviewing planner stats.

---

## 14. Autovacuum and Autoanalyze

### 14.1. Automatic Statistics Collection

PostgreSQL runs an autovacuum launcher and workers. In addition to automatic VACUUM, workers perform **autoanalyze** when a relation's statistics are considered sufficiently stale according to thresholds.

### 14.2. Threshold and Scale Factor

Key settings include:

~~~sql
SHOW autovacuum;
SHOW autovacuum_analyze_threshold;
SHOW autovacuum_analyze_scale_factor;
SHOW autovacuum_naptime;
SHOW autovacuum_max_workers;
~~~

The autoanalyze threshold for a table is generally described by:

\[
\text{analyze threshold}
=
\text{autovacuum\_analyze\_threshold}
+
\text{autovacuum\_analyze\_scale\_factor}
\times
\text{estimated table tuples}
\]

Common defaults are threshold 50 and scale factor 0.1, though you must inspect actual server configuration and table-level reloptions.

### 14.3. Threshold Estimation Example

For a table with roughly 1,000,000 rows, the illustrative threshold is:

\[
50 + 0.1 \times 1{,}000{,}000 = 100{,}050
\]

This is an estimated change count per the statistics mechanism, not a guarantee that autoanalyze runs immediately after row 100,050. Actual timing also depends on worker scheduling, stats collector state, table settings, and system load.

### 14.4. INSERT/UPDATE/DELETE

Modern PostgreSQL versions track modifications to evaluate analyze thresholds across inserts, updates, and deletes; exact counters and formulas can vary by version. Do not assume one legacy formula applies identically to every server.

### 14.5. Table-Level Settings

Thresholds can be overridden per table:

~~~sql
ALTER TABLE app.orders SET (
    autovacuum_analyze_threshold = 1000,
    autovacuum_analyze_scale_factor = 0.02
);
~~~

This is an example configuration that requires benchmarking. Setting a small scale factor refreshes stats more often at higher background resource cost; setting it too high leaves stats stale longer.

### 14.6. Autovacuum Does Not Always Run Immediately

Autovacuum workers may be busy, constrained by worker count, cost delays, or other maintenance workloads. Manual ANALYZE is appropriate for specific needs; do not run a per-minute cron ANALYZE over the entire database to compensate for misconfigured autovacuum.

### 14.7. Partitioned Parent

A partitioned parent does not store heap tuples like an ordinary table. Modifications in child partitions do not necessarily trigger autoanalyze on the parent the way regular tables work. When parent-level/global stats matter, **schedule ANALYZE on the parent** periodically or after major partition loads, while also checking individual partitions as needed.

### 14.8. Checking Whether Autovacuum Is Enabled

Autovacuum can be disabled at the system level, yet autovacuum is also tied to freeze/wraparound safety. Never disable it globally just to cut I/O. If a specific table needs special handling, tune table-level settings while still ensuring wraparound maintenance.

### 14.9. Autoanalyze and Auto-Vacuum Are Distinct Activities

A table may need ANALYZE without having many dead tuples, or need VACUUM even when stats are not stale. `last_analyze` and `last_autovacuum` track different events; do not treat one field as a substitute for the other.

---

## 15. Monitoring ANALYZE and Autoanalyze

### 15.1. pg_stat_user_tables

This view exposes per-relation activity. A common query:

~~~sql
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
WHERE schemaname='app'
ORDER BY n_mod_since_analyze DESC NULLS LAST;
~~~

Some columns can differ by PostgreSQL version. Check the actual view schema on older servers or managed services with custom compatibility.

### 15.2. Field Meanings

- **last_analyze:** timestamp of the most recent recorded manual ANALYZE.
- **last_autoanalyze:** timestamp of the most recent autoanalyze.
- **analyze_count:** count of manual ANALYZE runs per the statistics collector.
- **autoanalyze_count:** count of autoanalyze runs.
- **n_mod_since_analyze:** estimated number of modified tuples since the last analyze, in supported versions.
- **n_live_tup / n_dead_tup:** estimates of live/dead tuples, not exact COUNTs.

If `last_autoanalyze` is NULL, it is not necessarily an error: the table may not have reached threshold yet, may never have been autoanalyzed, or stats may have recently been reset.

### 15.3. Checking Tables Not Analyzed Recently

~~~sql
SELECT
    schemaname,
    relname,
    last_analyze,
    last_autoanalyze,
    n_mod_since_analyze,
    n_live_tup
FROM pg_stat_user_tables
WHERE n_live_tup > 0
ORDER BY last_autoanalyze NULLS FIRST;
~~~

This is a list for investigation, not a list of tables that "must immediately run ANALYZE". Cross-check workload, table churn, query plans, and autoanalyze thresholds.

### 15.4. Statistics Resets

Counters can be reset by statistics reset calls or restarts/maintenance depending on stats type and version. When comparing over time, always note the reset timestamp and never treat counts since reset as lifetime totals.

### 15.5. pg_stat_progress_analyze

Modern PostgreSQL versions provide an ANALYZE progress view:

~~~sql
SELECT *
FROM pg_stat_progress_analyze;
~~~

This view can report the relation, phase, and sampling/extended statistics progress using version-specific fields. Consult the documentation for your exact major version since columns and phases can vary.

### 15.6. Combining with pg_stat_activity

~~~sql
SELECT
    p.pid,
    p.datname,
    p.relid::regclass AS relation_name,
    p.phase,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_stat_progress_analyze AS p
JOIN pg_stat_activity AS a USING (pid);
~~~

This illustrative query helps when ANALYZE runs long. Some columns may not exist on older versions; trim the SELECT list if needed.

### 15.7. ANALYZE and pg_stat_activity

Because ANALYZE is a regular command, it is usually visible in `pg_stat_activity` while running. However, seeing the query text alone does not tell you whether it is sampling or waiting on a lock; combine it with the progress view, wait events, and logs.

---

## 16. Reading pg_stats Properly

### 16.1. Querying a Specific Column

~~~sql
SELECT
    attname,
    inherited,
    null_frac,
    avg_width,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds,
    correlation
FROM pg_stats
WHERE schemaname='analyze_lab'
  AND tablename='orders'
  AND attname IN ('customer_id','order_status','coupon_code');
~~~

The `inherited` field distinguishes statistics computed directly on the relation from statistics inherited across child relations in inheritance/partition setups.

### 16.2. Why Might pg_stats Omit a Column?

- ANALYZE has not run or the relation has no stats yet.
- Query filtered the wrong schema/table/column.
- The current role lacks privileges to view detailed stats for the relation under security rules.
- The column was dropped, is a system column, or does not belong to the expected relation.
- The data type/operator lacks an eligible statistics slot.
- The column's statistics target is 0 or stats have not been collected.

### 16.3. pg_statistic Is an Internal Catalog

`pg_statistic` stores the internal representation of statistics. Never manually INSERT/UPDATE/DELETE rows in this catalog. Use `ANALYZE`, `ALTER TABLE ... SET STATISTICS`, and `CREATE/ALTER STATISTICS` to manage collection.

### 16.4. Privileges to Read Statistics

`pg_stats` enforces security rules so it does not expose statistics of tables a role is not permitted to read. Internal catalogs have stricter access restrictions. Grant monitoring roles least privilege according to policy.

### 16.5. Array Values Are Representations, Not a Business API

Columns like `most_common_vals` and `histogram_bounds` are arrays whose types/formatting vary by column type. They are fine for inspection in a SQL client, but do not parse text output in brittle scripts for business logic. If metrics are needed, build explicit, version-aware monitoring queries.

---

## 17. ANALYZE on Partitioned Tables and Inheritance

### 17.1. Partitioned Tables Have a Parent and Partitions

~~~text
orders (partitioned parent)
    |
    +-- orders_2026_01
    +-- orders_2026_02
    +-- orders_2026_03
~~~

The parent is a logical relation; partitions store the rows. The planner needs appropriate stats for partition pruning, whole-table estimates, and per-partition plans.

### 17.2. Analyzing the Parent

~~~sql
ANALYZE app.orders;
~~~

Normally, analyzing a partitioned/inheritance relation processes child partitions/relations per PostgreSQL semantics. Parent-level statistics serve queries targeting the parent; per-partition statistics serve plans when pruning or scanning individual children.

### 17.3. ONLY

~~~sql
ANALYZE ONLY app.orders;
~~~

`ONLY` analyzes the named relation without analyzing descendants under inheritance rules. Use it only with a specific reason; for a partitioned parent, if the goal is refreshing aggregate statistics from partitions, analyzing only the parent without descendants may not reflect the data you want.

### 17.4. Autoanalyze and the Partitioned Parent

A partitioned parent does not store heap tuples like a normal table, so autovacuum does not necessarily trigger autoanalyze on the parent just because partitions receive many rows. When global/parent-level stats matter, schedule ANALYZE on the parent after major loads or partition maintenance and verify plans.

### 17.5. Analyzing Individual Partitions

~~~sql
ANALYZE app.orders_2026_03;
~~~

This is useful when a new partition was heavily loaded or has a distribution distinct from older partitions. Yet if queries target the parent, do not neglect parent statistics.

### 17.6. Inheritance and Inherited Statistics

With classic table inheritance, queries against the parent can include rows from descendants. PostgreSQL stores inherited/non-inherited stats separately where applicable; `pg_stats` exposes the `inherited` flag to distinguish them. When using `ONLY` or querying descendants directly, the planner relies on the corresponding stats.

### 17.7. Partition Pruning Does Not Replace ANALYZE

Partition pruning determines which partitions can be skipped based on partition keys/constraints. ANALYZE provides row and distribution stats within relations. A system with working partition pruning can still severely misestimate row counts inside a partition if stats are stale.

### 17.8. Partitions with Different Skew

For example, the current month's partition contains mostly `new` orders while older partitions contain mostly `cancelled`/`archived` rows. An averaged parent statistic may not describe an individual partition accurately for every query. The planner combines metadata and stats per plan; after loading a new partition, analyze both the partition and the parent as needed.

---

## 18. ANALYZE on Foreign Tables and Materialized Views

### 18.1. Foreign Tables

PostgreSQL can collect statistics for foreign tables when the foreign data wrapper supports the required operation. Cost can include reading data from the remote source; never assume analyzing a foreign table is a cheap local operation.

### 18.2. FDW Statistics

Some FDWs can fetch statistical estimates from the remote system or implement custom sampling. Behavior depends on extension/version. If the planner misestimates remote rows, inspect FDW options, remote EXPLAIN, and pushdown support.

### 18.3. Materialized Views

A materialized view stores the results of a query. After a REFRESH, the relation's stats may need updating so the planner sees the new distribution:

~~~sql
REFRESH MATERIALIZED VIEW app.monthly_sales;
ANALYZE app.monthly_sales;
~~~

REFRESH has its own locking/resource behavior; ANALYZE does not refresh data and does not make a materialized view contain newer rows.

### 18.4. Temporary Tables

Temporary tables often need manual ANALYZE after loading substantial rows so the planner has stats for subsequent joins/filters in the session. Autoanalyze behavior on temporary relations varies by session and version; do not assume temp tables are managed identically to permanent tables.

### 18.5. Regular Views

Regular views store no rows of their own, so analyzing a view like a physical table does not mean the same thing. The planner relies on base relation stats and relevant expression/extended stats. If a view query is slow, analyze the base tables and inspect view expansion, query plans, and expressions.

---

## 19. ANALYZE and Access Privileges

### 19.1. Who Can Run ANALYZE?

Required privileges depend on PostgreSQL version and grants. On many versions, the table owner or a superuser can run it; newer versions may support the `MAINTAIN` privilege for maintenance tasks. Check documentation for your exact version and never grant superuser just so a job can analyze a table.

### 19.2. Privileges to Read Statistics

`pg_stats` enforces security behavior to avoid leaking statistics from tables a role is not allowed to read. Internal catalogs are more restricted. Monitoring roles should receive least privilege per policy.

### 19.3. Security Definer Jobs

If an administrative job runs ANALYZE on behalf of an application, use a dedicated maintenance role with appropriate privileges. Do not make every application role the owner of the entire schema just to solve a missing analyze privilege.

### 19.4. ANALYZE Does Not Grant Query Privileges

Running ANALYZE does not alter GRANTs, ownership, or RLS. A query may get a better plan after analyze and still fail with permission denied or have rows filtered by RLS.

---

## 20. ANALYZE, Locks, and Operational Impact

### 20.1. Does It Block DML?

ANALYZE is designed not to block normal SELECT/INSERT/UPDATE/DELETE operations the way an exclusive lock does. Still, it requires an appropriate relation lock and can conflict with certain maintenance/DDL operations. If DDL is running or a relation is locked long-term, ANALYZE may have to wait.

### 20.2. Consumes I/O and CPU

Sampling still reads blocks and computes statistics. Running ANALYZE on a table with many columns, high targets, and complex extended stats can generate noticeable load.

### 20.3. Do Not Analyze Every Table Simultaneously

Running mass ANALYZE across many large tables at once can cause I/O spikes, competing with query latency and autovacuum. Stagger schedules, prioritize query-critical tables, and monitor impact.

### 20.4. SKIP_LOCKED

Some PostgreSQL versions support the `SKIP_LOCKED` option for ANALYZE to avoid waiting on a relation lock when the needed lock cannot be acquired immediately. If a relation is skipped, never assume its stats were refreshed. Check output/monitoring and reschedule once the lock clears.

Version-dependent syntax example:

~~~sql
ANALYZE (SKIP_LOCKED) app.orders;
~~~

Verify the option is supported on your running server before using it in automation.

### 20.5. ANALYZE Inside a Transaction

ANALYZE can be invoked within an appropriate SQL transaction context, though statistics updates and planner visibility follow specific semantics. Do not wrap batches of long-running analyze commands in one open transaction just to make them "atomic"; stats across multiple tables are not business data needing a single publication transaction.

### 20.6. When DDL Arrives While Analyze Is Running

Some DDL statements must wait on ANALYZE, or vice versa depending on locks. Coordinate migrations, partition attach/detach, reindexing, and analyze to avoid long maintenance queues.

---

## 21. Reasons Why ANALYZE Did Not Improve a Query

### 21.1. Predicate Not Described by Stats

Single-column stats cannot model every expression, JSON path, function call, or correlated predicate. Consider expression statistics, extended stats, or rewriting predicates so the planner can reason about them.

### 21.2. Correlation Between Columns

If a query filters both `region` and `status`, single-column stats may assume independence and misestimate. Create appropriate multivariate MCV/dependency stats, then run ANALYZE.

### 21.3. Generic Prepared Plan

A prepared statement may switch to a **generic plan** independent of specific parameter values while data distribution is heavily skewed by parameter. For example, customer 1 owns 40% of rows while customer 9999 owns only a few. One generic plan cannot be optimal for both.

Use `EXPLAIN EXECUTE` and check plan caching behavior/driver settings. Custom plans can leverage specific parameter values, though not every case warrants forcing custom plans because planning overhead also has a cost.

### 21.4. Good Stats, Unsuitable Cost Settings

The planner also relies on cost parameters such as `seq_page_cost`, `random_page_cost`, `cpu_tuple_cost`, and `effective_cache_size`. If storage/cache assumptions are off, plans can be poor even when cardinality estimates are fairly accurate.

Do not tweak cost settings to compensate for stale stats; separate cardinality errors from cost-model errors first.

### 21.5. Unsuitable Indexes

ANALYZE cannot create indexes. If a query predicate lacks an efficient access path, the planner may rightly pick a Seq Scan. Review index design, operator classes, collations, expressions, partial predicates, and selectivity.

### 21.6. Data Distribution Changes Immediately After Analyze

On write-heavy tables, stats can age rapidly. If ingestion jobs continually shift hot values, evaluate autoanalyze thresholds, scheduled manual runs, or data modeling/partitioning so stats stay representative.

### 21.7. Query Bottleneck Is Not in the Planner

A query may be slow due to lock waits, disk latency, network, client fetch, serialization, triggers, CPU contention, or memory spills. `EXPLAIN (ANALYZE, BUFFERS)` and wait-event monitoring help distinguish these.

### 21.8. Stable Plan, Variable Runtime

Warm vs. cold cache, concurrent load, I/O pressure, autovacuum, checkpoints, and parameter values can cause runtime variance even when the plan stays identical. Do not blame every latency regression on stats.

---

## 22. Workflow for Diagnosing Bad Estimates

~~~mermaid
flowchart TD
    A["Slow query or plan regression"] --> B["EXPLAIN (ANALYZE, BUFFERS)"]
    B --> C{"Estimated rows differ from actual?"}
    C -- "Negligibly" --> D["Check I/O, locks, memory, indexes, cost settings"]
    C -- "Yes" --> E["Find the first misestimated scan/predicate"]
    E --> F["Check pg_stats and last_analyze"]
    F --> G{"Stats stale or lacking detail?"}
    G -- "Yes" --> H["ANALYZE / raise target on needed column"]
    G -- "No" --> I{"Correlated columns or expressions?"}
    I -- "Yes" --> J["Extended statistics / expression statistics"]
    I -- "No" --> K["Check generic plan, casts, operators, skew"]
    H --> L["Re-run EXPLAIN with representative parameters"]
    J --> L
    K --> L
    L --> M["Compare plan, estimates, latency, and workload impact"]
~~~

### 22.1. Locate the Lowest Diverging Node

If a query has multiple joins, do not look only at total runtime. Find the lowest node from the bottom up where estimated rows diverge sharply from actuals. If a base scan returns 100x more rows than estimated, upper joins may simply be a downstream consequence.

### 22.2. Check Statistics Freshness

~~~sql
SELECT
    schemaname,
    relname,
    last_analyze,
    last_autoanalyze,
    n_mod_since_analyze,
    n_live_tup
FROM pg_stat_user_tables
WHERE schemaname='app'
  AND relname='orders';
~~~

Correlate with current query distribution and table growth. A recent analyze timestamp alone does not prove every column or extended stat covers the query.

### 22.3. Compare Estimates After ANALYZE

~~~sql
ANALYZE app.orders;

EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM app.orders
WHERE customer_id=1024;
~~~

If estimates improve while runtime stays unchanged, the bottleneck may be I/O, indexes, or locks. If estimates do not improve, check stats target, predicate support, skew, and parameterization.

### 22.4. Test Multiple Parameter Values

For skewed columns, test representative parameters: hot key, median key, rare key, missing key, and NULL where valid. A good plan for one customer does not prove it works well for all.

### 22.5. Record Before/After

When tuning statistics targets or extended stats, record:
- Query text/parameter class.
- EXPLAIN plan.
- Estimated vs. actual rows.
- Planning/execution time.
- Buffer hits/reads.
- Stats target/extended stats definition.
- System load during measurement.

Keep a change only when gains are repeatable and do not severely regress other workloads.

---

## 23. Managing Extended Statistics in Schema

### 23.1. Listing Objects

~~~sql
SELECT
    schemaname,
    tablename,
    statistics_name,
    attnames,
    kinds,
    inherited
FROM pg_stats_ext
WHERE schemaname='app'
ORDER BY tablename, statistics_name;
~~~

The `pg_stats_ext` view is available in PostgreSQL versions supporting extended statistics. Column names and expression-specific views can vary by version; check catalog/view definitions on the real server.

### 23.2. Creating Objects Based on Workload

For example, when queries frequently filter on `country`/`currency`:

~~~sql
CREATE STATISTICS app.users_country_currency_stats
    (mcv, dependencies)
ON country, currency
FROM app.users;

ANALYZE app.users;
~~~

Do not create stats objects merely because two columns look conceptually related. There must be actual query predicates or GROUP BY clauses needing joint estimation.

### 23.3. Dropping Unused Objects

~~~sql
DROP STATISTICS IF EXISTS app.users_country_currency_stats;
~~~

`DROP STATISTICS` does not delete business rows or indexes; it removes the extended stats metadata object. If managed via migrations, record the change in schema migration/version control.

### 23.4. Extended Statistics Target

Some PostgreSQL versions allow setting a dedicated statistics target on an extended statistics object via `ALTER STATISTICS ... SET STATISTICS`. This tunes the detail level of multivariate stats. Verify syntax/version and increase it only when plans show the current object under-represents combinations.

### 23.5. Do Not Use Dependency Objects Instead of Constraints

If a business invariant states that `zip_code` determines `city`, extended statistics only help the planner estimate; they do **not** prevent invalid data. Use `UNIQUE`, `FOREIGN KEY`, `CHECK`, or a mapping table/application logic to enforce consistency.

### 23.6. Do Not Use Extended Stats to Replace Normalization

If a table repeats dimension attributes or has governed relationships, proper schema design and constraints remain foundational. Extended stats are strictly metadata for the query optimizer.

---

## 24. Important Limitations of Planner Statistics

### 24.1. Not Every Predicate Is Modeled

Column stats and extended stats support specific predicate forms. Clauses involving custom functions, complex expressions, cross-type casts, collations, pattern matching, or specialized operator classes may not leverage stats as expected.

### 24.2. Correlation Does Not Mean the Planner Understands Every Column Pair

A dependencies stats object for equality restrictions does not automatically yield a full joint probability model for every query. Do not assume `CREATE STATISTICS` eliminates all estimation errors across joins or range predicates.

### 24.3. Join Selectivity

Extended statistics primarily aid single-relation restriction estimates; the planner does not use them as a universal model for estimating arbitrary multi-table joins. When join estimates fail, inspect per-table stats, unique keys, FKs, data skew, and join clauses.

### 24.4. Statistics Do Not Predict Future Data

A good ANALYZE reflects the sample at collection time. If continuous ingestion introduces a new tenant accounting for 70% of rows within minutes, prior stats cannot foresee the new distribution.

### 24.5. Stats Are Not a Business Histogram

The planner histogram is an internal structure for selectivity estimation. It is not designed for analytical dashboards, exact percentiles, or SLA-backed distribution reporting.

### 24.6. Statistics Can Vary Between Runs

Two ANALYZE runs can draw different samples. If a query plan shifts slightly after an analyze, evaluate stability and workload rather than automatically treating every plan shift as a bug.

### 24.7. Extremely High Statistics Targets Do Not Alter Query Semantics

Targets only change estimation granularity; they do not change SQL results, create constraints, or guarantee index selection. Do not use them as a "hint" to force a plan.

---

## 25. Decision Table: When to Run ANALYZE?

| Situation | Usually Appropriate Action | Why |
|---|---|---|
| Table created and millions of rows loaded | ANALYZE after load | Stats must represent the new data |
| A few rows added to a stable table | Usually leave to autoanalyze | Manual analyze is rarely needed |
| Backfill on a query-critical column | ANALYZE that column or table | Distribution may have shifted sharply |
| UPDATE alters status skew | ANALYZE status | MCV/selectivity may be stale |
| Created an extended statistics object | ANALYZE relation | Collects data for the new object |
| Created expression statistics | ANALYZE relation | Planner needs expression stats |
| Query plan has clear misestimates | Inspect `pg_stats`, then ANALYZE/tune if needed | Find root cause before tuning |
| Many rows DELETEd | VACUUM and/or ANALYZE as needed | Two distinct objectives |
| New partition just loaded | ANALYZE partition and parent if needed | Local and global stats |
| Large materialized view REFRESHed | ANALYZE materialized view | Relation distribution changed |
| Temp table loaded with many rows | ANALYZE within session | Autovacuum does not manage temp tables like permanent ones |
| Large remote foreign table | Check FDW and ANALYZE if supported | Remote stats may be stale |
| Index created without changing data distribution | Not strictly required just for the index | Index build does not change data distribution |
| Database restored/cloned | Follow restore procedure, typically verify and ANALYZE | Ensure planner stats match restored data |

---

## 26. Hands-On: Stale Stats and Autoanalyze Thresholds

### 26.1. Inspect the Lab Table

~~~sql
SELECT
    relname,
    n_live_tup,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname='analyze_lab'
  AND relname='orders';
~~~

If the table was just created, timestamp columns may be NULL. After manual ANALYZE, `last_analyze` updates; `last_autoanalyze` tracks automatic runs separately.

### 26.2. Change the Distribution

~~~sql
UPDATE analyze_lab.orders
SET order_status='paid'
WHERE order_status='cancelled';
~~~

This DML alters status distribution, yet stats are not necessarily refreshed immediately. In the lab, inspect EXPLAIN before and after running ANALYZE.

### 26.3. Read Stats Before and After

~~~sql
SELECT
    attname,
    most_common_vals,
    most_common_freqs,
    n_distinct
FROM pg_stats
WHERE schemaname='analyze_lab'
  AND tablename='orders'
  AND attname='order_status';
~~~

Then:

~~~sql
ANALYZE analyze_lab.orders (order_status);

SELECT
    attname,
    most_common_vals,
    most_common_freqs,
    n_distinct
FROM pg_stats
WHERE schemaname='analyze_lab'
  AND tablename='orders'
  AND attname='order_status';
~~~

### 26.4. Compare Estimates

~~~sql
EXPLAIN
SELECT *
FROM analyze_lab.orders
WHERE order_status='paid';
~~~

Plain `EXPLAIN` does not execute the SELECT; it returns only the plan and estimates. Use `EXPLAIN ANALYZE` if you want actual rows, noting it executes the query and reads data.

### 26.5. Inspect Counters

~~~sql
SELECT
    n_live_tup,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze,
    analyze_count,
    autoanalyze_count
FROM pg_stat_user_tables
WHERE schemaname='analyze_lab'
  AND relname='orders';
~~~

Counters can be reset and do not sync instantaneously across every transaction. Do not use a single counter in isolation to prove definitively whether autoanalyze ran.

---

## 27. Common Mistakes

| Mistake | Consequence | Correct Understanding |
|---|---|---|
| "ANALYZE cleans up dead tuples" | Bloat goes unaddressed | VACUUM handles MVCC cleanup |
| "VACUUM always updates all stats fully" | Planner keeps using stale stats | Run ANALYZE when needed |
| "ANALYZE counts every row exactly" | Confusing estimates with exact counts | Stats rely on sampling |
| "Run ANALYZE on every INSERT" | Unnecessary I/O/CPU overhead | Rely on workload patterns and autoanalyze |
| "Stats target is the number of sampled rows" | Wrong target sizing | Target sets detail/slots, affecting sample size |
| "Higher target always means faster queries" | Expensive analyze with uncertain gain | Tune based on evidence |
| "`n_distinct` is always positive" | Misreading negative fractions | Negative values are fractions of row count |
| "`correlation` is two-column correlation" | Misinterpreting `pg_stats` | Heap order vs. column value order |
| "Histograms contain every value" | Treating stats as raw data | Histograms hold bucket boundaries |
| "MCV lists all values" | Overlooking tail values | Stores only common values |
| "ANALYZE creates indexes automatically" | Expecting non-existent access paths | Stats only help the planner choose paths |
| "If an index exists, the planner must use it" | Forcing bad plans | Seq Scan can be cheaper |
| "Extended stats model all joins" | Join estimates stay wrong | Primarily aids single-relation restrictions |
| "Dependencies act like constraints" | Bad data enters the table | Enforce via constraints |
| "ANALYZE parent always auto-runs after partition load" | Parent stats stay stale | Analyze parent on schedule/after loads |
| "Autoanalyze runs the instant threshold is crossed" | Ignoring worker scheduling | Threshold is not a hard deadline |
| "NULL `last_autoanalyze` is an error" | False alarms | Table may not have crossed threshold |
| "`pg_stat_user_tables.n_live_tup` is an exact COUNT" | Using estimates as business totals | It is a statistical estimate |
| "ANALYZE only touches planner, uses no resources" | Causes I/O/CPU contention | Sampling reads blocks |
| "ANALYZE blocks all DML" | Avoiding needed maintenance | Usually permits DML, though takes locks/resources |
| "Successful `SKIP_LOCKED` means all tables analyzed" | Locked relations skipped silently | Check output/progress and retry |
| "`pg_statistic` can be manually updated" | Corrupts catalog/planner state | Use ANALYZE and official DDL |
| "ANALYZE materialized view refreshes its data" | Data stays stale | REFRESH first, then ANALYZE |
| "ANALYZE on a regular view works like a table" | No independent storage relation | Analyze base tables/expressions |
| "ANALYZE foreign table is always local/cheap" | Remote sampling can be expensive | Check FDW capabilities |
| "Bad estimates are always caused by stats" | Overlooking indexes/costs/locks/I/O | Find the first diverging node |
| "`EXPLAIN ANALYZE` only simulates" | DML modifies real data | It executes the query for real |
| "Generic plans are always optimal for all parameters" | Skew causes poor plans | Test hot and rare values |
| "Freshly analyzed stats cannot go stale" | New writes shift distributions | Watch write rate and autoanalyze |
| "Changing cost settings fixes stale stats" | Masks root cause | Separate cardinality from cost model |
| "ANALYZE alters authorization" | Queries still hit permission denied/RLS | SQL privileges are independent |

---

## 28. Statistics Operations Checklist

### 28.1. Before ANALYZE

- [ ] Identify query-critical relations and columns.
- [ ] Check last analyze timestamps and modifications since then.
- [ ] Determine how the data distribution changed.
- [ ] Verify autovacuum/autoanalyze is enabled and not backlogged.
- [ ] Inspect query plans and estimated vs. actual rows.
- [ ] Check active workload, I/O headroom, and locks.
- [ ] If partitioned, determine whether parent, partitions, or both need analyzing.

### 28.2. When Tuning Statistics

- [ ] Raise targets only for columns with evidence.
- [ ] Use extended stats when multi-column predicates are genuinely correlated.
- [ ] Distinguish `dependencies`, `ndistinct`, and `mcv`.
- [ ] Remember expression stats do not replace expression indexes.
- [ ] Do not use extended stats in place of constraints.
- [ ] Check whether queries use generic plans or unsupported predicates.
- [ ] Compare plans across multiple representative parameter values.

### 28.3. After ANALYZE

- [ ] Confirm `last_analyze`/`last_autoanalyze` or command progress/output.
- [ ] Inspect `pg_stats`/`pg_stats_ext`.
- [ ] Re-run EXPLAIN on representative queries.
- [ ] Compare estimated rows vs. actual rows.
- [ ] Measure execution latency, buffers, and workload impact.
- [ ] Do not keep elevated targets if there is no measurable gain.
- [ ] Monitor stats freshness as writes continue.

---

## 29. Runbook for Query Regressions Caused by Planner Estimates

1. Capture query text and representative parameters without exposing secrets/PII.
2. Run `EXPLAIN (ANALYZE, BUFFERS)` in a safe environment or with acceptable production impact.
3. Locate the lowest node where estimated rows diverge sharply from actuals.
4. Identify the predicate/column/expression causing the error.
5. Inspect `pg_stats` and `pg_stats_ext`; check `last_analyze` and `n_mod_since_analyze`.
6. Check skew, MCV coverage, histogram, NULL fraction, and distinct estimates.
7. For multi-column predicates, evaluate whether extended statistics fit and are supported by the planner for that clause type.
8. If using prepared statements, compare generic vs. custom plans across multiple parameter values.
9. Run manual ANALYZE if stats are stale; raise targets/add extended stats only with evidence.
10. Re-measure plan and latency; do not rely solely on a single warm-cache run.
11. If estimates look accurate yet the query remains slow, shift investigation to indexes, cost settings, locks, I/O, memory, parallelism, and concurrency.
12. Document DDL/target changes and rollback paths.
13. Monitor workloads post-deploy to ensure no other queries regressed.
14. If distribution shifts continuously, adjust autoanalyze thresholds or data model/partitioning to fit the workload.

---

## 30. PostgreSQL Reference Documentation

When implementing changes, prefer official documentation matching your server's exact major version:

- [PostgreSQL — ANALYZE](https://www.postgresql.org/docs/current/sql-analyze.html): syntax and purpose of ANALYZE.
- [PostgreSQL — Planner Statistics](https://www.postgresql.org/docs/current/planner-stats.html): basic stats, MCV, histograms, extended statistics, and statistics target.
- [PostgreSQL — pg_stats](https://www.postgresql.org/docs/current/view-pg-stats.html): column statistics view.
- [PostgreSQL — pg_statistic](https://www.postgresql.org/docs/current/catalog-pg-statistic.html): internal catalog.
- [PostgreSQL — CREATE STATISTICS](https://www.postgresql.org/docs/current/sql-createstatistics.html): multivariate/expression statistics.
- [PostgreSQL — ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html): per-column statistics target and table reloptions.
- [PostgreSQL — Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): autovacuum, autoanalyze, and vacuum.
- [PostgreSQL — Autovacuum Configuration](https://www.postgresql.org/docs/current/runtime-config-autovacuum.html): thresholds, scale factors, and workers.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): estimated costs/rows and ANALYZE output.
- [PostgreSQL — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_user_tables`, progress views, and activity.
- [PostgreSQL — Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html): partitioned tables and planning.
- [PostgreSQL — Foreign Data](https://www.postgresql.org/docs/current/ddl-foreign-data.html): foreign tables and FDW behavior.

Paths using `/current/` point to the latest version; features such as expression statistics, progress view fields, privileges, and autoanalyze counters depend on major version. Verify against docs for your actual server.

---

## 31. Summary

**ANALYZE supplies statistical data so PostgreSQL can estimate row counts and select execution plans.** A query can slow down not because SQL changed, but because the data distribution shifted while the planner still relied on outdated or overly simple stats.

Key principles:

1. **ANALYZE and VACUUM are distinct:** ANALYZE collects planner stats; VACUUM handles dead tuples, visibility, and freezing. `VACUUM ANALYZE` does both.
2. **Statistics rely on sampling:** MCV, histograms, distinct counts, and null fractions are estimates, not exact business counts.
3. **The planner uses stats for cardinality/selectivity estimation:** these estimates drive scans, join order, join methods, sorts, aggregates, and parallel plans.
4. **MCVs capture hot values; histograms capture range distributions:** both have resolution and sampling limits.
5. **`n_distinct` can be negative:** its magnitude is a fraction of row count, e.g., `-1` means nearly unique.
6. **`correlation` in `pg_stats` is heap order vs. column value order:** not correlation between two business columns.
7. **Statistics targets control resolution:** raise targets only when evidence shows stats under-describe data; avoid setting huge targets across all columns.
8. **Extended statistics describe multi-column/expression relationships:** `dependencies`, `ndistinct`, and `mcv` serve different estimation needs, mainly within one relation.
9. **Expression stats differ from expression indexes:** one helps estimation, the other creates an access path.
10. **Autoanalyze follows thresholds and scheduling:** crossing a threshold does not mean immediate execution; partitioned parents and temp tables have special caveats.
11. **After bulk loads, backfills, or distribution shifts, manual ANALYZE may be needed:** especially before opening query-critical workloads.
12. **EXPLAIN compares estimates with actuals:** find the lowest badly diverging node, check `pg_stats` and predicates before altering cost settings.
13. **ANALYZE consumes resources:** sampling reads blocks and updates catalogs; schedule around workload demand.
14. **Do not force planner hints to mask issues:** a Seq Scan might be optimal; inspect indexes, cost model, I/O, and concurrency once estimates look reasonable.
15. **Statistics do not enforce data integrity:** use constraints for business rules, never dependency stats instead of FK/UNIQUE/CHECK.
16. **Never edit `pg_statistic` directly:** use `ANALYZE`, `ALTER TABLE`, and `CREATE/ALTER STATISTICS`.
17. **Validate optimizations with evidence:** save before/after plans, test multiple parameter values, measure latency/buffers, and watch for regressions elsewhere.

Practical workflow: **detect query regression → EXPLAIN ANALYZE → locate first bad cardinality estimate → inspect `pg_stats` and freshness → run ANALYZE or tune target/extended stats on the right column → re-measure plan and workload → monitor autoanalyze to keep stats accurate as data keeps changing**.

---

## 32. Practice Exercises

Exercises use the `analyze_lab` schema unless stated otherwise. Data-creation/modification commands must run only in a test database. Exercises involving EXPLAIN should clearly distinguish plain `EXPLAIN` from `EXPLAIN ANALYZE`, which actually executes the query.

### Exercise 1 — What Is ANALYZE?

Explain what ANALYZE does for the planner and two things it does not do.

### Exercise 2 — ANALYZE and VACUUM

A table just had 5 million rows deleted. When is VACUUM needed, when is ANALYZE needed, and when might `VACUUM ANALYZE` be appropriate?

### Exercise 3 — Planner Statistics

Name at least five pieces of information the planner must estimate before picking an execution plan.

### Exercise 4 — null_frac

A `coupon_code` column has `null_frac=0.8`. Estimate the NULL percentage and explain how an `IS NULL` query can use this information.

### Exercise 5 — avg_width

A JSONB `payload` column's `avg_width` jumps from 100 bytes to 2,000 bytes after an import. What might change in planner cost estimates?

### Exercise 6 — Negative n_distinct

Explain the meaning of `n_distinct=-0.25`. If the table has roughly 2 million rows, what is the estimated distinct count?

### Exercise 7 — MCV

Column `status` has MCV `paid` with frequency 0.7. Roughly what is the estimated selectivity of `WHERE status='paid'` from this stat? Why can assuming uniform distinct values be wrong?

### Exercise 8 — Histogram

Does `histogram_bounds` list every value in the column? Give two query forms where the planner uses the histogram to estimate selectivity.

### Exercise 9 — Correlation

Does `pg_stats.correlation=-0.95` mean `customer_id` and `region` are strongly negatively correlated? Explain its exact meaning.

### Exercise 10 — Statistics Target

Write SQL to raise the statistics target for `customer_id` to 500, run ANALYZE on that column only, and revert the column to default.

### Exercise 11 — High Target

Why can setting target 10,000 on every column be a bad decision? Give at least three trade-offs.

### Exercise 12 — Sampling

Why can two runs of ANALYZE yield slightly different stats? When can sampling miss hot or rare values?

### Exercise 13 — ANALYZE After COPY

You just COPY'd 50 million rows into an empty table. Why should you consider running ANALYZE before opening heavy read traffic?

### Exercise 14 — Autoanalyze Threshold

With threshold=50 and scale_factor=0.1, roughly how many modifications does a 1-million-row table need under the general threshold formula? Why can this not be treated as an exact deadline?

### Exercise 15 — Autoanalyze Has Not Run

`n_mod_since_analyze` exceeds the estimated threshold, yet `last_autoanalyze` has not updated. List at least four possible reasons.

### Exercise 16 — pg_stat_user_tables

Write a query listing the top 10 tables with the largest `n_mod_since_analyze`, alongside `last_analyze` and `last_autoanalyze`.

### Exercise 17 — Extended Statistics

A query filters `country='VN'` and `currency='VND'`. The two columns are correlated. Write `CREATE STATISTICS` collecting `dependencies` and `mcv`, then run ANALYZE.

### Exercise 18 — Dependencies Are Not Constraints

If an extended dependency shows `zip_code` nearly determines `city`, will the database reject inconsistent `zip_code`/`city` data? What must be used to enforce it?

### Exercise 19 — Multivariate ndistinct

Why is the number of groups in `GROUP BY country, currency` not necessarily `distinct(country) × distinct(currency)`? Which extended stats kind helps estimate it?

### Exercise 20 — Extended Stats and Joins

Do extended statistics on `users` automatically describe the join relationship between `users` and `orders`? State the main limitation.

### Exercise 21 — Expression Statistics

Write a sample `CREATE STATISTICS` for `lower(email)`. Does it replace an expression index? Why or why not?

### Exercise 22 — pg_stats

Write a query inspecting `null_frac`, `n_distinct`, MCV, histogram, and correlation for `customer_id` in schema `app`, table `orders`.

### Exercise 23 — pg_statistic

Should you directly UPDATE `pg_statistic` to fix `n_distinct`? Why or why not?

### Exercise 24 — Partitioned Table

A partitioned parent table receives 20 million new rows in a new partition. Why might both the partition and the parent need ANALYZE? Is parent autoanalyze guaranteed to trigger on its own?

### Exercise 25 — Temporary Table

A session loads 1 million rows into a TEMP table and then joins it with a large table. Why should you consider running ANALYZE on the temp table?

### Exercise 26 — Foreign Table

Why can analyzing a foreign table consume network/remote I/O? What component determines this behavior?

### Exercise 27 — Materialized View

After `REFRESH MATERIALIZED VIEW`, the planner can still misestimate. What should you do next?

### Exercise 28 — EXPLAIN Rows

A plan node shows `rows=1,000`, `actual rows=100,000`, `loops=1`. What is the estimation error ratio? What can be affected above this node?

### Exercise 29 — Loops

An inner node shows `actual rows=10` and `loops=500`. Roughly how many total rows are processed? Why must `loops` never be ignored?

### Exercise 30 — EXPLAIN vs. EXPLAIN ANALYZE

What is the most important difference between the two commands? Why should you not run `EXPLAIN ANALYZE` on a production UPDATE just to inspect the plan?

### Exercise 31 — Generic Plan

One `customer_id` owns 40% of rows while most customers own only a few rows. Why can a generic prepared plan be suboptimal across parameter values? How do you diagnose it?

### Exercise 32 — Fresh Stats, Still Slow

List at least five causes other than stale stats that can make a query slow.

### Exercise 33 — Cost Settings

If the planner chooses Seq Scan after ANALYZE, should you immediately lower `random_page_cost`? Outline a sensible investigation sequence.

### Exercise 34 — SKIP_LOCKED

`ANALYZE (SKIP_LOCKED)` runs, but one relation is skipped due to a lock. Should that relation be marked as having refreshed stats? What should you do next?

### Exercise 35 — Distinguishing Stats Freshness from Vacuum

A table has a very recent `last_analyze`, yet `n_dead_tup` is high. Can you conclude the table is clean? Why or why not?

### Exercise 36 — ANALYZE Permissions

An application role lacks privileges to run ANALYZE. Should you grant it superuser? Propose a better privilege design.

### Exercise 37 — ANALYZE and Concurrency

ANALYZE does not block normal DML, yet how can it still affect workloads? Mention the relevant resources and locks.

### Exercise 38 — Write-Heavy Table

A table receives 100,000 updates/second; autoanalyze runs constantly, yet stats go stale quickly. Give three design or tuning approaches.

### Exercise 39 — Evidence-Based Target Tuning

Write a workflow from spotting a bad estimate to deciding to raise a target and verifying the outcome.

### Exercise 40 — Case Study

A query filtering `region='north' AND status='paid'` estimates 500 rows, yet returns 300,000 rows in reality. Each individual column has reasonable MCVs. Explain how the independence assumption causes the error and propose extended stats.

### Exercise 41 — Parent/Partition Stats

A new partition has a completely different status distribution from older partitions. Queries through the parent misestimate. Outline the inspection and analyze steps.

### Exercise 42 — Import Causing Join Plan Regression

After importing 100 million rows, a reporting query switches from Hash Join to Nested Loop and runs much slower. Write an ordered diagnostic workflow.

### Exercise 43 — Stats vs. Data Integrity

A developer wants to use dependencies statistics to guarantee each `customer_id` has only one `region`. Why is this design wrong? Propose a proper constraint/model.

### Exercise 44 — Command Selection

Match each scenario to the appropriate action: (a) only stale stats after bulk INSERT, (b) many dead tuples after UPDATE/DELETE, (c) right after REFRESH materialized view, (d) created a multivariate stats object, (e) query uses a newly loaded TEMP table.

### Exercise 45 — Production Runbook

A critical query regresses after a backfill, actual rows are 200x higher than estimates, and API p99 spikes. Write a safe runbook to identify the cause, update stats, and verify no other workload regresses.

---

## 33. Solutions — Exercises 1 to 25

### Exercise 1 — ANALYZE

ANALYZE samples data and updates planner statistics such as null fraction, distinct values, MCV, and histograms. It does **not** remove dead tuples and does **not** create indexes. Nor does it modify business values in the table.

### Exercise 2 — VACUUM and ANALYZE

Deleting 5 million rows creates dead tuple versions that must be reclaimed once snapshots no longer need them. VACUUM handles cleanup/reuse. ANALYZE updates statistics if distribution/row counts changed. `VACUUM ANALYZE` fits when both are needed. ANALYZE alone does not fix bloat.

### Exercise 3 — Planner Estimates

Examples: total rows, distinct values, NULL fraction, MCV/frequencies, histogram range distribution, physical correlation, row width, group counts, and join cardinality/selectivity.

### Exercise 4 — null_frac

0.8 means roughly 80% of rows are NULL according to stats. The planner can use this fraction to estimate `WHERE coupon_code IS NULL`/`IS NOT NULL`. This is a sampling estimate, not an exact count.

### Exercise 5 — avg_width

Higher estimated row width changes estimated costs and memory footprints for sorts, hashes, materialization, and scans. If stale stats still assume 100 bytes while actual payloads are 2,000 bytes, the planner may underestimate the cost of processing many rows.

### Exercise 6 — Negative n_distinct

`-0.25` indicates distinct values equal roughly 25% of rows. On 2 million rows, roughly 500,000 distinct values. This is an estimate, not an exact `COUNT DISTINCT`.

### Exercise 7 — MCV

If `paid` has frequency 0.7, selectivity of `status='paid'` is roughly 70%. Under skewed distributions, assuming uniformity across all distinct values misses hot values like `paid`.

### Exercise 8 — Histogram

A histogram does not hold every value; it holds bucket boundaries for the remaining data, typically after separating out MCV/NULLs. The planner uses it to estimate range predicates such as `amount BETWEEN 100 AND 200` or timestamps within an interval.

### Exercise 9 — Correlation

No. `-0.95` describes a strong inverse relationship between **physical heap order** and column value order. It does not describe any correlation between `customer_id` and `region`.

### Exercise 10 — Per-Column Target

~~~sql
ALTER TABLE app.orders
ALTER COLUMN customer_id
SET STATISTICS 500;

ANALYZE app.orders (customer_id);

ALTER TABLE app.orders
ALTER COLUMN customer_id
SET STATISTICS -1;
~~~

The final statement resets to the default target. If you want to keep target 500 after successful tuning, omit the reset step and record the change in migrations/configuration.

### Exercise 11 — Extremely High Target

- ANALYZE consumes more sampling/I/O/CPU.
- Statistics catalogs grow larger.
- Autoanalyze can consume significantly more resources.
- No benefit if queries do not use those stats.
- Sampling still has error; a high target does not guarantee a good plan.
- Unrelated columns suffer needless overhead.

### Exercise 12 — Sampling

Sampling is randomized; two samples can produce slightly different MCV/histogram estimates. Very rare values may miss the sample; a hot value concentrated in a small portion can also be underestimated if the sample is unrepresentative.

### Exercise 13 — ANALYZE After COPY

A table that was empty prior to import may have missing stats or stats unrepresentative of the new distribution. The planner can misestimate rows, join order, and scan types. Running ANALYZE post-load refreshes stats before heavy query/reporting traffic arrives.

### Exercise 14 — Threshold

`50 + 0.1 × 1,000,000 = 100,050 modifications` under the general formula. It is not a strict deadline because row counts are estimates, and worker scheduling, counters, table options, and version behavior influence when it actually runs.

### Exercise 15 — Autoanalyze Has Not Run

Possible reasons:
1. Workers are busy or constrained by max worker count.
2. Autovacuum is disabled or table options differ from defaults.
3. Stats counters were recently reset or not yet flushed.
4. The relation is held by locks/maintenance.
5. The table is a partitioned parent or temp table with special semantics.
6. Autovacuum naptime/scheduling has not reached it yet.
7. Statistics tracking does not match your assumption.

### Exercise 16 — Top 10 Modified Tables

~~~sql
SELECT
    schemaname,
    relname,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_mod_since_analyze DESC NULLS LAST
LIMIT 10;
~~~

Counters are estimates and depend on version and stats resets.

### Exercise 17 — Extended Statistics

~~~sql
CREATE STATISTICS app.users_country_currency_stats
    (dependencies, mcv)
ON country, currency
FROM app.users;

ANALYZE app.users;
~~~

MCV describes common combinations; dependencies describe certain functional relationships. If queries also run `GROUP BY country, currency` and misestimate group counts, you can add `ndistinct`.

### Exercise 18 — Dependencies Do Not Enforce Data

No. Extended stats only help planner estimation. Use `UNIQUE`/`FK`/`CHECK` or a mapping table and proper transaction logic to guarantee `zip_code`/`city` consistency. Choose constraints matching business cardinality.

### Exercise 19 — Multivariate ndistinct

Columns may be correlated so not every country uses every currency. Multivariate `ndistinct` helps estimate distinct combinations and group counts instead of multiplying two cardinalities independently.

### Exercise 20 — Extended Stats and Joins

No. Extended stats are built on columns/expressions of a single relation and primarily aid single-relation restriction estimates. Join selectivity also depends on join keys, uniqueness, constraints, and per-table stats; there are no general cross-table extended stats.

### Exercise 21 — Expression Statistics

~~~sql
CREATE STATISTICS app.customer_lower_email_stats
ON (lower(email))
FROM app.customers;

ANALYZE app.customers;
~~~

It does not replace an expression index. Stats help the planner estimate; an index provides the fast lookup path on `lower(email)`.

### Exercise 22 — pg_stats

~~~sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds,
    correlation
FROM pg_stats
WHERE schemaname='app'
  AND tablename='orders'
  AND attname='customer_id';
~~~

If no rows return, check privileges, relation name, and whether ANALYZE ran / statistics target is non-zero.

### Exercise 23 — Do Not Edit pg_statistic Directly

No. It is an internal catalog with a version-dependent representation. Manual updates can create inconsistent stats. Use `ALTER TABLE ... SET STATISTICS`, `CREATE STATISTICS`, and `ANALYZE`.

### Exercise 24 — Partitioned Table

Analyze the partition for local stats and the parent to update global/inherited stats for queries targeting the parent. Parent autoanalyze is not guaranteed to run just because partitions receive heavy inserts; schedule/run manual ANALYZE on the parent.

### Exercise 25 — TEMP Table

The planner needs cardinality, distribution, and distinct counts for the temp table to pick sensible join orders and methods. Autovacuum does not manage temp tables like permanent relations; the session should run ANALYZE after loading substantial rows ahead of critical joins.

---

## 34. Solutions — Exercises 26 to 45

### Exercise 26 — Foreign Table

ANALYZE may require the FDW to sample or read rows from the remote server. Cost depends on FDW implementation, remote query pushdown, network latency, source size, and credentials/permissions. Never assume it is a cheap local catalog read.

### Exercise 27 — Materialized View

After REFRESH, run ANALYZE on the materialized view to gather stats for the new distribution if the planner needs them:

~~~sql
REFRESH MATERIALIZED VIEW app.monthly_sales;
ANALYZE app.monthly_sales;
~~~

ANALYZE does not refresh data; the order is refresh first, then analyze.

### Exercise 28 — 100x Misestimate

Actual 100,000 / estimated 1,000 = **100x**. Upper nodes may choose the wrong join method/order, under-size memory, or execute far more nested loop iterations than intended.

### Exercise 29 — Loops

10 rows per loop × 500 loops ≈ **5,000 total rows** through the node. EXPLAIN typically shows average actual rows per loop; ignoring loops severely undercounts actual work.

### Exercise 30 — EXPLAIN vs. EXPLAIN ANALYZE

Plain EXPLAIN only displays the estimated plan without executing the query. EXPLAIN ANALYZE actually executes the query and measures actual rows/timing. For a production UPDATE, it modifies real data and fires triggers; never use it as a safe preview command.

### Exercise 31 — Generic Plan

A generic plan is not specialized to concrete parameter values. If customer 1 owns 40% of rows while others own only a few, one shared plan cannot be optimal for both. Diagnose via `EXPLAIN EXECUTE` with representative parameters, check plan caching/driver settings, and compare custom vs. generic plans as appropriate.

### Exercise 32 — Slow Query Despite Fresh Stats

Other causes:
- Missing/unsuitable index or predicate mismatch.
- Lock waits/deadlocks.
- Disk/network latency.
- CPU contention.
- Sort/hash disk spills due to memory limits.
- Wide rows/TOAST overhead.
- Expensive triggers/functions.
- Cost parameters out of sync with storage/cache.
- Generic prepared plan.
- Concurrent load and cold caches.

### Exercise 33 — Seq Scan Does Not Mean Stats Are Wrong

Do not immediately lower `random_page_cost`. Sequence:
1. Run `EXPLAIN (ANALYZE, BUFFERS)` safely.
2. Compare estimated vs. actual rows.
3. Verify stats freshness/distribution.
4. Check whether the index is selective and how many columns/rows the query needs.
5. Inspect cache/I/O and cost model.
6. Tune cost parameters only after representative benchmarking, never to force one individual query.

### Exercise 34 — SKIP_LOCKED

No. A skipped relation was not analyzed by that run. Check output/progress, wait for the DDL/maintenance lock to clear, and run ANALYZE again. Never mark stats freshness complete if the relation was skipped.

### Exercise 35 — Fresh Stats Do Not Mean a Clean Table

No. `last_analyze` only means statistics were collected recently; high `n_dead_tup` can still remain. VACUUM/autovacuum handles dead tuples. The two tasks have separate goals.

### Exercise 36 — ANALYZE Privileges

Do not grant superuser to applications. Use a DBA/maintenance role with appropriate privileges for your PostgreSQL version, or assign the maintenance job to the table owner or `MAINTAIN` privilege where supported. Keep runtime application roles least-privileged.

### Exercise 37 — ANALYZE and Concurrency

ANALYZE reads blocks and computes stats, consuming I/O/CPU/memory; updates system catalogs; acquires a relation lock that can conflict with certain DDL/maintenance; and concurrent runs can create I/O bursts. It normally permits standard DML, yet it is not free.

### Exercise 38 — Write-Heavy Table

Approaches:
1. Tune table-level analyze threshold/scale factor to balance write rate and cost.
2. Focus on critical columns and sensible targets, avoiding unnecessary stats.
3. Partition data by workload/time to bound stats scope and analyze work.
4. Schedule controlled manual ANALYZE runs for query-critical distributions.
5. Adjust query/data model if distributions shift faster than stats can track.
6. Monitor autoanalyze backlog and worker capacity.

Do not set tiny scale factors on every table without accounting for I/O.

### Exercise 39 — Target Tuning Workflow

1. Capture `EXPLAIN ANALYZE` and find the misestimating node.
2. Identify the column/predicate.
3. Inspect `pg_stats` MCV/histogram/`n_distinct`/`null_frac`.
4. Identify unrepresented skew or tail values.
5. Raise the target only on the needed column.
6. ANALYZE the column/table.
7. Compare plans/estimates across multiple parameter values.
8. Measure latency, buffers, and analyze overhead.
9. Keep the change if improvements are consistent; otherwise revert to default and investigate other causes.

### Exercise 40 — Correlated Region and Status

The planner multiplies the selectivities of `region='north'` and `status='paid'` as if independent. If most orders in `north` are also `paid`, actual rows far exceed the estimate. Create multivariate MCV/dependencies on the same table:

~~~sql
CREATE STATISTICS app.orders_region_status_stats
    (mcv, dependencies)
ON region, status
FROM app.orders;

ANALYZE app.orders;
~~~

Then re-run EXPLAIN. Dependencies do not cover every predicate; MCV helps with common combinations.

### Exercise 41 — Parent/Partition Stats

1. Check whether the query targets the parent or a partition directly.
2. Inspect `pg_stat_user_tables` for each partition and the parent.
3. Check `pg_stats` with the appropriate `inherited` flag.
4. Run ANALYZE on the new partition.
5. Run ANALYZE on the parent to refresh global/inherited stats if queries target the parent.
6. Re-run EXPLAIN with partition pruning.
7. Monitor autoanalyze; do not assume the parent updates automatically.

### Exercise 42 — Import Causing Join Plan Regression

1. Capture query/parameters and before/after `EXPLAIN (ANALYZE, BUFFERS)` if available.
2. Find the lowest scan node with bad estimates.
3. Check `last_analyze`/`n_mod_since_analyze` and row counts.
4. Run ANALYZE on modified tables/columns.
5. Inspect MCV/histogram/`n_distinct` and new skew.
6. Check correlated predicates and add extended stats if warranted.
7. Check generic prepared plans and parameter sensitivity.
8. Re-measure plan, actual rows, buffers, and p95/p99.
9. If estimates are now accurate yet the plan stays bad, inspect indexes, cost settings, locks, and I/O.
10. Monitor other workloads so fixing one query does not regress others.

### Exercise 43 — Dependencies Do Not Enforce Uniqueness

Extended stats do not stop two rows from having the same `customer_id` with different `region` values. Use a `UNIQUE` constraint, a mapping table with primary/foreign keys, or a normalized model. Choose constraints matching business cardinality; if regions change over time, use effective dates/versioning instead of a plain unique constraint.

### Exercise 44 — Command Matching

- (a) Only stale stats after bulk INSERT → **ANALYZE**.
- (b) Many dead tuples after UPDATE/DELETE → **VACUUM**, plus ANALYZE if stats need refreshing; **`VACUUM ANALYZE`** can be used.
- (c) Right after REFRESH materialized view → **ANALYZE materialized view** after REFRESH.
- (d) Created a multivariate stats object → **ANALYZE relation** to populate the object.
- (e) TEMP table just loaded with many rows → **ANALYZE temp table** inside the session before critical joins.

### Exercise 45 — Production Runbook

1. Record query text/parameters, backfill timing, deployments, and metrics; redact secrets.
2. Run `EXPLAIN (ANALYZE, BUFFERS)` safely or on a representative query.
3. Locate the lowest node where actual rows are 200x estimates.
4. Identify the predicate/column and check `pg_stats`, `last_analyze`, `n_mod_since_analyze`.
5. Run ANALYZE on changed columns/tables if stats are stale.
6. For correlated columns, create appropriate extended stats; for skew, consider a column target increase.
7. For generic plans, inspect prepared statement/driver behavior across multiple parameter classes.
8. Compare plans and runtimes afterward across multiple parameters.
9. Verify other queries on the same table do not regress; watch API p99, CPU/I/O, buffers, and locks.
10. If unimproved, investigate index design, cost settings, I/O, memory spills, locks, and application fetching.
11. Document target/extended stats migrations, privileges, rollback paths, and owners.
12. Monitor autoanalyze so stats do not immediately go stale again after the backfill.

---

## 35. Decision Flowchart for Choosing Statistics

~~~mermaid
flowchart TD
    A["Planner misestimates"] --> B{"Single column?"}
    B -- "Yes" --> C["Check null_frac, MCV, histogram, n_distinct"]
    C --> D{"Skew/rare values under-described?"}
    D -- "Yes" --> E["Raise column target + ANALYZE"]
    D -- "No" --> F["Check expressions, generic plan, operators"]
    B -- "Multiple columns on same table?" --> G["Extended statistics: dependencies / MCV / ndistinct"]
    B -- "Multi-table join?" --> H["Per-table stats, keys, uniqueness, FKs, join predicates"]
    E --> I["Re-run EXPLAIN, measure workload"]
    F --> I
    G --> I
    H --> I
~~~