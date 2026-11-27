# Sudden Slow Queries Due to Statistics, Data Skew, or Plan Changes

A MySQL query that used to run fast can suddenly slow down due to data growth, shifting value distributions, stale index statistics, outdated histograms, or the optimizer picking a different execution plan. Alternatively, the query itself may not have changed while system load, lock contention, I/O, or replication drives up response times. Therefore, before adding indexes or forcing the optimizer down a specific access path, determine which query is slow, whether the plan changed, and where actual rows diverge from estimates.

This lesson belongs to the `DATABASE_MYSQL` module and focuses on resolving query performance regressions caused by statistics, data skew, and execution plan changes. The content connects indexes, the optimizer, `EXPLAIN`, InnoDB persistent statistics, histograms, and production monitoring.

After this lesson, you will be able to:

- Isolate slow queries using statement digests and execution metrics.
- Compare execution plans before and after a performance regression.
- Read estimated rows, actual rows, access types, and join steps.
- Understand InnoDB index statistics, persistent stats, and automatic recalculation.
- Use histograms to describe skewed value distributions.
- Distinguish statistics problems from index, SQL, locking, or resource problems.
- Restore performance by updating stats, improving indexes, or rewriting queries.
- Assess risks when using optimizer hints and control plan changes safely.

## 1. Scoping the Incident Accurately

When someone reports a "slow query", determine whether it affects one SQL statement, a group of queries, or the entire database:

- Only one query digest is slow while other queries behave normally: focus on SQL, indexes, statistics, and execution plans.
- Multiple queries on the same table slowed down together: check I/O load, locks, buffer pool, data changes, or DDL.
- Many queries across multiple tables slowed down together: check CPU, memory, storage latency, connection saturation, and overall workload.
- Only certain parameter values are slow: suspect data skew, varying selectivity, or a query shape unsuited to every data distribution.
- Query slowed down after a deploy, bulk load, `ANALYZE TABLE`, index addition, or MySQL upgrade: compare schema changes, stats, optimizer settings, and versions.

Do not start by running `ANALYZE TABLE` or `FORCE INDEX` the moment a slow query appears. Capture evidence first so you know where the problem lies and can compare results after remediation.

## 2. Isolating Queries with Performance Schema

Performance Schema aggregates statements by digest, making it easy to find SQL consuming the most time or examining too many rows. Example querying top digests by total time:

```sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(AVG_TIMER_WAIT / 1000000000, 2) AS avg_ms,
    ROUND(MAX_TIMER_WAIT / 1000000000, 2) AS max_ms,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    FIRST_SEEN,
    LAST_SEEN
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST_TEXT IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Timers in Performance Schema are expressed in picoseconds; divide by `1,000,000,000` to convert to milliseconds. `COUNT_STAR`, `AVG_TIMER_WAIT`, `MAX_TIMER_WAIT`, `SUM_ROWS_EXAMINED`, and `SUM_ROWS_SENT` reveal frequently executed queries, high-latency queries, or queries scanning excessive rows.

Notes:

- Digests normalize literals, so many different parameter values collapse into the same digest.
- `AVG_TIMER_WAIT` can hide occasional very slow runs; also inspect `MAX_TIMER_WAIT` and latency percentiles from monitoring tools.
- High `SUM_ROWS_EXAMINED` does not automatically prove a bad plan; compare it against rows returned and the query's goal.
- Performance Schema resets on server restarts or when summary tables are truncated; snapshot metrics periodically if long-term history is required.

Inspect currently running queries:

```sql
SHOW FULL PROCESSLIST;
```

Record SQL fingerprint, schema, elapsed time, state, rows read/returned, start time, and recent changes. Do not include literals containing personal data or secrets in widely shared reports.

## 3. Capturing the Execution Plan Before Making Changes

`EXPLAIN` shows how the optimizer intends to execute a query. For a slow query, capture the plan on the exact server, schema, session settings, and SQL shape the application executes.

### 3.1. Tabular EXPLAIN

```sql
EXPLAIN
SELECT order_id, created_at, total_amount
FROM shop.orders
WHERE customer_id = 42
  AND order_status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
```

Key columns:

| Column | Meaning |
|---|---|
| `select_type` | `SELECT` type, such as `SIMPLE`, `PRIMARY`, or `SUBQUERY` |
| `table` | Table or derived table being read |
| `type` | Access type, from `const`/`eq_ref`/`ref`/`range` down to `index`/`ALL` |
| `possible_keys` | Indexes the optimizer could consider |
| `key` | Index the optimizer expects to choose |
| `key_len` | Length of the index prefix used |
| `rows` | Estimated rows the optimizer expects to read |
| `filtered` | Estimated percentage of rows remaining after filter conditions |
| `Extra` | Additional info such as `Using filesort`, `Using temporary`, or `Using index` |

`ALL` usually denotes a full table scan; `index` can be a full index scan. However, a full scan can be rational when a table is tiny or a query needs most of the rows. `Using filesort` and `Using temporary` are not automatically bugs either; evaluate data volume, duration, and the overall plan.

### 3.2. EXPLAIN FORMAT=JSON

```sql
EXPLAIN FORMAT=JSON
SELECT order_id, created_at, total_amount
FROM shop.orders
WHERE customer_id = 42
  AND order_status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
```

JSON plans provide richer details on cost, access paths, pushed-down conditions, estimated rows, and joins. This format is useful for comparing plans in automated reports.

### 3.3. EXPLAIN ANALYZE

In MySQL 8.0.18 and later, `EXPLAIN ANALYZE` executes the `SELECT` query and returns the execution tree annotated with actual runtime metrics:

```sql
EXPLAIN ANALYZE
SELECT order_id, created_at, total_amount
FROM shop.orders
WHERE customer_id = 42
  AND order_status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
```

Output typically includes `actual time`, `rows`, and `loops` for each iterator. Compare estimated rows in `EXPLAIN` with actual rows in `EXPLAIN ANALYZE`. Huge estimation gaps at a step point directly to statistics, data skew, column correlation, or filter selectivity issues.

`EXPLAIN ANALYZE` actually executes the `SELECT`. Never run heavy queries in production without evaluating load and impact. Prefer staging or a suitable replica, bounded datasets, and controlled test windows. Never run it on a `SELECT` invoking stored functions with side effects.

## 4. Understanding Why the Optimizer Changes Plans

The MySQL optimizer picks access paths based on estimated cost. Cost depends on row count statistics, index cardinality, predicate selectivity, histograms, table size, available indexes, and optimizer settings.

A small shift in statistics can flip the ranking between two plans. For example:

- Previously `order_status = 'PAID'` matched only 2% of rows, making the status index look attractive.
- After a payment campaign, 80% of orders transitioned to `PAID`.
- The optimizer estimates an index scan plus random row lookups costs more than a table scan.
- The new plan drops the index even though the SQL did not change.

The new plan is not necessarily wrong. If the data genuinely shifted, a different plan may be better. Trouble strikes when estimates fail to reflect reality or the new plan pushes a critical query past its SLA.

Common causes:

1. Bulk inserts/updates/deletes altered the data distribution.
2. InnoDB automatically recalculated persistent stats or an admin ran `ANALYZE TABLE`.
3. An index was created, dropped, or toggled visible/invisible.
4. Histograms no longer reflect current distribution.
5. The table grew rapidly or proportions between values shifted.
6. MySQL was upgraded, changing optimizer cost models or defaults.
7. `optimizer_switch`, SQL mode, collation, or session settings differ across environments.
8. SQL changed, predicates were added, parameter types changed, or implicit conversion appeared.

Save before/after plans and configurations to distinguish data changes from application or server changes.

## 5. InnoDB Index Statistics and Persistent Statistics

InnoDB maintains table and index statistics so the optimizer can estimate cardinality, row counts, and access costs. Index statistics rely on sampling a subset of pages, so `Cardinality` in `SHOW INDEX` is an estimate, not an exact distinct count.

Inspect indexes:

```sql
SHOW INDEX FROM shop.orders;
```

Pay attention to:

- `Key_name`: index name.
- `Seq_in_index`: column position in a composite index.
- `Column_name`: indexed column.
- `Non_unique`: whether the index allows duplicates.
- `Cardinality`: estimated count of distinct values.
- `Visible`: whether the optimizer considers the index, on versions supporting invisible indexes.

### 5.1. Persistent Statistics

InnoDB persistent statistics survive server restarts. On modern MySQL versions, persistent stats are usually enabled by default. Check:

```sql
SHOW VARIABLES LIKE 'innodb_stats_persistent';
SHOW VARIABLES LIKE 'innodb_stats_auto_recalc';
SHOW VARIABLES LIKE 'innodb_stats_persistent_sample_pages';
```

`innodb_stats_auto_recalc` controls automatic recalculation of persistent stats when data changes exceed an internal/configured threshold. Under common defaults, modifying roughly 10% of rows can trigger recalculation; this is not an instantaneous guarantee and can be affected by table/server settings.

`innodb_stats_persistent_sample_pages` controls how many pages are sampled when calculating persistent stats. Increasing sampling can improve representativeness on some skewed tables, at the cost of heavier analysis work. Do not raise this variable globally because of one slow query; first identify which index/table has inaccurate stats.

You can inspect persistent stats in system tables if authorized:

```sql
SELECT *
FROM mysql.innodb_table_stats
WHERE database_name = 'shop'
  AND table_name = 'orders';

SELECT
    index_name,
    stat_name,
    stat_value,
    sample_size,
    last_update
FROM mysql.innodb_index_stats
WHERE database_name = 'shop'
  AND table_name = 'orders'
ORDER BY index_name, stat_name;
```

This data is for diagnostics. Never edit system statistics tables directly to force optimizer plans. Use `ANALYZE TABLE` and supported mechanisms to refresh stats.

### 5.2. Updating Index Statistics

After loading large datasets, deleting many rows, or dramatically changing data distributions, you can run:

```sql
ANALYZE TABLE shop.orders;
```

This instructs MySQL to recalculate table/index statistics. Then re-run `EXPLAIN` and measure performance to see whether estimates improved.

`ANALYZE TABLE` is not harmless in every environment. It can consume I/O/CPU and acquire metadata locks or cause brief impacts depending on version, engine, and table state. Run it deliberately, monitor workload, and avoid mass stats refreshes during peak hours without assessment.

## 6. Data Skew: When Data Distribution Is Uneven

Data skew occurs when certain values appear vastly more often than others. Suppose `orders` has 50 million rows:

| `order_status` | Illustrative Share |
|---|---:|
| `PAID` | 78% |
| `CREATED` | 12% |
| `CANCELLED` | 8% |
| `REFUNDED` | 2% |

A single-column index on `order_status` can be very helpful when querying `REFUNDED`, yet poor for querying `PAID` because most of the table matches. If the optimizer has only basic cardinality stats or unrepresentative sampling, it can misestimate selectivity.

Check distribution in an environment able to handle the load:

```sql
SELECT
    order_status,
    COUNT(*) AS row_count,
    ROUND(
        100.0 * COUNT(*) / SUM(COUNT(*)) OVER (),
        2
    ) AS percentage
FROM shop.orders
GROUP BY order_status
ORDER BY row_count DESC;
```

On very large tables, `COUNT(*)` can take significant time and I/O. Use a replica, sampling, or pre-aggregated stats when needed; clearly mark estimated numbers.

### 6.1. Same Query Shape, Different Parameter Values

Query:

```sql
SELECT order_id, created_at
FROM shop.orders
WHERE order_status = ?
ORDER BY created_at DESC
LIMIT 50;
```

`REFUNDED` is highly selective, whereas `PAID` matches most of the table. An index ideal for a rare value may be suboptimal for a dominant value. Testing with a single parameter value does not represent the entire workload.

When investigating, test representative values:

- The most common value.
- The rarest value.
- A value with average frequency.
- Values belonging to the largest tenant or highest-traffic data group.

Never log sensitive literals. Log distribution buckets or selectivity tiers instead of raw customer values.

## 7. Histograms Help the Optimizer Understand Column Distributions

Histograms describe value distributions within a column so the optimizer estimates selectivity more accurately, especially under data skew where standard index stats fall short. MySQL supports histograms on selected columns and stores metadata in the data dictionary.

Create a histogram:

```sql
ANALYZE TABLE shop.orders
    UPDATE HISTOGRAM ON order_status
    WITH 16 BUCKETS;
```

Up to 1024 buckets are supported. More buckets capture finer distribution detail without automatically guaranteeing a better plan. Choose bucket count based on distinct value count, skew severity, and benchmark results.

View the histogram:

```sql
SELECT
    SCHEMA_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    HISTOGRAM
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = 'shop'
  AND TABLE_NAME = 'orders'
  AND COLUMN_NAME = 'order_status';
```

Drop a histogram:

```sql
ANALYZE TABLE shop.orders
    DROP HISTOGRAM ON order_status;
```

Histograms are managed explicitly via `UPDATE HISTOGRAM` and `DROP HISTOGRAM`. Never assume ordinary index statistics refreshes automatically update histograms. After major data shifts, verify whether histograms remain representative and refresh as needed.

### 7.1. Limitations of Histograms

- Histograms describe single-column distributions; they do not capture correlations across multiple columns.
- Histograms do not replace indexes. They help the optimizer estimate selectivity, whereas indexes provide physical access paths.
- A stale histogram can distort estimates when distributions shift.
- A better histogram does not guarantee the fastest plan; the cost model and workload still govern choices.

For example, `tenant_id` and `order_status` may correlate strongly: tenant A has 95% `PAID` orders while tenant B has only 10%. Separate single-column histograms cannot describe the joint distribution of `(tenant_id, order_status)`. In such cases, inspect composite indexes, query shapes, and estimated vs. actual rows.

## 8. Composite Indexes and Selectivity

When queries filter on multiple columns, a composite index lets the optimizer read far fewer rows. Example:

```sql
SELECT order_id, created_at, total_amount
FROM shop.orders
WHERE customer_id = 42
  AND order_status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
```

A candidate index might be:

```sql
CREATE INDEX idx_orders_customer_status_created
ON shop.orders (customer_id, order_status, created_at);
```

Column order must follow workload and filter predicates. Under the leftmost prefix rule, `(customer_id, order_status, created_at)` supports predicates starting with `customer_id`, yet is not similarly effective when filtering solely on `order_status` without the leading column.

Evaluate:

- Equality columns generally precede range or sort columns in many query patterns, though actual plans must still be verified.
- High cardinality often improves filtering, though it is not the sole criterion.
- Added indexes increase disk usage and `INSERT`/`UPDATE`/`DELETE` overhead.
- If a query selects many columns absent from the index, InnoDB must still look up rows in the clustered index.
- Indexes can satisfy `ORDER BY` and `LIMIT` without a large sort when column order aligns.

Never add an index merely because a column appears in `WHERE`. Weigh query frequency, selectivity, write workload, and existing indexes before changing anything.

## 9. Distinguishing Statistics Drift from SQL or Index Issues

Not every bad plan stems from statistics. Check these possibilities:

| Symptom | Possible Cause | How to Verify |
|---|---|---|
| Estimated rows differ vastly from actual rows | Stale stats, unrepresentative sampling, missing histogram, or data skew | `EXPLAIN ANALYZE`, `SHOW INDEX`, histograms, and InnoDB stats |
| Optimizer skips an existing index | Non-sargable predicate, implicit cast, collation mismatch, low selectivity | Check `key`, `type`, functions on columns, and parameter types |
| Plan looks good yet query stays slow | I/O, lock waits, CPU, buffer pool misses, or network/result transfer | Processlist, Performance Schema, InnoDB status, and system metrics |
| One value fast, another value slow | Data skew or per-tenant/group correlation | Test multiple representative values and real distributions |
| Query slowed down after DDL | Index altered, invisible, dropped, or schema/plan changed | Compare `SHOW CREATE TABLE`, `SHOW INDEX`, and plans |
| Slow after upgrade | Optimizer/cost model or defaults changed | Compare versions, settings, and plans in staging |
| Filesort or temporary table appears | Index cannot satisfy `ORDER BY`/`GROUP BY` or query needs sorting | Check row counts, indexes, and `EXPLAIN` output |

Expressions like `DATE(created_at) = ...`, `CAST(indexed_col AS ...)`, or cross-type comparisons can prevent effective index usage. Rewriting SQL into an equivalent range predicate is often far more effective:

```sql
-- May struggle to use index on created_at:
WHERE DATE(created_at) = '2026-11-19'

-- Range form is usually more index-friendly:
WHERE created_at >= '2026-11-19 00:00:00'
  AND created_at <  '2026-11-20 00:00:00'
```

Verify column type and time zone to guarantee both conditions remain semantically identical.

## 10. Using Optimizer Trace to Understand Decisions

When `EXPLAIN` shows the optimizer picking an unexpected access path, you can enable optimizer trace in your session:

```sql
SET optimizer_trace = 'enabled=on';

EXPLAIN
SELECT order_id, created_at
FROM shop.orders
WHERE customer_id = 42
  AND order_status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;

SELECT TRACE
FROM INFORMATION_SCHEMA.OPTIMIZER_TRACE\G

SET optimizer_trace = 'enabled=off';
```

The trace reveals considered access paths, pruned predicates, estimated costs, and why a given index was rejected. Output is verbose and version-dependent; enable it only inside an investigative session and disable it once data is collected.

Never tune global cost models or optimizer settings based on a single trace. First establish whether misestimation comes from stats, data skew, indexes, or SQL shape.

## 11. Procedure When Plans Flip and Queries Slow Down

Proceed in order to preserve evidence and avoid introducing extra variables:

1. **Identify the query:** capture digest, schema, p95/p99 latency, rows examined/sent, and regression start time.
2. **Scope the system:** check CPU, I/O, buffer pool, lock waits, connection counts, and concurrent workload.
3. **Collect SQL:** capture representative SQL and parameter groups with varying selectivity.
4. **Save current plan:** run `EXPLAIN`/`FORMAT=JSON`; use `EXPLAIN ANALYZE` safely on controlled queries.
5. **Compare against prior plan:** check indexes, join order, access type, estimated rows, and actual rows if a baseline exists.
6. **Check recent changes:** deploys, DDL, bulk loads, `ANALYZE TABLE`, upgrades, optimizer variables, and traffic shifts.
7. **Inspect stats:** check `SHOW INDEX`, persistent stats, histograms, and update timestamps.
8. **Confirm data skew:** measure column distributions and representative parameter values.
9. **Choose remediation:** refresh stats/histograms, rewrite SQL, or add a justified index.
10. **Re-measure:** run the same query, same parameter groups, and comparable load, comparing latency and rows examined.
11. **Roll out safely:** validate in staging/canary, monitor write overhead, and keep rollback ready.
12. **Document outcome:** record plans, stats, changes, and recovery verification criteria.

## 12. Fixes by Root Cause

### 12.1. Stale Index Statistics

If estimated rows diverge significantly after major data changes, consider:

```sql
ANALYZE TABLE shop.orders;
```

Then re-run `EXPLAIN` and measure runtime performance. Do not run `ANALYZE` repeatedly if estimates do not improve; investigate sampling, histograms, correlation, and query shape instead.

### 12.2. Histogram Missing or Stale Under Data Skew

Update the histogram on a skewed column when queries depend on its selectivity:

```sql
ANALYZE TABLE shop.orders
    UPDATE HISTOGRAM ON order_status
    WITH 32 BUCKETS;
```

Compare before/after estimated rows across both common and rare values. If a histogram worsens the plan, drop it and re-verify:

```sql
ANALYZE TABLE shop.orders
    DROP HISTOGRAM ON order_status;
```

### 12.3. Unsuitable Indexes

Design composite indexes matching filter predicates, sort order, and selectivity. Before creating an index, inspect existing indexes to avoid duplicates or near-duplicates differing only slightly in column order. Measure write overhead and storage impact.

### 12.4. Non-Sargable SQL

Rewrite predicates to avoid applying functions or casts to indexed columns whenever possible. Use range predicates, match parameter types to column types, and eliminate implicit conversions.

### 12.5. Load or Locks Are the Real Cause

If the plan and estimated/actual rows are reasonable yet latency remains high, address lock contention, long transactions, I/O, buffer pool pressure, or concurrency saturation. Changing indexes in this situation can worsen write overhead without fixing the root cause.

## 13. Controlled Use of Optimizer Hints and Index Forcing

Optimizer hints or `FORCE INDEX` can help as a temporary measure once you have proven the optimizer picks a bad plan on a specific workload. However, hints can become harmful when data or workloads evolve.

Example query hint:

```sql
SELECT /*+ INDEX(o idx_orders_customer_status_created) */
       o.order_id, o.created_at, o.total_amount
FROM shop.orders AS o
WHERE o.customer_id = 42
  AND o.order_status = 'PAID'
ORDER BY o.created_at DESC
LIMIT 20;
```

Before using a hint:

- Prove the unhinted plan is slower across multiple representative parameter groups.
- Benchmark on production-like MySQL version and data.
- Document the query, index, and rationale for adding the hint.
- Set a review date and removal criteria.
- Re-check whenever data, indexes, or server versions change.

Never force indexes globally or tweak optimizer settings just to patch one query. If a hint speeds up a rare value while slowing down common values, it is not a holistic fix.

## 14. Testing Index Impact with Invisible Indexes

MySQL 8.0 supports invisible indexes to evaluate what happens when the optimizer ignores an index without dropping it. This is a valuable testing tool in staging:

```sql
ALTER TABLE shop.orders
    ALTER INDEX idx_orders_status INVISIBLE;
```

The optimizer ignores invisible indexes by default. To test using that index inside a test session:

```sql
SET SESSION optimizer_switch = 'use_invisible_indexes=on';
```

Restore visibility:

```sql
ALTER TABLE shop.orders
    ALTER INDEX idx_orders_status VISIBLE;
```

Changing index visibility affects the optimizer table-wide, not just in one test session. Never toggle a production index to invisible before auditing all dependent queries. Use staging or a controlled change window, save before/after plans, and keep the restore command ready.

## 15. Things to Avoid When Queries Suddenly Slow Down

- Do not run `ANALYZE TABLE` across every table without identifying the involved table.
- Do not add multiple experimental indexes in production without measuring write overhead and storage.
- Do not slap on `FORCE INDEX` simply because the current plan shows `type=ALL`.
- Do not raise `innodb_stats_persistent_sample_pages` globally to fix a single query.
- Do not drop histograms without saving prior state and measuring impact.
- Do not conclude `Using filesort` is always the cause of slowness.
- Do not use one parameter value to represent skewed datasets.
- Do not run `EXPLAIN ANALYZE` on heavy queries during peak hours without assessing impact.
- Do not directly modify `mysql.innodb_*_stats` tables.
- Do not ignore lock waits, I/O, and system load when the plan has not changed.

## 16. Symptom and Diagnostic Matrix

| Symptom | High-Probability Cause | Evidence to Look For | Next Step |
|---|---|---|---|
| Query slowed right after `ANALYZE TABLE` | New stats caused optimizer to switch plans | Before/after plans, cardinality, estimated rows | Evaluate new plan across multiple parameters; check histograms/indexes |
| Estimated rows very low while actual rows very high | Stale stats, unrepresentative sampling, or missing histogram | `EXPLAIN ANALYZE`, distribution query, index stats | Refresh stats or histogram, then re-measure |
| One status is fast, another is slow | Data skew | Share per value, plan per value | Design workload-appropriate index/query or split query branches |
| Plan uses full table scan after table grew | Missing index, low selectivity, or changed stats | `EXPLAIN`, `SHOW INDEX`, table size | Evaluate composite index and actual costs |
| Plan unchanged yet latency rose | Locks, I/O, CPU, or network | Processlist, wait events, InnoDB metrics | Resolve contention/resources instead of forcing indexes |
| Query uses different index after deploy | SQL shape, schema, stats, or optimizer settings changed | Diff SQL, DDL, `optimizer_switch`, plans | Identify recent change and roll back or tune safely |
| Histogram exists yet estimates remain wrong | Multi-column correlation or stale histogram | Histogram JSON, joint values, actual rows | Evaluate composite index and query design |

## 17. Practice Scenario

An `orders` table has 40 million rows. A query fetching the 50 most recent orders by `order_status` used to run fast, but after a surge in completed payments, queries for status `PAID` became much slower. Digests show rows examined spiked and the optimizer stopped picking the old index.

Practice in a lab environment:

1. Record the `EXPLAIN FORMAT=JSON` plan and digest metrics before loading extra data.
2. Seed an initial distribution where `PAID` is a rare value.
3. Run queries for `PAID`, `CREATED`, and `REFUNDED`; record latency and rows examined.
4. Load more rows so `PAID` becomes the dominant value, then observe the plan change.
5. Run `EXPLAIN ANALYZE` in the lab to compare estimated rows against actual rows.
6. Run `ANALYZE TABLE` and observe cardinality and plan changes after stats refresh.
7. Create a histogram on `order_status`, inspect `INFORMATION_SCHEMA.COLUMN_STATISTICS`, and re-measure.
8. Test composite indexes `(order_status, created_at)` or `(customer_id, order_status, created_at)` against realistic query workloads; compare read/write costs.
9. Use an invisible index in the lab to observe behavior when the optimizer ignores an index.
10. Test an optimizer hint on a specific query across multiple parameter values and document removal criteria.
11. Compare before/after p95 latency, rows examined, CPU/I/O, and write throughput.
12. Write a runbook for detecting plan regressions and rolling back index/histogram changes.

**Self-assessment questions:**

- Why can a query change execution plans without any SQL changes?
- Is `Cardinality` in `SHOW INDEX` an exact count of distinct values?
- How do persistent stats and histograms differ in how they are managed?
- Why can `ANALYZE TABLE` make a query either faster or slower?
- How does data skew affect selectivity and index choice?
- What kind of correlation can a single-column histogram not describe?
- How does `EXPLAIN ANALYZE` differ from regular `EXPLAIN`, and why must it be used cautiously?
- When can a full table scan be a reasonable plan?
- Why can `FORCE INDEX` become problematic after data evolves?
- How do you distinguish a plan regression from a lock or I/O bottleneck?

## Conclusion

Sudden slow queries require investigation using execution metrics and execution plans before changing the schema. Compare estimated vs. actual rows, inspect persistent index stats, data skew, and histograms, and determine whether the root cause lies in statistics, indexes, SQL, or system resources. Refresh stats, create indexes, or apply hints only after measuring across representative data values; always save before/after plans and keep a clear rollback path.
