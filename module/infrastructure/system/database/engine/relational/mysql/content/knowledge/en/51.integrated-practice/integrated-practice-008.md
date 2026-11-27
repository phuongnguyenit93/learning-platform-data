# Query Optimization from Slow Log to Execution Plan and Index Selection

MySQL query optimization should start from real workloads, move through diagnosis, and finish with post-change measurement. A slow query in the log might be the root cause, or it might merely be a symptom of lock waits, resource contention, data growth, or a suboptimal execution plan. Adding an index immediately whenever a `SELECT` looks slow easily increases storage and write overhead without fixing the underlying issue.

This lab walks you through an end-to-end workflow: collecting the slow query log, grouping queries by digest, selecting high-priority workloads, reading execution plans, identifying bottlenecks, rewriting SQL when needed, designing appropriate indexes, and comparing before/after results. The goal is to improve latency and the amount of work MySQL performs while preserving accurate business results and controlling impacts on writes, transactions, and replication.

Within the scope of **DATABASE_MYSQL**, this workflow brings together table design, data types, keys, SQL queries, indexes, transactions, and concurrency control. You will also practice reading execution plans, tuning queries, managing privileges, backups, and operating relational databases.

## 1. Objectives and Overall Workflow

After this lesson, you will be able to:

- Enable and configure the slow query log in a controlled manner.
- Use digests and aggregated statistics to identify query groups driving high load.
- Read EXPLAIN and EXPLAIN ANALYZE to understand how MySQL accesses data.
- Recognize table scans, sorts, temporary tables, lock waits, and cardinality misestimates.
- Rewrite predicates so queries can use indexes effectively.
- Design composite indexes and covering indexes based on filter predicates, sort order, and returned columns.
- Evaluate index costs across INSERT, UPDATE, DELETE, storage, and replication.
- Roll out changes safely, compare before/after metrics, and retain evidence.

Practice workflow:

~~~mermaid
flowchart TD
    A[Collect slow log and metrics] --> B[Group queries by digest]
    B --> C[Select priority workload]
    C --> D[Reproduce with representative parameters]
    D --> E[Read EXPLAIN / EXPLAIN ANALYZE]
    E --> F{Primary root cause?}
    F -->|Non-SARGable predicate| G[Rewrite SQL]
    F -->|Missing or wrong index| H[Design index]
    F -->|Lock / transaction| I[Investigate concurrency]
    F -->|Bad cardinality estimate| J[Inspect statistics]
    G --> K[Measure before/after and verify results]
    H --> K
    I --> K
    J --> K
    K --> L[Deploy safely and monitor]
~~~

Do not start with the question "which index should we add?" Start with "which queries consume the most resources, how much work are they doing, and why?"

## 2. Collecting the Slow Query Log

### 2.1. What does the slow query log tell you?

The slow query log records statements exceeding a configured time threshold and additional query categories depending on optional settings. Depending on configuration and version, entries can show:

- Execution duration (`Query_time`).
- Lock wait duration (`Lock_time`).
- Rows returned (`Rows_sent`).
- Rows examined (`Rows_examined`).
- Timestamp, user/host, and the SQL statement.

High `Rows_examined` paired with low `Rows_sent` is often a signal that a query scans many rows to return only a few results. Still, that is not a final verdict: a query may legitimately need to scan many rows, or it may be affected by data skew, cache state, locks, or concurrent load.

A query taking 300 ms that runs tens of thousands of times per minute can impose far greater total load than a 10-second query running once a day. Therefore, combine the slow log with digest-level aggregated statistics.

### 2.2. Checking current configuration

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'slow_query_log',
  'slow_query_log_file',
  'long_query_time',
  'min_examined_row_limit',
  'log_output',
  'log_queries_not_using_indexes'
);
~~~

Key variables:

| Variable | Meaning | Usage |
|---|---|---|
| slow_query_log | Enables/disables the slow query log | Enable during an intentional collection window |
| slow_query_log_file | Log file path when output is FILE | Check disk space and rotation policy |
| long_query_time | Duration threshold in seconds for logging | Choose based on target latency and log volume |
| min_examined_row_limit | Minimum rows examined before logging | Helps filter out trivial fast queries |
| log_output | Destination: FILE, TABLE, or both | Typically FILE for operational collection |
| log_queries_not_using_indexes | Also logs queries not using indexes | Can generate huge logs; enable carefully |

### 2.3. Enabling logging in a test environment

Example setting a 500 ms threshold:

~~~sql
SET GLOBAL slow_query_log = ON;
SET GLOBAL long_query_time = 0.5;
SET GLOBAL min_examined_row_limit = 100;
SET GLOBAL log_output = 'FILE';
~~~

GLOBAL changes typically initialize session defaults for new connections. Existing sessions may retain their prior session values; check both GLOBAL and SESSION when verifying.

~~~sql
SELECT
  @@GLOBAL.slow_query_log AS global_slow_log,
  @@SESSION.long_query_time AS session_long_query_time,
  @@GLOBAL.long_query_time AS global_long_query_time;
~~~

To persist settings across restarts, update server config files or use `SET PERSIST` where operational policy permits. Never alter production settings purely to experiment without assessing log disk usage and performance impact.

`long_query_time` accepts fractional values. A threshold of 0.5 equals half a second. Setting it too low can produce massive logs, especially on high-QPS endpoints. Collect over a representative window, then disable or adjust according to policy.

### 2.4. Why shouldn't you blindly log every query not using an index?

Several valid queries legitimately skip indexes:

- Very small tables where a table scan is cheaper than an index lookup.
- Queries returning a large fraction of the table.
- Low-selectivity indexes where random I/O costs more than scanning.
- Cases where the optimizer estimates a scan is cheaper.
- Queries without a filtering predicate.

`log_queries_not_using_indexes` can flood logs and create noise. If needed, pair it with examined-row limits, bounded collection windows, and version-appropriate throttling. Never treat "not using an index" alone as proof of a broken query.

### 2.5. Securing the slow log

SQL in logs can expose sensitive literals, emails, customer IDs, tokens, or business data. You should:

- Restrict read permissions on log files and log tables.
- Apply appropriate retention and encryption policies.
- Never paste raw slow logs into public tickets or unauthorized chats.
- Redact sensitive values before sharing.
- Monitor disk usage and configure log rotation.
- Use a least-privilege account when querying log tables in MySQL.

## 3. Selecting Queries to Optimize

### 3.1. Do not rank solely by average latency

A query group can warrant priority for several reasons:

| Metric | Meaning | When It Matters |
|---|---|---|
| Execution count | How frequently the query runs | A moderately slow query executed at high frequency |
| Total time | Cumulative latency | Query group consuming the largest share of DB time |
| Average time | Mean latency per execution | Comparing per-call efficiency |
| Max time | Largest outlier | Exposing boundary datasets or lock contention |
| Rows examined | Rows inspected | Scanning excessive data to return little output |
| Rows sent | Rows returned | Evaluating work-to-output ratio |
| Temporary/disk tables | Temp tables created, potentially spilling to disk | Large sorts/groups or missing suitable indexes |
| Full scan | Full table or full index scan | Determining whether scanning fits the workload |

No single metric defines "the worst query." Ranking by total latency finds top resource consumers; ranking by execution count uncovers small yet hyper-frequent queries; ranking by rows examined reveals queries reading excessive data.

### 3.2. Using `mysqldumpslow`

When slow logs are written to a file, MySQL includes `mysqldumpslow` to group and summarize similar queries:

~~~bash
mysqldumpslow -s t -t 20 /var/log/mysql/mysql-slow.log
~~~

Common options:

- `-s t`: sort by total query time per group.
- `-s at`: sort by average query time per group.
- `-s c`: sort by occurrence count.
- `-s r`: sort by average rows sent.
- `-t 20`: display the top 20 groups.

Check `mysqldumpslow --help` on your target host since flags vary slightly by distribution. Tools like Percona `pt-query-digest` provide deeper analysis, subject to installation approval and log data protection policies.

### 3.3. Using the `sys` schema and Performance Schema

When statement instrumentation is enabled and digests remain in memory, the `sys` schema provides an aggregated view:

~~~sql
SELECT
  query,
  exec_count,
  total_latency,
  avg_latency,
  max_latency,
  rows_examined,
  rows_examined_avg,
  rows_sent,
  full_scan
FROM sys.statement_analysis
ORDER BY total_latency DESC
LIMIT 20;
~~~

You can also sort by execution count:

~~~sql
SELECT
  query,
  exec_count,
  avg_latency,
  rows_examined_avg,
  rows_sent_avg
FROM sys.statement_analysis
ORDER BY exec_count DESC
LIMIT 20;
~~~

Digests group structurally identical SQL statements by normalizing literals into placeholders. For instance, two queries with `account_id=10` and `account_id=20` collapse into the same digest.

Performance Schema statistics are memory-bounded and reset when MySQL restarts or summary tables are truncated. They represent cumulative counters over the observation window rather than long-term history. Export metrics to a monitoring system if you need daily or weekly trends.

### 3.4. Picking a representative query

For each selected digest, capture:

- The full SQL statement with sensitive literals stripped or masked.
- The schema, tables, and application version issuing the query.
- Representative parameters: small vs. large accounts, common vs. rare statuses, short vs. wide date ranges.
- Execution counts and latency percentiles if available.
- Rows examined, rows sent, full scans, and temporary tables.
- Collection timestamp, system load, and cache warmth.
- The current execution plan.

A query can have a great plan for a small account yet perform terribly for a large account. Never test only a single favorable parameter set.

## 4. Reading Execution Plans with EXPLAIN

### 4.1. Basic EXPLAIN

Example:

~~~sql
EXPLAIN
SELECT order_id, created_at, total_amount
FROM appdb.orders
WHERE account_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-10-01 00:00:00'
  AND created_at <  '2026-11-01 00:00:00'
ORDER BY created_at DESC
LIMIT 50;
~~~

Key columns in tabular output:

| Column | How to Read |
|---|---|
| id | SELECT sequence/group within the plan |
| select_type | SELECT type such as SIMPLE, PRIMARY, SUBQUERY |
| table | Table or derived table being accessed |
| type | Access type: ALL, index, range, ref, eq_ref, const... |
| possible_keys | Indexes the optimizer may consider |
| key | Index the optimizer actually chose |
| key_len | Byte length of the index prefix used |
| ref | Columns/constants compared against the index |
| rows | Estimated rows to examine |
| filtered | Estimated percentage of rows remaining after filtering |
| Extra | Details like Using filesort, Using temporary, Using index |

### 4.2. Understanding access types

Common access types ordered roughly from most selective to broadest scan:

- **const:** table is read as a single constant row, typically via primary/unique key against a constant.
- **eq_ref:** each row combination from preceding tables matches at most one row via unique/primary key.
- **ref:** index lookup matching a key value; may return multiple rows.
- **range:** reads one or more contiguous index ranges.
- **index:** scans the entire index; can be cheaper than a table scan if the index is small or covering, yet still a full scan.
- **ALL:** full table scan.

Never conclude that `ALL` is always wrong or `ref` is always optimal. Small tables scan faster than index lookups, and a low-selectivity index can trigger excessive random I/O. Always compare actual row counts, data size, and latency.

### 4.3. Reading `key`, `rows`, and `Extra`

- `possible_keys` lists an index yet `key` is `NULL`: the optimizer declined that index, possibly due to non-SARGable predicates, poor selectivity, type mismatches, or cost estimates.
- High `rows`: the optimizer expects to inspect many rows. Compare against actual row counts.
- `Using filesort`: MySQL requires an explicit sort step; it does not necessarily mean spilling to disk.
- `Using temporary`: an internal temporary table is needed; check size and disk spill behavior.
- `Using index`: all required columns are satisfied directly from the index (covering access).
- `Using index condition`: Index Condition Pushdown evaluates part of the filter while scanning the index.

`Using filesort` or `Using temporary` are signals to investigate, not automatic bugs. A top-N query may reasonably sort if the input slice is already small.

### 4.4. Tree format

MySQL supports tree output:

~~~sql
EXPLAIN FORMAT=TREE
SELECT order_id, created_at, total_amount
FROM appdb.orders
WHERE account_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-10-01 00:00:00'
  AND created_at <  '2026-11-01 00:00:00'
ORDER BY created_at DESC
LIMIT 50;
~~~

Tree format reveals the iterator pipeline and how scans, filters, sorts, and joins compose. For multi-table queries, read from leaf nodes (data sources) up toward the root node (final output) to trace how MySQL combines rows.

### 4.5. EXPLAIN ANALYZE

`EXPLAIN ANALYZE` executes the `SELECT` and reports actual timings and row counts for every iterator:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, created_at, total_amount
FROM appdb.orders
WHERE account_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-10-01 00:00:00'
  AND created_at <  '2026-11-01 00:00:00'
ORDER BY created_at DESC
LIMIT 50;
~~~

Output reveals:

- `actual time`: actual milliseconds for the iterator to produce its first row and finish.
- `rows`: actual rows returned per loop by the iterator.
- `loops`: how many times the iterator was invoked.
- Whether estimated rows diverge sharply from actual rows.

`EXPLAIN ANALYZE` runs the query for real. Use it only on safe `SELECT` statements with bounded scope in an appropriate environment; a heavy `SELECT` can still burn significant CPU/I/O or hold snapshots open. Never run unvetted heavy queries on an overloaded production primary.

When estimated rows differ widely from actual rows, inspect statistics, histograms, data skew, and query parameters. Poor estimates can cause the optimizer to pick a suboptimal join order or access path.

## 5. Analyzing a Sample Query

### 5.1. Schema and workload

Suppose the system has an orders table:

~~~sql
CREATE TABLE appdb.orders (
  order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  account_id BIGINT UNSIGNED NOT NULL,
  customer_id BIGINT UNSIGNED NOT NULL,
  status VARCHAR(16) NOT NULL,
  created_at DATETIME(6) NOT NULL,
  total_amount DECIMAL(13,2) NOT NULL,
  PRIMARY KEY (order_id),
  KEY idx_orders_account_created (account_id, created_at)
) ENGINE=InnoDB;
~~~

A reporting endpoint retrieves the 50 most recent orders for an account filtered by status and date range:

~~~sql
SELECT order_id, created_at, total_amount
FROM appdb.orders
WHERE account_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-10-01 00:00:00'
  AND created_at <  '2026-11-01 00:00:00'
ORDER BY created_at DESC
LIMIT 50;
~~~

The existing index is `(account_id, created_at)`. MySQL can filter by `account_id` and the `created_at` range, yet must filter `status` after reading candidate rows. If an account has many orders in the month but only a small fraction are `PAID`, the number of examined rows can be large.

This is a hypothesis derived from the schema. Confirm it with the slow log, `EXPLAIN`, and real data before making changes.

### 5.2. Forming a hypothesis before adding an index

Questions to answer:

1. How many rows belong to a single account?
2. What fraction of rows have status `PAID`?
3. How many rows fall inside the filtered date range?
4. Does the query require an extra sort after filtering?
5. Does this query run frequently enough to hurt endpoint latency?
6. Do other queries rely on the existing index?

Hypothesis: a composite index starting with `account_id`, followed by `status`, and then `created_at` will apply both equality predicates before scanning the time range.

### 5.3. Designing a composite index

Candidate index:

~~~sql
CREATE INDEX idx_orders_account_status_created
ON appdb.orders (account_id, status, created_at);
~~~

Rationale for column ordering:

- `account_id` has an equality predicate.
- `status` has an equality predicate.
- `created_at` serves both the range predicate and the sort order.
- With the first two columns fixed, the index can be scanned in `created_at` order to satisfy `ORDER BY created_at DESC`.

A composite index `(a, b, c)` typically supports queries using leftmost prefixes like `(a)`, `(a, b)`, or `(a, b, c)`. It does not replace an index on `(b)` or `(c)` alone. Review the full workload before dropping old indexes.

### 5.4. Is a covering index worth it?

The query selects `order_id, created_at, total_amount`. In InnoDB, secondary indexes store the primary key as the row locator. Thus `(account_id, status, created_at)` already supplies `order_id` and the indexed columns, yet `total_amount` still requires a lookup into the clustered index.

A covering candidate:

~~~sql
CREATE INDEX idx_orders_account_status_created_amount
ON appdb.orders (account_id, status, created_at, total_amount);
~~~

This index lets the query retrieve every needed column from the secondary index, avoiding clustered index lookups. However:

- The index is wider, consuming more buffer pool and disk storage.
- Every `INSERT` must update the wider index.
- `UPDATE` statements touching `total_amount`, `status`, `account_id`, or `created_at` may have to update the index.
- Backups and replication incur indirect overhead.
- If the query is infrequent or the table is write-heavy, read savings may not justify write costs.

Never create both candidate indexes simultaneously without justification. Benchmark each option against a representative workload.

### 5.5. Verifying the query after indexing

After creating the index in a test environment:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, created_at, total_amount
FROM appdb.orders
WHERE account_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-10-01 00:00:00'
  AND created_at <  '2026-11-01 00:00:00'
ORDER BY created_at DESC
LIMIT 50;
~~~

Compare:

- Did `key` switch to the new index?
- How did estimated rows and actual rows change?
- Are many rows still filtered out after the index read?
- Was the separate sort eliminated?
- Does `Using index` appear with the covering index?
- Did latency and CPU/I/O drop under a realistic workload?

Never fabricate improvement numbers before running benchmarks. Record actual measurements along with MySQL version, dataset details, and query parameters.

## 6. Rewriting Predicates so Queries Can Use Indexes

### 6.1. Avoid wrapping indexed columns in functions when possible

Query:

~~~sql
SELECT order_id, created_at
FROM appdb.orders
WHERE DATE(created_at) = '2026-10-15';
~~~

Even with an index on `created_at`, applying `DATE()` to every row prevents the optimizer from performing a range scan on a standard index.

Rewrite as a half-open interval:

~~~sql
SELECT order_id, created_at
FROM appdb.orders
WHERE created_at >= '2026-10-15 00:00:00'
  AND created_at <  '2026-10-16 00:00:00';
~~~

This keeps the predicate directly on the column, handles microseconds cleanly, and avoids assuming days end at `23:59:59`.

If business logic requires timezone-adjusted boundaries, convert the boundary timestamps into the stored timezone before executing the query. Avoid ad-hoc date math that can break around DST transitions.

### 6.2. Avoid unnecessary data type conversions

If `customer_id` is `BIGINT` while the application binds a string parameter, MySQL may cast values and undermine index usage depending on the expression. Bind parameters with proper numeric types in JDBC.

Similarly:

- Compare `VARCHAR` columns with string literals matching the column's charset and collation.
- Never compare datetimes against ambiguous string formats.
- Never apply `CAST(indexed_column AS ...)` inside a predicate when you can normalize the bound parameter instead.
- Never convert numeric columns to strings just for comparison.

### 6.3. `LIKE` and leading wildcards

Predicate:

~~~sql
WHERE email LIKE '%@example.com'
~~~

A standard B-tree index cannot seek efficiently when a pattern starts with a wildcard. If business logic requires searching by domain, consider storing and indexing a normalized `email_domain` column or using an appropriate search mechanism. Never create a B-tree index expecting it to accelerate leading-wildcard `LIKE`.

For prefix searches such as `email LIKE 'user%'`, a B-tree index can be used under compatible collations.

### 6.4. `OR` and multiple conditions

`OR` conditions are not always bad. MySQL can use Index Merge or other plans when appropriate. Inspect the plan before rewriting into `UNION`.

When splitting `OR` into `UNION` / `UNION ALL`, ensure semantics remain identical:

- `UNION` deduplicates rows; `UNION ALL` retains duplicates.
- Both branches may match the same row.
- `NULL` and SQL three-valued logic can alter edge-case behavior.
- `ORDER BY` and `LIMIT` scope changes if placed incorrectly.

Only rewrite after proving semantic equivalence and measuring performance.

## 7. Selecting Indexes Based on Workload

### 7.1. Composite indexes: equality, range, and ordering

A practical starting heuristic:

1. Place equality-filtered columns first.
2. Follow with range columns.
3. Consider `ORDER BY`/`GROUP BY` columns if index order can satisfy them.
4. Cross-check cardinality, query frequency, and other queries sharing the index.

This is a heuristic, not an unbreakable law. The optimal order depends on predicate sets, selectivity, joins, ranges, ordering, and overall workload.

Example:

~~~sql
SELECT order_id, created_at
FROM appdb.orders
WHERE account_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 100;
~~~

Index `(account_id, status, created_at)` satisfies both equality filters and timestamp ordering. If another query filters only by `status` without `account_id`, this index will not be effective because the leftmost prefix is missing.

### 7.2. Cardinality and selectivity

- **Cardinality** of an index is the estimated count of distinct values.
- **Selectivity** reflects how narrowly a predicate shrinks the dataset.

A boolean column with two values typically has low selectivity when evenly distributed. Yet it can still add value inside a composite index alongside `account_id` or timestamps.

Never choose an index based on single-column cardinality alone. Evaluate combined distributions and real queries.

### 7.3. Indexes for JOINs

~~~sql
SELECT o.order_id, c.customer_name
FROM appdb.orders o
JOIN appdb.customers c
  ON c.customer_id = o.customer_id
WHERE o.account_id = 42
  AND o.created_at >= '2026-10-01 00:00:00';
~~~

Ensure the join key on `customers` has a primary/unique key or suitable index. On `orders`, an index may need to start with `account_id`, `created_at`, and/or `customer_id` depending on access order and overall workload.

Inspect join order in `EXPLAIN`. If the outer table produces many rows, repeated lookups into the inner table accumulate significant cost.

### 7.4. Indexes and `GROUP BY`

~~~sql
SELECT status, COUNT(*)
FROM appdb.orders
WHERE account_id = 42
  AND created_at >= '2026-10-01'
  AND created_at < '2026-11-01'
GROUP BY status;
~~~

The ideal index here may differ from the index serving the top-50 recent orders query. Do not try to force one index to optimize every analytical report. For heavy analytical workloads, consider summary tables, application-managed materialized aggregates, or a dedicated analytics store.

### 7.5. Avoiding redundant indexes

Redundant indexes increase:

- Disk storage and buffer pool pressure.
- `INSERT`/`UPDATE`/`DELETE` overhead.
- Backup and restore duration.
- DDL duration and metadata lock exposure.
- Replication data volume.

An index that is a leftmost prefix of another index may be redundant in some workloads, yet never drop it based on appearance alone. Unique constraints, column ordering, collations, prefix lengths, and other queries may give each index a distinct role.

You can test hiding an index via invisible indexes in an appropriate environment:

~~~sql
ALTER TABLE appdb.orders
  ALTER INDEX idx_orders_account_created INVISIBLE;
~~~

Monitor query plans and workloads over a representative window. To restore optimizer visibility:

~~~sql
ALTER TABLE appdb.orders
  ALTER INDEX idx_orders_account_created VISIBLE;
~~~

An invisible index is still maintained on writes; the optimizer merely ignores it during normal plan selection. Thus, this test evaluates the read impact of removing the index without measuring the write savings gained once dropped. Only `DROP` an index after verifying no workload relies on it and preparing a rollback plan.

## 8. Statistics and Execution Plans

### 8.1. Stale or skewed statistics

The optimizer relies on statistics to estimate row counts and costs. After major data changes, stale statistics can cause poor plan choices.

Refresh table statistics:

~~~sql
ANALYZE TABLE appdb.orders;
~~~

Compare estimated rows against actual rows afterward. `ANALYZE TABLE` is not a universal cure for slow queries; it helps only when outdated statistics are part of the problem.

### 8.2. Histograms for skewed distributions

When a column has skewed distribution and the optimizer misestimates selectivity, histograms can help:

~~~sql
ANALYZE TABLE appdb.orders
  UPDATE HISTOGRAM ON status WITH 16 BUCKETS;
~~~

Inspect histograms:

~~~sql
SELECT
  SCHEMA_NAME,
  TABLE_NAME,
  COLUMN_NAME,
  HISTOGRAM
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = 'appdb'
  AND TABLE_NAME = 'orders';
~~~

Histograms do not replace indexes and do not guarantee the optimizer will pick a desired plan. Use them when you have evidence of misestimation due to data skew, and re-evaluate as data and workloads evolve.

To drop a histogram:

~~~sql
ANALYZE TABLE appdb.orders
  DROP HISTOGRAM ON status;
~~~

### 8.3. When the optimizer ignores an index

Do not rush to add `FORCE INDEX`. Check in order:

1. Do predicates match the column data type and collation?
2. Does the query satisfy the leftmost prefix and column order?
3. Is the predicate selective enough?
4. Is the table small, or does the query read most of its rows?
5. Do statistics/histograms reflect current distributions?
6. Is the chosen plan actually slow when measuring actual rows and time?

Index hints should be a last resort backed by evidence, testing, and a review plan as data grows.

## 9. Query Tuning Goes Beyond Indexes

### 9.1. Returning only needed columns and rows

Avoid `SELECT *` on endpoints needing only a few columns. Reading extra columns increases I/O, network traffic, memory footprint, and object hydration time.

Apply pagination or limits when business rules allow. `LIMIT 50` does not guarantee MySQL reads only 50 rows; if it must scan and filter many rows before finding 50 matches, total work remains high.

### 9.2. OFFSET pagination vs. keyset pagination

Large `OFFSET` values force MySQL to read and discard many rows:

~~~sql
SELECT order_id, created_at
FROM appdb.orders
WHERE account_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 50 OFFSET 50000;
~~~

For forward/backward cursor navigation, keyset pagination uses the last item's key from the previous page:

~~~sql
SELECT order_id, created_at
FROM appdb.orders
WHERE account_id = 42
  AND (
    created_at < '2026-10-15 12:00:00.000000'
    OR (
      created_at = '2026-10-15 12:00:00.000000'
      AND order_id < 987654
    )
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

A matching index could be `(account_id, created_at, order_id)`. The `(created_at, order_id)` pair provides deterministic ordering when multiple orders share the same timestamp. Keyset pagination fits next/previous cursor navigation; it does not support jumping directly to arbitrary page numbers.

### 9.3. N+1 queries from the application

An endpoint may execute one query fetching 100 orders followed by 100 separate queries fetching each order's details. Each individual query looks fast, yet cumulative round trips add up.

Identify N+1 patterns using query counts, digests, and application traces. Fix them with JOINs, batch fetching, or bounded `IN` queries. When introducing JOINs, guard against duplicate parent rows from one-to-many relations and avoid loading oversized payloads into memory.

### 9.4. Lock waits and long transactions

A query may be slow because it is blocked waiting on a lock rather than scanning data. Inspect lock waits, transaction age, and blocking sessions before adding indexes.

While a good index can reduce rows locked during some operations, it also adds index maintenance overhead. Keep transactions short, access tables in consistent order, and avoid calling external APIs while a transaction is open.

## 10. Measuring Before and After Optimization

### 10.1. Establishing a baseline

Before modifying SQL or adding indexes, record:

- The SQL text and representative parameters.
- Execution frequency, mean latency, and percentiles if available.
- Rows examined, rows sent, temporary tables, and full scans.
- Tabular/tree `EXPLAIN` and `EXPLAIN ANALYZE` in a safe environment.
- CPU, I/O, buffer pool hit rate, connection count, and lock waits.
- Write throughput and replication lag.
- Expected business output of the query.

Never measure once and jump to conclusions. Run multiple iterations with representative parameters and datasets, noting cache warmth and background load.

### 10.2. Comparing under identical conditions

After changes, test using the same:

- MySQL version and configuration.
- Dataset and data distribution.
- Query parameters.
- Iteration count and concurrency level.
- Cache state where controllable.
- Comparable background load window.

Compare p50/p95/p99 latency if available, throughput, rows examined, rows sent, sort/temp usage, CPU/I/O, and lock waits. Never compare only `EXPLAIN` estimates; measure actual execution behavior.

### 10.3. Verifying correctness

A faster query that returns wrong data is a regression. Verify:

- Row counts and identity keys.
- Result ordering when `ORDER BY` is present.
- `NULL` and duplicate handling.
- Date boundaries and timezone semantics.
- Aggregates, decimals, and rounding.
- Results on both common and edge-case parameters.

When rewriting with `UNION`, `JOIN`, subqueries, or keyset pagination, prove semantic equivalence before benchmarking.

### 10.4. Success criteria

Set concrete targets before making changes, for example:

| Area | Target Metric |
|---|---|
| Correctness | Results identical under business rules |
| Latency | p95/p99 reduced to target SLO |
| Read work | Rows examined reduced or proportional to rows sent |
| Plan | Appropriate access path without unexpected sorts/temp tables |
| Resources | CPU/I/O does not shift to create a new bottleneck |
| Writes | Write throughput remains within acceptable bounds |
| Replication | Replication lag remains within SLO |
| Operations | DDL and index rollback have runbooks, monitoring, and an owner |

No universal latency threshold fits all applications. Define SLOs per endpoint and business requirement.

## 11. Safe Index Deployment

### 11.1. Pre-DDL assessment

Before creating an index on a large table, verify:

- Estimated index size and free disk space.
- CPU/I/O headroom and buffer pool state.
- Long-running transactions and metadata lock exposure.
- Replication lag and catch-up capacity.
- Index build duration measured on a replica.
- Impact on `INSERT`/`UPDATE`/`DELETE`.
- Deployment window and stop/rollback procedures if issues arise.

Certain InnoDB operations support Online DDL, yet not every change is lock-free or zero-impact. Confirm supported algorithms and lock modes for your exact server version and table definition. You can explicitly specify `ALGORITHM` and `LOCK` clauses to fail fast rather than silently falling back to an undesirable lock mode, after verifying supported syntax.

### 11.2. Monitoring during index creation

While DDL executes:

- Monitor process list and metadata locks.
- Monitor CPU, I/O, disk, temp space, and redo/undo usage.
- Monitor replication lag and relay logs.
- Monitor application latency and lock waits.
- Enforce clear abort thresholds if load exceeds limits.

Never blindly `KILL` DDL or restart the server solely because it takes a while. Assess progress, metadata locks, and impact before intervening.

### 11.3. Post-index verification

- Run `ANALYZE TABLE` when statistics need refreshing.
- Re-inspect `EXPLAIN` and `EXPLAIN ANALYZE`.
- Re-run workload benchmarks.
- Check whether unrelated queries regressed onto suboptimal plans.
- Monitor write latency, storage growth, and replication lag.
- Document index ownership, served queries, and justification for keeping it.

Every index should have a concrete workload justifying its maintenance cost.

## 12. End-to-End Practice Scenario

Use a staging or test database populated with representative data.

### Step 1: Select a digest

From the slow log or `sys.statement_analysis`, pick a query group with high total latency or high rows examined. Record its digest, frequency, representative parameters, and owner.

### Step 2: Reproduce

Execute the query with matching bind parameter types against a production-like dataset. Verify the baseline output before optimizing.

### Step 3: Read the plan

Run `EXPLAIN FORMAT=TREE`, `EXPLAIN`, and `EXPLAIN ANALYZE` on a safe `SELECT`. Record access type, chosen key, estimated vs. actual rows, sort/temp operations, and iterator timings.

### Step 4: Identify the root cause

Classify the cause:

- Non-SARGable predicate.
- Missing or poorly ordered composite index.
- Low-selectivity or redundant index.
- Outdated statistics or missing histogram.
- Poor JOIN order or N+1 queries.
- Large `OFFSET` or extra sorting.
- Lock waits, long transactions, or resource saturation.

### Step 5: Test one change

Change only one variable per iteration: rewrite the predicate, add an index, refresh statistics, or switch pagination. This isolates what actually drove the improvement.

### Step 6: Re-measure and verify correctness

Run with the same dataset, parameters, and concurrency. Compare plan, latency, rows examined, CPU/I/O, and returned data. Also check write workloads and other queries touching the same table.

### Step 7: Plan the rollout

Document the DDL, deployment window, metadata locks, disk overhead, replication lag, abort thresholds, and rollback plan. For a new index, rollback usually means dropping the index after confirming no queries depend on it; account for `DROP` DDL duration and impact.

### Step 8: Monitor post-release

Watch slow logs/digests, latency, throughput, error rates, write load, lock waits, and replica lag. If plans regress or resources exceed thresholds, execute the prepared rollback runbook.

## 13. Common Query Tuning Pitfalls

| Symptom | Possible Cause | Troubleshooting Path |
|---|---|---|
| `type=ALL`, high `rows` | Table scan, non-SARGable predicate, or optimizer prefers scan | Inspect predicates, cardinality, table size, and `EXPLAIN ANALYZE` |
| `possible_keys` populated, `key=NULL` | Index unsuitable or scan estimated cheaper | Check selectivity, data types, statistics, and filter conditions |
| `Using filesort` | Index order does not satisfy `ORDER BY` or post-join sort needed | Check composite index order, `LIMIT`, and input row count |
| `Using temporary` | `GROUP BY`/`DISTINCT`/`ORDER BY` needs intermediate buffering | Inspect plan, cardinality, and ways to filter earlier |
| Very high `Rows examined`, low `Rows sent` | Late filtering or index missing filter columns | Review composite index and SARGability |
| Plan flips after deploy | Changed statistics, data volume, parameter skew, or server version | Compare plans and stats before/after; test with representative data |
| Fast query in isolation, slow endpoint | N+1 pattern, round trips, locks, serialization, or app load | Correlate digests with application traces and metrics |
| New index slows down writes | Increased index maintenance and I/O | Weigh read gains against write overhead |
| Index creation causes replica lag | Heavy DDL and concurrent workload | Check topology, schedule windows, and DDL strategy |
| Slow log grows too large | Threshold too low or broad `log_queries_not_using_indexes` | Tune thresholds, throttling, retention, and rotation |

## 14. Optimization Sign-Off Checklist

### Collection and prioritization

- [ ] Slow log enabled with an appropriate threshold.
- [ ] Digests reviewed and ranked by total latency, frequency, and rows examined.
- [ ] Representative parameters chosen and owner identified.
- [ ] Logs secured with sensitive values redacted.

### Analysis

- [ ] Read tabular/tree `EXPLAIN`.
- [ ] Compared estimated rows vs. actual rows where feasible.
- [ ] Checked predicates, data types, `JOIN`, `ORDER BY`, and `GROUP BY`.
- [ ] Checked lock waits and transactions if latency spiked unusually.
- [ ] Checked statistics/histograms when estimates were skewed.

### Indexes and rewrites

- [ ] Every index is justified by a concrete workload.
- [ ] Composite index column order aligns with predicates and ordering.
- [ ] Covering index benefits weighed against storage and write costs.
- [ ] No duplicate or redundant indexes added without reviewing the full workload.
- [ ] Query rewrites preserve exact semantics, `NULL`s, duplicates, and boundaries.

### Measurement and rollout

- [ ] Baseline and post-change measurements ran under identical conditions.
- [ ] Measured latency, rows examined, CPU/I/O, write load, and replication lag.
- [ ] Verified business accuracy of returned results.
- [ ] Assessed metadata locks and Online DDL behavior.
- [ ] Defined abort thresholds, rollback plan, and accountable owner.
- [ ] Monitored post-release metrics and archived evidence.

## 15. Self-Check

**Scenario 1:** The slow log shows one query taking 200 ms and executing 50,000 times per hour. Another query takes 8 seconds but runs once per day. Which should you prioritize?

**Hint:** Compare total latency, SLO impact, resource usage, and affected users. The 200 ms query likely generates far higher aggregate load, while the 8-second query still matters if it blocks a critical business workflow.

**Scenario 2:** `EXPLAIN` shows `type=ALL`. Must you add an index immediately?

**Hint:** No. The table may be tiny or the query may match most rows. Inspect `rows`, predicates, selectivity, actual execution, and overall workload before deciding.

**Scenario 3:** A query filters by `DATE(created_at)`. The index on `created_at` is not used effectively. What should you try?

**Hint:** Rewrite as a half-open interval: `created_at >= day_start AND created_at < next_day_start`, then compare execution plans and results.

**Scenario 4:** Index `(account_id, status, created_at)` works well for queries filtering all three columns. Will a query filtering only `status` use this index effectively?

**Hint:** No. Composite indexes follow the leftmost prefix rule; without `account_id`, the index is generally unsuitable for filtering on `status` alone.

**Scenario 5:** After adding a covering index, `SELECT` gets faster while `UPDATE` gets slower. Should you keep it?

**Hint:** Evaluate the entire workload. Indexes add write and storage overhead. Weigh read speedups against update frequency, write latency, replication lag, and disk footprint before deciding.

**Scenario 6:** `EXPLAIN ANALYZE` shows estimated rows = 10 while actual rows = 200,000. What should you inspect?

**Hint:** Inspect table statistics, data distribution, histograms, and selectivity. Refresh statistics or build histograms when misestimation is proven, then re-check the plan and measure actual runtime.

## 16. Key Takeaways

- The slow query log surfaces slow queries, while digests and metrics help prioritize high-impact workloads.
- Total latency and execution frequency often matter as much as single-execution average latency.
- `EXPLAIN` shows the estimated plan; `EXPLAIN ANALYZE` executes the `SELECT` and reports actual runtime metrics.
- `ALL` or `Using filesort` are signals for investigation, not automatic proof that an index is missing.
- Design composite indexes around predicates, leftmost prefixes, ranges, ordering, and overall workload.
- Covering indexes reduce lookups at the expense of storage and write overhead.
- SARGable predicates, matching data types, and proper pagination can speed up queries without adding any index.
- Statistics and histograms shape plan selection; update them when misestimates occur.
- Measure every new index for both read gains and impacts on writes, DDL, backups, and replication.
- Conclude optimization only after comparing under identical data, parameters, and concurrency while verifying business correctness.

## References

- [MySQL 8.4 Reference Manual: The Slow Query Log](https://dev.mysql.com/doc/refman/8.4/en/slow-query-log.html) — slow query log configuration and format.
- [MySQL 8.4 Reference Manual: mysqldumpslow](https://dev.mysql.com/doc/refman/8.4/en/mysqldumpslow.html) — grouping and summarizing slow query logs.
- [MySQL 8.4 Reference Manual: EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html) — reading execution plans and EXPLAIN ANALYZE.
- [MySQL 8.4 Reference Manual: Optimization and Indexes](https://dev.mysql.com/doc/refman/8.4/en/optimization-indexes.html) — optimization principles and index usage.
- [MySQL 8.4 Reference Manual: Multiple-Column Indexes](https://dev.mysql.com/doc/refman/8.4/en/multiple-column-indexes.html) — composite indexes and leftmost prefixes.
- [MySQL 8.4 Reference Manual: Optimizer Statistics](https://dev.mysql.com/doc/refman/8.4/en/optimizer-statistics.html) — optimizer statistics and histograms.
- [MySQL 8.4 Reference Manual: Invisible Indexes](https://dev.mysql.com/doc/refman/8.4/en/invisible-indexes.html) — testing index removal with invisible indexes.
- [MySQL 8.4 Reference Manual: InnoDB Online DDL](https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl-operations.html) — DDL algorithms and locking behavior.
- [MySQL 8.4 Reference Manual: sys Schema Statement Analysis](https://dev.mysql.com/doc/refman/8.4/en/sys-statement-analysis.html) — digest-level statement statistics.
