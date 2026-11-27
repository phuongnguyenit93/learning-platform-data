# Histograms, Distribution Types, and Optimizer Usage Conditions

This lesson belongs to the **Optimizer and Statistics** chapter of the **DATABASE_MYSQL** module. The module aims to build mastery of MySQL from table design, data types, keys, and SQL queries through indexes, transactions, concurrency control, execution plan reading, query optimization, privileges, backups, and operational troubleshooting for relational databases. Histograms are statistics describing the value distribution of a column, helping the optimizer estimate matching row counts more accurately when standard index statistics lack sufficient detail.

After this lesson, you will be able to explain how histograms help the optimizer, distinguish singleton and equi-height histograms, create and drop histograms via `ANALYZE TABLE`, read metadata in `INFORMATION_SCHEMA.COLUMN_STATISTICS`, identify predicates eligible to use histograms, understand sampling and staleness limitations, and verify impact using `EXPLAIN` and `EXPLAIN ANALYZE`.

## 1. What Problem Do Histograms Solve?

MySQL uses a cost-based optimizer to choose how to execute a query. To compare costs, the optimizer must estimate how many rows each filter predicate will return.

For example, an `orders` table with 1,000,000 rows and a `status` column with this distribution:

| status Value | Row Count | Share |
|---|---:|---:|
| COMPLETED | 900,000 | 90% |
| PENDING | 80,000 | 8% |
| CANCELLED | 20,000 | 2% |

The following two queries share the same structure yet have different selectivity:

~~~sql
SELECT *
FROM orders
WHERE status = 'COMPLETED';

SELECT *
FROM orders
WHERE status = 'CANCELLED';
~~~

If the optimizer only knows the number of distinct values without knowing the actual distribution, it may estimate both predicates using a simple distribution assumption. That assumption fails to reflect heavily skewed data like the example above.

Histograms provide frequency or value-distribution data so the optimizer can estimate selectivity (the fraction of rows passing a filter condition). In this example, a histogram can inform the optimizer that `status = 'CANCELLED'` selects only about 2% of rows.

Better estimates help the optimizer:

- Choose an appropriate `JOIN` order.
- Estimate intermediate row counts after each predicate.
- Evaluate the cost of table scans, index access, or other alternatives.
- Avoid picking plans based on flawed distribution assumptions.

Histograms do not filter data in place of `WHERE`, do not create indexes, and do not automatically make queries faster. They supply statistics so the optimizer can predict row counts and pick a plan.

## 2. How Do Histograms Differ from Index Statistics?

MySQL maintains multiple kinds of statistics. Distinguish index cardinality statistics from column histograms.

| Statistic Type | Description | Typical Purpose |
|---|---|---|
| Index cardinality | Estimated distinct values in an index or index prefix | Estimate index selectivity and access cost |
| Histogram | Describes a column's value distribution across buckets | Estimate fraction of rows matching comparisons with constants |
| Actual row count | Actual rows returned when executing the query | Compare against optimizer estimates |

Index statistics roughly answer "how many distinct values exist?" Histograms answer in greater detail "how are the values distributed?"

For example, two columns both have 10 distinct values yet different distributions:

- Column A: each value accounts for roughly 10%.
- Column B: one value accounts for 91%, and the remaining nine share 9%.

Knowing only that cardinality is 10 does not capture this difference. A histogram stores frequency details so the optimizer can estimate better.

Histograms are typically useful for unindexed columns. If a column is indexed, the optimizer can use index dives or the range optimizer to estimate; in some cases, index-based estimates are better than histograms.

## 3. What Is a Bucket?

A histogram divides a value distribution into buckets. Each bucket represents either a single value or a value range, depending on the histogram type.

MySQL supports two types:

1. **Singleton histogram:** each bucket represents a single distinct value.
2. **Equi-height histogram:** each bucket represents a range of values.

Which type is chosen depends on the number of distinct values (NDV) and the requested bucket count.

### Singleton Histogram

If the number of distinct values is less than or equal to the specified bucket count, MySQL builds a singleton histogram.

For example, a `status` column with three values:

- `CANCELLED`
- `COMPLETED`
- `PENDING`

With 16 buckets requested, the histogram can use three singleton buckets, one per value.

Each singleton bucket holds:

- The bucket's value.
- The cumulative frequency up to that value.

Illustrative example:

~~~json
{
  "histogram-type": "singleton",
  "buckets": [
    ["CANCELLED", 0.02],
    ["COMPLETED", 0.92],
    ["PENDING", 1.00]
  ],
  "null-values": 0.0
}
~~~

The percentages in this example illustrate data with 2% `CANCELLED`, 90% `COMPLETED`, and 8% `PENDING`. Cumulative frequency means:

- Up to `CANCELLED`: 2%.
- Up to `COMPLETED`: 92%.
- Up to `PENDING`: 100%.

Value ordering follows the comparison rules of the corresponding data type and collation.

Singleton histograms fit columns with low or moderate numbers of distinct values, such as statuses, transaction types, or category codes.

### Equi-Height Histogram

If the number of distinct values exceeds the specified bucket count, MySQL builds an equi-height histogram.

Each bucket represents a value interval containing:

- Lower bound value (inclusive).
- Upper bound value (inclusive).
- Cumulative frequency up to the upper bound.
- Number of distinct values within the range.

Intervals are constructed so each bucket contains roughly the same fraction of rows; because distributions can be skewed, distinct value counts across buckets do not have to be equal.

Illustrative example:

~~~json
{
  "histogram-type": "equi-height",
  "buckets": [
    [1, 100, 0.25, 100],
    [101, 250, 0.50, 150],
    [251, 500, 0.75, 250],
    [501, 1000, 1.00, 500]
  ]
}
~~~

The buckets above only illustrate the structure. Actual histograms may have different bounds and distinct counts.

Equi-height histograms are useful for columns with many distinct values, such as `amount`, `created_at`, `score`, or `customer_age`.

### Comparing Singleton and Equi-Height

| Criterion | Singleton | Equi-Height |
|---|---|---|
| Represents | A specific value | A range of values |
| Formation condition | NDV less than or equal to bucket count | NDV greater than bucket count |
| Bucket contents | Value and cumulative frequency | Lower bound, upper bound, cumulative frequency, distinct count |
| Typical examples | status, category with few values | amount, timestamp, score with many values |

NDV stands for number of distinct values.

## 4. What Information Does a Histogram Store?

Histograms are persisted in the data dictionary. Users inspect them via the `INFORMATION_SCHEMA.COLUMN_STATISTICS` view.

Key fields in the histogram JSON:

| Field | Meaning |
|---|---|
| buckets | List of buckets and distribution data |
| null-values | Fraction of SQL NULL values |
| last-updated | Timestamp when the histogram was created/updated, in UTC |
| sampling-rate | Fraction of data read to build the histogram |
| histogram-type | `singleton` or `equi-height` |
| number-of-buckets-specified | Requested bucket count at creation |
| data-type | Data type represented in the histogram |
| collation-id | Collation ID, primarily relevant for string data |
| auto-update | Whether automatic updating is enabled for the histogram |

Encountered `data-type` values include `int`, `uint`, `double`, `decimal`, `datetime`, and `string`. `string` covers both character strings and binary strings.

You can query metadata:

~~~sql
SELECT
    SCHEMA_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    HISTOGRAM
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE();
~~~

To extract commonly used attributes:

~~~sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    HISTOGRAM->>'$."histogram-type"' AS histogram_type,
    JSON_LENGTH(HISTOGRAM->>'$."buckets"') AS bucket_count,
    HISTOGRAM->>'$."sampling-rate"' AS sampling_rate,
    HISTOGRAM->>'$."null-values"' AS null_fraction,
    HISTOGRAM->>'$."last-updated"' AS last_updated
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
ORDER BY TABLE_NAME, COLUMN_NAME;
~~~

`HISTOGRAM` is JSON. Use JSON extraction to read specific properties instead of parsing the entire JSON manually by eye.

## 5. Creating Histograms with ANALYZE TABLE

Use the `UPDATE HISTOGRAM` clause:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status;
~~~

If no bucket count is specified, MySQL defaults to 100 buckets.

Specify the bucket count:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status WITH 16 BUCKETS;
~~~

You can create histograms for multiple columns in the same table:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status, amount, created_at
WITH 32 BUCKETS;
~~~

A single `UPDATE HISTOGRAM` statement applies to one table only. Valid bucket counts range from 1 to 1024.

If `status` has 3 distinct values and 16 buckets are requested, MySQL creates a singleton histogram with three buckets. If `amount` has 1,000 distinct values and 16 buckets are requested, MySQL creates an equi-height histogram with up to 16 buckets.

Creating histograms is separate from updating key distributions. The statement:

~~~sql
ANALYZE TABLE orders;
~~~

without a `HISTOGRAM` clause refreshes index/key distribution statistics; existing histograms remain intact.

## 6. Dropping Histograms

Use `DROP HISTOGRAM`:

~~~sql
ANALYZE TABLE orders
DROP HISTOGRAM ON status;
~~~

Drop histograms across multiple columns:

~~~sql
ANALYZE TABLE orders
DROP HISTOGRAM ON status, amount, created_at;
~~~

This command removes histogram statistics for the listed columns. Histograms on other columns are unaffected.

Dropping a histogram does not delete table data, drop indexes, or alter the schema.

You can verify:

~~~sql
SELECT
    TABLE_NAME,
    COLUMN_NAME
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'orders';
~~~

Once the histogram for the dropped column is gone, that column no longer appears in the result.

## 7. Predicates Eligible to Use Histograms

MySQL uses histograms to estimate rows satisfying predicates comparing a column value with a constant.

Eligible predicate forms include:

~~~sql
col_name = constant
col_name <> constant
col_name != constant
col_name > constant
col_name < constant
col_name >= constant
col_name <= constant
col_name IS NULL
col_name IS NOT NULL
col_name BETWEEN constant AND constant
col_name NOT BETWEEN constant AND constant
col_name IN (constant, ...)
col_name NOT IN (constant, ...)
~~~

Examples:

~~~sql
SELECT *
FROM orders
WHERE status = 'CANCELLED';

SELECT *
FROM orders
WHERE amount BETWEEN 100.00 AND 300.00;

SELECT *
FROM orders
WHERE status IN ('PENDING', 'CANCELLED');

SELECT *
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at < '2026-02-01';
~~~

Constant comparisons can also use constant expressions:

~~~sql
SELECT *
FROM orders
WHERE amount < ABS(-300);
~~~

Note: histograms are not relational statistics between two columns. A predicate such as:

~~~sql
orders.status = customers.preferred_status
~~~

is a comparison between two columns, not a column-to-constant comparison listed above.

Single-column histograms also do not describe correlations across columns. If `status` and `region` have interdependent distributions, two separate histograms cannot fully represent that correlation.

## 8. How Does the Optimizer Use Histograms?

Histograms feed into cardinality and selectivity estimation, which in turn influences cost evaluation.

Example:

~~~sql
SELECT *
FROM orders
WHERE status = 'CANCELLED';
~~~

If the histogram indicates roughly 2% of rows have `status` `CANCELLED`, the optimizer can estimate matching rows close to that fraction.

In a `JOIN` query:

~~~sql
SELECT
    o.order_id,
    o.customer_id,
    c.customer_name
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status = 'CANCELLED';
~~~

The estimated row count of `orders` after `WHERE` can affect `JOIN` order and the costs of table-combination alternatives.

Histograms can help the optimizer recognize when a condition is highly selective or weakly selective, even if that column lacks an index.

However:

- Histograms do not create an index access path.
- Histograms do not change query results.
- Histograms do not guarantee the optimizer chooses a good plan in every scenario.
- Histograms do not fix every error caused by multi-column correlation.
- Stale histograms can produce inaccurate estimates.

## 9. Histograms and the Range Optimizer

MySQL prefers row estimates from the range optimizer when the range optimizer applies. In that case, the optimizer does not replace range estimates with a histogram.

For indexed columns, index dives can provide better estimates for certain equality comparisons.

Consequently, histograms are primarily useful for unindexed columns or cases where supplemental distribution data improves estimation.

Do not create histograms on every column. Start from queries exhibiting a clear gap between estimated rows and actual rows, especially on heavily skewed columns lacking an appropriate index.

## 10. Histograms Do Not Replace Indexes

Suppose `status` has no index:

~~~sql
SELECT *
FROM orders
WHERE status = 'CANCELLED';
~~~

A histogram can help the optimizer estimate roughly 2% of rows match. Yet without an appropriate index, MySQL may still have to scan the entire table to find the matching rows.

If you create an index:

~~~sql
CREATE INDEX idx_orders_status
ON orders (status);
~~~

The optimizer gains an access path. Index statistics or index dives can supply estimates, and the histogram may not even be used.

Weigh the costs:

| Option | Benefit | Cost |
|---|---|---|
| Histogram | Adds distribution info; no per-DML maintenance overhead | Must be refreshed as needed; can go stale |
| Index | Enables direct access to matching rows | Consumes disk space and maintenance cost on INSERT/UPDATE/DELETE |
| Both | Can supply supplemental info in suitable cases | Increases administrative overhead; optimizer might not use the histogram |

Histograms are built or refreshed on demand, so they incur no maintenance overhead per data modification like indexes do. In exchange, histograms can gradually become outdated as data distributions evolve.

## 11. Sampling and Histogram Accuracy

To build a histogram, MySQL must read the column's data. If the data to read exceeds the histogram memory limit, MySQL samples instead of reading everything.

The `histogram_generation_max_mem_size` variable controls the maximum memory allocated for histogram generation.

Check:

~~~sql
SELECT
    @@GLOBAL.histogram_generation_max_mem_size,
    @@SESSION.histogram_generation_max_mem_size;
~~~

When the estimated data volume exceeds this limit, MySQL uses `SYSTEM` sampling, a page-level sampling method spread across the table.

InnoDB provides its own sampling support for InnoDB data to avoid a full table scan when building histograms on large tables.

In histogram metadata, `sampling-rate` shows the fraction of data read:

- `1.0`: read all data, no sampling.
- `0.5`: roughly half the data was sampled.
- `0.1`: roughly one-tenth of the data was sampled.

This is the sampling rate, not the fraction of rows matching `WHERE`.

Example reading `sampling-rate`:

~~~sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    HISTOGRAM->>'$."sampling-rate"' AS sampling_rate
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'orders';
~~~

If a rare but important value does not appear in the sample, the histogram may misrepresent its distribution. When high accuracy is needed, inspect `sampling-rate`, review bucket counts, and consider reading full data or user-defined JSON histograms.

Do not set `histogram_generation_max_mem_size` too low on large tables just to build histograms faster. Aggressive sampling can drop information about rare values or special distribution regions.

## 12. Choosing the Bucket Count

Bucket count controls histogram granularity.

Valid values: 1 to 1024. If omitted, the default is 100.

General guidelines:

- Columns with few distinct values: a singleton histogram can store each value as its own bucket.
- Columns with many distinct values: an equi-height histogram partitions into intervals.
- More buckets can represent finer distribution detail.
- More buckets also enlarge metadata and do not guarantee better estimates if the sampled data is unrepresentative.
- There is no single optimal number for every column.

Example:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status
WITH 16 BUCKETS;

ANALYZE TABLE orders
UPDATE HISTOGRAM ON amount
WITH 64 BUCKETS;
~~~

Different bucket counts can be used per column via separate statements.

Compare plans and estimation errors before and after. Do not blindly set 1024 buckets for every column.

## 13. Histograms Can Become Stale

Histograms are stored persistently in the data dictionary. When created in `MANUAL UPDATE` mode (the default if unspecified), a histogram does not automatically refresh after each `INSERT`, `UPDATE`, or `DELETE`.

Example:

1. When the histogram is created, 90% of orders are `COMPLETED`.
2. An import batch alters the data so `PENDING` rises to 40%.
3. The histogram still reflects the old distribution until refreshed.
4. The optimizer can misestimate row counts for `status = 'PENDING'`.

Refresh it:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status
WITH 16 BUCKETS;
~~~

Inspect `last-updated` and `sampling-rate` to determine what point in time the histogram reflects and how much data was read to build it.

### AUTO UPDATE and MANUAL UPDATE

MySQL 9.7 supports `AUTO UPDATE` and `MANUAL UPDATE` options when managing histograms.

Enable automatic updates:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status
WITH 16 BUCKETS AUTO UPDATE;
~~~

`AUTO UPDATE` mode allows the histogram to be updated whenever `ANALYZE TABLE` runs on that table and when the InnoDB background statistics thread recalculates the table's persistent statistics.

Specify manual updates:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status
WITH 16 BUCKETS MANUAL UPDATE;
~~~

`MANUAL UPDATE` is the default if no option is specified. The histogram is not automatically refreshed under the `AUTO UPDATE` mechanism.

Check the `auto-update` property in histogram JSON:

~~~sql
SELECT
    COLUMN_NAME,
    HISTOGRAM->>'$."auto-update"' AS auto_update,
    HISTOGRAM->>'$."last-updated"' AS last_updated
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'orders';
~~~

`AUTO UPDATE` does not mean MySQL re-scans the histogram after every DML statement. It ties into documented statistics update events; inspect `last-updated` to verify actual update times.

### Notes When Running ANALYZE TABLE in Production

- `ANALYZE TABLE` requires `SELECT` and `INSERT` privileges on the table.
- During analysis, MySQL takes a read lock on InnoDB and MyISAM tables. Evaluate scheduling on tables with heavy write traffic.
- By default, `ANALYZE TABLE` is written to the binary log so replicas receive it. Use `LOCAL` or `NO_WRITE_TO_BINLOG` only when operational intent explicitly requires omitting it from the binary log.
- Histogram management syntax accepts only one table name per statement.
- `ANALYZE TABLE` does not run on views.

Example running on source and allowing default binary logging:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status WITH 16 BUCKETS;
~~~

If there is a clear reason to skip binary logging:

~~~sql
ANALYZE LOCAL TABLE orders
UPDATE HISTOGRAM ON status WITH 16 BUCKETS;
~~~

## 14. Cases Where Histograms Cannot Be Created

MySQL enforces the following restrictions:

- Cannot create histograms on `JSON` columns.
- Cannot create histograms on geometry/spatial columns.
- Not supported on encrypted tables.
- Not supported on `TEMPORARY` tables.
- Cannot create histograms on columns covered by a single-column unique index.
- Can create histograms on stored generated columns and virtual generated columns.

If an `UPDATE HISTOGRAM` statement lists multiple columns, MySQL attempts the valid ones and returns diagnostics for nonexistent columns or unsupported data types.

For example, if a table has `status`, `payload_json`, and `location_geom`:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status, payload_json, location_geom
WITH 16 BUCKETS;
~~~

A histogram may be created for `status`, while `payload_json` and `location_geom` are rejected due to their data types. Read the `ANALYZE TABLE` output rather than assuming the whole column list succeeded.

### Histograms Affected by DDL

- `DROP TABLE` removes histograms for the table's columns.
- `DROP DATABASE` removes histograms for all tables in the dropped database.
- `RENAME TABLE` preserves histograms and associates them with the new table name.
- `ALTER TABLE` dropping or modifying a column removes that column's histogram.
- `ALTER TABLE ... CONVERT TO CHARACTER SET` removes histograms on affected character columns; non-character column histograms are preserved.

After schema migrations, re-check `INFORMATION_SCHEMA.COLUMN_STATISTICS` if queries rely on histograms.

## 15. Verifying Impact with EXPLAIN

Histograms affect optimizer estimates. To verify, compare plans before and after creating a histogram.

Example:

~~~sql
EXPLAIN
SELECT *
FROM orders
WHERE status = 'CANCELLED';
~~~

You can use JSON format:

~~~sql
EXPLAIN FORMAT=JSON
SELECT *
FROM orders
WHERE status = 'CANCELLED';
~~~

Inspect fields related to:

- estimated rows.
- `filtered`.
- `access_type`.
- `possible_keys` and `key`.
- cost estimates in the JSON plan.

A histogram can change the `filtered` estimate. However, if the column lacks an index, the access type may remain `ALL` because histograms do not create new access paths.

### EXPLAIN ANALYZE

`EXPLAIN ANALYZE` executes the `SELECT` and adds iterator, timing, and actual row counts.

~~~sql
EXPLAIN ANALYZE
SELECT *
FROM orders
WHERE status = 'CANCELLED';
~~~

Compare:

- Estimated rows: row count predicted by the optimizer.
- Actual rows: actual rows returned by the iterator.
- Actual time: execution time.
- Loops: number of times the iterator was invoked.

`EXPLAIN ANALYZE` actually runs the query. Use it only on appropriate `SELECT` statements and data safe to read; do not treat it as a parse-only command.

A good plan usually has estimates close to actual rows, though you should still inspect total time, loop counts, I/O, and overall plan cost.

## 16. Hands-On Practice: Creating Singleton and Equi-Height Histograms

This lab generates skewed data to observe both histogram types.

### Step 1: Create Database and Table

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_histogram_lab;
USE mysql_histogram_lab;

CREATE TABLE orders (
    order_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    created_at DATE NOT NULL
) ENGINE=InnoDB;
~~~

### Step 2: Generate 1,000 Rows with Skewed Distribution

~~~sql
INSERT INTO orders (status, amount, created_at)
SELECT
    CASE
        WHEN n <= 900 THEN 'COMPLETED'
        WHEN n <= 980 THEN 'PENDING'
        ELSE 'CANCELLED'
    END,
    CAST(n * 1.37 AS DECIMAL(12,2)),
    DATE_ADD('2026-01-01', INTERVAL MOD(n, 90) DAY)
FROM (
    SELECT
        d0.n + 10 * d1.n + 100 * d2.n + 1 AS n
    FROM
        (SELECT 0 AS n UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL
         SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL
         SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9) AS d0
    CROSS JOIN
        (SELECT 0 AS n UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL
         SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL
         SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9) AS d1
    CROSS JOIN
        (SELECT 0 AS n UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL
         SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL
         SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9) AS d2
) AS numbers;
~~~

Resulting data:

- 900 `COMPLETED` rows.
- 80 `PENDING` rows.
- 20 `CANCELLED` rows.

The `status` column has three distinct values. The `amount` column has many distinct values because it is generated from `n` multiplied by `1.37`.

### Step 3: Verify Actual Distribution

~~~sql
SELECT
    status,
    COUNT(*) AS row_count,
    COUNT(*) / (SELECT COUNT(*) FROM orders) AS fraction
FROM orders
GROUP BY status
ORDER BY status;
~~~

Expected output:

| status | row_count | fraction |
|---|---:|---:|
| CANCELLED | 20 | 0.02 |
| COMPLETED | 900 | 0.90 |
| PENDING | 80 | 0.08 |

### Step 4: Inspect Plan Before Creating a Histogram

~~~sql
EXPLAIN
SELECT *
FROM orders
WHERE status = 'CANCELLED';
~~~

Record `rows` and `filtered` in the output. Because the table only has primary key `order_id`, `status` is unindexed.

### Step 5: Create Histogram for status

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status
WITH 16 BUCKETS;
~~~

Because `status` has three distinct values and 16 buckets are requested, the histogram is built as `singleton`.

### Step 6: Create Histogram for amount

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON amount
WITH 16 BUCKETS;
~~~

Because `amount` has more than 16 distinct values, the histogram is built as `equi-height`.

### Step 7: Inspect Metadata

~~~sql
SELECT
    COLUMN_NAME,
    HISTOGRAM->>'$."histogram-type"' AS histogram_type,
    JSON_LENGTH(HISTOGRAM->>'$."buckets"') AS bucket_count,
    HISTOGRAM->>'$."sampling-rate"' AS sampling_rate,
    HISTOGRAM->>'$."null-values"' AS null_fraction
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY COLUMN_NAME;
~~~

Confirm `status` is `singleton` and `amount` is `equi-height`. Actual bucket count can be smaller than requested for singleton histograms.

### Step 8: Compare Plan After Histogram

~~~sql
EXPLAIN
SELECT *
FROM orders
WHERE status = 'CANCELLED';

EXPLAIN ANALYZE
SELECT *
FROM orders
WHERE status = 'CANCELLED';
~~~

Compare estimated `rows`/`filtered` against actual rows. Do not expect the optimizer to pick an index because `status` has no index. The goal is to observe how histograms improve selectivity estimates.

### Step 9: Test a Range Predicate

~~~sql
EXPLAIN
SELECT *
FROM orders
WHERE amount BETWEEN 200.00 AND 300.00;

EXPLAIN ANALYZE
SELECT *
FROM orders
WHERE amount BETWEEN 200.00 AND 300.00;
~~~

`amount` has an equi-height histogram, so the optimizer can use its distribution information for the `BETWEEN` predicate when conditions apply.

### Step 10: Test a Stale Histogram

Modify part of the data:

~~~sql
UPDATE orders
SET status = 'PENDING'
WHERE order_id BETWEEN 1 AND 300;
~~~

The current `status` distribution has shifted significantly, yet the histogram is in `MANUAL UPDATE` mode and was not rebuilt automatically by the `UPDATE`.

Check the timestamp:

~~~sql
SELECT
    COLUMN_NAME,
    HISTOGRAM->>'$."last-updated"' AS last_updated
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'orders'
  AND COLUMN_NAME = 'status';
~~~

Update the histogram:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status
WITH 16 BUCKETS;
~~~

Re-run `EXPLAIN` and observe the estimates.

### Step 11: Drop Histograms and Clean Up

~~~sql
ANALYZE TABLE orders
DROP HISTOGRAM ON status, amount;

DROP DATABASE mysql_histogram_lab;
~~~

Only run `DROP DATABASE` on the lab database you just created.

## 17. Workflow When the Optimizer Misestimates

When you see an unreasonable plan, do not create histograms immediately. Follow this sequence:

1. Identify the problematic query and collect `EXPLAIN` or `EXPLAIN ANALYZE`.
2. Compare estimated rows with actual rows at the iterator with the largest discrepancy.
3. Determine whether the filter condition compares a column against a constant and falls into a histogram-supported form.
4. Check whether the column is indexed; the range optimizer or index dives may already supply better estimates.
5. Check actual data distribution using `GROUP BY`, `COUNT`, and appropriate summary queries.
6. Check existing histograms, histogram type, bucket count, `sampling-rate`, and `last-updated`.
7. If a histogram is missing or stale, refresh it via `ANALYZE TABLE ... UPDATE HISTOGRAM`.
8. Re-run `EXPLAIN`/`EXPLAIN ANALYZE` on the exact same query and data.
9. Compare plan, estimated rows, actual rows, and timing.
10. If histograms do not help, inspect indexes, `JOIN` conditions, column correlations, data types, and other optimizer choices.

Do not use `FORCE INDEX` just because one `EXPLAIN` shows the optimizer chose a table scan. Understand selectivity, table size, matching row fraction, and access cost before forcing a plan.

## 18. Common Mistakes

| Symptom | Cause | Remedy |
|---|---|---|
| Created histogram yet query is no faster | Histograms only improve estimates, not create indexes | Check access path and consider an index if needed |
| Optimizer ignores histogram | Predicate doesn't compare column to constant, or range optimizer estimates take precedence | Inspect predicate form and plan |
| Histogram not created for column | JSON/geometry type, encrypted/TEMPORARY table, or single-column unique index | Review support limitations |
| Histogram has fewer buckets than requested | Low NDV led to singleton histogram | Check `histogram-type` and actual bucket count |
| Histogram wrong after data import | `MANUAL UPDATE` was not refreshed | Run `ANALYZE TABLE UPDATE HISTOGRAM` |
| Low sampling-rate | Memory limit forced MySQL to sample | Review `histogram_generation_max_mem_size` and sample representativeness |
| Histogram misses column correlation | Histograms are single-column statistics | Inspect correlation and query structure; do not expect multi-column histograms |
| EXPLAIN rows still diverge from actuals | Sampling error, skewed data, or optimizer uses another estimate source | Compare `sampling-rate`, range estimates, and actual rows |
| ANALYZE TABLE returns warning for one column | Invalid column or unsupported type | Read `Msg_type`/`Msg_text` and handle per column |
| Histogram disappears after ALTER TABLE | Column modified/dropped or charset converted | Recreate histogram after migration if needed |
| Histogram JSON hard to read | Reading entire JSON instead of extracting fields | Use JSON extraction on `COLUMN_STATISTICS` |

## 19. Histogram Management Checklist

- [ ] Identified queries with significant cardinality estimation discrepancies.
- [ ] Distinguished index cardinality from histograms.
- [ ] Checked actual data distributions.
- [ ] Verified histograms are eligible for the predicates in use.
- [ ] Checked whether the column is indexed and whether the range optimizer supplies another estimate.
- [ ] Chosen a bucket count between 1 and 1024.
- [ ] Understood singleton vs. equi-height histograms.
- [ ] Checked `sampling-rate` and `last-updated`.
- [ ] Accounted for `histogram_generation_max_mem_size` limits.
- [ ] Recognized histograms do not support JSON, geometry, encrypted tables, or temporary tables.
- [ ] Checked whether the column has a single-column unique index.
- [ ] Deliberately chosen `MANUAL UPDATE` or `AUTO UPDATE`.
- [ ] Refreshed histograms after imports or major distribution shifts when using manual mode.
- [ ] Used `EXPLAIN` to verify estimates.
- [ ] Used `EXPLAIN ANALYZE` to check actual rows when safe.
- [ ] Evaluated indexes and multi-column correlations if histograms are insufficient.
- [ ] Re-verified histograms after schema migrations.

## 20. Key Principles to Remember

1. Histograms describe a column's value distribution so the optimizer can estimate selectivity.
2. Histograms are not indexes and do not create new access paths.
3. Singleton histograms use one bucket per value; equi-height histograms use buckets representing intervals.
4. Histogram type depends on the number of distinct values relative to the requested bucket count.
5. Histograms are stored as JSON in the data dictionary and readable via `INFORMATION_SCHEMA.COLUMN_STATISTICS`.
6. `ANALYZE TABLE UPDATE HISTOGRAM` creates or updates histograms; `DROP HISTOGRAM` removes them.
7. Valid bucket counts are 1 to 1024, defaulting to 100.
8. The optimizer uses histograms for supported column-to-constant comparison predicates.
9. The range optimizer and index dives can take precedence over histograms.
10. Histograms are mainly useful for unindexed columns or when distribution details improve estimation.
11. A low `sampling-rate` can cause histograms to miss rare values.
12. Manual histograms can become stale after data changes; refresh them according to workload.
13. Histograms are single-column statistics and do not fully describe correlations across multiple columns.
14. Use `EXPLAIN` and `EXPLAIN ANALYZE` to compare estimates with actual row counts.
15. Choose histograms, indexes, or other optimizations based on evidence from real queries.

## Official References

The behaviors in this lesson are cross-checked against the **MySQL 9.7 Reference Manual** as of **2026-11-19**:

1. [Optimizer Statistics](https://dev.mysql.com/doc/refman/9.7/en/optimizer-statistics.html): histogram structure, singleton/equi-height, selectivity, and optimizer usage conditions.
2. [ANALYZE TABLE Statement](https://dev.mysql.com/doc/refman/9.7/en/analyze-table.html): `UPDATE HISTOGRAM`, `DROP HISTOGRAM`, bucket counts, `AUTO UPDATE`/`MANUAL UPDATE`, and sampling.
3. [EXPLAIN Statement](https://dev.mysql.com/doc/refman/9.7/en/explain.html): reading plans, `EXPLAIN ANALYZE`, and comparing estimates with actuals.
4. [Optimizing SELECT Statements](https://dev.mysql.com/doc/refman/9.7/en/select-optimization.html): keeping statistics current and slow-query investigation workflows.
5. [Optimizer-Related Issues](https://dev.mysql.com/doc/refman/9.7/en/optimizer-issues.html): tools for when the cost-based optimizer picks a suboptimal plan.
