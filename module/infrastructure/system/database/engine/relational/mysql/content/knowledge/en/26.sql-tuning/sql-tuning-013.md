# Controlling Unbounded Queries or Queries Reading Excessive Data

A query may return very few rows yet still force MySQL to read a massive volume of data. Conversely, a query returning many rows is not necessarily a problem if its read scope is bounded, suitable indexes exist, and results are processed in batches.

When controlling queries, distinguish three limits:

- **Result limits**: the number of rows and bytes returned to the application.
- **Read-work limits**: the number of rows/index entries that must be scanned to find the result.
- **Resource and time limits**: execution duration, memory, I/O, locks, and concurrent load.

LIMIT only caps the number of rows returned. It does not automatically bound the number of rows that must be read or sorted. A query without WHERE, an overly broad predicate, an ORDER BY without supporting index order, or a join missing a condition can all read and process far more data than expected.

This article presents how to design queries with explicit bounds, use indexes to limit read work, paginate stably, read/process data in batches, protect SELECT statements with timeouts, and monitor rows examined versus rows sent.

## 1. Illustrative Table Setup

The examples use an orders table:

~~~sql
CREATE TABLE sales_orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status_code TINYINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    total DECIMAL(13, 2) NOT NULL,
    payload JSON NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_tenant_created
        (tenant_id, created_at, order_id),
    KEY idx_orders_tenant_status_created
        (tenant_id, status_code, created_at, order_id),
    KEY idx_orders_created
        (created_at, order_id)
) ENGINE = InnoDB;
~~~

Indexes are designed for common query patterns:

| Index | Purpose |
|---|---|
| PRIMARY (order_id) | Reading or processing by primary key |
| (tenant_id, created_at, order_id) | Filtering by tenant and time range, sorting chronologically |
| (tenant_id, status_code, created_at, order_id) | Filtering by tenant, status, and time |
| (created_at, order_id) | System-wide chronological scans |

This is an illustrative schema. Do not create all these indexes in production merely because they appear here; select indexes based on your actual workload and measure write costs.

## 2. Identifying Unbounded Queries

A query without any filter predicate:

~~~sql
SELECT *
FROM sales_orders;
~~~

may have to read the entire table and ship all results to the client. As the table grows from thousands to tens of millions of rows, the exact same SQL becomes a major load source for the database, network, and application.

A query with WHERE whose scope is still too broad:

~~~sql
SELECT order_id, customer_id, total
FROM sales_orders
WHERE created_at >= '2020-01-01';
~~~

If data since 2020 accounts for nearly the entire table, this predicate barely limits the data read.

A query with LIMIT that can still read heavily:

~~~sql
SELECT order_id, customer_id, total
FROM sales_orders
WHERE YEAR(created_at) = 2026
ORDER BY total DESC
LIMIT 20;
~~~

The YEAR() function wraps the column and ORDER BY total is unsupported by a single index covering the entire condition. MySQL may have to read many matching rows, evaluate the expression, and sort before returning 20 rows.

### 2.1. Do Not Look Only at Returned Rows

Distinguish two metrics:

- rows sent: number of rows shipped to the client.
- rows examined: number of rows inspected by the server/storage engine during execution, as reported by MySQL.

For instance, a query returning 20 rows while examining 500,000 rows has a very high examined/sent ratio. That is a signal to investigate, even though the API response is tiny.

This ratio is only an indicator. For a query returning 0 rows, division is meaningless; for an aggregate query, rows sent can be 1 even when millions of rows must be read. Also inspect the plan, timing, I/O, and query type.

## 3. Bound Results with Business Predicates

A well-crafted query explicitly expresses the scope required by the user or job:

~~~sql
SELECT order_id, customer_id, created_at, total
FROM sales_orders
WHERE tenant_id = 42
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00'
ORDER BY created_at DESC, order_id DESC
LIMIT 100;
~~~

This query includes:

- tenant_id to scope data to one tenant.
- Half-open time range to bound dates read.
- Deterministic ORDER BY with order_id as tie-breaker.
- LIMIT to cap returned rows.
- Projection selecting only columns needed by the screen.

### 3.1. Use Half-Open Time Ranges

When filtering DATETIME by day or month, prefer:

~~~sql
WHERE created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00'
~~~

This range captures every instant in January without guessing an end-of-day timestamp. It also keeps created_at bare so an index range scan can be used.

Avoid writing:

~~~sql
WHERE DATE(created_at) = '2026-01-01'
~~~

because DATE() wraps the column. If business logic mandates filtering by an expression, consider a functional index or generated column; if only a calendar day is needed, a half-open range is usually simpler.

### 3.2. Do Not Let Clients Choose Unbounded Scopes

For search or reporting APIs, enforce input bounds at the application tier:

- Require a tenant or authorization scope.
- Enforce a maximum date range, such as disallowing multi-year queries in a synchronous request.
- Cap page size and set a sensible default.
- Reject or offload to a background job if a user requests a huge export.
- Never allow blank parameters to accidentally drop the entire WHERE clause.

Tenant scoping is one example; non-multi-tenant systems still need appropriate business bounds such as status, time range, or data partition.

## 4. LIMIT Caps Output, Not Input Data Read

LIMIT:

~~~sql
SELECT order_id, total
FROM sales_orders
ORDER BY total DESC
LIMIT 10;
~~~

only asks to return at most 10 rows. If MySQL has no index matching total DESC order, it may have to read and sort many rows to find the 10 largest.

When an index matches both filter predicates and sort order, MySQL can walk the index and stop once enough rows are gathered. Example:

~~~sql
SELECT order_id, created_at, total
FROM sales_orders
WHERE tenant_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Index (tenant_id, created_at, order_id) can filter by tenant and read chronologically. When both sort key parts share the same direction, InnoDB can scan an ascending B-tree index backward to serve descending order.

### 4.1. LIMIT Can Still Require Large Scans or Sorts

Common scenarios:

- Missing WHERE and missing suitable index.
- WHERE uses functions or conversions that disable range access.
- ORDER BY does not match index order.
- GROUP BY or DISTINCT must process many rows before final output is known.
- Joins produce many intermediate rows before LIMIT is applied.
- Large OFFSET forces MySQL to skip many rows before returning the target page.

Therefore, inspect EXPLAIN to verify whether LIMIT enables early index termination or still processes a massive dataset.

### 4.2. ORDER BY Must Have Deterministic Ordering

If multiple rows share the same created_at, ORDER BY created_at alone can yield differing results across runs. Add a unique key as a tie-breaker:

~~~sql
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Deterministic ordering stabilizes pagination and prevents rows from repeating or disappearing when sort values tie.

## 5. Select Only Required Columns

Avoid SELECT * in APIs or reports needing only a few fields:

~~~sql
SELECT *
FROM sales_orders
WHERE tenant_id = 42
ORDER BY created_at DESC
LIMIT 100;
~~~

If payload holds large JSON, the query may transmit hundreds of kilobytes or megabytes even though the UI only needs order ID, date, and total.

List columns explicitly:

~~~sql
SELECT order_id, created_at, total
FROM sales_orders
WHERE tenant_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 100;
~~~

Benefits:

- Reduces bytes read from storage or buffer pool when a covering index can be used.
- Reduces bytes sent across the network.
- Reduces application memory used for deserializing and holding results.
- Reduces JSON serialization or object mapping work.
- Reduces API fragility when schema columns are added.

Listing fewer columns does not automatically guarantee a covering index. Inspect EXPLAIN and index definitions to confirm whether MySQL still needs clustered record lookups.

## 6. Paginate Without Re-Reading Too Many Rows

Large OFFSET is a common source of wasted reads:

~~~sql
SELECT order_id, created_at, total
FROM sales_orders
WHERE tenant_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 50 OFFSET 500000;
~~~

MySQL must traverse rows ahead of the OFFSET position before returning the next 50 rows. As OFFSET grows, work scales accordingly.

For large lists, consider keyset pagination. First page:

~~~sql
SELECT order_id, created_at, total
FROM sales_orders
WHERE tenant_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Suppose the last row of the previous page has created_at = '2026-02-15 10:30:00' and order_id = 9000. Next page:

~~~sql
SELECT order_id, created_at, total
FROM sales_orders
WHERE tenant_id = 42
  AND (created_at, order_id) < ('2026-02-15 10:30:00', 9000)
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

The tuple continuation predicate starts right after the previous page's final key in descending order. Index (tenant_id, created_at, order_id) can locate the next position and read 50 rows.

Keyset pagination suits infinite-scroll lists or APIs iterating over large datasets. It does not offer arbitrary page-number jumps like OFFSET; clients carry a cursor holding the last sort values.

### 6.1. Cursors Must Carry All Sort Keys

If you only store created_at while multiple orders share the same timestamp, the next page can repeat or skip rows. Cursors need every ORDER BY column, including a unique tie-breaker key.

If the order is:

~~~sql
ORDER BY status_code ASC, created_at DESC, order_id DESC
~~~

the cursor must include status_code, created_at, and order_id, and the continuation predicate must reflect each column's individual sort direction. Never use a simple tuple comparison when ASC/DESC directions are mixed without verifying the logic.

### 6.2. Data Changes During Pagination

Keyset pagination avoids OFFSET skipping overhead, yet it does not automatically create an immutable snapshot across requests. If rows are inserted, deleted, or have sort columns updated while a client browses, result sets can shift.

Depending on business requirements, you can:

- Accept that each page reflects current data.
- Anchor a timestamp or high-water mark in the cursor.
- Run background exports against a fixed key set.
- Use a consistent snapshot inside a transaction if strict consistency is required, while weighing long-transaction costs.

## 7. Read Large Datasets in Batches

When processing an entire dataset for export, migration, or sync, never default to loading the whole result into application memory.

A common approach is scanning by primary key in batches:

~~~sql
SELECT order_id, tenant_id, created_at, total
FROM sales_orders
WHERE order_id > 0
  AND order_id <= 9000000
ORDER BY order_id
LIMIT 1000;
~~~

The application saves the last processed order_id. The next batch uses that value:

~~~sql
SELECT order_id, tenant_id, created_at, total
FROM sales_orders
WHERE order_id > 1250
  AND order_id <= 9000000
ORDER BY order_id
LIMIT 1000;
~~~

In production code, replace 1250 with the previous batch's final checkpoint. The primary key locates the next slice without skipping all previously processed rows.

### 7.1. Lock In a High-Water Mark

If a job must process the dataset present at start time, capture an upper bound before running:

~~~sql
SELECT MAX(order_id) AS high_water_mark
FROM sales_orders;
~~~

Suppose the result is 9000000. Each batch uses:

~~~sql
WHERE order_id > ?
  AND order_id <= 9000000
ORDER BY order_id
LIMIT 1000;
~~~

Newly inserted rows with order_id above the watermark will not extend the job indefinitely. A high-water mark does not guarantee a consistent snapshot for older rows updated or deleted in flight; if that matters, design a snapshot or versioning mechanism.

### 7.2. Safe Checkpoint Handling

A batch worker should:

1. Read at most N rows past the checkpoint.
2. Process and write output idempotently whenever possible.
3. Persist the checkpoint only after the batch succeeds.
4. If an error occurs mid-batch, replay the batch without causing duplicate side effects.
5. Log checkpoint, row count, and duration for each batch.

Never advance the checkpoint before batch writes are safely committed; if the process halts midway, rows would be skipped.

### 7.3. Batch Size

Batches that are too large can:

- Hold transactions open too long.
- Hold excessive row locks or undo records.
- Consume large temporary storage and application memory.
- Spike response times and degrade concurrent workloads.

Batches that are too small inflate round-trips and coordination overhead. Start with a moderate size, measure duration, rows examined, lock waits, CPU, and I/O, and tune from there. No single batch size fits every system.

## 8. Control Broad UPDATE and DELETE Statements

An UPDATE or DELETE without WHERE affects the entire table:

~~~sql
UPDATE sales_orders
SET status_code = 9;

DELETE FROM sales_orders;
~~~

If the goal is modifying only a subset, the predicate must define the exact scope. For large jobs, break work into batches along a stable key:

~~~sql
UPDATE sales_orders
SET status_code = 9
WHERE order_id > 100000
  AND order_id <= 101000
  AND status_code = 1;
~~~

After verifying the first batch, advance through subsequent key ranges. Alternatively, pick the next batch using ORDER BY and LIMIT in a single-table statement:

~~~sql
UPDATE sales_orders
SET status_code = 9
WHERE status_code = 1
ORDER BY order_id
LIMIT 1000;
~~~

Single-table UPDATE/DELETE statements support ORDER BY and LIMIT in MySQL. Verify the plan and affected rows before looping. Multi-table UPDATE/DELETE syntax and restrictions differ; never assume LIMIT behaves identically to single-table statements.

In the illustrative schema, no index begins with status_code. If status_code = 1 is rare, MySQL may have to scan many rows in primary key order before finding 1,000 rows to update. LIMIT caps modified rows, not rows scanned. Consider an appropriate index or explicit bounded order_id ranges.

### 8.1. Run Each Batch in a Short Transaction

In InnoDB, run each batch in its own transaction:

~~~sql
START TRANSACTION;

UPDATE sales_orders
SET status_code = 9
WHERE order_id > 100000
  AND order_id <= 101000
  AND status_code = 1;

COMMIT;
~~~

Short transactions release locks and undo history much sooner than one giant transaction. In exchange, if campaign-level atomicity is required, design job-level progress tracking, retries, and compensating rollback.

### 8.2. Check Scope Before Writing

Before UPDATE/DELETE, run a SELECT with the same predicate to estimate target rows:

~~~sql
SELECT COUNT(*)
FROM sales_orders
WHERE order_id > 100000
  AND order_id <= 101000
  AND status_code = 1;
~~~

For large operations, COUNT(*) also carries cost; avoid running full-table COUNT just to validate every small batch. Use key-bounded SELECT with LIMIT or track affected rows returned by DML.

To inspect the execution plan for DML, use EXPLAIN UPDATE or EXPLAIN DELETE on supported versions. EXPLAIN ANALYZE is not the tool for measuring UPDATE/DELETE in this workflow; measure timing and affected row counts per batch in a suitable test environment.

## 9. COUNT(*) and UI Pagination

A common pattern runs two queries per page:

~~~sql
SELECT COUNT(*)
FROM sales_orders
WHERE tenant_id = 42;

SELECT order_id, created_at, total
FROM sales_orders
WHERE tenant_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

An exact COUNT(*) can read vast numbers of index entries, especially when the tenant filter matches many rows. If the UI only needs to know whether a next page exists, fetch page_size + 1:

~~~sql
SELECT order_id, created_at, total
FROM sales_orders
WHERE tenant_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 51;
~~~

If 51 rows come back, display the first 50 and set has_next = true. If at most 50 rows return, there is no next page under that query snapshot.

Do not substitute an estimate for exact COUNT if business rules require exact numbers. For dashboards, consider summary tables or scheduled cached counts, clearly displaying data freshness timestamps.

## 10. Avoid Building Oversized Intermediate Sets in JOINs

A query with a trailing LIMIT can still materialize many intermediate rows before returning results:

~~~sql
SELECT
    e.employee_id,
    e.employee_name,
    so.order_id,
    so.total
FROM employees AS e
JOIN sales_orders AS so
  ON so.employee_id = e.employee_id
ORDER BY so.total DESC
LIMIT 100;
~~~

If an employee has many orders, the join generates many row pairs. If total order lacks a matching index, MySQL must process and sort a huge result set before returning 100 rows.

When the business wants the Top-N orders, querying the orders table directly is cleaner:

~~~sql
SELECT order_id, employee_id, total
FROM sales_orders
ORDER BY total DESC, order_id DESC
LIMIT 100;
~~~

If employee names are needed, join after isolating the 100 orders:

~~~sql
SELECT
    top_orders.order_id,
    top_orders.total,
    e.employee_name
FROM (
    SELECT order_id, employee_id, total
    FROM sales_orders
    ORDER BY total DESC, order_id DESC
    LIMIT 100
) AS top_orders
JOIN employees AS e
  ON e.employee_id = top_orders.employee_id
ORDER BY top_orders.total DESC, top_orders.order_id DESC;
~~~

The derived table caps the set to 100 orders before joining employee names. Keep ORDER BY on the outer query too because inner derived-table ordering does not automatically guarantee outer result order.

You cannot always push LIMIT into one branch before a JOIN while preserving semantics. Do so only when the bounded branch represents the exact Top-N set required by the business.

### 10.1. Verify JOIN Predicates

A JOIN missing a condition or using an unselective condition can trigger a Cartesian product or unexpected row multiplication:

~~~sql
SELECT e.employee_id, so.order_id
FROM employees AS e
JOIN sales_orders AS so;
~~~

Without ON, the result is a Cartesian product of both tables. Before running multi-table queries, verify:

- Every JOIN edge has proper key-matching conditions.
- One-to-many cardinalities are understood.
- Filters are placed on the right tables.
- Indexes support join keys and filter predicates.
- Estimated and actual row counts do not spike unexpectedly at join iterators.

## 11. Control Large IN Lists and UNIONs

Prepared statement pattern with an IN list (actual placeholder count matches key count; abbreviated below):

~~~sql
SELECT order_id, total
FROM sales_orders
WHERE order_id IN (?, ?, ?);
~~~

When the list grows to thousands or tens of thousands of keys, SQL length and placeholder count balloon, raising parse/optimize overhead and lookup volume. When keys originate from another table or job, consider loading them into an indexed temporary/staging table and joining.

Temporary table example:

~~~sql
CREATE TEMPORARY TABLE requested_order_ids (
    order_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;

SELECT so.order_id, so.total
FROM requested_order_ids AS requested
JOIN sales_orders AS so
  ON so.order_id = requested.order_id;
~~~

Temporary tables fit when a large key list is reused across multiple queries in the same session. With only a few dozen keys, an IN list is simpler and faster; measure instead of applying blindly.

UNION or UNION DISTINCT across large branches can generate heavy intermediate data and deduplication overhead. Ensure each branch has its own bounding predicates, matching indexes, and confirm whether deduplication is genuinely needed.

## 12. Large Exports: Stream or Run as Background Jobs

Never let a synchronous web request load millions of rows, hold the full dataset in RAM, and then return a file.

Options:

- Run exports as background jobs and report status/progress to users.
- Read in batches by primary key or stable cursor.
- Select only columns needed in the exported file.
- Write each batch incrementally to disk or object storage instead of buffering everything in memory.
- Rate-limit reads so they do not starve transactional workloads.
- Persist checkpoints to resume after failures.

Some drivers offer streaming modes or cursor/fetch sizes, though implementations vary. Certain drivers buffer the entire result set on the client despite fetch-size APIs; verify driver docs and measure actual memory usage.

### 12.1. Consistency of Batched Exports

If each batch runs in its own transaction, data can mutate between batches. This may be fine for near-current reports, though it does not guarantee a single point-in-time snapshot.

Holding one consistent snapshot across an entire export creates a long-lived transaction, pinning an old read view and slowing InnoDB undo history purging. Weigh:

- Does the export require a strict point-in-time snapshot or tolerate concurrent updates?
- Can you anchor a high-water mark or version?
- Can the export run against a replica or analytical copy?
- Can transactions be chunked while still meeting business needs?

Using a replica offloads read traffic from the primary, yet does not make unbounded queries cheap. Replicas still read data and can suffer increased replication lag if an export saturates resources.

## 13. Timeouts for SELECT Statements

MySQL provides max_execution_time (in milliseconds) to bound execution duration for eligible read-only SELECT statements in a session.

Example setting a 2-second session limit:

~~~sql
SET SESSION max_execution_time = 2000;
~~~

Or use an optimizer hint for a single query:

~~~sql
SELECT /*+ MAX_EXECUTION_TIME(2000) */
    order_id, created_at, total
FROM sales_orders
WHERE tenant_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 100;
~~~

A value of 2000 equals 2,000 milliseconds. A value of 0 means no timeout imposed by this variable.

### 13.1. Timeouts Are a Guardrail, Not Query Optimization

max_execution_time helps stop runaway read-only SELECTs from consuming resources indefinitely. However, it cannot fix:

- Missing filter predicates.
- Unsuitable indexes.
- Large sorts.
- Joins generating too many rows.
- Oversized result payloads sent to clients.

Timeouts cap duration; they do not ensure the query read little data. A poorly designed query may simply fail repeatedly with timeouts.

### 13.2. Scope of Applicability

max_execution_time applies to read-only SELECT statements per MySQL version rules. Do not treat it as a general timeout for UPDATE, DELETE, INSERT, or entire transactions. Broad DML requires scoped bounds, chunked batches, lock monitoring, and dedicated transaction management.

Client, connection pool, and proxy timeouts can also abort requests at other layers. Determine which timeout fired using error logs, application logs, and Performance Schema; never assume a client timeout immediately halts server execution.

## 14. Reading EXPLAIN to Catch Overly Broad Scans

EXPLAIN shows how the optimizer intends to access tables:

~~~sql
EXPLAIN
SELECT order_id, created_at, total
FROM sales_orders
WHERE tenant_id = 42
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
ORDER BY created_at DESC, order_id DESC
LIMIT 100;
~~~

Indicators to inspect:

- type: ALL may indicate a full table scan; range/ref usually indicates more targeted access.
- possible_keys and key: candidate indexes and the chosen index.
- rows: estimated rows the optimizer expects to examine.
- filtered: estimated percentage remaining after filter predicates.
- Extra: Using where, Using filesort, Using temporary, or Using index.

Never judge from a single metric alone. ALL on a small table can be optimal; range across millions of entries can still be expensive.

### 14.1. EXPLAIN ANALYZE

On MySQL 8.0.18 and later:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, created_at, total
FROM sales_orders
WHERE tenant_id = 42
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
ORDER BY created_at DESC, order_id DESC
LIMIT 100;
~~~

EXPLAIN ANALYZE executes the SELECT and reports actual rows, loops, and iterator timings. This verifies whether LIMIT actually triggers early exit or whether the query still reads many rows before returning results.

Run EXPLAIN ANALYZE only on queries with assessed cost in a suitable environment; it is a real execution.

### 14.2. Statistics Can Cause Misestimation

If EXPLAIN predicts row counts far from reality, check table statistics and data distribution. You can refresh statistics:

~~~sql
ANALYZE TABLE sales_orders;
~~~

Then compare plans and actual measurements. ANALYZE TABLE updates statistics; it does not guarantee a specific index will be chosen.

## 15. Monitoring Queries Reading Excessive Data

### 15.1. Slow Query Log

The slow query log records queries exceeding time thresholds alongside execution metrics. Useful fields:

- Query_time: query duration.
- Lock_time: recorded lock wait time.
- Rows_sent: rows shipped to client.
- Rows_examined: rows inspected by server.

Inspect settings:

~~~sql
SHOW VARIABLES LIKE 'slow_query_log';
SHOW VARIABLES LIKE 'long_query_time';
SHOW VARIABLES LIKE 'min_examined_row_limit';
~~~

Set logging thresholds based on workload and disk capacity. Filtering by duration alone can miss a very fast query that examines millions of rows; min_examined_row_limit helps catch heavy-read queries even with low runtime.

Slow query logs may contain SQL text and sensitive literal values. Enforce appropriate access controls, storage security, and retention.

### 15.2. Performance Schema by Digest

Performance Schema aggregates statements by digest, surfacing query patterns with high total rows examined:

~~~sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    ROUND(
        SUM_ROWS_EXAMINED / NULLIF(SUM_ROWS_SENT, 0),
        2
    ) AS examined_per_sent,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 2) AS total_seconds
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST_TEXT IS NOT NULL
ORDER BY SUM_ROWS_EXAMINED DESC
LIMIT 20;
~~~

Columns indicate:

- COUNT_STAR: number of recorded executions.
- SUM_ROWS_EXAMINED: total rows examined.
- SUM_ROWS_SENT: total rows sent to clients.
- examined_per_sent: ratio of rows examined to rows returned when denominator is non-zero.
- total_seconds: total wait time converted from picoseconds to seconds.

A high examined_per_sent ratio is a signal to investigate, not standalone proof. For aggregate statements, one output row can legitimately summarize millions of source rows. For queries returning zero rows, the ratio is NULL.

Performance Schema can be constrained by instrumentation configuration and history/summary table sizes. Appropriate privileges are needed to query these tables.

### 15.3. Job-Level Monitoring

For exports or batch jobs, record at the application tier:

- Job name and tenant/time scope.
- Start/end checkpoints of each batch.
- Rows read, rows processed, and rows written.
- Per-batch duration and total job duration.
- Retries, errors, timeouts, and reruns.
- Application memory usage and file write throughput.

These metrics help distinguish slow MySQL queries from slow serialization, network transfer, or file I/O.

## 16. Application-Layer Guardrails

A search API should enforce explicit boundary contracts:

| Guardrail | Example |
|---|---|
| Default page size | 25 rows |
| Maximum page size | 100 rows |
| Maximum date range | 31 days for synchronous requests |
| Mandatory filter | tenant_id or authorization scope |
| Timeout | Execution limit for read SELECTs |
| Large exports | Offload to background jobs |
| Concurrent load | Per-user/tenant rate limiting |

These figures are examples. Choose limits based on target latency, hardware, row width, and concurrency.

### 16.1. Never Let Empty Parameters Drop Filters

A common bug builds dynamic SQL by appending WHERE clauses only when user filters are supplied. If the user supplies nothing, the app accidentally runs:

~~~sql
SELECT order_id, created_at, total
FROM sales_orders;
~~~

Instead, enforce mandatory filters before building the query. If full search is a legitimate feature, require explicit scope selection or offload to a background export.

### 16.2. Enforce Limits on the Server, Never Trust Clients

Clients can send page_size = 1000000 even if the UI displays only 25. The server must enforce maximums, verify authorization, and validate date windows. Never rely on hidden buttons or disabled browser controls.

Use prepared statements for parameter values; dynamic column names and sort directions must map through a strict server-side allow-list instead of concatenating user strings into SQL.

## 17. When Is a Full Scan Reasonable?

Not every full table scan must be eliminated. A full scan can be the right choice when:

- The table is small.
- Analytical queries require most of the table.
- Sequential reads are cheaper than many random secondary-index lookups.
- An export job needs all rows and is already chunked into batches.
- The optimizer determines available indexes are unselective.

When the business genuinely requires reading all data, keep execution controlled:

- Run as a background job.
- Use batching and checkpoints.
- Limit concurrent jobs.
- Monitor I/O, CPU, buffer pool, and replication lag.
- Prefer replicas or analytical stores when appropriate.
- Persist aggregated summaries to avoid repeatedly scanning for the same report.

The goal is keeping data read proportional to useful work without unexpectedly degrading concurrent workloads.

## 18. Common Misconceptions

**"Having LIMIT means the query is bounded."** No. LIMIT caps returned rows; MySQL may still read and sort a huge dataset before returning results.

**"Returning 20 rows means reading 20 rows."** No. Compare rows examined against rows sent and inspect the execution plan.

**"Having a WHERE clause is enough."** No. The predicate can be overly broad, unselective, or unable to use an index.

**"SELECT * does not matter when LIMIT is small."** No. Large BLOB/JSON columns increase I/O, network traffic, and memory even for few rows.

**"Single-column ORDER BY is always deterministic."** No. When duplicate values exist, append a unique key as a tie-breaker.

**"Keyset pagination automatically guarantees a consistent snapshot."** No. It cuts pagination overhead, yet data can still mutate between requests.

**"Batching is just adding LIMIT."** No. You need stable checkpoints, high-water marks when appropriate, idempotent retries, and post-commit checkpoint persistence.

**"One huge transaction is safer than many small transactions."** No. Long transactions hold locks and undo history; short transactions require proper progress tracking and retry logic.

**"COUNT(*) is always cheap because it returns one number."** No. MySQL may have to read vast numbers of index entries for an exact count.

**"EXISTS is always better than JOIN."** No. Compare results and execution plans; the optimizer can rewrite EXISTS into a semijoin.

**"max_execution_time solves unbounded queries."** No. It is a time guardrail for read-only SELECTs; it never replaces proper filters, indexes, and batching.

**"Replicas can handle every heavy query for free."** No. Replicas still consume CPU and I/O and can fall behind in replication lag.

## 19. Workflow for Controlling Heavy-Read Queries

1. Clarify purpose: API, list view, report, export, migration, or broad DML.
2. Define mandatory business bounds: tenant, time window, status, or key range.
3. Project only needed columns; avoid sending large unused payloads.
4. Write index-friendly WHERE predicates and half-open time ranges.
5. Use deterministic ORDER BY and LIMIT aligned with page size.
6. For large datasets, use keyset pagination or primary-key batch scans.
7. For broad DML, split into batches with short transactions, checkpoints, and safe retries.
8. Configure appropriate SELECT timeouts and concurrency caps.
9. Run EXPLAIN; inspect rows, access methods, sorts, and temporary tables.
10. Run EXPLAIN ANALYZE when safe to measure actual rows, loops, and timing.
11. Monitor slow query logs, Performance Schema, and rows examined/rows sent.
12. Benchmark with representative data and load before deploying.

## 20. Pre-Release Checklist

- [ ] Query has mandatory business scope filters.
- [ ] Time ranges or data bounds are reasonably capped.
- [ ] Indexes support filter predicates, JOINs, and sort orders.
- [ ] Maximum LIMIT is enforced on the server.
- [ ] ORDER BY includes a unique tie-breaker.
- [ ] Large OFFSET is avoided for deep traversal when keyset is viable.
- [ ] Only genuinely required columns are SELECTed.
- [ ] Exact COUNT runs only when business logic requires it.
- [ ] Large exports run in batches or background jobs.
- [ ] Batches use checkpoints, high-water marks where needed, and safe retries.
- [ ] Transactions do not hold locks or undo history unexpectedly long.
- [ ] Timeouts and concurrency caps are configured properly.
- [ ] EXPLAIN/EXPLAIN ANALYZE verified on representative data.
- [ ] Rows examined, rows sent, and execution duration are monitored.
- [ ] Behavior on client disconnect or mid-batch failure is defined.

## Conclusion

Controlling unbounded queries takes more than slapping on LIMIT. You must bound business scope, rows read, result payload size, execution time, and concurrent load together.

For interactive requests, use indexed filters, narrow projections, deterministic sorting, and capped page sizes. For large exports or migrations, use keyset/key-range batching, checkpoints, short transactions, and background jobs. Finally, verify with EXPLAIN, EXPLAIN ANALYZE, slow query logs, and Performance Schema to see how much data MySQL actually reads compared to what the application receives.
