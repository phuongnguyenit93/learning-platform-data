# Workflow for Load Measurement, Selecting Critical SQL, Fixing, and Re-verifying

SQL tuning is the process of identifying queries that consume significant resources, finding the root cause using measured data, and modifying the query, indexes, or data access pattern to improve results. Effective tuning does not start by adding indexes or rewriting every `SELECT`; it starts by understanding the workload and measuring a baseline.

A query with low average latency can still generate heavy load if it is called tens of thousands of times. A query taking several seconds that only runs in a monthly report may have lower priority than a query running on every request. Therefore, rank by overall impact, define clear goals (latency, throughput, I/O, CPU, or lock wait), then fix one cause at a time and verify using the same data, parameters, and load level.

## 1. SQL Tuning Is Workload Tuning

An application system typically runs hundreds or thousands of query patterns. The goal is not to make every SQL statement shorter, but to improve overall performance while preserving exact business results.

First questions to ask:

- Which query consumes the most database time during an observation window?
- Which query has high p95/p99 latency and directly affects users?
- Which query examines too many rows compared to the number of rows returned?
- Which query runs too frequently, causing high total CPU/I/O even though each execution is fast?
- Which query creates on-disk temporary tables, large sorts, or lock waits?
- Are there N+1 queries causing a single request to generate many round-trips?
- Is the bottleneck in SQL, indexes, data, concurrency, network, or the application?

Do not draw conclusions from a single execution. Buffer pool, caches, data hotness, concurrency, query parameters, and system state can cause execution time to vary significantly.

## 2. Define Goals and Baseline Before Making Changes

Before tuning, record the initial state (baseline). A useful baseline may include:

| Metric | Meaning | Used to evaluate |
| --- | --- | --- |
| Query count | Number of times a SQL pattern ran in the measurement window | Frequency and total load |
| Total latency | Total database time consumed | Contribution to workload |
| Average latency | Average time per execution | Average cost |
| p95 / p99 latency | Time threshold not exceeded by 95% / 99% of requests | Tail latency experience |
| Rows examined | Number of rows read/inspected | Filtering efficiency and access path |
| Rows sent | Number of rows returned to client | Comparing read work against result size |
| Temporary tables / disk temp tables | Usage of temporary tables and on-disk temp tables | Cost of sort, group, materialization |
| Sort rows / merge passes | Sorting work | Large ORDER BY/GROUP BY queries |
| Lock wait / deadlocks | Wait time and lock contention | Concurrency impact |
| CPU, I/O, buffer pool | Server-wide resources | Distinguishing SQL bottleneck from server bottleneck |

Lock in a measurable goal, for example: reduce p95 from 900 ms to under 300 ms, reduce average rows examined from 200,000 to under 5,000, or reduce the total time of the top digest by 30% under the same load window.

If you only measure the duration of a single statement on a development machine without measuring query count, p95, and concurrent load, you may end up tuning a low-impact query by mistake.

## 3. Collect Critical SQL Using the Slow Query Log

The Slow Query Log records statements that exceed a configured time threshold. It is a useful data source for finding slow queries, especially when you need to inspect the exact SQL and the number of rows examined.

Check the configuration:

```sql
SHOW VARIABLES LIKE 'slow_query_log';
SHOW VARIABLES LIKE 'long_query_time';
SHOW VARIABLES LIKE 'log_output';
SHOW VARIABLES LIKE 'log_queries_not_using_indexes';
```

In an environment with administrative privileges, you can enable the log and set the threshold at runtime:

```sql
SET GLOBAL slow_query_log = ON;
SET GLOBAL long_query_time = 0.5;
```

Changing `GLOBAL` sets the default for new connections; already open sessions may still retain the old `long_query_time` value. You can check or set it per session:

```sql
SELECT @@SESSION.long_query_time;
SET SESSION long_query_time = 0.5;
```

Runtime settings may be lost after a server restart if not persisted in the deployment configuration or service management system. Appropriate privileges such as `SYSTEM_VARIABLES_ADMIN` or equivalent administrative privileges for your MySQL version are required.

`log_queries_not_using_indexes` can produce very large logs, because many queries scanning small tables or reading most of a table are completely valid. Enable it only with a clear investigation goal and monitor log disk usage.

The Slow Query Log may contain literals, business information, or sensitive data. Protect log read permissions, configure retention, and avoid including sensitive content in shared reports.

## 4. Rank Workload Using Performance Schema

Performance Schema aggregates statements by digest (query patterns with normalized literals). You can find digests consuming large total time:

```sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 2) AS total_seconds,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_seconds,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    SUM_CREATED_TMP_DISK_TABLES,
    SUM_NO_INDEX_USED
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST_TEXT IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

The `*_TIMER_WAIT` columns in Performance Schema are expressed in picoseconds; divide by (10^{12}) to convert to seconds. `COUNT_STAR` shows execution count; `SUM_TIMER_WAIT` reveals total time for the digest; `AVG_TIMER_WAIT` gives the average.

You can rank by frequency or rows examined:

```sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    ROUND(SUM_ROWS_EXAMINED / NULLIF(COUNT_STAR, 0), 1)
        AS avg_rows_examined
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST_TEXT IS NOT NULL
ORDER BY SUM_ROWS_EXAMINED DESC
LIMIT 20;
```

Results are cumulative statistics since Performance Schema started collecting or since the last summary reset. It does not natively provide p95/p99 for every digest; use APM, application telemetry, or a metrics system to measure request latency percentiles.

If the `sys` schema is installed, the `sys.statement_analysis` view can present query statistics in a more readable format. Verify that the view exists in your environment before using it; not all MySQL-compatible services enable the exact same set of views.

## 5. Select Queries to Tune by Impact

A practical priority order:

1. Queries with the largest total time in the workload.
2. Queries with high p95/p99 on critical request paths.
3. Queries that examine many rows but return few rows.
4. Queries executed very frequently, even if per-execution latency is low.
5. Queries causing on-disk temporary tables, large sorts, or lock waits.
6. Queries that increase concurrent load, such as an update touching many rows or N+1 queries.

For example, digest A runs 100,000 times at 5 ms each, totaling 500 seconds. Digest B runs 10 times at 2 seconds each, totaling 20 seconds. If the goal is to reduce overall load, A may deserve higher priority than B; if B blocks a critical administrative operation, business priority may differ.

Do not sort solely by `AVG_TIMER_WAIT`. Combine execution count, total latency, rows examined, request criticality, and latency percentiles.

## 6. Reproduce Queries with Representative Parameters and Data

After selecting a digest, retrieve the concrete SQL statement from the slow log, APM, or application logs. You need to know:

- Common bind parameter values and edge cases.
- Table size, row count, and data distribution.
- Existing indexes and optimizer statistics.
- Execution frequency and concurrency.
- Expected results and NULL/duplicate edge cases.
- Isolation level and transaction context if the query writes or performs locking reads.

A SQL statement with a `customer_id` that has 2 orders can be very fast, while for a tenant with 20 million orders it can be very slow. Small lab datasets or uniformly distributed data are not representative of production.

Standardize the test harness: same parameters, same schema/indexes, same concurrency level, same cache state if possible, and record the MySQL version. Do not change multiple variables at once.

## 7. Read EXPLAIN Before Modifying SQL

`EXPLAIN` shows the execution plan the optimizer expects to use:

```sql
EXPLAIN
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
  AND status = 'paid'
ORDER BY created_at DESC
LIMIT 20;
```

Common fields to inspect:

- `type`: access method such as `const`, `eq_ref`, `ref`, `range`, `index`, `ALL`.
- `possible_keys`: indexes considered by the optimizer.
- `key`: the chosen index.
- `key_len`: length of the index prefix used.
- `rows`: estimated number of rows to read.
- `filtered`: estimated percentage of rows remaining after filter conditions.
- `Extra`: indicators such as `Using where`, `Using index`, `Using temporary`, `Using filesort`.
- `partitions`: partitions accessed if the table is partitioned.

Do not judge a plan solely by `type`. A full table scan can be appropriate if the table is small or the query needs most of the data. `Using filesort` is also not automatically an error; check the number of sorted rows, duration, and whether an index can be leveraged.

For complex plans, use:

```sql
EXPLAIN FORMAT=JSON
SELECT ...;
```

JSON provides finer detail on query blocks, access paths, costs, and row estimates. When suspecting inaccurate estimates, compare against actual row counts.

## 8. Use EXPLAIN ANALYZE to Measure Actual Execution

On MySQL 8.0.18 and later, `EXPLAIN ANALYZE` executes the query and displays actual timing, actual row counts, and loop counts for each iterator:

```sql
EXPLAIN ANALYZE
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
  AND status = 'paid'
ORDER BY created_at DESC
LIMIT 20;
```

Compare:

- `estimated rows` vs `actual rows`.
- `loops` to see how many times an iterator was invoked.
- `actual time` to pinpoint the time-consuming step.
- Rows entering and leaving after filters/joins.

`EXPLAIN ANALYZE` actually runs the query; it does not just print a static plan. Use it with appropriate `SELECT` queries in a safe environment and on representative data. For heavy queries, consider production load and execution time before running.

If estimates diverge sharply, check table/index statistics, data skew, histograms, column correlations, and whether the optimizer chose a poor join order. Do not rush to add hints before understanding the root cause.

## 9. Fix Predicates so Indexes Can Be Used

Filter predicates should keep indexed columns in a directly comparable (sargable) form whenever possible.

Non-preferred example:

```sql
SELECT order_id
FROM orders
WHERE DATE(created_at) = '2026-03-15';
```

The `DATE()` function is applied to the column; a regular B-tree index on `created_at` may not be used effectively for this range lookup.

Rewrite as a range:

```sql
SELECT order_id
FROM orders
WHERE created_at >= '2026-03-15 00:00:00'
  AND created_at <  '2026-03-16 00:00:00';
```

Other cases to watch for:

- Avoid implicit type conversions on indexed columns; bind parameters with the exact data type.
- Avoid `LOWER(indexed_column) = ...` unless you have an appropriate functional index or generated column strategy.
- `LIKE 'prefix%'` can leverage a B-tree under appropriate conditions; `LIKE '%suffix'` usually cannot use a B-tree for prefix lookup.
- Avoid arithmetic expressions on columns in conditions if the computation can be moved to the constant side.
- For nullable columns, preserve `NULL` semantics explicitly; do not substitute arbitrary default values just to "make index usage easier".

For every rewrite, verify equivalent results, timezone handling, datetime precision, collation, and NULL rules.

## 10. Select Only the Columns You Need

`SELECT *` can read and transmit more data than necessary, especially when the table contains `TEXT`, `BLOB`, large JSON, or many rarely used columns.

Non-preferred:

```sql
SELECT *
FROM customers
WHERE customer_id = 42;
```

If the UI only needs name and status:

```sql
SELECT customer_name, status
FROM customers
WHERE customer_id = 42;
```

Benefits can include fewer bytes read from storage, less data sent over the network, lower server/client memory usage, and higher chance of using a covering index. Not every query needs a covering index; do not add many columns to an index just to avoid a few lookups without measuring write cost and index size.

## 11. Design Composite Indexes Around Query Predicates

Composite indexes should be designed around the columns queries actually use. For example:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
  AND status = 'paid'
ORDER BY created_at DESC
LIMIT 20;
```

A candidate index:

```sql
CREATE INDEX idx_orders_customer_status_created
ON orders (customer_id, status, created_at);
```

Two equality predicates come before the timestamp sort column. InnoDB can use the leftmost prefix of the index and read the customer/status slice in chronological order. Check `EXPLAIN` to confirm the actual plan.

Key principles:

- Leftmost prefix: an index `(a, b, c)` can support predicates on `a`, `(a,b)`, or `(a,b,c)`; it is not an equivalent choice for predicates on `b` alone.
- Equality columns are typically placed before range/order columns in many query patterns, though optimal order depends on workload and selectivity.
- After a range condition, trailing columns may no longer be used to narrow the range in the same way, though they can still support covering or residual predicates.
- Adding columns to an index helps queries but increases storage size and the cost of every write operation.
- InnoDB stores the primary key inside secondary indexes; account for that before redundantly adding primary key columns.

Do not create an index simply because a column appears in `WHERE`. Consider how the query combines `WHERE`, `JOIN`, `ORDER BY`, `GROUP BY`, row count, and frequency.

## 12. Choose Indexes by Selectivity and Workload

A column with few distinct values is not necessarily useless in an index. If one value is very rare, an index can still be highly selective for that value. Conversely, a high-cardinality column where queries routinely request 80% of the table may bring no benefit.

For example, `status` has values `active`, `pending`, `failed`. If `active` accounts for 95% of the table, `WHERE status = 'active'` may use a full scan. However, `status = 'failed'` only matches 0.1%, where an index can be very helpful.

Check the distribution:

```sql
SELECT status, COUNT(*) AS row_count
FROM orders
GROUP BY status
ORDER BY row_count DESC;
```

After a bulk load or major distribution shift, consider updating statistics:

```sql
ANALYZE TABLE orders;
```

For heavily skewed columns, histograms can help the optimizer estimate single-column selectivity. Histograms do not replace composite indexes and do not fully capture multi-column correlation.

## 13. Reduce JOIN Cost

When a JOIN query is slow:

- Verify that JOIN conditions have matching data types and identical comparison semantics.
- Create appropriate indexes on join keys on the lookup side.
- Filter early with selective conditions if doing so suits the query plan.
- Avoid joining independent one-to-many tables before aggregating, which causes fan-out row multiplication.
- Select only needed columns from each table.
- Use `EXISTS` when you only need to check for related rows; use `JOIN` when you need columns from both sides.
- Inspect estimated/actual rows at each iterator, especially nested loops with many `loops`.

Example finding customers who have at least one paid order:

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'paid'
);
```

If you need each order alongside customer details, `JOIN` is the right semantics. Do not replace JOIN with EXISTS just to reduce row count if the application actually needs every detail row.

## 14. ORDER BY, LIMIT, and Pagination

`ORDER BY` may require a sort if no index supports the ordering. When a query fetches a small page, an index aligned with both the filter and sort order allows MySQL to stop early once enough rows are found.

Example:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

You can evaluate index `(customer_id, created_at)`; InnoDB secondary indexes store the primary key, so primary key order can also participate in index order. Still, sort direction and the actual plan should be verified with `EXPLAIN`.

### 14.1. Large OFFSET

Pagination like:

```sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 100000;
```

typically must traverse many rows before discarding the first 100,000 rows, even though it only returns 20 rows. As offset grows, cost increases with page position.

### 14.2. Keyset Pagination

If the application can pass a cursor from the last row of the previous page, use keyset pagination:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
  AND (
      created_at < '2026-03-15 10:00:00'
      OR (
          created_at = '2026-03-15 10:00:00'
          AND order_id < 900100
      )
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

An index `(customer_id, created_at)` can support cursor-based access; verify the plan and actual distribution. A deterministic sort order is required, typically adding a unique key as a tie-breaker. Keyset pagination avoids skipping a huge offset and stays more stable when new rows are inserted at the top of the list.

## 15. Optimize GROUP BY and Aggregations

For aggregation queries, check:

- Can data be filtered before grouping?
- Does an index support both filter columns and grouping columns?
- Are multiple child tables being joined before aggregating, multiplying rows?
- Is `DISTINCT` actually needed before aggregating?
- Can results be pre-aggregated in a derived table/CTE before joining?
- Can a summary/materialized table be maintained in batches if freshness requirements permit?

Example totaling amount per customer over a time range:

```sql
SELECT customer_id, SUM(total_amount) AS paid_total
FROM orders
WHERE status = 'paid'
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01'
GROUP BY customer_id;
```

A suitable index might be `(status, created_at, customer_id)` or another order depending on selectivity and related queries. You cannot determine the best order from column names alone; measure on real data.

## 16. Avoid N+1 Queries and Unnecessary Round-Trips

N+1 occurs when the application fetches a list and then runs a separate query for each row. For example, fetching 100 customers and then running 100 queries to fetch their latest order. Each query may be fast, but total latency grows due to network round-trips and repeated parse/execute overhead.

Possible remedies include:

- Use JOIN when related data is needed in the same result set.
- Use a single `IN (...)` query for a moderately sized set of IDs, then merge results in the application.
- Use window functions or a derived table to fetch the latest record per group.
- Batch write operations instead of sending individual small statements when business logic allows.
- Inspect query count per request using APM or tracing.

Do not force everything into one giant query at all costs. If a JOIN query creates massive fan-out or returns redundant data, multiple controlled/batched queries may be better. Compare round-trip count, bytes transferred, and actual rows.

## 17. Optimize DML and Batch Writes/Deletes

`UPDATE`/`DELETE` statements also need optimized access paths. Unindexed predicates can scan many rows, hold locks for a long time, and impact other transactions.

Example updating a group of orders:

```sql
UPDATE orders
SET status = 'archived'
WHERE status = 'completed'
  AND created_at < '2025-01-01';
```

Check index coverage for the condition, actual affected rows, and lock duration. For very large datasets, process in batches if business logic allows partial commits:

```sql
DELETE FROM audit_events
WHERE occurred_at < '2024-01-01'
ORDER BY occurred_at
LIMIT 1000;
```

The application can loop batches until no matching rows remain, tracking affected rows and duration per batch. Batching changes atomicity: each commit is independent; use it only if the workflow accepts partial progress and can resume after failure.

Never run a massive delete on production without evaluating locks, undo, redo, replication lag, binlog volume, and backup size.

## 18. Transactions and Concurrency Are Also Part of SQL Tuning

A query that is fast in isolation can still slow down the system if it holds locks for a long time or runs inside a long-lived transaction.

Principles:

- Keep transactions short; do not call external APIs while holding locks.
- Use appropriate indexes to minimize rows scanned/locked.
- Update multiple rows in a consistent order to reduce deadlocks.
- Use conditional UPDATEs for simple read-modify-write patterns.
- Classify deadlocks and lock wait timeouts; retry the entire transaction with bounds when appropriate.
- Monitor lock waits, long-running transactions, and deadlocks alongside query latency.

If `EXPLAIN ANALYZE` shows the query is fast yet requests are still slow, check connection pool wait time, lock wait, network latency, and application processing time.

## 19. Controlled Experiments: Change One Variable at a Time

Once you identify a cause, form a concrete hypothesis:

- "This composite index will reduce rows examined from 80,000 to under 500."
- "Changing the date predicate to a range will enable a range scan."
- "Keyset pagination will avoid reading/skipping 100,000 rows."
- "Aggregating before JOIN will eliminate fan-out and reduce intermediate rows."

Then:

1. Save the baseline SQL, plan, row counts, latency, and existing indexes.
2. Apply one change: query rewrite, index, histogram, or schema change.
3. Run with the same parameters and representative data.
4. Measure actual rows, loops, latency, CPU/I/O, and lock wait.
5. Verify that the SQL results are completely equivalent.
6. Check impact on other queries and DML overhead from any new index.
7. Repeat under near-production concurrency.

Do not add three indexes and rewrite the query at the same time and guess which change produced the benefit. Testing one factor at a time clarifies causality and makes rollback easier.

## 20. Measure Properly: Cache, Concurrency, and Latency Percentiles

When benchmarking, clearly record the cache state. The first run may read from disk; subsequent runs may serve most data from the buffer pool. Comparing a cold-cache run against a warm-cache run leads to false conclusions.

Measurement principles:

- Run enough iterations to avoid concluding from a single sample.
- Use representative parameters including both common and rare values.
- Keep the same client count/concurrency when comparing.
- Measure p50, p95, and p99 alongside average.
- Observe throughput and server resources, not just single-client latency.
- Separate pool wait, network, and application time from database time if telemetry is available.
- Do not clear production caches to run benchmarks; that can trigger a load spike.

`EXPLAIN ANALYZE` is helpful for understanding iterators, but it adds measurement overhead and usually runs a single query in isolation. Load tests or application telemetry better reflect behavior under concurrent load.

## 21. Optimizer Statistics and Histograms

Plans depend on statistics. After a bulk load, deleting many rows, or significant distribution shifts, consider:

```sql
ANALYZE TABLE orders;
```

For a single column with a skewed distribution where appropriate, you can evaluate a histogram:

```sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status WITH 32 BUCKETS;
```

MySQL histograms describe single-column distributions; they do not fully describe multi-column correlation. If queries filter multiple columns simultaneously, composite indexes and prefix statistics may be more appropriate. After updating statistics, re-check the plan and other critical queries.

## 22. When Do You Need Query Rewrite, Index, Schema, or Cache?

| Symptom | Approach to evaluate | Verification |
| --- | --- | --- |
| Rows examined much higher than rows sent | Fix predicates, indexes, partition pruning, or query shape | `EXPLAIN ANALYZE`, rows examined |
| `DATE(column)` or function on indexed column | Rewrite as range condition or use appropriate functional/generated index | `EXPLAIN` and equivalent results |
| Large sort for `ORDER BY ... LIMIT` | Index matching filter and sort order | `EXPLAIN`, actual rows, and sort work |
| Very large OFFSET | Keyset pagination | Measure rows/latency on deep pages |
| N+1 queries | JOIN, batching, or query by ID set | Queries/request, bytes, and latency |
| JOIN causes fan-out | Aggregate before JOIN or switch to EXISTS if only existence is needed | Compare row counts and totals |
| Severe estimate mismatch | Update statistics/histograms, check skew/correlation | Estimated vs actual rows |
| High lock wait | Short transactions, indexes, lock ordering, and conditional DML | Lock wait/deadlock metrics |
| SQL already tuned but data is read repeatedly | Consider caching or summary tables | Hit rate, freshness, invalidation |
| Schema stores heavy LOBs for list queries | Select only needed columns or split metadata/content | I/O, bytes returned, and latency |

Caching is not the first step for every slow query. Caching introduces invalidation, stale data, memory, and consistency challenges. Optimize the query and access path first; cache only when data is read repeatedly, freshness policy is clear, and the benefit is measured.

## 23. Optimizer Hints Are Only a Last Resort

MySQL offers optimizer hints and index hints, but forcing the optimizer to use a specific index or join order may help a current dataset and then become a poor choice when data distribution shifts.

Before adding a hint:

- Confirm the estimation error with `EXPLAIN ANALYZE`.
- Check statistics, histograms, and composite indexes.
- Measure across multiple parameters with differing selectivity.
- Verify the hint targets the intended query block and MySQL version.
- Document the rationale, measurements, and plan for removing the hint.

Do not use `FORCE INDEX` simply because you see `type = ALL`; a full scan can be the right plan when most of the table must be read.

## 24. Deploy Changes to Production Safely

An optimization change should be deployed in a controlled manner:

1. Save the SQL and pre-change baseline.
2. Test correctness, NULLs, duplicates, time boundaries, and permissions.
3. Assess index creation or table rebuild cost, disk space, and metadata locks.
4. Deploy in an appropriate window; on large systems, evaluate online DDL and replication impact.
5. Monitor query digests, p95/p99, throughput, CPU/I/O, lock waits, and error rates.
6. Have a rollback plan for the query or index if load degrades.
7. Record actual results and update operational documentation.

A new index can improve SELECTs while slowing down INSERT/UPDATE/DELETE and increasing backup size. A query rewrite can alter NULL or duplicate handling. Never deploy based solely on local benchmarks.

## 25. Common Mistakes and Misconceptions

| Misconception / mistake | Reality | How to handle |
| --- | --- | --- |
| Tuning the SQL with highest average latency is enough | Total load also depends on query count and p95/p99 | Rank by total latency, frequency, and business impact |
| Every full table scan is bad | A full scan can be cheaper than an index when reading most of a table | Inspect selectivity, actual rows, and duration |
| Adding an index always speeds up queries | Indexes increase write cost and may not be chosen by the optimizer | Measure read gain and DML cost |
| EXPLAIN rows is the actual row count | It is an estimate | Use EXPLAIN ANALYZE to see actual rows and loops |
| EXPLAIN ANALYZE only displays, does not run the query | It executes the query | Run suitable SELECTs and assess load |
| SELECT * does not matter if LIMIT is present | LOBs/large columns can still increase I/O and bytes transferred | Select only required columns |
| DISTINCT always fixes duplicate JOIN rows | It can mask fan-out bugs and add costly sort/hash work | Determine cardinality and semantics first |
| Large OFFSET is cheap because LIMIT is small | The server may still have to skip many rows | Use keyset pagination for deep pages |
| Histograms solve every estimate error | Single-column histograms do not fully describe correlations | Evaluate composite indexes and actual rows |
| Retrying or increasing timeouts fixes slow queries | Root cause may be scans, locks, or a bad plan | Measure the actual bottleneck before changing timeouts |
| Caching is always better than fixing SQL | Caching has invalidation and consistency costs | Optimize query/access path before evaluating cache |

## 26. Single-Query Tuning Checklist

Before concluding a query is tuned, check:

- [ ] Baseline recorded with query count, latency, and rows examined.
- [ ] High-impact query selected appropriately.
- [ ] Reproduced with representative parameters and data.
- [ ] Business results remain identical.
- [ ] Read `EXPLAIN`/`EXPLAIN FORMAT=JSON`.
- [ ] Compared estimated rows with actual rows where applicable.
- [ ] Are predicates sargable and bind types exact?
- [ ] Are there `SELECT *`, LOBs, or unnecessary columns?
- [ ] Does the composite index match filter, join, and order/group?
- [ ] Are there fan-out, N+1, or large OFFSET issues?
- [ ] Have transactions, lock waits, and concurrency been evaluated?
- [ ] Have p95/p99, throughput, CPU/I/O, and write costs been measured?
- [ ] Changed only one factor at a time with a rollback plan ready?

## 27. Practice Exercises

1. Enable the Slow Query Log in a lab environment with an appropriate `long_query_time`; run an intentionally slow query and inspect the log.
2. Use `performance_schema.events_statements_summary_by_digest` to rank the top 20 digests by total time and rows examined.
3. Pick a query with high rows examined and low rows sent; record the baseline before fixing.
4. Run `EXPLAIN` and `EXPLAIN ANALYZE`; identify the first iterator where actual rows diverge from estimated rows.
5. Rewrite `DATE(created_at) = ...` into a date range; compare the plan and results.
6. Design a composite index for a query filtering by customer/status and sorting by timestamp; measure both SELECT and INSERT/UPDATE cost.
7. Compare `SELECT *` against an explicit column list on a table with TEXT/BLOB columns.
8. Compare `LIMIT ... OFFSET ...` on the first page and a deep page against keyset pagination.
9. Find an N+1 query in a sample application; replace it with a JOIN or batch query and measure round-trips.
10. Construct a JOIN across multiple child tables causing fan-out; fix it by aggregating before the JOIN and verify totals.
11. Run the query under concurrency; compare average, p95/p99, throughput, and lock waits.
12. Write a before/after report including hypothesis, change, results, side costs, and rollback procedure.

## 28. Key Takeaways

SQL tuning starts with workload and baseline. Collect queries using the Slow Query Log, Performance Schema digests, or APM; rank by total latency, query count, p95/p99, rows examined, temporary tables, and business impact. Reproduce with representative data and parameters, read `EXPLAIN`, then use `EXPLAIN ANALYZE` to compare estimated rows, actual rows, loops, and timing.

Fix root causes in the right order: sargable predicates, selecting only needed columns, composite indexes following the leftmost prefix, JOIN/cardinality, GROUP BY, ORDER BY/LIMIT, keyset pagination, N+1, and transaction/concurrency. Update statistics when needed, keeping in mind that single-column histograms do not fully capture correlation. Change one factor at a time, re-measure under representative load, verify correctness and write cost, and deploy with monitoring and a rollback plan. No single index, hint, or query rewrite is universally optimal for every workload.
