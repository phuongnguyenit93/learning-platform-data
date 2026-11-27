# Data Skew, Column Correlation, and Estimation Errors

The MySQL optimizer must estimate how many rows will flow through each query step before choosing indexes, `JOIN` order, filtering strategies, and table-joining methods. These estimates rely on table statistics, index statistics, histograms, and optimizer rules. When data has a skewed distribution or columns are correlated, estimates can diverge substantially from actual row counts.

A plan built on bad estimates may pick an unsuitable `JOIN` order, probe an inner table excessively, read too many rows, or use an inefficient index. The fix is to measure actual row counts, inspect statistics quality, update histograms where appropriate, design composite indexes for conditions that commonly appear together, and verify again using `EXPLAIN ANALYZE`.

## 1. Why Does the Optimizer Need Statistics?

SQL describes the desired result, while the optimizer decides how to execute it. For multi-table queries, many different `JOIN` orders and access paths may exist. The optimizer estimates cost based on rows to read, rows remaining after filter predicates, index/table access costs, and operations like sorting or materialization.

Example:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL,
    customer_name VARCHAR(150) NOT NULL,
    region_code CHAR(2) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer (customer_id),
    KEY idx_orders_status (status)
) ENGINE=InnoDB;

SELECT c.customer_id, c.customer_name, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'failed'
  AND c.region_code = 'VN';
```

The optimizer must estimate how many `failed` orders exist, how many customers are in `VN`, how many orders each customer has, and which order minimizes total work. If it thinks `failed` represents 40% of the table when in reality it is only 0.1%, the chosen join order may be suboptimal.

Statistics are not exact replacements for query execution. They are summaries enabling the optimizer to predict cost without counting the entire table before every SQL statement.

## 2. Concepts to Distinguish

| Concept | Meaning | Example |
| --- | --- | --- |
| Cardinality | Number of distinct values or rows depending on statistics context | A `status` column has 4 distinct values |
| Selectivity | Fraction of rows satisfying a condition | `status = 'failed'` matches only 0.1% of rows |
| Data skew | Uneven value distribution | 99% of records have `status = 'active'` |
| Correlation | Distribution of one column depends on another column's value | Most accounts in `VN` use the `free` plan |
| Estimate error | Gap between optimizer-predicted rows and actual rows | Predicted 100,000 rows while actual is only 50 |

High cardinality does not guarantee a predicate is always selective; you must also consider the specific value and distribution. A column with 2 values can be heavily skewed (99.9%/0.1%) or balanced (50%/50%). Simple cardinality statistics alone do not distinguish these two cases.

## 3. Data Skew: Uneven Value Distribution

Suppose the `subscription_events` table has 1 million rows:

| status | Row Count | Share |
| --- | ---: | ---: |
| `active` | 940,000 | 94% |
| `expired` | 50,000 | 5% |
| `pending` | 9,000 | 0.9% |
| `failed` | 1,000 | 0.1% |

The condition `status = 'active'` returns most of the table; `status = 'failed'` returns only a tiny slice. If the optimizer assumes values are roughly uniformly distributed, it can misestimate selectivity for individual values.

Skew commonly appears in:

- Order, payment, or job statuses.
- Tenant IDs, countries, regions, or customer segments.
- Boolean flags such as `is_deleted`, `is_active`.
- Dates when recent data clusters heavily in a recent window.
- Certain foreign keys with massive child row counts while most keys have only a few rows.

Conditions on rare values can be highly selective, whereas conditions on dominant values can make a full table scan cheaper than index lookups. Do not force the optimizer to use an index just because the column is indexed.

## 4. Correlation: Relationships Between Columns

Two columns are correlated when the distribution of one column changes depending on the value of the other. Examples:

- In region `VN`, most users are on the `free` plan.
- In region `US`, most users are on the `enterprise` plan.
- `failed` orders cluster in specific payment channels.

Consider the query:

```sql
SELECT COUNT(*)
FROM subscriptions
WHERE region_code = 'VN'
  AND plan_type = 'free';
```

If the optimizer estimates the selectivity of `region_code` and `plan_type` as two independent conditions, it combines the individual fractions under an assumption close to independence. When the two columns are strongly correlated, the actual result can differ vastly from that estimate.

Standard MySQL histograms describe the distribution of **one column at a time**. The histogram for `region_code` contains no information that `VN` commonly pairs with `free`; the histogram for `plan_type` also stores no such relationship. Thus, two single-column histograms still may not fix estimation errors caused by correlation.

## 5. Creating a Practice Table with Skew and Correlation

Create a sample table to test filter predicates on status, region, and plan type:

```sql
CREATE TABLE subscriptions (
    subscription_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    region_code CHAR(2) NOT NULL,
    plan_type VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (subscription_id),
    KEY idx_subscriptions_customer (customer_id),
    KEY idx_subscriptions_created (created_at)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

Suppose data is loaded with the following distribution:

- `status = 'active'` accounts for ~94%; `failed` accounts for only ~0.1%.
- `region_code = 'VN'` usually pairs with `plan_type = 'free'`.
- `region_code = 'US'` usually pairs with `plan_type = 'enterprise'`.
- Other combinations appear less frequently.

You can load representative data using ETL or a data-generation script in a lab environment. What matters is having enough rows while preserving skew/correlation to observe estimates; a handful of sample rows is insufficient to produce meaningful statistics.

Count actual rows before analyzing:

```sql
SELECT status, COUNT(*) AS row_count
FROM subscriptions
GROUP BY status
ORDER BY row_count DESC;

SELECT region_code, plan_type, COUNT(*) AS row_count
FROM subscriptions
GROUP BY region_code, plan_type
ORDER BY row_count DESC;
```

These `COUNT(*)` queries measure existing data. They serve as a baseline to compare against optimizer estimates, not something the optimizer runs before every production query.

## 6. InnoDB Index Statistics

InnoDB maintains table and index statistics, including estimated row counts, distinct value counts for index prefixes, and key distributions. The optimizer uses these statistics to estimate access path costs.

Inspect indexes:

```sql
SHOW INDEX FROM subscriptions;
```

Notable columns:

- `Key_name`: index name.
- `Seq_in_index`: column position in a composite index.
- `Column_name`: column included in the index.
- `Cardinality`: estimated number of distinct values for the corresponding index prefix.
- `Sub_part`: prefix length if only part of the value is indexed.

`Cardinality` is a statistical estimate, not an exact count of all values in the table. For composite index `(a, b)`, prefix statistics describe distinct values for `(a)` and `(a, b)` according to how InnoDB stores index stats.

InnoDB statistics can be persistent or transient depending on configuration. Check related variables:

```sql
SHOW VARIABLES LIKE 'innodb_stats_persistent';
SHOW VARIABLES LIKE 'innodb_stats_auto_recalc';
SHOW VARIABLES LIKE 'innodb_stats_persistent_sample_pages';
```

Persistent statistics are saved so the optimizer has more stable information across restarts. Page sampling bounds analysis overhead, which also means statistics are estimates; heavy skew or unrepresentative samples can make cardinality inaccurate.

## 7. ANALYZE TABLE to Refresh Index Statistics

After bulk loads, large deletions, or major distribution shifts, old index statistics may no longer be representative. Use:

```sql
ANALYZE TABLE subscriptions;
```

This command tells MySQL to re-analyze the table and update key distribution statistics used by the optimizer. Afterward, check again:

```sql
SHOW INDEX FROM subscriptions;
```

`ANALYZE TABLE` does not modify business data and does not replace `OPTIMIZE TABLE`. It updates statistics; it does not guarantee every estimate will be exact, especially when errors stem from multi-column correlations that single-column statistics cannot capture.

With InnoDB, statistics rely on sampling. If estimates fluctuate or seem unrepresentative, evaluate an appropriate sample page count, keeping in mind that higher sampling makes `ANALYZE` take longer. Change configuration only after measuring and understanding the impact.

## 8. Histograms in MySQL

MySQL 8.0 supports histogram statistics to describe a column's value distribution. Histograms are especially useful when the optimizer needs to estimate filter conditions on unindexed columns. For indexed columns, the optimizer also has index statistics and range optimizer estimates; do not assume histograms always take precedence or replace index statistics.

Two main histogram types:

| Type | Representation | Suited For |
| --- | --- | --- |
| Singleton | Each distinct value is represented by its own bucket | Columns with few distinct values |
| Equi-height | Each bucket represents a value range with roughly equal row counts | Columns with many distinct values |

A histogram stores information such as histogram type, bucket count, NULL fraction, value intervals, and estimated frequencies. It helps the optimizer see that `failed` is rare while `active` is common, instead of treating all values as equally likely.

Histograms are estimated statistics. Bucket count, sampling, data types, and distributions changing over time all affect quality.

## 9. Creating Histograms for Skewed Columns

Create a histogram for `status`:

```sql
ANALYZE TABLE subscriptions
UPDATE HISTOGRAM ON status WITH 32 BUCKETS;
```

For a column with only a few statuses, MySQL can create a singleton histogram if the number of distinct values fits within the bucket count. `WITH 32 BUCKETS` is the maximum requested buckets for this histogram; it does not force the result to contain exactly 32 buckets.

You can create histograms for multiple columns:

```sql
ANALYZE TABLE subscriptions
UPDATE HISTOGRAM ON status, region_code, plan_type
WITH 100 BUCKETS;
```

Each histogram still describes a single column. The command above does not create a multi-dimensional histogram for the combination of `region_code` and `plan_type`.

Inspect histograms:

```sql
SELECT
    SCHEMA_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    HISTOGRAM
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'subscriptions';
```

`HISTOGRAM` is JSON. You can inspect it directly or extract needed fields with JSON functions to check histogram type, buckets, and update time.

## 10. Updating and Dropping Histograms

Histograms do not reflect every data change immediately. When distributions shift noticeably, refresh them:

```sql
ANALYZE TABLE subscriptions
UPDATE HISTOGRAM ON status WITH 32 BUCKETS;
```

If a histogram is no longer helpful or you want to revert to estimates based on other statistics:

```sql
ANALYZE TABLE subscriptions
DROP HISTOGRAM ON status;
```

Creating or dropping a histogram alters the information the optimizer uses to estimate; query plans may change afterward. Check critical queries with `EXPLAIN` and re-measure before and after changes.

Do not refresh histograms constantly after every insert. Choose an update schedule based on data churn rate, degree of skew, and queries relying on that column.

## 11. Histograms Do Not Fully Resolve Correlation

Suppose data has this distribution:

| region_code | plan_type | Illustrative Share |
| --- | --- | ---: |
| VN | free | 70% |
| VN | enterprise | 2% |
| US | free | 3% |
| US | enterprise | 20% |
| Other | Remaining plans | 5% |

Single-column histograms can capture the share of `VN` and the share of `free`, yet they do not directly store the share of the `VN + free` combination. If the optimizer combines the two selectivities assuming near-independence, estimates can be off because `VN` and `free` are correlated.

MySQL does not provide general multi-column histograms to store conditional distributions for arbitrary column combinations. Therefore, when multiple predicates are correlated, combine the following approaches:

- Use a composite index for predicate combinations that occur frequently.
- Check prefix statistics of the composite index.
- Write queries aligned with proper access patterns, avoiding unnecessary functions on filtered columns.
- Split or normalize data if the current model produces hard-to-estimate distributions and overly complex queries.
- Measure actual rows with `EXPLAIN ANALYZE`; do not expect the optimizer to rely on single-column histograms to capture multi-column relationships.

## 12. Composite Indexes Help Combined Predicates

If queries frequently filter on both `region_code` and `plan_type`, evaluate a composite index:

```sql
CREATE INDEX idx_subscriptions_region_plan
ON subscriptions (region_code, plan_type);
```

This index supports the query:

```sql
SELECT subscription_id, customer_id, status
FROM subscriptions
WHERE region_code = 'VN'
  AND plan_type = 'free';
```

Composite index statistics contain cardinality for the index prefixes. This helps the optimizer both estimate and access data efficiently when predicates match the column order.

Column order matters due to the leftmost prefix rule:

- `(region_code, plan_type)` supports predicates filtering only `region_code` or filtering both columns in order.
- It is not an equivalent option for a query filtering only on `plan_type`.
- If the workload primarily leads with `plan_type`, evaluate `(plan_type, region_code)` order.

A composite index is not a multi-dimensional histogram for arbitrary queries. It supplies an access path and useful prefix statistics for the indexed columns, not every conditional correlation, expression, or arbitrary combination. Create indexes based on real queries and measure write and storage impact.

## 13. Comparing Estimates and Actual Row Counts

`EXPLAIN` shows the expected plan and estimates. Example:

```sql
EXPLAIN
SELECT subscription_id, customer_id
FROM subscriptions
WHERE status = 'failed'
  AND region_code = 'VN';
```

In tabular output, key fields include:

- `rows`: estimated rows the optimizer expects to read at that step.
- `filtered`: estimated percentage of rows remaining after filter conditions.
- `key`: chosen index.
- `type`: access method such as `const`, `eq_ref`, `ref`, `range`, `index`, `ALL`.
- `Extra`: additional notes such as `Using where`, `Using index`, `Using temporary`, or `Using filesort`.

In `EXPLAIN FORMAT=JSON`, you can inspect finer details such as `rows_examined_per_scan`, `rows_produced_per_join`, `filtered`, and `cost_info` depending on query block structure.

The `rows` estimate is not a guaranteed final returned row count. It describes expected work/volume at an execution step. When comparing with actual rows, match the right iterator and loop count.

## 14. EXPLAIN ANALYZE: Checking Actual Rows and Loops

MySQL 8.0.18 and later support `EXPLAIN ANALYZE` for read queries. It executes the query and reports actual timing, actual rows, and loop counts per iterator:

```sql
EXPLAIN ANALYZE
SELECT subscription_id, customer_id
FROM subscriptions
WHERE status = 'failed'
  AND region_code = 'VN';
```

Tree output can show details such as:

- `estimated rows`: row count predicted by the optimizer.
- `actual time`: actual time spent by the iterator.
- `actual rows`: rows actually processed/returned by the iterator.
- `loops`: number of times the iterator was invoked.

If an iterator estimates 100,000 rows while reality has only 20, or vice versa, a large discrepancy can distort join order and algorithm choice. For iterators executed many times, examine both `rows` and `loops`; a small row count per loop across thousands of loops can still be expensive.

`EXPLAIN ANALYZE` actually executes the query. Use it on safe `SELECT` queries in an appropriate environment, scoping data and load as needed. Do not treat it as free or as a static explain.

## 15. Identifying Estimation Errors in JOIN Plans

Suppose a query joins `customers` and `subscriptions`:

```sql
EXPLAIN ANALYZE
SELECT c.customer_id, s.subscription_id
FROM customers AS c
JOIN subscriptions AS s
  ON s.customer_id = c.customer_id
WHERE s.status = 'failed'
  AND s.region_code = 'VN';
```

Warning signs worth investigating:

- The optimizer predicts a large input set when reality is tiny, leading to the wrong driving table.
- A nested-loop iterator has very high `loops` where each inner-table probe is costly.
- A filter step emits many times more rows than estimated, forcing downstream steps to handle far more volume than anticipated.
- A table undergoes a full scan despite highly selective predicates and a suitable index existing.
- Sorting/materialization processes many rows because filters are applied late.

Not every `ALL` or full scan is bad. If a predicate returns most of the table or the table is small, a full scan can be cheaper than many random lookups. Inspect actual rows, timing, and workload rather than judging solely by access method name.

## 16. Optimizer Trace to Understand Decisions

When `EXPLAIN` does not clarify why the optimizer picked an access path or join order, you can use optimizer trace:

```sql
SET optimizer_trace = 'enabled=on';

SELECT subscription_id, customer_id
FROM subscriptions
WHERE status = 'failed'
  AND region_code = 'VN';

SELECT TRACE
FROM INFORMATION_SCHEMA.OPTIMIZER_TRACE;

SET optimizer_trace = 'enabled=off';
```

The trace is JSON containing the steps the optimizer evaluated, such as range analysis, cost estimation, index choice, and `JOIN` order. Output can be long and version-dependent; filter to the relevant section instead of reading everything mechanically.

Optimizer trace explains decisions based on current statistics. It neither fixes statistics automatically nor guarantees the chosen plan is optimal across all workloads.

## 17. Workflow for Resolving Estimate Errors

When you suspect optimizer misestimation, follow this order:

1. **Reproduce the query:** keep identical parameters, predicates, joins, and representative data.
2. **Capture the plan:** run `EXPLAIN FORMAT=JSON` or `EXPLAIN` to view estimated rows, indexes, and join order.
3. **Measure actuals:** run `EXPLAIN ANALYZE` on a suitable `SELECT` to inspect actual rows, loops, and timing.
4. **Pinpoint the divergence:** locate the earliest iterator where actual rows differ sharply from estimates; early errors propagate through the entire plan.
5. **Check distributions:** count value frequencies to identify skew and rare/dominant values.
6. **Check correlation:** determine whether multi-column predicates depend on each other; compare single-column counts against combined counts.
7. **Check index statistics:** inspect `SHOW INDEX`; if data changed substantially, consider `ANALYZE TABLE`.
8. **Evaluate histograms:** create or refresh single-column histograms for eligible conditions, especially on unindexed columns.
9. **Evaluate composite indexes:** if queries often filter on correlated columns together, test a composite index with proper column order.
10. **Compare again:** run the same query and parameters, comparing before/after plans, actual rows, loops, and execution time.
11. **Check related queries:** an index or histogram can help one query while altering plans for others.
12. **Monitor post-deployment:** data distributions continue evolving; maintain a refresh and re-measurement cadence.

## 18. When to Use Histograms, Composite Indexes, or Query Rewrites

| Symptom | Approach to Evaluate | Limitation |
| --- | --- | --- |
| Unindexed column, heavy value skew | Single-column histogram | Does not capture correlation with other columns |
| Stale index stats after bulk load | `ANALYZE TABLE` | Still an estimate subject to sampling |
| Query frequently filters two columns together | Composite index | Column order and leftmost prefix matter |
| Multiple strongly correlated predicates | Composite index, query design, and actual row verification | No general multi-dimensional histograms |
| Predicate applies a function to a column | Consider sargable expression or generated column/index | Must preserve semantics and write cost |
| Query selects excessive columns/LOBs | Select only needed columns | Does not fix cardinality errors, though reduces I/O |
| Estimate error at first JOIN step | Fix statistics/access paths and inspect join order | Hints should not be the first resort |

## 19. Optimizer Hints: Use Only After Understanding the Root Cause

MySQL provides optimizer hints and index hints to influence execution choices. However, forcing an index or join order may help a current dataset while hurting queries later as data shifts.

Before using a hint:

- Confirm the estimate error with `EXPLAIN ANALYZE`.
- Check index statistics, histograms, and correlation.
- Verify the hint targets the right query block and MySQL version.
- Measure on representative data across varied distributions.
- Monitor plans as data grows or changes.

Do not add `FORCE INDEX` simply because the optimizer picked a full scan. A full scan can be the right choice if most rows must be read. Hints should be deliberate, measured, and documented.

## 20. Common Mistakes and Misconceptions

| Misconception / Mistake | Reality | Remedy |
| --- | --- | --- |
| High cardinality means every value is selective | Distribution can be heavily skewed despite high cardinality | Check per-value frequencies and histograms |
| ANALYZE TABLE makes all estimates exact | It updates index stats via sampling | Measure actual rows and check skew/correlation |
| Histograms capture multi-column relationships | MySQL histograms are single-column stats | Use composite indexes and verify combined conditions |
| Creating a histogram forces the optimizer to use it | Optimizer picks estimate sources per access path and predicate | Compare plans before/after; use trace when needed |
| EXPLAIN rows are actual rows | They are estimates | Use EXPLAIN ANALYZE to measure actual rows |
| EXPLAIN ANALYZE only displays without running the query | It executes the query | Run scoped SELECTs in a safe environment |
| Full table scans are always bad | Can be cheaper than index lookups when reading most of a table | Evaluate selectivity, I/O, and timing |
| A composite index is a multi-dimensional histogram | It provides an access path and prefix stats, not arbitrary condition relationships | Design for the workload and re-measure |
| Increasing bucket count is always better | Larger histograms add overhead and cannot fix correlation | Pick buckets based on cardinality and estimate quality |
| FORCE INDEX always fixes estimate errors | Hints can degrade plans as data evolves | Use only with evidence and testing |

## 21. Practice Exercises

1. Create the `subscriptions` table with a heavily skewed `status` distribution; use `GROUP BY` to count actual frequencies.
2. Run `EXPLAIN` for `status = 'failed'` before creating a histogram; record estimates and chosen index.
3. Create a histogram using `ANALYZE TABLE ... UPDATE HISTOGRAM`; inspect `INFORMATION_SCHEMA.COLUMN_STATISTICS`.
4. Re-run `EXPLAIN` and `EXPLAIN ANALYZE`; compare estimates against actual rows.
5. Generate data with correlation between `region_code` and `plan_type`; count single columns and two-column combinations.
6. Create separate histograms for `region_code` and `plan_type`; observe why they do not fully describe the combined distribution.
7. Create composite index `(region_code, plan_type)`; compare access paths and actual rows.
8. Swap column order in the index in a lab environment; test leftmost prefix behavior with a single-column filter query.
9. After a bulk load or major data change, run `ANALYZE TABLE`; inspect cardinality in `SHOW INDEX`.
10. Use optimizer trace to inspect how the optimizer evaluates indexes and join order.
11. Build a `JOIN` query with a bad estimate; locate the first iterator showing a large gap between estimated and actual rows.
12. Only after measuring, test an optimizer hint in the lab and compare across different data distributions.

## 22. Takeaways

The optimizer chooses plans based on row count and cost estimates. Data skew causes common and rare values to have vastly different selectivities; correlation prevents multi-column selectivity from being accurately inferred from single-column statistics. InnoDB maintains sampled index statistics; `ANALYZE TABLE` refreshes key distributions, while MySQL 8.0 histograms describe single-column distributions via singleton or equi-height buckets.

Histograms help with single-column skew, but they are not multi-dimensional histograms. For correlated multi-column predicates, evaluate composite indexes and prefix statistics while measuring actual rows. `EXPLAIN` shows estimates; `EXPLAIN ANALYZE` executes the `SELECT` and reports actual rows, loops, and timing. Find the earliest iterator with an estimation error, inspect distributions, refresh appropriate statistics, test index/query designs, and re-measure. Use optimizer hints only after understanding the root cause, gathering evidence, and testing across representative data.
