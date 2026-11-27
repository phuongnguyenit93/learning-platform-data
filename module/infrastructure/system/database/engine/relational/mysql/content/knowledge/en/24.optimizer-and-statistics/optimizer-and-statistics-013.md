# Evaluating Plan Regressions After Data Loads or Upgrades

A query that used to run fast can slow down after loading more data, shifting value distributions, or upgrading MySQL. Causes can include the optimizer choosing a different access path, statistics no longer reflecting data, missing or stale histograms, altered indexes, or higher actual execution costs even when the plan itself stayed identical.

Evaluating execution plan regression is the process of comparing the plan and performance of the same workload before and after a change. The goal is to pinpoint what changed, uncover evidence-backed root causes, and choose appropriate remedies. Never jump to conclusions solely because a SQL statement slowed down or from a single `key` column in `EXPLAIN`.

## 1. Distinguishing Plan Regression from Performance Regression

These two phenomena are related yet distinct:

- **Plan regression:** the optimizer picks a different access path or join order—for example, switching from an index range scan to a full table scan, changing join order, or adding a sort step.
- **Performance regression:** execution time, rows read, CPU, or I/O degrades. This can happen even when the plan stays identical—for instance, due to data growth, cold caches, busy storage, or higher concurrency.

When investigating, compare estimated plans, actual row counts, and execution times together. A different plan is not automatically worse; the optimizer may have selected a new plan that is faster on current data. Conversely, an identical plan can still slow down because total work increased.

## 2. Capturing a Baseline Before Data Loads or Upgrades

A baseline is the reference set used for comparison after a change. For every critical query, record:

1. The SQL text or query digest, along with representative parameter values.
2. MySQL version, storage engine, schema, indexes, and relevant optimizer configuration.
3. The `EXPLAIN` plan (ideally saving `JSON` or `TREE` formats as well when supported).
4. Estimated rows, actual rows, loop counts, and execution times.
5. Mean latency and percentiles such as p95/p99, execution counts, rows examined, and rows sent.
6. Measurement conditions: data volume, timestamp, concurrent load, and cache state.

Example environment check:

```sql
SELECT VERSION() AS mysql_version,
       @@version_comment AS version_comment,
       @@SESSION.optimizer_switch AS optimizer_switch;

SHOW CREATE TABLE orders;
SHOW INDEX FROM orders;
```

Store baseline artifacts outside the test session or in your team's change-management system. When comparing, keep SQL text, parameter types, representative data, and load conditions as consistent as possible. Upgrading MySQL, modifying indexes, and changing optimizer settings simultaneously makes it nearly impossible to tell which factor caused a difference.

## 3. Gathering Queries to Evaluate

Do not inspect only the single query just reported as slow. Look for queries with high total execution time, high frequency, high rows examined, or high tail latency.

If Performance Schema is collecting statement digests, you can inspect time-consuming queries in the current schema:

```sql
SELECT DIGEST_TEXT,
       COUNT_STAR,
       ROUND(SUM_TIMER_WAIT / 1000000000000, 2) AS total_seconds,
       ROUND(AVG_TIMER_WAIT / 1000000000, 2) AS avg_ms,
       SUM_ROWS_EXAMINED,
       SUM_ROWS_SENT
FROM performance_schema.events_statements_summary_by_digest
WHERE SCHEMA_NAME = DATABASE()
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Performance Schema timers are expressed in picoseconds; the divisions above convert total time to seconds and average time to milliseconds. Summary tables hold cumulative counters since statistics were initialized or reset, not per-execution history. Capture snapshots at two timestamps or use monitoring tools to calculate deltas across an observation window.

You can also inspect `sys.statement_analysis` if the `sys` schema is installed and your user has read privileges. This view sorts digests by total latency, average latency, and rows examined. The slow query log is also useful for capturing executions exceeding thresholds, provided log retention and disk sizing are managed properly.

## 4. Comparing Plans with EXPLAIN

`EXPLAIN` reveals how the optimizer expects to execute a statement. Example:

```sql
EXPLAIN
SELECT order_id, customer_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC
LIMIT 50;
```

With traditional tabular output, pay attention to:

- `possible_keys`: candidate indexes the optimizer considered.
- `key`: index actually selected.
- `key_len`: length of the key prefix used; interpret alongside data types, nullability, and index structure.
- `type`: access type such as `const`, `eq_ref`, `ref`, `range`, or `ALL`.
- `rows` and `filtered`: estimated rows to read and estimated percentage remaining after filtering.
- `Extra`: details such as `Using filesort`, `Using temporary`, `Using index`, or `Using index condition`.

Use JSON to inspect predicate details and estimated costs:

```sql
EXPLAIN FORMAT=JSON
SELECT order_id, customer_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC
LIMIT 50;
```

Or use `TREE` to view the iterator tree on supported versions:

```sql
EXPLAIN FORMAT=TREE
SELECT order_id, customer_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC
LIMIT 50;
```

Compare the baseline and new result step by step: each table's access method, selected index, join order, filters, sorts, temporary tables, and row estimates. Do not rely on raw text diffing of full `EXPLAIN` output because minor metadata details can change without affecting the critical access paths.

## 5. Comparing Estimates Against Actuals with EXPLAIN ANALYZE

MySQL 8.0.18 and later support `EXPLAIN ANALYZE` for `SELECT` statements. It actually runs the query and reports actual row counts, loop counts, and iterator timings:

```sql
EXPLAIN ANALYZE
SELECT order_id, customer_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC
LIMIT 50;
```

Focus on:

- `rows`: actual rows returned by the iterator.
- `loops`: number of times the iterator executed; evaluate together with `rows` to gauge total work.
- `actual time`: actual iterator timing, usually showing time to first row and time to completion.
- Discrepancies between estimates and actuals: large gaps can cause the optimizer to pick an unsuitable join order or index.

For instance, suppose the optimizer estimates a predicate returns a few dozen rows, yet in reality it returns hundreds of thousands. A nested-loop join or row-by-row lookup then becomes far more expensive than anticipated. Inspect statistics and data distributions of the filtered column.

`EXPLAIN ANALYZE` carries runtime impact because it executes the query. Run it only on safely executable read queries, bound load, and choose timing windows carefully in production. Single-run timing is affected by caches, I/O, resource contention, and concurrency; measure multiple runs under controlled conditions and compare percentiles instead of drawing conclusions from one sample.

## 6. Refreshing InnoDB Statistics After Bulk Loads

The optimizer relies on index statistics to estimate cardinality and matching row counts. After loading large datasets, value distributions may differ from before while old statistics fail to reflect the new data.

For InnoDB, index statistics can be stored persistently. Key variables:

```sql
SHOW VARIABLES LIKE 'innodb_stats_persistent';
SHOW VARIABLES LIKE 'innodb_stats_auto_recalc';
SHOW VARIABLES LIKE 'innodb_stats_persistent_sample_pages';
```

- `innodb_stats_persistent` controls persisting InnoDB statistics to disk.
- `innodb_stats_auto_recalc` controls automatic statistics recalculation when data changes sufficiently.
- `innodb_stats_persistent_sample_pages` controls the number of pages sampled when computing persistent statistics.

With default settings, InnoDB schedules background recalculation of persistent stats when roughly 10% of table rows change. Because this runs automatically in the background, it does not guarantee statistics are refreshed the instant a bulk load finishes. When evaluating plans right after a load, proactively run `ANALYZE TABLE` and verify results.

After large loads or significant distribution changes, explicitly request a statistics refresh:

```sql
ANALYZE TABLE orders;
```

Then re-run `EXPLAIN` and `EXPLAIN ANALYZE` on the same query. Compare estimated row counts before and after `ANALYZE TABLE`; if estimates move closer to actuals and the plan improves, stale statistics were likely part of the cause.

Inspect persistent InnoDB statistics in system tables:

```sql
SELECT *
FROM mysql.innodb_table_stats
WHERE database_name = DATABASE()
  AND table_name = 'orders';

SELECT index_name, stat_name, stat_value, sample_size, stat_description
FROM mysql.innodb_index_stats
WHERE database_name = DATABASE()
  AND table_name = 'orders'
ORDER BY index_name, stat_name;
```

Values such as `n_rows`, `n_diff_pfxNN`, and `stat_value` are statistical estimates, not exact counts for every query. Sampling can also introduce variance, especially when data is heavily skewed or unevenly distributed.

`ANALYZE TABLE` can require metadata locks and consume resources while sampling. Schedule it appropriately, check for long-running transactions, and monitor load on large tables. Do not run it repeatedly just hoping to force the optimizer into picking a desired index.

## 7. Histograms for Columns with Skewed Distributions

Index statistics typically describe cardinality for index prefixes. For a heavily skewed column—where a few values occur very frequently while others are rare—histograms help the optimizer estimate selectivity more accurately.

Create a histogram on `status`:

```sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status WITH 64 BUCKETS;
```

Inspect histograms in the data dictionary:

```sql
SELECT SCHEMA_NAME, TABLE_NAME, COLUMN_NAME, HISTOGRAM
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'orders';
```

Histograms are per-column statistics that can assist the optimizer even when a column is not the leading part of an index. Histograms do not replace indexes: they improve row estimation, whereas access paths still require proper storage structures. Histograms do not refresh automatically merely because table rows change; run `UPDATE HISTOGRAM` proactively whenever distributions shift noticeably.

When data shifts significantly, refresh the histogram:

```sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status WITH 64 BUCKETS;
```

To remove a column's histogram:

```sql
ANALYZE TABLE orders
DROP HISTOGRAM ON status;
```

Do not choose bucket counts by guesswork. More buckets do not automatically yield better plans; compare estimates, plans, and execution times against representative workloads. Histograms are especially beneficial when common and rare values differ sharply in selectivity.

## 8. Investigating Regressions After a MySQL Upgrade

Upgrades can alter the optimizer, cost model, configuration defaults, expression handling, or statistics. Consequently, a query can receive a different plan even when SQL text and schema remain unchanged.

Before/after upgrade comparison workflow:

1. Record old and new MySQL versions, relevant settings, schemas, and index lists.
2. Record critical query digests along with representative parameter values.
3. Capture `EXPLAIN FORMAT=JSON` or `TREE` on both old and new environments.
4. Run controlled benchmarks on comparable data; measure actual rows, loops, execution time, rows examined, and latency.
5. Check InnoDB statistics and histograms on the new environment; do not assume they already reflect post-load distributions accurately.
6. Review changes in `optimizer_switch`, cost model, index visibility, collations, and data types if they affect queries.
7. Change only one factor at a time, then re-measure to isolate the cause.

Example recording key variables:

```sql
SELECT VERSION(), @@optimizer_switch;
SHOW VARIABLES LIKE 'innodb_stats%';
```

Do not copy optimizer configuration verbatim from an old version to a new version without evaluation. Defaults and optimizer behaviors evolve; legacy settings may disable improvements or introduce new issues.

## 9. Diagnosing by Symptoms

| Observed Symptom | Causes to Check | First Investigative Action |
|---|---|---|
| Small estimated `rows` yet massive actual rows | Stale statistics, missing histogram, or skewed distribution | Run `ANALYZE TABLE`, check histograms, and compare estimates |
| Optimizer switches from `range`/`ref` to `ALL` | Index no longer suitable, shifted selectivity, or changed cost estimate | Check `possible_keys`, `key`, indexes, and actual row counts |
| Join order shifts and nested loop iterates heavily | Cardinality misestimation or larger-than-expected driving table | Compare per-iterator rows/loops and table statistics |
| New `Using filesort` or temporary table appears | Index ordering does not satisfy query or result set grew | Check composite indexes, `ORDER BY`/`GROUP BY`, and rows to sort |
| Plan is nearly identical yet latency rose | I/O, buffer pool, CPU, lock waits, or concurrency | Measure resources, waits, rows examined, and cache state |
| Only one subset of parameter values is slow | Skewed value distribution, histograms, or varying selectivity | Test with common vs. rare parameters; check histograms and actual rows |

## 10. Remediating and Verifying After Adjustments

Prioritize fixing verified root causes:

- Refresh index statistics after bulk loads or major data changes.
- Update histograms on skewed columns when selectivity estimation is at fault.
- Adjust or add indexes if queries and access paths reveal missing prefixes.
- Rewrite queries if expressions, type conversions, or predicates prevent expected index usage.
- Check configuration and version differences if the regression began after an upgrade.
- Re-measure related workloads to confirm fixing one query does not noticeably degrade others.

`FORCE INDEX` or optimizer hints can serve as controlled experiments: compare the plan with the suggested index against the optimizer's natural plan. Avoid using hints as a knee-jerk reaction or hardcoding them in application code before understanding why the optimizer chose the old plan. Data keeps evolving, and a hint can become a bad choice in the future.

Before rolling changes to production, prepare a rollback path: restore indexes, drop a new histogram if harmful, revert configuration, or redeploy SQL. Post-deployment, keep monitoring digests, latency, rows examined, and query errors across a representative period.

## 11. Regression Evaluation Checklist

| Step | Items to Verify |
|---|---|
| Baseline | Saved SQL/digest, parameters, version, schema, indexes, config, and pre-change plans |
| Workload | Selected critical queries, periodic queries, and representative parameters |
| Plan | Compared access paths, join order, keys, rows, sorts, and temporary tables |
| Execution | Compared actual rows, loops, duration, and latency under comparable load |
| Statistics | Checked persistent stats, `ANALYZE TABLE`, and histograms where appropriate |
| Remediation | Changed one factor at a time and re-measured all related queries |
| Rollout | Prepared rollback path and post-change monitoring |

## 12. Self-Check

1. How does a plan regression differ from a performance regression?
2. Why should you capture a baseline before a bulk load or upgrade?
3. What different kinds of evidence do `EXPLAIN` and `EXPLAIN ANALYZE` provide?
4. When should you run `ANALYZE TABLE` after loading large datasets?
5. In what scenarios do histograms help the optimizer improve estimates?
6. Why can latency increase even when the execution plan remains unchanged?
7. When investigating a post-upgrade regression, why should you change only one factor at a time?
8. Why should you avoid using `FORCE INDEX` before understanding why the optimizer chose its plan?
