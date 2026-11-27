# Characteristics of OLTP, Reporting, and Mixed Workloads

An e-commerce system can receive thousands of order placement requests during peak hours while simultaneously allowing staff to view revenue by day, product, and region. Both request groups read data from MySQL, yet they consume resources very differently. Placing an order needs to process a few records quickly and complete a transaction safely; a report may have to read millions of records and then group and aggregate them. When both groups run on the same server, they form a **mixed workload**.

Understanding the characteristics of each workload type helps in choosing table and index structures, organizing transactions, evaluating execution plans, allocating resources, and deciding when to offload traffic to a read replica or an analytical system.

## 1. Identifying the Three Workload Types

### 1.1. OLTP Transactional Workload

OLTP (Online Transaction Processing) serves online business operations such as creating orders, deducting inventory, recording payments, updating profiles, or transitioning order statuses. Each request typically operates on a relatively small set of data and must return results within a short time.

Common characteristics:

- **Short transactions with clear boundaries:** a business operation consists of one or a few statements, followed by `COMMIT` or `ROLLBACK`. For example, creating an order and deducting inventory must succeed or fail together.
- **High concurrency:** many users or services read and update rows simultaneously. Concurrency throughput and lock wait times directly affect user experience.
- **Selective reads and writes:** queries typically look up by primary key, customer ID, order ID, or an indexed predicate; write operations typically affect a small number of rows.
- **Latency matters:** the system cares about per-request response time, especially p95 and p99 percentiles during peak hours, not just average latency.
- **Correctness and durability:** InnoDB constraints, atomicity, consistency, isolation, and durability must hold under contention and failure scenarios.

For example, a sales transaction can check and deduct inventory, then insert order line items. The inventory update condition should be placed directly in the statement to avoid reading the quantity first and updating based on a stale value:

```sql
START TRANSACTION;

UPDATE inventory
SET available_qty = available_qty - 2
WHERE product_id = 42
  AND available_qty >= 2;

-- The application checks the number of affected rows.
-- If 0, out of stock or product does not exist: ROLLBACK.
-- If 1, continue writing the order and order line items.

INSERT INTO order_items (order_id, product_id, quantity)
VALUES (9001, 42, 2);

COMMIT;
```

This abbreviated example assumes the application already has a valid order and verifies the `UPDATE` result before running `INSERT`. In real code, if exactly one row was not deducted, it must `ROLLBACK`; it must never proceed to insert order items. Statements belonging to the same business action must reside in the same transaction so no half-finished state is created.

### 1.2. Reporting and Analytical Workload

Reporting workloads answer aggregate questions such as daily revenue, order counts by status, high-value customer segments, or monthly sales trends. These are read-heavy queries and often need to combine many rows across multiple tables.

Common characteristics:

- **Broad read scope:** queries filter over date ranges, scan many records, or join data from multiple tables.
- **Aggregate computations:** using `GROUP BY`, `COUNT`, `SUM`, `AVG`, `DISTINCT`, window functions, or large joins.
- **Longer runtimes:** a report may run for several seconds or minutes, depending on data size and complexity.
- **Request count may be low, but per-request cost is high:** a continuously refreshing dashboard or a large aggregation query can consume far more CPU, memory, and I/O than many small OLTP transactions.
- **Flexible data freshness:** end-of-day financial reports may accept scheduled pre-aggregated data; operational monitoring screens may need near-real-time data.

Example query for daily revenue within a month:

```sql
SELECT
    DATE(created_at) AS sales_day,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS revenue
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-11-01'
  AND created_at <  '2026-12-01'
GROUP BY DATE(created_at)
ORDER BY sales_day;
```

The time filter uses a half-open interval (`>=` first day and `<` next month's first day) to cover every instant in the month, even when the column includes a time component. This filter pattern also allows the optimizer to consider an index on `created_at`; wrapping the column in `DATE(created_at)` inside `WHERE` usually prevents standard index usage. Even so, `GROUP BY DATE(created_at)` may still require a temporary table or sorting. Always inspect the actual execution plan rather than inferring solely from the SQL text.

### 1.3. Mixed Workload

A mixed workload occurs when OLTP transactions and reporting queries share the same MySQL server, storage cluster, or bounded set of resources. For example, the system continues accepting orders while a dashboard runs a 12-month revenue report.

This is a common situation in small-to-medium systems. A single server can serve both workloads well when data volume, user count, and complexity are moderate. Problems arise when reporting queries consume resources or hold read states open too long, forcing latency-sensitive transactions to wait.

A mixed workload cannot be evaluated solely by read/write ratio. Two systems might both have 90% reads yet behave very differently: one mostly performs primary-key lookups; the other runs joins and aggregations over millions of records. Consider touched data size, concurrency, runtime, resource utilization, and data freshness requirements.

## 2. Comparing Characteristics of Each Workload Type

| Aspect | OLTP | Reporting | Mixed workload |
|---|---|---|---|
| Goal | Complete business actions accurately | Mine and aggregate data | Serve business transactions and analytics together |
| Access pattern | Many small, selective reads/writes | Broad range scans, joins, and aggregations | Interleaved small queries and resource-heavy queries |
| Transactions | Usually short, need fast commit | Can be long queries or read snapshots | Short transactions must share resources with long queries |
| Priority | Low latency, steady throughput, correctness | Completion time, completeness, and data freshness | Maintain business SLAs while serving reports |
| Common bottlenecks | Lock waits, many random accesses, write-heavy indexes | Multi-page scans, sorts, temporary tables, large joins | CPU, memory, and I/O contention and latency from long queries |
| Optimization approach | Short transactions, targeted indexes, key-based access | Reduce scanned data, pre-aggregate, or offload | Throttle heavy queries, separate read paths when needed |

These are tendencies, not absolute rules. A reporting query with a highly selective filter can run fast; a poorly designed OLTP transaction can trigger a full table scan. Classifying by actual query behavior matters more than the name of the screen or API.

## 3. Why Do Workloads Contend Inside MySQL/InnoDB?

### 3.1. Buffer Pool and Storage I/O

InnoDB uses the buffer pool to keep frequently accessed data and index pages in memory. OLTP typically has a hot working set of repeatedly accessed rows and indexes. A report performing a broad range scan can load many other pages into the buffer pool, evicting hot pages. When transactions return and need those pages, InnoDB must read them back from storage, increasing latency.

Reporting queries can also perform large sequential reads, competing for I/O bandwidth with OLTP random reads and writes. Therefore, increasing buffer pool size can help if the server has spare RAM, but it does not replace reducing scanned data volume or offloading queries when contention exceeds server capacity.

### 3.2. CPU, Sorting, and Temporary Tables

Multi-table joins, grouping, deduplication, and sorting can consume significant CPU. When intermediate results are large, MySQL may need temporary tables; part of the processing may spill to disk depending on size and configuration. Meanwhile, OLTP statements also need CPU for index lookups, row updates, constraint checks, and encryption/decryption.

A single reporting query does not necessarily cause trouble. Many dashboards refreshing simultaneously, each firing multiple aggregate queries, can create concurrent load spikes. Limiting the number of concurrent reporting queries and avoiding overly frequent full-dashboard refreshes often brings clear relief.

### 3.3. Redo Log, Disk Writes, and Checkpoints

Every InnoDB data modification is recorded via the redo log to support crash recovery. OLTP write transactions must complete according to configured durability requirements. Bulk write bursts, multi-row updates, or large data imports can increase redo volume and write pressure, causing small transactions to contend for I/O or wait for checkpoint conditions.

When loading large datasets, split them into reasonably sized batches, monitor write throughput, and avoid running concurrently with peak hours unless necessary. Do not casually disable durability safeguards just to make a benchmark faster and treat those numbers as real production capacity.

### 3.4. MVCC, Undo, and Long-Running Read Transactions

InnoDB uses MVCC (Multi-Version Concurrency Control) to provide consistent snapshots for regular read queries. A normal consistent `SELECT` generally does not lock the rows it reads, allowing reads and writes to proceed concurrently in many cases.

However, a read transaction left open too long holds onto an old read view. When that happens, InnoDB may have to retain older row versions in the undo log because an active transaction still needs to see them. Purge cannot reclaim those versions until no matching read view remains. As a result, undo history grows, consuming space and making cleanup lag behind.

Distinguish this from locking queries. `SELECT ... FOR UPDATE` and `SELECT ... FOR SHARE` are locking reads, which acquire locks and affect other transactions. A normal reporting `SELECT` does not automatically lock every row it reads, yet it can still create resource pressure and pin read views if kept inside a long transaction.

### 3.5. Locks and Access Order

OLTP can slow down when many transactions update the same hot row, the same index range, or acquire locks in different orders. Read-only reporting queries are not usually direct sources of row locks, but reports using locking reads, summary-table update jobs, or administrative transactions can participate in lock contention.

Deadlocks are a possibility in concurrent systems; InnoDB selects one transaction as the victim to roll back. Applications need a bounded retry strategy for deadlock errors, keep transactions short, and access rows in a consistent order whenever possible.

### 3.6. Replication and Data Lag

If reports run on a replica, heavy queries primarily contend for resources with other read queries on the replica. However, the replica must receive and apply changes from the source; when apply speed cannot keep up, read data becomes stale. Long reporting queries can also starve the replica of resources needed for other work.

Asynchronous replication does not guarantee a replica immediately has the newest data right after a primary commit. Business flows that need to read back newly written data, confirm payments, or show immediate status must have a consistent read strategy, such as routing to the primary for the required window or using a replica-catch-up wait mechanism appropriate to the deployment topology.

## 4. Designing Queries and Data by Usage Purpose

### 4.1. Keep the OLTP Path Short and Predictable

- Use primary keys and appropriate indexes to locate exact rows; avoid table scans when the operation only needs a single record.
- Keep transactions short. Do not leave transactions open while waiting for user input, calling external services, or doing non-database work.
- Select only needed columns instead of always using `SELECT *`, especially on tables with large columns.
- Enforce update conditions inside the SQL statement itself when possible, as in the inventory deduction example above.
- Keep index counts intentional. Each secondary index increases storage usage and the work required on `INSERT`, `UPDATE`, or `DELETE`.
- When updating multiple rows, access them in a stable order to reduce deadlock risk.

For example, a customer's order history page may need to filter by `customer_id`, bound a time range, and sort by creation time:

```sql
SELECT id, status, total_amount, created_at
FROM orders
WHERE customer_id = 120
  AND created_at >= '2026-11-01'
  AND created_at <  '2026-12-01'
ORDER BY created_at DESC
LIMIT 50;
```

A composite index ordered `(customer_id, created_at)` is a reasonable candidate for this query pattern: the equality predicate on customer comes first, followed by the time range. InnoDB can scan the index in reverse order to satisfy descending order. Even so, verify with real data and `EXPLAIN`; the right index depends on selectivity, data distribution, and other queries.

### 4.2. Reduce the Cost of Reporting Queries

- Filter using ranges on raw columns, especially datetime columns; avoid applying functions to columns inside `WHERE` if you want to leverage standard B-tree indexes.
- Select only needed columns. Avoid reading large datasets and transferring everything to the application to sum when MySQL can aggregate efficiently.
- Consider composite indexes for filter and join predicates. Column order should be based on query patterns and selectivity; no single order fits every report.
- Limit time ranges, paginate, or split reports into manageable chunks. For deep pagination, consider keyset pagination instead of huge `OFFSET` values.
- If a report runs repeatedly and the aggregation is expensive, consider summary tables updated on a schedule or via an event stream.
- Do not assume `COUNT(*)`, `DISTINCT`, or `GROUP BY` are always cheap. Measure how much data actually gets read and processed.

MySQL does not provide automatic materialized views like some other database systems. When using summary tables, the application or ETL/CDC pipeline must handle updates, late-arriving data, idempotent reruns, and reconciliation against source data. Clearly define how much staleness the report tolerates and how numbers are adjusted when orders are later canceled or amended.

### 4.3. Avoid Optimizing One Query by Slowing Down Every Write Transaction

Adding an index can reduce the number of pages a report reads, yet every modification on the table must maintain that index. An OLTP table with too many indexes can slow down `INSERT` and `UPDATE`, increase storage consumption, and reduce how much useful data fits in the buffer pool.

Therefore, evaluate both sides: how much cost the reporting query saves, and how much extra cost the write path pays to maintain the index. For very heavy reports with looser freshness requirements, summary tables or a replica may be a better choice than adding many indexes to the primary transactional table.

## 5. Measure Workload Before Deciding Optimization

Do not conclude a server lacks CPU, RAM, or IOPS based solely on a feeling that the app is slow. Collect metrics during normal hours and peak hours, and distinguish OLTP queries from reporting queries.

### 5.1. Metrics to Monitor

| Category | Metric or signal | What to inspect |
|---|---|---|
| User experience | p50, p95, p99 response times | Identify long-tail transactions without letting averages mask problems |
| Throughput | TPS, QPS, completed requests | Know how much work the system processes in a given period |
| Concurrency | Active connections, connection pool queue, threads running | Distinguish connection starvation from genuinely slow queries |
| Locks | Lock waits, deadlocks, long-open transactions | Find hot-row contention or lingering transactions |
| Memory and I/O | Buffer pool reads, disk read/write volume, storage latency | Detect large data scans or I/O contention |
| Queries | Slow queries, digests, rows examined vs. rows returned | Find expensive or overly frequent queries |
| InnoDB | Undo history, purge status, redo/checkpoint pressure | Detect long-running read transactions or heavy write load |
| Replica | Log apply lag and data freshness | Determine whether reports are reading stale data |

No single metric is sufficient to draw conclusions. For example, a high buffer pool hit ratio does not prove every query is efficient; a query can scan millions of pages already in RAM and still burn significant CPU. Combine response times, rows examined, CPU, I/O, and concurrency metrics.

### 5.2. Observability Tools in MySQL

- **Slow query log:** records queries exceeding a time threshold or configured criteria. Use it to find slow queries, then group by query digest and frequency. Avoid leaving the general query log enabled continuously on high-load systems without evaluating logging overhead.
- **Performance Schema:** provides statistics per statement, wait events, locks, and server activity. Views in the `sys` schema make reading common statistics easier.
- **`EXPLAIN`:** inspects the plan the optimizer expects to use, including join order, indexes, access types, and estimated row counts.
- **`EXPLAIN ANALYZE`:** on supported MySQL versions, executes the `SELECT` query and returns actual timing and row counts at each iterator. Because the statement actually executes, use caution with very heavy queries and pick an appropriate environment or time window.
- **`SHOW ENGINE INNODB STATUS`:** provides diagnostic details on transactions, deadlocks, I/O, and InnoDB state at the moment of inspection.

When analyzing a query, compare estimated rows with actual rows, see which step reads the most data, check whether the right index is used, and identify where time concentrates. After modifying indexes or SQL, re-measure on the same sample data and workload. Avoid benchmarking a single query in isolation and assuming the whole system will speed up.

## 6. Choosing Where to Run Reports

Not every system needs a multi-tier architecture from day one. The decision should rest on resource contention, data freshness requirements, report scale, and operational cost.

| Option | Suitable when | Considerations |
|---|---|---|
| Run together on primary | Data and reports are still small, queries are optimized, schedule causes minimal impact | Heavy reports can raise transaction latency; limit frequency and runtime |
| Offload reports to read replica | Reports are mostly reads, replication lag is acceptable, and read CPU/I/O should be isolated from primary | Replicas may serve stale data; monitor lag, resources, and log apply throughput |
| Summary tables or ETL/CDC pipeline | Repeated reports, expensive aggregations, freshness SLA can be defined | Requires sync workflow, handling updates/deletes, safe reruns, and reconciliation |
| Dedicated analytical data warehouse | Large historical analysis, multi-dimensional slicing, scans and aggregations on high data volumes | Introduces additional systems, pipelines, cost, and sync latency |

### 6.1. Running Together on Primary

This is the simplest option and can be reasonable when reporting queries are light, user count is small, and numbers must be immediately up to date. Even when sharing the primary, use a read-only account for reporting flows, restrict queries, and prevent dashboards from firing arbitrary ad-hoc queries against large tables.

Monitor p95/p99 of business transactions when reports start running. If latency spikes alongside aggregate queries, consider lowering refresh frequency, narrowing scope, pre-aggregating, or offloading.

### 6.2. Using a Read Replica

A read replica provides a separate read target to reduce direct contention with OLTP queries on the primary. The reporting account on the replica should have only `SELECT` privileges on the required schemas and tables. The application must clearly classify which queries are permitted to read from the replica.

Why care about replication lag? Suppose a customer just completed a payment and immediately opens the order history page. If that query routes to a replica that has not yet applied the payment transaction, the UI may display an outdated status. You can route consistency-critical reads back to the primary, or use synchronization-wait mechanisms suited to the topology. Never assume every replica immediately reflects just-committed data.

Replicas also require monitoring. A full-scan report can slow down other queries on the replica or cause change application to fall behind. Separating servers isolates part of the resources, but it does not eliminate the need to optimize queries.

### 6.3. Using Summary Tables or a Data Warehouse

For dashboards querying the same aggregation continuously, create summary tables by day, product, or region. For example, instead of grouping millions of orders every time a dashboard opens, a pipeline can update daily revenue totals and the dashboard reads only the pre-aggregated rows.

This design must answer several questions: is data updated event-by-event or on a schedule; what staleness latency is acceptable; how are canceled or refunded orders adjusted; do pipeline reruns produce duplicate numbers; and how are summaries reconciled with transactional tables. Without answering these questions, a dashboard may be fast yet display wrong numbers.

When analytical needs require scanning huge histories, many dimensions, or complex aggregations, consider a dedicated analytical data warehouse. MySQL can remain the transactional source of truth while data flows via ETL or CDC into a system better suited for analytical queries.

## 7. Troubleshooting Workflow When OLTP Slows Down During Reports

Suppose order creation latency jumps from 80 ms to 900 ms whenever the revenue dashboard opens. You can investigate in this sequence:

1. **Establish time correlation:** compare ordering API p95/p99 against report execution timestamps; check concurrent report counts and dashboard refresh schedules.
2. **Locate load-generating queries:** use the slow query log and digest statistics in Performance Schema to identify SQL patterns, frequency, latency, and rows examined.
3. **Inspect execution plans:** use `EXPLAIN`, and `EXPLAIN ANALYZE` where appropriate, to spot table scans, expensive joins, sorts, or temporary tables.
4. **Reduce work done:** narrow time ranges, fix filter predicates, select fewer columns, add justified indexes, or build summary tables.
5. **Throttle contention:** lower refresh frequency, cap concurrent report runs, set appropriate timeouts, and separate accounts/connections for reporting paths.
6. **Evaluate offloading:** move reports to a replica or data warehouse if post-optimization load still harms OLTP SLAs and data freshness tolerances allow it.
7. **Re-measure under realistic load:** verify business transactions recover, reports still return accurate figures, and replicas do not develop excessive lag.

Do not rush to raise the connection limit to fix slowness. If the root cause is saturated CPU or I/O, adding connections lets more queries contend for resources simultaneously and lengthens wait times. Identify the root cause across queries, locks, resources, or connection pool limits before tuning.

## 8. Common Misconceptions

- **"Reads do not affect writes."** Normal consistent reads may not lock rows, yet they still consume CPU, buffer pool, and I/O; long read transactions also pin read views and slow down purge.
- **"Adding a replica means reports are always fresh."** Asynchronous replication has lag; distinguish which queries tolerate delayed data and which must read from the primary.
- **"Adding an index always makes queries faster."** Indexes carry storage cost and write maintenance overhead. Add them only after identifying query patterns and verifying with execution plans.
- **"High QPS means heavy load."** A high volume of primary-key lookups can be cheaper than a few queries scanning and aggregating millions of rows. Look at per-query cost.
- **"Adding RAM solves every problem."** RAM helps cache data, but it does not eliminate CPU-heavy joins, large sorts, lingering transactions, hot locks, or queries examining far too many rows.
- **"Partitioning automatically speeds everything up."** Partitioning helps when aligned with filtering and data retention/maintenance; it does not replace indexes or fix a poor query plan on its own.

## 9. Workload Assessment Checklist for a MySQL System

When designing or investigating performance, make sure you can answer these questions:

- What are the most critical business transactions, and what p95/p99 latency and throughput do they require?
- Which tables and rows are read/written most frequently? Are there hot rows or lock contention?
- Which reports scan large amounts of data, how long do they run, how often do they run, and how much staleness can they tolerate?
- Do queries use indexes aligned with filter predicates, joins, and sort orders?
- Are any read or write transactions staying open too long? Do undo history and lock waits spike during reporting hours?
- Where is pressure concentrated: CPU, buffer pool, I/O, redo, or connection pool?
- Should reports run on the primary, a replica, summary tables, or a separate data warehouse?
- After offloading, how does the application handle read-after-write and replica lag?
- Are there before/after measurements confirming changes improve both performance and correctness?

## Conclusion

OLTP prioritizes short, accurate transactions and predictable latency; reporting prioritizes reading, joining, and aggregating large datasets; mixed workloads must satisfy both within the same resource budget. With MySQL/InnoDB, this contrast surfaces in buffer pool usage, CPU, I/O, redo/undo, MVCC, and locking. Measure query behavior under realistic workloads, optimize data access paths, bound heavy queries, and choose primary, replica, or analytical pipelines according to business latency and data freshness requirements.
