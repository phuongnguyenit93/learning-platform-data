# Parallel Execution, Degree of Parallelism, and Resource Oversubscription Risks in Oracle

## 1. What Problem Does Parallel Execution Solve?

Parallel execution (PX) allows Oracle to split parts of a SQL statement's work into multiple pieces and execute them concurrently across multiple parallel execution servers. Instead of one process handling all data serially, a Query Coordinator (QC) coordinates workers, distributes work, and gathers results.

PX is useful for workloads processing large volumes of data:
- Scanning and aggregating massive fact tables.
- Hash joins across large datasets.
- CTAS, index builds, or certain partition maintenance operations.
- Time-windowed batch ETL, reporting, and analytics.
- Partitioned data queries carrying sufficient work volume.

Running in parallel does not automatically make SQL faster. Every worker consumes CPU, memory, I/O, and other resources. Many workers operating concurrently can saturate CPU, spike TEMP, generate heavy I/O, contend on the buffer cache, or exhaust the parallel server pool and force other SQL statements to wait.

This lesson belongs to the **System Performance** chapter in the **Database Engine Relational Oracle** module. It focuses on PX architecture, **Degree of Parallelism (DOP)**, how Oracle chooses DOP, worker limits, statement queuing, Resource Manager, data distribution, parallel query, parallel DML, and measurement workflows to prevent resource oversubscription.

## 2. Components of the Parallel Execution Architecture

### 2.1. Query Coordinator (QC)

The QC is the process controlling a parallel SQL statement. The QC:
- Receives the statement from the user session.
- Determines the execution plan and chosen DOP.
- Requests parallel execution servers.
- Splits and coordinates operations.
- Exchanges data between worker sets.
- Collects results and returns them to the client.

The QC still performs part of the work. A parallel query does not mean workers execute every step; some coordination, final result handling, or non-PX-capable operations still run in the QC.

### 2.2. Parallel Execution Servers

A parallel execution server (PX server) is a worker process executing an assigned portion of work. Oracle acquires workers from the parallel execution server pool as needed.

One SQL statement may use one or multiple sets of PX servers across different stages. Workers can read data, perform joins/aggregations, or send rows to workers in the next operation.

Do not equate DOP with the exact total number of processes a SQL statement uses at any instant. DOP describes the parallelism level of an operation; an execution plan may allocate two server sets for producer/consumer roles at the same stage, so allocated PX servers can exceed DOP. Actual counts depend on the plan, operations, pipeline, and available resources.

### 2.3. Data Flow Operations (DFOs)

Oracle breaks a parallel execution plan into Data Flow Operations. A DFO can consist of one or more operations and is executed by a set of PX servers.

DFOs exchange data via table queues. For example:
1. One set of PX servers scans the `orders` table.
2. Workers distribute rows by join key.
3. Another worker set receives the rows and performs a hash join.
4. Results are sent to the QC to return to the client.

### 2.4. Processing Flow Diagram

```text
Client session
     |
     v
Query Coordinator (QC)
     |
     +---- PX server set A: scan / producer
     |          |
     |          +---- table queue (PX SEND)
     |                         |
     +---- PX server set B: join / aggregate (consumer)
                |
                +---- results sent back to QC
                             |
                             v
                           Client
```

This diagram illustrates a common pipeline. Actual execution plans can have multiple DFOs, multiple table queues, multiple server sets, or serial operations.

### 2.5. PX Server Pool

Oracle manages the pool of PX servers assignable to statements. Parameters such as `PARALLEL_MAX_SERVERS`, `PARALLEL_MIN_SERVERS`, and `PARALLEL_SERVERS_TARGET` govern pool allocation and management.

If a statement requests more workers than can be granted immediately, Oracle may downgrade DOP, queue the statement, or handle it according to configured policy. Exact behavior depends on `PARALLEL_DEGREE_POLICY`, Resource Manager, and release.

## 3. What Is Degree of Parallelism (DOP)?

DOP is the level of parallelism Oracle uses for an operation or statement. DOP 1 corresponds to serial execution; DOP greater than 1 allows dividing work across multiple PX servers.

Example:

```sql
SELECT /*+ PARALLEL(o 4) */
       customer_id,
       SUM(order_amount)
FROM orders o
WHERE order_date >= DATE '2026-01-01'
GROUP BY customer_id;
```

The hint asks Oracle to consider DOP 4 for table `o`. It is a directive/request to the optimizer, not a guarantee that every operation will always receive exactly four workers under all conditions.

### 3.1. DOP 4 Does Not Mean Only Four Processes Total

Within a DFO tree, Oracle can employ producer and consumer server sets. In some plans, each set receives DOP workers. Thus, a DOP 4 statement may use roughly eight PX servers across two concurrently active sets; this is a resource estimation rule of thumb, not a fixed constant for every plan.

When multiple statements run concurrently, PX server demand adds up. Four concurrent DOP 8 queries can demand a large number of workers depending on plan structure and server set counts.

### 3.2. DOP Is Not Dedicated CPU Cores

DOP does not pin one dedicated CPU core per worker. Multiple workers compete for CPU on the same host; the OS and Oracle scheduler distribute CPU time. If DOP exceeds useful CPU capacity, extra workers may simply add context switching and contention.

### 3.3. DOP and Data Size

A very large table does not automatically warrant high DOP. Consider:
- Number of blocks to read.
- Predicate selectivity.
- Partition pruning.
- Join and aggregation cost.
- Storage throughput.
- Headroom on CPU.
- Memory and TEMP.
- Other concurrent parallel statements.
- Workload completion deadline.

If a predicate returns only a handful of rows via an index unique scan, parallel query rarely offers meaningful benefit.

## 4. How Oracle Determines DOP

DOP can come from several sources:
- SQL hints.
- `PARALLEL` attribute on a table or index.
- Auto DOP policy.
- `ALTER SESSION FORCE PARALLEL QUERY`.
- Resource Manager and system limits.
- Optimizer decisions per version and configuration.

### 4.1. DOP Specified as an Object Attribute

```sql
ALTER TABLE sales PARALLEL 8;
```

The table is declared with degree 8. SQL statements accessing the table may be considered for parallel execution by the optimizer per current configuration and policies.

Return the table to serial default:

```sql
ALTER TABLE sales NOPARALLEL;
```

Object attributes are an input to the optimizer's decision, not a guarantee every SQL on that table runs at DOP 8. The optimizer still weighs cost, statement type, and parallel execution policy.

### 4.2. DOP via SQL Hint

```sql
SELECT /*+ PARALLEL(s 8) */
       region_id,
       SUM(amount)
FROM sales s
GROUP BY region_id;
```

You can specify hints per table alias. The alias inside the hint must match the alias in the `FROM` clause.

Related hint:

```sql
SELECT /*+ NO_PARALLEL(s) */ ...
FROM sales s;
```

`PARALLEL` and `NO_PARALLEL` are statement-scoped controls. Use hints once you understand the plan and need to control a specific workload; do not scatter hints everywhere as a substitute for measurement.

### 4.3. Session-Level FORCE PARALLEL QUERY

In a test environment:

```sql
ALTER SESSION FORCE PARALLEL QUERY PARALLEL 4;
```

This instructs the session to consider parallel execution for queries at the specified degree per Oracle semantics. It is session-scoped and affects subsequent queries executed in that session.

Disable forcing:

```sql
ALTER SESSION DISABLE PARALLEL QUERY;
```

Never enable `FORCE PARALLEL QUERY` on shared application sessions or connection pools without an explicit policy. One request can share the same session with the next request.

### 4.4. PARALLEL_DEGREE_POLICY

`PARALLEL_DEGREE_POLICY` controls Auto DOP behavior and certain parallel statement management features. Values and details can vary by Oracle release; check documentation for your exact version.

Common modes:

| Value | General Meaning |
|---|---|
| `MANUAL` | Does not automatically pick DOP via Auto DOP; relies on hints, object attributes, or explicit settings |
| `LIMITED` | Enables limited Auto DOP behavior scoped by object attributes/version policy |
| `AUTO` | Enables Auto DOP and parallel management mechanisms such as statement queuing where supported |
| `ADAPTIVE` | Mode present in some older releases; verify support/deprecation status by version |

Never change this parameter database-wide just to tune one query. Policy changes affect many workloads and must be tested in staging.

### 4.5. Auto DOP

When Auto DOP is enabled, Oracle estimates the cost/execution time of a SQL statement, decides whether to run in parallel, and picks a DOP within configured bounds.

Queries estimated to finish quickly remain serial; larger queries can receive higher DOP if policy and resources permit.

`PARALLEL_MIN_TIME_THRESHOLD` is one factor controlling the estimated time threshold at which Auto DOP considers parallel execution. Defaults and semantics vary by release. Never lower this threshold arbitrarily, as doing so can push many small SQL statements into parallel execution.

### 4.6. DOP Caps

`PARALLEL_DEGREE_LIMIT` and related limits can cap Auto DOP. Resource Manager can also enforce caps per consumer group.

DOP caps protect the database from a single SQL requesting excessive parallelism, but do not replace controlling concurrent statement counts.

## 5. Key PX Server Management Parameters

Parameter names and defaults depend on version, edition, instance configuration, and the CPU count visible to Oracle. Check live values before modifying anything.

### 5.1. PARALLEL_MAX_SERVERS

Maximum number of PX servers the instance may use per configuration.

```sql
SHOW PARAMETER parallel_max_servers;
```

Too low a limit forces statements to wait or downgrade below desired DOP. Too high a limit lets the system spawn excessive processes and burn heavy resources under concurrent load.

### 5.2. PARALLEL_MIN_SERVERS

Minimum number of PX servers Oracle keeps pre-spawned per pool policy. Keeping processes warm cuts startup overhead for frequent PX workloads, while consuming background resources.

```sql
SHOW PARAMETER parallel_min_servers;
```

### 5.3. PARALLEL_SERVERS_TARGET

A key threshold for parallel server management and statement queuing in supported configurations. When PX demand exceeds the target, Oracle can queue statements instead of allocating workers unboundedly right away.

```sql
SHOW PARAMETER parallel_servers_target;
```

The target is a load-coordination mechanism. It is not an absolute worker ceiling usable by every workload in every case; interpret it alongside `PARALLEL_MAX_SERVERS`, Resource Manager, and policy.

### 5.4. CPU_COUNT and PARALLEL_THREADS_PER_CPU

These parameters influence how Oracle perceives CPU capacity and computes default parallelism under certain policies.

```sql
SHOW PARAMETER cpu_count;
SHOW PARAMETER parallel_threads_per_cpu;
```

Never set `CPU_COUNT` higher than the CPUs the instance is actually permitted to use. Misconfiguration causes the optimizer and parallel execution to overestimate available compute capacity.

### 5.5. Inspecting Parameters Together

```sql
SELECT name, value
FROM v$parameter
WHERE name IN (
    'parallel_degree_policy',
    'parallel_degree_limit',
    'parallel_min_time_threshold',
    'parallel_max_servers',
    'parallel_min_servers',
    'parallel_servers_target',
    'parallel_threads_per_cpu',
    'cpu_count'
)
ORDER BY name;
```

Read access to `V$PARAMETER` is required. Never copy values from another environment as a standard; size according to your own CPU, storage, concurrency, and workload.

## 6. Statement Queuing: Queuing to Protect Resources

When many SQL statements request PX simultaneously, granting workers to all of them at once can overload the database. Statement queuing lets Oracle queue SQL statements and start them only when sufficient resources are available per policy.

### 6.1. Why Queuing Beats Oversubscription

Suppose a database can sustain a certain number of PX workers. If ten reports simultaneously demand high DOP, granting all concurrently can:
- Oversubscribe CPU.
- Increase context switching.
- Slow down every single report.
- Lengthen I/O queues and spike TEMP.
- Degrade OLTP workloads.

Queuing some statements allows active ones to finish faster and improves overall workload throughput.

### 6.2. Related Configuration

Statement queuing is typically tied to the parallel degree policy and `PARALLEL_SERVERS_TARGET`. Exact configuration depends on version and Resource Manager.

Do not enable `AUTO` solely for queuing without measuring wait times and concurrency. Queuing controls load, yet can raise individual request latency if applications do not account for queue wait time.

### 6.3. Monitoring Queued Statements

Session and PX views help identify statements running in parallel and workers requested/granted. Queue and Resource Manager details appear in version-appropriate performance views.

During investigation, record:
- Time spent queued.
- Requested DOP.
- Granted DOP.
- PX servers in use.
- Number of competing statements.
- CPU, I/O, and Resource Manager consumer group.

### 6.4. Queue Timeouts and Applications

If applications enforce short timeouts, queued statements may hit client timeouts before starting execution. Align:
- Request SLAs.
- JDBC/OCI/client timeouts.
- Queue wait tolerances.
- Batch windows.
- Retry policies.

Immediately retrying a queued statement worsens load. If retries are required, use backoff and cap retry attempts.

## 7. Resource Manager and Controlling Parallel Workloads

Database Resource Manager allocates resources by consumer group, priority, and limits. It is essential when OLTP, reporting, and batch share the same database.

### 7.1. Separating Workloads by Consumer Group

Example classification:
- `OLTP_CRITICAL`: critical interactive transactions.
- `REPORTING`: large read reports.
- `BATCH_ETL`: scheduled batch jobs.
- `ADHOC_ANALYTICS`: ad hoc queries.

Each group can receive distinct priorities, CPU shares, parallel server limits, or DOP caps depending on release capabilities and Resource Manager plans.

### 7.2. Limiting Parallel Servers per Group

Resource Manager includes directives governing parallel server usage and DOP caps per consumer group, such as limiting parallel server percentages or maximum DOP. Check exact directive names and settings in Oracle documentation for your release.

Goals:
- Prevent reports from starving the PX server pool.
- Shield OLTP from ad hoc queries.
- Allow batch jobs higher resource usage within scheduled windows.
- Keep group behavior predictable under heavy load.

### 7.3. Do Not Use DOP as a Substitute for Workload Governance

Even if every SQL statement is capped at DOP 4, hundreds of concurrent statements can still overwhelm the database. Control all of:
- Concurrent session counts.
- Per-statement DOP.
- Workers per DFO.
- Consumer groups.
- CPU and I/O.
- TEMP and PGA.
- Queuing and timeouts.

## 8. How Parallel Execution Divides Work

### 8.1. Granules

Oracle divides data into units of work called granules for PX servers to process. Depending on operation and table structure, granules can be based on:
- Block ranges.
- Partitions or subpartitions.
- Other work units managed by the execution engine.

Each worker claims a granule and processes it independently within the operation. Well-balanced granules keep workers evenly utilized.

### 8.2. Partition Granules

For partitioned tables, Oracle can divide work by partition/subpartition. Partition-wise joins can eliminate data redistribution when two tables are compatibly partitioned on the join key.

If there are fewer partitions than DOP, or data is concentrated in a few partitions, effective parallelism may be limited or skewed.

### 8.3. Block-Range Granules

For certain scans, Oracle divides block ranges into multiple granules for workers to pull. This enables parallel execution even when a table is not partitioned into many units.

### 8.4. Data Skew

Skew occurs when data or work distributes unevenly across workers. For instance, one `region_id` value accounts for 80% of rows; hash distribution by region forces one worker to process most of the data.

Consequences:
- Several workers finish early and sit idle.
- The slowest worker dictates overall operation completion time.
- High DOP yields poor throughput scaling.
- One worker consumes far more memory/TEMP than others.
- Table queues can bottleneck.

Raising DOP does not fix data skew. Examine distribution keys, cardinalities, skewed values, and distribution methods.

## 9. PX Data Distribution and Table Queues

When two worker sets exchange rows, Oracle uses `PX SEND` and `PX RECEIVE` operations.

### 9.1. HASH Distribution

Data is distributed by hashing one or more keys. This is commonly used to route rows with matching join keys to the same worker for hash joins or `GROUP BY`.

If keys are heavily skewed, a subset of workers receives disproportionately more rows.

### 9.2. BROADCAST Distribution

A small dataset is sent to every worker to join against larger datasets. Broadcast works well when one side is small, yet replicates data across many workers and inflates memory/network traffic if the broadcast side is larger than estimated.

### 9.3. RANGE Distribution

Data is split by value ranges, supporting certain sorts or range-oriented operations. Balance depends on data distribution.

### 9.4. RANDOM Distribution

Data is distributed roughly randomly across workers in applicable operations. It balances row counts, though not necessarily per-row size or processing cost.

### 9.5. Reading Operations in Execution Plans

Common operations:
- `PX COORDINATOR`: QC orchestrating parallel execution.
- `PX SEND`: sending rows through a table queue.
- `PX RECEIVE`: receiving rows from a table queue.
- `PX BLOCK ITERATOR`: distributing block-range granules.
- `PX SEND HASH`: distributing by hash key.
- `PX SEND BROADCAST`: broadcasting data.
- `PX SEND RANGE`: distributing by range.
- `PX PARTITION`: operations tied to partition-wise processing.

Never judge a plan by operation names alone. Inspect row counts, bytes, starts, waits, skew, and per-stage time.

## 10. Parallel Query and Parallel DML

### 10.1. Parallel Query

Parallel Query primarily speeds up reading and query processing. Example:

```sql
SELECT /*+ PARALLEL(s 8) */
       product_id,
       SUM(quantity_sold)
FROM sales s
WHERE sale_date >= DATE '2026-01-01'
GROUP BY product_id;
```

Appropriate when scanning/aggregating large data volumes, with spare CPU/I/O and compatible SLAs.

### 10.2. Parallel DML Must Be Enabled

Parallel DML does not automatically activate merely because a table has the `PARALLEL` attribute. The session or statement must enable PDML via supported Oracle mechanisms.

Example in a lab session:

```sql
ALTER SESSION ENABLE PARALLEL DML;
```

Or statement-level hint depending on version:

```sql
INSERT /*+ ENABLE_PARALLEL_DML PARALLEL(target_table 4) */
INTO target_table (id, amount)
SELECT id, amount
FROM source_table;
```

Hint syntax requires valid aliases and version support. Disable via:

```sql
ALTER SESSION DISABLE PARALLEL DML;
```

### 10.3. Parallel INSERT Example

```sql
ALTER SESSION ENABLE PARALLEL DML;

INSERT /*+ PARALLEL(t 4) */
INTO sales_archive t
SELECT /*+ PARALLEL(s 4) */
       s.sale_id,
       s.product_id,
       s.quantity,
       s.sale_date
FROM sales s
WHERE s.sale_date < DATE '2025-01-01';

COMMIT;
```

This is an illustrative example. Check table definitions, partitioning, constraints, triggers, logging, transactions, and PDML restrictions before running.

### 10.4. Parallel UPDATE and DELETE

Workloads updating or deleting massive row counts may benefit from PDML:

```sql
ALTER SESSION ENABLE PARALLEL DML;

UPDATE /*+ PARALLEL(s 4) */
       sales s
SET s.archive_flag = 'Y'
WHERE s.sale_date < DATE '2025-01-01';

COMMIT;
```

PDML can generate heavy concurrent undo/redo and write I/O. When updating most of a table, compare against controlled partition-by-partition or range-based batching.

### 10.5. ORA-12838 After Parallel DML

After modifying a table with parallel DML in a transaction, certain subsequent operations accessing the same table before `COMMIT`/`ROLLBACK` can raise `ORA-12838` under Oracle rules.

```sql
ALTER SESSION ENABLE PARALLEL DML;

UPDATE /*+ PARALLEL(t 4) */
       target_table t
SET status = 'DONE'
WHERE batch_id = 100;

-- Do not assume you can query this table again in the same transaction.
COMMIT;

SELECT COUNT(*)
FROM target_table
WHERE batch_id = 100;
```

`COMMIT` establishes a clear transaction boundary. Never insert `COMMIT` inside stored procedures merely to sidestep errors if transaction control belongs to the caller.

### 10.6. PDML Restrictions

Parallel DML carries numerous restrictions depending on table type, indexes, triggers, constraints, partitioning, distributed transactions, and Oracle version. Certain operations silently downgrade to serial or are unsupported in parallel.

Before designing PDML, consult the SQL Language Reference and Data Warehousing Guide for your release. Inspect the execution plan/runtime stats to verify Oracle actually executed DML in parallel.

## 11. When Does Parallel Execution Pay Off?

PX is generally worth evaluating when:
- Queries process large data volumes.
- Work splits cleanly into independent chunks.
- CPU and I/O headroom exist.
- Enough PX servers are available.
- Data is reasonably balanced.
- Results must finish faster than a single serial execution allows.
- The workload can absorb worker startup and data-exchange overhead.

Examples: scanning and aggregating huge fact tables, hash joins between large tables, building indexes on large tables during maintenance windows, CTAS or batch archiving, and analytical reporting outside peak OLTP hours.

## 12. When Should High DOP Be Avoided?

### 12.1. Small Queries or Few Rows Returned

Worker startup, coordination, and data-exchange overhead can outweigh actual work. Index unique lookups rarely benefit from high DOP.

### 12.2. Latency-Sensitive OLTP

OLTP transactions typically touch few rows and demand consistent latency. Many OLTP sessions invoking PX can starve interactive requests of resources.

### 12.3. CPU Already Saturated

When CPU is near saturation, raising DOP increases worker contention. Individual statement elapsed times can rise while overall throughput drops.

### 12.4. Storage Already at Capacity

Parallel scans can saturate storage throughput, slowing down other workloads. Adding workers cannot speed up storage once hardware limits are reached.

### 12.5. Data Skew

If one worker receives most of the data, high DOP still leaves that single slow worker dragging out the entire statement. Check rows/bytes per worker and table queues.

### 12.6. Insufficient PGA or TEMP

Parallel hash joins and sorts spawn many concurrent work areas. Without enough memory, operations spill to TEMP and spike I/O. Raising DOP multiplies competing work areas and worsens pressure.

### 12.7. Many Concurrent Parallel Statements

A DOP 16 query might perform nicely in isolation yet overload the system when dozens of reports run together. Test under realistic concurrency and enforce controls via queuing/Resource Manager.

## 13. Resource Oversubscription Risks

### 13.1. CPU Oversubscription

Too many active PX servers push runnable processes past CPU capacity. Consequences:
- Rising context switching.
- Higher CPU time and elapsed time.
- Degraded OLTP latency.
- Flat or falling throughput despite higher DOP.

### 13.2. PGA and TEMP Pressure

Each worker can allocate private work areas. For hash joins or sorts, many concurrent workers multiply total memory demand. When PGA is insufficient, Oracle spills to TEMP.

Monitor:
- PGA allocated/used.
- Work area executions (optimal/one-pass/multipass).
- TEMP usage.
- `direct path read/write temp`.
- Hash/sort operations and worker counts.

### 13.3. I/O Amplification

PX scans drive concurrent reads across many processes. While this can boost throughput if storage has headroom, it can also:
- Drive up storage latency.
- Lengthen I/O queues.
- Contend with redo, archiving, and other workloads.
- Increase physical reads and bandwidth consumption.

### 13.4. RAC Interconnect

In RAC, PX workers can span multiple instances. Exchanging rows across instances raises interconnect traffic. Consider PX instance placement, data locality, and cluster configuration.

### 13.5. Parallel Server Pool Exhaustion

If too many statements demand PX, the pool runs out of idle workers. Subsequent statements queue, downgrade DOP, or fail to obtain requested workers depending on policy. Ad hoc workloads can starve critical reports or batch jobs if resource governance is absent.

### 13.6. DML Side Effects

PDML can amplify:
- Undo and redo generation.
- Write I/O.
- Locking and contention on related structures.
- Index maintenance overhead.
- Recovery or replication apply lag.
- Temporary space requirements.

Never measure only SELECTs when rolling out PDML.

## 14. Monitoring Parallel Execution in Oracle

### 14.1. V$PX_SESSION

`V$PX_SESSION` displays session metadata for parallel execution, showing QC and workers:

```sql
SELECT sid,
       serial#,
       qcsid,
       qcinst_id,
       server_group,
       server_set,
       server#,
       degree,
       req_degree
FROM v$px_session
ORDER BY qcinst_id, qcsid, server_group, server_set, server#;
```

Columns:
- `QCSID`: SID of the Query Coordinator.
- `QCINST_ID`: QC's instance in RAC.
- `SERVER_GROUP` and `SERVER_SET`: PX server group/set.
- `SERVER#`: worker sequence number within the set.
- `DEGREE`: granted DOP per the view.
- `REQ_DEGREE`: requested DOP.

Filter by the QC SID of the statement under investigation. Read privileges on dynamic performance views are required.

### 14.2. V$PX_PROCESS

```sql
SELECT server_name,
       status,
       pid,
       spid,
       sosid
FROM v$px_process
ORDER BY status, server_name;
```

This view reports PX process states per version and privileges, helping identify active vs. available workers.

### 14.3. V$PX_PROCESS_SYSSTAT

```sql
SELECT statistic,
       value
FROM v$px_process_sysstat
WHERE statistic IN (
    'Servers In Use',
    'Servers Available',
    'Servers Highwater',
    'Servers Started',
    'Servers Shutdown'
)
ORDER BY statistic;
```

These are system statistics per view semantics. Take before/after snapshots for deltas; do not treat highwater as current load.

### 14.4. V$PQ_TQSTAT

`V$PQ_TQSTAT` provides table queue statistics for the last parallel query executed in the session. It helps inspect rows/bytes flowing through table queues and imbalances across workers.

```sql
SELECT dfo_number,
       tq_id,
       server_type,
       instance,
       num_rows,
       bytes
FROM v$pq_tqstat
ORDER BY dfo_number, tq_id, server_type, instance;
```

Visibility and timing depend on version and execution mode. Use these metrics to spot heavy queues or uneven worker distribution.

### 14.5. V$SQL and Runtime Plans

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       px_servers_executions,
       elapsed_time,
       cpu_time,
       buffer_gets,
       disk_reads
FROM v$sql
WHERE sql_id = :sql_id;
```

Columns and semantics vary by release. Combine with runtime plans:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :sql_id,
        :child_number,
        'ALLSTATS LAST +PARALLEL +PREDICATE'
    )
);
```

Plans reveal PX operations; runtime statistics compare estimates against actuals.

### 14.6. SQL Monitor

SQL Monitor displays per-operation and per-worker progress for long-running or parallel executions in supported setups. It is invaluable for spotting lagging workers, time-consuming operations, and I/O volume.

Real-Time SQL Monitoring generally falls under the Oracle Tuning Pack per standard licensing. Check usage rights in the Licensing Information User Manual and your contracts before using related reports or views.

## 15. Reading Parallel Execution Plans

### 15.1. Inspecting DOP and PX Operations

Run a test query, then:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PARALLEL +PREDICATE'
    )
);
```

In the plan, watch for:
- `PX COORDINATOR`.
- `PX SEND`/`RECEIVE`.
- `PX BLOCK ITERATOR`.
- `PX PARTITION`.
- Scan, join, and aggregate operations placed before/after table queues.

### 15.2. Verifying Granted Workers

Requested DOP can differ from granted DOP. Check `V$PX_SESSION` while the statement executes or use SQL Monitor if licensed. Never assume full worker allocation based solely on an estimated plan.

### 15.3. Checking for Skew

When per-worker or table-queue stats are available, compare:
- Rows per worker.
- Bytes per worker.
- Completion time per server set.
- Any worker handling an outsized share of data.
- An operation waiting longer than the rest.

Severe skew typically turns one worker into the bottleneck.

### 15.4. Do Not Judge Solely by DOP in the Plan

A plan showing DOP 16 does not prove it runs four times faster than DOP 4. Check elapsed time, CPU, I/O, queue time, actual rows, and concurrency. High DOP can multiply resource burn without proportional speedup.

## 16. Safe DOP Selection Process

### Step 1. Define the Workload Goal

Clarify whether the goal is lowering latency of one report, boosting batch throughput, or protecting OLTP stability. Identify SLAs and run windows.

### Step 2. Measure the Serial Baseline

Run at DOP 1 or current configuration under representative conditions. Record:
- Elapsed time.
- CPU time.
- Buffer gets.
- Physical reads.
- Rows processed.
- TEMP/PGA.
- Wait events.
- Overall throughput.

### Step 3. Assess Available Headroom

Evaluate CPU, storage, PGA, TEMP, PX server pool, and concurrent workloads. If resources are already saturated, raising DOP is rarely the right first move.

### Step 4. Test Increasing DOP Gradually

In staging or a controlled test window, test incremental levels such as 2, 4, and 8. Avoid jumping straight to very high DOP.

### Step 5. Measure Under Identical Workloads

Keep data, bind values, concurrency, and cache state constant. Record both requested DOP and granted DOP.

### Step 6. Identify Diminishing Returns

If moving from DOP 4 to DOP 8 trims elapsed time by only 5% while nearly doubling CPU, DOP 8 may not be worthwhile. Choose the level meeting SLAs at the lowest total resource cost.

### Step 7. Test Under Concurrent Load

Run alongside production-like session counts and competing workloads. Check OLTP p95/p99 latency, queue times, PX server usage, and storage latency.

### Step 8. Set Limits and Monitor

Configure appropriate DOP caps, consumer groups, or statement queuing. Monitor post-deployment and define rollback thresholds.

## 17. DOP Comparison Example

Suppose a report scans and aggregates a large dataset. Illustrative results:

| DOP | Elapsed | Total CPU | Buffer gets | TEMP | Assessment |
|---:|---:|---:|---:|---:|---|
| 1 | 240 s | 210 s | 12M | 2 GB | Serial, slow |
| 2 | 135 s | 235 s | 12M | 2.5 GB | Good improvement |
| 4 | 78 s | 270 s | 12.5M | 3 GB | Efficient |
| 8 | 52 s | 390 s | 14M | 6 GB | Faster, heavy CPU/TEMP cost |
| 16 | 49 s | 700 s | 16M | 13 GB | Tiny gain, steep resource jump |

Numbers are purely illustrative, not universal Oracle benchmarks. Here DOP 8 or 16 makes the individual report faster, yet DOP 16 saves only 3 seconds over DOP 8 while exploding CPU and TEMP usage. If the system also serves OLTP, DOP 8 or 4 may be the better overall choice depending on SLAs.

### 17.1. Calculating Speedup and Efficiency

Speedup:

\[
\text{Speedup}(D) = \frac{T_1}{T_D}
\]

Parallel efficiency:

\[
\text{Efficiency}(D) = \frac{T_1}{D \times T_D}
\]

Where:
- \(T_1\): serial execution time.
- \(T_D\): execution time at DOP \(D\).

If DOP 1 takes 240 seconds and DOP 8 takes 52 seconds:

\[
\text{Speedup}(8) \approx 4.62
\]

\[
\text{Efficiency}(8) \approx 57.7\%
\]

Efficiency drops as overhead, skew, I/O, or contention rises. This measures relative efficiency, not a standalone decision metric.

## 18. Designing DOP by Workload Type

### 18.1. OLTP

- Prioritize predictable latency.
- Keep most short queries serial.
- Restrict high DOP during peak hours.
- Isolate heavy reports into a separate consumer group.
- Monitor queuing and CPU.

### 18.2. Reporting

- Use moderate DOP for large scans/aggregations.
- Measure under concurrent workloads.
- Verify partition pruning and data skew.
- Prevent one report from exhausting the PX server pool.

### 18.3. Batch ETL

- Define batch windows and dependencies.
- Measure full pipeline throughput, not one isolated statement.
- Check redo/undo, TEMP, staging tables, and index maintenance.
- Higher DOP may be viable outside OLTP peak hours if resources and policies permit.

### 18.4. Ad Hoc Analytics

- Restrict via consumer groups.
- Enable statement queuing.
- Enforce DOP caps.
- Monitor long-running queries and query fan-out.
- Consider workload isolation or a dedicated analytics environment as demand grows.

## 19. Anti-Patterns to Avoid

| Anti-pattern | Consequence | Fix |
|---|---|---|
| Setting high `PARALLEL` on every table | SQL not needing PX still requests workers | Set attributes/hints selectively per workload |
| Enabling `FORCE PARALLEL QUERY` on connection pools | Even tiny requests get parallelized | Scope to specific statements or dedicated sessions |
| Raising `PARALLEL_MAX_SERVERS` to eliminate queuing | Oversubscribes CPU/PGA/I/O | Fix bottlenecks and govern concurrency |
| Using high DOP when CPU is saturated | Context switching and latency climb | Lower DOP or throttle workloads |
| Benchmarking only a single isolated session | Ignores concurrency contention | Test under realistic concurrency |
| Ignoring TEMP/PGA | Hash/sort spills severely slow queries | Monitor work areas, TEMP, and memory |
| Ignoring data skew | One worker stalls the whole statement | Analyze distribution keys and partitions |
| Using PX for queries returning a few rows | Overhead exceeds any benefit | Use serial execution / index lookups |
| Comparing elapsed time alone | Can inflate CPU and cut system throughput | Compare total resources and overall SLAs |
| Ignoring queue timeouts | Requests time out before starting | Align SLAs, queuing, and client timeouts |
| Enabling PDML without understanding transactions | Triggers `ORA-12838` and alters semantics | Define clear transaction boundaries |
| Ignoring RAC interconnect | Cross-instance PX floods interconnect | Measure data locality and network traffic |
| Changing DB-wide policy to fix one SQL | Impacts unrelated workloads | Tune at statement, session, or consumer group level first |

## 20. Checklist Before Enabling Parallel Execution

### Before Testing
- Confirmed which SQL or batch job genuinely needs speedup.
- Captured serial or current-state baseline.
- Inspected execution plan and actual row counts.
- Verified spare CPU, storage, PGA, and TEMP capacity.
- Checked existing PX statements running concurrently.
- Verified Oracle version and DOP policy.

### During Testing
- Tested incremental DOP steps.
- Recorded requested DOP and granted DOP.
- Measured elapsed time, CPU, I/O, TEMP, and queue time.
- Checked worker counts per server set.
- Checked for data skew.
- Tested under production-like concurrency.
- Verified query results remain accurate.

### Before Deployment
- Configured appropriate DOP caps and Resource Manager policies.
- Prepared a rollback plan.
- Checked PDML restrictions if modifying data.
- Aligned timeouts/queuing with application owners.
- Defined alert thresholds for CPU, PX servers, TEMP, and latency.

### After Deployment
- Monitor overall throughput.
- Monitor OLTP p95/p99 latency.
- Monitor PX servers in use and highwater marks.
- Monitor TEMP, PGA, I/O, and wait events.
- Check statement queuing.
- Check for regressions in other workloads.

## 21. Comprehensive Practice Lab

Examples use a lab schema and large populated tables. Read access to dynamic performance views is required for some statistics. Never test high DOP or PDML in production.

### Step 1. Check PX Configuration

```sql
SELECT name, value
FROM v$parameter
WHERE name LIKE 'parallel%'
   OR name IN ('cpu_count')
ORDER BY name;
```

Record policy, server limits, and targets.

### Step 2. Check Table Parallel Attributes

```sql
SELECT table_name,
       degree,
       instances,
       temporary
FROM user_tables
WHERE table_name IN ('SALES', 'CUSTOMERS');
```

### Step 3. Run Serial Baseline

```sql
SELECT /*+ NO_PARALLEL(s) */
       product_id,
       SUM(amount_sold)
FROM sales s
WHERE sale_date >= DATE '2026-01-01'
GROUP BY product_id;
```

Record elapsed time, CPU, buffers, reads, and row count.

### Step 4. Test DOP 2

```sql
SELECT /*+ PARALLEL(s 2) */
       product_id,
       SUM(amount_sold)
FROM sales s
WHERE sale_date >= DATE '2026-01-01'
GROUP BY product_id;
```

### Step 5. Test DOP 4 and 8

Repeat with DOP 4 and 8 under identical conditions. Do not run test levels concurrently if measuring each level independently.

### Step 6. Inspect the Execution Plan

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PARALLEL +PREDICATE'
    )
);
```

### Step 7. Observe PX Sessions While Running

From a second DBA session, identify the QC SID, then run:

```sql
SELECT sid,
       serial#,
       qcsid,
       qcinst_id,
       server_group,
       server_set,
       server#,
       degree,
       req_degree
FROM v$px_session
ORDER BY qcinst_id, qcsid, server_group, server_set, server#;
```

### Step 8. Check PX Process Usage

```sql
SELECT statistic, value
FROM v$px_process_sysstat
WHERE statistic IN (
    'Servers In Use',
    'Servers Available',
    'Servers Highwater'
);
```

Capture before/after snapshots for deltas and highwater marks.

### Step 9. Compare Results

| DOP | Elapsed | CPU | Buffer gets | Physical reads | TEMP | Rows |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | Measure | Measure | Measure | Measure | Measure | Verify |
| 2 | Measure | Measure | Measure | Measure | Measure | Verify |
| 4 | Measure | Measure | Measure | Measure | Measure | Verify |
| 8 | Measure | Measure | Measure | Measure | Measure | Verify |

### Step 10. Test Statement Queuing in a Dedicated Setup

Generate enough concurrent load to hit the PX server target, then observe queue wait times and granted workers. Never induce overload on shared environments.

### Step 11. Reset Session State

If the session forced parallel queries or enabled PDML, restore session state per session policy:

```sql
ALTER SESSION DISABLE PARALLEL QUERY;
ALTER SESSION DISABLE PARALLEL DML;
```

These commands alter only the current session state. Never modify system parameters during lab exercises without DBA authorization and a plan.

## 22. Self-Check Questions

**Q1.** What is parallel execution?

**A:** A mechanism that splits SQL operations into parts executed concurrently by multiple PX servers coordinated by a Query Coordinator.

**Q2.** What is DOP?

**A:** Degree of Parallelism—the parallelism level used for an operation/statement, indicating the worker count participating at a parallel processing stage.

**Q3.** Does DOP 8 always use only eight PX processes?

**A:** No. An execution plan can use producer and consumer server sets; actual process count can exceed DOP depending on the plan.

**Q4.** What does the Query Coordinator do?

**A:** Orchestrates the statement, requests PX servers, manages data flow, and aggregates final results.

**Q5.** What does `PARALLEL_DEGREE_POLICY` control?

**A:** The DOP selection policy and parallel execution behaviors such as Auto DOP and statement queuing depending on version.

**Q6.** Does Auto DOP mean every SQL runs in parallel?

**A:** No. Oracle estimates cost and selects PX only when thresholds and limits warrant it.

**Q7.** How do `PARALLEL_MAX_SERVERS` and `PARALLEL_SERVERS_TARGET` differ?

**A:** `MAX` sets the hard maximum number of PX servers; `TARGET` sets the management/queuing threshold in supported configurations.

**Q8.** How does statement queuing help?

**A:** It queues statements waiting for resources instead of granting workers to every SQL immediately, preventing oversubscription.

**Q9.** Why can raising DOP make SQL slower?

**A:** Workers compete for CPU, I/O, PGA, and TEMP, and can suffer from data skew or contention.

**Q10.** What is data skew?

**A:** Uneven distribution of data or work across workers, forcing a few workers to shoulder most of the load and lengthen the entire statement.

**Q11.** When is HASH distribution used?

**A:** Distributing rows by hash key, typically to route matching join/group keys to the same worker.

**Q12.** What risk does BROADCAST distribution carry?

**A:** Data is replicated to all workers; if the broadcast dataset is large, memory and network traffic can spike sharply.

**Q13.** How does Parallel Query differ from Parallel DML?

**A:** Parallel Query focuses on reading/query processing; Parallel DML executes `INSERT`/`UPDATE`/`DELETE` in parallel and must be explicitly enabled via supported mechanisms.

**Q14.** Why can `ORA-12838` occur after PDML?

**A:** Certain operations accessing a table already modified by PDML within the same transaction are disallowed before `COMMIT`/`ROLLBACK` under Oracle rules.

**Q15.** Why monitor TEMP and PGA?

**A:** Many workers create many concurrent work areas; insufficient memory causes TEMP spills and heavy I/O.

**Q16.** How does Resource Manager help parallel workloads?

**A:** Allocates and caps resources by consumer group, preventing reports/batches from starving critical workloads.

**Q17.** Is the highest DOP always the best choice?

**A:** No. Pick the DOP that meets SLAs while keeping total CPU, I/O, memory, and impact on other workloads acceptable.

**Q18.** What should you compare after changing DOP?

**A:** Elapsed time, CPU, throughput, buffer gets, physical reads, TEMP, queue time, actual DOP, worker skew, and latency of other workloads.

## 23. Conclusion

Parallel execution enables Oracle to handle large queries and data operations across multiple PX servers, yet DOP is only part of the picture. Query Coordinator, server sets, DFOs, granules, and table queues work together to partition work and exchange rows. High DOP can shorten elapsed time for one statement while inflating CPU, PGA, TEMP, I/O, redo, and parallel server demand. When many statements run concurrently, aggregate worker demand can easily overwhelm system capacity.

Choose DOP based on workload and measurements. Start with a serial baseline, step up DOP gradually, measure both latency and throughput, and verify actual DOP, queue wait times, worker skew, CPU, I/O, PGA/TEMP, and OLTP impact. Use Auto DOP, `PARALLEL_SERVERS_TARGET`, `PARALLEL_MAX_SERVERS`, statement queuing, and Resource Manager to govern resource contention according to database policy.

Parallel Query and Parallel DML carry distinct semantics and constraints. PDML must be enabled properly, generates heavy redo/undo, and enforces transaction restrictions like `ORA-12838`. Avoid slapping high `PARALLEL` attributes or hints on every table, avoid raising server pools blindly just to clear queues, and never mistake faster isolated single-query runs for better overall system health. Deploy only when representative benchmarks demonstrate improved SLAs while total workload remains safely within defined resource boundaries.
