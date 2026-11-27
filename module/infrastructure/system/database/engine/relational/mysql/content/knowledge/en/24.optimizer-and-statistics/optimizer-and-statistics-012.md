# Optimizer and Statistics

## Optimizer Trace and Verifying Optimization Decisions

`EXPLAIN` shows the plan MySQL chose, yet it often hides the alternatives the optimizer evaluated and rejected. When you need to understand why MySQL picked a table scan instead of an index, chose a particular `JOIN` order, skipped a range scan, or added an extra sort, you can enable **optimizer trace**. The trace records statement preparation and optimization steps, including candidate access paths, row estimates, costs, and reasons why certain options were chosen or discarded.

Optimizer trace is a tool for explaining planning decisions. It does not measure actual execution time and does not replace `EXPLAIN ANALYZE`, the slow query log, or Performance Schema. To find the root cause of a slow query, cross-check the trace with the final plan, data statistics, and runtime metrics.

### 1. What Questions Does Optimizer Trace Answer?

The trace is useful when you have a specific query and want to see how the optimizer reached its decision. Typical questions include:

- Why did the optimizer pick `ALL` (full table scan) even though the table has an index covering the columns?
- Why did an index appear in the candidate list yet go unchosen?
- Why did the optimizer pick join order A before B rather than B before A?
- Why does the query require `filesort` or a temporary table despite having an index?
- Why did the `WHERE` condition fail to generate a range scan?
- Why did the optimizer pick a different plan after updating statistics?
- Which decision was affected by a change in `optimizer_switch`, indexes, or predicate phrasing?

The trace shows the steps the optimizer took and the estimates used for comparison. It helps form hypotheses about root causes, which must still be confirmed against real data and measurements.

### 2. Enabling Trace and Retrieving Output in the Same Session

Optimizer trace is controlled via session variables. Enable trace before running the statement under analysis, run the query, read the trace immediately in the same connection, and then turn trace off:

```sql
SET SESSION optimizer_trace = 'enabled=on';
SET SESSION optimizer_trace_max_mem_size = 1048576;

SELECT id, customer_id, created_at, total
FROM orders
WHERE status = 'paid'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
ORDER BY created_at DESC
LIMIT 100;

SELECT
    QUERY,
    MISSING_BYTES_BEYOND_MAX_MEM_SIZE,
    INSUFFICIENT_PRIVILEGES,
    TRACE
FROM INFORMATION_SCHEMA.OPTIMIZER_TRACE;

SET SESSION optimizer_trace = 'enabled=off';
```

In this example, `optimizer_trace_max_mem_size` sets the memory cap for the session's trace content. You can format the JSON more legibly with `JSON_PRETTY`:

```sql
SELECT
    QUERY,
    MISSING_BYTES_BEYOND_MAX_MEM_SIZE,
    INSUFFICIENT_PRIVILEGES,
    JSON_PRETTY(TRACE) AS TRACE_PRETTY
FROM INFORMATION_SCHEMA.OPTIMIZER_TRACE;
```

Key points to remember:

1. Enable trace before the target statement; queries run beforehand have no recorded trace.
2. Read `INFORMATION_SCHEMA.OPTIMIZER_TRACE` right after the target statement in the same session. Do not switch to another connection in a connection pool.
3. If the trace was truncated due to the memory cap, `MISSING_BYTES_BEYOND_MAX_MEM_SIZE` reports how many bytes were dropped. Raise the limit adequately and re-run.
4. `INSUFFICIENT_PRIVILEGES` indicates whether the trace could not be fully displayed due to missing permissions.
5. Turn trace off when done to avoid recording traces for unrelated statements.

To inspect the plan without running the real `SELECT`, enable trace and run `EXPLAIN` on the query. By contrast, `EXPLAIN ANALYZE` actually executes the analyzed statement; use it only when query execution cost is acceptable.

### 3. Reading the Overall Trace Structure

The trace is typically JSON with a `steps` field. For a `SELECT` statement, common top-level sections include:

| Section | Meaning |
| --- | --- |
| `join_preparation` | Query block preparation, syntax expansion, and initial transformations |
| `join_optimization` | Condition optimization, row estimation, access path evaluation, and `JOIN` ordering |
| `join_execution` | Execution-stage details if recorded for the statement type and MySQL version |

Within `join_optimization`, sub-steps typically include information such as:

- `condition_processing`: condition transformation and simplification.
- `table_dependencies`: dependency relationships among tables in the query block.
- `ref_optimizer_key_uses`: index lookup possibilities via reference equality.
- `rows_estimation`: row estimation and range access evaluation.
- `considered_execution_plans`: evaluated access paths and `JOIN` orders.
- `attaching_conditions_to_tables`: predicates attached to each table in the plan.
- `refine_plan` or plan-refinement steps: adjustments to the chosen plan.

Node names, layouts, and granularity can vary by MySQL version, statement type, and optimizer features used. Read the trace as a structured decision tree rather than hardcoding assumptions on a single JSON path.

### 4. The join_preparation Step: How Did the Optimizer Normalize the Query?

`join_preparation` usually shows the statement after MySQL expands syntax and prepares query blocks. Common nodes include:

- `expanded_query`: expanded query form, such as resolved expressions or normalized column references.
- Subquery, view, or derived table transformation steps where applicable.
- Query block metadata and post-preparation query structure.

This section is helpful when queries involve views, subqueries, expressions, or deeply nested conditions. It shows what structure the optimizer actually optimizes after initial rewrites.

For example, predicates with constant expressions may be simplified before choosing an access path. If querying through a view, check whether the view was merged into the query block or handled as a derived table/materialized result. That handling can alter usable indexes and `JOIN` order.

### 5. condition_processing: How Were Conditions Transformed?

The optimizer can perform logical rewrites to simplify conditions. The trace can show steps such as:

- `equality_propagation`: propagating equalities across equivalent expressions.
- `constant_propagation`: substituting known constant values for expressions.
- `trivial_condition_removal`: removing tautological or redundant predicates.

Example:

```sql
SELECT o.id, o.total
FROM orders AS o
JOIN customers AS c ON c.id = o.customer_id
WHERE c.id = 42
  AND o.status = 'paid';
```

From `c.id = 42` and the `JOIN` predicate `c.id = o.customer_id`, the optimizer can infer an equivalent predicate on `o.customer_id`. This can open up an index access path on `orders` that the author never explicitly wrote in `WHERE`.

When reading the trace, compare input conditions with post-transformation conditions. If a condition was removed or rewritten into another expression, understand why before concluding the optimizer dropped a business rule.

### 6. rows_estimation and range_analysis: How Does the Optimizer Estimate Rows?

This is one of the most critical sections when investigating index selection. The optimizer must estimate how many rows each access path reads to compute costs. The trace can contain:

- `potential_range_indexes`: indexes eligible for range analysis and their usability status.
- `range_analysis`: evaluation of predicates capable of producing a range scan.
- `range_scan_alternatives`: range scan candidates per index, including row estimates and costs.
- `analyzing_roworder_intersect` or index merge details if the optimizer evaluates combining multiple indexes.
- `chosen_range_access_summary`: summary of the selected range plan, if any.

Not every query contains all of these nodes. If a condition fails to produce a valid range, the optimizer may discard an index before comparing range scan costs.

For example, an `orders` table with indexes:

```sql
CREATE TABLE orders (
    id BIGINT NOT NULL PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total DECIMAL(12, 2) NOT NULL,
    KEY idx_status_created (status, created_at),
    KEY idx_created (created_at)
) ENGINE = InnoDB;
```

Query filtering on status and a date interval:

```sql
SELECT id, customer_id, created_at, total
FROM orders
WHERE status = 'paid'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
ORDER BY created_at DESC
LIMIT 100;
```

When reading `range_analysis`, look for `idx_status_created` and `idx_created`. Check whether the optimizer built a range for each index, how many rows it estimated reading, estimated cost, and which candidate was marked `chosen` or summarized as best. With `status` pinned via equality, composite index `(status, created_at)` can narrow by time range and provide time ordering within that status slice.

If the optimizer picks `idx_created` or a table scan, do not jump to assuming a bug. `paid` might dominate the table, the time interval might be too broad, or clustered-record lookups might make the composite index costlier. Cross-check row estimates and costs in the trace against actual data distributions.

### 7. Why Can an Index Be Rejected Even When Its Column Appears in WHERE?

Having an index on a column does not mean every condition on that column yields a range scan. Common reasons include:

1. The column is wrapped in a function or expression not matching a functional index.
2. Comparing mismatched data types triggers implicit conversion on the indexed column.
3. The condition is not sargable to define a contiguous index interval.
4. A leading key part in a composite index is unconstrained or unusable for the predicate.
5. The matching range is too wide, making an index scan plus row lookups costlier than a table scan.
6. Statistics or histograms misrepresent data distribution, distorting estimates.

Example of a condition unfavorable to a regular index on `created_at`:

```sql
SELECT id, created_at
FROM orders
WHERE DATE(created_at) = '2026-01-15';
```

Because `DATE()` is applied directly to the column, a standard B-tree index on `created_at` cannot directly use a simple range for this predicate. It can be rewritten as a half-open interval:

```sql
SELECT id, created_at
FROM orders
WHERE created_at >= '2026-01-15 00:00:00'
  AND created_at <  '2026-01-16 00:00:00';
```

After rewriting, re-run trace to see whether `range_analysis` forms an interval on `idx_created`. Comparing before and after traces reveals changes in range construction and chosen access paths.

### 8. considered_execution_plans: Comparing Access Plans and JOIN Order

For multi-table queries, the optimizer must choose how to access each table and in what `JOIN` order. `considered_execution_plans` typically lists evaluated plan prefixes and access paths. You may encounter fields such as `plan_prefix`, `table`, `best_access_path`, `considered_access_paths`, `cost_for_plan`, `rows_for_plan`, or `chosen`, depending on version and optimization branch.

Example:

```sql
SELECT o.id, o.total, c.name
FROM customers AS c
JOIN orders AS o ON o.customer_id = c.id
WHERE c.region = 'south'
  AND o.created_at >= '2026-01-01'
ORDER BY o.created_at DESC
LIMIT 100;
```

The optimizer may consider:

- Reading customers with `region = 'south'` first, then looking up orders by `customer_id`.
- Reading orders in the date range first, then looking up customers by primary key.
- Picking another access path if row estimates or costs change.

In the trace, compare each plan prefix, estimated post-join rows, cumulative cost, and reason a plan was rejected. If the final plan starts from `orders`, check whether the trace estimated the time filter on `orders` to be more selective than the `south` customer set.

Table order in SQL is not necessarily execution order. For inner joins, the optimizer can usually reorder joins based on cost. Outer joins and semantic dependencies can restrict valid orders.

### 9. Reading Cost and Rows Properly

Traces typically contain estimates named `rows`, `cost`, `read_cost`, `eval_cost`, `prefix_cost`, `rows_for_plan`, or similar. Understand these as internal cost-model values, not millisecond durations.

| Value | Interpretation |
| --- | --- |
| `rows` | Estimated rows an access path reads or emits at a step |
| `cost` | Estimated cost for an alternative within its node scope |
| `read_cost` | Data/index read cost component under the cost model |
| `eval_cost` | Condition evaluation or row-processing cost component under the cost model |
| `prefix_cost` | Cumulative cost of a plan prefix in certain trace sections |
| `rows_for_plan` | Estimated row count of the plan after joined steps |

Names and cost breakdowns depend on version and access path type. Never compare a cost figure directly across two servers with different configs, statistics, or versions as if it were a timing benchmark. Use cost to understand how the optimizer compares options in the same context; use runtime metrics to measure actual performance.

If estimated `rows` diverge wildly from actual rows, check index statistics, histograms, data skew, column correlations, and query predicates. The optimizer may pick a plan that is completely rational given the statistics it sees, while those statistics themselves are inaccurate.

### 10. Cross-Checking Trace with EXPLAIN and EXPLAIN ANALYZE

The four tools serve distinct roles:

| Tool | Question Answered | Executes the SELECT Query? |
| --- | --- | --- |
| `EXPLAIN` | What is the final plan chosen by the optimizer? | Does not execute the `SELECT` portion to return results |
| `EXPLAIN FORMAT=JSON` | What is the final plan and detailed JSON estimates? | Does not execute the `SELECT` portion to return results |
| Optimizer trace | Which alternatives did the optimizer consider and why did it pick/reject them? | Trace records optimization decisions; reading the trace itself is not a runtime benchmark |
| `EXPLAIN ANALYZE` | How long did actual iterators run, how many loops, and how many rows? | Yes, the query is executed |

An investigative flow should move from high-level outcome to root cause:

1. Run `EXPLAIN` to inspect tables, access types, keys, estimated rows, and `Extra`.
2. Use optimizer trace to inspect candidates and reasons for picking access paths or join order.
3. Run `EXPLAIN ANALYZE` on safely runnable queries to compare actual rows and timings against estimates.
4. If the plan is sound yet the query remains slow, investigate I/O, buffer pool residency, lock waits, concurrency, network, and returned data volume.

Example:

```sql
EXPLAIN FORMAT=JSON
SELECT id, customer_id, created_at, total
FROM orders
WHERE status = 'paid'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
ORDER BY created_at DESC
LIMIT 100;

EXPLAIN ANALYZE
SELECT id, customer_id, created_at, total
FROM orders
WHERE status = 'paid'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
ORDER BY created_at DESC
LIMIT 100;
```

`EXPLAIN ANALYZE` has been available since MySQL 8.0.18. Be cautious with heavy queries because it actually executes them; do not treat it as a passive plan-only command in production without load assessment.

### 11. Using Trace to Investigate a Table Scan Choice

Suppose index `idx_status(status)` exists, yet the following query still picks a full table scan:

```sql
SELECT id, status, total
FROM orders
WHERE status = 'paid';
```

The trace may show that the optimizer inspected the index, estimated `paid` rows make up a large fraction, and concluded that reading most of the secondary index and hopping back to the clustered index for `total` is costlier than scanning the clustered index sequentially. That can be a sensible decision when selectivity is low.

Check:

- `potential_range_indexes`: was the index even considered?
- `range_scan_alternatives`: was a range scan valid and how many rows did it estimate?
- `considered_access_paths`: what costs were computed for table scan, index scan, or ref/range?
- `chosen`/`cause` or equivalent summary: which option won and why?
- Do `CARDINALITY`, histograms, and actual row counts accurately reflect the `paid` ratio?

Do not use `FORCE INDEX` simply to force index usage after spotting a table scan. First confirm whether the query truly benefits from an index, whether a covering index is feasible, and whether the table scan is genuinely slow on current data. A full scan is sometimes the best plan.

### 12. Using Trace to Investigate Filesort or Temporary Tables

When `EXPLAIN` reports `Using filesort` or `Using temporary`, inspect filter conditions, column ordering, and index direction. The optimizer may be unable to leverage index order because:

- Key parts preceding the sort column are not pinned to constants.
- `ASC`/`DESC` directions of key parts do not match `ORDER BY` via a forward or backward scan.
- The query sorts on an expression or collation incompatible with the index.
- `JOIN` order or derived table materialization disrupts index order.
- The estimated benefit of ordered index access does not offset row lookup cost.

The trace may reveal ordering candidates and decisions inside query block optimization steps. Exact structure varies by version; look for nodes relating to ordering, `filesort`, grouping, temporary tables, or access paths instead of relying on a fixed path.

After modifying an index, re-run the same query and compare traces. If `Using filesort` disappears yet runtime does not improve, the query may be bottlenecked by other I/O, result set size, random lookups, or `JOIN` cost.

### 13. Comparing Traces Before and After Updating Statistics

The optimizer makes decisions using index statistics and available distribution data. If statistics are stale or lack detail, estimated row counts can drift.

Example updating index statistics:

```sql
ANALYZE TABLE orders;
```

For heavily skewed columns, MySQL supports histograms:

```sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status WITH 32 BUCKETS;
```

You can inspect histograms in `INFORMATION_SCHEMA.COLUMN_STATISTICS` on supported versions. When a histogram needs to be removed:

```sql
ANALYZE TABLE orders
DROP HISTOGRAM ON status;
```

To assess impact, keep the query and parameters identical, capture a trace before refreshing statistics, run `ANALYZE TABLE` or modify the histogram, and capture the trace again. Compare:

1. Row estimates in `rows_estimation`.
2. Evaluated ranges and index candidates.
3. Cost of each access path.
4. Chosen `JOIN` order.
5. Final plan in `EXPLAIN` and actual metrics in `EXPLAIN ANALYZE`.

Histograms can improve estimates for single-column distributions, yet they do not fully describe multi-column correlations. If `status` and `created_at` correlate over time, a single-column histogram may not suffice to accurately estimate combined conditions.

### 14. Comparing Traces When Changing optimizer_switch or Indexes

When testing an optimizer feature, you can adjust `optimizer_switch` at session scope in a test environment:

```sql
SELECT @@SESSION.optimizer_switch;

SET SESSION optimizer_switch = 'index_merge=off';

-- Enable optimizer trace, run the query, and retrieve the trace for comparison.

SET SESSION optimizer_switch = DEFAULT;
```

This is merely an example testing `index_merge`; option names and valid values depend on version. Do not change `GLOBAL` settings or disable features wholesale in production just because one trace shows an unexpected plan.

You can use an invisible index to test the impact of removing an index from optimizer consideration without physically dropping it. Before-and-after traces reveal which access path the optimizer switches to. Note that invisible indexes are still maintained on writes; this test evaluates optimizer read choices, not write-cost savings after index removal.

When comparing, change only one variable at a time. Changing indexes, histograms, `optimizer_switch`, and SQL simultaneously makes it hard to isolate what altered the plan.

### 15. Limitations and What Traces Cannot Conclude

Optimizer trace has diagnostic value, yet comes with boundaries:

- Traces describe optimization decisions and estimates, not actual execution times.
- Traces can be truncated by `optimizer_trace_max_mem_size`; always check `MISSING_BYTES_BEYOND_MAX_MEM_SIZE`.
- Certain details may be omitted due to privileges, statement types, features, or version.
- JSON node names and layouts can change; automated parsers must tolerate missing or shifted nodes.
- The optimizer may choose well according to statistics while runtime remains slow due to cache misses, I/O, lock waits, contention, network, or huge result sets.
- A query running fast on the second measurement may simply reflect warmed buffer pool pages; do not attribute the entire difference to the plan.
- Internal cost is not milliseconds and cannot be compared arbitrarily across differently configured servers.

Do not retain traces indefinitely if they contain sensitive SQL or literal values. When sharing traces for troubleshooting, follow data-protection policies and redact identifying details appropriately.

### 16. Repeatable Diagnostic Workflow

1. **Capture baseline:** save SQL, parameters, MySQL version, `optimizer_switch`, table statistics, and current `EXPLAIN`.
2. **Enable trace:** use the same session, raise memory cap if needed, and execute the exact statement under analysis.
3. **Read trace:** inspect `join_preparation`, `condition_processing`, `rows_estimation`, `range_analysis`, and `considered_execution_plans`.
4. **Identify decision points:** locate rejected candidates, estimated rows/costs, and the final chosen plan.
5. **Verify against data:** check cardinality, histograms, skew, column correlations, and predicate sargability.
6. **Change one factor:** SQL, index, statistics, or optimizer setting; state a clear hypothesis before testing.
7. **Re-measure:** compare trace, `EXPLAIN`, `EXPLAIN ANALYZE`, latency, and resources.
8. **Keep or revert:** retain a change only if it improves representative workloads without causing significant regressions on other queries.

### 17. Checklist When Reading Optimizer Trace

1. Does the trace correspond to the exact SQL and session?
2. Is `MISSING_BYTES_BEYOND_MAX_MEM_SIZE` equal to `0`?
3. Does `INSUFFICIENT_PRIVILEGES` indicate missing trace details?
4. How was the query expanded/transformed in `join_preparation`?
5. Were conditions in `condition_processing` propagated or simplified as expected?
6. Which indexes appeared in `potential_range_indexes` and `range_scan_alternatives`?
7. Are estimated row counts and costs reasonable against real data?
8. Which access paths and join orders were evaluated, and which were rejected?
9. Does the final plan match `EXPLAIN`?
10. Do `EXPLAIN ANALYZE` and runtime metrics confirm real improvement?

Optimizer trace turns the question "why did MySQL pick this plan?" into an evidence-based investigation: inspect post-transformation predicates, candidate indexes/ranges, row and cost estimates, and `JOIN` order, then cross-check against the final plan and execution metrics. Used properly alongside `EXPLAIN`, `EXPLAIN ANALYZE`, and statistics, trace enables grounded adjustments to SQL, indexes, and statistics.
