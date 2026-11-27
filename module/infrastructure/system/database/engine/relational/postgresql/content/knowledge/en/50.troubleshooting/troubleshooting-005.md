# High CPU, Memory Exhaustion, and Queries Generating Excessive Temp Files

A PostgreSQL query can spike CPU, exhaust server RAM, or generate massive amounts of temporary files on disk. These three symptoms often trace back to the same execution plan: the query reads too many rows, must sort or join large datasets, and cannot fit all intermediate data in memory. Still, each symptom requires its own diagnosis. High CPU does not automatically mean insufficient RAM; growing temp files do not automatically mean a failing disk; and a query in `active` state is not necessarily consuming CPU.

This lesson explains how to recognize symptoms, find the queries driving load, read execution plans, understand memory limits, and handle temporary files. The goal is to pinpoint the true bottleneck before changing configuration or query structure.

## 1. Recognizing the Three Incident Categories

### High CPU Usage

High CPU usage typically appears with these signs:

- PostgreSQL processes consume heavy CPU in `top`, `htop`, or server monitoring tools.
- Response times of many queries climb together even when data volume and user counts barely changed.
- One or several PostgreSQL backends use CPU continuously.
- Queries contain heavy joins, sorts, aggregations, computed expressions, or large data scans.

A query with a long execution duration is not necessarily consuming high CPU. It could be waiting on locks, disk reads, or other resources. Always combine PostgreSQL metrics with OS metrics and backend wait information.

### Memory Exhaustion

Memory incidents may manifest as:

- The operating system begins swapping heavily, with latency spiking sharply.
- Containers or virtual machines hit RAM limits.
- The kernel or container orchestrator kills a process due to OOM (Out Of Memory).
- PostgreSQL logs memory allocation errors or queries fail while processing large datasets.
- The server stays up, yet many concurrent queries slow down due to memory and I/O contention.

Never assume PostgreSQL uses only RAM equal to `shared_buffers`. PostgreSQL also uses per-backend memory, memory per sort/hash operation, maintenance memory, parallel workers, and memory for other processes on the host.

### Rapid Temp File Growth

PostgreSQL writes intermediate data to disk when a query operation needs more memory than allowed. Common operations include:

- `ORDER BY` or sort nodes in the execution plan.
- `GROUP BY`, `DISTINCT`, and aggregations.
- Hash joins and hash aggregates.
- Certain materialize steps or intermediate result processing.
- Queries with multiple stages processing large datasets before returning results.

These files are commonly called temporary files or temp files. They differ from temporary tables created by applications via `CREATE TEMP TABLE`. They also differ from `temp_buffers`, which is the buffer cache dedicated to explicit temporary tables.

When a sort or hash operation lacks sufficient memory, PostgreSQL partitions data into chunks, writes those chunks to disk, and reads them back in subsequent steps. This mechanism lets queries finish without holding the entire dataset in RAM, at the cost of increased I/O, latency, and disk usage.

## 2. Understanding How PostgreSQL Uses Resources

### How CPU, RAM, and Disk Relate

A query can pass through several stages:

1. Read rows from tables or indexes.
2. Filter rows with `WHERE` conditions.
3. Join datasets.
4. Sort or aggregate.
5. Produce final results and send them to the client.

If a query reads too many rows, CPU must process more data. If a sort or hash step needs more memory, PostgreSQL spills to temp files. Writing and re-reading intermediate data burdens disks and prolongs queries. Prolonged queries hold connections and resources longer, compounding pressure under high concurrency.

Hence, a single inefficient query can trigger all three symptoms. Even so, identify which step generates the primary load rather than blindly scaling CPU, RAM, or disk space.

### Key Memory Areas

| Parameter | Role | Things to Keep in Mind |
| --- | --- | --- |
| `shared_buffers` | Shared data buffer cache used by PostgreSQL | Does not represent all RAM consumed by PostgreSQL |
| `work_mem` | Memory limit per sort or hash operation before spilling to disk | One query can have multiple operations; many backends can run concurrently |
| `hash_mem_multiplier` | Multiplier applied to `work_mem` for hash operations | Check actual value on your running version |
| `maintenance_work_mem` | Memory for maintenance tasks such as `VACUUM` or index creation | Not the primary knob for fixing normal query sorts |
| `autovacuum_work_mem` | Memory for autovacuum workers | A value of `-1` falls back to `maintenance_work_mem` |
| `temp_buffers` | Buffer cache for explicit temporary tables within a session | Not the memory limit for sort/hash spills |
| `effective_cache_size` | Planner estimate of cache available to a query | Hint for the planner only; allocates no RAM |

The most important takeaway is that `work_mem` is not a fixed budget for an entire query or the entire server. It is a per-operation limit for memory-intensive nodes. A plan with multiple sort/hash nodes can allocate multiple chunks. Parallel workers may also allocate their own memory. Consequently, setting `work_mem` too high globally can push total RAM demand beyond server capacity during concurrency spikes.

You can visualize memory pressure with this rough mental model:

~~~text
Required RAM
≈ shared_buffers
  + baseline memory of active backends
  + total sort/hash memory across concurrent queries
  + parallel worker memory
  + maintenance/autovacuum memory
  + OS and other services
~~~

This is only a conceptual model for spotting risk, not an exact forecasting formula. `work_mem` is allocated when an operation needs it; not every backend immediately reserves the full configured value.

### Temp Files Are Not Temporary Tables

Distinguish three concepts:

- **Executor temp files:** intermediate data from sort, hash, or query execution steps spilling to disk.
- **Temporary tables:** tables created by a session or transaction via `CREATE TEMP TABLE`; data persists for the table/session lifecycle.
- **`temp_buffers`:** in-memory buffer pool reserved for explicit temporary tables.

Increasing `temp_buffers` does not directly resolve sorts or hashes generating temp files. Increasing `work_mem` can reduce spills for some queries, while raising OOM risk under high concurrency.

## 3. Investigation Workflow Before Changing Configuration

### Step 1: Record Scope and Timing

Before tuning anything, capture:

- Incident start and end times.
- CPU, RAM, swap, and free space on each relevant filesystem.
- PostgreSQL connection count and running query count.
- Affected databases, roles, applications, and query types.
- Whether the issue followed an application deployment, batch job, report run, or data change.

When possible, compare against the same time window on the previous day. A recurring batch or scheduled report creates periodic load, whereas a newly deployed query can cause a sudden jump in load.

### Step 2: Inspect Active Queries

Run the following query to inspect executing backends and their wait states:

~~~sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS elapsed,
    left(query, 300) AS query
FROM pg_stat_activity
WHERE state = 'active'
ORDER BY query_start NULLS LAST;
~~~

Columns to watch:

- `pid`: backend process ID, used to correlate with OS processes.
- `application_name`: identifies the service or application opening the connection.
- `state`: shows whether the backend is `active`, `idle`, or in another state.
- `wait_event_type` and `wait_event`: indicate what kind of event the backend is waiting on.
- `elapsed`: time since the current query started.
- `query`: currently executing statement, potentially restricted by the viewer's stats privileges.

`state = 'active'` only means the backend is handling a query. If `wait_event_type` is populated, the backend is waiting on that event. If there is no wait event, the query may be executing on CPU, though you should still corroborate with OS metrics.

If many queries are waiting on locks, resolve the locking cause first. Raising `work_mem` or adding CPU will not fix a transaction holding locks too long.

### Step 3: Check Database-Level Temp File Metrics

The `pg_stat_database` view provides counters for temp file counts and total bytes written:

~~~sql
SELECT
    datname,
    temp_files,
    pg_size_pretty(temp_bytes) AS temp_written,
    stats_reset
FROM pg_stat_database
WHERE datname IS NOT NULL
ORDER BY temp_bytes DESC;
~~~

- `temp_files`: number of temporary files created by queries.
- `temp_bytes`: total bytes written to temporary files.
- `stats_reset`: timestamp when statistics were last reset, if available.

These are cumulative counters since the last stats reset. `temp_bytes` is not the disk space currently occupied by temp files at the moment of the query. A finished query may have already removed its files while still incrementing the counter. Therefore, compare values over time or correlate with logs and filesystem usage.

### Step 4: Find Statements Generating the Most Temp Blocks

If `pg_stat_statements` is installed, rank statements by temp blocks written:

~~~sql
SELECT
    queryid,
    calls,
    round(total_exec_time::numeric, 1) AS total_ms,
    round(mean_exec_time::numeric, 1) AS mean_ms,
    temp_blks_read,
    temp_blks_written,
    left(query, 300) AS query
FROM pg_stat_statements
ORDER BY temp_blks_written DESC
LIMIT 20;
~~~

`temp_blks_read` and `temp_blks_written` show temporary blocks read and written. Block size is typically 8 KiB in standard PostgreSQL builds, depending on compile-time settings.

To find queries consuming the largest share of total execution time, sort by `total_exec_time`:

~~~sql
SELECT
    queryid,
    calls,
    round(total_exec_time::numeric, 1) AS total_ms,
    round(mean_exec_time::numeric, 1) AS mean_ms,
    rows,
    left(query, 300) AS query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Do not look solely at `mean_exec_time`. A 100 ms query called hundreds of thousands of times can generate higher total load than a 20-second query run once a day. Conversely, a query with a very high `mean_exec_time` still warrants investigation if it slows down a critical business workflow.

`total_exec_time` is cumulative execution time, not pure CPU time. It can include wait time. Combine it with wait events and OS CPU metrics.

If the view does not yet exist, an administrator can enable `pg_stat_statements` by adding it to `shared_preload_libraries`, preserving existing libraries, and restarting PostgreSQL. After the server restarts, create the extension in the target database:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

Changing `shared_preload_libraries` requires a restart, not merely a configuration reload. Column names and statistics capabilities can vary across PostgreSQL and extension versions; verify the actual schema before running sample queries on older servers.

### Step 5: Correlate with the Operating System

PostgreSQL runs multiple backend processes. When CPU rises, identify which PIDs consume CPU and which queries they run.

On Linux, common tools include:

~~~bash
top
htop
pidstat -p <PID> 1
vmstat 1
free -h
df -h
iostat -xz 1
~~~

- `top` or `htop`: inspect PostgreSQL processes consuming CPU and RAM.
- `pidstat`: track CPU usage of a specific PID over time.
- `vmstat`: inspect run queue, swap, and memory activity.
- `free`: check available RAM and swap.
- `df`: check free space on filesystems.
- `iostat`: inspect storage device load and latency.

In container environments, also check CPU/RAM limits and container throttling metrics. A container may be throttled to a fraction of a CPU even when the physical host has plenty of idle cores.

## 4. Analyzing and Reducing CPU Load

### Pinpoint the Query Actually Driving Load

Combine three sources:

1. `pg_stat_activity` to see running queries and wait states.
2. `pg_stat_statements` to find statements with high total time or call frequency.
3. OS tools to correlate PIDs with CPU utilization.

Once a suspect statement is chosen, capture its execution plan:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 42
  AND created_at >= TIMESTAMP '2026-01-01'
ORDER BY created_at DESC;
~~~

`EXPLAIN ANALYZE` executes the statement to measure actual runtime metrics. The example above is a `SELECT`. For `INSERT`, `UPDATE`, `DELETE`, or statements with side effects, do not run `ANALYZE` in production without fully assessing impact; use a staging environment or a controlled procedure.

Key details to examine in the plan:

- **Estimated rows vs. actual rows:** large discrepancies indicate inaccurate statistics or skewed data distribution.
- **`loops`:** number of times a node executes. A child node returning few rows per call yet running hundreds of thousands of loops still generates heavy load.
- **`Rows Removed by Filter`:** rows read and then discarded by a filter. A large number signals reviewing filter predicates and plans, though it does not automatically prove an index is needed.
- **`Buffers`:** blocks found in shared buffers or read from storage. High `shared read` counts indicate reading large data volumes or cold caches.
- **`Sort Method`:** shows how sorting ran and whether disk was used.
- **`Hash Batches`:** number of batches in a hash operation. Multiple batches indicate the hash operation partitioned data and used temp files.

You can add `SETTINGS` on supported versions to display non-default planner settings:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT ...;
~~~

Do not look only at the total execution time at the bottom of the plan. Find the nodes with high row counts, high loop counts, heavy buffer reads, or temp reads/writes to see where cost originates.

### Common Causes of High CPU

**Scanning too much data.** Unselective filters, missing suitable indexes, or reading more columns/rows than needed force PostgreSQL to process excessive data. Still, a sequential scan remains optimal when tables are small or queries need most of the table.

**Joins with high loop counts.** A Nested Loop can be very fast when the outer input is small and the inner side has a matching index. If the inner side is scanned repeatedly over large datasets, CPU and I/O spike sharply. Check actual rows, loops, join conditions, and indexes on join columns.

**Sorts and aggregates on large datasets.** `ORDER BY`, `GROUP BY`, `DISTINCT`, and window functions can process huge row counts. If business logic only needs a subset, see if you can filter earlier, bound results with `LIMIT`, or leverage ordering from an appropriate index.

**Statistics not reflecting current data.** After large loads or modifications, stale statistics can cause poor planner choices. Run `ANALYZE` on affected tables at an appropriate time:

~~~sql
ANALYZE orders;
~~~

If multiple columns are correlated and the planner misestimates combined predicates, extended statistics can help:

~~~sql
CREATE STATISTICS orders_status_region_stats (dependencies, mcv)
ON status, region_id
FROM orders;

ANALYZE orders;
~~~

Create extended statistics only when you have observed estimation errors involving those columns. There is no need to create statistics for every column combination.

**Excessive repeated queries.** An individual query may be fast yet get executed tens of thousands of times due to application loops or N+1 patterns. Inspect call counts, total execution time, and how the application batches operations.

**Excessive parallelism.** Parallel queries can speed up large queries, but many concurrent parallel queries can saturate CPU and raise memory demand. Check `max_parallel_workers_per_gather` and actual active workers before increasing parallelism.

### Approaches to Reduce CPU

- Write clear filter predicates and narrow datasets as early as possible while preserving business semantics.
- Select only needed columns instead of fetching entire wide rows unnecessarily.
- Design indexes around real filter predicates, join conditions, and sort orders. Avoid indexing a column merely because it appears in `WHERE`.
- Check data types and expressions on filtered columns. Type casts or wrapping columns in functions can prevent expected index usage.
- Review join cardinalities and join conditions to avoid unintended row multiplication.
- Reduce repeated round-trip queries in application code using batching or consolidated queries.
- Refresh statistics with `ANALYZE` after substantial data changes.
- Tune parallelism based on overall server load, not isolated single-query benchmarks.

After each change, re-run the plan and compare actual rows, loops, buffers, temp blocks, and timing. A new index may speed up one query while increasing storage usage and write overhead for other operations.

## 5. Handling Memory Pressure

### Checking Effective Configuration

Do not guess configuration values from sample config files. Inspect the live values used by the instance:

~~~sql
SHOW shared_buffers;
SHOW work_mem;
SHOW hash_mem_multiplier;
SHOW maintenance_work_mem;
SHOW autovacuum_work_mem;
SHOW temp_buffers;
SHOW max_connections;
SHOW max_parallel_workers_per_gather;
SHOW effective_cache_size;
~~~

Some parameters exist only in specific PostgreSQL versions. If `SHOW` reports an unrecognized parameter, check your server version and documentation before applying examples.

### Controlled Tuning of work_mem

When a plan shows a sort or hash operation spilling, test increasing `work_mem` strictly for that session or query. Example:

~~~sql
BEGIN;
SET LOCAL work_mem = '128MB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT ...
FROM ...
WHERE ...;

ROLLBACK;
~~~

`SET LOCAL` applies only within the current transaction and automatically reverts when the transaction ends. This example suits testing read-only queries. If the statement has side effects, never run `EXPLAIN ANALYZE` like this on production.

After testing, verify:

- Whether Sort still uses `external merge`.
- Whether Hash operations reduced their batch count.
- Whether temp blocks read/written dropped.
- Whether query execution time improved.
- Whether total RAM and concurrent query load remain within safe limits.

Never raise `work_mem` globally simply because one query needs more memory. Raising it at the role or database level applies the new limit to every matching query in subsequent sessions. A high value may look safe during a single-query test yet become dangerous when dozens of concurrent queries run multiple sort/hash operations.

### Checking Hash Memory and Parallel Queries

`hash_mem_multiplier` scales the hash memory limit relative to `work_mem`. Default values vary by version, so check with `SHOW hash_mem_multiplier`.

If `Hash Batches` is high, you can test tuning `work_mem` or `hash_mem_multiplier` in a test session, but verify input row counts and plan quality first. A hash join receiving excessive rows due to a broken join predicate or misestimate will still consume excessive resources even with more memory.

Parallel workers also expand total potential memory usage. In a test session, compare plans with parallel execution disabled:

~~~sql
BEGIN;
SET LOCAL max_parallel_workers_per_gather = 0;
EXPLAIN (ANALYZE, BUFFERS)
SELECT ...;
ROLLBACK;
~~~

This is a diagnostic comparison, not a recommendation to disable parallel queries globally. If a non-parallel plan behaves more predictably under concurrency, review worker limits and concurrent parallel queries.

### Controlling Connection Counts and Maintenance Activity

Every backend carries baseline memory overhead. Too many connections increase RAM pressure even when not every connection runs heavy queries. For applications opening many short-lived connections, consider a connection pooler like PgBouncer and set appropriate connection limits.

Do not overlook maintenance tasks:

- `CREATE INDEX` and `VACUUM` can use `maintenance_work_mem`.
- Autovacuum workers use `autovacuum_work_mem`, or inherit `maintenance_work_mem` when set to `-1`.
- Multiple concurrent maintenance jobs also drive RAM and I/O demand.

When investigating RAM exhaustion, record active autovacuum workers and running maintenance jobs before altering memory parameters.

### Inspecting Memory Contexts for Deep Investigation

On versions offering `pg_backend_memory_contexts`, you can inspect memory distribution for the backend running the query:

~~~sql
SELECT
    name,
    parent,
    level,
    total_bytes,
    free_bytes,
    used_bytes
FROM pg_backend_memory_contexts
ORDER BY used_bytes DESC
LIMIT 20;
~~~

This view reflects only the backend executing the query; it does not automatically display memory for other backends. If you need to analyze another backend, use diagnostics appropriate for your version and privileges while accounting for potential log volume.

## 6. Handling Queries Generating Excessive Temp Files

### Enabling Logging to Identify Offending Queries

`log_temp_files` instructs PostgreSQL to log when a temporary file is deleted. `-1` disables logging, `0` logs every temp file, and a positive value logs files at or above that size threshold.

Example configuration logging temp files of 64 MB or larger:

~~~conf
log_temp_files = 64MB
~~~

This parameter can be applied via configuration reload. An administrator can run:

~~~sql
SELECT pg_reload_conf();
~~~

Changing configuration requires appropriate permissions and must follow your environment's configuration management workflow. Never overwrite `shared_preload_libraries` or other settings when intending to add just one parameter.

Logs typically record file size and process info. Correlate PID, timestamp, and query in the logs with `pg_stat_activity` or query logs to pinpoint the workload. Setting the threshold to `0` on high-traffic systems can generate rapid log growth; pick an appropriate threshold and monitor log disk usage.

### Reading Spill Indicators in EXPLAIN

For example, a Sort node may show:

~~~text
Sort
  Sort Key: created_at DESC
  Sort Method: external merge  Disk: 51200kB
  Buffers: shared hit=..., read=..., temp read=6400 written=6410
~~~

`external merge` indicates the sort spilled to disk. `Disk` reports the temporary space used by the sort in the plan. `temp read` and `temp written` show temporary block read/write activity.

A Hash node may show:

~~~text
Hash
  Buckets: 131072  Batches: 8  Memory Usage: ...
~~~

`Batches` greater than 1 shows the hash operation partitioned data into multiple batches. This signals checking hash memory, input row counts, and the join plan. Seeing temp blocks does not automatically mean `work_mem` must be raised; the query may simply be processing unnecessary data.

### Reducing Intermediate Data Before Raising Limits

Effective approaches typically include:

1. Filter rows earlier if predicates can be applied before sorting/joining without altering results.
2. Select only genuinely required columns to avoid carrying wide payloads through intermediate steps.
3. Review `ORDER BY`, `DISTINCT`, `GROUP BY`, and window functions to eliminate unnecessary work.
4. Check whether joins duplicate rows; fix join conditions if business logic is wrong.
5. Check whether an index can supply the ordering required by the query.
6. Refresh statistics if the planner misestimated row counts.
7. Only after those steps, test controlled `work_mem` increases for eligible workloads.

For instance, this query sorts all orders for a tenant:

~~~sql
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 42
ORDER BY created_at DESC;
~~~

If business logic only needs the 50 most recent orders, bounding results sharply cuts data processed:

~~~sql
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 42
ORDER BY created_at DESC
LIMIT 50;
~~~

A composite index starting with `tenant_id` followed by `created_at` can support that filter and sort order depending on data types, sort direction, query conditions, and planner choice:

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_tenant_created_at
ON orders (tenant_id, created_at DESC);
~~~

This is an illustrative example, not an index to add automatically to every table. Before creating it, evaluate table size, write frequency, existing indexes, selectivity, and execution plans. `CREATE INDEX CONCURRENTLY` avoids long write locks compared to standard index builds in many cases, though it still consumes CPU, I/O, and disk space and comes with its own limitations.

### Capping Temp File Size per Backend

`temp_file_limit` caps total temporary file space a single PostgreSQL process can hold at any point in time. This is a per-process limit, not an instance-wide total and not a per-statement cap.

Example setting a limit for a role:

~~~sql
ALTER ROLE reporting_user SET temp_file_limit = '20GB';
~~~

The new value applies to sessions opened after the configuration takes effect. When a backend exceeds the limit, the query is canceled with a `temp_file_limit` error. This is a guardrail so one backend cannot consume unbounded disk space, not a fix for why the query spills. Setting it too low can break legitimate reports.

This limit does not apply to disk space consumed by explicit temporary tables created by applications. Their lifecycle and size must be managed per session/transaction and application logic.

### Using a Separate Tablespace for Temp Data When Needed

`temp_tablespaces` can direct certain temporary files to a dedicated tablespace. This helps when your system has suitable storage devices and wants to isolate temp I/O from primary data storage.

Before using it, verify:

- The tablespace has sufficient free space and independent monitoring.
- The storage device has adequate performance for the workload.
- Permissions, backup exclusions, and monitoring policies are aligned.
- Moving temp files does not bottleneck another device.

Separating tablespaces only relocates I/O. It does not shrink the rows being sorted/hashed or eliminate query processing cost.

## 7. Real-World Scenario: A Report Spikes CPU and Temp Files

Suppose a reporting application starts slowing down. CPU rises, free space on the filesystem holding PostgreSQL data drops rapidly, and multiple users complain.

### Initial Symptoms

The report query joins `orders` with `customers`, filters by tenant, groups by customer, and sorts by total amount. Inspection shows:

- `pg_stat_activity` shows multiple concurrent executions of the same statement.
- `pg_stat_statements` shows the statement writing large `temp_blks_written`.
- `pg_stat_database` shows `temp_bytes` jumping rapidly during the incident window.
- `EXPLAIN (ANALYZE, BUFFERS)` reveals an `external merge` sort and a multi-batch hash join.

These findings confirm the query builds large intermediate datasets and spills to disk. They are not enough to conclude you should merely increase `work_mem`.

### Root-Cause Investigation

Reading the plan end-to-end reveals:

- The tenant filter is applied after a huge dataset has already been read.
- A join produces far more rows than expected due to an incomplete join condition.
- The planner vastly underestimates row counts compared to actual rows.
- The application runs many concurrent reports simultaneously.

Four issues need attention: fixing the join condition per business logic, checking access paths for the tenant filter, updating statistics, and capping concurrent report executions.

### Applying Fixes and Re-Measuring

After fixing the query and statistics, re-run the plan under equivalent conditions. Compare:

- Actual rows at join and sort nodes.
- Loop counts on child nodes.
- `temp_blks_written` and `temp_blks_read`.
- Execution duration and call frequency.
- CPU, I/O, and RAM usage when multiple reports run concurrently.

If sorting still spills even with a reasonable dataset size, test raising `work_mem` for the reporting session or dedicated reporting role. Test under concurrent load before rolling out broadly. If one query runs well alone yet exhausts RAM when multiple reports run together, lower concurrency or adjust workload memory budgets.

## 8. Responding When Disk or Memory Is Nearly Exhausted

### When the Filesystem Holding Temp Files Is Nearly Full

1. Identify which filesystem and tablespace are filling up; do not assume all temp files reside on the same mount.
2. Inspect `log_temp_files` logs, running queries, and associated PIDs.
3. Identify queries or workloads that can be paused without corrupting business operations.
4. If a verified query must be stopped, use `pg_cancel_backend(pid)` to request query cancellation:

~~~sql
SELECT pg_cancel_backend(12345);
~~~

5. Use `pg_terminate_backend(pid)` only when the entire session must be ended and the transaction impact is understood:

~~~sql
SELECT pg_terminate_backend(12345);
~~~

Canceling a query can cause its transaction to roll back. Appropriate privileges are required to signal other backends. Never pick a PID based solely on CPU usage or process name; verify database, user, application, and statement before acting.

Never manually delete files inside the PostgreSQL data directory or `pgsql_tmp` while the server is running. PostgreSQL manages the lifecycle of these files; deleting an active file can break queries or disrupt server operation. Control the workload through PostgreSQL and let the server clean up files via its own mechanisms.

### When the Server Runs Out of RAM or Hits OOM

- Check available RAM, swap, container limits, and OS OOM logs.
- Identify active backends and workloads; check connection counts, parallel queries, sort/hash operations, and maintenance tasks.
- Temporarily throttle heavy workloads or concurrent report queries if needed to stabilize the service.
- Never raise `work_mem` across the board while the host is already out of memory.
- Once stabilized, reallocate memory budgets and tune connection pools, concurrency, parallel workers, or workload-specific settings.

`temp_file_limit` protects disk space per backend, not RAM limits. `statement_timeout` caps query runtime but does not replace fixing bad plans and controlling resource usage. Apply limits per role, database, or workload group based on business requirements rather than enforcing an overly tight cap on all queries.

## 9. Actions Likely to Worsen the Incident

| Action | Why It Is Risky | Better Approach |
| --- | --- | --- |
| Setting global `work_mem` very high | Concurrent sort/hash operations can exceed total RAM | Test in one session, benchmark under concurrency, then expand carefully |
| Raising `shared_buffers` to fix every slow query | Does not fix bad join plans, sorts, or unselective filters | Read plans and distinguish cache misses from CPU, locks, or spills |
| Raising `temp_buffers` to fix sort spills | `temp_buffers` serves explicit temporary tables | Check `work_mem`, `Hash Batches`, and `Sort Method` |
| Manually deleting files in `pgsql_tmp` | Can delete files actively used by a backend | Identify the query and cancel the workload through PostgreSQL if needed |
| Indexing every column in `WHERE` | Increases storage and write overhead; planner may still skip indexes | Base decisions on selectivity, plans, and read/write workload |
| Disabling sequential scans system-wide | Can force the planner into worse plans | Fix statistics, queries, and indexes; alter planner knobs only for controlled diagnosis |
| Inspecting only the single slowest query | Misses high-frequency queries driving the highest total load | Review calls, total time, mean time, and temp blocks |
| Running `VACUUM FULL` to handle temp files | Rewrites the table, requires extra disk and exclusive locks | Fix the queries generating temp files; vacuum only to manage dead tuples/bloat |

## 10. Quick Diagnostic Query Pack

When taking on an incident, use these queries to gather initial evidence:

**Version and Key Parameters**

~~~sql
SELECT version();

SHOW work_mem;
SHOW hash_mem_multiplier;
SHOW shared_buffers;
SHOW max_connections;
SHOW max_parallel_workers_per_gather;
SHOW temp_file_limit;
SHOW log_temp_files;
~~~

**Running Queries and Wait States**

~~~sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS elapsed,
    left(query, 300) AS query
FROM pg_stat_activity
WHERE state = 'active'
ORDER BY query_start NULLS LAST;
~~~

**Databases with Heavy Temp File Activity**

~~~sql
SELECT
    datname,
    temp_files,
    pg_size_pretty(temp_bytes) AS temp_written,
    stats_reset
FROM pg_stat_database
WHERE datname IS NOT NULL
ORDER BY temp_bytes DESC;
~~~

**Queries Generating High Temp Blocks**

~~~sql
SELECT
    queryid,
    calls,
    temp_blks_read,
    temp_blks_written,
    round(total_exec_time::numeric, 1) AS total_ms,
    round(mean_exec_time::numeric, 1) AS mean_ms,
    left(query, 300) AS query
FROM pg_stat_statements
ORDER BY temp_blks_written DESC
LIMIT 20;
~~~

Statistics queries require appropriate viewing privileges. Cumulative counters may have been reset and can aggregate multiple executions of the same query pattern. Record reset timestamps, measurement windows, and concurrent load to avoid comparing metrics across mismatched conditions.

## 11. Recommended Resolution Sequence

When CPU spikes, RAM tightens, or temp files surge, follow this sequence:

1. Confirm the affected host, database, filesystem, and time window.
2. Check `pg_stat_activity` to separate actively running queries from waiting queries.
3. Correlate PostgreSQL PIDs with OS CPU, RAM, swap, and I/O.
4. Use `pg_stat_database` and `pg_stat_statements` to find the databases and query patterns generating heavy temp blocks.
5. Read `EXPLAIN (ANALYZE, BUFFERS)` safely to locate expensive sort, hash, or join nodes.
6. Fix root causes inflating input rows, skewing cardinality estimates, repeating calls, or running too many concurrent workloads.
7. Test configuration changes within a narrow scope, measuring both isolated runs and concurrent load.
8. Add logging thresholds, resource guardrails, and alerts to catch future incidents earlier.

A fix is only considered effective when the query meets business requirements, response times improve, and CPU, RAM, I/O, and temp file usage remain stable under realistic load. Never declare success just because one query ran faster in an idle test environment with few connections.
