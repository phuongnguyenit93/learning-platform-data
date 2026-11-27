# Selectivity, Cardinality, and Skewed Data Distributions

An index can contain many distinct values and still not help a specific query. Conversely, a column with only a few values can be very useful if queries frequently search for a rare value. To understand why MySQL chooses an index or a full table scan, you must distinguish three concepts: **cardinality**, **index selectivity**, and **filter selectivity**.

In MySQL/InnoDB, cardinality in index statistics is the estimated number of distinct values. Selectivity indicates how strongly a column or predicate narrows the row set. Skewed data distributions cause values in the same column to occur at vastly different frequencies; in such cases, a single average figure cannot accurately describe the query being executed.

This lesson belongs to the **Indexes** chapter of the **DATABASE_MYSQL** module. Within the scope of mastering MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control, reading statistics accurately helps choose indexes by workload, spot optimizer misestimates, and avoid adding an index merely because a column has high cardinality.

## 1. Distinguishing cardinality and two meanings of selectivity

The **cardinality** of a column is the number of distinct values in the column. For example, if a table has one million orders yet only four statuses, the cardinality of `status` is roughly 4. If every `order_id` is unique, the cardinality of `order_id` is roughly one million.

In MySQL, the `Cardinality` column of `SHOW INDEX` estimates the number of distinct values of the index or corresponding index prefix. For multi-column indexes, each row in `SHOW INDEX` output describes one column in the index; `Cardinality` on that row estimates distinct values of the prefix up to that column. This is an estimated statistic, not an exact count across every value on every query.

From cardinality you can compute a metric often called **index selectivity**:

\[
\text{Index selectivity} =
\frac{\text{Number of distinct values}}
{\text{Total number of rows}}
\]

The closer this ratio is to 1, the better values distinguish rows. For a unique key, this ratio is close to 1. For a status column with only four values across one million rows, this ratio is tiny.

Another usage is the **filter selectivity** of a `WHERE` condition:

\[
\text{Filter selectivity} =
\frac{\text{Number of matching rows}}
{\text{Total number of rows}}
\]

Under this usage, the smaller the ratio, the more selective the condition because fewer rows remain. The two usages of the word selectivity have opposite directional interpretations. When reading documentation, reports, or discussing with teammates, clarify whether you mean `distinct/total` or `matching/total`.

| Concept | Formula or meaning | Example |
|---|---|---|
| Cardinality | Number of distinct values | 4 statuses in an orders table |
| Index selectivity | `distinct values / total rows` | 4 / 1,000,000 = 0.000004 |
| Filter selectivity | `matching rows / total rows` | 1,000 `FAILED` rows / 1,000,000 = 0.001 |
| Data skew | Uneven frequencies across values | `PAID` is 95%, `FAILED` is 0.1% |

Do not conclude that low index selectivity means an index is useless. Cardinality tells you only how many distinct values exist; it does not tell you how frequently each value occurs. To evaluate a specific query, examine the actual distribution of the value sought by `WHERE`.

## 2. Inspecting the cardinality MySQL stores

Suppose you have an `orders` table with columns `order_id`, `tenant_id`, `status`, `created_at`, and `amount`. You can view existing indexes with:

~~~sql
SHOW INDEX FROM orders;
~~~

Key columns in the output:

- **Key_name**: index name.
- **Seq_in_index**: column position in a composite index, starting at 1.
- **Column_name**: column in the index.
- **Non_unique**: `0` if the index enforces uniqueness, `1` if duplicates are allowed.
- **Cardinality**: estimated distinct values for the index or index prefix up to the current column.
- **Sub_part**: indexed prefix length if the index uses a prefix.
- **Index_type**: index type, usually `BTREE` for standard InnoDB indexes.

Composite index example:

~~~sql
CREATE INDEX ix_orders_tenant_status_created
ON orders (tenant_id, status, created_at);
~~~

`SHOW INDEX` can return three rows for this index. `Cardinality` on the `tenant_id` row describes distinct tenants; on the `status` row, distinct `tenant_id + status` combinations; on the `created_at` row, estimated distinct `tenant_id + status + created_at` combinations. Do not read the second column's cardinality as if it were the count of distinct statuses across the whole table.

You can read statistics from Information Schema:

~~~sql
SELECT
    INDEX_NAME,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    CARDINALITY,
    NON_UNIQUE,
    INDEX_TYPE
FROM information_schema.statistics
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

InnoDB cardinality is a statistic derived from sampling index pages. It can diverge from actual distinct counts, especially when data distribution is uneven or the table changes substantially. Row counts in `INFORMATION_SCHEMA.TABLES` are also typically estimates for InnoDB. Do not treat these two estimates as exact proof for a design decision.

If you need an exact distinct count for analysis on an appropriately sized table, you can run:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT status) AS distinct_status,
    ROUND(
        COUNT(DISTINCT status) / NULLIF(COUNT(*), 0),
        8
    ) AS index_selectivity
FROM orders;
~~~

`COUNT(DISTINCT column)` ignores `NULL` values. If the column is nullable and the `NULL` ratio matters to the query, tally `NULL`s separately. On very large tables, `COUNT(*)` and `COUNT(DISTINCT)` can read substantial data; consider running them on an analytics replica, during an appropriate window, or using sampling when preliminary profiling is sufficient.

## 3. Measuring per-value distribution instead of looking only at distinct counts

Suppose `orders` has one million rows and `status` has only four values. A distinct count of 4 does not tell you which status dominates. Count rows per value:

~~~sql
SELECT
    status,
    COUNT(*) AS rows_for_value
FROM orders
GROUP BY status
ORDER BY rows_for_value DESC;
~~~

To view each group's percentage of the whole table:

~~~sql
SELECT
    grouped.status,
    grouped.rows_for_value,
    totals.total_rows,
    ROUND(
        100.0 * grouped.rows_for_value / NULLIF(totals.total_rows, 0),
        2
    ) AS percent_of_table
FROM (
    SELECT status, COUNT(*) AS rows_for_value
    FROM orders
    GROUP BY status
) AS grouped
CROSS JOIN (
    SELECT COUNT(*) AS total_rows
    FROM orders
) AS totals
ORDER BY grouped.rows_for_value DESC;
~~~

Suppose an illustrative result looks like:

| status | Row count | Percentage |
|---|---:|---:|
| `PAID` | 950,000 | 95% |
| `PENDING` | 35,000 | 3.5% |
| `CANCELLED` | 14,000 | 1.4% |
| `FAILED` | 1,000 | 0.1% |

These numbers merely illustrate a skewed table. In practice, measure on your own system's data at a time meaningful to your workload.

Condition `status = 'FAILED'` matches only 0.1% of rows, so an index can locate this small group quickly. Condition `status = 'PAID'` matches 95% of rows; reading the index and jumping back to the table for nearly every record can cost more than a sequential table scan. Hence, the exact same index can be helpful for one value and ignored by the optimizer for another.

Another example is `tenant_id`. Suppose tenant 42 produces 70% of all rows while thousands of other tenants share the remaining 30%. The cardinality of `tenant_id` may be very high, yet `tenant_id = 42` still matches most of the table. Looking solely at distinct tenant count misses this skew.

## 4. Why skewed distributions affect index selection

The optimizer needs to estimate rows read and the cost of candidate execution plans. When estimates are accurate, it can choose among:

- Scanning the entire table or the required data span.
- Finding entries via a secondary index and reading corresponding rows from the clustered index.
- Using a covering index if query columns reside in the index.
- Combining predicates across multiple columns or multiple indexes when that plan costs less.

A `BTREE` secondary index can drastically reduce rows read when a condition selects a small fraction of data. However, when a condition matches most of the table, scanning the index and performing numerous clustered index lookups can be costlier than a single sequential scan.

Therefore, **indexing a column with few distinct values is not automatically wrong**:

- If a rare status is queried frequently, a `status` index can be useful.
- If most queries look up the dominant status, a standalone `status` index may not be selected.
- If queries always filter by tenant and time interval, a composite index `tenant_id + created_at` may be more useful than a standalone `status` index.
- If queries need only columns already in the index, a covering index can avoid reading rows from the clustered index.

Every index also carries costs: disk space, extra write work on `INSERT`/`UPDATE`/`DELETE`, maintenance overhead, and more candidate plans for the optimizer to weigh. Create indexes to serve real queries, not just to make cardinality look higher.

## 5. Using EXPLAIN to check optimizer estimates

Start with a query representative of the workload:

~~~sql
EXPLAIN
SELECT order_id, created_at
FROM orders
WHERE status = 'FAILED';
~~~

In tabular `EXPLAIN` output, inspect:

- **type**: access type, ranging from scans like `ALL` to index accesses like `range`, `ref`, or `const`. This is a signal to interpret alongside the other columns, not an absolute score.
- **possible_keys**: indexes the optimizer considers candidates.
- **key**: index actually selected, if any.
- **key_len**: length of the index portion used.
- **rows**: estimated number of rows to read at that step.
- **filtered**: estimated percentage of rows remaining after additional filtering at that step.
- **Extra**: additional details such as `Using where`, `Using index`, or `Using index condition`.

If `key` is `NULL`, the optimizer chose no index for that access step. This can be entirely reasonable if the condition matches most of the table, the index does not match column ordering, or the index's expected cost exceeds a table scan.

In MySQL 8.0.18 and later, `EXPLAIN ANALYZE` provides actual execution metrics for `SELECT`:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, created_at
FROM orders
WHERE status = 'FAILED';
~~~

`EXPLAIN ANALYZE` actually executes the query to measure real timings and row counts across iterators. Run it only on read queries whose scope you clearly understand; an expensive query can still consume production CPU, I/O, and resources. Do not treat `EXPLAIN ANALYZE` as a static analysis command.

When comparing plans, examine discrepancies between estimated rows and actual rows:

- Estimates close to actuals: the optimizer has reasonably accurate information for that condition.
- Estimates far lower than actuals: the optimizer may underestimate data volume to read, leading to a poor join order or access path.
- Estimates far higher than actuals: the optimizer may skip a useful index or choose a costlier plan than necessary.
- Sharp discrepancy on one value but not another: check data skew, histograms, and parameter binding.

Costs and timings in `EXPLAIN ANALYZE` depend on data, caches, server load, and environment. A single run is insufficient to conclude stable performance; test multiple times under comparable conditions.

## 6. Refreshing index statistics

When data changes substantially, stale statistics may no longer represent the table. You can ask MySQL to refresh statistics with:

~~~sql
ANALYZE TABLE orders;
~~~

Then re-check:

~~~sql
SHOW INDEX FROM orders;
~~~

`ANALYZE TABLE` updates optimizer statistics; it creates no indexes and alters no business data. With InnoDB, cardinality statistics rely on sampling and remain estimates. Analyzing a table may read data and consume resources; schedule an appropriate window for large tables or heavily loaded systems.

If you just loaded a large dataset, deleted most of the data, heavily shifted status ratios, or shifted workload to a different set of tenants, re-evaluate statistics rather than assuming old cardinality remains valid.

## 7. Using histograms to describe skewed distributions

Cardinality describes only the count of distinct values. Histograms add information about how values are distributed within a column, helping the optimizer produce better estimates when certain values occur far more often than others.

In MySQL 8.0, you can create or update histograms on one or more columns:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status, tenant_id
WITH 64 BUCKETS;
~~~

MySQL supports two main histogram types:

- **Singleton histogram**: has one bucket per distinct value. This suits columns with a relatively small number of distinct values.
- **Equi-height histogram**: divides the distribution into buckets representing roughly equal row counts; bucket boundaries describe value ranges and cumulative frequencies. This is useful when a column has many distinct values.

The bucket count is the upper limit of granularity you request for the histogram. More buckets can describe the distribution in finer detail while increasing statistics size. Do not mechanically pick the maximum bucket count; balance estimate quality against cost and workload.

You can inspect histograms in Information Schema:

~~~sql
SELECT
    SCHEMA_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    JSON_PRETTY(HISTOGRAM) AS histogram_json
FROM information_schema.column_statistics
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'orders'
  AND COLUMN_NAME IN ('status', 'tenant_id');
~~~

In the histogram JSON, important fields can include histogram type, bucket count, `NULL` fraction, sampling rate, update timestamp, and buckets with cumulative frequencies. This is statistical metadata, not a row-by-row copy of data.

If you need to drop created histograms:

~~~sql
ANALYZE TABLE orders
DROP HISTOGRAM ON status, tenant_id;
~~~

MySQL histograms are single-column statistics. They do not fully capture correlations across multiple columns. For instance, if `FAILED` appears almost exclusively for one specific tenant, separate histograms on `status` and `tenant_id` do not necessarily capture the joint probability of both predicates together. Composite indexes and index prefix statistics can supplement multi-column combination info, yet you must still inspect real execution plans.

Histograms can also become stale when data changes sharply. Check update timestamps and proactively refresh them after major distribution shifts. Do not confuse InnoDB's automatic index statistics updates with refreshing manually created histograms.

## 8. Designing indexes around query conditions and skew

Suppose a query frequently fetches failed orders for a tenant over a time range:

~~~sql
SELECT order_id, created_at, amount
FROM orders
WHERE tenant_id = 17
  AND status = 'FAILED'
  AND created_at >= '2026-10-01'
  AND created_at <  '2026-11-01'
ORDER BY created_at;
~~~

A composite index may fit:

~~~sql
CREATE INDEX ix_orders_tenant_status_created
ON orders (tenant_id, status, created_at);
~~~

The first two predicates are equality comparisons; `created_at` is used for a time range. Index column order must be based on actual query sets, selectivity, predicate types, and sort requirements. The order of predicates in the `WHERE` clause does not dictate index column order.

If another query frequently filters only by `status` and `created_at` without `tenant_id`, an index starting with `tenant_id` may not serve that query well due to the leftmost prefix principle. Another index might be needed, but add it only when workload and measurements demonstrate sufficient benefit.

Compare two cases:

~~~sql
-- Query for one tenant and a narrow time window.
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 17
  AND created_at >= '2026-11-01'
  AND created_at <  '2026-11-02';

-- Query for a tenant holding most of the data and a wide time window.
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 42
  AND created_at >= '2025-01-01'
  AND created_at <  '2027-01-01';
~~~

Both filter by `tenant_id`, yet the first query may read only a small set. The second query may match most of tenant 42's data. Index `(tenant_id, created_at)` can be clearly beneficial for the first query; the optimizer may choose to scan a large span or pick another access method for the second query depending on actual cost.

For a `status` column with few values:

- A standalone `status` index can help for a rare status like `FAILED`.
- A standalone `status` index may be unattractive for a status covering nearly the entire table like `PAID`.
- Index `(status, created_at)` can help when queries always filter status and bound time.
- If a query retrieves only a few columns, an appropriate covering index can reduce clustered index lookups; in exchange, the index is larger and increases write cost.

There is no single composite index order right for all queries. List your important queries, identify equality columns, range columns, join columns, order/group columns, and returned columns, then test candidate indexes with `EXPLAIN` and real measurements.

## 9. Distinguishing single-column statistics from multi-column correlation

Suppose a system has business rules causing `FAILED` status to appear only within a certain group of tenants. Inspecting each column individually, you might see:

- `status` has 4 values and `FAILED` is very rare.
- `tenant_id` has thousands of values and tenant 42 is very large.

Yet the combined query `status = 'FAILED' AND tenant_id = 42` can have a vastly different distribution than assuming independence between the two columns. Single-column histograms cannot fully represent this correlation.

In that scenario:

1. Measure actual row counts for key predicate combinations.
2. Check the cardinality of each composite index prefix.
3. Inspect estimates and `actual rows` in `EXPLAIN ANALYZE`.
4. Test composite indexes ordered to fit the workload.
5. Monitor plans after data grows or distribution shifts.

Example profiling joint distribution:

~~~sql
SELECT
    tenant_id,
    status,
    COUNT(*) AS rows_for_combination
FROM orders
GROUP BY tenant_id, status
ORDER BY rows_for_combination DESC
LIMIT 30;
~~~

This query helps spot common or rare combinations. On large tables, `GROUP BY` can be resource-intensive; run it in an analytics environment or bound it by a time range if appropriate.

## 10. Investigation workflow when the optimizer chooses an unexpected index

When a query slows down or its plan changes, proceed in order:

1. **Identify a representative query.** Record SQL, parameters, execution frequency, latency, and result row count. Queries with identical structure but different parameters can have vastly different selectivity.
2. **Inspect current indexes.** Use `SHOW INDEX` to check columns, column order, cardinality, and existing indexes.
3. **Measure data distribution.** Use `GROUP BY`, `COUNT(DISTINCT)`, and group counts to identify rare values, dominant values, `NULL`s, and skewed tenants.
4. **Read the plan.** Use `EXPLAIN` to inspect `key`, `type`, `rows`, and `filtered`. Use `EXPLAIN ANALYZE` on appropriate read queries to compare estimated rows against actual rows.
5. **Check statistics freshness.** Consider `ANALYZE TABLE` when index statistics are stale; create or update histograms if skew exists on eligible columns.
6. **Test workload-aligned indexes.** Create candidate indexes in a test environment or via an approved change process. Evaluate both read queries and write costs.
7. **Re-measure and monitor.** Compare timings, rows read, plans, CPU/I/O load, and impact on other queries. Drop redundant indexes via your schema management process once proven unnecessary.

Do not force the optimizer to use an index just because current `EXPLAIN` did not pick the index you expected. First verify data, statistics, distribution, and cost. Index hints can be useful in measured edge cases, yet can also lock the system into a bad plan as data changes.

## 11. Common reasoning errors

**High cardinality means every query is fast.** High cardinality shows many distinct values, yet a specific predicate can still match many rows. Measure filter selectivity for actual values.

**A column with only a few values never needs an index.** A rare value in a low-cardinality column can still be found very quickly via an index. Per-value distribution and query patterns matter more than conclusions drawn from distinct counts alone.

**The optimizer ignoring an index means the index is broken.** A table scan may simply be cheaper, predicates may not match the index prefix, statistics may be skewed, or the query returns too many rows. Read the full plan.

**Cardinality in SHOW INDEX is an exact number.** It is an estimate based on InnoDB index statistics. Use `ANALYZE TABLE` to refresh and compare with actual measurements when needed.

**Histograms replace indexes.** Histograms are statistics helping the optimizer estimate distribution; they create no data access path. To access data fast, a query still needs an appropriate access path.

**Single-column histograms describe all combinations.** Single-column histograms do not capture correlations across columns. Examine joint distributions and composite indexes.

**The more columns in a composite index, the better.** Wide indexes inflate disk usage and write costs. Pick columns based on real queries, predicate types, and leftmost prefix usability.

**A single EXPLAIN ANALYZE proves a query is always fast.** Timings depend on caches, server load, data size, and parameters. Measure multiple times under near-production conditions.

## 12. Checklist for evaluating selectivity and data skew

Before adding, dropping, or altering an index, answer:

- Does cardinality refer to a single column or which prefix of a composite index?
- Are `distinct/total` and `matching/total` ratios interpreted in the right direction?
- Are values in the column uniformly distributed or heavily skewed?
- Is the value the query actually searches common or rare?
- Does the column have many `NULL`s or a few tenants dominating the data?
- Does `Cardinality` in `SHOW INDEX` still represent current data?
- How many rows does `EXPLAIN` estimate, and how many does `EXPLAIN ANALYZE` actually read?
- Could a histogram improve estimates for a skewed column?
- Does the query filter on correlated columns that single-column histograms cannot describe?
- Does the composite index follow proper leftmost prefix, equality, and range ordering?
- Do read gains outweigh the index's storage and write costs?

When evaluating indexes, start from the queries and the data distribution those queries encounter. Cardinality reveals diversity, selectivity reveals narrowing power, and histograms help describe frequency. Combining this information with `EXPLAIN`, real measurements, and workload profiling helps you understand why MySQL picks an access path and design indexes that hold up as data grows or skews.
