# Representative Workload Testing, One-Factor Changes, and Regression Testing

A query running fast on a few hundred rows does not prove MySQL will respond well when data grows to millions of rows and many transactions execute concurrently. Measurement results are trustworthy only when the test workload reflects how the application actually accesses data, the environment is held steady, and each test run can be compared against a baseline.

This lesson explains how to construct a representative test workload, change one factor at a time in a controlled way, and re-run performance regression suites after modifying SQL, indexes, configuration, or transaction handling. The goal is finding repeatable improvements while preserving data correctness and application behavior.

## 1. Building a Representative Workload

A representative workload models the MySQL operations an application normally performs, along with their frequencies and execution conditions. Before picking a tool, answer these questions:

- **Which business flows generate queries?** For example: login, product search, order creation, status updates, and reporting.
- **What is the read/write ratio?** Distinguish `SELECT`, `INSERT`, `UPDATE`, `DELETE`, and multi-statement transactions.
- **Which queries are frequent or resource-heavy?** Collect digests, execution counts, total time, rows examined, and rows returned.
- **What does the data shape look like?** Use near-realistic scale, value distributions, filter selectivity, related record counts, and data skew. A column where most rows share one value behaves differently from a uniformly distributed column.
- **How does the application generate load?** Record concurrent connections, request rate, batch sizes, think times between operations, and transaction durations.
- **What is the cache state?** Distinguish cold runs right after startup or data loads from warm runs when the InnoDB Buffer Pool already holds most needed data pages.

A benchmark running a single `SELECT` repeatedly rarely represents an application mixing reads, writes, locks, and commits. Similarly, using a tiny table that fits completely in RAM can mask disk read latency when real data exceeds the Buffer Pool.

Build the workload in this order:

1. Extract business flows and queries from the application, sanitized query logs, or Performance Schema.
2. Group queries by pattern (digest), parameters, and operation type; determine each group's weight.
3. Generate test data matching the target environment's scale and distribution.
4. Reproduce transaction boundaries, concurrency levels, and application request pacing.
5. Verify that the workload produces valid business outcomes, not just high QPS.

You can use **sysbench** to create an initial OLTP baseline. For custom application workloads, write sysbench Lua scripts or use an appropriate load-replay tool. Canned sample scenarios cannot replace real access patterns.

## 2. Locking Down the Environment and Baseline

Before measuring, record factors that can skew results:

| Group | Information to Record |
|---|---|
| MySQL | Version, engine, effective configuration, plugins, and Performance Schema state |
| Host | CPU, RAM, storage type, filesystem, and I/O limits |
| Data | Size, row counts, schema, indexes, sample data, and initialization method |
| Application | Version, connection pool, worker count, and timeout settings |
| Network | Latency between app and MySQL, placement of load generator host |
| Scenario | Workload ID, seed, parameters, thread count, warm-up duration, and measurement duration |

Use the same MySQL version, dataset, configuration, load generator, and scenario across comparisons. If one factor must change, document it explicitly and treat it as a variable of the experiment. Never compare a warm-cache run against a freshly booted cold run unless comparing those two states is the primary goal.

The baseline is the measurement taken before any change. Run a dry test to verify the workload, let the system stabilize, and then execute multiple independent runs. Three or more runs are a useful starting point; increase run counts if variance is high. Alternating run order between old and new variants helps reduce bias from host thermal throttling, background jobs, or environmental drift.

Clearly separate:

- **Warm-up:** time for caches, connection pools, and the workload to stabilize; exclude from primary measurement data.
- **Measurement window:** duration over which results are collected after warm-up.
- **Cooldown/reset:** restoring data or resource state before the next run when write scenarios mutate data.

For write workloads, re-initialize data state or restore an identical snapshot before each run. If a later run has more rows, altered indexes, or different transaction state than the earlier run, it is no longer a like-for-like comparison.

## 3. Choosing Metrics to Track

Never conclude from QPS or TPS alone. High throughput can coincide with long wait times and rising error rates. Monitor these groups together:

| Metric Group | Meaning |
|---|---|
| QPS / TPS | Statements or transactions completed per second |
| Latency p50, p95, p99 | Median and tail response times; p95/p99 reveal the experience of slow requests |
| Errors / timeouts | SQL errors, deadlocks, timeouts, and rejected requests |
| CPU and RAM | CPU utilization, memory pressure, and Buffer Pool activity |
| Storage I/O | IOPS, throughput, read/write latency, and I/O wait time |
| InnoDB | Buffer Pool physical reads, row lock waits, redo activity, and checkpoint state |
| SQL | Rows examined vs. rows sent, full scans, temporary tables, and execution plans |
| Concurrency | `Threads_running`, connection count, lock waits, and transaction duration |

Measure latency at the application side to capture connection pool waits, network time, and app processing. Also measure inside MySQL to isolate server-side execution time. Having both measurements separates slow queries from requests waiting on pool acquisition or network transfer.

For cumulative counters in MySQL, capture snapshots before and after each run and compute the difference. Never compare totals accumulated since server startup directly across unequal observation windows. Always record timestamps and intervals for accurate interpretation.

## 4. Running a Repeatable Scenario

The example below uses sysbench's **oltp_read_write** workload to establish a benchmark in a test environment. The benchmark account should hold only the necessary privileges on the test schema.

Prepare data:

~~~bash
sysbench oltp_read_write --mysql-host=127.0.0.1 --mysql-port=3306 --mysql-user=bench --mysql-password='<PASSWORD>' --mysql-db=bench --tables=16 --table-size=100000 --threads=32 --time=300 --report-interval=10 --rand-type=pareto prepare
~~~

Run load:

~~~bash
sysbench oltp_read_write --mysql-host=127.0.0.1 --mysql-port=3306 --mysql-user=bench --mysql-password='<PASSWORD>' --mysql-db=bench --tables=16 --table-size=100000 --threads=32 --time=300 --report-interval=10 --rand-type=pareto run
~~~

After completing and saving results, you can clean up benchmark data:

~~~bash
sysbench oltp_read_write --mysql-host=127.0.0.1 --mysql-port=3306 --mysql-user=bench --mysql-password='<PASSWORD>' --mysql-db=bench --tables=16 --table-size=100000 --threads=32 --time=300 --report-interval=10 --rand-type=pareto cleanup
~~~

Replace connection info and parameters with your test environment configuration. Never put real passwords into documentation, logs, or shared command history; use your environment's secure secret injection mechanism. **`--threads`** simulates concurrent threads, **`--time`** sets duration, and **`--report-interval`** exposes variance during the run. You can test multiple distinct concurrency levels, such as low load, typical load, and observed peak load.

Sysbench output typically provides throughput, average and percentile latencies, and error counts. Save the full output and configuration for each run. For real applications, supplement with scenarios mirroring real query parameters and transaction boundaries; never extrapolate production capacity solely from one generic OLTP benchmark.

## 5. Observing Queries and MySQL Resources

Performance Schema helps locate time-consuming statement patterns. For example, the following query ranks digests by total execution time:

~~~sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR AS executions,
    ROUND(SUM_TIMER_WAIT / 1e12, 2) AS total_seconds,
    ROUND(AVG_TIMER_WAIT / 1e9, 2) AS avg_ms,
    SUM_ROWS_EXAMINED AS rows_examined,
    SUM_ROWS_SENT AS rows_sent
FROM performance_schema.events_statements_summary_by_digest
WHERE SCHEMA_NAME = 'appdb'
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 10;
~~~

Replace **appdb** with the schema under observation. Counters in summary tables typically accumulate since MySQL startup or the last statistics reset. When measuring a single test run, capture snapshots before and after and compute the difference. Verify Performance Schema and required consumers/instruments are enabled before relying on the figures.

If the **sys** schema is available, the **`sys.statement_analysis`** view offers a more readable summary:

~~~sql
SELECT
    query,
    exec_count,
    total_latency,
    avg_latency,
    rows_examined,
    rows_sent,
    full_scans
FROM sys.statement_analysis
ORDER BY total_latency DESC
LIMIT 10;
~~~

Pay attention to both total time and average time. A fast query executed millions of times can still consume the bulk of resources. Conversely, a rare query with very high average latency may still require attention depending on business needs and blast radius.

Track additional counters aligned with your hypothesis, such as **`Threads_running`**, **`Innodb_buffer_pool_reads`**, **`Innodb_buffer_pool_read_requests`**, **`Innodb_row_lock_waits`**, **`Innodb_row_lock_time`**, and **`Created_tmp_disk_tables`**. Compute deltas over the exact same time window as the benchmark. Pair MySQL metrics with OS CPU, RAM, and I/O to find real bottlenecks.

When inspecting the plan of a specific `SELECT`, use **`EXPLAIN`** to see how the optimizer intends to access tables. On MySQL 8.0.18 and later, **`EXPLAIN ANALYZE`** reports actual timings and row counts for each iterator:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, created_at
FROM orders
WHERE status = 'PENDING'
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC
LIMIT 50;
~~~

**`EXPLAIN ANALYZE`** executes the `SELECT` to collect real statistics. Run it in a test environment or controlled window with appropriately bounded queries. Compare estimated rows with actual rows, loop counts, and per-iterator timings. Large mismatches between estimates and reality can cause the optimizer to pick poor plans.

## 6. Changing One Factor at a Time and Testing Hypotheses

Each test run should have a specific hypothesis, one primary change, and predefined evaluation criteria. For example:

> Hypothesis: the query fetching pending orders reads too many rows due to a missing suitable index. Test change: add a composite index on `(status, created_at)`. Expected outcome: lower rows examined and query p95 latency without increasing write cost beyond acceptable thresholds.

An experimental cycle can proceed as follows:

1. Record the baseline and save execution plans for relevant queries or workloads.
2. State the hypothesis and specify the single variable to change—for example, one index, one SQL query, one configuration variable, or concurrency level.
3. Change only that variable in the test environment; record configurations before and after.
4. Run with the same dataset, workload, parameters, warm-up duration, and measurement window.
5. Collect chosen metrics, verify data correctness, and note side effects.
6. Repeat enough runs, compare against baseline, and decide whether to keep, adjust, or revert the change.

Never add an index, rewrite SQL, and raise `innodb_buffer_pool_size` all in one pass and credit the entire improvement to a single cause. Changing multiple variables simultaneously hides which factor drove the gain or caused side effects. If you suspect variables interact, measure each separately first, then design a deliberate combined experiment documenting every combination tested.

For instance, index **`(status, created_at)`** may fit when a query filters with equality on **`status`** and then filters or sorts by **`created_at`**. Verify with execution plans and real workloads. A new index consumes storage and adds work to `INSERT`/`UPDATE`/`DELETE`; thus, the benchmark must test both reads and writes. Record index creation time separately rather than mixing it with steady-state post-index query timings.

For configuration changes, verify effective runtime values via **`SHOW GLOBAL VARIABLES`** or direct variable queries rather than trusting an intended config file alone. Some changes require restarting MySQL or alter cache state. Document this explicitly and measure cold/warm states according to your objective.

## 7. Reading Results and Detecting Regressions

Compare runs using identical units, intervals, and calculations. A minimal results table may include:

| Metric | Baseline | After Change | Difference | Meets Criteria? |
|---|---:|---:|---:|---|
| TPS |  |  |  |  |
| Latency p95 |  |  |  |  |
| Latency p99 |  |  |  |  |
| Errors / timeouts |  |  |  |  |
| CPU avg / peak |  |  |  |  |
| Rows examined |  |  |  |  |
| Storage read latency |  |  |  |  |

Do not look solely at averages. p95 or p99 can worsen even while averages improve, especially when the system nears saturation or some transactions wait on locks. If increasing threads yields almost no throughput gain while latency surges, the system has likely hit a CPU, I/O, connection, or lock contention ceiling.

A change counts as an improvement when target metrics improve repeatably, guardrail metrics remain within agreed bounds, and data stays accurate. Set thresholds around SLOs and application traits rather than applying one universal percentage across all systems. If differences are smaller than run-to-run variance, run more iterations or reduce noise before concluding.

Classify outcomes to make clear decisions:

- **Improvement:** target improves consistently without violating guardrail criteria.
- **No clear difference:** difference falls within measurement noise or is too small to matter operationally.
- **Regression:** latency, throughput, errors, or resource usage breach allowed thresholds.
- **Invalid:** environment, data, workload, or cache state differed from planned conditions; must re-run.

## 8. Building a Performance Regression Suite

After editing SQL, adding indexes, changing schemas, tuning config, or modifying transaction logic, re-run the same test suite to catch regressions. A suite can be structured into three tiers:

1. **Smoke test:** confirms connectivity, core queries, and basic writes still function.
2. **Representative test:** runs a workload mimicking realistic read/write ratios, data, transactions, and concurrency; serves as the performance comparison basis.
3. **Stress or soak test:** ramps load safely or runs longer to uncover saturation points, resource leaks, and time-dependent issues.

The test suite must also validate business correctness. For write transactions, check row counts, constraints, final states, and consistency after commit/rollback. For concurrent workloads, watch deadlocks, lock waits, timeouts, and lock hold durations. When replicas exist, inspect replication lag under write loads and confirm replica read flows still meet data freshness requirements.

Save alongside every run:

- Application, schema, and MySQL versions.
- Dataset snapshot or generation method, seed, and data distribution.
- Effective MySQL configuration, connection pool configuration, and machine resources.
- Workload ID, parameters, thread count, warm-up time, and measurement duration.
- Throughput, latency percentiles, errors, and resource metrics.
- Execution plans for critical queries alongside the tested change.
- Conclusion, pass/fail criteria, and keep/revert decision.

In CI, run only small, stable workloads on every change if CI noise can be controlled. Run heavy benchmarks on dedicated environments on a schedule or before major releases. When a regression appears, archive results and reproduction conditions so developers can investigate reliably.

## 9. End-to-End Application Example

Suppose an admin screen lists pending orders. The query has high p95 latency and statistics show far more rows examined than rows returned.

- **Baseline:** save SQL, common parameters, `EXPLAIN` or `EXPLAIN ANALYZE`, p50/p95/p99, rows examined, throughput, and CPU/I/O load.
- **Hypothesis:** filter and sort predicates lack a suitable index.
- **Experiment:** on a data copy, add composite index `(status, created_at)`; do not alter SQL or server settings at the same time.
- **Re-measure:** run the exact same workload and parameters, checking the new plan, rows examined, and latency.
- **Check side effects:** run order-creation and order-update workloads to measure write overhead, index size, and impact on other queries.
- **Conclusion:** keep the index only if improvements are repeatable, meet latency thresholds, and keep write operations within SLO. If criteria fail, revert and test another hypothesis.

This example illustrates why optimizing a single query must be evaluated across the entire system workload. An index can speed up reads while slowing down writes; metrics from one screen alone never represent the whole service.

## 10. Pre-Publication Checklist

- [ ] Workload reflects real queries, read/write ratios, transactions, and concurrency.
- [ ] Dataset scale and distribution closely match the target environment.
- [ ] Environment, versions, configuration, and cache state are documented.
- [ ] Baseline includes multiple runs and a separate warm-up period.
- [ ] Throughput, latency percentiles, errors, and resources are measured over the same window.
- [ ] Each test run changes only the variable stated in the hypothesis.
- [ ] Results are verified for data correctness and read/write side effects.
- [ ] Regression suite is repeatable with identical datasets and parameters.
- [ ] Pass/fail thresholds are grounded in SLOs and measured variance.
- [ ] Results, configuration, workload, and decisions are archived for future comparison.

Representative load testing reveals what work MySQL is doing and how it handles load. Changing one factor at a time isolates the cause of improvements or regressions. Regression testing turns those measurements into a repeatable process after every SQL, index, transaction, or configuration change, keeping performance steady alongside data correctness.
