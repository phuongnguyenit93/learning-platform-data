# Measuring Latency, Throughput, CPU/I/O, and Correctness After Changes

SQL tuning only matters when you can prove the query or workload improved while business results remain accurate. A single statement running faster in one ad-hoc test is not enough to declare success: the cache may have been warmer, the test dataset too small, connection counts different, or the workload unrepresentative of production.

A tuning evaluation must answer four groups of questions:

1. **Latency:** how long does a request/query take, especially at p95 and p99?
2. **Throughput:** how many requests, statements, or transactions per second does the system complete at a defined concurrency level?
3. **Resources:** how do CPU, memory, I/O, buffer pool, lock waits, and temporary work change?
4. **Correctness:** do query results, side effects, transaction semantics, and business invariants remain unchanged?

This lesson builds a before/after measurement process: collecting metrics from Performance Schema and status variables, measuring client-side load, comparing one change at a time, and verifying output correctness. The goal is turning "the query looks faster" into a reproducible, explainable conclusion.

## 1. Distinguish Four Metric Groups

| Group | Metrics to monitor | Question to answer |
|---|---|---|
| Latency | p50, p95, p99, max, timeouts, error rate | How long do users wait and did the tail degrade? |
| Throughput | completed requests/s, QPS, TPS, rows/s | How much work does the system finish per unit of time? |
| Resources | CPU, RAM, disk IOPS/latency, bytes read/write, buffer pool, lock waits | How many resources does that speed cost and where is the bottleneck? |
| Correctness | row set, values, duplicates, ordering, invariants, side effects, transaction outcome | Did the change preserve business behavior? |

Never use one metric as a proxy for everything. For example, higher throughput paired with a sharp p99 spike can degrade user experience. Lower CPU paired with higher disk I/O may simply shift a bottleneck from CPU to storage. A faster query returning missing rows is a failed tuning effort.

## 2. Latency: Measure the Distribution, Not Just the Average

Latency is the elapsed time from when a request starts until its result arrives across a chosen measurement boundary. Clarify what is being measured:

- Round-trip time from the application to MySQL and back.
- Statement execution time recorded by MySQL.
- Entire transaction duration, covering multiple statements and commit.
- End-to-end API/request duration including application logic, serialization, and network.

These numbers are not identical. Performance Schema records server-side statement time; client benchmarks typically measure round-trip time. When users complain an API is slow, inspecting only server statement time misses connection pool waits, network latency, application processing, or queuing before SQL is sent.

### Common Percentiles

| Metric | Interpretation |
|---|---|
| p50 | 50% of requests finish at or below this time; represents typical behavior. |
| p95 | 95% of requests finish at or below this time; captures the significant slow tail. |
| p99 | 99% of requests finish at or below this time; sensitive to tail latency. |
| max | Slowest request in the measurement window; easily skewed by outliers. |
| mean/average | Total time divided by request count; can hide a cluster of very slow requests. |

Example:

```text
                         Baseline       Candidate
p50 latency                 8 ms            7 ms
p95 latency                35 ms           42 ms
p99 latency               110 ms          190 ms
Average latency             12 ms           11 ms
```

The candidate has a better average yet worse p95/p99. Some queries may have sped up while heavy requests slowed due to CPU, I/O, lock, or sort contention. Never claim an improvement based solely on average latency.

### Percentiles Should Be Measured on the Client Side

MySQL summary views usually report counts, averages, min/max, or total times, and do not always maintain sufficient histograms for p95/p99 per query digest. Use a client-side benchmark/load-test harness with latency histograms (e.g., HDR Histogram or percentile-capable benchmark tools) to collect p50/p95/p99.

When measuring, record timeouts and errors too. Never exclude timed-out requests from the distribution and declare lower latency; timeouts must count against error/SLO budgets and be analyzed separately.

## 3. Throughput: Define the Right Unit of Work

Throughput is completed work per unit of time. Across MySQL and applications, distinguish:

- **Request/s:** application requests completed per second.
- **QPS:** SQL statements executed per second.
- **TPS:** committed transactions per second.
- **Rows/s:** rows read or written per second; useful for batch jobs but not a full proxy for business work.

A single request might execute 1, 5, or 20 SQL statements. Thus, higher QPS does not guarantee higher request throughput. A transaction can span multiple statements; counting statements is not equivalent to counting committed transactions.

When reporting, specify units and scope clearly:

```text
Completed API requests:  820 requests/s
SQL statements:        4,100 statements/s
Committed business tx:   760 transactions/s
Concurrency:              64 clients
Measurement window:       5 minutes after warm-up
```

These numbers are illustrative. Real measurements must report metrics from the actual tested workload along with accompanying error/timeout counts.

### Offered Load vs Completed Throughput

Offered load is the rate at which clients submit work; completed throughput is the rate at which the system finishes work. At saturation, clients might keep submitting 1,000 requests/s while the server completes only 700 requests/s; the remainder accumulates as queuing, timeouts, or backlog.

Always report offered rate, completed rate, concurrency, and error rate together. Reporting only submitted requests mistakes generated load for completed work.

### Concurrency and Saturation

Measure across multiple concurrency levels to locate where the system saturates—such as 1, 8, 16, 32, and 64 clients. Never test at a single load level. At low concurrency, a query can seem instant; at high concurrency, lock contention, buffer pool pressure, CPU scheduling, or I/O queues can send p99 soaring.

As concurrency rises, observe:

- Whether completed throughput keeps climbing, plateaus, or drops.
- At which concurrency level p95/p99 spikes sharply.
- Whether `Threads_running`, CPU, and I/O queues climb.
- Whether lock waits, deadlocks, timeouts, and connection pool queues rise.
- Whether error rates and dropped requests change.

## 4. CPU and I/O: Identify Which Resource Constrains the Workload

### CPU

CPU usage can climb due to scanning many rows, evaluating expressions across rows, join fan-out, sorting, aggregation, excessive statement parse/execute overhead, or high concurrency. Measure both the MySQL process CPU and host-wide CPU during the same benchmark window.

Performance Schema statement timers measure elapsed/wait time for statements, not pure CPU time. To measure CPU, pair with OS/process tools such as Windows Performance Monitor or Task Manager; on Linux, use `pidstat`, `top`, or equivalent monitoring tools.

Signals to check:

- `mysqld` process CPU nearing saturation while throughput stalls.
- High rows examined or high JOIN loop counts.
- p95/p99 climbing alongside CPU utilization.
- Sorting, aggregation, or expensive expressions appearing in top query digests.

### Disk I/O

I/O rises when the working set does not fit in the buffer pool, queries perform many random page reads, sorts/materializations spill to disk, checkpoints/flushes write heavily, or storage exhibits high latency.

Measure both:

- Device read/write IOPS and throughput.
- Average and tail disk latency.
- Device queue depth or wait time.
- Bytes read/written.
- MySQL file I/O waits and InnoDB physical reads.

Performance Schema file waits reflect time MySQL spent waiting on instrumented I/O events; they do not replace device/OS latency metrics. Combine both to see whether MySQL is waiting on files and whether the storage device is actually saturated.

### Buffer Pool

The InnoDB buffer pool caches data and index pages. When a needed page is already in the buffer pool, the engine avoids a physical read. If the working set exceeds memory or access is scattered, physical reads climb.

Two common status counters:

- `Innodb_buffer_pool_read_requests`: logical read requests.
- `Innodb_buffer_pool_reads`: times InnoDB had to read a page from storage into the buffer pool.

You can approximate the hit ratio over a measurement interval:

\[
\text{Approx. hit ratio} = 1 - \frac{\Delta\text{Innodb\_buffer\_pool\_reads}}{\Delta\text{Innodb\_buffer\_pool\_read\_requests}}
\]

This is only a coarse indicator. It is influenced by read-ahead, workload mix, and sampling interval; never treat a high ratio as proof that every query is fast or free of I/O bottlenecks.

## 5. Build a Reproducible Baseline

A baseline is pre-change data collected under well-defined conditions so subsequent runs are directly comparable. A solid baseline records:

1. MySQL version, storage engine, and relevant configuration.
2. Schema, indexes, row counts, and data distribution.
3. Exact SQL, parameter values, and query digests.
4. Isolation level, autocommit, and transaction boundaries.
5. Identical dataset snapshot or data loading procedure.
6. Cache state: warm-up, buffer pool state, and handling of initial runs.
7. Concurrency, connection pool size, offered load, and run duration.
8. p50/p95/p99, completed throughput, errors, and timeouts.
9. CPU, memory, disk I/O, lock waits, and temporary/sort counters.
10. Execution plans and actual rows/loops when safe to capture.

Never compare a cold-cache run against a warm-cache run and credit the whole difference to a new index. Pick a consistent protocol: either warm up both before measuring, or explicitly measure cold-start and steady-state separately.

### Warm-Up and Cache State

Warm-up eliminates initial cold-cache startup effects before measuring steady-state performance. However, warm-up must not mutate data or give a candidate more warm-up iterations than the baseline.

Sample protocol:

```text
1. Restore the exact same dataset snapshot.
2. Start/prepare the same server version and configuration.
3. Run warm-up with the same workload for 60-120 seconds.
4. Start a fixed measurement window, e.g., 5 minutes.
5. Collect latency histograms, completed throughput, and resource metrics.
6. Repeat at least several rounds under identical conditions.
7. Alternate baseline/candidate order across rounds if possible.
```

Durations are illustrative; real workloads may require longer warm-up and measurement windows to stabilize caches and represent traffic cycles.

### Keep the Workload Identical

Baseline and candidate must use the same:

- Parameter value sets, or identical parameter distributions.
- Read/write ratio and query digest mix.
- Client count and connection pool configuration.
- Warm-up and measurement durations.
- Equivalent data and statistics.
- Resource limits and host conditions.

If a candidate is tested with fewer clients or fewer heavy queries, the result is no longer a fair comparison.

## 6. Tuning Example: Rewriting DATE() to a Range Predicate

Create a test table with a `DATETIME` timestamp:

```sql
CREATE TABLE tuning_orders (
    order_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE=InnoDB;

INSERT INTO tuning_orders (
    order_id, tenant_id, status, created_at, total_amount
)
VALUES
    (1, 42, 'PAID', '2026-01-15 08:10:00', 100.00),
    (2, 42, 'PAID', '2026-01-15 16:30:00', 250.00),
    (3, 42, 'NEW',  '2026-01-15 18:45:00',  80.00),
    (4, 42, 'PAID', '2026-01-16 00:05:00', 300.00),
    (5, 99, 'PAID', '2026-01-15 12:00:00', 500.00);
```

Baseline query:

```sql
SELECT order_id, status, created_at, total_amount
FROM tuning_orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND DATE(created_at) = '2026-01-15'
ORDER BY created_at DESC, order_id DESC;
```

Applying `DATE()` to the column can prevent a regular index on `created_at` from being used for range access as intended. The candidate query preserves the exact business condition using a half-open range:

```sql
SELECT order_id, status, created_at, total_amount
FROM tuning_orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-01-15 00:00:00'
  AND created_at <  '2026-01-16 00:00:00'
ORDER BY created_at DESC, order_id DESC;
```

Create the candidate index:

```sql
CREATE INDEX idx_tuning_orders_tenant_status_created
ON tuning_orders (tenant_id, status, created_at);
```

In InnoDB, secondary indexes carry the primary key as a row locator; since `order_id` is the primary key, there is no need to repeat it in the index definition. After creating the index, inspect the plan:

```sql
EXPLAIN FORMAT=TREE
SELECT order_id, status, created_at, total_amount
FROM tuning_orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-01-15 00:00:00'
  AND created_at <  '2026-01-16 00:00:00'
ORDER BY created_at DESC, order_id DESC;

EXPLAIN ANALYZE
SELECT order_id, status, created_at, total_amount
FROM tuning_orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-01-15 00:00:00'
  AND created_at <  '2026-01-16 00:00:00'
ORDER BY created_at DESC, order_id DESC;
```

The fixture has only five rows, so the optimizer may still choose a table scan. Use a sufficiently large dataset to evaluate access paths and actual runtime; never treat a tiny table's plan as proof that an index is useless.

### Verify Result Equivalence

On `DATETIME`, a half-open range from midnight to before the next midnight equals `DATE(created_at) = date` in this example. To compare row sets and column values, save both outputs into temporary tables on the same session:

```sql
CREATE TEMPORARY TABLE result_before AS
SELECT order_id, status, created_at, total_amount
FROM tuning_orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND DATE(created_at) = '2026-01-15';

CREATE TEMPORARY TABLE result_after AS
SELECT order_id, status, created_at, total_amount
FROM tuning_orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-01-15 00:00:00'
  AND created_at <  '2026-01-16 00:00:00';
```

Compare row counts:

```sql
SELECT 'before' AS result_set, COUNT(*) AS row_count
FROM result_before
UNION ALL
SELECT 'after', COUNT(*)
FROM result_after;
```

Find missing, extra, or altered rows:

```sql
SELECT b.order_id, 'missing_or_changed' AS difference
FROM result_before AS b
LEFT JOIN result_after AS a
  ON a.order_id = b.order_id
WHERE a.order_id IS NULL
   OR NOT (b.status <=> a.status)
   OR NOT (b.created_at <=> a.created_at)
   OR NOT (b.total_amount <=> a.total_amount)

UNION ALL

SELECT a.order_id, 'extra' AS difference
FROM result_after AS a
LEFT JOIN result_before AS b
  ON b.order_id = a.order_id
WHERE b.order_id IS NULL;
```

The expected result is zero difference rows. These two temporary tables compare membership and values, not ordering, because SQL tables have no guaranteed physical order. If business logic requires ordering, execute both SELECTs with the same `ORDER BY` and compare sequences on the client side.

**Timestamp note:** this example uses `DATETIME`. If the column is `TIMESTAMP`, MySQL converts values according to the session time zone on read/write; determine the business day's timezone and apply the exact same timezone to both expressions. Never mechanically swap `DATE(timestamp_col)` for UTC bounds if the original query evaluated calendar dates in another timezone.

## 7. Measuring Application-Side Latency and Throughput

A client benchmark should record at least:

```text
test_name
query_or_request_id
concurrency
offered_requests_per_second
completed_requests_per_second
success_count
error_count
timeout_count
p50_ms
p95_ms
p99_ms
max_ms
measurement_duration_seconds
```

If the workload mixes multiple query types, collect separate histograms per query type or class. One fast digest running millions of times can drown out a slow, infrequent digest if you inspect only overall latency.

### Avoid Coordinated Omission

A load generator must continue recording latency for requests that should have been sent while the server was stalled. If a client waits for the previous request to finish before issuing the next, it throttles offered load whenever the server slows down and underestimates tail latency. Pick a tool whose load generation model and histogram fit your goal, and document whether the test is closed-loop or open-loop.

### Measure Transactions End-to-End

For multi-statement transactions, measure from before the first statement until after `COMMIT`/`ROLLBACK`, rather than measuring only the fastest SELECT. A transaction can incur lock waits, log flushes, or network round-trips between statements. Record committed transaction counts and rolled-back transaction counts alongside the latency distribution.

## 8. Using Performance Schema to Find Time-Consuming Query Digests

`performance_schema.events_statements_summary_by_digest` aggregates statements by normalized digest. This view is useful for spotting queries with high total time, high rows examined, or temporary/sort work.

```sql
SELECT
    SCHEMA_NAME,
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(AVG_TIMER_WAIT / 1000000000, 2) AS avg_ms,
    ROUND(MAX_TIMER_WAIT / 1000000000, 2) AS max_ms,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    SUM_CREATED_TMP_TABLES,
    SUM_CREATED_TMP_DISK_TABLES,
    SUM_SORT_ROWS,
    SUM_NO_INDEX_USED
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST_TEXT IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Performance Schema timers are in picoseconds. Divide `AVG_TIMER_WAIT` by 1,000,000,000 to convert to milliseconds. `SUM_TIMER_WAIT` ranks by total time consumed; frequently executed queries can top the list even if individual runs are fairly fast.

Read the columns together:

- `COUNT_STAR`: number of recorded statement executions.
- `AVG_TIMER_WAIT` and `MAX_TIMER_WAIT`: average and maximum server-side statement time.
- `SUM_ROWS_EXAMINED`: total rows examined.
- `SUM_ROWS_SENT`: total rows returned to clients.
- `SUM_CREATED_TMP_TABLES` and `SUM_CREATED_TMP_DISK_TABLES`: internal temporary tables recorded.
- `SUM_SORT_ROWS`: rows sorted.
- `SUM_NO_INDEX_USED`: executions performed without using an index.

Digest summaries do not directly provide p95/p99. They also collapse differing parameter values into one digest, so pair them with application tracing or slow logs to pinpoint which parameters trigger slowness.

### Inspect Table I/O Waits

```sql
SELECT
    OBJECT_SCHEMA,
    OBJECT_NAME,
    COUNT_READ,
    ROUND(SUM_TIMER_READ / 1000000000000, 3) AS read_wait_seconds,
    COUNT_WRITE,
    ROUND(SUM_TIMER_WRITE / 1000000000000, 3) AS write_wait_seconds
FROM performance_schema.table_io_waits_summary_by_table
WHERE OBJECT_SCHEMA = DATABASE()
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Performance Schema timers are cumulative and depend on enabled instrumentation. This reports wait time recorded at the table handler layer, not raw physical device latency. Use it to find tables with heavy I/O activity, then cross-check against file/device metrics.

### Inspect File I/O Waits

```sql
SELECT
    EVENT_NAME,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS wait_seconds
FROM performance_schema.events_waits_summary_global_by_event_name
WHERE EVENT_NAME LIKE 'wait/io/file/%'
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

This query highlights file event classes with high total wait time, such as data files or redo log files if the corresponding instruments are enabled. Counters are cumulative since startup or last reset; compute deltas over your measurement window rather than relying on absolute values alone.

## 9. Measure InnoDB Buffer Pool and Status Counters

Capture snapshots of status counters before and after a workload window:

```sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Threads_running',
    'Threads_connected',
    'Questions',
    'Queries',
    'Slow_queries',
    'Innodb_buffer_pool_read_requests',
    'Innodb_buffer_pool_reads',
    'Innodb_data_reads',
    'Innodb_data_writes',
    'Innodb_data_read',
    'Innodb_data_written',
    'Created_tmp_tables',
    'Created_tmp_disk_tables'
);
```

Take a snapshot before the benchmark, run the workload for a fixed window, and take a second snapshot. Deltas between snapshots estimate logical/physical reads, bytes read/written, temporary tables, and concurrency during that window.

Do not reset global status counters in production purely for convenience without understanding the impact on other monitoring systems. Taking before/after snapshots and computing deltas is much safer.

### Interpreting Key Counters

| Counter | How to use |
|---|---|
| `Threads_running` | Threads actively executing, not merely open connections. Watch alongside CPU and throughput. |
| `Threads_connected` | Open connections; compare against connection pool and server limits. |
| `Questions`/`Queries` | Statement counters as defined by MySQL; do not equate with business TPS. |
| `Innodb_buffer_pool_read_requests` | Logical page read requests. |
| `Innodb_buffer_pool_reads` | Physical page reads into the buffer pool. |
| `Innodb_data_read`/`Innodb_data_written` | Bytes read/written by InnoDB per the respective counters. |
| `Created_tmp_disk_tables` | Internal temporary tables recorded as on-disk; does not represent all filesort temp files or all memory-mapped temp storage. |

Global counters reflect the entire instance's workload, not solely the query under test. Use a test instance or isolate the workload when attributing changes to a specific query.

## 10. Measure CPU, Disk, and Memory at the Host Level

SQL status variables do not replace OS monitoring. During the same benchmark window, record:

| Resource | Metrics to collect | Interpretation |
|---|---|---|
| CPU | mysqld process CPU, host CPU, run queue | Sustained near-100% CPU while throughput stalls signals CPU saturation. |
| Memory | mysqld RSS/working set, available memory, swap/page faults | RAM exhaustion or swapping can cause sudden latency spikes. |
| Disk | read/write IOPS, MB/s, average/p95 latency, queue depth | High I/O wait paired with high device latency points to a storage bottleneck. |
| Network | bytes/s, retransmits, connection latency | Can constrain large result payloads or high round-trip counts. |
| MySQL | Threads_running, buffer pool reads, file waits, lock waits | Connects SQL activity to host resource consumption. |

On Windows, use Performance Monitor to track the `mysqld` process, CPU, working set, and disk counters. On Linux, use tools such as `iostat`, `pidstat`, `vmstat`, or your observability platform. Monitor the exact volumes holding data, redo logs, and temporary files; they may reside on separate storage devices.

## 11. Control Variables in Before/After Comparisons

A benchmark is valid only when baseline and candidate run under sufficiently comparable conditions. Factors that easily skew comparisons:

- Datasets differing in row count or data distribution.
- One run having a warm buffer pool while the other is cold.
- Running one test off-peak and the other during peak hours.
- Differing background jobs, backups, purging, or replication activity.
- Different connection pool sizes or concurrency levels.
- Parameter values not drawn from the same distribution.
- One side receiving extra warm-up.
- Other processes competing for host CPU or storage.
- A candidate altering another query's plan via index or cache contention.

Whenever possible, run baseline and candidate on the same instance type and identical dataset snapshot. Repeat multiple rounds, alternate run order to cancel time-drift bias, and report medians across rounds alongside per-request distributions.

### Change One Factor at a Time

If you alter SQL, indexes, isolation level, connection pool, and buffer size all at once, you cannot tell which change caused the outcome. Change one factor at a time or design a controlled experiment; record exact DDL, config, and query versions for every candidate.

Example tracking table:

| Run | Candidate | Concurrency | p95 | p99 | Completed TPS | CPU | Disk read MB/s | Errors |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| A1 | Baseline | 32 | 42 ms | 110 ms | 720 | 68% | 85 | 0.02% |
| B1 | New index | 32 | 25 ms | 61 ms | 910 | 59% | 44 | 0.01% |

These are illustrative figures, not real measured results. A real report should include multiple rounds and document the measurement window, warm-up, workload mix, dataset, and configuration.

## 12. Verify Correctness After Optimizing SELECTs

A rewrite can alter semantics even when it looks equivalent. Verify:

- Row counts and returned key sets.
- Column values, including NULLs and data types.
- Duplicates and `DISTINCT`/`UNION` semantics.
- Ordering when the query has `ORDER BY`.
- Range boundaries, timestamps, timezones, and precision.
- Collation, case sensitivity, and string comparisons.
- Aggregates, rounding, overflow, and numeric types.
- Authorization/visibility if queries filter by tenant or user.

Never compare only `COUNT(*)` or `SUM(amount)`. Two different result sets can have identical counts and sums. Compare key sets and individual column values; test boundary cases such as start/end of day, NULLs, duplicates, zero/negative numbers, large values, and multiple tenants.

### Verify Query Results Using Comparison Tables

Section 6 created `result_before` and `result_after`. Use anti-joins to detect missing/extra rows and null-safe equality (`<=>`) to compare values. If results allow duplicates without a unique key, compare multiplicities via grouping/counts rather than anti-joining on non-unique keys alone.

For ordered queries, compare sequences on the client side. A SQL table has no guaranteed row order; only the final `ORDER BY` on the outer SELECT determines returned order.

## 13. Verify Correctness After DML Changes

When tuning INSERT/UPDATE/DELETE or batch jobs, verify both resulting data state and side effects:

- Is the affected row count right (`ROW_COUNT()` on the same session immediately after the statement, or affected rows from the driver)?
- Were any rows skipped or double-updated?
- Do unique, foreign key, check constraints, and business invariants hold?
- Do triggers, audit rows, outbox events, or business counters fire identically?
- Could retries execute the same operation twice?
- Do transaction commit/rollback boundaries enclose the exact right statements?

Example in a test environment:

```sql
START TRANSACTION;

UPDATE tuning_orders
SET status = 'ARCHIVED'
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at < '2026-01-01 00:00:00';

SELECT ROW_COUNT() AS affected_rows;

-- Check invariants before deciding how to end the transaction.
SELECT COUNT(*) AS remaining_old_paid_rows
FROM tuning_orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at < '2026-01-01 00:00:00';

ROLLBACK;
```

This example rolls back for illustration; DDL is not inside this transaction. In real applications, `ROW_COUNT()` must be read immediately after DML on the same connection because the next statement can overwrite that session state.

## 14. Verify Transactions and Concurrency

A query that works cleanly in isolation can trigger lost updates, double spends, duplicate inserts, or inconsistent reads under concurrency. After tuning, check:

- Isolation levels and transaction boundaries remain unchanged.
- Locking reads (`FOR UPDATE`, `FOR SHARE`) still protect write decisions where needed.
- Conditional update operations remain atomic.
- Deadlocks and lock wait timeouts do not increase.
- Whole-transaction retries preserve idempotency.
- No phantoms or race conditions violate business rules.
- Lock acquisition order across concurrent transactions did not shift unexpectedly.

### Balance Invariant Example

Suppose money transfers must keep total balances constant across successful transfers, with all updates inside one transaction. Concurrency tests should verify:

1. No account goes negative if business rules forbid negative balances.
2. Sum of balances before and after remains equal for internal transfers.
3. Each transfer ID is applied at most once.
4. If one step fails, both updates roll back.
5. Two concurrent withdrawals cannot read the same stale balance and overdraw available funds.

Use `SELECT ... FOR UPDATE` or conditional UPDATEs appropriately to protect invariants. Tuning must preserve concurrency protections, never drop locks just to lower single-thread latency.

## 15. Evaluate Write Cost and Side Impact Beyond the Target Query

Adding an index typically reduces read cost while increasing write amplification. A candidate may speed up query A while slowing INSERT/UPDATE/DELETE, increasing disk usage, buffer pool pressure, and replication lag.

Measure the full workload mix rather than benchmarking only the tuned query:

- SELECT/INSERT/UPDATE/DELETE ratio.
- Write-path throughput.
- Redo generation, data bytes written, and disk latency.
- Lock waits and deadlocks.
- Buffer pool hit/read behavior.
- Replica lag if replication is present.
- Index size before and after.

An index is worthwhile only when read savings outweigh maintenance overhead in the real workload. If a new index cuts target query latency by 30% while dropping write throughput by 40%, re-evaluate system priorities.

## 16. Acceptance Thresholds and Rollout Decisions

Define success criteria before running benchmarks. Example:

| Criterion | Illustrative threshold |
|---|---|
| Correctness | 100% of test cases and invariants pass. |
| p95 latency | No worse than baseline; target at least 15% reduction. |
| p99 latency | No more than 5% increase at target concurrency. |
| Throughput | At least 10% increase, or flat throughput with lower resources. |
| Error/timeout rate | Zero increase; no SLO regressions tolerated. |
| CPU | Stays within operational limits. |
| Disk I/O | No storage queue/latency spikes beyond thresholds. |
| Write path | Write throughput stays above business requirements. |

These are merely examples. Choose thresholds grounded in actual SLOs, capacity, and business priorities. If correctness fails, reject the candidate regardless of how fast latency looks.

### Controlled Rollout

1. Archive baseline SQL, plans, DDL, config, and benchmark results.
2. Deploy candidate to staging or canary with comparable data and workload.
3. Run correctness suites and concurrency tests.
4. Measure latency, throughput, CPU/I/O, and error rates.
5. Roll out gradually to a small percentage if canary traffic is supported.
6. Monitor query digests, p95/p99, resource usage, and business metrics.
7. Roll back SQL/indexes/config if any regression breaches thresholds.
8. Preserve before/after evidence so others can reproduce measurements.

For DDL creating indexes on large tables, also assess build time, metadata locks, disk space, replica lag, and index drop/rollback procedures. A faster query in benchmarks is worthless if the migration causes an outage.

## 17. Common Mistakes When Measuring Tuning

| Mistake | Why it misleads | How to fix |
|---|---|---|
| Measuring only once | Caches, schedulers, and background tasks introduce variance | Warm up and repeat across multiple rounds. |
| Reporting only average latency | Hides p95/p99 and timeouts | Collect client-side latency histograms. |
| Calling QPS "TPS" | One transaction can contain many statements | Report requests/s, statements/s, and transactions/s separately. |
| Counting offered load as completed throughput | Ignores backlog, timeouts, and errors | Report offered, completed, and error rates. |
| Running candidate warm-cache vs baseline cold-cache | Unfair comparison | Standardize cache state or report cold/warm runs separately. |
| Using tiny fixtures | Optimizer chooses table scans, unrepresentative of production | Use large enough data with representative distributions. |
| Looking only at EXPLAIN | Plan estimates do not show real latency | Combine EXPLAIN ANALYZE, client metrics, and host metrics. |
| Treating statement timers as CPU time | Timers include elapsed/wait time | Measure process/host CPU and cross-check Performance Schema waits. |
| Treating `Created_tmp_disk_tables` as all temp files | Excludes some filesort spills and memory-mapped temp storage | Read alongside Sort counters, plans, and OS I/O. |
| Comparing counts/sums to prove result equality | Different row sets can have identical counts/sums | Compare key sets, per-row values, duplicates, and order. |
| Testing with one client only | Misses lock contention and saturation | Test multiple concurrency levels and transaction mixes. |
| Ignoring write paths when adding indexes | Reads speed up while writes slow down | Benchmark the full workload mix and write amplification. |
| Changing multiple factors at once | Cannot isolate cause of gain or regression | Change one factor at a time or run controlled experiments. |
| Omitting errors/timeouts from reports | Makes throughput/latency look artificially good | Report successes, errors, timeouts, and dropped requests. |

## 18. Before/After Tuning Practice Checklist

### Before Changes

- [ ] Recorded exact SQL and parameter distributions.
- [ ] Recorded schema, indexes, row counts, and data distributions.
- [ ] Recorded MySQL version, isolation level, autocommit, and relevant config.
- [ ] Captured EXPLAIN/EXPLAIN ANALYZE appropriately.
- [ ] Measured client-side p50/p95/p99, throughput, and error rate.
- [ ] Measured CPU, RAM, disk latency/IOPS, buffer pool, and lock waits.
- [ ] Executed baseline correctness tests and saved reference outputs.

### After Changes

- [ ] Used the same dataset, workload mix, concurrency, and measurement window.
- [ ] Followed identical warm-up rules.
- [ ] Repeated multiple rounds and compared latency distributions.
- [ ] Compared completed throughput, errors/timeouts, and resource consumption.
- [ ] Compared execution plans, actual rows/loops, and statement digests.
- [ ] Verified result sets, NULLs, duplicates, ordering, and business invariants.
- [ ] Tested concurrent reads/writes, rollbacks, retries, and deadlock behavior where relevant.
- [ ] Measured impact on other queries and write paths.
- [ ] Approved rollout only after correctness passes and performance meets thresholds.

## 19. Practice Exercises

### Exercise A — Build a Baseline

1. Create `tuning_orders` and load a dataset with multiple tenants, statuses, and dates.
2. Run the query using `DATE(created_at)`.
3. Capture EXPLAIN, query digest, p50/p95/p99, and completed throughput.
4. Record CPU, disk I/O, buffer pool counters, and error rates.
5. Save the baseline along with parameter distributions and concurrency.

### Exercise B — Tune One Predicate

1. Rewrite `DATE(created_at)` into a half-open range.
2. Create an appropriate composite index.
3. Run EXPLAIN and EXPLAIN ANALYZE.
4. Compare rows examined, actual time, and access paths.
5. Run benchmarks at the exact same concurrency and workload.

### Exercise C — Verify Correctness

1. Save baseline and candidate outputs into two temporary tables.
2. Compare row counts.
3. Use anti-joins and null-safe equality to find missing, extra, or changed rows.
4. Test start/end-of-day boundaries, differing tenants, differing statuses, and NULLs if allowed by schema.
5. Compare client-side ordering if ORDER BY is part of the contract.

### Exercise D — Measure CPU/I/O and Saturation

1. Run the workload at concurrency 1, 8, 16, and 32.
2. Record completed throughput, p95/p99, and error rates.
3. Record mysqld CPU, disk latency, Threads_running, and buffer pool read deltas.
4. Locate where throughput plateaus or latency climbs sharply.
5. Explain whether the bottleneck points toward CPU, storage, locks, or connection queuing.

### Exercise E — Evaluate Workload Mix

1. Benchmark SELECTs after adding the index.
2. Benchmark INSERT/UPDATE at the matching workload ratio.
3. Compare read latency, write throughput, bytes written, and index size.
4. Check whether any other query digests regressed.
5. Recommend keeping, adjusting, or dropping the index based on the total workload.

You complete this lesson when you can establish reproducible baselines, interpret latency percentiles and throughput units accurately, correlate host CPU/I/O with MySQL metrics, prove before/after result equivalence, and make rollout decisions grounded in both correctness and performance.

## 20. Principles to Remember

- Successful tuning must improve measurable targets while preserving business correctness.
- Measure p50/p95/p99 on the client side; averages cannot substitute for tail latency.
- Distinguish requests/s, QPS, TPS, and rows/s; always report offered load, completed throughput, and error rates.
- Measure across multiple concurrency levels to uncover saturation and lock contention.
- Performance Schema statement timers measure elapsed/wait time, not pure CPU time.
- Combine process/host CPU, disk latency/IOPS, memory, buffer pool, and MySQL wait counters.
- Keep datasets, parameter distributions, workload mix, warm-up, concurrency, and measurement windows identical when comparing.
- Use query digests to spot statements with high total time or rows examined; use client histograms for p95/p99.
- Status counters are cumulative; take before/after snapshots and compute deltas instead of resetting carelessly in production.
- Verify row sets, values, NULLs, duplicates, ordering, side effects, and transaction/concurrency invariants.
- Never infer correctness solely from counts/sums or a single benchmark run.
- Evaluate write amplification, storage, replica lag, and impact on other queries when adding indexes.
- Enforce performance/correctness gates before rollout and prepare a rollback plan.

When you measure latency, throughput, CPU/I/O, and correctness within a single controlled workflow, you can prove a SQL change genuinely improves the system. Before/after metrics become reproducible, explainable, and trustworthy enough to guide deployment decisions.
