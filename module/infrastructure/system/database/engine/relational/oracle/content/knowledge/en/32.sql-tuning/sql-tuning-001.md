# Workflow for Load Measurement, Selecting Critical SQL, Fixing, and Re-comparing in Oracle

## 1. SQL tuning starts from the workload

SQL tuning is not about rewriting a query simply because it has many JOINs, many lines of code, or a complex-looking execution plan. The goal is to improve a specific workload: users need operations to finish faster, a batch needs to complete within its window, the system needs to serve more requests, or the database needs to use less CPU and I/O.

A tuning workflow can be divided into five phases:

1. **Load measurement:** collect metrics under conditions representative of the real workload.
2. **Selecting critical SQL:** find the SQL statements with the largest impact on response time, resources, or business operations.
3. **Root cause analysis:** examine the SQL, execution plan, runtime statistics, bind values, and execution environment.
4. **Controlled changes:** fix a group of root causes backed by a clear hypothesis.
5. **Re-measuring and comparing:** verify the results, side-effect costs, and correctness before broad rollout.

Do not start by creating indexes or rewriting SQL by intuition. First, you need to know which SQL statement is worth fixing, which resources it is consuming, and how users are actually affected.

This lesson belongs to the **SQL Tuning** chapter, focusing on the workflow of measuring load, selecting critical SQL, fixing SQL statements, and performing before/after comparisons on Oracle Database. Topics include workload metrics, SQL_ID, execution plans, SQL Trace/TKPROF, V$SQL, DBMS_XPLAN, work prioritization, testing, and safe deployment.

## 2. Defining measurement goals and scope

Before running a benchmark, determine which outcome needs improvement. A SQL statement might become faster in elapsed time while consuming more CPU, or reduce buffer gets while increasing commit time for a write workload.

### 2.1. Choosing appropriate metrics

| Goal | Metrics to monitor |
|---|---|
| Fast user request response | Elapsed time, p95/p99 latency |
| Reduce CPU load | CPU time, DB CPU, CPU per execution |
| Reduce logical I/O | Buffer gets, gets per row |
| Reduce physical I/O | Physical reads, read latency |
| Increase throughput | Executions/second, rows/second, transactions/second |
| Improve batch performance | Total batch duration, completion time |
| Reduce write overhead | Redo size, write I/O, DML elapsed time |
| Reduce contention | Wait events, lock waits, concurrency |
| Reduce per-request resources | CPU, buffers, reads per execution |

Elapsed time is the wall-clock time observed by the caller. CPU time is the time the CPU actually spends executing that work. The two values can differ widely if the SQL waits on I/O, locks, network, or other resources.

### 2.2. Distinguishing latency and throughput

- **Latency:** how long a single request takes to complete.
- **Throughput:** how many requests the system completes per unit of time.

Tuning a query running sequentially can reduce latency. However, under concurrent load, that same change might increase contention or reduce throughput. Therefore, measure both when the system serves multiple sessions.

### 2.3. Choosing percentiles for interactive workloads

Do not look only at the average. An average can hide abnormally slow requests. For APIs or interactive applications, monitor:
- p50: typical level.
- p95: 95% of requests complete no slower than this value.
- p99: reflects the latency tail.
- Maximum: useful for investigation but very sensitive to outliers.

Do not combine different request groups into a single percentile. For example, search queries, reports, and order updates have different SLAs and should be grouped separately.

## 3. Designing a comparable measurement

A measurement is only meaningful when you know the conditions under which it was performed.

### 3.1. Recording the environment

Before measuring, record the following details:
- Oracle Database version and Release Update.
- Edition, instance configuration, and node count if using RAC.
- CPU, RAM, storage, and I/O configuration.
- Optimizer-related database parameters.
- Schema, indexes, partitions, and statistics.
- Test data and value distribution.
- Bind values or representative bind groups.
- Number of concurrent sessions.
- Module, action, and service name.
- Measurement timestamp and system state.

A SQL change measured on a lightly loaded machine cannot automatically prove it will improve production when many sessions access it concurrently.

### 3.2. Using the same data and the same conditions

When comparing the old and new versions:
- Same dataset or an equivalent snapshot.
- Same filter conditions and bind values.
- Same transaction boundaries.
- Same number of concurrent sessions.
- Same cache state, or explicitly document differences.
- Same database configuration if the goal is to compare the SQL alone.
- Same measurement method and workload duration.

If the data changes significantly between two runs, the results may reflect different data distributions rather than SQL quality.

### 3.3. Warm cache and cold cache

The first run may have to read blocks from storage; subsequent runs may read from the buffer cache. Therefore:
- Measure warm-cache when the real workload repeatedly accesses the same data.
- Measure cold-cache only in a controlled test environment and when the goal requires evaluating cold I/O.
- Do not flush the buffer cache in production to create a benchmark.
- Document the number of warm-up iterations and how results are selected.

Do not take the fastest run out of multiple measurements as the conclusion. Use median and percentiles, or gather statistics over a sufficient number of iterations.

### 3.4. Avoiding single-session-only benchmarks when production runs concurrently

An index can make a single session faster while causing contention when many sessions update the index concurrently. A faster read query can increase CPU usage enough to slow down other workloads.

You should have two measurement levels:
1. **Microbenchmark:** isolate the SQL statement to understand its access path and per-execution cost.
2. **Workload test:** run alongside representative requests at near-realistic concurrency to confirm system-wide impact.

## 4. Collecting database-level load data

Oracle provides multiple metric sources. Choose tools based on privileges, version, licensing policy, and necessity.

### 4.1. V$SQL: SQL statement statistics in the shared pool

`V$SQL` displays SQL cursors currently cached in the shared SQL area along with cumulative execution statistics. Useful columns include:

| Column | Meaning |
|---|---|
| `SQL_ID` | SQL statement identifier |
| `CHILD_NUMBER` | Child cursor |
| `PLAN_HASH_VALUE` | Plan hash identifier |
| `EXECUTIONS` | Number of executions |
| `ELAPSED_TIME` | Total elapsed time, in microseconds |
| `CPU_TIME` | Total CPU time, in microseconds |
| `BUFFER_GETS` | Logical reads |
| `DISK_READS` | Recorded physical reads |
| `ROWS_PROCESSED` | Number of rows processed |
| `PARSE_CALLS` | Number of parse calls |
| `MODULE`, `ACTION` | Application context if set |
| `LAST_ACTIVE_TIME` | Most recent active timestamp |

Example of finding SQL consuming high total elapsed time:

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       ROUND(elapsed_time / 1e6, 2) AS elapsed_seconds,
       ROUND(cpu_time / 1e6, 2) AS cpu_seconds,
       buffer_gets,
       disk_reads,
       rows_processed,
       module,
       action,
       last_active_time
FROM v$sql
WHERE executions > 0
ORDER BY elapsed_time DESC
FETCH FIRST 30 ROWS ONLY;
```

These are cumulative statistics over the cursor's lifetime in the shared pool, not a report for a fixed time window. Cursors can be aged out or reloaded; metrics can reset when the instance restarts or the cursor is reloaded.

### 4.2. Do not rank solely by total elapsed time

A SQL with high total elapsed time might only run once in a report. Another SQL with low per-execution elapsed time might run hundreds of thousands of times and generate massive total load.

Compute average metrics:

```sql
SELECT sql_id,
       plan_hash_value,
       executions,
       ROUND(elapsed_time / 1e6, 3) AS total_elapsed_s,
       ROUND(elapsed_time / GREATEST(executions, 1) / 1e6, 6)
           AS elapsed_s_per_exec,
       ROUND(cpu_time / GREATEST(executions, 1) / 1e6, 6)
           AS cpu_s_per_exec,
       ROUND(buffer_gets / GREATEST(executions, 1), 1)
           AS gets_per_exec,
       ROUND(rows_processed / GREATEST(executions, 1), 1)
           AS rows_per_exec
FROM v$sql
WHERE executions > 0
ORDER BY elapsed_time DESC;
```

Averages help reveal per-call cost, but they can hide variance caused by bind values or child cursors. If the workload has multiple parameter groups, analyze them separately.

### 4.3. Taking deltas instead of reading cumulative numbers only

To measure a test interval:
1. Take a statistics snapshot before.
2. Run the workload for the defined interval.
3. Take a snapshot after.
4. Compute the delta between the two.

You can store metrics from `V$SQL` into a lab table or external file. When comparing, match by `SQL_ID` and `CHILD_NUMBER`/`PLAN_HASH_VALUE` appropriately; if a cursor disappears between snapshots, record that rather than assuming the delta is valid.

### 4.4. Viewing SQL by module/action

Applications should set module and action so DBAs know which feature a SQL statement belongs to:

```sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_API',
        action_name => 'SEARCH_ORDERS'
    );
END;
/
```

After completing an operation, the application can update the action or reset the module according to connection conventions. With connection pools, set the context properly for each request so SQL is not misattributed to a previous request.

You can inspect these in `V$SQL.MODULE` and `V$SQL.ACTION`, or related session/workload views.

### 4.5. V$SQL is not a complete history

`V$SQL` only reflects cursors still in the shared pool and statistics attached to those cursors. It does not replace a workload history repository. For longer time ranges, use historical sources such as AWR or Statspack according to privileges and licensing.

## 5. AWR, ASH, and Statspack

### 5.1. AWR

Automatic Workload Repository (AWR) stores workload statistic snapshots for trend analysis and comparing time intervals. AWR reports help identify:
- DB time and DB CPU.
- Top SQL by elapsed time, CPU, buffer gets, or reads.
- Prominent wait events.
- Load profile.
- SQL execution and plan statistics.
- Workload changes between two snapshots.

AWR is a useful tool for systems with long-term load, but using AWR and related features has Oracle licensing requirements. Check the Oracle Licensing Information User Manual and your active agreement before using them.

### 5.2. ASH

Active Session History (ASH) samples active session states, showing which SQL a session is running and what event it is waiting on. It aids in investigating:
- SQL_IDs causing load at a specific point in time.
- Sessions waiting on I/O, locks, or CPU.
- Module/action.
- Blocking sessions and wait chains within the recorded data range.

ASH/AWR and reports based on them fall under features requiring appropriate license verification. Do not use a view or report simply because an account has access privileges.

### 5.3. Statspack

Statspack is an option for collecting and comparing performance statistics via snapshots, commonly used when AWR is not licensed or per system policy. Install, configure snapshots, and manage Statspack data following Oracle documentation for your release.

Statspack does not have all the capabilities and granularity of AWR/ASH, but it can help identify workloads and load trends.

### 5.4. Choosing a tool

| Need | Suggested tool |
|---|---|
| View current cursors and cumulative statistics | `V$SQL`, `V$SQLAREA` |
| Measure a specific SQL statement | SQL Trace + TKPROF |
| View runtime plan of a cursor | `DBMS_XPLAN.DISPLAY_CURSOR` |
| Analyze workload history | AWR if licensed; Statspack per policy |
| Analyze active sessions | ASH if licensed; appropriate session/wait views |
| Analyze PL/SQL timing | `DBMS_HPROF` or appropriate profiler |
| Monitor long-running SQL in real time | SQL Monitor if licensed and supported |

## 6. Selecting critical SQL: prioritizing by impact

After collecting metrics, you do not necessarily fix the SQL at the top of a single ranking. Combine technical cost with business impact.

### 6.1. Prioritization criteria

- Total DB time/elapsed time consumed.
- Total CPU time.
- Buffer gets and physical reads.
- Execution count.
- Average cost per execution.
- p95/p99 latency if available.
- Execution timing and impact on batch windows.
- Number of affected users or services.
- Criticality of the business function.
- Risk level and implementation effort.

### 6.2. Example ranking table

| SQL | Executions | Total elapsed | Elapsed/exec | Gets/exec | Impact |
|---|---:|---:|---:|---:|---|
| SQL A | 2,000 | 900 s | 0.45 s | 80,000 | Scheduled report |
| SQL B | 500,000 | 600 s | 0.0012 s | 35 | Continuously called API |
| SQL C | 10 | 300 s | 30 s | 2,000,000 | Slow report |
| SQL D | 100,000 | 120 s | 0.0012 s | 20 | Low impact |

Numbers are illustrative only. SQL A has the highest total elapsed time; SQL B may deserve priority because it is called very frequently. SQL C may heavily impact a specific user group or batch window. The decision depends on SLAs and business criticality.

### 6.3. Prioritization matrix

You can score across dimensions:
- **Impact:** user/batch impact.
- **Cost:** total resources consumed by the SQL.
- **Frequency:** execution frequency.
- **Confidence:** certainty about root cause and solution.
- **Risk:** risk of the change returning wrong results or affecting other workloads.

Do not add scores mechanically. Use the matrix to explain why a SQL was chosen and document the rationale so the team can review it.

### 6.4. Selecting SQL by business function, not just SQL_ID

SQL_ID identifies a statement in Oracle, whereas users understand features such as "search orders", "calculate inventory", or "close period". Combine module/action, service, schema, and application logs to map SQL to business functions.

If a single feature generates many distinct SQL_IDs due to literal values, review bind variables and how the application constructs SQL.

## 7. Analyzing SQL_ID and child cursors

A single SQL statement can have multiple child cursors due to environment differences, bind metadata, optimizer environment, object resolution, or adaptive cursor sharing.

### 7.1. Viewing child cursors

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       parse_calls,
       loads,
       invalidations,
       is_bind_sensitive,
       is_bind_aware
FROM v$sql
WHERE sql_id = :sql_id
ORDER BY child_number;
```

If the same SQL_ID has multiple child cursors with different plan hashes, determine why. Do not assume multiple child cursors are always an error; Oracle may need different plans for different groups of bind values.

### 7.2. Viewing SQL text

```sql
SELECT sql_id,
       child_number,
       sql_fulltext
FROM v$sql
WHERE sql_id = :sql_id;
```

SQL text can be long; use `SQL_FULLTEXT` or `V$SQL.SQL_TEXT` as needed. Do not put literals containing sensitive data into uncontrolled documentation or logs.

### 7.3. Bind values

Bind variables enable cursor reuse and reduce hard parses, but data distribution can make a single plan suboptimal for all values. `V$SQL_BIND_CAPTURE` captures binds by sampling and is not guaranteed to store every execution or every value. Do not treat it as a complete record of all bind values.

For benchmarks, document representative bind groups at the application layer or test harness while protecting sensitive data.

### 7.4. SQL_ID and PLAN_HASH_VALUE

- `SQL_ID` identifies the statement.
- `PLAN_HASH_VALUE` helps compare execution plan shapes.
- The same SQL_ID can have different plans across child cursors.
- The same plan hash does not guarantee identical runtime performance because data, cache, binds, concurrency, and system state differ.

## 8. Reading execution plans properly

An execution plan shows which operations Oracle intends to use or actually used to execute a query. Do not just check whether an index is used.

### 8.1. EXPLAIN PLAN

```sql
EXPLAIN PLAN FOR
SELECT order_id, customer_id, order_date
FROM orders
WHERE customer_id = 1001
  AND order_date >= DATE '2026-01-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` generates an estimated plan for the SQL statement in the explain context. It does not necessarily reflect the actual child cursor and runtime execution.

### 8.2. DISPLAY_CURSOR

In a test session, enable runtime statistics collection:

```sql
ALTER SESSION SET statistics_level = ALL;
```

Run the SQL statement:

```sql
SELECT order_id, customer_id, order_date
FROM orders
WHERE customer_id = 1001
  AND order_date >= DATE '2026-01-01';
```

Then:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +PEEKED_BINDS'
    )
);
```

`ALLSTATS LAST` displays runtime statistics for the most recent execution if they were collected. You can enable `STATISTICS_LEVEL=ALL` in a test session instead of using hints, subject to privileges and environment policy.

### 8.3. Comparing E-Rows and A-Rows

- `E-Rows`: number of rows estimated by the optimizer.
- `A-Rows`: actual number of rows in the runtime plan.

Large discrepancies may indicate:
- Stale or unrepresentative statistics.
- Unmodeled data skew.
- Correlated predicates across multiple columns.
- Bind values with differing distributions.
- Functions or expressions that make estimation difficult for the optimizer.
- Misestimated JOIN cardinality.

Inaccurate estimates can lead to an unsuitable join order or join method.

### 8.4. Inspecting key operations

| Operation | Questions to ask |
|---|---|
| TABLE ACCESS FULL | Is the table large or small? What percentage of rows does the query return? |
| INDEX RANGE SCAN | Is the predicate selective? Does it access the table many times? |
| INDEX UNIQUE SCAN | Does the condition use the full unique key? |
| TABLE ACCESS BY INDEX ROWID | How many table accesses occur and what is the clustering factor? |
| NESTED LOOPS | Is the outer row count as small as the optimizer predicted? |
| HASH JOIN | Is there enough PGA? Does it spill to TEMP? |
| SORT ORDER BY | Can an index/order be leveraged or can data be reduced before sorting? |
| HASH GROUP BY | Does it spill to TEMP or process an overly large set? |
| PARTITION RANGE | Is partition pruning working properly? |
| FILTER | Which predicate is being evaluated repeatedly? |

Do not assume a full scan is always bad or an index scan is always good. If a large fraction of the table must be read, a full scan can be cheaper than many random accesses via an index.

## 9. Diagnosing by resource type

### 9.1. High CPU

Symptoms:
- High CPU time.
- DB CPU accounts for a large share.
- High buffer gets or function call counts.
- SQL runs slowly even though physical reads are low.

Investigation areas:
- Repeated expressions or function calls.
- Joins producing excessive intermediate rows.
- Large sorts or hashes.
- Non-sargable predicates.
- SQL called too many times.
- PL/SQL/SQL context switches.
- Parse CPU from hard parses.

### 9.2. High buffer gets

Buffer gets count block accesses in the buffer cache. A query might read very little from storage yet still burn CPU by scanning too many blocks.

Investigation areas:
- Unnecessary full scans.
- Index range scans returning too many rowids.
- Nested loops iterating over a large outer set.
- Missing suitable composite index.
- JOINs or predicates inflating the dataset.
- Function-based predicates preventing index usage.

### 9.3. High physical reads

Investigation areas:
- Working set larger than cache.
- Access path reading many blocks.
- Table/index scans on large segments.
- Storage latency or throughput.
- Cache behavior and concurrency.
- Unnecessary access to LOBs or table data.

Physical reads alone do not prove bad SQL; the workload may genuinely require reading large volumes of data.

### 9.4. Waits and blocking

If elapsed time is high while CPU is low, check wait events:
- User I/O.
- Concurrency/latch/mutex.
- Lock waits.
- Network or client waits.
- Commit/log file sync.
- TEMP I/O.

Tuning the SQL statement does not solve every wait. For example, an UPDATE that is slow waiting on a row lock requires investigating the transaction holding the lock; adding an index may not address the root cause.

## 10. Common SQL tuning approaches

Every change should correspond to a root cause observed in the plan or metrics.

### 10.1. Filtering early and avoiding unnecessary row processing

If only a subset of data is needed, place predicates in the appropriate query block to reduce the rows flowing through JOINs, sorts, and aggregations. Avoid fetching an entire table to the application and filtering on the client.

### 10.2. Using EXISTS for existence checks

When you only need to know whether related rows exist, `EXISTS` directly expresses the intent:

```sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'OPEN'
);
```

Do not JOIN all orders and apply DISTINCT just to check existence, unless there is a specific plan or result reason.

### 10.3. Avoiding functions on filter columns if they prevent index usage

Example:

```sql
SELECT order_id
FROM orders
WHERE TRUNC(order_date) = DATE '2026-03-01';
```

A form that is typically friendlier to an index on `ORDER_DATE`:

```sql
SELECT order_id
FROM orders
WHERE order_date >= DATE '2026-03-01'
  AND order_date <  DATE '2026-03-02';
```

This keeps a range predicate on the original column and avoids applying TRUNC to every column value. If semantics involve timezones or timestamp types, construct the time boundaries to match business rules.

### 10.4. Avoiding implicit conversion

If a column is NUMBER, bind a NUMBER value. If a column is DATE, bind a DATE. Do not compare a NUMBER to a string or a DATE to an environment-dependent formatted string.

Example to avoid:

```sql
WHERE customer_id = '1001'
```

Prefer:

```sql
WHERE customer_id = :customer_id
```

with a NUMBER bind variable.

Implicit conversion can alter semantics, cause errors depending on NLS settings, or prevent an index expression from being used as expected.

### 10.5. Using bind variables

```sql
SELECT order_id
FROM orders
WHERE customer_id = :customer_id;
```

Bind variables reduce hard parses when the same SQL structure is executed with many values. However, bind peeking and data skew can make a single plan unsuitable for all values. Check child cursors, bind sensitivity, and adaptive cursor sharing before changing configuration.

### 10.6. Choosing composite indexes based on predicates

If a query commonly filters on:

```sql
WHERE tenant_id = :tenant_id
  AND status = :status
  AND created_at >= :from_time
```

You can evaluate an index such as `(tenant_id, status, created_at)`. Column order depends on predicates, selectivity, other queries, sorting, and DML workload. Do not create an index based on a single SQL statement while ignoring other queries sharing the table.

### 10.7. Reducing columns and rows read

Avoid `SELECT *` if only a few columns are needed. Reducing payload can cut I/O, memory, network, and client work. However, do not add overly wide covering indexes if storage/DML costs outweigh the benefits.

### 10.8. Partition pruning

If a table is partitioned by date and a query filters on the partition key, write clear predicates so Oracle can prune unneeded partitions. Verify whether the plan contains the appropriate partition range operation.

### 10.9. Checking JOIN cardinality

Before changing join methods, determine:
- Whether the relationship is one-to-one, one-to-many, or many-to-many.
- Whether unexpected duplicates exist.
- Whether JOIN predicates are complete.
- Statistics and cardinality estimates.
- Whether data can be filtered before the JOIN.

Do not add DISTINCT to hide a JOIN bug that creates duplicates without understanding the cause.

### 10.10. Avoiding optimizations that break semantics

SQL rewrites must preserve:
- NULL semantics.
- Duplicate rows.
- Outer join behavior.
- Timezone and date boundaries.
- Collation/NLS.
- Ordering if the application depends on order.
- Transaction isolation and concurrency.
- Error behavior on anomalous data.

A faster SQL query that returns different results is a bug, not an optimization.

## 11. Formulating and testing modification hypotheses

A good change begins with a testable hypothesis.

| Observation | Hypothesis | Trial change |
|---|---|---|
| `TRUNC(order_date)` in predicate | Index on date column is hard to use directly | Convert to range predicate |
| E-Rows much lower than A-Rows | Inaccurate cardinality estimate | Check stats/histograms and predicate correlation |
| 500,000 executions, small gets/exec | SQL is called too frequently | Review N+1 in application or batching |
| Nested loops iterating millions of times | Outer row count is larger than predicted | Check join order, filters, and join method |
| Full scan when only a few rows are needed | Unselective predicate or missing index | Review suitable index and stats |
| SQL has multiple child plans | Different bind/data distributions or environments | Analyze child cursors and bind groups |
| Query waiting on row lock | Another transaction holds the lock | Find blocker and transaction duration |

Change only one major factor at a time if possible. If you change indexes, statistics, SQL text, and optimizer parameters simultaneously, it is hard to tell which factor caused the improvement or regression.

## 12. Before/after testing workflow

### 12.1. Saving the baseline

Before making changes, save:
- SQL text.
- SQL_ID and child number.
- Plan hash value.
- Execution plan with runtime statistics.
- Representative bind values (with sensitive data sanitized).
- Executions.
- Elapsed, CPU, buffer gets, disk reads.
- Rows processed.
- Wait profile.
- Measurement timestamp and conditions.

### 12.2. Creating a test version

Depending on the change:
- Use a staging schema or database.
- Create a test index.
- Use separate SQL text or a SQL patch/test harness.
- Keep the old query version for rollback.
- Document DDL, statistics, and parameter changes.

Do not create indexes or change optimizer parameters in production solely for benchmarking without proper operational approval.

### 12.3. Running the same workload

Run with the same bind values and concurrency. If the workload spans multiple value groups, take a representative sample:
- Common values.
- Rare values.
- Small result sets.
- Large result sets.
- Boundary values.
- NULL or empty-result cases if allowed by business logic.

### 12.4. Comparing plans and runtime

Compare:
- Plan hash and operations.
- E-Rows/A-Rows.
- Starts and operation loop counts.
- Buffer gets.
- Physical reads.
- CPU and elapsed time.
- Waits.
- Rows returned/affected.
- DML redo and index maintenance.

A different plan hash does not automatically mean better. The same plan hash does not guarantee the same runtime. Conclusions must be based on actual results.

### 12.5. Benchmark table

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| Median elapsed | Measure | Measure | Calculate |
| p95 elapsed | Measure | Measure | Calculate |
| CPU per execution | Measure | Measure | Calculate |
| Buffer gets per execution | Measure | Measure | Calculate |
| Physical reads | Measure | Measure | Calculate |
| Rows returned | Measure | Measure | Must be equivalent |
| Executions/second | Measure | Measure | Calculate |
| Redo per transaction | Measure | Measure | Calculate |
| Error count | Measure | Measure | No abnormal increase |

Elapsed improvement percentage:

\[
\text{Improvement} =
\frac{\text{Before} - \text{After}}{\text{Before}} \times 100\%
\]

If the value is negative, the new version is slower. Always state the denominator and units; do not just report "30% faster" without benchmark conditions.

## 13. SQL Trace and TKPROF for a specific SQL statement

When you need to know how many times a SQL statement parses, executes, and fetches, and where time is spent, SQL Trace is very useful.

### 13.1. Enabling trace in a test session

```sql
ALTER SESSION SET SQL_TRACE = TRUE;

-- Run the procedure or workload to analyze.

ALTER SESSION SET SQL_TRACE = FALSE;
```

Or use `DBMS_SESSION`/`DBMS_MONITOR` to trace a session or service per DBA policy.

Trace files are written to the database server's diagnostic location. File names and paths are managed by Oracle; DBAs can locate them using the appropriate diagnostic views.

### 13.2. TKPROF

TKPROF formats a trace file into a readable report containing:
- Parse, execute, and fetch counts.
- CPU and elapsed time.
- Disk reads and query/current buffer gets.
- Rows processed.
- SQL text.

Example command run on a machine with an Oracle client:

```text
tkprof input_trace.trc output_report.txt sys=no sort=exeela,fchela
```

File paths are examples. Run TKPROF on a host with the appropriate Oracle tools and comply with trace/bind data protection policies.

### 13.3. When to use trace?

- A specific request is slow.
- You need to find repeated SQL inside a procedure.
- You want to separate parse, execute, and fetch phases.
- You need to see the exact SQL statements being issued.
- You want to compare call counts before and after.

Do not leave broad tracing enabled for too long because it incurs overhead and may capture sensitive information.

## 14. SQL Monitor and SQL Tuning Advisor

Some Oracle tools provide deeper SQL analysis, subject to version, privilege, and licensing conditions.

### 14.1. Real-Time SQL Monitoring

SQL Monitor can display progress and runtime details for long-running or parallel SQL execution, including operations, timing, I/O, and activity distribution. Automatic monitoring depends on thresholds and configuration.

Real-Time SQL Monitoring is a feature requiring verification of the Oracle Tuning Pack license under common licensing models. Check current terms before using it.

### 14.2. SQL Tuning Advisor

SQL Tuning Advisor can produce recommendations such as statistics, SQL profiles, or access structures depending on the situation. It is an assistive tool; DBAs must still evaluate correctness, cost, and licensing.

SQL Tuning Advisor belongs to the Oracle Tuning Pack under common licensing models. Do not run or enable a feature merely because the package exists without confirming usage rights.

### 14.3. Tools do not replace understanding the workload

An advisor may recommend an index without full awareness of its impact on all DML and other queries in the system. Recommendations must be benchmarked against the overall workload.

## 15. Checking statistics before modifying SQL

The optimizer uses statistics to estimate cardinality and choose a plan.

### 15.1. Table and index statistics

```sql
SELECT table_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats
FROM user_tab_statistics
WHERE table_name = 'ORDERS';
```

Check index statistics:

```sql
SELECT index_name,
       num_rows,
       leaf_blocks,
       distinct_keys,
       clustering_factor,
       last_analyzed
FROM user_ind_statistics
WHERE table_name = 'ORDERS';
```

Column and view names may vary by privilege or version. These metrics help clarify which statistics the optimizer is relying on.

### 15.2. Gathering statistics

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'ORDERS',
        cascade => TRUE
    );
END;
/
```

Do not gather statistics arbitrarily in production. Changing statistics can cause many SQL statements to switch plans simultaneously. Follow your statistics policy, check stale stats, incremental stats, and system maintenance windows.

### 15.3. Histograms and data skew

If a column has a heavily skewed distribution, a histogram can help the optimizer produce better estimates for different values. However:
- Histograms are not needed for every column.
- Bind variables and bind peeking affect plan selection.
- Adaptive cursor sharing can create child cursors per bind group.
- Statistics changes can alter plans beyond the SQL being tuned.

Do not create histograms or change `OPTIMIZER_FEATURES_ENABLE` just to force one query to run faster without analyzing the workload-wide impact.

## 16. Choosing indexes based on overall workload

Indexes help reads but make writes more expensive. Before adding an index, evaluate:
- Which queries will use the index?
- Does the predicate have sufficient selectivity?
- Does the index duplicate or nearly duplicate an existing index?
- Which column should lead a composite index?
- Impact on INSERT/UPDATE/DELETE?
- Storage and backup impact?
- Can the index serve multiple queries?
- Are there local/global partitions and pruning requirements?
- Is the clustering factor favorable?

An index that helps one SQL statement while slowing down all DML on the table may be a net negative for the workload.

### 16.1. Checking existing indexes

```sql
SELECT index_name,
       column_name,
       column_position,
       descend
FROM user_ind_columns
WHERE table_name = 'ORDERS'
ORDER BY index_name, column_position;
```

Also inspect uniqueness, status, visibility, and partition metadata before creating a new index.

### 16.2. Invisible indexes for testing

Oracle supports invisible indexes in corresponding releases. You can create an index as invisible to test optimizer scenarios with `OPTIMIZER_USE_INVISIBLE_INDEXES` in a test session. Invisible indexes are still maintained by DML and still consume storage; they are not free.

Do not use invisible indexes as a way to bypass write-cost evaluation or licensing checks. Confirm syntax and behavior for your release before deploying.

## 17. Change control and rollback capability

A SQL change can affect multiple features sharing the same table or view. Therefore, manage it as a verifiable engineering change.

### 17.1. Recording a change record

Each change should include:
- SQL_ID/SQL text or related feature.
- Problem statement and baseline metrics.
- Root cause hypothesis.
- Specific modification.
- Index/statistics/parameter changes.
- Before/after results.
- Tested bind groups.
- Risks and blast radius.
- Rollback plan.
- Approver and deployment window per team process.

### 17.2. Changing one explainable group of factors at a time

If you change SQL text, indexes, statistics, and optimizer parameters at once, attributing the improvement becomes very difficult. Separating changes helps:
- Identify which factor produced the gain.
- Detect regressions.
- Roll back precisely.
- Preserve engineering knowledge.

### 17.3. Verifying correctness

Compare before/after results:
- Row count returned.
- Content and data types.
- Duplicates.
- NULL handling.
- Ordering if `ORDER BY` is present and the application depends on it.
- Results across different bind values.
- Transaction and locking behavior.
- Error behavior.

You can use two-way `MINUS` on suitable result sets for comparison, keeping in mind LOB data types, ordering, and comparison semantics. For large datasets, build checksums or validate by business keys.

### 17.4. Rollback plan

- Keep the old SQL.
- Know how to drop/disable test indexes if needed.
- Save statistics state or use statistics restore mechanisms per policy.
- Do not drop old indexes immediately after deployment until after an observation period.
- Define rollback thresholds such as increased p95, increased CPU, or increased errors.
- Assign an owner responsible for post-deployment monitoring.

## 18. Re-measuring under real load and watching for regressions

A query running faster in staging is not enough. After deployment, monitor:
- p50/p95/p99 latency.
- Throughput.
- DB CPU and host CPU.
- Buffer gets and physical reads.
- Wait events.
- Parse rate and child cursors.
- DML latency on tables with new indexes.
- TEMP and PGA if joins/sorts changed.
- Error rate and business outcomes.
- Other SQL statements sharing the same table or service.

A change can improve the target SQL while slowing down another query group. Monitor all related workloads.

### 18.1. Setting acceptance thresholds

Example project conventions:
- p95 reduced by at least 20%.
- CPU per execution does not increase beyond an agreed threshold.
- Rows returned must match.
- No increase in errors.
- DML throughput does not degrade beyond limits.
- No other batch misses its SLA.

These thresholds are examples; the project team must define them according to SLAs and system capacity.

### 18.2. Do not keep an optimization just because one metric looks good

If elapsed time drops while CPU doubles and total throughput decreases, the change may be harmful. If buffer gets decrease while user latency stays flat due to lock waits, address the actual root cause. Decide based on system-wide goals rather than a single isolated number.

## 19. End-to-end practical workflow

Suppose the order search API is slow during peak hours.

### Step 1. Tag module/action

The application or test session sets:

```sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_API',
        action_name => 'SEARCH_ORDERS'
    );
END;
/
```

This separates SQL from the order search feature from other workloads.

### Step 2. Collect critical SQL

Within the defined measurement window:

```sql
SELECT sql_id,
       plan_hash_value,
       executions,
       ROUND(elapsed_time / 1e6, 2) AS elapsed_s,
       ROUND(cpu_time / 1e6, 2) AS cpu_s,
       buffer_gets,
       disk_reads,
       module,
       action
FROM v$sql
WHERE module = 'ORDER_API'
  AND action = 'SEARCH_ORDERS'
  AND executions > 0
ORDER BY elapsed_time DESC;
```

These are cumulative metrics in the shared pool. If an exact time interval is needed, capture before/after snapshots or use an appropriate historical tool.

### Step 3. Inspect SQL text and child cursors

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       sql_fulltext
FROM v$sql
WHERE sql_id = :sql_id;
```

Check multiple child cursors and plan hashes if present.

### Step 4. Retrieve the runtime plan

Run the SQL in a test session with runtime statistics enabled, then:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :sql_id,
        :child_number,
        'ALLSTATS LAST +PREDICATE'
    )
);
```

Check E-Rows/A-Rows, buffer gets, and high-cost operations.

### Step 5. Formulate a hypothesis

For example, the plan shows `TRUNC(created_at)` in the predicate and a full scan on a large table. Hypothesis: applying a function on the date column prevents the existing index from being used directly.

### Step 6. Modify the query in a test environment

Old query:

```sql
SELECT order_id, created_at
FROM orders
WHERE TRUNC(created_at) = :order_day;
```

Test query:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= :order_day
  AND created_at <  :order_day + 1;
```

`:order_day` must be bound as a DATE and normalized to the start of the day according to timezone/business rules.

### Step 7. Re-run the same workload

Use the same data, bind values, concurrency, and iteration count. Record the plan, elapsed time, CPU, buffers, reads, and row counts.

### Step 8. Compare results

Verify both queries return the same row set and timestamps. Compare the runtime plan and metrics.

### Step 9. Test under concurrency

Run many concurrent search requests. Check p95/p99, throughput, and impact on write operations.

### Step 10. Deploy and monitor

Deploy following the release process. Keep the old SQL and rollback plan. Monitor metrics and roll back if agreed thresholds are breached.

## 20. Before-and-after report template

A short tuning report should be sufficient for others to understand why the change is valuable.

### 20.1. General information

| Field | Value |
|---|---|
| Feature | Example: search orders |
| SQL_ID | Record SQL_ID |
| Child cursor | Record child number |
| Plan hash before/after | Record both values |
| Measurement window | Timestamp and duration |
| Environment | Version, service, concurrency |
| Bind group | Representative parameter group |

### 20.2. Results

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| Executions | Measure | Measure | — |
| Median elapsed | Measure | Measure | % |
| p95 elapsed | Measure | Measure | % |
| CPU per execution | Measure | Measure | % |
| Buffer gets per execution | Measure | Measure | % |
| Physical reads | Measure | Measure | % |
| Rows returned | Measure | Measure | Must be equivalent |
| Throughput | Measure | Measure | % |
| DML impact | Measure | Measure | % |

### 20.3. Evidence-based conclusion

Document clearly:
- What the initial problem was.
- Evidence in the plan/metrics.
- The specific change made.
- Which metrics improved and by how much.
- Which metrics degraded.
- Whether semantics remained identical.
- Tested bind/concurrency scope.
- Conditions to monitor post-deployment.

Do not write "SQL is optimized" based only on a single faster run without a baseline or result verification.

## 21. Common mistakes

| Mistake | Why it is problematic | Better approach |
|---|---|---|
| Fixing the slowest SQL by intuition | May have low business impact or run only once | Combine resources, frequency, and SLA |
| Measuring elapsed time only once | Noise from cache, scheduling, and load | Run repeatedly, use median/percentiles |
| Testing only one bind value | May miss data skew | Use multiple representative bind groups |
| Looking only at EXPLAIN PLAN | Does not fully reflect runtime | Use DISPLAY_CURSOR with actual stats |
| Assuming full scan is always bad | Full scan can be cheaper when reading most of a table | Compare cost and runtime |
| Adding an index as soon as a full scan is seen | Can increase DML and storage costs | Review selectivity and overall workload |
| Creating indexes for every predicate | Too many indexes increase write cost | Select indexes for critical queries |
| Ignoring child cursors | Different plans may exist per bind | Analyze SQL_ID/child/plan hash |
| Gathering stats arbitrarily in production | Can change plans for many SQLs | Follow stats policy and plan ahead |
| Comparing two runs with different data | Unfair comparison | Use equivalent snapshots and binds |
| Testing only one session | Misses contention | Test near-realistic concurrency |
| Using hints to force plans immediately | Can mask root causes and cause regressions | Understand optimizer estimates first |
| Skipping result verification | Faster query with wrong semantics | Compare data and edge cases |
| Having no rollback plan | Hard to recover on regression | Keep old version and rollback thresholds |
| Using AWR/ASH/SQL Monitor without checking license | May violate licensing terms | Confirm usage rights per release/contract |

## 22. Tool selection guide

| Question | Tool |
|---|---|
| Which SQL consumes the most resources in the shared pool? | V$SQL |
| Which feature does the SQL belong to? | MODULE/ACTION, service, and application logs |
| Which SQLs does a single request invoke? | SQL Trace/TKPROF |
| What is the actual execution plan? | DBMS_XPLAN.DISPLAY_CURSOR |
| Why are row estimates inaccurate? | E-Rows/A-Rows, statistics, histograms |
| How does workload change over time? | AWR if licensed, or Statspack |
| Where are sessions waiting? | ASH if licensed, or appropriate session/wait views |
| How are long/parallel SQLs running? | SQL Monitor if licensed |
| Which PL/SQL subprogram takes the most time? | DBMS_HPROF or appropriate profiler |
| Is the change actually better? | Before/after benchmark on the same workload |

## 23. Operational SQL tuning checklist

Before making changes:
- Affected feature and SLA identified.
- Baseline and measurement window established.
- SQL_ID, child cursor, and plan hash captured.
- Representative bind values prepared.
- Elapsed, CPU, gets, reads, executions, and waits reviewed.
- Current data, statistics, and indexes understood.

During the change:
- Evidence-based hypothesis documented.
- Change scope kept small.
- Semantics preserved.
- Impact on DML and related SQL checked.
- Rollback mechanism available.

After the change:
- Same workload re-run.
- Plan and runtime statistics compared.
- Multiple bind groups verified.
- Concurrency and percentiles measured.
- Data output verified for equality.
- Post-deployment regressions monitored.
- Before/after report saved.

## 24. Self-check questions

**Question 1.** Why must SQL tuning start from the workload?

**Answer:** Because you need to know which SQL statements actually impact the system, what resources they consume, and how they affect business operations before choosing a fix.

**Question 2.** How does elapsed time differ from CPU time?

**Answer:** Elapsed time is the wall-clock time the caller waits; CPU time is the time the CPU actually spends executing. Differences can come from I/O, locks, or other waits.

**Question 3.** Why shouldn't you rank solely by total elapsed time?

**Answer:** A SQL running a few times can have high total elapsed time; a SQL running very frequently even if cheap per call can also create heavy load.

**Question 4.** What kind of metrics does V$SQL store?

**Answer:** Cumulative execution statistics of cursors in the shared pool, such as executions, elapsed time, CPU time, buffer gets, reads, and plan hash.

**Question 5.** Why is V$SQL not a complete workload history?

**Answer:** Cursors can be aged out or reloaded; statistics are tied to the active cursor and can reset.

**Question 6.** How do SQL_ID and PLAN_HASH_VALUE differ?

**Answer:** SQL_ID identifies the statement; PLAN_HASH_VALUE helps identify the execution plan shape.

**Question 7.** What are E-Rows and A-Rows used for?

**Answer:** Comparing the optimizer's estimated row counts with actual row counts to detect cardinality misestimates.

**Question 8.** Is a full table scan always bad?

**Answer:** No. If a query needs most of the data or the table is small, a full scan can be cheaper than index lookups.

**Question 9.** Why are multiple bind value groups needed?

**Answer:** Data distribution can be skewed; a plan good for common values may perform poorly for rare values.

**Question 10.** How do SQL Trace/TKPROF help?

**Answer:** They show parse/execute/fetch counts, timing, I/O, and SQL statements executed within the traced workload.

**Question 11.** Do AWR and ASH require license verification?

**Answer:** Yes. Usage must be checked against Oracle terms and your system's contract.

**Question 12.** Why can adding an index slow down the system?

**Answer:** Indexes increase storage and maintenance cost during INSERT/UPDATE/DELETE, and can also introduce contention.

**Question 13.** Why is concurrency measurement necessary?

**Answer:** A SQL statement that runs faster in isolation may contend for CPU, I/O, or indexes when many sessions run concurrently.

**Question 14.** Does an identical plan hash guarantee identical runtime?

**Answer:** No. Data, bind values, cache state, concurrency, and system conditions can differ.

**Question 15.** What should be compared after modifying SQL?

**Answer:** Plan, elapsed time, CPU, buffer gets, physical reads, rows, throughput, waits, and DML impact, while verifying equivalent business results.

**Question 16.** Why must there be a rollback plan?

**Answer:** Because a change may cause regressions on other workloads or under real load; a rollback enables fast, controlled recovery.

## 25. Conclusion

Effective SQL tuning is a measured loop: define workload goals, collect a baseline, select high-impact SQL statements, analyze the SQL_ID and execution plan, form a hypothesis, modify in a controlled environment, and re-run the same workload to compare. V$SQL is useful for current cursor statistics; SQL Trace/TKPROF analyzes a single request; DBMS_XPLAN reveals plans and runtime statistics. AWR, ASH, SQL Monitor, and SQL Tuning Advisor can provide additional insights, provided usage rights under Oracle licensing are verified.

When selecting critical SQL, combine total resources, per-execution cost, frequency, p95/p99, and business impact. When fixing, start from proven root causes: predicates, join cardinality, statistics, indexes, bind values, partition pruning, or SQL call counts. Do not assume full scans are always bad, do not add indexes by intuition, and do not force plans before understanding the optimizer.

A change is only considered successful when it improves the target metrics in a representative workload, preserves identical results, and introduces no unacceptable regressions for related SQL or DML. Save baselines, document change records, define rollback thresholds, and monitor after deployment so every tuning effort is explainable, repeatable, and verifiable.
