# Cardinality, Selectivity, Cost, and Estimation Limits

MySQL does not choose a query execution plan based solely on whether a column has an index. The optimizer needs to estimate how many rows satisfy each condition, how many rows an index access will read, how many intermediate rows joins will produce, and how much work each alternative costs. These estimates rely on table and index statistics, histograms, query structure, and the cost model.

Three foundational concepts are **cardinality**, **selectivity**, and **cost**. Cardinality describes the estimated number of distinct values in a column or index prefix. Selectivity describes how strongly a condition filters rows. Cost is a relative score used by the optimizer to compare plans. If statistics are missing, stale, or fail to reflect the data distribution, the optimizer can misestimate row counts and choose an inefficient full table scan, index scan, or join order.

This lesson belongs to the `DATABASE_MYSQL` module, which focuses on table design, data types, keys, SQL queries, indexes, transactions, concurrency control, reading execution plans, and query tuning. The goal is to read statistics, understand what the optimizer is estimating, recognize gaps between estimates and actuals, and then update statistics or adjust queries/indexes based on evidence.

After this lesson, you will be able to:

- Distinguish index cardinality from table row count.
- Distinguish the distinct-value ratio from the fraction of rows matching a predicate when discussing selectivity.
- Explain the cost model and why cost is not execution time in milliseconds.
- Read `rows`, `filtered`, `key`, `type`, and `cost_info` in `EXPLAIN`.
- Inspect persistent InnoDB statistics and index-prefix cardinality.
- Use `ANALYZE TABLE` to refresh key distributions.
- Create, view, and drop histograms to describe column distributions.
- Identify data skew, correlation, and sampling discrepancies.
- Compare estimates with actual row counts using `EXPLAIN ANALYZE`.
- Use optimizer trace and choose evidence-based remedies.

## 1. What Does the Optimizer Need to Estimate?

When receiving a `SELECT` statement, MySQL parses it and constructs execution alternatives. For each table, the optimizer evaluates data access methods; for multiple tables, it evaluates join orders and join methods. To compare alternatives, the optimizer needs to estimate:

- Total rows and the number of distinct values in columns/indexes.
- How many rows are likely to satisfy each predicate.
- How many rows must be read from a table or index.
- How many rows remain after applying filter conditions.
- Intermediate row counts when combining tables.
- Costs of reading index pages, reading data pages, filtering rows, sorting, materializing, and performing joins.

The optimizer does not test-run every plan over the entire dataset and pick the fastest one. It uses statistics and a cost model to predict. Therefore, statistics quality directly affects plan quality.

For example, with the query:

```sql
SELECT order_id, customer_id, amount
FROM orders
WHERE status = 'OPEN'
  AND created_at >= '2026-11-01';
```

The optimizer needs to estimate how many orders are open, how many orders were created since November 1, and how many rows satisfy both conditions. If it only has separate statistics for `status` and `created_at`, yet the two columns are strongly correlated, the combined estimate can be wrong.

## 2. What Is Cardinality?

Cardinality is the estimated number of distinct values in a dataset or part of an index. In MySQL, the `Cardinality` column in `SHOW INDEX` is an estimate of the number of unique values in the index or corresponding index prefix; it is not an exact row count.

For example, a table with 100,000 rows:

| Column | Actual Distinct Values | Notes |
| --- | ---: | --- |
| `order_id` | 100,000 | Primary key; every row has a unique ID |
| `customer_id` | 5,000 | A customer can have multiple orders |
| `status` | 4 | Only four statuses exist |
| `country_code` | 30 | Most rows are concentrated in a few countries |

High cardinality usually means an index distinguishes many values. Low cardinality means many rows share the same value. However, high cardinality does not automatically make every query fast; effectiveness still depends on the predicate, number of rows to return, index column order, and lookup cost.

### 2.1. Cardinality of a Composite Index

With the index:

```sql
KEY idx_orders_customer_date (customer_id, created_at)
```

InnoDB maintains cardinality statistics for each prefix:

- Prefix 1: `(customer_id)`.
- Prefix 2: `(customer_id, created_at)`.

Example:

| Index Prefix | Estimated Cardinality |
| --- | ---: |
| `customer_id` | 5,000 |
| `customer_id, created_at` | 70,000 |

This shows that the combination of customer and timestamp has more distinct values than customer alone. It does not mean queries filtering on `created_at` alone can use this index effectively; the leftmost prefix rule still applies.

### 2.2. Cardinality Is Not Row Count

An index on `status` with cardinality 4 in a 100,000-row table can still be very useful for certain queries if one status is rare and the query needs only a small slice of data. Conversely, if one status makes up 99% of the table and the query needs most of those rows, the optimizer may choose a scan instead of reading the index and looking up nearly all data pages.

Cardinality also does not say whether the value distribution is uniform. Two tables both having 4 distinct values can have vastly different distributions:

- Table A: each value appears roughly 25% of the time.
- Table B: one value accounts for 97%, while the other three share 3%.

Distinct-value counts alone do not capture this skew.

## 3. Selectivity: How Many Rows Does a Predicate Filter?

The term "selectivity" is often used in two related but distinct ways. To avoid confusion, this lesson clearly distinguishes:

1. **Distinct-value fraction**: the ratio of distinct values to total rows, typically close to `cardinality / row_count`.
2. **Predicate selectivity**: the fraction of rows satisfying the condition out of total rows, i.e., `qualifying_rows / total_rows`.

For a uniformly distributed column, an equality predicate on a single value can be estimated close to `1 / cardinality`. When data is skewed, however, that division can be far off.

For example, a table with 100,000 rows where `status` has four values:

| status | Row Count | Predicate Selectivity |
| --- | ---: | ---: |
| `OPEN` | 2,000 | 2% |
| `PAID` | 8,000 | 8% |
| `CLOSED` | 85,000 | 85% |
| `CANCELLED` | 5,000 | 5% |

The cardinality of `status` is 4; the distinct-value fraction is 0.004%. Yet the predicate `status = 'CLOSED'` has a selectivity of 85%, while `status = 'OPEN'` has a selectivity of 2%. On the same column, two values have very different filtering power.

In everyday index terminology, people often call a column with few matching rows per value "selective" or "highly selective." Be explicit about whether you mean a small fraction of matching rows or a large fraction of distinct values so you do not invert the meaning.

### 3.1. Why Does Selectivity Affect Index Choice?

Suppose a table has 1,000,000 rows:

- Predicate matches 100 rows: an index lookup reads few index entries and few data pages.
- Predicate matches 800,000 rows: an index lookup must read many index entries and perform many random row lookups; a sequential table scan can be cheaper.

There is no fixed threshold. The optimizer also evaluates row size, whether the index is covering, clustering, cache residency, I/O/CPU costs, join order, and other conditions.

### 3.2. Combining Multiple Predicates

With:

```sql
WHERE status = 'OPEN'
  AND region = 'NORTH'
```

If the optimizer only has single-column selectivities, it must estimate how many rows satisfy both simultaneously. Under independence, you can picture:

```text
selectivity(status AND region)
    ~= selectivity(status) * selectivity(region)
```

This is an illustrative assumption, not an always-true rule. If `OPEN` orders belong mostly to the `NORTH` region, the two conditions are correlated and multiplying under independence can underestimate or overestimate actual rows.

## 4. What Cost Is and What It Is Not

Cost is a relative score calculated by the optimizer to compare execution alternatives. Cost reflects estimated work such as reading pages, accessing indexes, evaluating conditions, processing rows, and other operations under the cost model.

Cost is **not**:

- Actual runtime in milliseconds.
- Number of rows returned.
- Exact number of disk reads.
- A number directly comparable across different servers, versions, and configurations.
- A guarantee that the lowest-cost plan will always run fastest at every moment.

The optimizer picks the alternative with the lowest estimated cost among those it considers. If cardinality or selectivity is wrong, plan costs can also be wrong, leading to a poor final choice.

### 4.1. Components That Affect Cost

Depending on access type and plan, the cost model may include:

- Cost of reading index and data pages.
- Cost of range access or key lookup.
- CPU cost for predicate evaluation.
- Join cost and intermediate row counts.
- Cost of sorting, temporary tables, and materialization.
- Whether a covering index avoids row lookups.

MySQL provides cost model tables such as `mysql.server_cost` and `mysql.engine_cost`. They allow configuring certain cost items; arbitrary changes can cause the optimizer to choose worse plans.

Inspect the cost model:

```sql
SELECT cost_name, cost_value, default_value, comment
FROM mysql.server_cost
ORDER BY cost_name;

SELECT engine_name, device_type, cost_name, cost_value, default_value, comment
FROM mysql.engine_cost
ORDER BY engine_name, device_type, cost_name;
```

Reading these tables may require appropriate privileges. Do not adjust cost values just to force a specific query before identifying why statistics or access paths diverged.

## 5. Where Does MySQL Get Statistics?

The optimizer can draw on multiple information sources:

- Estimated row count and table size.
- Cardinality of indexes and prefixes of composite indexes.
- InnoDB persistent statistics.
- Column histograms.
- Information from index dives and the range optimizer.
- Metadata about data types, nullability, unique keys, and constraints.

Not every query uses all statistics sources. Estimation mechanics depend on predicate types, indexes, MySQL version, and query structure.

### 5.1. Persistent InnoDB Statistics

InnoDB can store table/index statistics persistently so they survive server restarts. Check settings:

```sql
SHOW VARIABLES LIKE 'innodb_stats_persistent';
SHOW VARIABLES LIKE 'innodb_stats_auto_recalc';
SHOW VARIABLES LIKE 'innodb_stats_persistent_sample_pages';
```

- `innodb_stats_persistent` controls saving persistent statistics.
- `innodb_stats_auto_recalc` enables automatic recalculation of persistent stats when enough data changes.
- `innodb_stats_persistent_sample_pages` controls the default number of sampled pages when computing persistent stats.

In InnoDB, persistent statistics are enabled by default in modern MySQL configurations. Automatic recalculation may run asynchronously; after a bulk load or major distribution shift, statistics may not immediately reflect the new state. You can run `ANALYZE TABLE` to request an update.

### 5.2. Per-Table Statistics Settings

Persistent stats and sample pages can be configured per table:

```sql
ALTER TABLE optimizer_lab STATS_PERSISTENT = 1;
ALTER TABLE optimizer_lab STATS_AUTO_RECALC = 1;
ALTER TABLE optimizer_lab STATS_SAMPLE_PAGES = 64;
```

These options control how InnoDB collects and refreshes statistics for the table. Larger sample pages can make estimates more stable on unevenly distributed data, at the cost of extra work when collecting stats. Do not raise sample pages by default for every table; evaluate specific tables individually.

### 5.3. Viewing Persistent Statistics

Table statistics can be viewed via:

```sql
SELECT
    database_name,
    table_name,
    last_update,
    n_rows,
    clustered_index_size,
    sum_of_other_index_sizes
FROM mysql.innodb_table_stats
WHERE database_name = DATABASE()
  AND table_name = 'optimizer_lab';
```

Index statistics:

```sql
SELECT
    index_name,
    stat_name,
    stat_value,
    sample_size,
    last_update
FROM mysql.innodb_index_stats
WHERE database_name = DATABASE()
  AND table_name = 'optimizer_lab'
ORDER BY index_name, stat_name;
```

Rows named `n_diff_pfxNN` represent estimated distinct values for index prefixes. These are sampled statistics, not exact `COUNT(DISTINCT ...)` results. Access to the `mysql` schema may require appropriate privileges; in many cases `SHOW INDEX` is sufficient.

## 6. Creating a Fixture to Observe Cardinality and Skew

Create a 1,000-row lab table with a heavily skewed `status` distribution. Use test data to observe how the optimizer estimates, without treating cardinality numbers on a tiny table as fixed across all versions.

```sql
DROP TABLE IF EXISTS optimizer_lab;

CREATE TABLE optimizer_lab (
    id BIGINT UNSIGNED NOT NULL,
    customer_id INT UNSIGNED NOT NULL,
    status VARCHAR(12) NOT NULL,
    region VARCHAR(12) NOT NULL,
    created_at DATE NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_optimizer_customer_date (customer_id, created_at)
) ENGINE = InnoDB;

INSERT INTO optimizer_lab
    (id, customer_id, status, region, created_at, amount)
WITH RECURSIVE seq (n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1
    FROM seq
    WHERE n < 1000
)
SELECT
    n,
    MOD(n, 100) + 1,
    CASE WHEN n <= 950 THEN 'CLOSED' ELSE 'OPEN' END,
    CASE MOD(n, 4)
        WHEN 0 THEN 'NORTH'
        WHEN 1 THEN 'SOUTH'
        WHEN 2 THEN 'EAST'
        ELSE 'WEST'
    END,
    DATE_ADD('2026-01-01', INTERVAL MOD(n, 90) DAY),
    CAST(MOD(n * 37, 100000) / 100.0 AS DECIMAL(10, 2))
FROM seq;
```

The script uses a recursive CTE to generate 1,000 numbers; the default recursion limit of 1,000 is sufficient for this example. If your environment enforces a lower limit, adjust the session setting in the lab or reduce the row count.

Verify the actual distribution:

```sql
SELECT status, COUNT(*) AS row_count
FROM optimizer_lab
GROUP BY status
ORDER BY status;

SELECT region, COUNT(*) AS row_count
FROM optimizer_lab
GROUP BY region
ORDER BY region;

SELECT COUNT(*) AS total_rows,
       COUNT(DISTINCT customer_id) AS distinct_customers,
       COUNT(DISTINCT created_at) AS distinct_dates
FROM optimizer_lab;
```

The `status` result has 950 `CLOSED` rows and 50 `OPEN` rows. `customer_id` has 100 distinct values; `region` has four nearly uniform values. Neither `status` nor `region` has a dedicated index yet, which is convenient for observing the effect of histograms.

## 7. Reading Cardinality with SHOW INDEX

Run:

```sql
ANALYZE TABLE optimizer_lab;
SHOW INDEX FROM optimizer_lab;
```

In the `SHOW INDEX` output, focus on:

| Column | Meaning |
| --- | --- |
| `Key_name` | Index name |
| `Seq_in_index` | Column position in the index |
| `Column_name` | Column belonging to the index |
| `Non_unique` | 0 if unique index, 1 if non-unique |
| `Cardinality` | Estimated distinct values for the index prefix up to that column |
| `Sub_part` | Prefix length if only part of a string column is indexed |
| `Index_type` | Index type, typically BTREE in this example |

For `idx_optimizer_customer_date`, the `customer_id` row shows the cardinality of the single-column prefix; the `created_at` row shows the cardinality of the `(customer_id, created_at)` combination. Values can vary across analyses or environments due to sampling and data changes.

Do not read `Cardinality` as an exact figure. If you need to verify true data counts, run `COUNT(DISTINCT ...)` over an appropriate scope, keeping in mind that such a query may scan a lot of data and consume resources.

## 8. Updating Statistics with ANALYZE TABLE

After bulk loads, large deletions, or substantial distribution shifts, stale statistics can cause the optimizer to misestimate.

```sql
ANALYZE TABLE optimizer_lab;
```

`ANALYZE TABLE` instructs MySQL to update key distributions and related statistics for subsequent optimizer plans. It does not reorganize data or create indexes; it refreshes statistical metadata.

Situations where you should consider it:

- After loading a large volume of data.
- After deleting or archiving a large portion of a table.
- After value distributions change noticeably.
- When `EXPLAIN` row estimates differ wildly from actuals and statistics are old.
- After index or schema changes affecting access paths.

`ANALYZE TABLE` can consume I/O and require metadata locks during certain phases. Schedule it in appropriate windows for heavy workloads; check status and duration rather than embedding it into application requests.

## 9. Histograms Describe Column Distributions

Index cardinality shows the estimated count of distinct values, but it does not necessarily show which values are common. Histograms provide bucketed distribution information so the optimizer can estimate column predicates.

Histograms are especially helpful when:

- A column is heavily skewed.
- A column lacks its own index but is frequently filtered.
- Distinct value count is low or distribution is uneven.
- Equality or range predicate estimates on the column are inaccurate.

### 9.1. Creating Histograms

On MySQL 8.0 and later:

```sql
ANALYZE TABLE optimizer_lab
UPDATE HISTOGRAM ON status, region
WITH 16 BUCKETS;
```

MySQL builds histograms for the specified columns. The bucket count is the requested maximum; the actual histogram structure depends on the data and chosen histogram type.

### 9.2. Viewing Histograms

```sql
SELECT
    SCHEMA_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    HISTOGRAM
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'optimizer_lab';
```

Histograms are stored as JSON. Depending on the distribution, MySQL may use a singleton or equi-height histogram. Singleton works well for small numbers of distinct values; equi-height groups values into buckets with roughly equal observation counts.

### 9.3. Dropping Histograms

```sql
ANALYZE TABLE optimizer_lab
DROP HISTOGRAM ON status, region;
```

Dropping a histogram does not delete table data or indexes. The optimizer falls back to other available statistics sources.

### 9.4. Histograms Are Not Multi-Column Statistics

MySQL histograms describe each column independently; they do not directly capture full correlations across columns such as `(status, region)` or `(tenant_id, created_at)`. If two columns are strongly dependent, the optimizer can still misestimate combined predicates even when individual column histograms are accurate.

For critical queries, consider a composite index matching the combined conditions, rewriting the query, or building summary/materialized data if the workload warrants it. Do not expect single-column histograms to fix every join and correlation skew.

## 10. Comparing Estimates Before and After a Histogram

Run the following queries before creating a histogram and after creating a histogram:

```sql
EXPLAIN FORMAT=TREE
SELECT id, customer_id, status, amount
FROM optimizer_lab
WHERE status = 'OPEN';

EXPLAIN FORMAT=TREE
SELECT id, customer_id, status, amount
FROM optimizer_lab
WHERE status = 'CLOSED';
```

Because `status` does not yet have its own index, MySQL may choose a table scan. What to observe is the estimated rows after filtering for `OPEN` versus `CLOSED`, rather than expecting the optimizer to pick a specific plan on a small lab table.

Before the histogram, the optimizer may rely on a less informed distribution assumption. After the histogram, it has data showing `OPEN` is much rarer than `CLOSED`. Exact numbers depend on version, other statistics, and query structure.

To see the impact of an index, try creating an index in the lab:

```sql
CREATE INDEX idx_optimizer_status ON optimizer_lab (status);
ANALYZE TABLE optimizer_lab;

EXPLAIN FORMAT=TREE
SELECT id, customer_id, status, amount
FROM optimizer_lab
WHERE status = 'OPEN';
```

The index can help the `OPEN` query because only a small fraction of rows match. For `CLOSED` at 95%, a table scan can be cheaper than reading many index entries and looking up data rows. The optimizer decides by estimated cost; there is no rule that "having an index always uses the index."

## 11. Reading EXPLAIN: rows and filtered

Run:

```sql
EXPLAIN
SELECT id, customer_id, amount
FROM optimizer_lab
WHERE customer_id = 42
  AND created_at >= '2026-02-01';
```

Commonly inspected columns:

| Column | Meaning |
| --- | --- |
| `type` | Access method such as `const`, `eq_ref`, `ref`, `range`, `index`, `ALL` |
| `possible_keys` | Indexes the optimizer considers candidates |
| `key` | Index actually chosen, if any |
| `key_len` | Length of the index prefix used |
| `rows` | Estimated rows to read/examine in this table access step |
| `filtered` | Estimated percentage of rows remaining after filter conditions at this step |
| `Extra` | Additional notes such as `Using where`, `Using index`, `Using temporary`, `Using filesort` |

Estimated rows passed to the next step can be approximated by:

```text
estimated_output_rows ~= rows * filtered / 100
```

This is an approximate reading for a single step in traditional `EXPLAIN`. In multi-table joins, each step has its own context and estimates; do not multiply numbers mechanically without understanding the access path.

### 11.1. Large rows Is Not Automatically Bad

If a query must return 80% of a table, reading many rows may be unavoidable. A sequential table scan can sometimes be cheaper than hundreds of thousands of random lookups through a secondary index.

Conversely, if a query needs only 10 rows yet `rows` estimates hundreds of thousands, investigate predicates, indexes, data types, statistics, and how the optimizer evaluates selectivity.

### 11.2. Low filtered May Indicate Post-Access Filtering

If `rows = 100000` and `filtered = 1.00`, the optimizer estimates only around 1,000 rows remain after filtering. If a good index can move selective predicates into the access condition, the query can read fewer rows. However, some conditions cannot use an index directly, or using an index is not cheaper than a scan.

## 12. Reading Cost in EXPLAIN FORMAT=JSON and TREE

`EXPLAIN FORMAT=JSON` provides deeper detail on each query block and cost:

```sql
EXPLAIN FORMAT=JSON
SELECT id, customer_id, amount
FROM optimizer_lab
WHERE customer_id = 42
  AND created_at >= '2026-02-01';
```

In the JSON output, depending on the plan, you may see:

- `rows_examined_per_scan`: estimated rows per scan.
- `rows_produced_per_join`: estimated rows after conditions at the join step.
- `filtered`: percentage of rows retained.
- `read_cost`: estimated read cost.
- `eval_cost`: estimated condition evaluation cost.
- `prefix_cost`: cumulative cost up to that step.
- `data_read_per_join`: estimated volume of data read.

`EXPLAIN FORMAT=TREE` displays the plan as a tree, making it easy to see operator order and joins:

```sql
EXPLAIN FORMAT=TREE
SELECT c.customer_id, COUNT(*) AS order_count
FROM optimizer_lab AS c
JOIN optimizer_lab AS d
    ON d.customer_id = c.customer_id
WHERE c.status = 'OPEN'
GROUP BY c.customer_id;
```

The self-join example only illustrates plan shape; it is not a recommended business query pattern. On real queries, inspect which operators read many rows and where intermediate row counts grow.

Step costs typically accumulate. Do not compare costs across two servers with different versions or configurations as an absolute benchmark. Use cost to understand optimizer decisions in the same environment, then verify with actual execution.

## 13. EXPLAIN ANALYZE: Comparing Estimates Against Actuals

`EXPLAIN ANALYZE` runs the query and adds actual metrics such as timing, row counts, and loop counts. It is an essential tool for spotting cardinality/selectivity mismatches.

```sql
EXPLAIN ANALYZE
SELECT id, customer_id, amount
FROM optimizer_lab
WHERE status = 'OPEN';
```

TREE output can contain:

- `cost=... rows=...`: optimizer estimates.
- `actual time=first..last`: actual elapsed time from start until producing the first row and finishing the operator, usually shown in ms.
- `rows=...`: average actual rows returned by the operator per loop.
- `loops=...`: number of times the operator executed.

When comparing, check both `rows` and `loops`. An operator returning 10 rows per loop across 10,000 loops can perform substantial work. `actual` time also reflects cache warmth, CPU, I/O, concurrency, and system state at measurement time.

**Note:** `EXPLAIN ANALYZE` executes the real query. Use it on bounded `SELECT` queries in an appropriate environment; do not treat it as a metadata-only read command. Avoid running it directly on very heavy queries during peak hours.

### 13.1. Reading Estimation Mismatches

Illustrative example:

| Operator | Estimated rows | Actual rows | Notes |
| --- | ---: | ---: | --- |
| Index range scan | 100 | 95 | Estimate is close to actual |
| Filter status | 50 | 2 | Optimizer overestimated selectivity |
| Join lookup | 5,000 | 180 | Error amplified through the join |

These are synthetic numbers to illustrate interpretation. When estimates are many times lower than actuals, the optimizer may pick an unsuitable nested-loop join or join order. When estimates are many times higher than actuals, the optimizer may choose unnecessary scans, sorts, or materializations.

Do not look only at the final operator. Find the earliest operator with a major discrepancy; early errors propagate upward to every subsequent step.

## 14. Optimizer Trace: Finding Why a Plan Was Chosen

When `EXPLAIN` shows a surprising plan, optimizer trace can reveal the alternatives considered and why they were rejected or selected.

```sql
SET optimizer_trace = 'enabled=on';

SELECT id, customer_id, amount
FROM optimizer_lab
WHERE customer_id = 42
  AND created_at >= '2026-02-01';

SELECT TRACE
FROM INFORMATION_SCHEMA.OPTIMIZER_TRACE\G

SET optimizer_trace = 'enabled=off';
```

The trace can include details on:

- Range analysis and candidate range scans.
- Row count estimates for each access path.
- Estimated costs of table scans and index accesses.
- Join order candidates and selection/replacement reasons.
- Where predicates are pushed down or evaluated.

Optimizer trace output is verbose and version-dependent. Enable it in a diagnostic session, read the trace for the statement just executed, and turn it off. Do not enable it globally for all sessions just to inspect one query.

## 15. Limits of Statistics and Estimation

Statistics are not a complete copy of the data. Common limitations include:

### 15.1. Sampling and Uneven Data

InnoDB typically samples pages to estimate cardinality. If data is unevenly distributed across pages, a small sample can miss regions holding rare or concentrated values. Increasing sample pages can improve stability at the expense of extra I/O and statistics computation time.

### 15.2. Data Skew

A column with 10 values where one value makes up 99% renders uniform-distribution assumptions inaccurate. Histograms help the optimizer recognize per-column skew, though finite buckets remain an approximation.

### 15.3. Multi-Column Correlation

Single-column histograms do not fully capture relationships between `status` and `region`, or between `tenant_id` and `created_at`. Combined predicate estimates can be wrong if the optimizer assumes independence.

### 15.4. Stale Statistics

After bulk loads, archiving, or drastic distribution changes, persistent stats and histograms may no longer reflect current data. Automatic recalculation may not trigger immediately. Schedule `ANALYZE TABLE` when appropriate.

### 15.5. Hard-to-Estimate Predicates

Conditions using functions, expressions, implicit conversions, JSON paths, string patterns, or complex operators can be harder to estimate than simple equality/range predicates on columns with statistics.

Example:

```sql
WHERE DATE(created_at) = '2026-11-19'
```

Wrapping a column in an expression can prevent range access on the `created_at` index. Rewriting it as a time interval usually leverages the index better:

```sql
WHERE created_at >= '2026-11-19 00:00:00'
  AND created_at <  '2026-11-20 00:00:00'
```

### 15.6. The Cost Model Does Not Know Full Runtime State

Cost estimates cannot precisely predict transient conditions such as hot/cold caches, fluctuating storage latency, CPU contention, lock waits, network delays, concurrent workloads, or data modified right after statistics collection.

Therefore, a lower-cost plan does not guarantee lower actual latency in every scenario.

## 16. Investigation Workflow When the Optimizer Misestimates

When a query is slow or chooses an unexpected access path, proceed in order:

1. **Verify query and data:** actual predicates, parameters, table row counts, value distribution, and expected output.
2. **Read EXPLAIN:** identify access path, indexes, join order, `rows`, `filtered`, sorts, and temporary work.
3. **Measure actuals:** run `EXPLAIN ANALYZE` on a scoped `SELECT`; locate the first operator where estimates diverge sharply.
4. **Check statistics:** `SHOW INDEX`, persistent stats, last update timestamps, and histograms.
5. **Refresh purposefully:** run `ANALYZE TABLE` or update histograms if data has changed.
6. **Check indexes:** column order, leftmost prefix, covering behavior, selectivity, and row lookups.
7. **Check correlation:** if multiple predicates are related, consider composite indexes or query/model adjustments.
8. **Inspect optimizer trace:** when you need to know why a candidate was rejected or how costs were computed.
9. **Re-measure:** compare plan, actual rows, latency, and resources before and after.

Do not add indexes, force `FORCE INDEX`, or alter the cost model right away. First determine whether the issue stems from statistics, predicates, indexes, or a runtime bottleneck.

## 17. When Should You Use FORCE INDEX?

Optimizer hints such as `FORCE INDEX` can help when you have proven that the optimizer consistently chooses a poor access path for a specific workload and reasonable statistics/index fixes do not resolve it.

Syntax example:

```sql
SELECT id, customer_id, amount
FROM optimizer_lab FORCE INDEX (idx_optimizer_customer_date)
WHERE customer_id = 42;
```

Do not apply a hint merely because one `EXPLAIN` shows `type = ALL`. A table scan can be the right choice if the query needs most of the data or index lookups cost more. Hints can also become counterproductive as data grows, distributions shift, or MySQL versions change.

Before keeping a hint:

- Compare `EXPLAIN ANALYZE` with and without the hint.
- Test across multiple representative predicate values, not just one favorable value.
- Confirm statistics are up to date.
- Document the reason and conditions for re-evaluating the hint.

## 18. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating `SHOW INDEX.Cardinality` as exact | Mispredicting matching row counts | Remember it is an estimate from statistics/sampling |
| Equating cardinality with predicate selectivity | Misunderstanding value distributions | Separate distinct count from fraction of rows matching predicate |
| Thinking high cardinality always makes an index good | Forcing an index even when reading most of the table | Evaluate matching row counts and row lookups |
| Thinking low cardinality makes an index useless | Ignoring rare values in skewed columns | Check histograms and specific predicates |
| Thinking cost is milliseconds | Invalid comparisons across servers or plans | Use cost to understand choices; use ANALYZE to measure actuals |
| Ignoring `filtered` | Missing how many rows are eliminated post-access | Read together with `rows` and estimated output rows |
| Skipping stats updates after bulk load | Optimizer relies on stale distributions | Run `ANALYZE TABLE` purposefully |
| Raising sample pages on every table | Unnecessary statistics collection overhead | Adjust only tables with unstable estimates |
| Assuming histograms capture multi-column correlation | Combined AND/join estimates remain wrong | Evaluate composite indexes and data correlation |
| Running EXPLAIN ANALYZE on heavy production queries | Real query causes heavy load | Bound data, use an appropriate environment, assess risk |
| Forcing FORCE INDEX too early | Plan goes stale as data evolves | Fix stats/indexes/queries first; use hints only with evidence |

## 19. Practice Exercises

1. Create the fixture from Section 6. Use `COUNT(DISTINCT ...)` to measure true cardinality of `customer_id`, `status`, and `region`.
2. Run `ANALYZE TABLE` and `SHOW INDEX`. Compare estimated cardinality against exact distinct counts.
3. Create composite index `(customer_id, created_at)`. Explain the cardinality of each prefix and the leftmost prefix rule.
4. Compare `EXPLAIN` for `status = 'OPEN'` and `status = 'CLOSED'` before creating a histogram.
5. Create a histogram on `status`, inspect `INFORMATION_SCHEMA.COLUMN_STATISTICS`, and compare estimates.
6. Create an index on `status`; observe how the optimizer may choose the index for `OPEN` and a scan for `CLOSED` depending on cost.
7. Write a combined predicate on `status` and `region`. Compare estimate with actual and explain correlation effects.
8. Run `EXPLAIN FORMAT=JSON` and locate `rows_examined_per_scan`, `rows_produced_per_join`, `read_cost`, `eval_cost`, and `prefix_cost`.
9. Run `EXPLAIN ANALYZE` on a bounded `SELECT`. Find the first operator where estimated rows differ widely from actual rows.
10. Enable optimizer trace in the session, run a query, and determine why a particular access path was chosen.
11. Alter the data distribution in the lab, re-run `ANALYZE TABLE`, histogram updates, and `EXPLAIN`. Write down before/after observations.
12. Try `FORCE INDEX` in the lab and compare actual runtime against the default plan across multiple predicate values.

## 20. Checklist Before Concluding the Optimizer Picked the Wrong Plan

- [ ] Verified current row counts and data distribution.
- [ ] Distinguished cardinality from predicate selectivity.
- [ ] Checked indexes and per-prefix cardinality.
- [ ] Checked persistent stats, sample pages, and last update time.
- [ ] Considered `ANALYZE TABLE` after large data changes.
- [ ] Reviewed histograms for skewed columns where appropriate.
- [ ] Evaluated correlation across predicates and single-column histogram limits.
- [ ] Read `rows`, `filtered`, access type, `key`, and join order in `EXPLAIN`.
- [ ] Understood cost as a relative unit, not actual runtime.
- [ ] Safely compared estimates against actual rows/loops via `EXPLAIN ANALYZE`.
- [ ] Located the earliest operator with a large discrepancy instead of checking only total time.
- [ ] Used optimizer trace when needed to explain optimizer choices.
- [ ] Applied optimizer hints only after measuring and documenting rationale.
- [ ] Re-measured plan and latency after each individual change.

## 21. Completion Criteria

You have completed this lesson when you can explain index and index-prefix cardinality, calculate predicate selectivity from data, distinguish distinct-value fraction from matching-row fraction, describe how the cost model compares plans, read `rows`/`filtered`/cost in `EXPLAIN`, update persistent statistics and histograms, and use `EXPLAIN ANALYZE` to locate discrepancies between estimates and actuals. You should also be able to state the limitations caused by sampling, skew, correlation, stale statistics, and runtime state.

## References

- [MySQL 8.4 Reference Manual — Optimizer Statistics](https://dev.mysql.com/doc/refman/8.4/en/optimizer-statistics.html)
- [MySQL 8.4 Reference Manual — InnoDB Persistent Statistics](https://dev.mysql.com/doc/refman/8.4/en/innodb-persistent-stats.html)
- [MySQL 8.4 Reference Manual — Optimizer Cost Model](https://dev.mysql.com/doc/refman/8.4/en/cost-model.html)
- [MySQL 8.4 Reference Manual — Optimizer Trace](https://dev.mysql.com/doc/refman/8.4/en/optimizer-tracing.html)
- [MySQL 8.4 Reference Manual — EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
- [MySQL 8.4 Reference Manual — ANALYZE TABLE](https://dev.mysql.com/doc/refman/8.4/en/analyze-table.html)
