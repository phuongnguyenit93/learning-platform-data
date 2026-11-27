# Statement Digests and Grouping Structurally Identical Queries

In the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, privilege management, backups, and handling relational database operational issues. When an application sends thousands of SQL statements per minute, inspecting individual statements does not reveal which query groups are consuming resources. MySQL Performance Schema can normalize statement structures into digests to group queries with the same shape, then aggregate execution counts, durations, rows examined, rows sent, errors, warnings, and other execution metrics.

Statement digests help answer operational questions:

- Which SQL statement group runs most frequently?
- Which group accounts for the largest share of total database time?
- Which group is slow on average per execution?
- Which group examines many rows while returning few?
- Which group frequently creates disk temporary tables, sorts, or full scans?
- After a deployment, which query group increased in call count or latency?

Digests are an aggregation and investigation-prioritization tool. They do not replace execution plans, query traces, application logs, or analyzing individual parameter values. Statements with the exact same structure can still exhibit vastly different data selectivity, plans, and execution times.

## 1. Why Group Queries by Structure?

Suppose an application executes these statements:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 101;

SELECT order_id, total_amount
FROM orders
WHERE customer_id = 202;

SELECT order_id, total_amount
FROM orders
WHERE customer_id = 303;
~~~

The three statements differ in the value of customer_id yet share the exact same structure. During a performance investigation, you typically need to know how many times this query group ran overall, how much total time it consumed, and how many rows it examined.

Another example:

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 501;

UPDATE inventory
SET available_quantity = available_quantity - 2
WHERE product_id = 502;
~~~

Both UPDATE statements share the same shape. Grouping them by digest helps identify inventory-update workloads even though each product_id varies.

Looking only at the slow query log tends to focus on individual runs that exceeded a time threshold. Digests add an aggregated view: a query taking only a few milliseconds that runs millions of times can consume far more resources than an infrequent slow query.

## 2. What Is a Statement Digest?

A statement digest is a normalized representation of an SQL statement's structure. MySQL parses the statement, replaces common literals with `?` placeholders, normalizes certain whitespace and formatting differences, and generates a digest to identify the group.

Example:

| SQL Sent to Server | Illustrative Digest Form |
|---|---|
| SELECT * FROM orders WHERE order_id = 10 | SELECT * FROM orders WHERE order_id = ? |
| SELECT * FROM orders WHERE order_id = 25 | SELECT * FROM orders WHERE order_id = ? |
| SELECT * FROM orders WHERE order_id = 900 | SELECT * FROM orders WHERE order_id = ? |
| SELECT * FROM orders WHERE customer_id = 10 | SELECT * FROM orders WHERE customer_id = ? |

The first three statements belong to the same structural group; the last belongs to a different group because the filter predicate targets a different column.

### 2.1. DIGEST and DIGEST_TEXT

In Performance Schema:

- **DIGEST** is the digest identifier computed from the statement structure.
- **DIGEST_TEXT** is the normalized digest text, convenient for reading and analysis.
- **SCHEMA_NAME** indicates the default schema associated with the statement when recorded.

The summary table groups by schema and digest. The same SQL structure executed under two different default schemas can appear as two separate rows.

### 2.2. What Gets Normalized

Typically, literals such as numbers, strings, and datetime values are replaced by placeholders. Non-semantic differences such as whitespace and comments generally do not create separate groups. Table names, column names, operators, JOIN structures, predicates, and ordering of SQL clauses still affect the digest.

Therefore:

- Changing customer_id from 101 to 202 usually stays in the same digest.
- Changing customer_id to order_id produces a different structure.
- Adding a JOIN or WHERE predicate can produce a different digest.
- Two SQL statements yielding the same business result but written with different structures can map to two different digests.

Do not treat digests as proof that two statements are business-equivalent. Digests only serve structural grouping according to MySQL's parser rules.

### 2.3. Digests Do Not Retain Individual Parameter Values

Because literals are normalized, DIGEST_TEXT does not tell you which specific customer_id or date a query ran with. This is a useful property for reducing group counts and avoiding directly exposing literal values.

If you need to investigate a specific parameter value, combine application logs, tracing, controlled slow query logging, or appropriate audit tools. Do not enable full SQL logging containing sensitive data merely to replace digests.

### 2.4. Same Digest Does Not Mean Same Performance

A single digest can aggregate runs with vastly different parameter values:

- One customer has 5 orders, another has millions of orders.
- One filter date range covers a few dozen rows, another covers tens of millions of rows.
- One value is highly common in the distribution, another is very rare.
- One run uses an efficient plan, another is affected by statistics or data conditions.

Thus, digests show which group warrants attention; inspect representative parameters and execution plans before changing SQL or indexes.

## 3. Data Source: events_statements_summary_by_digest

MySQL Performance Schema provides the table:

performance_schema.events_statements_summary_by_digest

This table stores aggregated statistics by digest and schema. Each row represents a group of instrumented and aggregated statements. Metrics are cumulative values for the current statistics lifecycle, usually counted since server startup or the most recent summary table reset.

Commonly used columns:

| Column | Meaning |
|---|---|
| SCHEMA_NAME | Default schema of the statement |
| DIGEST | Group identifier hash |
| DIGEST_TEXT | Normalized SQL statement text |
| COUNT_STAR | Number of recorded executions |
| SUM_TIMER_WAIT | Total execution time |
| AVG_TIMER_WAIT | Average time per execution |
| MIN_TIMER_WAIT | Shortest execution time |
| MAX_TIMER_WAIT | Longest execution time |
| SUM_LOCK_TIME | Total measured lock wait time |
| SUM_ERRORS | Number of errors |
| SUM_WARNINGS | Number of warnings |
| SUM_ROWS_AFFECTED | Total rows affected |
| SUM_ROWS_SENT | Total rows sent to client |
| SUM_ROWS_EXAMINED | Total rows read/examined |
| SUM_CREATED_TMP_TABLES | Total temporary tables created |
| SUM_CREATED_TMP_DISK_TABLES | Total temporary tables created on disk |
| SUM_SELECT_SCAN | Number of select full table scans |
| SUM_NO_INDEX_USED | Number of executions without an index |
| SUM_NO_GOOD_INDEX_USED | Number of times the optimizer found no suitable index |
| FIRST_SEEN | Timestamp when digest was first recorded |
| LAST_SEEN | Timestamp when digest was most recently recorded |

Column lists may vary by MySQL version. Inspect the table structure on your running version before putting monitoring queries into long-term production use.

### 3.1. Is Performance Schema Enabled?

Check:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'performance_schema';
~~~

If Performance Schema was disabled at startup, it cannot be fully enabled with a single runtime UPDATE. Configure it at startup and restart following operational procedures.

### 3.2. Checking the statements_digest Consumer

~~~sql
SELECT NAME, ENABLED
FROM performance_schema.setup_consumers
WHERE NAME IN (
    'statements_digest',
    'events_statements_current',
    'events_statements_history',
    'events_statements_history_long'
);
~~~

The statements_digest consumer controls digest collection. On supported MySQL releases, this consumer is usually enabled by default; still verify the actual configuration.

If intentionally enabling digest collection with proper authorization:

~~~sql
UPDATE performance_schema.setup_consumers
SET ENABLED = 'YES'
WHERE NAME = 'statements_digest';
~~~

History consumers serve different purposes and are not required just to read digest summaries. Do not enable all consumers indiscriminately, as each additional collection adds memory and processing overhead.

### 3.3. Checking Statement Instruments

~~~sql
SELECT NAME, ENABLED, TIMED
FROM performance_schema.setup_instruments
WHERE NAME LIKE 'statement/%'
ORDER BY NAME;
~~~

Instruments determine which statement types are captured and whether they are timed. If statement instruments are disabled or TIMED = NO, data or timing may be incomplete.

Enable only the instruments needed per monitoring policy:

~~~sql
UPDATE performance_schema.setup_instruments
SET ENABLED = 'YES',
    TIMED = 'YES'
WHERE NAME LIKE 'statement/%';
~~~

The example above enables a broad group of statement instruments. Only do this after evaluating overhead, privileges, and environment requirements. On production systems, prefer controlled configuration and monitor overhead after enabling.

## 4. Basic Digest Queries

### 4.1. Viewing Query Groups with the Largest Total Time

~~~sql
SELECT
    SCHEMA_NAME,
    DIGEST,
    DIGEST_TEXT,
    COUNT_STAR AS exec_count,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_latency_seconds,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_latency_seconds,
    SUM_ROWS_EXAMINED AS rows_examined,
    SUM_ROWS_SENT AS rows_sent,
    SUM_ERRORS AS errors,
    SUM_WARNINGS AS warnings
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

Performance Schema timer columns are expressed in picoseconds. Divide by 10^12 to convert to seconds. High total time indicates the query group consumes a large share of database time over the current statistics window; it does not mean every individual execution is slow.

### 4.2. Groups with the Highest Execution Count

~~~sql
SELECT
    SCHEMA_NAME,
    DIGEST_TEXT,
    COUNT_STAR AS exec_count,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_latency_seconds,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_latency_seconds
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY COUNT_STAR DESC
LIMIT 20;
~~~

A very fast query executed continuously can still top this list. Check whether the application calls the same SQL overly frequently, and whether batching, application-layer caching, or reducing round trips is feasible.

### 4.3. Groups with High Average Time

~~~sql
SELECT
    SCHEMA_NAME,
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_latency_seconds,
    ROUND(MAX_TIMER_WAIT / 1000000000000, 3) AS max_latency_seconds,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
  AND COUNT_STAR > 0
ORDER BY AVG_TIMER_WAIT DESC
LIMIT 20;
~~~

AVG_TIMER_WAIT helps find groups with high per-execution cost. Always read it alongside COUNT_STAR because a digest run once may be lower priority than a group run hundreds of thousands of times.

### 4.4. Groups Examining Many Rows While Returning Few

~~~sql
SELECT
    SCHEMA_NAME,
    DIGEST_TEXT,
    COUNT_STAR,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    ROUND(
        SUM_ROWS_EXAMINED / NULLIF(SUM_ROWS_SENT, 0),
        1
    ) AS examined_per_row_sent,
    SUM_NO_INDEX_USED,
    SUM_NO_GOOD_INDEX_USED
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY SUM_ROWS_EXAMINED DESC
LIMIT 20;
~~~

A high examined/sent ratio can suggest queries reading excessive rows. However, this ratio alone does not prove a query is wrong: aggregations, EXISTS checks, zero-row queries, or queries processing intermediate rows can naturally show skewed ratios. Inspect the SQL and plan.

### 4.5. Groups Creating Disk Temporary Tables

~~~sql
SELECT
    SCHEMA_NAME,
    DIGEST_TEXT,
    COUNT_STAR,
    SUM_CREATED_TMP_TABLES,
    SUM_CREATED_TMP_DISK_TABLES,
    SUM_SORT_ROWS,
    SUM_SORT_MERGE_PASSES
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY SUM_CREATED_TMP_DISK_TABLES DESC
LIMIT 20;
~~~

Disk temporary tables can arise from GROUP BY, ORDER BY, DISTINCT, UNION, or other operations. Not every temporary table is an error; compare data size, frequency, and latency. If counts are high, inspect execution plans, expressions, indexes, and temporary memory limits.

### 4.6. Groups with Errors or Warnings

~~~sql
SELECT
    SCHEMA_NAME,
    DIGEST_TEXT,
    COUNT_STAR,
    SUM_ERRORS,
    SUM_WARNINGS,
    FIRST_SEEN,
    LAST_SEEN
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
  AND (SUM_ERRORS > 0 OR SUM_WARNINGS > 0)
ORDER BY SUM_ERRORS DESC, SUM_WARNINGS DESC
LIMIT 20;
~~~

The digest summary shows which groups encountered errors or warnings, though it does not store full detailed messages for each run. Use error logs, application logs, or appropriate statement history to find specific root causes.

## 5. Choosing Ranking Criteria Aligned with Your Goal

No single top-10 list fits every investigation. Choose ranking criteria based on the question:

| Goal | Priority Metric | How to Read |
|---|---|---|
| Reduce total DB time | SUM_TIMER_WAIT | Groups consuming the largest total time |
| Reduce call frequency | COUNT_STAR | Frequently executed groups |
| Find slow queries on average | AVG_TIMER_WAIT | Average cost per execution |
| Find extreme slow runs | MAX_TIMER_WAIT | Maximum value in the statistics interval |
| Reduce excessive row reads | SUM_ROWS_EXAMINED, SUM_ROWS_SENT | Compare rows examined vs. rows sent |
| Find notable full scans | SUM_NO_INDEX_USED, SUM_SELECT_SCAN | Inspect SQL and plan |
| Reduce disk temporary tables | SUM_CREATED_TMP_DISK_TABLES | Investigate sorting, grouping, and data sizes |
| Find application errors | SUM_ERRORS, SUM_WARNINGS | Cross-check detailed logs |

### 5.1. Total Time and Average Time Differ

Suppose:

| Digest | Executions | Average | Total Time |
|---|---:|---:|---:|
| A | 100,000 | 2 ms | 200 s |
| B | 20 | 2 s | 40 s |
| C | 10,000 | 5 ms | 50 s |

Digest A consumes the most total time. Digest B is slowest per execution. Depending on your goal, you might optimize A to reduce aggregate load or B to improve user experience on a critical operation.

### 5.2. Do Not Look Only at COUNT_STAR

A high-count group might just be a tiny lookup query. A low-count group might be a massive report, migration, or administrative job. Combine frequency, latency, rows examined, lock time, errors, and business role before prioritizing.

### 5.3. Do Not Look Only at MAX_TIMER_WAIT

MAX_TIMER_WAIT only reports the single slowest execution recorded during the current statistics period. It does not reveal latency distribution, percentiles, or root cause. When per-request distributions are required, use tracing or an appropriate metrics system.

## 6. Using sys.statement_analysis

MySQL provides the sys schema with more readable views over Performance Schema. A commonly used view is sys.statement_analysis.

~~~sql
SELECT
    query,
    db,
    full_scan,
    exec_count,
    err_count,
    warn_count,
    total_latency,
    avg_latency,
    rows_sent,
    rows_examined,
    tmp_tables,
    tmp_disk_tables
FROM sys.statement_analysis
LIMIT 20;
~~~

This view presents normalized statements alongside aggregated metrics in an operator-friendly format. Columns may vary depending on the sys schema version bundled with MySQL. Check the view definition if building dashboards that depend on specific column names.

### 6.1. When to Use sys vs. Performance Schema?

- Use sys.statement_analysis for quick top-statement inspection with readable column names.
- Use performance_schema.events_statements_summary_by_digest when you need exact control over calculations, timers, digests, and summary columns.
- Use events_statements_history or events_statements_history_long to inspect a few recent executions if those consumers are enabled and history capacity suffices.
- Use the slow query log to retain statements exceeding thresholds per logging policy.
- Use application tracing to link queries to endpoints, request IDs, tenants, or users.

Digest summaries are not immutable historical logs. They hold aggregated statistics rather than a full record of every execution.

## 7. Digest Limits and Truncated Content

Performance Schema does not retain an unlimited number of digest groups. Row capacity is controlled by the startup variable performance_schema_digests_size.

Check:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'performance_schema_digests_size';
SHOW GLOBAL VARIABLES LIKE 'max_digest_length';
SHOW GLOBAL VARIABLES LIKE 'performance_schema_max_digest_length';
~~~

- performance_schema_digests_size controls how many digest entries can be stored in the summary table.
- max_digest_length limits the statement length used during digest generation.
- performance_schema_max_digest_length controls the maximum length of digest text stored in Performance Schema.

The scope and mutability of these variables depend on version; they typically must be set at startup. Check the documentation for your exact MySQL release before tuning.

### 7.1. When the Digest Table Runs Out of Space

When the number of distinct statement structures exceeds storage capacity, MySQL may aggregate unmatched statements into a row where DIGEST IS NULL. That row signals that digest capacity may be insufficient; its content does not represent a single query shape to optimize.

Check:

~~~sql
SELECT
    COUNT_STAR,
    SUM_TIMER_WAIT,
    SUM_ERRORS,
    SUM_WARNINGS
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NULL;
~~~

If this row shows significant activity, consider increasing performance_schema_digests_size at startup after evaluating memory. Also check whether the application generates excessive dynamic SQL with varying table/column names or structures.

### 7.2. Truncated Digest Text

Very long statements may be truncated during digest generation or when storing digest text. When reading DIGEST_TEXT, verify whether the tail was truncated and whether enough structure remains to distinguish groups.

Do not mechanically raise all digest limits to huge values. Both entry counts and text length consume Performance Schema memory. Set limits sufficient for your workload and verify after restart.

## 8. Monitoring Over Time Intervals

Counters in the digest summary are cumulative. Looking at them once shows totals since server startup or the last reset, not the rate over the last 5 minutes.

### 8.1. Taking Two Snapshots

Record these columns:

~~~sql
SELECT
    SCHEMA_NAME,
    DIGEST,
    DIGEST_TEXT,
    COUNT_STAR,
    SUM_TIMER_WAIT,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    SUM_ERRORS,
    LAST_SEEN
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL;
~~~

Take snapshot A, wait through an interval with representative workload, then take snapshot B. Match rows by key (SCHEMA_NAME, DIGEST) to compute deltas:

- Delta COUNT_STAR: number of executions within the window.
- Delta SUM_TIMER_WAIT: total time within the window.
- Delta SUM_ROWS_EXAMINED: additional rows examined.
- Delta SUM_ERRORS: new errors.

If time-series dashboards are needed, export snapshots to an external metrics system or monitoring store. Do not treat Performance Schema digest summaries as a time-series database.

### 8.2. Computing Average Latency Within a Window

With two snapshots:

~~~text
delta_count = count_B - count_A
delta_timer = timer_B - timer_A

avg_latency_window =
    delta_timer / delta_count
~~~

Compute only when delta_count > 0. Timers remain in picoseconds when read directly from Performance Schema. Convert to seconds by dividing by 10^12.

### 8.3. Purposefully Resetting Summaries

In a lab environment or an approved measurement window, you can reset digest summaries:

~~~sql
TRUNCATE TABLE performance_schema.events_statements_summary_by_digest;
~~~

This resets aggregated statistics in the Performance Schema table; it does not delete application business data. However, it clears the prior statistical baseline across the whole server. In production, do not reset casually; save a snapshot beforehand and coordinate with your monitoring system.

### 8.4. Resetting Does Not Solve Digest Capacity Limits

If distinct digests continuously exceed performance_schema_digests_size, resetting may free entries briefly, but the overflow will return. Inspect dynamic SQL, schema count, digest sizing, and true capacity needs.

## 9. Combining Digests with Execution Plans

Digests indicate which query groups deserve investigation; execution plans help uncover data access root causes.

Workflow:

1. Pick a digest with notable total latency, average latency, or rows examined.
2. Read DIGEST_TEXT to identify tables, predicates, JOINs, GROUP BY, and ORDER BY.
3. Obtain representative parameter values from logs or the application.
4. Run EXPLAIN with a concrete SQL statement.
5. Where appropriate, use EXPLAIN ANALYZE in a safe environment to inspect actual rows, loops, and iterator timings.
6. Compare estimated versus actual rows.
7. Check indexes, statistics, cardinality, join order, temporary tables, and sorts.
8. After making changes, monitor digest deltas to confirm results.

Example digest:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = ?;
~~~

A query for a customer with few orders:

~~~sql
EXPLAIN
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 101;
~~~

A query for a customer with very many orders:

~~~sql
EXPLAIN
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 900;
~~~

Both executions belong to the same digest, yet the optimizer can react differently depending on data distribution and statistics. Evaluate across representative values rather than just one convenient value.

### 9.1. Using EXPLAIN ANALYZE Carefully

~~~sql
EXPLAIN ANALYZE
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 900;
~~~

EXPLAIN ANALYZE actually executes the query to measure real iterators. Do not run it carelessly on UPDATE/DELETE statements or very heavy reporting queries in production. Start in staging or with bounded-impact SELECT queries.

### 9.2. Checking Accompanying Indicators

If a digest has high SUM_NO_INDEX_USED or SUM_SELECT_SCAN, check:

- Are filter predicates sargable?
- Do filter columns have suitable indexes?
- Do expressions wrap columns in functions that prevent index usage?
- Are data types on both sides of comparisons compatible?
- Do JOINs have indexes on join keys?
- Are optimizer statistics fresh enough and representative of data distribution?

Do not add an index merely because a counter is non-zero. A full scan can be reasonable when a table is small or when a query requires most of the rows.

## 10. Dynamic SQL and Application Design

Digests help detect when an application generates excessive distinct SQL structures.

### 10.1. Using Placeholders for Values

Prepared statements separate SQL structure from parameter values:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = ?;
~~~

The application binds customer_id on each execution. This reduces SQL string concatenation, enables statement reuse at the client/driver layer, and typically yields cleaner digest groups for analysis.

### 10.2. Do Not Bind Identifiers Like Values

Table names, column names, or sort directions generally cannot be bound like value placeholders. If an application builds SQL by dynamically concatenating table names or arbitrary predicates, it can generate many distinct digests.

Use allowlists for identifiers and keep query structures stable whenever possible. Never concatenate raw user input directly into SQL.

### 10.3. Distinguishing Query Shapes from Business Endpoints

One endpoint can execute multiple digests; one digest can also be called from multiple endpoints. Digest summaries do not automatically store routes, tenants, user IDs, or request IDs. To connect SQL to business flows, add application-layer tracing or metrics while controlling labels to avoid excessive cardinality.

## 11. Security and Metric Access Privileges

Performance Schema exposes SQL structure, schemas, table/column names, and operational statistics. Even though literals are usually normalized, digest text can still reveal object names and business logic.

Principles:

- Grant only required SELECT privileges on Performance Schema or sys views to operations teams.
- Do not broadly grant UPDATE on setup_consumers/setup_instruments to application accounts.
- Reset summaries only with proper authorization and an approved measurement plan.
- Do not store snapshots containing sensitive data in uncontrolled shared locations.
- Avoid placing raw DIGEST_TEXT into high-cardinality metric labels.

Normal application accounts do not need privileges to read or alter Performance Schema configuration.

## 12. Common Mistakes When Reading Digests

| Mistake | Why It Misleads | Proper Approach |
|---|---|---|
| Ranking only by COUNT_STAR | Fast queries can run often while using few resources | Also inspect total and average latency |
| Ranking only by SUM_TIMER_WAIT | Rare slow groups can be missed if user latency is the goal | Combine avg, max, and frequency |
| Assuming same digest means same plan | Parameter values and data distributions can vary | Run EXPLAIN with representative parameters |
| Treating SUM_NO_INDEX_USED > 0 as a bug | Full scans can be optimal for small tables or reports | Inspect plan, cardinality, and row counts |
| Treating DIGEST_TEXT as original SQL | Literals are normalized and text may be truncated | Use logs or tracing to find actual queries |
| Treating summary as per-run history | Table stores aggregated numbers only | Enable controlled history or use tracing |
| Comparing total counters without deltas | Counters accumulate since startup/reset | Take snapshots and compute deltas |
| Resetting summaries repeatedly to clear dashboards | Loses baseline and affects the whole server | Save snapshots and reset only in approved windows |
| Ignoring the DIGEST IS NULL row | Can miss digest capacity exhaustion | Monitor NULL digest row and configure capacity |
| Enabling all statement instruments without assessing overhead | Broad collection has memory and CPU cost | Enable selectively and monitor afterward |

## 13. Hands-On Exercise: Finding Resource-Heavy SQL Groups

Perform this on MySQL 8.0 in a lab or staging database. Do not reset Performance Schema or broadly enable instruments on production just for exercises.

### 13.1. Checking Performance Schema

~~~sql
SHOW GLOBAL VARIABLES LIKE 'performance_schema';

SELECT NAME, ENABLED
FROM performance_schema.setup_consumers
WHERE NAME = 'statements_digest';
~~~

Confirm Performance Schema and the digest consumer are active. If the environment does not allow changes, perform only the read-only steps.

### 13.2. Creating a Lab Table

~~~sql
CREATE DATABASE IF NOT EXISTS observability_lab;
USE observability_lab;

CREATE TABLE lab_orders (
    order_id BIGINT NOT NULL PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    created_at DATETIME NOT NULL,
    KEY ix_lab_orders_customer (customer_id),
    KEY ix_lab_orders_status_date (status, created_at)
) ENGINE = InnoDB;
~~~

Load representative data:

~~~sql
INSERT INTO lab_orders (
    order_id,
    customer_id,
    status,
    total_amount,
    created_at
)
VALUES
    (1, 101, 'PAID', 120.00, '2026-01-01 10:00:00'),
    (2, 101, 'PENDING', 80.00, '2026-01-02 10:00:00'),
    (3, 202, 'PAID', 250.00, '2026-01-03 10:00:00'),
    (4, 303, 'CANCELLED', 40.00, '2026-01-04 10:00:00');
~~~

### 13.3. Running the Same Query Shape with Different Literals

~~~sql
SELECT order_id, total_amount
FROM lab_orders
WHERE customer_id = 101;

SELECT order_id, total_amount
FROM lab_orders
WHERE customer_id = 202;

SELECT order_id, total_amount
FROM lab_orders
WHERE customer_id = 303;
~~~

These statements share the same query shape. After running them, inspect digests:

~~~sql
SELECT
    SCHEMA_NAME,
    DIGEST,
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 6) AS total_seconds,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT
FROM performance_schema.events_statements_summary_by_digest
WHERE SCHEMA_NAME = 'observability_lab'
  AND DIGEST IS NOT NULL
ORDER BY COUNT_STAR DESC;
~~~

Observe whether the executions are grouped under a single digest with customer_id replaced by a placeholder. Exact results depend on active consumers and instruments.

### 13.4. Creating a Different Query Shape

~~~sql
SELECT order_id, total_amount
FROM lab_orders
WHERE status = 'PAID';
~~~

This query filters on the status column and therefore generates a different digest structure. Compare DIGEST and DIGEST_TEXT.

### 13.5. Comparing Two Ranking Methods

~~~sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 6) AS total_seconds,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_seconds
FROM performance_schema.events_statements_summary_by_digest
WHERE SCHEMA_NAME = 'observability_lab'
  AND DIGEST IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC;
~~~

Run again with ORDER BY COUNT_STAR DESC and ORDER BY AVG_TIMER_WAIT DESC. Explain why the priority order can differ.

### 13.6. Reading the Query Shape's Plan

~~~sql
EXPLAIN
SELECT order_id, total_amount
FROM lab_orders
WHERE customer_id = 101;
~~~

Observe the selected index. Then try a query without a direct index:

~~~sql
EXPLAIN
SELECT order_id, total_amount
FROM lab_orders
WHERE total_amount > 100;
~~~

Do not draw performance conclusions from a tiny table. The goal is linking digests to SQL structure and plans, not benchmarking throughput on a few lab rows.

### 13.7. Cleaning Up the Lab Database

~~~sql
DROP DATABASE observability_lab;
~~~

Only drop the lab database you created. Do not TRUNCATE digest summaries on a shared server just to clear exercise results.

## 14. Runbook for Investigating a High-Cost Digest

1. **Define the goal:** reduce total time, reduce per-call latency, reduce errors, or reduce read resource usage.
2. **Select the digest:** use COUNT_STAR, SUM_TIMER_WAIT, AVG_TIMER_WAIT, rows examined, and related counters.
3. **Establish scope:** check SCHEMA_NAME, FIRST_SEEN, LAST_SEEN, and server uptime/reset timing.
4. **Check capacity:** inspect the DIGEST IS NULL row and performance_schema_digests_size.
5. **Inspect structure:** analyze DIGEST_TEXT, tables, JOINs, predicates, and expressions.
6. **Find representative parameters:** use tracing or controlled logs to understand data selectivity.
7. **Inspect the execution plan:** EXPLAIN and, where safe, EXPLAIN ANALYZE.
8. **Identify root cause:** indexes, statistics, scans, sorts, temporary tables, locks, or call frequency.
9. **Propose changes:** adjust SQL, indexes, batching, caching, or application calling patterns.
10. **Re-measure:** compare before and after digest snapshots under equivalent workloads.
11. **Document limitations:** state representative data, measurement window, and other changes that could influence results.

## 15. Monitoring Deployment Checklist

### Collection

- [ ] Performance Schema is enabled.
- [ ] statements_digest consumer is enabled.
- [ ] Required statement instruments are enabled with appropriate timing.
- [ ] Verified digest capacity suffices for the number of query shapes.
- [ ] Checked digest text length limits.

### Analysis

- [ ] Track top digests by total latency.
- [ ] Track top digests by execution count.
- [ ] Track top digests by average/max latency.
- [ ] Track rows examined and rows sent.
- [ ] Track errors, warnings, disk temporary tables, and scans.
- [ ] Have alerting/checks for NULL digests.
- [ ] Analyze counters via snapshot/delta when time windows matter.

### Operations

- [ ] Dashboards do not treat summaries as per-execution history.
- [ ] Summary resets require approval and prior snapshots.
- [ ] Digest text is protected by access controls.
- [ ] Metrics do not introduce excessive label cardinality.
- [ ] Query plans are checked with representative parameters.
- [ ] Post-optimization gains are verified on equivalent workloads.

## 16. Principles to Remember

- Statement digests normalize SQL structure to group statements with differing literals.
- DIGEST is the identifier; DIGEST_TEXT is the readable normalized SQL form.
- The summary table groups by schema and digest; sharing a digest does not guarantee identical plans or latencies across runs.
- COUNT_STAR measures frequency; SUM_TIMER_WAIT measures total time; AVG_TIMER_WAIT measures per-execution average.
- Performance Schema timers use picoseconds; divide by 10^12 to convert to seconds.
- Rows examined, rows sent, errors, warnings, disk temporary tables, and no-index counters guide investigation direction.
- Performance Schema and the statements_digest consumer must be active for digests to be collected.
- Digest summaries are cumulative aggregates, not per-run history or a time series.
- A DIGEST IS NULL row can signal that distinct query shapes exceeded digest capacity.
- max_digest_length, performance_schema_max_digest_length, and performance_schema_digests_size affect digest storage and identification; check version specifics before tuning.
- Resetting summaries with TRUNCATE discards the statistical baseline; capture a snapshot and coordinate beforehand.
- Use digests to select candidate groups, then use EXPLAIN, EXPLAIN ANALYZE, logs, and tracing to pinpoint root causes.
- Do not add indexes solely because a counter reports full scans; evaluate selectivity, table size, and workload.
- Protect DIGEST_TEXT and Performance Schema read access as sensitive internal operational data.

Statement digests turn high volumes of SQL statements into comparable, prioritizable groups. By reading these metrics correctly, operators know which query group to tune first, whether an issue stems from call frequency or per-execution cost, and where to inspect execution plans. Combining digests with timed snapshots, execution plans, and application tracing creates a performance observability loop that can be verified after every change.
