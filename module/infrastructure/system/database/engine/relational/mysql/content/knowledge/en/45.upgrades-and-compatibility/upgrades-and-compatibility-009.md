# Comparing SQL Plans, Latency, Errors, and Business Results Before/After

Upgrading MySQL can alter how the optimizer chooses indexes, join orders, row estimates, and query execution strategies. A SQL statement may still succeed yet run slower, examine more rows, or return different results due to changes in SQL mode, collation, data types, or compatibility behavior. Therefore, upgrade evaluation must compare execution plans, latency, errors, and business results simultaneously on the same dataset and a reproducible workload.

This lesson belongs to the **Upgrades and Compatibility** chapter of the **DATABASE_MYSQL** module. Within the learning path to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, access control, backups, and operations, before/after measurement confirms that an upgrade preserves correctness and meets system performance requirements.

## 1. Four Perspectives to Compare

Never conclude an upgrade succeeded merely because the application starts or all migrations complete. Evaluate at least four metric groups:

| Perspective | Question to Answer | Evidence to Collect |
|---|---|---|
| SQL plan | Which access path and join order does the optimizer choose? Did it change significantly? | EXPLAIN FORMAT=JSON, EXPLAIN ANALYZE |
| Latency and throughput | How much faster/slower are queries at p50, p95, p99? How many requests can the system handle? | APM, application metrics, same-workload benchmarks |
| Errors and resources | Is there an increase in SQL errors, warnings, timeouts, deadlocks, lock waits, CPU, or I/O? | Application logs, Performance Schema, MySQL status, server logs |
| Business results | Are row counts, monetary totals, statuses, relationships, and business rules preserved? | Result set comparisons, aggregates, constraints, and business tests |

A plan change is not automatically a regression. The optimizer may select a different plan that runs faster. Conversely, plans that look nearly identical can still run slower due to larger datasets, cold caches, contention, or resource changes. Combine plan inspection with real measurements.

## 2. Establishing a Pre-Upgrade Baseline

A baseline is the reference dataset used for post-upgrade comparison. Capture the baseline on the current MySQL version before changing binaries, configuration, or schemas.

### Recording the Environment

Save the version, optimizer configuration, and settings affecting query semantics:

~~~sql
SELECT VERSION() AS mysql_version,
       @@version_comment AS version_comment;

SHOW VARIABLES
WHERE Variable_name IN (
  'sql_mode',
  'time_zone',
  'system_time_zone',
  'character_set_server',
  'collation_server',
  'optimizer_switch',
  'transaction_isolation',
  'innodb_stats_persistent',
  'binlog_format'
);
~~~

Some variables or variable names may differ across version branches. If a variable does not exist, record the difference rather than assuming an equivalent value. Also record MySQL configuration, instance size, CPU, RAM, storage, filesystem, connection pools, driver versions, and application versions.

Inspect schemas and dependent objects:

~~~sql
SHOW CREATE TABLE orders;
SHOW CREATE TABLE customers;
SHOW INDEX FROM orders;
SHOW INDEX FROM customers;
~~~

For critical stored programs, triggers, and events, save their corresponding definitions with `SHOW CREATE`. Record charsets/collations, column types, defaults, generated columns, indexes, constraints, partitions, and histograms if any. These factors can influence both results and execution plans.

### Selecting a Representative Workload

Select critical queries based on traffic volume and business risk:

- Frequent read queries accounting for the bulk of requests.
- Queries with high p95/p99 latency or unstable execution times.
- Queries joining multiple tables, filtering by date, paginating, or aggregating.
- Write queries targeting tables with many indexes or foreign keys.
- Queries executed by batch jobs, reporting, or background tasks.
- Queries with skewed parameter distributions, such as one status being far more common than others.

Do not pick only a favorable parameter value. The same SQL statement can have vastly different plans or runtimes depending on parameter selectivity and data distribution. Save a representative parameter set, including boundary cases.

### Using the Same Data State

A reliable comparison restores the exact same data snapshot into two test environments: one running the old version and one running the target version. Keep application schema, indexes, data, hardware configuration, and workload identical during the initial measurement to isolate the effect of the server version.

If upgrading schema or configuration simultaneously, separate them into distinct test runs so you know which factor caused any difference. For write workloads, run on a clone or resettable test data; never replay DML with side effects on production solely for benchmarking.

## 3. Reading Execution Plans with EXPLAIN

EXPLAIN shows how the optimizer plans to access data. Start with JSON format for a structure that is easy to compare:

~~~sql
EXPLAIN FORMAT=JSON
SELECT
  o.id,
  o.created_at,
  o.total_amount,
  c.email
FROM orders AS o
JOIN customers AS c
  ON c.id = o.customer_id
WHERE o.status = 'PAID'
  AND o.created_at >= '2026-01-01'
ORDER BY o.created_at DESC, o.id DESC
LIMIT 100;
~~~

When comparing before and after, pay attention to:

- **access_type:** access method such as `const`, `eq_ref`, `ref`, `range`, `index`, or `ALL`. `ALL` usually indicates a full table scan, though it can still be optimal for small tables or queries reading most of the rows.
- **key and possible_keys:** indexes considered by the optimizer and the index chosen. Plans can switch indexes due to statistics or cost estimates.
- **rows and filtered:** estimated rows to examine and percentage of rows remaining after filter predicates. These are estimates, not actual row counts.
- **join order:** the sequence in which tables are accessed. Changing join order can reduce or inflate intermediate row counts.
- **temporary table and filesort:** creation of temporary tables or extra sorting. Not always bad, but monitor if newly introduced or cost increases.
- **materialization and derived table:** the optimizer may materialize subqueries/CTEs or transform execution strategies.
- **partition pruning:** whether the query prunes unnecessary partitions or scans multiple partitions.

Do not diff raw JSON verbatim and draw conclusions from formatting alone. Newer versions may alter how plans are formatted. Extract key attributes and explain their workload impact.

### Viewing Tree Plans

~~~sql
EXPLAIN FORMAT=TREE
SELECT
  customer_id,
  COUNT(*) AS order_count
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY customer_id;
~~~

TREE format displays the iterator pipeline and parent-child step relationships. This format is used alongside `EXPLAIN ANALYZE` in MySQL 8.0.18 and later.

### Measuring Execution with EXPLAIN ANALYZE

~~~sql
EXPLAIN ANALYZE
SELECT
  o.id,
  o.created_at,
  o.total_amount
FROM orders AS o
WHERE o.customer_id = 1001
  AND o.status = 'PAID'
ORDER BY o.created_at DESC
LIMIT 50;
~~~

`EXPLAIN ANALYZE` actually executes the `SELECT` statement and reports actual timing, actual row counts, and loop counts at each iterator. Use it only with safe read queries whose parameters and data scope have been evaluated. A `SELECT` query can still consume substantial CPU, I/O, and hold resources; do not run it arbitrarily on production during peak hours.

Compare actual rows against estimated rows. If the optimizer estimates a few dozen rows while actually reading millions, statistics may fail to reflect data distribution. Inspect indexes, histograms, and `ANALYZE TABLE` timing. Do not rush to force indexes before understanding why estimates diverged.

`EXPLAIN ANALYZE` carries measurement overhead and typically executes once for the specified query. Do not use a single `EXPLAIN ANALYZE` timing as the sole conclusion about production latency. Combine it with repeated benchmarks and application-tier measurements.

## 4. Analyzing Digests with Performance Schema

Performance Schema aggregates statement statistics by digest, helping identify queries consuming high total time, examining many rows, or generating errors. Example:

~~~sql
SELECT
  SCHEMA_NAME,
  DIGEST,
  LEFT(DIGEST_TEXT, 180) AS query_sample,
  COUNT_STAR,
  ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_seconds,
  ROUND(MAX_TIMER_WAIT / 1000000000000, 6) AS max_seconds,
  SUM_ROWS_EXAMINED,
  SUM_ROWS_SENT,
  SUM_ERRORS,
  SUM_WARNINGS,
  SUM_CREATED_TMP_DISK_TABLES,
  SUM_SORT_ROWS
FROM performance_schema.events_statements_summary_by_digest
WHERE SCHEMA_NAME = DATABASE()
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 30;
~~~

Performance Schema timers are expressed in picoseconds; divide by 10^12 to convert to seconds. The digest table accumulates metrics over the collection interval, rather than reporting per-request latency. Take snapshots at the start and end of a workload window and compute deltas for counters such as `COUNT_STAR`, `SUM_TIMER_WAIT`, `SUM_ROWS_EXAMINED`, and `SUM_ERRORS`.

Do not truncate/reset global summaries on production solely to create a baseline if doing so disrupts operations team visibility. Export snapshots to files or a monitoring system and compute deltas across time windows instead.

Performance Schema must have appropriate instruments and consumers enabled. If the table shows no data, check instrumentation configuration and privileges before concluding the workload issued no statements.

### Interpreting the Metrics

- Rapidly rising `COUNT_STAR` indicates the digest is executed frequently.
- `AVG_TIMER_WAIT` shows the digest's average duration over the collection interval; it does not reveal p95 or p99 percentiles.
- High `SUM_ROWS_EXAMINED` relative to `SUM_ROWS_SENT` can indicate queries scanning many rows to return few results. For aggregate queries, that ratio may be inherent to the business logic.
- Increasing `SUM_CREATED_TMP_DISK_TABLES` can indicate queries spilling temporary tables to disk.
- `SUM_ERRORS` and `SUM_WARNINGS` help catch post-upgrade changes in errors or warnings.

For example, a digest with high total time may be slow per execution or called very frequently. Distinguish the two cases by inspecting both `COUNT_STAR` and `AVG_TIMER_WAIT`. Optimizing a very fast query called millions of times can sometimes yield greater gains than optimizing a rarely executed slow query.

## 5. Measuring Latency, Throughput, and Resources Properly

Latency must be measured where users experience it. Application Performance Monitoring (APM) or application telemetry should record p50, p95, p99, timeouts, and connection pool wait times. Performance Schema complements this with a server-side view.

| Metric | Meaning | How to Compare |
|---|---|---|
| p50 latency | Duration of a typical request | Detects shifts across the majority of requests |
| p95 latency | 95% of requests complete within this threshold | Evaluates experience for most users |
| p99 latency | Slow tail of the distribution | Detects rare slow queries, locks, or contention |
| Throughput | Requests or transactions per second | Determines processing capacity under load |
| Error rate | Percentage of failed requests/transactions | Detects compatibility errors and timeouts |
| CPU and I/O | Resource consumption | Identifies regressions due to execution cost |
| Lock wait/deadlock | Concurrency contention | Detects changes in locking order or hold duration |

Performance Schema digests provide averages and maximums, not exact per-request percentiles. Use APM or application-tier histograms to obtain p50/p95/p99. If no APM exists, deploy latency histograms before upgrading so you have a comparable baseline.

### Benchmark Conditions

Keep the following conditions identical between the two versions:

1. Same data snapshot, schema, and indexes.
2. Same SQL statements, parameter sets, and read/write ratio.
3. Same hardware, resource limits, and connection settings.
4. Same concurrency level and workload duration.
5. Same cache state, or separate cold-cache and warm-cache measurements.
6. Include a warm-up phase before recording metrics.
7. Repeat multiple runs and compare medians and percentiles rather than picking the best single run.

Measure both low load and near-production load. A plan with low latency in single-threaded runs can cause lock waits or spike p99 when many transactions execute concurrently.

## 6. Comparing SQL Errors, Warnings, and Locks

An upgrade can expose queries that previously relied on ambiguous behavior or legacy settings. Track errors by `SQLSTATE` and error code, not just grepping logs for the word `ERROR`.

Categories to watch closely:

- **Syntax/compatibility errors:** identifier keywords, deprecated/removed syntax, or removed features.
- **Data conversion errors:** string-to-number/date conversion, out-of-range values, or strict SQL mode.
- **Constraint violations:** duplicate keys, foreign keys, `NOT NULL`, or `CHECK` constraints.
- **Authentication/privilege errors:** authentication plugins, accounts, roles, or routine privileges.
- **Timeouts:** query timeout, lock wait timeout, connection timeout.
- **Deadlocks:** conflicting transactions rolled back by InnoDB to break a wait cycle.
- **Warnings:** implicit casts, truncated values, or deprecated syntax.

Compare error totals across equal time windows and request counts. Error rates are more meaningful than absolute counts if throughput differs between two measurement runs.

Use Performance Schema digests to inspect `SUM_ERRORS` and `SUM_WARNINGS`; cross-reference application logs to identify the failing request, endpoint, and parameters. When deadlocks occur, gather details from application logs and `SHOW ENGINE INNODB STATUS`. Do not merely count errors: classify them by code, severity, endpoint, and business impact.

Checking lock waits in Performance Schema on MySQL 8.0:

~~~sql
SELECT
  w.REQUESTING_ENGINE_TRANSACTION_ID,
  w.BLOCKING_ENGINE_TRANSACTION_ID,
  r.OBJECT_SCHEMA,
  r.OBJECT_NAME,
  r.INDEX_NAME,
  r.LOCK_TYPE,
  r.LOCK_MODE AS requesting_lock_mode,
  b.LOCK_MODE AS blocking_lock_mode
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS r
  ON r.ENGINE = w.ENGINE
 AND r.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS b
  ON b.ENGINE = w.ENGINE
 AND b.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
~~~

This query shows the relationship between a waiting transaction and its blocking transaction. If it returns no rows, there may simply be no lock waits at the moment of sampling. To locate the blocker, combine with `data_locks`, `events_statements_current`, and the process list. Never kill a session based solely on one lock-wait row without identifying the transaction and its impact.

## 7. Verifying Business Results Before and After

Execution plans and latency do not prove result correctness. Compare business results on the same snapshot with identical parameters.

### Comparing Result Sets

For queries returning lists, export results in both environments with deterministic ordering by a unique key:

~~~sql
SELECT
  id,
  customer_id,
  status,
  total_amount,
  created_at
FROM orders
WHERE created_at >= '2026-01-01'
ORDER BY id;
~~~

Compare by primary key and column-by-column after normalizing formatting. Without `ORDER BY`, row order is not guaranteed; do not compare two output files by line position. When paginating, use a stable sort including a unique tie-breaker key so rows do not shift positions across runs.

For `DECIMAL`, compare exact values matching scale. For `FLOAT`/`DOUBLE`, choose tolerances based on business rules and permissible rounding error. For `JSON`, decide whether to compare normalized structure or raw string representation. For temporal values, standardize timezones and fractional-second precision.

### Comparing Aggregates

For reporting queries, reconcile row counts, sums, and groupings:

~~~sql
SELECT
  status,
  COUNT(*) AS order_count,
  SUM(total_amount) AS total_amount
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY status
ORDER BY status;
~~~

You can also compare `MIN`/`MAX` timestamps, distinct customer counts, row counts per tenant, or daily totals. Aggregates surface large discrepancies quickly, though they do not replace key-by-key reconciliation when you need to pinpoint exact differing records.

### Checking Relationships and Constraints

~~~sql
SELECT COUNT(*) AS orphan_orders
FROM orders AS o
LEFT JOIN customers AS c
  ON c.id = o.customer_id
WHERE c.id IS NULL;
~~~

Results must adhere to business rules and constraints. Check for duplicates on business keys, `NULL` rows in mandatory columns, and invalid statuses. Reconcile row counts before/after migration per partition, tenant, or batch.

### Do Not Compare on Mutating Data

If the source keeps accepting writes while results are collected, two queries can observe two different snapshots. Restore the same snapshot, or use a transactional snapshot and an alignable checkpoint. For continuously changing data, record a watermark such as GTID/binlog position or cutover batch to bound the comparison scope.

For write queries, run tests on a resettable clone. Compare pre/post transaction states, affected row counts, audit events, and side effects such as triggers or events. Never replay payment transactions, send notifications, or trigger external side effects on production merely to measure performance.

## 8. Compatibility Changes That Can Alter Results

When upgrading across MySQL versions, inspect factors capable of changing semantics:

- **SQL mode:** strict mode, `ONLY_FULL_GROUP_BY`, and invalid date/value rules can cause legacy queries to emit errors or warnings.
- **Character set and collation:** comparison, sorting, case sensitivity, and accent sensitivity rules may change; this affects equality, unique keys, and `ORDER BY`.
- **Time zone:** session `time_zone` and `system_time_zone` can alter how `TIMESTAMP` values are displayed or converted.
- **Data types and implicit conversions:** expressions comparing strings with numbers, `DECIMAL`/`FLOAT` precision, and date/time values must be verified.
- **Optimizer and statistics:** the new version may select different indexes, join orders, or materialization strategies.
- **Reserved words and syntax:** previously valid identifiers may become keywords; check column, table, and routine names.
- **Authentication and privileges:** auth plugins, roles, and grants may change how clients connect or invoke routines.
- **Stored programs:** check routines, triggers, events, `DEFINER`, `SQL SECURITY`, and `EXECUTE` privileges.

Do not tweak SQL mode, collation, or `optimizer_switch` mid-benchmark just to make the two versions produce identical outputs. Measure first under each version's intended target configuration; only then test changing individual variables one at a time to isolate root causes.

## 9. Analyzing Plan or Latency Regressions

When a query runs slower, investigate methodically to avoid changing multiple factors at once:

1. Confirm workload, parameters, concurrency, and cache state are equivalent between runs.
2. Compare `EXPLAIN` JSON/TREE outputs to identify access paths, join orders, estimated rows, temporary tables, and filesorts.
3. Run `EXPLAIN ANALYZE` in a test environment to compare estimated rows against actual rows.
4. Check index statistics, histograms, and when `ANALYZE TABLE` last ran.
5. Inspect rows examined, rows sent, temporary disk tables, sorts, and lock waits in Performance Schema.
6. Check changes in schema, collation, SQL mode, `optimizer_switch`, and server configuration.
7. Test one adjustment at a time on a clone, then re-run the exact same workload.
8. Record plans, metrics, and before/after results for peer review.

`ANALYZE TABLE` updates statistics and can cause the optimizer to pick a different plan. Test in a non-production environment first, record execution timestamps, and compare statistics before and after. Do not run `ANALYZE TABLE` across production tables indiscriminately during an investigation without assessing its impact.

Index hints or optimizer hints can help in proven cases, but increase coupling to specific data distributions and versions. Prioritize understanding why estimates went wrong, designing proper indexes, and verifying query shapes before locking plans with hints.

## 10. Upgrade Evaluation Matrix

Define acceptance criteria before starting tests. Example:

| Item | Acceptance Criterion | Action if Unmet |
|---|---|---|
| Business results | Zero discrepancies beyond approved differences | Halt rollout, locate changed query or rule |
| SQL errors | Zero new errors on critical flows | Classify SQLSTATE/error code and fix compatibility |
| Warnings | No increase in severe or ignored warnings | Identify implicit casts, truncation, or deprecated syntax |
| p95/p99 latency | Within SLO or agreed regression threshold | Analyze digests and plans of slow queries |
| Throughput | Meets target load with required headroom | Inspect CPU, I/O, locks, and connection pools |
| Resource usage | CPU, memory, I/O, and disk remain within operational thresholds | Tune workload/configuration after locating bottleneck |
| Locks/deadlocks | No increase beyond what applications can safely retry | Analyze transactions and access ordering |
| Recovery/replication | Replicas and backups still satisfy RPO/RTO | Halt change or remediate recovery path |

Thresholds must reflect system SLOs and characteristics. For instance, a team might require p95 not to increase by more than 10% on critical queries; that is an illustrative threshold, not a universal standard. Define run counts, duration, load, and delta calculations prior to benchmarking to avoid cherry-picking favorable numbers after seeing results.

## 11. Testing and Rollout Workflow

A comparison workflow can be executed as follows:

1. **Capture baseline:** save versions, config variables, schemas, indexes, statistics, digests, latency percentiles, error rates, and business aggregates.
2. **Build comparison environments:** restore the same snapshot onto both the current version and the target version.
3. **Run compatibility checks:** migrations, stored programs, authentication, SQL modes, charsets/collations, and drivers.
4. **Execute workload:** use identical parameters, concurrency, duration, and warm-up.
5. **Collect plans:** save `EXPLAIN` JSON/TREE and `EXPLAIN ANALYZE` outputs for representative queries.
6. **Compare performance:** compare p50/p95/p99, throughput, rows examined, errors, warnings, CPU, I/O, and lock waits.
7. **Reconcile results:** compare result sets, aggregates, constraints, and business states.
8. **Resolve regressions:** adjust one factor at a time, re-run the same test suite, and record evidence.
9. **Canary:** deploy on a small slice or test replica/cluster and monitor live metrics.
10. **Expand or halt:** proceed only when acceptance criteria are met; retain backups and rollback/forward-fix plans.

For systems using replication, also verify apply time, lag, and replica status after upgrading. For Group Replication or InnoDB Cluster, follow the corresponding topology upgrade procedure; never arbitrarily upgrade a member without verifying version compatibility and rolling upgrade rules.

## 12. Key Takeaways

- Compare before/after on the same snapshot, schema, parameters, and workload.
- Use `EXPLAIN FORMAT=JSON`/`TREE` to inspect plans; use `EXPLAIN ANALYZE` to measure actual iterators on safe read queries.
- A changed plan does not equal a regression; inspect actual rows, latency, and throughput.
- Performance Schema digests pinpoint high-cost queries, excessive row scans, errors, and warnings; they do not replace application-tier p95/p99 metrics.
- Measure latency under load and separate cold-cache from warm-cache runs.
- Compare errors by SQLSTATE/error code and rate per total requests.
- Verify result sets, aggregates, constraints, and business relationships on the same snapshot.
- Inspect SQL modes, collations, timezones, data types, authentication, and stored programs.
- Investigate one factor at a time; never force indexes or reset statistics without understanding the cause.
- Define acceptance thresholds before rollout and keep evidence for review.

An upgrade should be accepted only when data remains accurate, errors stay within bounds, performance meets SLOs, and recovery procedures are verified. Saving baselines alongside plans, metrics, and business results provides clear evidence to decide whether to proceed, tune, or halt a rollout.

## References

- [MySQL 8.0 Reference Manual: EXPLAIN](https://dev.mysql.com/doc/refman/8.0/en/explain.html)
- [MySQL 8.0 Reference Manual: EXPLAIN ANALYZE](https://dev.mysql.com/doc/refman/8.0/en/explain.html#explain-analyze)
- [MySQL 8.0 Reference Manual: Performance Schema Statement Summary Tables](https://dev.mysql.com/doc/refman/8.0/en/performance-schema-statement-summary-tables.html)
- [MySQL 8.0 Reference Manual: Performance Schema Data Lock Waits](https://dev.mysql.com/doc/refman/8.0/en/performance-schema-data-lock-waits-table.html)
- [MySQL 8.0 Reference Manual: Optimizer Statistics](https://dev.mysql.com/doc/refman/8.0/en/optimizer-statistics.html)
- [MySQL 8.0 Reference Manual: Server SQL Modes](https://dev.mysql.com/doc/refman/8.0/en/sql-mode.html)
