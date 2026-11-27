# Measuring Latency, Throughput, CPU/I/O, and Correctness After Every Change in Oracle

SQL tuning does not end when a statement runs faster once on a developer's machine. A change is only valuable when it improves a real workload under comparable conditions, introduces no unexpected resource overhead, and still returns accurate results. Therefore, every change to SQL, indexes, schema, statistics, or configuration must be evaluated using a repeatable measurement process.

In Oracle Database, examine four outcome categories simultaneously:

- **Latency:** how long one request or execution takes; track both median and high percentiles such as p95/p99.
- **Throughput:** how many requests, transactions, or rows per second the system completes over an interval.
- **Resources (CPU/I/O):** CPU consumption, logical reads, physical reads, bytes read/written, redo, wait times, and contention.
- **Correctness:** output data, row counts, business rules, transaction behavior, and concurrency safety remain intact after the change.

A SQL statement with a lower elapsed time in a single isolated run is not automatically better. It might burn more CPU, drive more I/O, drop throughput as concurrency rises, or return wrong results on an edge case. Proper measurement requires a representative workload, a baseline, multiple iterations, identical data and environment conditions, and independent verification of correctness alongside performance.

This lesson belongs to the **SQL Tuning** topic of *Database Engine Relational Oracle*. It focuses on:

- Designing repeatable baselines and A/B experiments.
- Measuring latency, throughput, and percentiles.
- Measuring CPU, logical/physical I/O, redo, and wait events.
- Instrumenting SQL with SQL IDs, module/action, and bind values.
- Using `V$SQL`, `DBMS_XPLAN`, SQL Trace/TKPROF, and monitoring tools.
- Controlling warm/cold cache state, concurrency, bind peeking, and workloads.
- Verifying results using row counts, `MINUS`, checksums, and business rules.
- Evaluating transactions, errors, regressions, and trade-offs after each change.
- A hands-on lab measuring a query before and after adding an index and verifying correctness.

## 1. Why measure both performance and correctness?

SQL tuning changes how the database accesses or processes data. Common changes include:

- Rewriting predicates or joins.
- Adding, dropping, or altering indexes.
- Changing partitioning or how partitions are queried.
- Refreshing optimizer statistics/histograms.
- Using bind variables, hints, or SQL Plan Management.
- Changing pagination, aggregation, or batching strategies.
- Changing transaction scope, isolation, or locking.

Every change can affect multiple dimensions. For example, adding an index makes a `SELECT` faster while making `INSERT`/`UPDATE`/`DELETE` pay extra index maintenance overhead. A query returning fewer rows faster might slow the overall workload due to increased random I/O. A rewrite using `DISTINCT` or turning an outer join into an inner join might run quickly while silently dropping valid rows.

Therefore, concluding "tuning succeeded" requires answering:

1. Are business results identical before and after?
2. Did latency improve across a representative workload?
3. Did throughput increase, or at least not degrade, at target concurrency?
4. How did CPU, logical reads, physical I/O, redo, and waits change?
5. Were any regressions introduced for other queries, other bind values, or write operations?
6. Are results stable across repeated runs and cache/plan shifts?

### An example of a false conclusion

Suppose version A takes 120 ms once and version B takes 70 ms. If B reads 4x as many blocks, uses double the CPU, and under 50 concurrent sessions pushes p99 from 300 ms to 2 seconds, B can degrade the system despite a faster single run.

Conversely, a change that moves single-run latency from 70 ms to 80 ms while cutting logical reads by 80%, lowering CPU, and boosting throughput under heavy load may be the better choice.

## 2. Establishing a baseline before making changes

A baseline is the initial set of measurements used for comparison with later versions. Without a baseline, you cannot tell whether a change helped or merely coincided with system noise.

### Recording execution context

Before running measurements, record:

- Database version, edition, instance, and service.
- Relevant schema, objects, partitions, and data sizes.
- Key optimizer parameters and optimizer statistics timestamps.
- SQL text, SQL ID, plan hash value, child cursor, and bind values.
- Module/action/client identifier if set.
- Concurrent session count, read/write mix, and request distribution.
- Cache state, run timestamp, maintenance/background jobs, and ambient load.
- Specific code, index, statistics, or configuration change under evaluation.

Without recording bind values and plan hashes, two measurements might actually be executing different plans or selectivities.

### Choosing a representative workload

A representative workload should cover:

- Frequent queries and business-critical queries.
- Common, rare, and varying-selectivity bind values.
- Small and large result set sizes.
- Low-load and peak-load windows if traffic varies by hour.
- Both read paths and write paths if the change can affect both.
- Multi-step transactions and rollback/error cases.

Do not cherry-pick one easy-to-tune SQL statement. An index change can speed up the target query while slowing many other DML statements on the same table.

### Keeping before/after conditions equivalent

For a fair comparison:

- Use the same dataset or equivalent data snapshot.
- Use the same bind values and bind data types.
- Use the same iteration count and concurrency.
- Use the same warm-up duration.
- Do not run A during off-peak hours and B during peak hours.
- Document warm/cold cache state and never mix the two types of measurements.
- Keep database/hardware configuration consistent or explicitly note differences.

If all conditions cannot be held identical, collect enough samples and document which variables shifted.

### Recording the baseline in a results table

A compact table can start like this:

| Version | Bind case | Concurrency | Runs | Median | p95 | p99 | Throughput | CPU | Buffer gets | Physical reads |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | common | 1 | 100 | ... | ... | ... | ... | ... | ... | ... |
| A | common | 20 | 500 | ... | ... | ... | ... | ... | ... | ... |
| A | low selectivity | 20 | 500 | ... | ... | ... | ... | ... | ... | ... |

Specify clear units, such as ms, requests/s, CPU seconds, buffer gets/request, and bytes/request. Do not collapse multi-run metrics into a single number without a distribution.

## 3. Measuring latency

Latency is the time from when an operation starts until it finishes according to the chosen measurement boundary. That boundary could be:

- One SQL execution inside the database.
- One transaction spanning multiple SQL statements.
- One application request from receipt to response.
- One batch covering many rows or tasks.

Measurements with different boundaries cannot be compared directly.

### Elapsed time

Elapsed time is wall-clock time, encompassing both CPU execution time and resource wait time. A query with high elapsed time may be waiting on I/O, locks, network, CPU scheduling, or other resources.

In SQL*Plus/SQLcl you can use:

~~~sql
SET TIMING ON;

SELECT COUNT(*)
FROM orders
WHERE customer_id = 1001;
~~~

`TIMING` is convenient for manual observation. It includes client/server round-trip overhead and tool rendering time; it does not replace controlled benchmarking.

### Measuring time in PL/SQL

You can use `SYSTIMESTAMP` to capture start/end timestamps:

~~~sql
DECLARE
    l_start TIMESTAMP WITH TIME ZONE;
    l_end   TIMESTAMP WITH TIME ZONE;
    l_elapsed INTERVAL DAY TO SECOND;
    l_count NUMBER;
BEGIN
    l_start := SYSTIMESTAMP;

    SELECT COUNT(*)
    INTO l_count
    FROM orders
    WHERE customer_id = 1001;

    l_end := SYSTIMESTAMP;
    l_elapsed := l_end - l_start;

    DBMS_OUTPUT.PUT_LINE('Rows counted = ' || l_count);
    DBMS_OUTPUT.PUT_LINE('Elapsed = ' || l_elapsed);
END;
/
~~~

This is a coarse single-session measurement. It does not separate CPU time, wait time, or network latency, and `DBMS_OUTPUT` adds its own overhead. Use it for illustration, not as a sole production benchmark.

### Median and percentiles

Latency usually has a skewed distribution: most requests are fast, while a few are slow due to I/O, locks, parsing, checkpoints, or background load. Averages can conceal tail latency.

- **p50/median:** 50% of requests finish at or below this duration.
- **p90:** 90% of requests finish at or below this duration.
- **p95:** 95% of requests finish at or below this duration.
- **p99:** 99% of requests finish at or below this duration.
- **max:** slowest run in the sample; sensitive to outliers.

Example:

| Version | p50 | p95 | p99 |
| --- | ---: | ---: | ---: |
| A | 40 ms | 180 ms | 700 ms |
| B | 45 ms | 90 ms | 150 ms |

B has a slightly higher median yet much better tail latency. If the application is sensitive to timeouts or p99 SLAs, B may be the better choice.

### Calculating percentiles from a dataset

If run timings are stored in a benchmark table:

~~~sql
SELECT version_name,
       PERCENTILE_CONT(0.50)
           WITHIN GROUP (ORDER BY elapsed_ms) AS p50_ms,
       PERCENTILE_CONT(0.95)
           WITHIN GROUP (ORDER BY elapsed_ms) AS p95_ms,
       PERCENTILE_CONT(0.99)
           WITHIN GROUP (ORDER BY elapsed_ms) AS p99_ms,
       AVG(elapsed_ms) AS avg_ms,
       MAX(elapsed_ms) AS max_ms
FROM benchmark_runs
GROUP BY version_name
ORDER BY version_name;
~~~

Percentiles are only meaningful when the sample is sufficiently large and collected over the same request type. Never compute p99 from a handful of runs and treat it as an SLA.

## 4. Measuring throughput

Throughput is the number of work units completed per unit of time. Depending on the application, units may be:

- Requests/second.
- Transactions/second (TPS).
- SQL executions/second.
- Rows processed/second.
- Messages or jobs completed/second.

Define the unit before measuring. One request might run one query or dozens of queries; hence requests/second and SQL executions/second are not interchangeable.

### Basic formula

\[
\text{Throughput} =
\frac{\text{Completed units}}{\text{Measurement duration}}
\]

For example, 12,000 requests completed in 60 seconds:

\[
\text{Throughput} = 12,000 / 60 = 200\ \text{requests/s}
\]

Measure throughput across multiple concurrency levels to find the saturation point. As sessions increase, throughput may rise initially, then plateau or drop once CPU, I/O, locks, latches, or connection pools become bottlenecks.

### Throughput and latency are related, not interchangeable

By Little's Law in steady state:

\[
L = \lambda W
\]

Where:

- \(L\): average number of requests in the system (average concurrency).
- \(\lambda\): throughput (requests/second).
- \(W\): average latency (seconds).

For instance, if throughput is 100 requests/s and average latency is 0.2 seconds, roughly 20 requests are in flight/waiting on average. This is a workload measurement relationship, not a predictive formula for unstable systems.

### Measuring throughput in a test

Record start/end timestamps and successful request counts:

~~~text
start_time = 10:00:00
end_time   = 10:01:00
completed_successfully = 12,000
failed = 3
duration_seconds = 60

throughput_success = 12,000 / 60 = 200 requests/s
error_rate = 3 / 12,003
~~~

Do not count failed requests as successful work. Report success throughput, error rate, timeouts, and retries separately; a system achieving high throughput by failing fast is not a healthy system.

### Testing throughput at varying concurrency

| Concurrent sessions | Throughput | Median | p95 | Error rate |
| ---: | ---: | ---: | ---: | ---: |
| 1 | ... | ... | ... | ... |
| 5 | ... | ... | ... | ... |
| 20 | ... | ... | ... | ... |
| 50 | ... | ... | ... | ... |
| 100 | ... | ... | ... | ... |

Look not only for peak throughput, but also the stable operating region with acceptable latency and error rates.

## 5. Measuring CPU and DB time in Oracle

Oracle exposes several metric layers. Understand each scope and unit to avoid invalid comparisons.

### CPU time

CPU time is the time the CPU actually spends executing work. Queries with high CPU time typically spend heavy processing inside the database on joins, sorts, functions, PL/SQL, or scanning/filtering many rows.

### DB time

DB time is total time foreground sessions spend in database calls, encompassing CPU time and non-idle wait events. When multiple sessions run concurrently, DB time can exceed wall-clock elapsed time for the observation window because it sums across sessions.

### Elapsed time and DB time are not identical

- Request elapsed time is end-to-end wall-clock duration across the chosen measurement boundary.
- DB time for a SQL/session reflects total database processing time, which can include various waits.
- CPU time is strictly CPU execution time, excluding wait time.

If elapsed time increases while CPU time barely moves, inspect waits, network, and resource contention. If CPU time and buffer gets rise together, inspect row counts processed, joins, predicates, and plans.

### V$SQL: cumulative cursor-level metrics

`V$SQL` holds statistics for child cursors currently in the shared pool:

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       elapsed_time,
       cpu_time,
       buffer_gets,
       disk_reads,
       rows_processed,
       parse_calls,
       last_active_time
FROM v$sql
WHERE sql_id = :sql_id
ORDER BY child_number;
~~~

Time columns like `ELAPSED_TIME` and `CPU_TIME` in `V$SQL` are typically in microseconds and are cumulative totals for the cursor, not single-execution latency. `BUFFER_GETS` and `DISK_READS` are also cumulative totals. To compare per execution, divide by `EXECUTIONS` when metrics share the same point in time and `executions > 0`; to measure changes over a window, take before/after snapshots and compute deltas.

Example computing cumulative averages:

~~~sql
SELECT sql_id,
       child_number,
       executions,
       ROUND(elapsed_time / 1e6, 3) AS total_elapsed_seconds,
       ROUND(elapsed_time / NULLIF(executions, 0) / 1e3, 3)
           AS avg_elapsed_ms,
       ROUND(cpu_time / NULLIF(executions, 0) / 1e3, 3)
           AS avg_cpu_ms,
       ROUND(buffer_gets / NULLIF(executions, 0), 1)
           AS avg_buffer_gets,
       ROUND(disk_reads / NULLIF(executions, 0), 1)
           AS avg_disk_reads
FROM v$sql
WHERE sql_id = :sql_id
ORDER BY child_number;
~~~

These are averages since the cursor was created/reset, not p95/p99. One child cursor can serve many executions with differing bind values; analyze child numbers and bind behavior.

### V$SQLSTATS

`V$SQLSTATS` provides aggregated statistics per SQL statement and often offers better retention/query performance than `V$SQL` for monitoring tasks:

~~~sql
SELECT sql_id,
       plan_hash_value,
       executions,
       elapsed_time,
       cpu_time,
       buffer_gets,
       disk_reads,
       rows_processed
FROM v$sqlstats
WHERE sql_id = :sql_id;
~~~

Consult release documentation for exact units and scope of each metric. Never add metrics from `V$SQL` and `V$SQLSTATS` together, as they represent the same activity from different views.

### V$SESSTAT and V$STATNAME

To measure statistics for a specific session, join `V$SESSTAT` with `V$STATNAME`:

~~~sql
SELECT n.name,
       s.value
FROM v$sesstat s
JOIN v$statname n
  ON n.statistic# = s.statistic#
WHERE s.sid = :sid
  AND n.name IN (
      'CPU used by this session',
      'session logical reads',
      'physical reads',
      'physical read total bytes',
      'physical writes',
      'physical write total bytes',
      'redo size',
      'user commits',
      'user rollbacks'
  )
ORDER BY n.name;
~~~

Capture two snapshots before and after on the same session and take the delta. Statistics are cumulative per session; a single snapshot cannot isolate which query generated them if the session ran multiple operations.

## 6. Measuring logical I/O, physical I/O, and redo

Not every block read hits storage. Oracle can serve blocks from the buffer cache; therefore, distinguish logical reads from physical reads.

### Buffer gets / logical reads

Buffer gets count how many times a session requests access to a block in the buffer cache. It reflects the logical read work performed by the SQL, regardless of whether blocks had to be fetched from storage.

A query with very high buffer gets may be:

- Scanning many blocks.
- Executing nested loops with excessive lookups.
- Re-reading the same blocks repeatedly.
- Using unselective predicates.
- Joining or aggregating a larger dataset than necessary.

Buffer gets are usually a reliable metric for comparing SQL work, especially when cache state varies. Still, fewer buffer gets do not automatically yield faster execution if other locks/waits dominate.

### Physical reads

Physical reads count blocks that had to be read from storage into the database buffer cache. Distinguish specific counters, such as `DISK_READS` in `V$SQL` versus physical read requests/bytes in session/system stats. One physical read request can fetch multiple blocks; never confuse request counts with block counts or bytes.

### Direct path reads

Some operations read directly from datafiles into private process memory bypassing the standard buffer cache. Watch wait events like `direct path read` and matching statistics during large scans or parallel execution.

### Physical writes and redo

DML changes can generate:

- Physical writes when dirty buffers are flushed to datafiles.
- Redo for change recovery.
- Undo to support rollback and read consistency.
- TEMP I/O when sort/hash operations exceed PGA memory.

When adding an index, `SELECT` reads may drop while `INSERT`/`UPDATE`/`DELETE` must maintain extra index entries and generate more redo/undo. SELECT-only benchmarks miss this write cost.

### Key metrics to record

| Metric | Meaning | Question to answer |
| --- | --- | --- |
| Buffer gets | Logical block accesses | Does the SQL read fewer blocks? |
| Physical reads | Blocks read from storage | Was actual I/O reduced or was it just warm cache? |
| Physical read bytes | Bytes read | Did it shift from many small requests to fewer larger reads? |
| Physical writes/bytes | Datafile writes | Did the index or rewrite raise write cost? |
| Redo size | Redo bytes generated | Does DML produce noticeably more redo? |
| Sorts (memory/disk) | In-memory vs. TEMP-spilled sorts | Were spills reduced? |
| Temp space | TEMP space consumed | Did hash/sort increase TEMP pressure? |

## 7. Wait events and identifying bottlenecks

A session can spend time waiting on various resources. Wait events categorize causes of high elapsed time.

### Common wait groups

| Wait/event group | Common meaning | Investigation focus |
| --- | --- | --- |
| `db file sequential read` | Typically single-block read, common with index/table lookups | Lookup counts, index selectivity, physical I/O latency. |
| `db file scattered read` | Typically multiblock read, common with full scans | Blocks scanned, filter selectivity, cache/storage throughput. |
| `direct path read` | Direct read, often from large scans or parallel queries | I/O bandwidth, parallelism, data volume. |
| `direct path write temp` | Writing temp data during sort/hash spills | PGA, sort/hash size, join cardinality. |
| `direct path read temp` | Reading temp data back from TEMP | Spill volume and TEMP I/O. |
| `enq: TX - row lock contention` | Waiting on another transaction holding a row lock | Transaction duration, hot rows, update order. |
| `buffer busy waits` | Buffer block contention | Hot blocks, segment/index contention. |
| `latch: cache buffers chains` | Latch contention protecting buffer cache chains | Hot blocks or concentrated repeated access. |
| `log file sync` | Foreground waiting on commit redo flush | Commit frequency, redo write latency. |
| `log file parallel write` | LGWR waiting to write redo | Redo storage latency. |
| `SQL*Net message from client` | Session idle waiting for client to send more work | Typically idle; not a database bottleneck. |

Exact wait event names and detailed interpretations depend on release and context. Never conclude from event name alone; inspect wait time, count, session state, SQL, and workload.

### V$SESSION_WAIT and V$SESSION

To observe currently waiting sessions:

~~~sql
SELECT sid,
       serial#,
       username,
       sql_id,
       event,
       wait_class,
       state,
       seconds_in_wait
FROM v$session
WHERE username IS NOT NULL
  AND state = 'WAITING'
ORDER BY seconds_in_wait DESC;
~~~

This is an instantaneous snapshot. A query may have waited on an event moments earlier yet currently be running on CPU; sample multiple times or use appropriate historical tools.

### Session wait statistics

~~~sql
SELECT sid,
       event,
       total_waits,
       time_waited,
       average_wait
FROM v$session_event
WHERE sid = :sid
  AND wait_class <> 'Idle'
ORDER BY time_waited DESC;
~~~

Metrics are cumulative per session since session start. Take before/after snapshots and compute deltas across the experiment window. `TIME_WAITED`/`AVERAGE_WAIT` units vary by view/release; check dictionary documentation.

### System wait events

~~~sql
SELECT event,
       total_waits,
       time_waited_micro,
       average_wait
FROM v$system_event
WHERE wait_class <> 'Idle'
ORDER BY time_waited_micro DESC;
~~~

System-wide waits mix activity across all sessions; do not attribute them to one specific SQL without filtering by time/session or pairing with SQL monitoring.

### CPU-bound or I/O-bound?

Diagnostic pointers:

- High CPU time, low waits, high buffer gets: check plan, row counts, joins, predicates, PL/SQL functions, and parallelism.
- High elapsed time, low CPU, high physical read waits: check storage latency, scan volume, and cache.
- High elapsed time, low CPU, high TX lock waits: check lock-holding transactions, hot rows, and update ordering.
- Sort/hash spilling to TEMP: check cardinality estimates, PGA/workareas, and intermediate sizes.
- High `log file sync`: check commit frequency and redo storage; never drop `COMMIT` casually as that alters transaction semantics.

A query can alternate between CPU-bound and I/O-bound across phases. Always read execution plans and waits together.

## 8. Viewing execution plans and row-source statistics

An execution plan reveals which operations Oracle intends to execute or executed: table accesses, index range scans, joins, sorts, filters, partition pruning, parallel operations, and execution order.

### EXPLAIN PLAN

~~~sql
EXPLAIN PLAN FOR
SELECT *
FROM orders
WHERE customer_id = 1001;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` creates an estimated plan in the explain context. It is not necessarily the actual plan a cursor executes because bind values, session settings, adaptive plans, child cursors, or parse environments may differ.

### DISPLAY_CURSOR

After executing the query, inspect the actual cursor:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        sql_id => :sql_id,
        cursor_child_no => :child_no,
        format => 'ALLSTATS LAST +PEEKED_BINDS +OUTLINE'
    )
);
~~~

Passing `NULL` for `SQL_ID`/child number usually targets the most recent cursor in the session; for exact diagnostics, pass the identified `SQL_ID` and child number.

### Collecting actual row-source statistics

Enable statistics for the query:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       *
FROM orders
WHERE customer_id = 1001;
~~~

Then view:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST'
    )
);
~~~

`ALLSTATS LAST` shows actual rows (`A-Rows`), operation executions (`Starts`), logical I/O (`Buffers`), and row-source metrics when collected. Compare `E-Rows` against `A-Rows` to spot large estimation errors.

### Key columns

- `E-Rows`: optimizer's estimated rows.
- `A-Rows`: actual rows produced by the operation.
- `Starts`: how many times the operation was started.
- `Buffers`: buffer gets for the operation.
- `Reads`: physical reads recorded for the operation if any.
- `A-Time`: cumulative/displayed operation execution time per plan format.
- `TEMP`: temporary space usage details if present.

Do not sum `A-Time` across every operation to obtain total query elapsed time, because parent/child timings overlap. Read the plan as an operation tree and cross-check cursor-level metrics.

### Plan hash value

`PLAN_HASH_VALUE` is a fingerprint identifying plan structure. It helps compare before/after structures, but does not capture bind values, outlines, predicates, adaptive behavior, or runtime. Identical plan hashes do not guarantee identical execution conditions; differing plan hashes do not automatically prove the new plan is worse.

## 9. SQL Trace and TKPROF

SQL Trace records a session's or workload's SQL activity, including parse/execute/fetch counts, CPU/elapsed time, logical/physical reads, waits, and bind values depending on settings. TKPROF formats trace files into more readable reports.

### Enabling trace for the current session

~~~sql
ALTER SESSION SET tracefile_identifier = 'ROW438_TEST';
ALTER SESSION SET sql_trace = TRUE;

-- Run the workload to measure here.
SELECT COUNT(*)
FROM orders
WHERE customer_id = 1001;

ALTER SESSION SET sql_trace = FALSE;
~~~

Trace files are written to the server-side diagnostic destination, not the client machine. DBAs can use ADRCI or query `V$DIAG_INFO` to locate trace files:

~~~sql
SELECT name, value
FROM v$diag_info
WHERE name IN ('Diag Trace', 'Default Trace File');
~~~

### DBMS_SESSION and DBMS_MONITOR

`DBMS_MONITOR` provides APIs to enable/disable tracing by session, client identifier, service/module/action, or other scopes depending on version:

~~~sql
BEGIN
    DBMS_MONITOR.SESSION_TRACE_ENABLE(
        waits => TRUE,
        binds => TRUE
    );
END;
/

-- Execute the workload to trace.

BEGIN
    DBMS_MONITOR.SESSION_TRACE_DISABLE;
END;
/
~~~

Tracing bind values can write sensitive data into trace files. Enable `binds` only when necessary and authorized; limit duration, scope, and trace storage access.

### Reading TKPROF

A DBA/engineer can run TKPROF on the trace file:

~~~text
tkprof input_trace.trc output_report.txt
~~~

TKPROF summarizes parse/execute/fetch counts, CPU, elapsed time, disk reads, query/current gets, and rows processed per SQL. Check how the report separates recursive SQL, waits, and bind data rather than reading total elapsed time alone.

### When to use trace?

- Complex queries needing exact parse/execute/fetch breakdowns.
- Pinpointing which SQL inside a transaction generates heavy I/O.
- Inspecting bind values or repeated executions.
- When `V$SQL`/plan views do not fully explain behavior.

Do not enable broad database-wide tracing for long periods without accounting for disk space and overhead. Traces can produce many files and contain sensitive information.

## 10. SQL Monitor and real-time reports

SQL Monitor provides detailed tracking for eligible SQL executions, especially long-running or parallel queries. You can use `DBMS_SQL_MONITOR` and `DBMS_SQLTUNE_REPORT`, or query `V$SQL_MONITOR`/`V$SQL_PLAN_MONITOR` views subject to privileges and version.

Example querying monitored executions:

~~~sql
SELECT sql_id,
       sql_exec_id,
       sql_exec_start,
       status,
       elapsed_time,
       cpu_time,
       buffer_gets,
       disk_reads,
       px_servers_requested,
       px_servers_allocated
FROM v$sql_monitor
WHERE sql_id = :sql_id
ORDER BY sql_exec_start DESC;
~~~

SQL Monitor reports timing and row counts per operation, which is especially helpful for parallel queries. Automatic monitoring thresholds and reporting options depend on version/configuration.

### SQL Monitor and licensing

Real-Time SQL Monitoring/SQL Monitoring reports belong to features associated with Oracle Tuning Pack in many commercial editions. Usage may require Diagnostic Pack/Tuning Pack and corresponding entitlements per edition, release, contract, and licensing policy. Before enabling or exporting reports in production, DBAs must verify entitlements; never assume every Oracle installation is licensed for them.

### AWR and ASH

AWR (Automatic Workload Repository) stores performance snapshots over time; ASH (Active Session History) samples active session activity. They help examine historical workloads, top SQL, waits, and trends over time. AWR/ASH features generally belong to Oracle Diagnostics Pack in many commercial releases; verify licensing before use.

Without matching licenses, use authorized dynamic performance views, SQL Trace/TKPROF, `DBMS_XPLAN`, and application instrumentation; check contracts/policies before picking tools.

### Do not substitute historical reports for controlled experiments

AWR/ASH are great for locating problematic workloads and time windows, but comparing two historical periods can be skewed by differing load, data, cache, background jobs, and concurrency. Use them for direction, then run controlled benchmarks to confirm.

## 11. Instrumentation: linking SQL to workloads

To measure properly, you need to know which request, module, action, or client owns a SQL statement. Oracle provides `DBMS_APPLICATION_INFO` and `DBMS_SESSION` to tag sessions.

### MODULE and ACTION

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_SERVICE',
        action_name => 'SEARCH_ORDERS'
    );
END;
/
~~~

After completing the action:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_ACTION(NULL);
END;
/
~~~

Module/action appear in `V$SESSION` and many monitoring tools. Use stable, meaningful names and avoid stuffing sensitive user data into labels.

### CLIENT_IDENTIFIER

~~~sql
BEGIN
    DBMS_SESSION.SET_IDENTIFIER('request-2026-000123');
END;
/
~~~

`CLIENT_IDENTIFIER` links a session to an application's logical request/user. When connection pools reuse sessions, reset the identifier when returning connections to the pool to avoid misattributing the next request.

### Recording SQL ID and plan hash

~~~sql
SELECT sid,
       serial#,
       username,
       module,
       action,
       client_identifier,
       sql_id,
       sql_child_number,
       prev_sql_id
FROM v$session
WHERE sid = :sid;
~~~

Combine module/action/client identifier with `SQL_ID` to trace SQL back to a request. Once a query finishes, `V$SESSION` may move to another SQL statement; to track historical executions, use `V$SQL`, SQL Monitor, or tracing within authorized bounds.

### Instrumentation should not alter results

Tagging module/action/identifier provides observability metadata, but code must reset it promptly and never trust those values for security decisions if callers can set them. Never put tokens, full emails, or sensitive data in `client_identifier`.

## 12. Verifying correctness after every change

Performance only matters if results are right. When rewriting SQL or changing schemas/indexes, compare before/after outputs on the exact same data snapshot and inputs.

### Checking row counts alone is not enough

Two queries can return identical row counts while differing in content. For example, query A returns 100 valid rows, while query B also returns 100 rows yet omits one row and duplicates another. `COUNT(*)` misses that discrepancy.

### Comparing two result sets with MINUS

Suppose old and new queries are materialized into two temporary or staging tables with matching structure:

~~~sql
SELECT col1, col2, col3
FROM result_before
MINUS
SELECT col1, col2, col3
FROM result_after;
~~~

This finds rows in BEFORE missing from AFTER. Check the reverse direction as well:

~~~sql
SELECT col1, col2, col3
FROM result_after
MINUS
SELECT col1, col2, col3
FROM result_before;
~~~

If both directions return zero rows, the two distinct value sets match under `MINUS` semantics. However, `MINUS` removes duplicates; when multiplicity/duplicate rows are part of the output, also compare occurrence counts per column tuple using `GROUP BY` and `COUNT`.

### Duplicate-aware comparison

~~~sql
SELECT col1, col2, col3, COUNT(*) AS occurrences
FROM result_before
GROUP BY col1, col2, col3
MINUS
SELECT col1, col2, col3, COUNT(*) AS occurrences
FROM result_after
GROUP BY col1, col2, col3;
~~~

Run the reverse direction to catch extra occurrences in AFTER as well. For LOB, LONG, or types not supporting `GROUP BY`/`MINUS` directly, compare using suitable alternatives like chunk hashing or streaming content comparison in application code.

### NULLs and comparisons

SQL uses three-valued logic. Predicate `a = b` does not return TRUE when both values are NULL; it returns UNKNOWN. When comparing outputs, clarify what NULL means and use null-safe comparison expressions.

Null-safe difference check example:

~~~sql
SELECT *
FROM result_before b
JOIN result_after a
  ON a.key_id = b.key_id
WHERE (a.value <> b.value)
   OR (a.value IS NULL AND b.value IS NOT NULL)
   OR (a.value IS NOT NULL AND b.value IS NULL);
~~~

This example assumes `KEY_ID` is unique and NOT NULL. If keys can be NULL or duplicated, use an appropriate full comparison key.

### ORDER BY and result ordering

Relational SQL sets have no guaranteed order without `ORDER BY`. Two queries can return the exact same row set in different display orders. If ordering is a business or API requirement, include a complete `ORDER BY`, including a deterministic tie-breaker when rows share sort keys.

### Checking aggregated values

For queries computing sums/counts/averages, compare:

- Group count and group keys.
- `COUNT(*)` and `COUNT(column)`.
- `SUM`/`AVG`/`MIN`/`MAX`.
- NULL handling.
- Numeric precision and rounding.
- Time zone/date boundaries.

Never check only a single grand total; errors across two groups can cancel each other out.

## 13. Verifying DML and transaction semantics

When modifying `INSERT`/`UPDATE`/`DELETE`/`MERGE`, verify both affected row counts and final data state.

### Comparing affected row counts

In PL/SQL, `SQL%ROWCOUNT` reports how many rows the latest DML statement affected:

~~~sql
UPDATE orders
SET status = 'EXPIRED'
WHERE expires_at < SYSTIMESTAMP;

DBMS_OUTPUT.PUT_LINE('Rows updated = ' || SQL%ROWCOUNT);
~~~

Record before/after row counts and verify against business expectations. Read `SQL%ROWCOUNT` immediately after the target DML statement, before running other SQL that overwrites implicit cursor attributes.

### Comparing before/after data state

For DML, create snapshots/staging or run in a cloned environment to compare:

- Inserted/deleted/modified keys.
- Changed columns and old/new values.
- Child row counts and FK relationships.
- Audit records and side effects.
- Totals, balances, quantities, or invariants.

### Transaction boundaries

A rewrite can alter SQL statement counts, lock acquisition timing, or transaction scope. Verify:

- Does `COMMIT` still occur at the right business boundary?
- Does `ROLLBACK` revert all changes that must be reverted?
- Are savepoints or autonomous transactions affected?
- How long are row locks held?
- Did isolation or read consistency change?
- Could a mid-flight failure leave partial data behind?

Never merge multiple small transactions into one giant transaction solely to save round trips if doing so lengthens lock duration, swells undo usage, or breaks business atomicity.

### Idempotency and retries

If applications retry on timeouts, evaluate statements against the case where a commit succeeded yet the response was lost. Ensure requests enforce idempotency keys or deduplication logic where business rules require it. A faster query that creates duplicates on retry is a broken change.

### Constraints and triggers

After DML changes, verify constraint checks, trigger firing, audit rows, and side effects. When adding indexes/constraints, test both valid write paths and rejected invalid paths.

## 14. Verifying correctness under concurrency

Passing in a single session is not enough for multi-session systems. Many bugs surface only when two transactions read/write concurrently.

Scenarios to test:

- Two sessions updating the same row.
- Two sessions inserting the same unique key simultaneously.
- One session reading while another updates/commits.
- Two transactions updating multiple rows in opposite orders.
- Retrying requests after timeouts.
- Bulk loads running alongside queries/reports.
- Paginated queries running during concurrent INSERT/DELETE.

### Unique races

If an application checks that a key does not exist before INSERTing, two sessions can both pass the pre-check. A `UNIQUE` constraint must be the final line of defense. Measure both success latency and conflict latency; record error rates and retry counts.

### Lost updates and locking

If a rewrite alters read-then-update patterns, check for lost updates. You may need `SELECT FOR UPDATE`, an optimistic version column, or a version-checked `UPDATE`:

~~~sql
UPDATE accounts
SET balance = :new_balance,
    version_no = version_no + 1
WHERE account_id = :account_id
  AND version_no = :old_version;
~~~

If `SQL%ROWCOUNT = 0`, another transaction modified the row or the row no longer exists; the application must handle the conflict. This is business semantics, not merely performance.

### Deadlocks and lock ordering

If transaction A locks row 1 then row 2 while transaction B locks row 2 then row 1, a deadlock can occur. After rewriting DML or adding update steps, check access/lock ordering and test concurrency. Oracle picks one statement as the deadlock victim; applications must handle the error and retry safely.

### Stable pagination

When using `OFFSET`/`FETCH` or keyset pagination, check:

- Is ordering deterministic?
- Are rows skipped or repeated when data changes between pages?
- Do pagination predicates use the matching sort key/index?
- Is the tie-breaker unique?

A fast pagination query that drops or duplicates records under concurrency fails requirements.

## 15. Designing repeatable benchmarks

A solid benchmark separates distinct phases:

1. **Setup:** create/restore data, statistics, and environment.
2. **Warm-up:** run to populate code, parses, and caches per defined scenario.
3. **Measurement:** run sufficient iterations/duration, collecting latency, throughput, and resource counters.
4. **Correctness:** cross-check outputs and side effects.
5. **Cleanup:** roll back/clean test data, close sessions, and archive logs.

### Warm cache and cold cache

Warm-cache tests measure workloads after data blocks are likely in the buffer cache. Cold-cache tests measure colder cache conditions, which are very hard to reproduce cleanly in production; never flush the buffer cache/shared pool arbitrarily on shared systems.

Document clearly whether you are measuring cold or warm. Comparing A warm against B cold is invalid.

### Parse and execute

The very first run may incur a hard parse, PL/SQL compilation/loading, library cache lookups, or cache misses. If production calls SQL repeatedly with cursor reuse, benchmarking only the first run is unrepresentative.

Measure separately:

- Hard parse vs. soft parse.
- Execute/fetch.
- Warm-up vs. steady state.
- Queries with common and rare bind values.

### Repetition and A/B ordering

Run multiple iterations and alternate version ordering—such as A-B-B-A or randomized order in a test environment—to reduce bias from background load and cache drift. Never run all of A and then run B hours later if ambient conditions shift over time.

### Matching concurrency levels

Single-session runs reveal single-execution latency; multi-session runs expose contention. Test representative concurrency tiers without saturating unrelated systems. Record throughput, p95/p99, error rate, CPU, and I/O at each tier.

### Avoid DBMS_OUTPUT in benchmarks

`DBMS_OUTPUT` and printing every row skew timings due to formatting, buffer allocation, and client fetches. Query benchmarks should consume rows similarly to the application without extra display overhead.

### Benchmark data must be representative

Ensure data skew, NULL ratios, distinct value counts, row lengths, partition sizes, and row volumes resemble production. Tiny lab tables can cause the optimizer to pick completely different plans.

## 16. Analyzing before/after results

After benchmarking, never report only "X% faster". Explain changes via metrics and check whether gains traded off other resources.

### Calculating percentage latency improvement

If latency drops from \(T_{before}\) to \(T_{after}\):

\[
\text{Latency improvement} =
\frac{T_{before} - T_{after}}{T_{before}} \times 100\%
\]

For example, if median drops from 100 ms to 75 ms:

\[
\frac{100-75}{100}\times 100\% = 25\%
\]

For throughput rising from \(R_{before}\) to \(R_{after}\):

\[
\text{Throughput increase} =
\frac{R_{after} - R_{before}}{R_{before}} \times 100\%
\]

Always state whether the metric is median, p95, p99, or average. Never apply a single generic improvement percentage to everything.

### Trade-off matrix

| Measured outcome | Possible interpretation | What to verify |
| --- | --- | --- |
| Latency down, CPU down, buffer gets down | Likely genuine reduction in total work | Verify correctness and concurrency. |
| Latency down, physical reads up | Cache/warm state or access path shifted | Repeat warm/cold tests, measure bytes and storage latency. |
| Single-run latency down, throughput down | Increased contention or per-request resource cost | Test concurrency and session waits. |
| CPU down, elapsed unchanged | Query may be waiting on I/O/locks/network | Check wait events and transactions. |
| Buffer gets down, redo up | Better read path but higher write maintenance | Benchmark DML and total workload. |
| p50 better, p99 worse | One request subgroup affected or contention rose | Segment bind values and request classes. |
| Plan hash changed, runtime better | Optimizer picked a plan better suited to workload sample | Test across diverse bind values and workloads. |
| Plan hash unchanged, runtime better | Differing cache, ambient load, or runtime conditions | Control conditions and re-measure. |

### Evaluating impact on the overall workload

Never evaluate a SQL change solely on the target query. For instance, a new index can cut `SELECT` latency while increasing:

- `INSERT`/`UPDATE`/`DELETE` duration.
- Redo generation and archive log volume.
- Storage footprint and backup duration.
- Latch/buffer contention on hot index blocks.
- Optimizer statistics and maintenance cost.

Measure the production read/write mix. If a query accounts for 1% of DB time while an index slows all DML on the table, the trade-off may not pay off.

### Defining acceptance thresholds before testing

Define criteria upfront, for example:

- Correctness: zero output differences or invariant violations.
- Error rate: no increase beyond threshold.
- p95: at least 15% reduction.
- p99: no worse than +5%.
- Throughput: no drop at target concurrency.
- CPU/request and buffer gets/request: within allowed budget.
- DML latency: within budget.

Thresholds are illustrative; each system must set appropriate SLAs/SLOs and resource budgets.

## 17. Lab: measuring a query before and after adding an index

This lab creates an isolated table, loads synthetic data, measures an aggregate query, inspects plans, adds an index, and compares both outputs and metrics. Run in a learning schema with `CREATE TABLE` and `CREATE INDEX` privileges. DDL performs an implicit commit in Oracle.

### Step 1: create sample table

~~~sql
CREATE TABLE lab_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_status VARCHAR2(10) NOT NULL,
    order_amount NUMBER(12,2) NOT NULL,
    created_at DATE NOT NULL
);
~~~

### Step 2: load representative data

~~~sql
INSERT INTO lab_orders (
    order_id,
    customer_id,
    order_status,
    order_amount,
    created_at
)
SELECT level,
       MOD(level, 1000),
       CASE WHEN MOD(level, 100) = 0 THEN 'OPEN' ELSE 'CLOSED' END,
       MOD(level * 17, 100000) / 100,
       DATE '2025-01-01' + MOD(level, 365)
FROM dual
CONNECT BY level <= 200000;

COMMIT;
~~~

This dataset exhibits status skew and multiple orders per customer. Lab scale is solely for observation and does not represent every production distribution.

### Step 3: gather initial stats

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO',
        cascade => TRUE
    );
END;
/
~~~

### Step 4: measure version A without secondary index

Enable timing in SQL*Plus/SQLcl:

~~~sql
SET TIMING ON;

SELECT /*+ GATHER_PLAN_STATISTICS */
       customer_id,
       COUNT(*) AS order_count,
       SUM(order_amount) AS total_amount
FROM lab_orders
WHERE customer_id = 101
  AND order_status = 'OPEN'
GROUP BY customer_id;
~~~

Immediately after the query, inspect the plan:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST'
    )
);
~~~

Record client elapsed time, `E-Rows`/`A-Rows`, `Starts`, `Buffers`, `Reads`, and plan hash. Run warm-up iterations and measure multiple times; never conclude from a single execution.

### Step 5: save version A results

~~~sql
CREATE TABLE lab_result_before AS
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(order_amount) AS total_amount
FROM lab_orders
WHERE customer_id = 101
  AND order_status = 'OPEN'
GROUP BY customer_id;
~~~

The snapshot table stores results for comparison. CTAS is DDL and commits implicitly; use in a lab schema.

### Step 6: add index

~~~sql
CREATE INDEX ix_lab_orders_customer_status
ON lab_orders(customer_id, order_status);
~~~

This index can support equality predicates on `CUSTOMER_ID` and `ORDER_STATUS`. Do not assume the optimizer will definitely choose the index; selection depends on cost, statistics, and release.

Re-gather table/index stats:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO',
        cascade => TRUE
    );
END;
/
~~~

### Step 7: measure version B

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       customer_id,
       COUNT(*) AS order_count,
       SUM(order_amount) AS total_amount
FROM lab_orders
WHERE customer_id = 101
  AND order_status = 'OPEN'
GROUP BY customer_id;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST'
    )
);
~~~

Record the exact same metrics as version A. Run multiple iterations following the same cache protocol. The query might still use a full scan if the optimizer finds it favorable; read the actual plan.

### Step 8: save version B results

~~~sql
CREATE TABLE lab_result_after AS
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(order_amount) AS total_amount
FROM lab_orders
WHERE customer_id = 101
  AND order_status = 'OPEN'
GROUP BY customer_id;
~~~

### Step 9: two-way correctness check

~~~sql
SELECT customer_id, order_count, total_amount
FROM lab_result_before
MINUS
SELECT customer_id, order_count, total_amount
FROM lab_result_after;

SELECT customer_id, order_count, total_amount
FROM lab_result_after
MINUS
SELECT customer_id, order_count, total_amount
FROM lab_result_before;
~~~

Both queries must return zero rows. Because output is grouped by `CUSTOMER_ID`, each customer appears at most once in the result set. If a real query has duplicate semantics, add multiplicity checks.

### Step 10: check write overhead

Test `INSERT`/`UPDATE`/`DELETE` on `LAB_ORDERS` before and after the index for the same row counts. Record elapsed time, CPU, redo, buffer gets, and throughput. The new index can add maintenance cost to write operations.

### Step 11: clean up lab

~~~sql
DROP TABLE lab_result_before PURGE;
DROP TABLE lab_result_after PURGE;
DROP TABLE lab_orders PURGE;
~~~

Clean up only after saving all measurements. `DROP` is DDL and commits implicitly.

## 18. Common mistakes when measuring performance

| Mistake | Why it misleads | Fix |
| --- | --- | --- |
| Measuring only once | Skewed by hard parse, cache, and ambient load | Warm up, repeat many times, and use percentiles. |
| Comparing averages only | Hides tail latency | Track p50/p95/p99 and max. |
| Running A warm and B cold | Incomparable cache states | Enforce explicit warm/cold protocol. |
| Testing on tables far smaller than production | Optimizer chooses a different plan | Match production volume, skew, and partitions closely. |
| Measuring SELECT only | Ignores index/DML/redo overhead | Measure read/write mix and full transactions. |
| Not keeping bind values identical | Different selectivity and child cursors | Fix bind values and test multiple bind groups. |
| Looking only at EXPLAIN PLAN | Not always the actual executed cursor | Use `DISPLAY_CURSOR` and `ALLSTATS LAST`. |
| Treating `V$SQL.elapsed_time` as single-run time | Cumulative counter across executions | Compute deltas or divide by executions; check child cursors. |
| Using system waits to diagnose one SQL | Aggregates across all sessions | Use session/SQL-level tracing and instrumentation. |
| Skipping correctness checks | Faster query might drop rows | Compare result sets, duplicates, NULLs, and invariants. |
| Skipping concurrency testing | Misses locks, deadlocks, and races | Test multi-session concurrency and retry paths. |
| Running benchmarks alongside abnormal background jobs | Background load distorts numbers | Pick a quiet window and log background activity. |
| Flushing shared pool/buffer cache in production | Disrupts the whole instance | Run cold-cache tests only in isolated environments. |
| Ignoring tool licensing | Risks using unlicensed features | Verify Diagnostics/Tuning Pack entitlements beforehand. |

## 19. Self-check questions

1. **What is latency?** Time to complete one unit of work within a defined measurement boundary.
2. **What is throughput?** Number of work units completed per unit of time.
3. **Why measure p95/p99?** To observe tail latency that averages/medians can hide.
4. **How does CPU time differ from elapsed time?** CPU time is CPU processing duration; elapsed time includes waits and all components within the measurement boundary.
5. **What is DB time?** Total time foreground sessions spend in database calls, covering CPU and non-idle waits.
6. **What do buffer gets reflect?** Logical block accesses in the buffer cache.
7. **How do physical reads differ from buffer gets?** Physical reads fetch blocks from storage; buffer gets can be served from cache.
8. **Is `V$SQL.ELAPSED_TIME` a single-execution latency?** No; it is a cumulative counter per cursor/child.
9. **How do you view actual rows?** Use `GATHER_PLAN_STATISTICS` and `DBMS_XPLAN.DISPLAY_CURSOR` with `ALLSTATS LAST`.
10. **How do `E-Rows` and `A-Rows` differ?** Optimizer's estimated rows versus actual rows produced by a row source.
11. **When should SQL Trace/TKPROF be used?** When detailed parse/execute/fetch counts, waits, binds, and SQL execution breakdowns are needed.
12. **Do SQL Monitor/AWR/ASH require license checks?** Yes; many features fall under Tuning Pack/Diagnostics Pack depending on release/contract.
13. **What is `DBMS_APPLICATION_INFO` used for?** Tagging module/action to associate SQL with workloads.
14. **What does two-way `MINUS` prove?** That two distinct value sets are equal, though it does not prove duplicate multiplicities match.
15. **Why check NULLs explicitly?** SQL uses three-valued logic; standard equality does not treat NULL as equal to NULL.
16. **Why test concurrency?** To catch lock contention, races, lost updates, deadlocks, and retry bugs.
17. **Why must DML be measured after adding an index?** Because `INSERT`/`UPDATE`/`DELETE` must maintain additional index entries and redo.
18. **Why shouldn't you flush the buffer cache in production for cold benchmarks?** It disrupts the entire instance and other workloads.
19. **Is plan hash value enough to conclude two plans are identical?** No; binds, predicates, child cursors, adaptive behavior, and runtime still matter.
20. **When is a change considered successful?** When correctness is preserved and target latency/throughput/resource goals improve or meet predefined trade-offs.

Every SQL change needs a baseline and a representative workload. Measure latency across multiple samples and percentiles, measure throughput across concurrency levels, and track CPU, buffer gets, physical I/O, redo, and wait events. Use `V$SQL`, `DBMS_XPLAN`, traces, or authorized monitoring tools to explain root causes rather than merely recording numbers. Verify results with two-way comparisons, duplicates, NULLs, ordering, DML effects, and transaction behavior. Accept a change only when correctness holds and performance measurably improves against defined criteria on a realistic workload.
