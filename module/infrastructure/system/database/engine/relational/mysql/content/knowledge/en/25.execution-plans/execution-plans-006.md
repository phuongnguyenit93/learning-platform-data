# rows, filtered, and Estimated Data Volume After Filtering

When reading MySQL `EXPLAIN`, the two columns `rows` and `filtered` answer two distinct questions: how many rows MySQL projects it must read from a table access step, and what percentage of those rows it projects will still satisfy the filter conditions at this step. Combining the two numbers lets us estimate the volume of rows passed forward to the next step of the plan.

These are optimizer estimates, not actual rows read or returned. If estimates are off by a wide margin, MySQL can choose a suboptimal JOIN order, index, or access method. Therefore, it is essential to understand how to read `rows` and `filtered`, how they affect JOIN cardinality, and how to compare them against actual metrics using `EXPLAIN ANALYZE`.

## 1. `rows` and `filtered` answer two different questions

In tabular `EXPLAIN` output, the relevant columns typically include:

| Column | Meaning |
|---|---|
| `type` | Table/index access type, such as `const`, `eq_ref`, `ref`, `range`, `index`, `ALL` |
| `key` | Index chosen by the optimizer |
| `rows` | Number of rows MySQL estimates it must read/examine per table access |
| `filtered` | Estimated percentage of rows passing filter conditions attached to the table access step |
| `Extra` | Additional information about filtering, sorting, covering index, ICP, and other operations |

`rows` describes the amount of data the access method expects to examine. With `ALL`, it is usually close to the estimated total rows in the table. With `range` or `ref`, it may be just the estimated rows within that index range or lookup.

`filtered` is the percentage of rows from that access step that the optimizer predicts will remain after relevant filter conditions. For example, `filtered = 25` means an estimated 25% remain and roughly 75% are discarded by filters at this step. It is neither a percentage of total rows in the database, nor a cache hit rate or CPU percentage.

Example:

| `rows` | `filtered` | Estimated rows after filtering |
|---:|---:|---:|
| 10,000 | 10% | 1,000 |
| 2,000 | 50% | 1,000 |
| 500 | 100% | 500 |
| 100,000 | 0.1% | 100 |

Basic estimation formula:

```text
estimated_rows_after_filter
    = rows * filtered / 100
```

For example, `rows = 10,000`, `filtered = 10`:

```text
10,000 * 10 / 100 = 1,000 rows
```

The optimizer predicts the access step examines roughly 10,000 rows and roughly 1,000 rows pass the filter to be forwarded.

## 2. `rows` is not necessarily the total number of rows in the table

A common misconception is seeing `rows = 500` and concluding the table only has 500 rows. That figure is an estimate tied to the table's access method in the current plan.

For example, suppose an `orders` table has 5 million rows:

```sql
SELECT id, total_amount
FROM orders
WHERE customer_id = 120;
```

If the optimizer picks index `idx_orders_customer_id`, `rows` might be the estimated number of rows with `customer_id = 120`, say 35. It is not the row count of the whole table.

If the query has no condition usable by an index and the optimizer chooses a full table scan, `rows` will be close to the estimated total rows of the table:

```sql
SELECT *
FROM orders;
```

In this case, `rows` in the plan may be near 5 million, depending on statistics. The number remains an estimate; `EXPLAIN` does not execute the query just to count all data exactly.

### 2.1. Meaning depends on access type

| Access type | General interpretation of `rows` |
|---|---|
| `const`, `system` | At most one row read in this special access type |
| `eq_ref` | Typically at most one matching row per row combination from preceding tables |
| `ref` | Estimated rows matching a key value for a single lookup |
| `range` | Estimated rows within the index range |
| `index` | Estimated entries/rows to traverse during an index scan |
| `ALL` | Estimated rows to scan during a full table scan |

This is a high-level summary. Read it together with `key`, `key_len`, `ref`, `Extra`, access predicates, and JOIN structure. Especially for a table on the inner side of a nested-loop join, the access step may be executed many times.

## 3. `filtered` is the percentage passing the filter

Suppose MySQL accesses 20,000 rows via an index, and then applies remaining conditions:

```sql
WHERE status = 'PAID'
  AND total_amount > 1000000
```

The optimizer predicts 25% of the accessed rows satisfy those filter predicates. `filtered = 25` means roughly one-quarter of the estimated accessed rows remain:

```text
20,000 * 25 / 100 = 5,000 rows
```

`filtered = 100` does not mean the whole table is returned. It means the optimizer predicts 100% of the rows examined by that access step pass the filtering accounted for here. If `rows = 10`, the estimated result after filtering is still just 10.

Conversely, `filtered = 1` does not necessarily mean the query is very fast. If `rows = 10,000,000`, it may still have to examine a huge number of rows just to keep roughly 100,000 rows.

## 4. Reading `rows` and `filtered` together

Never evaluate either column in isolation. Two queries can have vastly different `filtered` values and different costs:

| Query | `rows` | `filtered` | Estimated rows after filtering |
|---|---:|---:|---:|
| A | 100 | 100% | 100 |
| B | 100,000 | 0.1% | 100 |

Both project forwarding 100 rows to the next step, yet B must examine far more rows to get there. If B runs frequently and its filter predicates could be better supported by an index, the access path may need optimization.

Another scenario:

| Query | `rows` | `filtered` | Estimated rows after filtering |
|---|---:|---:|---:|
| C | 10,000 | 80% | 8,000 |
| D | 1,000,000 | 1% | 10,000 |

D keeps only 1%, yet still produces around 10,000 rows after filtering while examining a million rows. A low filtering percentage is not automatically good; you must consider input volume, output volume, and how many times the access step is executed.

## 5. Practical example with the customers table

Create the table:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    region_code CHAR(2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_customers_region (region_code)
) ENGINE=InnoDB;
```

Query:

```sql
EXPLAIN
SELECT id, full_name
FROM customers
WHERE region_code = 'VN'
  AND status = 'ACTIVE';
```

Suppose the illustrative output shows:

| table | type | key | rows | filtered | Extra |
|---|---|---|---:|---:|---|
| customers | ref | idx_customers_region | 40,000 | 25.00 | Using where |

Optimizer prediction:

- Roughly 40,000 rows are accessed through the index on `region_code`.
- Roughly 25% pass the residual condition `status = 'ACTIVE'`.
- Roughly 10,000 rows are passed forward.

This is solely a hypothetical output to illustrate the math, not a fixed output for the schema above. If you later create a composite index `(region_code, status)`, the optimizer may pick it and produce different estimated rows and `filtered` values.

Re-running `EXPLAIN` after adding or changing an index reveals the new access path and estimates. Never infer that a composite index is always better from `rows` alone; weigh write overhead, index size, and the actual workload.

## 6. `rows` and `filtered` in JOINs

In a JOIN, each row in `EXPLAIN` describes a table access step in the order chosen by the optimizer. In a nested-loop join, the inner table is typically accessed once per input row coming from outer tables.

Example:

```sql
SELECT
    c.id,
    o.id,
    o.total_amount
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
WHERE c.region_code = 'VN'
  AND o.status = 'PAID';
```

Suppose the estimated plan is:

| table | access | rows | filtered | After filtering per access |
|---|---|---:|---:|---:|
| c | `ref` | 10,000 | 50% | 5,000 |
| o | `ref` | 4 | 25% | 1 |

Interpretation:

1. The `customers` step estimates accessing 10,000 rows and keeping roughly 5,000 customers.
2. For each forwarded customer, the `orders` step estimates looking up roughly 4 rows.
3. Of those 4 rows, roughly 25% have status PAID, corresponding to an average of 1 matching order per customer.
4. The final output estimate is approximately 5,000 rows, assuming independence and accurate estimates.

The number 4 on the `orders` row is typically an estimate per access/lookup; it does not mean the entire JOIN reads only 4 orders. If that lookup repeats for 5,000 customer rows, the total rows examined by the inner step is far larger.

In practice, the optimizer's cardinality and cost model is more intricate than simple multiplication. This example helps grasp per-scan meaning; do not use it as a substitute for reading the full plan.

### 6.1. Why does JOIN order matter?

If the first step emits 500,000 rows instead of 5,000 rows, an inner lookup examining only 4 rows per call will repeat dramatically more times.

Example:

```text
5,000 outer rows * 4 inner rows per lookup
    = 20,000 inner rows examined (simple estimate)

500,000 outer rows * 4 inner rows per lookup
    = 2,000,000 inner rows examined (simple estimate)
```

Consequently, an inaccuracy in the first step propagates and alters the cost of downstream steps. When reading a JOIN plan, track the row volume passed from each table to the next, rather than just looking for the row with the largest `rows`.

### 6.2. Nested loops and iteration counts

In a nested-loop join, the inner table can be accessed repeatedly. The `rows` column in traditional EXPLAIN is not the cumulative rows processed across all loops. You must factor in the table's position in the join order and, when actual counts are needed, use `EXPLAIN ANALYZE` to inspect `loops`.

If `rows = 4` and the step repeats 5,000 times, you can picture roughly 20,000 examined rows as a simple estimate. Actual numbers depend on execution mechanics, predicates, caching, and join algorithm.

## 7. How do cardinality and selectivity relate?

The optimizer needs to estimate how many rows match conditions in order to pick a plan. Two helpful concepts:

- **Cardinality:** the number of distinct values or value combinations described by statistics, depending on index/statistics context.
- **Selectivity:** the fraction of rows satisfying a condition relative to the input row set.

For example, suppose a table has 1,000,000 customers, of whom 100,000 are in VN:

```text
selectivity(region_code = 'VN')
    = 100,000 / 1,000,000
    = 10%
```

If statistics reflect the distribution accurately, the optimizer can estimate this predicate retains roughly 10% of rows when applied across the whole table.

Index cardinality and column statistics are inputs to estimation. However, skewed distributions, correlations across columns, and complex predicates can cause inaccurate estimates.

## 8. Multi-predicate estimates can be wrong

Suppose the `customers` table has:

- 10% of rows with `region_code = 'VN'`.
- 50% of rows with `status = 'ACTIVE'`.

If the optimizer assumes the two conditions are independent, it may estimate:

```text
10% * 50% = 5%
```

Yet if nearly all VN customers are ACTIVE, the true fraction may be close to 10%. If only 10% of VN customers are ACTIVE, the true fraction may be close to 1%.

This is the column correlation problem. Single-column statistics do not always capture relationships across multiple predicates. Histograms help describe single-column distributions; they do not automatically solve all multi-column correlations.

When `filtered` is off by a large margin, check:

- Are index/column statistics stale?
- Is data distribution skewed?
- Are filtered columns correlated?
- Do predicates use expressions, functions, or type conversions?
- Do query parameters have widely varying distributions?
- Are there conditions depending on another table in a JOIN?

## 9. Distinguishing estimated rows from actual row counts

Standard `EXPLAIN` does not run the query. `rows` and `filtered` are estimates produced by the optimizer from statistics and its cost model.

To see reality, MySQL 8.0.18 and later supports `EXPLAIN ANALYZE` for SELECT queries:

```sql
EXPLAIN ANALYZE
SELECT id, full_name
FROM customers
WHERE region_code = 'VN'
  AND status = 'ACTIVE';
```

TREE output may contain information like:

```text
-> Index lookup on customers using idx_customers_region (region_code='VN')
   (cost=... rows=40000)
   (actual time=... rows=10000 loops=1)
```

The numbers above are illustrative examples:

- `cost` and `rows` are optimizer estimates.
- `actual time` is the actual execution time of the iterator.
- `actual rows` is the actual average rows emitted per iterator execution.
- `loops` is the number of times the iterator was executed.

In this example, the iterator returned 10,000 actual rows in one run, whereas the estimate was 40,000. This suggests the cardinality estimate is roughly four times higher than reality.

### 9.1. Calculating total rows across loops

For an iterator with `actual rows = 3` and `loops = 1,000`, the average rows per loop is 3; total rows across all loops is approximately:

```text
3 * 1,000 = 3,000 rows
```

Do not compare `rows` in traditional EXPLAIN against total actual rows across all loops without converting to the same unit. Compare per-scan to per-loop, or convert both to total rows for the iterator.

### 9.2. EXPLAIN ANALYZE executes the query

`EXPLAIN ANALYZE` executes the SELECT statement to gather actual metrics. Do not run it carelessly on very heavy queries in production because the measurement itself consumes CPU, I/O, and time. It is also not a replacement for concurrent workload benchmarking.

## 10. Evaluating estimate/actual discrepancy

A simple approach is computing the ratio:

```text
estimate_ratio = estimated_rows / actual_rows
```

Example:

| Estimate | Actual | Observation |
|---:|---:|---|
| 10,000 | 9,500 | Fairly close |
| 100,000 | 10,000 | Overestimated by 10x |
| 1,000 | 50,000 | Underestimated by 50x |
| 0 or near 0 | Many actual rows | Inspect statistics and special predicates |

No single threshold applies to every query. A 10x error on a step returning 1 row may be negligible; a 10x error on the outer table of a nested-loop join can massively inflate inner lookup counts.

Prioritize investigating discrepancies:

- On the outer table of a nested-loop join.
- When estimated rows are small yet actual rows are huge.
- When the chosen access path is based on wrong selectivity.
- When the query runs frequently and consumes heavy resources.

## 11. Using EXPLAIN FORMAT=JSON to inspect cardinality

JSON provides additional detail on estimates:

```sql
EXPLAIN FORMAT=JSON
SELECT
    c.id,
    o.id
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
WHERE c.region_code = 'VN'
  AND o.status = 'PAID';
```

Useful properties typically include:

| Property | General meaning |
|---|---|
| `rows_examined_per_scan` | Estimated rows examined per table access |
| `rows_produced_per_join` | Estimated rows produced after the corresponding join step |
| `filtered` | Estimated percentage remaining after filtering |
| `access_type` | Table access method |
| `key` | Selected index |
| `used_key_parts` | Key parts used |
| `attached_condition` | Condition attached to the access/evaluation step |
| `cost_info` | Estimated cost breakdown |

Field names and JSON nesting depend on plan type and version. Read the full structure instead of looking for a fixed field in every query.

`rows_examined_per_scan` clarifies rows for one scan; `rows_produced_per_join` reflects cumulative estimated output after the join step. These two fields do not share the same unit and should not be compared directly.

## 12. When rows is large yet filtered is small

Example:

| `rows` | `filtered` | After filtering |
|---:|---:|---:|
| 1,000,000 | 0.01% | 100 |

The optimizer projects examining a million rows to retain roughly 100. This can indicate the access path needs improvement.

Options to consider:

1. Can a composite index be added so a more selective predicate participates in range access?
2. Does index column order align with equality/range predicates?
3. Can a different index reduce the number of entries scanned?
4. Do statistics reflect current data distribution?
5. Can functions or implicit conversions on filtered columns be eliminated?
6. Can input rows be reduced prior to the JOIN?

However, not every low `filtered` requires a new index. If a query must read most of the data to return a large result or compute aggregations, a full scan can be a reasonable plan.

## 13. When rows is small yet filtered is low

Example:

| `rows` | `filtered` | After filtering |
|---:|---:|---:|
| 20 | 5% | 1 |

The optimizer projects accessing 20 rows and retaining roughly 1. This can be an excellent access path even though `filtered` is only 5%.

Do not try to force `filtered` up to 100% by adding an index covering every column when the number of rows examined is already tiny. Extra indexes carry write, storage, and maintenance costs; optimization must weigh total cost.

## 14. `filtered` and `Using where`

`Using where` in the `Extra` column indicates a WHERE condition is applied to filter rows. `filtered` is the optimizer's estimated percentage of rows surviving filtering for the access step.

The two are related but not identical:

- `Using where` describes execution behavior in the plan.
- `filtered` is an estimated percentage.
- Seeing `Using where` does not mean `filtered` must be low.
- `filtered = 100` does not mean there is no WHERE clause; the condition may already have bounded the access range, or the optimizer estimates all rows in the accessed set pass.

If the query uses ICP, part of the condition is checked inside the storage engine. Read `Extra` values like `Using index condition` alongside `Using where` and JSON fields to see which filtering happens where. Do not assume `filtered` directly measures how many full-row reads ICP avoided.

## 15. Statistics affect rows and filtered

The optimizer uses statistics to estimate cardinality and selectivity. In InnoDB, index statistics are persisted and may be sampled; results can change after data shifts or statistics updates.

Common commands:

```sql
SHOW INDEX FROM customers;
```

```sql
ANALYZE TABLE customers;
```

`SHOW INDEX` displays index metadata such as estimated `Cardinality`. `ANALYZE TABLE` instructs MySQL to refresh statistics for the table. In InnoDB, statistics involve sampling, so cardinality remains an estimate rather than an exact count.

With skewed data distributions, histograms can help the optimizer better estimate single-column predicates:

```sql
ANALYZE TABLE customers
UPDATE HISTOGRAM ON region_code, status
WITH 100 BUCKETS;
```

A histogram describes the distribution of each selected column. It can improve estimates for single-column conditions, yet it does not automatically model correlations between `region_code` and `status`.

Do not run ANALYZE TABLE or create histograms in production merely as an experiment without assessing impact, required privileges, and workload behavior. After refreshing statistics, compare plans and actual performance.

## 16. Causes of inaccurate estimates

| Cause | Visible symptom | Investigation direction |
|---|---|---|
| Stale statistics | `rows`/`filtered` no longer match data | Check last ANALYZE time; consider updating statistics |
| Data skew | Common and rare values estimated similarly | Check histograms and actual value distribution |
| Column correlation | Product of single-column selectivities is wrong | Inspect joint distribution, not just individual columns |
| Predicates using functions | Hard to estimate or unable to use index efficiently | Check expressions, generated columns/indexes if justified |
| Implicit conversion/collation | Access path and selectivity differ from expectations | Check data types, charset/collation, and EXPLAIN |
| Skewed parameter distribution | One plan does not suit all parameter values | Measure multiple representative values |
| Join fan-out | Post-join row estimates severely off | Check uniqueness, FKs, indexes, and relationship cardinality |
| Temp tables/derived tables | Estimates depend on materialization and query rewrites | Read JSON/TREE plan and actual rows |

## 17. Workflow for analyzing rows and filtered

When a query is slow:

1. Run `EXPLAIN` to get access type, key, rows, filtered, and Extra.
2. For each table, clarify whether `rows` is a per-scan estimate and which access path applies.
3. Compute `rows * filtered / 100` to estimate rows passing the filter at that step.
4. For JOINs, inspect the outer table and how many times inner tables are accessed.
5. Use `EXPLAIN FORMAT=JSON` to inspect rows examined per scan and rows produced per join.
6. Use `EXPLAIN ANALYZE` to obtain actual rows, loops, and timings.
7. Compare estimates against actuals using matching units.
8. If discrepancies are large, investigate statistics, skew, correlation, predicates, and join fan-out.
9. Only change indexes or queries after understanding which step generates excessive data volume.
10. Re-run EXPLAIN/ANALYZE on representative parameters to confirm improvement.

## 18. Example analyzing a JOIN with inaccurate estimates

Query:

```sql
SELECT
    c.id,
    o.id,
    o.total_amount
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
WHERE c.region_code = 'VN'
  AND c.status = 'ACTIVE'
  AND o.created_at >= '2026-01-01';
```

Suppose `EXPLAIN` estimates:

| table | rows | filtered | Estimated after filtering |
|---|---:|---:|---:|
| c | 50,000 | 20% | 10,000 |
| o | 8 | 50% | 4 per lookup |

If actual `customers` has only 500 rows, the optimizer overestimated by 20x. If `orders` is looked up 500 times instead of 10,000 times, total inner accesses will be far lower than projected.

If actual `customers` has 200,000 rows, the optimizer severely underestimated and the `orders` lookup step can execute far more times than expected.

Inspect statistics on `region_code` and `status`, especially when the two columns are correlated. If needed, evaluate histograms per column, a composite index `(region_code, status)`, and the resulting JOIN plan. Then re-measure actual rows/loops; never draw conclusions solely because `rows` dropped in EXPLAIN.

## 19. Common misconceptions

| Misconception | Reality |
|---|---|
| `rows` is the exact number of rows returned | It is the estimated rows to examine under the access path |
| `rows` always equals total table rows | It depends on access type and access conditions |
| `filtered = 10` means only 10 rows are read | It means an estimated 10% of accessed rows pass the filter |
| `filtered = 100` means there is no WHERE clause | Predicates may already be in the access path or all accessed rows are estimated to pass |
| `rows * filtered` is the actual row count | It is an estimate, not an actual row count |
| `rows` on an inner JOIN table is the whole JOIN total | It is typically an estimate per scan/lookup, which can repeat many times |
| Lower `filtered` is always better | You must consider both input rows and surviving rows |
| Small `rows` always means a fast query | Performance also depends on loops, row width, I/O, sorts, locks, and other iterators |
| `EXPLAIN ANALYZE` only shows estimates | It executes the SELECT and displays actual metrics alongside estimates |
| ANALYZE TABLE produces exact statistics | InnoDB statistics can rely on sampling and remain estimates |

## 20. Checklist for reading rows and filtered

- Which access path does `rows` describe, and how many rows per access?
- Is the access type `range`, `ref`, `eq_ref`, `index`, or `ALL`?
- What percentage surviving filtering does `filtered` represent?
- How many estimated rows does `rows * filtered / 100` yield?
- Is the table on the inner side of a nested-loop join and repeated many times?
- Is the volume of rows forwarded from the outer table too large?
- Do estimates diverge significantly from actual rows/loops?
- Are index/column statistics stale or missing?
- Does the data exhibit skew or correlation across columns?
- Do predicates involve functions, implicit conversions, or hard-to-estimate conditions?
- Could an index reduce rows examined rather than filtering only after reading?
- Have you re-measured with `EXPLAIN ANALYZE` on representative parameters?

## Conclusion

In `EXPLAIN`, `rows` is the number of rows the optimizer estimates it must examine for a table access; `filtered` is the estimated percentage of rows remaining after filtering. Multiplying `rows * filtered / 100` gives the estimated volume of rows passed to the next step, though it is not an actual measurement. For JOINs, pay attention to inner-table lookup counts and cumulative rows from preceding steps. Use `EXPLAIN FORMAT=JSON` for detailed cardinality, `EXPLAIN ANALYZE` to cross-check actual rows/loops/timings, and then investigate statistics, skew, correlation, and indexes when discrepancies are large. Reading these two numbers properly helps explain optimizer choices and pinpoint the exact step inflating data volume in an execution plan.
