# Latency, Rows Examined, Rows Sent, and Execution Frequency

An SQL query cannot be evaluated by the runtime of a single execution alone. A statement taking 2 ms that runs 200,000 times per hour can consume more resources than a report taking 2 seconds that runs once a day. Likewise, a query returning one row is not necessarily lightweight: it may have read and filtered millions of rows before producing that result.

To observe a workload properly, combine at least four perspectives: **latency** shows how long callers wait; **rows examined** shows how many rows the server inspected; **rows sent** shows how many rows were returned to the client; and **execution frequency** shows how often the statement runs. Combining these metrics by query digest and by request helps identify which queries to optimize first.

## Objectives

After this lesson, you will be able to:

- Distinguish average latency, maximum latency, total time, and application-level percentiles.
- Read `ROWS_EXAMINED` and `ROWS_SENT` and understand the limits of each metric.
- Use query digests to aggregate execution counts and costs of an SQL pattern.
- Query Performance Schema and `sys.statement_analysis` to locate time-consuming workloads.
- Combine the slow query log, execution plans, and application traces to find root causes.
- Prioritize optimizations based on overall impact rather than solely on the slowest single query.
- Track before/after changes while preserving semantics and service quality.

Examples assume MySQL 8.0 or later, Performance Schema enabled, and applications using prepared statements. Some columns, views, and tools can differ by version or configuration; verify directly against your running instance.

## 1. Four Questions When Observing a Query

When an endpoint or report is slow, break the issue into four questions:

| Metric | Question | What It Reveals |
|---|---|---|
| Latency | How long does each run take? How much total time is consumed? | Wait experience, tail latency, and cumulative cost |
| Rows examined | How many rows did the server inspect? | Scan scope and filtering work |
| Rows sent | How many rows did the server return? | Result size by row count and potential over-fetching |
| Execution frequency | How many times does the SQL pattern run over an interval? | Repeated queries, hot paths, and N+1 |

No single metric proves a query is good or bad. An aggregate query may examine many rows yet send one row; a primary-key lookup may examine one row and send one row; a query returning 10,000 rows may have low server latency yet be slow on the client due to network transfer and object hydration.

## 2. Latency: Single-Run Duration and Cumulative Cost

**Latency** is the duration from when a statement starts until it completes from the measurement tool's perspective. Distinguish MySQL server metrics from end-to-end latency recorded by the application.

### Common Latency Statistics

- **Average latency:** mean duration per execution. Useful for comparing trends, though it can hide very slow runs.
- **Maximum latency:** slowest execution within the statistics window. Useful for spotting outliers, though sensitive to a single isolated incident.
- **Total latency:** sum of durations across all executions in the measurement window. Helps identify SQL patterns consuming the most cumulative time.
- **p50, p95, p99:** percentiles describing the distribution. p95 is the level at or below which 95% of runs complete; p99 focuses on the slower tail.

For example, consider two query digests with these metrics:

| Query Pattern | Executions | Average | Approximate Total Latency |
|---|---:|---:|---:|
| A: order status lookup | 120,000 | 2 ms | 240 seconds |
| B: summary report | 20 | 1,200 ms | 24 seconds |

Query B is much slower per execution, yet pattern A consumes more total database time in the measurement window. Reducing A's latency from 2 ms to 1 ms can yield substantial cumulative savings.

Cumulative total latency is not system wall-clock time: many statements execute concurrently. Use it to compare relative contributions of digests over the same window, not to directly infer request duration or server busy time.

### Average Does Not Replace Percentiles

Suppose 99 requests finish in 5 ms and one request takes 2 seconds. The average may still look acceptable over a large enough sample, yet users hitting the slow run still experience timeouts or UI freezes.

Performance Schema digest summary tables provide execution count, total, average, and maximum; do not assume they retain enough raw samples to compute exact p95/p99. To track percentiles, use histograms or traces/metrics at the application layer, APM, or monitoring systems that store latency distributions. You can combine the slow query log and statement history to investigate specific slow runs.

### Server Latency vs. Application Latency

Time measured by the application may include:

- Waiting to acquire a connection from the connection pool.
- Sending the request over the network to MySQL.
- MySQL execution and lock/I/O waits.
- Transmitting results back to the client.
- Driver decoding, ORM object construction, and application processing logic.

Performance Schema measures server-side statement time; it does not include connection pool wait time or processing after data reaches the application. If application latency is high while statement latency is low, check pool wait, networking, bytes returned, and mapping time.

Statement timers reflect server elapsed time, including waits occurring within the statement's instrumentation scope; they are not pure CPU time. When separating CPU, lock waits, and I/O waits, combine wait events, file I/O, and operating system metrics.

## 3. Rows Examined and Rows Sent

### Rows Examined

`ROWS_EXAMINED` indicates the number of rows the server recorded as examined during statement execution. It is a useful indicator of whether a query had to filter a large range before producing results.

Example:

```sql
SELECT order_id, status
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-11-01';
```

Without an appropriate index for the predicates, MySQL may have to examine many rows before keeping orders for customer 42. High `ROWS_EXAMINED` signals a need to review access paths, indexes, and selectivity.

Rows examined does not equate to physical pages read from disk. A row may be found in the buffer pool; an index range scan may also traverse many index entries. To understand I/O, combine buffer pool, file I/O, and storage device metrics.

### Rows Sent

`ROWS_SENT` is the number of rows the server sent back to the client. It helps spot queries returning too many rows, especially when an endpoint only needs a small page or a few fields.

For example, a query returning 100,000 rows can create heavy network transfer, decoding, and object-allocation overhead even when MySQL reads the data efficiently. Check column counts, row width, pagination, and whether the application actually consumes the full result set.

Rows sent does not measure bytes. Two queries each sending 1,000 rows—one with two numeric columns, the other with large `TEXT`/JSON columns—can produce vastly different payload sizes and transfer times. Measure response bytes or network throughput when suspecting a data-transfer bottleneck.

### Examined-to-Sent Ratio

You can use the following ratio as a diagnostic signal:

\[
\text{examined per sent} = \frac{\text{rows examined}}{\text{rows sent}}
\]

If a query examines 500,000 rows yet sends only 20 rows, investigate why the scan scope is so much larger than the output. However, no universal threshold applies to all queries:

- `COUNT(*)`, `SUM()`, or `GROUP BY` queries may send very few rows while legitimately reading many rows.
- `UPDATE`/`DELETE` statements usually send 0 rows, making the ratio undefined; inspect rows examined alongside rows affected.
- Search queries may need to scan many candidates to guarantee accurate results.
- A full scan on a small table can be cheaper than index lookups and may not need fixing.

Do not optimize merely to drive the ratio down. Verify whether the query is doing unnecessary work relative to business requirements.

## 4. Execution Frequency and Query Digests

Applications often send the same SQL pattern with different parameter values:

```sql
SELECT order_id, status
FROM orders
WHERE customer_id = 42;

SELECT order_id, status
FROM orders
WHERE customer_id = 91;
```

Performance Schema normalizes literals into digests to group structurally identical runs together. Both statements above are typically aggregated into the same query digest. `COUNT_STAR` indicates how many times statements in that group executed since statistics were initialized or reset.

Grouping hides differences across parameter values. If `customer_id = 42` has millions of orders while `customer_id = 91` has only a few, the two runs can have vastly different latencies and rows examined while residing in the same digest. When `MAX_TIMER_WAIT` is high or distributions are unstable, correlate with application logs/traces to identify skewing parameters or tenants.

Frequency matters because:

- A 1 ms query executed 100,000 times can consume significant CPU and round trips.
- N+1 patterns generate high execution counts of one digest with changing key parameters.
- Overly frequent polling can add load even if each query is lightweight.
- One query digest may be called from multiple endpoints or tenants; application tracing is needed to identify the source.

### Total Time and Execution Counts

For each digest, inspect simultaneously:

- `COUNT_STAR`: execution frequency.
- `SUM_TIMER_WAIT`: cumulative total time.
- `AVG_TIMER_WAIT`: average duration.
- `MAX_TIMER_WAIT`: slowest recorded execution.
- `SUM_ROWS_EXAMINED` and `SUM_ROWS_SENT`: total rows examined and returned.
- `SUM_ROWS_AFFECTED`: total rows modified by write statements; helpful for UPDATE/DELETE where `ROWS_SENT` is typically 0.

A digest with high count and low average can still be a prime optimization target due to repetition. A digest with low count and very high max may warrant investigating data skew, lock waits, or parameter-dependent execution plans.

## 5. Query Digests in Performance Schema

MySQL stores digest statistics in `performance_schema.events_statements_summary_by_digest`. This table aggregates statement metrics since server startup or the corresponding statistics reset.

Example: finding the top 20 digests by total latency in the current schema:

```sql
SELECT SCHEMA_NAME,
       DIGEST_TEXT,
       COUNT_STAR AS exec_count,
       ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_latency_s,
       ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_latency_s,
       ROUND(MAX_TIMER_WAIT / 1000000000000, 6) AS max_latency_s,
       SUM_ROWS_EXAMINED AS rows_examined,
       SUM_ROWS_SENT AS rows_sent,
       SUM_ROWS_AFFECTED AS rows_affected,
       ROUND(SUM_ROWS_EXAMINED / NULLIF(COUNT_STAR, 0), 1)
           AS avg_rows_examined
FROM performance_schema.events_statements_summary_by_digest
WHERE SCHEMA_NAME = DATABASE()
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Performance Schema timers are expressed in picoseconds. Divide `SUM_TIMER_WAIT` by (10^{12}) to convert to seconds; divide `AVG_TIMER_WAIT` or `MAX_TIMER_WAIT` similarly. Do not read raw timer values as milliseconds.

Find the highest-frequency digests:

```sql
SELECT DIGEST_TEXT,
       COUNT_STAR AS exec_count,
       ROUND(AVG_TIMER_WAIT / 1000000000, 3) AS avg_latency_ms,
       ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_latency_s,
       SUM_ROWS_EXAMINED,
       SUM_ROWS_SENT
FROM performance_schema.events_statements_summary_by_digest
WHERE SCHEMA_NAME = DATABASE()
ORDER BY COUNT_STAR DESC
LIMIT 20;
```

Find digests examining many rows while returning few:

```sql
SELECT DIGEST_TEXT,
       COUNT_STAR,
       SUM_ROWS_EXAMINED,
       SUM_ROWS_SENT,
       ROUND(SUM_ROWS_EXAMINED / NULLIF(SUM_ROWS_SENT, 0), 1)
           AS examined_per_sent
FROM performance_schema.events_statements_summary_by_digest
WHERE SCHEMA_NAME = DATABASE()
  AND SUM_ROWS_SENT > 0
ORDER BY examined_per_sent DESC
LIMIT 20;
```

The third query only produces a shortlist for investigation. Filter out legitimate aggregate queries, verify intentional small-table scans, and inspect `EXPLAIN` before adding indexes.

### Other Useful Columns

Depending on version, the digest table also provides metrics such as:

- `SUM_CREATED_TMP_TABLES`, `SUM_CREATED_TMP_DISK_TABLES`: internal temporary tables recorded.
- `SUM_SORT_ROWS`, `SUM_SORT_MERGE_PASSES`: sorting activity.
- `SUM_NO_INDEX_USED`, `SUM_NO_GOOD_INDEX_USED`: counts where no index or no suitable index was used according to counters.
- `SUM_ERRORS`, `SUM_WARNINGS`: statement errors and warnings.
- `FIRST_SEEN`, `LAST_SEEN`: first and most recent timestamps the digest was recorded.

Counters are cumulative totals. Compare deltas between two points in time to calculate occurrence rates, especially on instances with long uptimes.

## 6. Using sys.statement_analysis for Quick Workload Inspection

MySQL ships the `sys` schema on many distributions. The `sys.statement_analysis` view presents digests in a more readable form, including execution count, total/average/max latency, rows sent, rows examined, temporary tables, and scan indicators.

```sql
SELECT query,
       exec_count,
       total_latency,
       avg_latency,
       max_latency,
       rows_sent,
       rows_examined,
       rows_examined_avg,
       tmp_tables,
       tmp_disk_tables,
       full_scan
FROM sys.statement_analysis
ORDER BY total_latency DESC
LIMIT 20;
```

You can sort by `exec_count` to locate frequently executed query patterns or by `rows_examined` to find patterns reading large volumes of data. `sys.statement_analysis` is a convenience view built on Performance Schema; if the view is missing or empty, check the `sys` schema, privileges, and relevant instruments/consumers.

## 7. Viewing Recent Executions

Digest summaries show aggregates, but sometimes you need to inspect a specific execution to uncover slow parameter values or lock wait timestamps. If statement history is enabled and entries remain in the ring buffer, you can query:

```sql
SELECT THREAD_ID,
       EVENT_ID,
       ROUND(TIMER_WAIT / 1000000000000, 6) AS latency_s,
       ROWS_EXAMINED,
       ROWS_SENT,
       MYSQL_ERRNO,
       SQL_TEXT
FROM performance_schema.events_statements_history_long
WHERE SQL_TEXT IS NOT NULL
ORDER BY TIMER_WAIT DESC
LIMIT 30;
```

`events_statements_history_long` holds only a bounded number of events; older data is overwritten. It is not long-term historical storage. If consumers or instruments are disabled, the table may be empty or missing events.

Check collection configuration:

```sql
SELECT NAME, ENABLED
FROM performance_schema.setup_consumers
WHERE NAME IN (
    'events_statements_current',
    'events_statements_history',
    'events_statements_history_long'
);

SELECT NAME, ENABLED, TIMED
FROM performance_schema.setup_instruments
WHERE NAME LIKE 'statement/%';
```

Enabling additional instruments/consumers can add overhead and increase history memory usage. Make observability configuration changes deliberately, test on staging, and balance detail against cost.

## 8. Slow Query Log: Finding Slow Runs

The slow query log records statements exceeding configured criteria. It is a good source for finding individual slow queries and retrieving sample SQL, though it does not replace digest summaries since fast, highly repeated queries may never cross the threshold.

Check settings:

```sql
SHOW VARIABLES LIKE 'slow_query_log';
SHOW VARIABLES LIKE 'long_query_time';
SHOW VARIABLES LIKE 'min_examined_row_limit';
SHOW VARIABLES LIKE 'log_output';
```

Example test configuration:

```sql
SET GLOBAL slow_query_log = ON;
SET GLOBAL long_query_time = 0.2;
SET GLOBAL min_examined_row_limit = 100;
```

GLOBAL changes typically apply to new connections; to test immediately in the current session, check and set the SESSION variable when SESSION scope is supported. Appropriate administrative privileges are required. Overly verbose logging can generate extra I/O and disk consumption; establish clear thresholds, enablement windows, and rotation/retention policies.

Do not enable `log_queries_not_using_indexes` broadly without evaluating your workload: many valid queries on small tables legitimately skip indexes and can rapidly inflate logs. Slow logs can also contain sensitive literals; restrict read access and protect log files.

## 9. Reading EXPLAIN to Explain Rows Examined

Once you identify a notable digest, take a representative SQL statement and inspect its plan:

```sql
EXPLAIN FORMAT=TREE
SELECT order_id, status
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-11-01'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Inspect these elements:

- Access method: `const`, `ref`, `range`, `index`, or `ALL`.
- Selected index and key length used.
- Estimated rows and residual filter predicates.
- Join order, sorts, temporary tables, and materialization.
- Which predicates apply early versus which filter after reading rows.

`EXPLAIN ANALYZE` executes the SELECT and reports actual rows and timings per iterator:

```sql
EXPLAIN ANALYZE
SELECT order_id, status
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-11-01'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Run it only when executing the query and its load are acceptable. Compare estimated rows against actual rows to spot stale statistics or skewed data distributions. `EXPLAIN ANALYZE` does not replace measuring end-to-end application latency.

## 10. Example: One Endpoint, Four Types of Issues

Suppose an endpoint displays a customer's 50 most recent orders. The table has an index:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    KEY ix_orders_customer_created
        (customer_id, created_at, order_id)
) ENGINE = InnoDB;
```

Query:

```sql
SELECT order_id, status, total_amount, created_at
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Observed scenarios:

| Metrics | Signal | Investigation Direction |
|---|---|---|
| High latency, high rows examined | Excessive data read or poor plan | Check indexes, selectivity, partition pruning, and statistics |
| Low latency, very high frequency | Repeated query or N+1 | Batch loading, per-request caching, reduce polling |
| High rows examined, low rows sent | Filtering many rows for few results | Check predicates, composite indexes, and early filtering |
| High rows sent, examined close to sent | Potentially returning too much data | Pagination, select fewer columns, limit payload |
| Low server latency, high application latency | Pool wait, network, or mapping | Measure pool waits, network, bytes, and client processing time |

The composite index `(customer_id, created_at, order_id)` aligns with the equality condition on `customer_id` and ordering by date/order ID. However, verify with `EXPLAIN` and real data; an index might not be chosen if the table is very small or the optimizer estimates a scan is cheaper.

## 11. Prioritizing Optimizations

Do not just pick the query with the highest `MAX_TIMER_WAIT`. Rank across multiple dimensions:

1. **Total latency:** digests consuming the largest total time in the measurement window.
2. **Frequency:** digests running excessively often, especially on hot endpoints or inside loops.
3. **Average and tail latency:** patterns delivering poor user experience or large outliers.
4. **Rows examined:** excessive read/filter volume relative to necessary work.
5. **Rows sent and payload:** queries returning unneeded rows or too many columns.
6. **Errors, warnings, temporary tables, and full scans:** supporting clues for underlying issues.
7. **Business criticality:** prioritize checkout, login, ordering, or flows with strict SLOs.

A practical approach is building a shortlist table:

| Digest | Exec count | Avg latency | Total latency | Avg examined | Avg sent | Priority |
|---|---:|---:|---:|---:|---:|---|
| A | Very high | Low | Very high | Medium | Low | Reduce call frequency |
| B | Low | Very high | Medium | High | Low | Investigate plan and lock waits |
| C | High | Medium | High | High | High | Reduce read scope and payload |

After each change, re-measure over an equivalent time window and workload. Do not compare a peak hour before optimization against an off-peak hour afterward and claim success.

## 12. Common Mistakes When Reading Metrics

| Mistake | Why It Is Wrong | Proper Interpretation |
|---|---|---|
| Looking only at average latency | Hides tail latency | Track p95/p99 in application/APM |
| Optimizing the single slowest query first | May run only once | Check total latency and frequency |
| Treating rows examined = disk reads | Many rows may be in buffer pool; counter does not count page I/O | Cross-check file I/O and buffer pool metrics |
| Treating rows sent = network bytes | Row widths differ | Measure payload bytes/network throughput |
| Lower examined/sent is always better | Valid aggregates may read many rows to return one | Check query type and business requirement |
| Treating digest summary as complete history | Summary and history tables have bounds/resets | Export periodically or use long-term monitoring |
| Assuming one digest maps to one endpoint | Same SQL can be called from multiple places | Correlate trace ID, service, and endpoint in the app |
| Full scan is always a bug | Scanning a small table can beat index access | Check plan, table size, and actual row count |

## 13. Workflow for Observing a Workload

1. Choose a representative measurement window; record timestamps, request volume, and load state.
2. Capture a digest snapshot from `events_statements_summary_by_digest`; save counts, latencies, rows, and timestamp.
3. After the interval, take a second snapshot and compute deltas per digest.
4. Rank by total latency, count, average/max latency, and rows examined.
5. Correlate with application-side p95/p99 and end-to-end latency.
6. Pick representative digests, inspect SQL, `EXPLAIN`, and where appropriate `EXPLAIN ANALYZE`.
7. Identify root causes: indexes, joins, N+1, payload, sorting, lock waits, I/O, or pool/network.
8. Change one variable at a time and re-run an equivalent workload.
9. Compare latency, frequency, rows examined, rows sent, bytes, and error rates.
10. Set up dashboards/alerts and save baselines to catch regressions.

When computing deltas from cumulative counters, handle server restarts or Performance Schema resets between samples. If a counter decreases, do not treat a negative difference as a rate; start a new measurement window.

Frequency within the window can be estimated as `(COUNT_STAR_new - COUNT_STAR_old) / elapsed_seconds`. Similarly, divide the `SUM_TIMER_WAIT` delta by (10^{12}) to get total seconds in the window. Always store timestamps for both snapshots so calculations do not depend on an assumed polling interval.

## 14. Hands-On Exercises

On a test MySQL instance containing the `orders` table from Section 10:

1. Run a lookup query by `customer_id` and observe `COUNT_STAR`, `SUM_TIMER_WAIT`, `SUM_ROWS_EXAMINED`, and `SUM_ROWS_SENT` in the digest summary.
2. Generate a repeated workload of the same SQL pattern with varied `customer_id` values. Confirm statements with different literals group into the corresponding digest.
3. Run an unindexed filter query on a sufficiently large table; compare rows examined before and after adding a suitable composite index.
4. Run a query returning all rows and then constrain it with pagination. Compare rows sent and application payload size.
5. Run an aggregate `COUNT(*)` or `SUM()` query and explain why low rows sent does not mean low rows examined.
6. Enable the slow query log with a test threshold and correlate slow runs with the digest summary.
7. Use `sys.statement_analysis` to find digests with high total latency and digests with high execution count.
8. Use `events_statements_history_long` to inspect recent executions if the consumer is enabled.
9. Measure p95/p99 at the application layer and compare with average/max in Performance Schema. Explain why the two sources do not replace each other.
10. Write a short report selecting three digests to optimize, citing evidence from latency, frequency, rows examined, and rows sent.

## Key Takeaways

- Latency measures time; rows examined reflects rows inspected; rows sent reflects rows returned; execution frequency shows repetition.
- Total latency identifies cumulative cost, while p95/p99 reveals tail latency; digest summaries do not provide full percentiles on their own.
- Performance Schema `events_statements_summary_by_digest` is a strong starting point for ranking workloads by SQL pattern.
- Rows examined is not disk reads; rows sent is not network bytes.
- A fast query running very frequently may be worth optimizing ahead of a rare slow query.
- Use the slow query log to locate slow runs, `EXPLAIN` to understand access paths, and application traces to find load-generating endpoints.
- Measure before and after under equivalent conditions and combine multiple metrics before declaring an optimization successful.
