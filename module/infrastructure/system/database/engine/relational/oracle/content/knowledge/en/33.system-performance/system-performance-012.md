# Establishing a Performance Baseline and Before/After Change Testing

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** System Performance  
> **Objective:** Build a repeatable performance baseline; define workloads and metrics at system, service, session, SQL, and application levels; design controlled before/after change tests; distinguish latency, throughput, CPU, logical/physical I/O, waits, and errors; gather evidence with appropriate Oracle tools; evaluate results using distributions and variance; and deploy, monitor, and roll back on regressions.

## 1. What Is a Performance Baseline?

A performance baseline is a set of measurements describing how a system behaves over a defined time window under a defined workload. Baselines serve as the reference point for evaluating future changes: database upgrades, SQL edits, new indexes, statistics changes, parameter changes, data growth, application releases, or infrastructure changes.

A useful baseline should answer:

- How many transactions or requests does the system process per unit of time?
- How long do users wait on average and at high percentiles?
- How much CPU, logical reads, physical reads, and redo does the database consume?
- Where do sessions spend wait time: I/O, locks, concurrency, network, or CPU?
- Which SQL statements account for most DB time, CPU, or buffer gets?
- Does the workload fluctuate by hour, day, batch window, or tenant?
- After a change, which metrics improved and which suffered trade-offs?

A baseline is not a single number like "the query runs in 2 seconds." It is a contextualized measurement set: version, configuration, data, workload, concurrency, timeframe, environment, and collection method.

### 1.1. A Baseline Is Not an Absolute Performance Guarantee

A single fast run does not prove the system is always fast. Results can be skewed by:

- Whether the buffer cache is warm or cold.
- Storage latency at the time of measurement.
- Concurrent session counts.
- Background jobs and overlapping batches.
- Varying bind values and selectivity.
- Statistics or execution plan changes.
- Network behavior and client fetch speed.
- CPU scheduling, virtualization, or noisy neighbors.
- Data and index differences compared to production.

A baseline must document measurement conditions and representative scope. If production workloads have peak and off-peak hours, maintain separate baselines or segment by period.

## 2. Define Measurement Scope Before Running Tests

Before collecting metrics, define clearly what is being evaluated.

| Scope | Question to Answer | Example Metrics |
|---|---|---|
| System/database | How is the overall database consuming resources? | DB time, DB CPU, waits, I/O, redo |
| Service/application | What are users or services experiencing? | Request rate, latency, error rate |
| Workload/job | How long does a batch or business flow take? | Rows/sec, job duration, retry count |
| SQL/cursor | Which SQL statements consume resources? | Executions, elapsed time, CPU, buffer gets |
| Session | What is a group of sessions doing? | Wait events, module/action, blocking |
| Operation | Did a specific change improve a plan step? | E-Rows, A-Rows, Starts, Buffers, A-Time |

Never let a metric at one scope stand in for another scope. For instance, low SQL elapsed time does not guarantee fast API responses if the application spends long periods post-processing or fetching slowly. Conversely, high API latency may stem from network or application queues even when the database is idle.

### 2.1. Formulate the Test Question

Examples of strong questions:

- Does adding the new index reduce buffer gets on the order-lookup query?
- Does replacing `OFFSET` pagination with keyset pagination keep p95 latency stable on deep pages?
- Does changing batch size boost rows/sec, and how much does PGA grow?
- Does the database upgrade increase hard parses or physical reads?
- Does the statistics change improve the overall workload without regressing other critical SQL?

A question must specify the primary metric, success criteria, regression bounds, and affected SQL/jobs.

### 2.2. State a Hypothesis Before Changing Anything

Example:

> Hypothesis: a composite index on `CUSTOMER_ID, STATUS, CREATED_AT` will reduce logical reads for the query fetching the latest orders per customer.

Translate the hypothesis into measurable criteria:

- Target `SQL_ID` or SQL signature.
- Representative bind values.
- Buffer gets per execution.
- Elapsed time p50/p95.
- Rows returned.
- DML overhead introduced by the new index.
- Index size and additional redo generated.
- Impact on other queries touching the `ORDERS` table.

Measuring only read queries while ignoring `INSERT`/`UPDATE`/`DELETE` costs leads to conclusions that misrepresent the real workload.

## 3. Choosing a Representative Workload

A workload is the actual mix of activity the database must serve. A tiny benchmark running one simple `SELECT` rarely represents production.

Workload categories:

- OLTP: short transactions, many sessions, concurrent reads/writes.
- Reporting: queries reading many rows, joins, and aggregations.
- Batch: bulk periodic processing, potentially heavy redo and I/O.
- Mixed workload: OLTP overlapping with batch/reporting.
- Maintenance: statistics gathering, index maintenance, backups, purges.

A change can improve one category while degrading another. For example, a new index speeds up `SELECT` latency yet slows down writes and raises redo.

### 3.1. Selecting Representative Transactions by Weight

You can construct a workload mix table:

| Category | Request Share | Frequency | Criticality |
|---|---:|---:|---|
| Login and lookup | 35% | High | High |
| Order creation | 25% | High | Very high |
| Status updates | 20% | High | High |
| Daily reports | 10% | Hourly | Medium |
| Reconciliation batch | 10% | Scheduled | High |

Weights should come from real logs/telemetry, not guesswork. Beyond request share, account for business-critical transactions and explicit SLAs.

### 3.2. Bind Value Distribution

A SQL statement can run fast for rare bind values and slow for common ones. When assembling a test suite, include bind groups covering:

- Frequent values.
- Rare values.
- Boundary values.
- Large tenants and small tenants.
- Short and long date ranges.
- States exhibiting data skew.

Record bind data types and data distributions. Never compare two runs with wildly different bind selectivity and attribute the entire difference to a code change.

### 3.3. Data Scale

Test data should resemble production in:

- Total row count and block count.
- `NULL` ratios.
- Data skew and distinct value counts.
- LOB/JSON/XML sizes.
- Relationship depth and join fan-out ratios.
- Partition counts and per-partition row distribution.
- Indexes, constraints, triggers, and statistics.

A 10,000-row lab table cannot validate performance on a 500-million-row production table, especially when access paths and partition pruning differ.

## 4. Standardizing Before and After Conditions

To make comparisons meaningful, hold conditions as constant as possible.

| Factor | What to Hold Constant or Record |
|---|---|
| Oracle release | Version, RU/patch level |
| Configuration | SGA/PGA, parallel settings, optimizer parameters |
| Infrastructure | CPU, memory, storage, network, VM/container limits |
| Schema | DDL, indexes, constraints, partitioning |
| Data | Same snapshot or equivalent copy |
| Statistics | Record collection timestamp and statistics state |
| SQL | Identical text/logic except for the tested change |
| Binds | Identical data types and value distributions |
| Concurrency | Identical session count and request mix |
| Cache | Identical warm-up procedure or cold-cache policy |
| Client | Identical driver, fetch size, and result consumption |
| Background work | Record batches, backups, stats jobs, and maintenance |
| Measurement | Identical measurement window, tools, and units |

Holding everything constant is not always possible. When something differs, explicitly log the difference and evaluate its impact rather than pretending both runs are identical.

### 4.1. Same Data or Same Snapshot

Ideally, clone/refresh from the exact same snapshot for before and after runs. Testing directly against a constantly mutating environment introduces row-count or skew drift that corrupts conclusions.

For read-only tests, Flashback Query `AS OF SCN` can pin a snapshot if UNDO remains available and privileges allow. For write tests, use isolated data copies or reset fixtures between runs.

Never run destructive benchmarks in production just to regenerate test data.

### 4.2. Warm vs. Cold Cache

Cache state can skew results dramatically:

- Cold cache typically raises physical reads and storage latency.
- Warm cache cuts physical reads while still incurring logical buffer gets.
- The very first run after deployment behaves differently from repeated executions.

Pick an explicit policy:

- Compare warm-cache against warm-cache.
- Compare cold-cache against cold-cache only in controlled test environments.
- Or measure both scenarios separately.

Never flush the shared pool or buffer cache in production just to run a benchmark. Flushing disrupts other sessions and induces abnormal load spikes.

### 4.3. Concurrency and Load Shape

Measuring a single session reveals single-request latency, but says nothing about throughput under concurrent load.

Test across representative concurrency levels, e.g., 1, 5, 20, and 50 sessions depending on environment capacity. Record:

- Request rate.
- Active session count.
- Connection pool queue/wait time.
- Throughput.
- p50, p95, p99 latency.
- Error/timeout rate.
- CPU and wait profile.

Ramp concurrency gradually to locate the saturation point. Never test solely at light load.

## 5. Core Performance Metrics

### 5.1. Latency

Latency is the time for a request/transaction to complete.

Measure the distribution:

- p50: half of requests complete at or faster than this value.
- p90/p95: reflects requests slower than the majority.
- p99: exposes tail latency.
- Maximum: helpful for investigating extreme outliers, though highly sensitive to a single anomaly.

Averages hide tail latency. For instance, 99 requests at 50 ms and 1 request at 5 seconds yield a mild average, yet one user waited an eternity.

### 5.2. Throughput

Throughput is units of work completed per unit of time:

- Transactions/sec.
- Requests/sec.
- Rows/sec.
- Batch records/minute.
- Jobs/hour.

Define units clearly. One transaction may run many SQL statements; SQL executions/sec does not equal business transactions/sec.

### 5.3. CPU Time

CPU time reflects database CPU processing time. High CPU can come from:

- SQL processing excessive rows.
- CPU-heavy PL/SQL functions or expressions.
- Heavy parsing and optimization.
- Compression/encryption.
- Parallel execution.
- Concurrency driving CPU scheduling overhead.

Low CPU time paired with high elapsed time points to wait time; inspect wait events.

### 5.4. DB Time

DB time is the total time foreground database sessions spend on CPU and non-idle waits per Oracle's definition. It is widely used to gauge overall database load.

DB time can exceed wall-clock duration within the same window because multiple sessions run concurrently. Never divide DB time directly by the elapsed window and call it user latency.

### 5.5. Logical I/O and Physical I/O

- Buffer gets/logical reads: block accesses via the buffer cache.
- Physical reads: blocks read from storage into database caches per relevant statistics.
- Direct path reads: operations reading directly via direct path mechanisms.
- Writes: blocks or bytes written depending on the metric.

High logical reads can cause CPU burn and contention even when physical reads are low. High physical reads can inflate latency depending on storage throughput and latency.

### 5.6. Redo, Undo, and Commits

For write workloads, also measure:

- Redo size.
- Undo generation/usage.
- User commits.
- `log file sync` waits.
- Row lock waits.
- Index maintenance overhead.

A new index can cut `SELECT` buffers while raising redo and commit times because every DML statement must maintain the extra index.

### 5.7. Errors and Retries

A change is not a success if latency drops while errors or retries climb.

Measure:

- `ORA` errors.
- Application exceptions.
- Deadlocks.
- Timeouts.
- Connection pool waits/timeouts.
- Retry counts.
- Failed transactions.
- Partial batch failures.

## 6. System-Level Baselines with Dynamic Performance Views

Oracle provides `V$` views to observe current activity and cumulative statistics.

### 6.1. Database Version

~~~sql
SELECT banner
FROM v$version;
~~~

Record the exact version/RU, as optimizer behavior, features, and bug fixes vary across releases.

### 6.2. Database Time and CPU from System Statistics

Read system time model statistics:

~~~sql
SELECT name, value
FROM v$sys_time_model
WHERE name IN (
    'DB time',
    'DB CPU',
    'background elapsed time',
    'background cpu time'
)
ORDER BY name;
~~~

`V$SYS_TIME_MODEL` holds cumulative values since startup or reset, not automatic interval metrics. Capture start and end snapshots and compute deltas.

Time model values are typically in microseconds. Verify units in the Reference for your running release before converting.

### 6.3. System Statistics

~~~sql
SELECT name, value
FROM v$sysstat
WHERE name IN (
    'session logical reads',
    'physical reads',
    'physical writes',
    'redo size',
    'user commits',
    'execute count',
    'parse count (total)',
    'parse count (hard)'
)
ORDER BY name;
~~~

These are cumulative counters. Compute deltas between two checkpoints:

\[
\Delta metric = value_{after} - value_{before}
\]

If the instance restarts or counters reset between snapshots, deltas may turn negative or become incomparable. Record `startup_time` and snapshot timestamps.

### 6.4. Interval Load Profile

Example capturing two snapshots 5 minutes apart and computing deltas:

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| DB time | 10,000 s | 10,600 s | 600 s |
| DB CPU | 7,000 s | 7,350 s | 350 s |
| Logical reads | 8,000,000 | 8,600,000 | 600,000 |
| Physical reads | 500,000 | 520,000 | 20,000 |
| Redo size | 4 GB | 4.2 GB | 0.2 GB |

These numbers are illustrative examples only. A 5-minute window may span many sessions and workloads; never attribute the entire delta to one query when multiple activities overlap.

### 6.5. V$INSTANCE and Startup Time

~~~sql
SELECT instance_name,
       host_name,
       startup_time,
       status
FROM v$instance;
~~~

Record `startup_time` to detect restarts between snapshots. In RAC, each instance maintains its own counters; use `GV$` views and `INST_ID` when aggregating across the cluster.

## 7. Session- and Service-Level Baselines

### 7.1. Session Statistics

Join `V$SESSTAT` with `V$STATNAME` to view per-session counters:

~~~sql
SELECT s.sid,
       s.serial#,
       n.name,
       ss.value
FROM v$sesstat ss
JOIN v$statname n
  ON n.statistic# = ss.statistic#
JOIN v$session s
  ON s.sid = ss.sid
WHERE s.sid = SYS_CONTEXT('USERENV', 'SID')
  AND n.name IN (
      'session logical reads',
      'physical reads',
      'CPU used by this session',
      'redo size',
      'execute count',
      'parse count (total)'
  )
ORDER BY n.name;
~~~

Capturing before/after snapshots for a test session isolates its work from unrelated database activity. With connection pools, sessions get reused; correlate the exact request using `MODULE`/`ACTION` and timestamps.

### 7.2. Tagging Module/Action

Applications or PL/SQL can tag module/action using `DBMS_APPLICATION_INFO`:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_API',
        action_name => 'SEARCH_RECENT_ORDERS'
    );
END;
/
~~~

When finished:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => NULL,
        action_name => NULL
    );
END;
/
~~~

Inspect via `V$SESSION`:

~~~sql
SELECT sid,
       serial#,
       username,
       service_name,
       module,
       action,
       client_identifier,
       sql_id,
       event,
       state
FROM v$session
WHERE module = 'ORDER_API';
~~~

Module/action lets DBAs group sessions by application feature. With pools, ensure context is cleared when returning connections so subsequent requests do not inherit previous labels.

### 7.3. Client Identifier

Non-sensitive tenant or user context can be attached via `DBMS_SESSION.SET_IDENTIFIER` per organizational policy. Never place passwords, tokens, sensitive personal data, or confidential payloads in module/action/client identifier.

## 8. SQL- and Cursor-Level Baselines

`V$SQL` stores statistics for child cursors in the shared pool.

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       rows_processed,
       elapsed_time,
       cpu_time,
       buffer_gets,
       disk_reads,
       direct_reads,
       direct_writes,
       last_active_time
FROM v$sql
WHERE parsing_schema_name = 'APP'
ORDER BY elapsed_time DESC
FETCH FIRST 30 ROWS ONLY;
~~~

Several time fields in `V$SQL` are stored in microseconds. Counters are typically cumulative for the child cursor; do not treat them as metrics for the last execution alone.

### 8.1. Computing Per-Execution Metrics

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       ROUND(elapsed_time / 1e6, 3) AS total_elapsed_seconds,
       ROUND(elapsed_time / 1e6 / NULLIF(executions, 0), 4)
           AS avg_elapsed_seconds,
       ROUND(cpu_time / 1e6 / NULLIF(executions, 0), 4)
           AS avg_cpu_seconds,
       ROUND(buffer_gets / NULLIF(executions, 0), 1)
           AS avg_buffer_gets,
       ROUND(disk_reads / NULLIF(executions, 0), 1)
           AS avg_disk_reads
FROM v$sql
WHERE parsing_schema_name = 'APP'
  AND executions > 0
ORDER BY elapsed_time DESC;
~~~

Averages can hide outliers and differing bind values. Use them to screen resource-intensive SQL, not as a substitute for per-execution p95/p99.

### 8.2. SQL_ID and PLAN_HASH_VALUE

Record `SQL_ID`, child number, and plan hash value before and after. One `SQL_ID` can have multiple child cursors and differing plans. A different plan hash does not automatically mean regression; measure runtime behavior.

Conversely, an unchanged plan hash does not guarantee unchanged performance: data volume, caching, concurrency, I/O, and bind distributions may have shifted.

### 8.3. V$SQLSTATS

`V$SQLSTATS` provides aggregated metrics by `SQL_ID` with different retention and metadata query performance than `V$SQL`. Use it to screen SQL workloads while remembering its counters remain cumulative statistics.

## 9. Runtime Execution Plans and Row-Source Statistics

To pinpoint expensive operations, gather runtime plan statistics.

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       customer_id,
       total_amount
FROM orders
WHERE status = :p_status
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 50 ROWS ONLY;
~~~

After fetching results:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

Compare:

- `E-Rows`: estimated rows.
- `A-Rows`: actual rows.
- `Starts`: times the operation started.
- `Buffers`: logical buffer gets.
- `Reads`: physical reads.
- `A-Time`: recorded row-source time.

When `Starts` exceeds 1, factor in `A-Rows/Starts` before comparing with `E-Rows`. Do not mechanically sum `Buffers` or `A-Time` across all plan lines, as parent operations roll up child work.

### 9.1. Recording Actual Rows

`A-Rows` requires runtime statistics. `EXPLAIN PLAN` provides estimates only and does not execute SQL. `GATHER_PLAN_STATISTICS` or `STATISTICS_LEVEL = ALL` in a test session collects runtime data.

For `SELECT` statements, fetch all rows if the goal is measuring full execution. A client fetching 10 rows vs. fetching all rows represents two distinct workloads.

## 10. Wait Events: Knowing What the Database Is Waiting On

When elapsed time increases without a matching rise in CPU, inspect wait events.

Common categories:

| Wait Class | Example | Investigation Direction |
|---|---|---|
| User I/O | `db file sequential read`, `db file scattered read` | Index/table I/O, storage latency |
| Commit | `log file sync` | Commit frequency, redo log latency |
| Concurrency | `buffer busy waits`, `enq` waits | Hot blocks, contention, locking |
| Application | `enq: TX - row lock contention` | Row-lock-holding transactions, update conflicts |
| Network | `SQL*Net message to/from client` | Client fetches, network, app processing |
| Configuration | `log buffer space`, `free buffer waits` | Redo/buffer pressure and configuration |
| CPU | Not a specific wait event | CPU saturation, run queue, SQL CPU |

Exact wait names and relevance depend on workload and release. Never conclude solely from the top wait event: a wait with high total time may be idle or normal for the application.

### 10.1. V$SESSION

~~~sql
SELECT sid,
       serial#,
       username,
       sql_id,
       event,
       wait_class,
       state,
       seconds_in_wait,
       blocking_session,
       module,
       action
FROM v$session
WHERE type = 'USER'
  AND status = 'ACTIVE'
ORDER BY seconds_in_wait DESC;
~~~

`V$SESSION` is a current-state snapshot, not a complete history. Short queries can finish between observations.

### 10.2. V$SYSTEM_EVENT and V$SESSION_EVENT

Event statistics views typically contain cumulative counters. Capture before/after snapshots to compute deltas. Separate foreground/background, idle/non-idle, and distinct workloads within the window.

Never sum all wait events and label the sum as user latency. Multiple sessions wait concurrently, so total wait time can exceed wall-clock time.

### 10.3. Blocking Sessions and Row Locks

If requests are blocked:

~~~sql
SELECT sid,
       serial#,
       blocking_session,
       event,
       wait_class,
       sql_id,
       module,
       action
FROM v$session
WHERE blocking_session IS NOT NULL;
~~~

Identify the lock-holding session, active SQL, and transaction age. Never kill a session from a single snapshot without verifying the owner, transaction, and business impact.

## 11. Measuring Workloads at the Application Tier

Database metrics do not replace application metrics.

Record:

- Request rate per endpoint.
- p50/p95/p99 latency.
- Error rates and timeouts.
- Connection pool wait time.
- Active/idle connection counts.
- Queue wait times.
- Database call time vs. non-database processing time.
- Payload sizes and row counts returned.
- Retry counts.

For example, an API may exhibit 2-second latency while SQL takes only 100 ms; the rest may come from networking, serialization, downstream service calls, or waiting on the connection pool.

### 11.1. Correlation IDs and Tracing

Attach request IDs at the application tier and propagate relevant context into the database session. Use module/action/client identifier to link database activity to endpoints or jobs.

Never embed secrets inside SQL comments or application contexts. Choose non-sensitive identifiers and limit telemetry retention.

### 11.2. Measuring Fetch Behavior

For multi-row queries, database execution time may be tiny while client fetching of the entire result set takes long. Record:

- Rows returned.
- Driver fetch size.
- Round-trip counts.
- Payload size.
- Time to first row.
- Time to last row.

These metrics are critical for reporting APIs and paginated screens.

## 12. Oracle Telemetry Collection Tools

### 12.1. DBMS_XPLAN

Used to inspect estimated and actual execution plans when runtime statistics are available:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        'SQL_ID_HERE',
        0,
        'ALLSTATS LAST +PEEKED_BINDS +PREDICATE'
    )
);
~~~

`PEEKED_BINDS` shows bind values peeked at parse time when available and permitted. Be careful not to leak sensitive bind data into shared reports.

### 12.2. SQL Trace and TKPROF

SQL Trace captures parse, execute, fetch, CPU, elapsed time, logical/physical I/O, and wait information within the enabled scope. TKPROF formats trace files into readable reports.

Enable tracing for the current session in a test environment:

~~~sql
ALTER SESSION SET sql_trace = TRUE;
~~~

Disable:

~~~sql
ALTER SESSION SET sql_trace = FALSE;
~~~

For finer control, `DBMS_MONITOR` provides tracing APIs by session/client/service/module as appropriate. Weigh trace file size and overhead; never enable unbounded broad tracing in production.

### 12.3. AWR and ASH

Automatic Workload Repository (AWR) stores workload snapshots and rich statistics for time-based comparisons. Active Session History (ASH) samples session activity to aid wait, SQL, and blocking analysis.

AWR/ASH and related features require Oracle Diagnostics Pack/Tuning Pack licensing per product terms. Before using them in production, confirm license entitlements and organizational policy. Do not assume dictionary view access equals license rights.

Without appropriate licenses, rely on dynamic performance views, SQL Trace/TKPROF, application telemetry, and authorized snapshot/delta scripts.

### 12.4. SQL Monitor

Real-Time SQL Monitoring observes individual executions, especially long-running or parallel SQL. SQL Monitor carries corresponding licensing requirements; verify before using.

### 12.5. OS Metrics

Correlate Oracle performance with the operating system:

- CPU utilization and run queue.
- Memory pressure, paging/swapping.
- Disk latency, IOPS, and throughput.
- Network throughput/latency.
- VM/container CPU throttling.
- Storage queue depth.

The database may report rising physical reads because storage is slow, while the real root cause lies in infrastructure. Synchronize timestamps between OS telemetry and database snapshots.

## 13. Designing Before/After Tests

A rigorous test includes a baseline, a single isolated change, measured outcomes, and clear decision criteria.

### 13.1. Preparation

Document:

- Objective and hypothesis.
- Affected SQL/jobs/APIs.
- `SQL_ID`/plan hash if known.
- Data and bind values.
- Schema/indexes/statistics.
- Oracle version and configuration.
- Concurrency and workload mix.
- Primary metrics and guardrail metrics.
- Acceptable regression thresholds.
- Exact restoration steps.

### 13.2. Running the Pre-Change Baseline

1. Prepare production-equivalent data.
2. Verify statistics and execution plans.
3. Warm up per defined procedure.
4. Execute the workload at target concurrency.
5. Collect both application and database metrics.
6. Record p50/p95/p99, throughput, errors, CPU, I/O, waits, and redo.
7. Repeat enough times to observe variance.

### 13.3. Changing One Factor

For example, create one new index, update SQL, or adjust batch size. Record exact DDL/config/code versions and timestamps. Avoid changing indexes, statistics, optimizer parameters, and application code simultaneously if you want to isolate what drove the improvement.

If multiple changes are required to reach the goal, break them into individually measurable steps or explicitly note that impacts cannot be separated.

### 13.4. Running the Identical Workload Post-Change

Hold constant:

- Same data snapshot/fixture.
- Same bind distribution.
- Same request mix.
- Same concurrency.
- Same warm-up duration.
- Same run duration and fetch behavior.
- Same measurement tooling.

Re-collect the exact same metric set. If environment or workload shifted, document it clearly and avoid direct unadjusted comparisons.

### 13.5. Interleaving Runs When Possible

In a stable test environment, interleave baseline and candidate runs (`A/B/A/B`) to minimize time-drift bias. Reset state appropriately between runs and keep the same data snapshot.

Running `A` once followed by `B` once risks mistaking background load drift or cache warming for a candidate improvement.

## 14. Evaluating Results Using Distributions

Never draw conclusions from a single execution. Run multiple iterations and compare distributions.

Example:

| Metric | Baseline | Candidate | Assessment |
|---|---:|---:|---|
| p50 latency | 80 ms | 65 ms | Improved |
| p95 latency | 240 ms | 170 ms | Clearly improved |
| p99 latency | 900 ms | 1,100 ms | Tail regression |
| Throughput | 1,000 req/s | 1,080 req/s | Increased |
| DB CPU | 70% | 78% | Higher CPU burn |
| Buffer gets/req | 12,000 | 7,000 | Reduced |
| Redo/req | 8 KB | 12 KB | Increased |
| Error rate | 0.1% | 0.1% | Unchanged |

Numbers are illustrative. A candidate may improve p50/p95 while worsening p99; weigh against SLAs and tail-latency impact.

### 14.1. Improvement Percentage

For lower-is-better metrics, percentage reduction:

\[
\text{Improvement \%} =
\frac{\text{Baseline} - \text{Candidate}}
{\text{Baseline}} \times 100
\]

For example, p95 drops from 200 ms to 160 ms:

\[
\frac{200 - 160}{200} \times 100 = 20\%
\]

For higher-is-better throughput:

\[
\text{Throughput Gain \%} =
\frac{\text{Candidate} - \text{Baseline}}
{\text{Baseline}} \times 100
\]

Never apply one "improvement" formula across metrics with opposite optimization directions without clarifying signs.

### 14.2. Use Percentiles Rather Than Averages Alone

p50 reflects the typical experience; p95/p99 expose slow requests. Averages summarize overall volume, yet are easily skewed by outliers or mask tail issues.

Use consistent percentile calculation methods and sample sizes. With small samples, p99 is noisy; increase request counts or extend the measurement window.

### 14.3. Variance and Confidence

When two results differ by only a few percent, natural run-to-run variance may exceed the apparent gain. Record:

- Iteration counts.
- Requests per iteration.
- Median and percentiles.
- Min/max or standard deviation where appropriate.
- Load and cache conditions.
- Run-to-run spread.

Never claim a 2% improvement when runs fluctuate by 10%. When statistical rigor is needed, apply analytical methods suited to latency distributions rather than comparing single means.

### 14.4. Normalize by Unit of Work

When throughput differs, total CPU or total buffers may rise simply because the candidate processed more requests.

Also compare:

- CPU per transaction.
- Buffer gets per request.
- Redo per row.
- Physical reads per report.
- Elapsed time per batch.
- Errors per 10,000 requests.

Normalized metrics separate per-unit efficiency from total throughput changes.

## 15. Evaluating Trade-Offs and Regressions

A single change rarely improves every metric simultaneously.

Examples:

- A new index cuts `SELECT` latency yet increases DML latency and redo.
- Parallelism boosts throughput yet raises CPU and memory pressure.
- Larger batches increase rows/sec yet raise PGA usage and transaction duration.
- Compression saves storage/I/O yet increases CPU.
- Caching raises hit rates yet expands memory footprint.
- SQL rewrites cut buffer gets yet increase parse complexity.

Evaluate against business objectives and SLOs rather than optimizing a single metric in isolation.

### 15.1. Defining Guardrails

Example guardrails:

- p95 API latency increases by no more than 5%.
- p99 stays within SLA.
- Error rate does not increase.
- Peak CPU stays below operational limits.
- DML throughput drops by no more than 3%.
- Redo volume stays within log/storage capacity.
- Batches complete before deadline.
- Zero new deadlocks or timeouts occur.

Thresholds should be agreed upon by product and DBA teams per workload. No universal percentage threshold fits every system.

### 15.2. Regressions in Other SQL

A new index can cause the optimizer to pick different plans for other SQL statements. After schema or statistics changes, inspect top SQL by elapsed time, CPU, and buffer gets—not solely the target SQL.

If SQL Plan Management, SQL Profiles, or baselines are active, record their status and how they constrain plans. Never drop baselines or profiles during benchmarks without an explicit purpose.

## 16. Planning Rollout and Rollback

Before deploying to production, define how to revert.

| Change Type | Rollback Plan to Prepare |
|---|---|
| SQL/application release | Rollback artifact or feature flag |
| New index | Planned `DROP`/`INVISIBLE` index; check dependencies |
| Statistics | Export stats, pending stats, stats history/restore |
| Parameters | Record old values, scope, and persistence |
| Partition operations | Verify data and index recoverability |
| Schema migrations | Tested rollback or forward-fix script |
| Batch/job config | Restore config and checkpoint/retry state |

Rolling back code does not automatically undo written data. Rolling back statistics does not undo DML. Dropping an index does not reverse business state changes. Each change category demands its own recovery plan.

### 16.1. Canary or Staged Rollout

Where supported by the application, roll out the candidate to a subset of traffic/tenants first. Monitor latency, errors, DB CPU, SQL plans, and resource usage. Ramp up gradually as guardrails hold.

Avoid canary rollouts if both groups contend on shared resources in ways that obscure results, or if traffic/data profiles are non-comparable; in those cases, design dedicated isolated tests.

### 16.2. Stop Conditions

Halt rollout immediately if:

- Error rate breaches threshold.
- p95/p99 violates guardrails.
- DB CPU or I/O nears saturation.
- Lock waits/deadlocks spike sharply.
- Connection pool timeouts rise.
- Batches miss completion windows.
- Data correctness or transaction semantics break.

Upon halting, preserve metrics, `SQL_ID`, plan hashes, timestamps, and deployment versions for root-cause analysis.

## 17. Practical Runbook: Baselining a Critical SQL Statement

### Step 1 — Identify the SQL

Record `SQL_ID`, child number, plan hash, bind data types, and query purpose.

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       last_active_time,
       parsing_schema_name
FROM v$sql
WHERE sql_id = 'SQL_ID_HERE';
~~~

### Step 2 — Capture Runtime Plan

Run the statement with `GATHER_PLAN_STATISTICS` in a test session, fetch all rows, then run:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        'SQL_ID_HERE',
        0,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

### Step 3 — Capture Session Statistics

Query `V$SESSTAT`/`V$STATNAME` before and after execution. Compute deltas for logical reads, physical reads, `CPU used by this session`, `redo size`, and `execute count`.

### Step 4 — Measure at the Application Tier

Record start/end timestamps, row counts, fetch duration, p50/p95/p99, request IDs, and error codes. Synchronize clocks between app and database hosts.

### Step 5 — Run Multiple Iterations

Follow the defined warm-up policy, then repeat multiple iterations with representative bind values. Never record only the fastest run.

### Step 6 — Test the Candidate

Change exactly one factor and re-run using the identical protocol. Record the new plan hash and runtime stats.

### Step 7 — Compare

Compare latency distributions, throughput, buffers/request, CPU/request, reads, redo, waits, and errors. Document both gains and regressions.

### Step 8 — Archive Evidence

Save:

- Sanitized SQL text with sensitive data removed.
- `SQL_ID`, child number, plan hash.
- DB version/RU and test environment details.
- DDL/index/statistics changes.
- Bind profile.
- Workload concurrency and duration.
- Before/after metrics.
- Conclusions and tested rollback commands.

## 18. Sample SQL Queries for Snapshotting Metrics

### 18.1. System Counters

~~~sql
SELECT SYSTIMESTAMP AS captured_at,
       name,
       value
FROM v$sysstat
WHERE name IN (
    'session logical reads',
    'physical reads',
    'physical writes',
    'redo size',
    'user commits',
    'execute count',
    'parse count (total)',
    'parse count (hard)'
)
ORDER BY name;
~~~

Save results at two timestamps on the same instance and compute deltas externally or in a lab table.

### 18.2. Time Model

~~~sql
SELECT SYSTIMESTAMP AS captured_at,
       stat_name,
       value
FROM v$sys_time_model
WHERE stat_name IN ('DB time', 'DB CPU')
ORDER BY stat_name;
~~~

Time model values are cumulative. In RAC, use `GV$SYS_TIME_MODEL` and group by `INST_ID`.

### 18.3. Active Sessions

~~~sql
SELECT sid,
       serial#,
       username,
       sql_id,
       event,
       wait_class,
       state,
       module,
       action,
       client_identifier
FROM v$session
WHERE type = 'USER'
  AND status = 'ACTIVE';
~~~

This is a point-in-time snapshot; it does not replace sampled activity history.

### 18.4. Top SQL by Buffer Gets

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       buffer_gets,
       ROUND(buffer_gets / NULLIF(executions, 0), 1)
           AS buffers_per_exec,
       elapsed_time,
       cpu_time
FROM v$sql
WHERE executions > 0
ORDER BY buffer_gets DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Top SQL by total buffer gets surfaces high total-resource consumers. To find SQL inefficient per execution, sort by buffers per execution while filtering out tiny execution counts and inspecting rows returned.

## 19. Common Benchmarking Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Running each option only once | Results skewed by random cache/load noise | Warm up and repeat multiple iterations |
| Comparing two different datasets | Differences reflect data, not just the change | Use the same snapshot or fixture |
| Varying bind values | Selectivity and plans may diverge | Use identical bind profiles |
| Measuring averages only | Hides tail latency | Track p50/p95/p99 |
| Measuring `SELECT` only | Ignores write and redo penalties | Test representative workload mix |
| Measuring only one SQL statement | Misses regressions in other SQL | Monitor top workload statements |
| Looking only at cost/plan hash | Misses actual runtime behavior | Measure actual rows, buffers, and elapsed time |
| Reading cumulative `V$SQL` as one execution | Misattributes time/I/O to single runs | Use deltas, tracing, or SQL Monitor |
| Failing to fetch all rows | Compares mismatched workloads | Match fetch behavior |
| Flushing production caches to benchmark | Disrupts other workloads | Use isolated test environments and fixed cache policy |
| Increasing concurrency uncontrollably | Creates noise and saturation | Use controlled load profiles |
| Ignoring errors/retries | Performance looks fast while reliability drops | Verify correctness and error rates |
| Ignoring licensing | Uses unlicensed pack features | Verify entitlements before AWR/ASH/Monitor |
| Lacking a rollback plan | Hard to recover upon regression | Prepare and test rollback in lab first |

## 20. Before/After Change Checklist

### Before Change

- [ ] Defined test question and hypothesis.
- [ ] Selected representative workload and target SQL/jobs/APIs.
- [ ] Recorded Oracle version, RU, configuration, and infrastructure.
- [ ] Recorded schema, indexes, partitions, and statistics.
- [ ] Prepared representative data and bind values.
- [ ] Locked concurrency, warm-up, duration, and fetch behavior.
- [ ] Recorded baseline p50/p95/p99 latency and throughput.
- [ ] Recorded CPU, DB time, buffers, physical reads, redo, and waits.
- [ ] Recorded error rates, timeouts, retries, and correctness checks.
- [ ] Defined primary metrics, guardrails, and stop conditions.
- [ ] Prepared rollback scripts and data/config restoration procedures.

### After Change

- [ ] Executed identical workload and protocol.
- [ ] Repeated sufficient iterations; did not cherry-pick the best run.
- [ ] Compared percentiles, throughput, and normalized metrics.
- [ ] Compared `SQL_ID`/child/plan hash and runtime plans.
- [ ] Checked other SQL for regressions.
- [ ] Evaluated CPU, I/O, redo, waits, and connection pools.
- [ ] Verified correctness, errors, and retries stayed within bounds.
- [ ] Archived evidence, changes, and conclusions.
- [ ] Rolled out gradually where feasible.
- [ ] Monitored production post-deploy and rolled back if guardrails breached.

## 21. Core Takeaways

- A performance baseline is a contextualized measurement set, not a single latency number.
- Workload, data, bind values, concurrency, cache state, and client fetch behavior must be controlled or documented.
- Measure both latency distribution and throughput; p95/p99 usually matter more than averages for user experience.
- DB time sums foreground session time and can exceed the elapsed window due to concurrency.
- Buffer gets represent logical I/O; physical reads and storage latency are another piece of the picture.
- Measure CPU, redo, undo, commits, waits, errors, and retries alongside SQL latency.
- `V$SYSSTAT`, `V$SYS_TIME_MODEL`, `V$SESSTAT`, and `V$SQL` hold cumulative counters; take before/after snapshots and compute deltas.
- `V$SQL` metrics are not automatically the last execution's figures; a child cursor can serve many sessions.
- `DBMS_XPLAN` with `GATHER_PLAN_STATISTICS` compares `E-Rows`, `A-Rows`, `Starts`, `Buffers`, and `A-Time`.
- SQL Trace/TKPROF supports detailed parse/execute/fetch and wait analysis within traced scopes.
- AWR, ASH, SQL Monitor, and certain tuning features require licensing; verify entitlements before use.
- `DBMS_APPLICATION_INFO` tags module/action to tie database work to application features.
- Test changes against matching workloads, data snapshots, bind profiles, concurrency, and measurement methods.
- Run multiple iterations and compare distributions; never conclude from one run or differences smaller than natural variance.
- Normalize metrics per request/transaction/row to separate efficiency from throughput changes.
- Weigh trade-offs across reads, writes, CPU, memory, I/O, redo, and tail latency.
- Prepare guardrails, staged rollouts, stop conditions, and rollback plans before deploying.
- Rolling back statistics, code, schema, and data are distinct tasks; plan each change type separately.

### Oracle Reference Documentation

- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/) — Performance methodology, wait events, statistics, and tuning workflow.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — `V$SYSSTAT`, `V$SYS_TIME_MODEL`, `V$SESSTAT`, `V$SQL`, `V$SESSION`, and dynamic performance views.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_APPLICATION_INFO](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_APPLICATION_INFO.html) — `MODULE`, `ACTION`, and application instrumentation.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html) — `DISPLAY_CURSOR` and runtime plan statistics.
- [Oracle Database Performance Tuning Guide — SQL Trace and TKPROF](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/) — SQL trace collection and report interpretation.
- [Oracle Database Licensing Information User Manual](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/) — Diagnostics Pack and Tuning Pack feature licensing.

`V$` view columns, instrumentation APIs, SQL Monitor behavior, and performance features can vary by Oracle release and license. Confirm the deployed version, privileges, and entitlements; test with a representative workload and preserve a rollback path before modifying production.
