# work_mem per Operation, Session, and Parallel Query in PostgreSQL

## 1. Why Does work_mem Need to Be Understood at Multiple Levels?

PostgreSQL uses memory for intermediate operations during query execution, such as sorts, hash joins, and hash aggregates. If an operation requires more data than its allowed memory budget, PostgreSQL can split the work into multiple parts and use temporary files on disk. This allows the query to continue running, but it can significantly increase latency and I/O.

The `work_mem` parameter is often misunderstood as the amount of RAM allocated to a single query or a single connection. In reality, it is a budget for **each relevant sort or hash operation**, and a single query can contain multiple such operations. Multiple concurrently running queries, multiple backends, and parallel workers can each use their own separate budgets.

Therefore, increasing `work_mem` server-wide from 16 MB to 256 MB does not mean adding only 240 MB of RAM. Under high concurrency, the total potential demand can grow to gigabytes.

```text
PostgreSQL instance
   |
   +-- Session A
   |     |
   |     +-- Query A
   |     |     +-- Sort node       -> work_mem budget
   |     |     +-- Hash Join       -> hash memory budget
   |     |     +-- Hash Aggregate  -> hash memory budget
   |     |
   |     +-- Other active query ...
   |
   +-- Session B
   |     +-- Query B / Sort / Hash ...
   |
   +-- Parallel query
         +-- Leader process
         +-- Worker 1
         +-- Worker 2
         +-- Worker 3
```

Actual consumption depends on the execution plan, the number of operations active at the same time, the number of sessions, the number of workers, the operator types, and the actual data. It should be measured using query plans, temp I/O, process/host memory, and workload concurrency.

### Learning Objectives

After this lesson, you will be able to:

1. Explain accurately which operations `work_mem` applies to.
2. Distinguish between per-operator, per-query, per-session, and server-wide budgets.
3. Identify sort/hash spills via EXPLAIN and statistics.
4. Understand `hash_mem_multiplier` and hash-based operations.
5. Estimate memory pressure when multiple queries run concurrently.
6. Analyze parallel queries and worker memory usage.
7. Distinguish `work_mem` from `shared_buffers`, `maintenance_work_mem`, `temp_buffers`, and other parameters.
8. Tune memory at session, transaction, role, and database scopes.
9. Use `SET LOCAL` to limit the scope of tuning.
10. Monitor temp files, temp blocks, and memory contexts.
11. Optimize the query plan before increasing memory.
12. Design a capacity budget, concurrency tests, and alerts.
13. Avoid OOM, swap, and cross-workload interference.
14. Build a runbook for investigating query spills and memory pressure.

---

## 2. What Is work_mem?

`work_mem` is the base amount of memory that PostgreSQL allows a query operation requiring sorting or hashing to use before switching to disk-based or batching strategies.

Examples of commonly involved operations:

- Sorting for `ORDER BY`.
- Sorting for `DISTINCT` or certain plans requiring ordered input.
- Sorting in a merge join.
- Hash join build table.
- Hash aggregate for `GROUP BY`.
- Certain other hash-based operations.
- Certain executor nodes using a tuplestore/memory depending on the plan and implementation.

Key point: `work_mem` is not a total RAM limit for a query. A single execution plan can contain multiple memory-consuming nodes.

### 2.1. A Single Query Can Have Multiple work_mem Consumers

Conceptual plan example:

```text
SELECT ...
  -> Sort                         (work_mem)
       -> Hash Join               (hash memory)
            -> Seq Scan orders
            -> Hash                (hash memory)
                 -> Seq Scan customers
```

If multiple nodes require memory during the same execution phase, the total memory for the query can exceed a single `work_mem` allocation.

### 2.2. Multiple Concurrent Queries

Each backend executing a query can use its own budget. If 30 sessions concurrently run queries with sorts/hashes, you cannot count just a single `work_mem` for the entire instance.

### 2.3. work_mem Is a Budget, Not a Reservation

PostgreSQL does not necessarily allocate the entire `work_mem` value as soon as a query starts. Memory is consumed as operators need it. Therefore, multiplying sessions by `work_mem` is a way to estimate risk/ceiling, not an exact RSS forecast.

### 2.4. Not All Plan Nodes Run Simultaneously

Some plan branches execute sequentially, some nodes may hold state simultaneously, and some memory is freed when a node finishes. Do not sum all nodes mechanically; inspect the plan and observe the workload.

## 3. Distinguishing Memory Scopes

| Scope | Example | Meaning |
|---|---|---|
| Operator | A Sort or Hash node | Basic unit tied to work_mem |
| Query | An execution plan | Can have multiple operators and workers |
| Session/backend | A PostgreSQL connection | Can run multiple queries over time |
| Parallel query | Leader and parallel workers | Multiple processes executing one query together |
| Instance | All sessions, workers, background processes | Total memory pressure on the host/container |

### 3.1. Do Not Set work_mem Based on Total RAM

If a machine has 64 GB of RAM, that does not mean you can set `work_mem = 1 GB`. Shared buffers, OS cache, backend overhead, maintenance, parallel workers, and concurrency all require memory.

### 3.2. Do Not Set work_mem Based on a Single Query

A query running alone might need 256 MB and finish quickly. When 50 similar queries run concurrently, potential consumption can exceed host limits.

### 3.3. Set Budgets by Workload

High-concurrency OLTP typically requires a conservative default. Reporting/batch workloads can be granted higher limits per role or transaction if concurrency is controlled.

## 4. Sort Operations and work_mem

Sorting typically appears when a query requests ordered data or the execution plan requires sorted input.

Example:

```sql
SELECT order_id, created_at, total
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC;
```

If an appropriate index can provide the required order, the planner can avoid an explicit Sort. If many rows must be sorted, the operator needs memory.

### 4.1. Sort in Memory

If the data to be sorted fits within the budget, PostgreSQL can use an in-memory sort algorithm, such as quicksort or top-N heapsort depending on the query.

EXPLAIN ANALYZE may display:

```text
Sort Method: quicksort  Memory: 8192kB
```

### 4.2. External Sort

If the data exceeds the memory budget, PostgreSQL can use external merge sort and temporary files:

```text
Sort Method: external merge  Disk: 128000kB
```

This is evidence that the operator spilled to disk. Not every external sort is an incident; compare it against latency SLOs and the workload baseline.

### 4.3. LIMIT and Top-N

With `ORDER BY ... LIMIT`, the planner can use a top-N heapsort or an index scan. Do not assume `work_mem` needs to be increased; check the plan first.

### 4.4. Indexes Can Eliminate Sorts

A B-tree index whose ordering matches the filter/order direction can allow reading in order instead of sorting the entire result. Compare the cost of index scan, heap fetch, and sort.

## 5. Hash Joins and Hash Memory

A hash join builds a hash table from one input (the build side), then uses the other input to probe it.

```text
Build input
    |
    v
 Hash table in memory
    |
    v
Probe input -----> Match rows
```

If the hash table does not fit in the memory budget, PostgreSQL can split the data into multiple batches and use temporary I/O.

EXPLAIN may display:

```text
Hash
  Buckets: 65536
  Batches: 8
  Memory Usage: 4096kB
```

### 5.1. Batches = 1

Usually indicates the hash table is processed in a single batch, without partitioning into multiple batches on disk. Still evaluate the plan, memory, and latency.

### 5.2. Batches Greater Than 1

Multiple batches indicate the hash operation needed to split data, typically accompanied by temp I/O. Check estimates, build-side size, and actual rows.

### 5.3. Build Side and Cardinality

The planner chooses build/probe sides based on estimates. If statistics are inaccurate, the hash table may be larger than expected. Run ANALYZE and check row estimates before increasing memory.

### 5.4. Hash Join Is Not Always Better

Nested loop with index lookup or merge join can be more efficient under certain data distributions. Optimize join strategy and indexes before increasing system-wide memory budgets.

## 6. Hash Aggregate and GROUP BY

Hash aggregate groups rows by grouping keys using a hash table.

Example:

```sql
SELECT customer_id, count(*), sum(total)
FROM orders
GROUP BY customer_id;
```

If the number of groups is large or row width is wide, the hash table can consume substantial memory. When insufficient, the executor can spill/partition depending on implementation and version.

### 6.1. Number of Groups Matters

GROUP BY on a column with a few dozen values is very different from grouping on multiple nearly unique columns. Estimating cardinality helps predict hash table size.

### 6.2. HashAggregate vs. GroupAggregate

The planner can choose HashAggregate or GroupAggregate. GroupAggregate typically requires input sorted by group keys; it can leverage an index/sort. HashAggregate requires a hash table.

### 6.3. EXPLAIN Evidence

Inspect node type, actual rows, planned rows, memory usage, and temp blocks. Do not increase `work_mem` just because a query has GROUP BY.

### 6.4. Batched Aggregation

For large datasets, splitting aggregation by partition/time window or pre-aggregating can reduce memory and temp I/O.

## 7. hash_mem_multiplier

`hash_mem_multiplier` scales the memory limit for hash-based operations relative to `work_mem`.

General concept:

```text
Hash operation memory limit
    ≈ work_mem × hash_mem_multiplier
```

For example, if `work_mem` is 32 MB and `hash_mem_multiplier` is 2, the base limit for a hash operation can be around 64 MB according to the semantics of the PostgreSQL version in use.

### 7.1. Why Have a Separate Multiplier?

Hash operations may have different memory needs than sorts. The multiplier allows granting a higher hash budget without proportionally increasing every sort operation.

### 7.2. Version Awareness

`hash_mem_multiplier` is present in modern PostgreSQL versions; availability and defaults can vary by major version. Check `SHOW hash_mem_multiplier` or `pg_settings` before using it.

### 7.3. Do Not Increase the Multiplier Globally Without a Capacity Model

Many concurrent hash joins/aggregates can rapidly increase memory pressure. A high multiplier does not replace checking concurrency.

### 7.4. Evaluate Hash Spills Separately

If a query has many hash batches, inspect the build-side size and estimates. You can raise the hash budget for a specific workload instead of changing `work_mem` everywhere.

## 8. Operators and Query Patterns That Consume work_mem

| SQL pattern / plan | Operator that may appear | What to inspect |
|---|---|---|
| ORDER BY | Sort | Sort Method, Disk, Memory |
| DISTINCT | Sort or HashAggregate | Rows/groups, spill |
| GROUP BY | HashAggregate/GroupAggregate | Group count, hash batches |
| JOIN | Hash/Sort/Merge Join | Build side, batches, sort |
| UNION / set operations | Sort/Hash | Cardinality, duplicate elimination |
| Window functions | Sort/tuplestore depending on plan | Partition/order size |
| Materialization | Tuplestore | Temp files and plan shape |
| Memoize | Cache node | Evictions/hits, version behavior |

Not every query containing these clauses uses `work_mem` in the same way. The execution plan determines the actual operators.

### 8.1. Window Functions

`ROW_NUMBER`, `RANK`, and window aggregates may require sorting by PARTITION BY/ORDER BY. Large partition datasets can cause spills.

### 8.2. DISTINCT and UNION

Duplicate elimination can use a sort or hash strategy. Inspect the plan rather than guessing from the SQL text.

### 8.3. Materialize and Tuplestore

Some nodes buffer tuples temporarily in memory and can spill to temporary files. Temp I/O can appear even without an obvious Sort node.

### 8.4. Memoize

Memoize caches results of parameterized scans in certain plans. Memory/eviction behavior depends on the executor and version; check EXPLAIN details if the node appears.

## 9. Identifying Spills with EXPLAIN

Use:

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS, SUMMARY)
SELECT customer_id, sum(total)
FROM orders
GROUP BY customer_id
ORDER BY customer_id;
```

### 9.1. Sort Method

- quicksort: in-memory sort.
- top-N heapsort: optimized for LIMIT.
- external merge: sort spilled to disk.

Output details depend on version and plan.

### 9.2. Hash Batches

Check the number of batches and memory usage. Multiple batches can indicate the hash operation exceeded its in-memory budget.

### 9.3. Buffers: temp read/written

EXPLAIN BUFFERS can show temporary blocks read/written for the query. This is a useful signal for spill I/O.

### 9.4. Planned Rows vs. Actual Rows

If actual rows are much higher than the estimate, the planner may choose the wrong strategy or allocate insufficient memory for the actual data volume.

### 9.5. EXPLAIN ANALYZE Executes the Query

EXPLAIN ANALYZE runs the actual statement. For DML, side effects can occur; rolling back a transaction does not undo external side effects created by triggers/functions. Choose the environment and execution approach appropriately.

## 10. Comparing Estimated and Actual Cardinality

Memory demand depends on row count, row width, and operator structure. The planner uses statistics to estimate.

In EXPLAIN:

```text
HashAggregate
  (cost=... rows=1000 ...)
  (actual time=... rows=800000 loops=1)
```

Large discrepancies can cause the planner to underestimate hash table or sort volume.

### 10.1. ANALYZE

Run ANALYZE on relations with stale statistics or after bulk loads. Check `last_analyze`/`last_autoanalyze` and `n_mod_since_analyze`.

### 10.2. Statistics Target

Increase the statistics target for columns with skew or complex cardinality when needed, rather than using it as random tuning.

### 10.3. Extended Statistics

`CREATE STATISTICS` can help the planner understand correlations/dependencies between columns. This improves row estimates in certain predicates/grouping clauses.

### 10.4. Row Width

`SELECT *` can make tuples wider than necessary, increasing sort/hash memory. Select only the columns needed.

## 11. Calculating Memory per Operation, Not by Simple Query Count

A single query can contain:
- Two sort nodes.
- One hash join.
- One hash aggregate.
- One or more parallel workers.

If all operations need memory at the same time, the query can use multiple `work_mem` budgets. However, not all nodes are active concurrently, and memory allocation may be lower than the limit.

### 11.1. Conservative Estimation Model

```text
Potential memory pressure
  ≈ concurrent active processes
    × simultaneous memory-consuming operations
    × per-operation budget
```

For hash operations, apply the appropriate multiplier.

### 11.2. Workload Example

Suppose:
- 20 concurrent query sessions.
- Each query can have 2 sort operations active simultaneously.
- `work_mem = 32 MB`.

An illustrative ceiling for sort budgets is:

```text
20 × 2 × 32 MB = 1280 MB
```

This is a conservative model, not an RSS forecast. Reality depends on plan, lifetime, allocation, and concurrency.

### 11.3. Adding a Hash Operation

If each query also has one hash operation with a multiplier of 2:

```text
Per-query modeled budget
  = 2 × 32 MB + 1 × (32 MB × 2)
  = 128 MB

20 concurrent queries
  = 20 × 128 MB
  = 2560 MB
```

This model illustrates why a large `work_mem` can be dangerous under high concurrency.

### 11.4. Do Not Sum All Nodes Without Reading the Plan

Some nodes execute sequentially or release memory before another node starts. Use the plan and load tests to refine the estimate.

## 12. work_mem per Session/Backend

You can set `work_mem` in a session:

```sql
SET work_mem = '64MB';

SHOW work_mem;
```

The setting applies to the current session and affects subsequent queries in the session according to the parameter's scope.

### 12.1. Long-Lived Sessions

If a session is held in a connection pool, the setting can persist after a request. The next request may inadvertently receive a different memory level than expected.

### 12.2. RESET

```sql
RESET work_mem;
```

`RESET` returns the parameter to the default inherited from role/database/session configuration.

### 12.3. Pool Hygiene

When using session pooling, ensure the pool resets session state upon returning a connection or use transaction-scoped settings.

### 12.4. Do Not Let Application Clients Freely SET Large Values

Put allowlists/guardrails in the application or database roles. A single client can inadvertently cause memory pressure across the entire instance.

## 13. work_mem per Transaction with SET LOCAL

`SET LOCAL` limits the change to the current transaction:

```sql
BEGIN;

SET LOCAL work_mem = '128MB';

SELECT customer_id, sum(total)
FROM orders
GROUP BY customer_id
ORDER BY customer_id;

COMMIT;
```

After COMMIT or ROLLBACK, the local setting expires and the previous session value is restored.

### 13.1. Well-Suited for Connection Pooling

In transaction pooling, `SET LOCAL` stays within the transaction and does not leak to the next transaction when the transaction ends cleanly. Do not use session-level `SET` assuming the proxy will pin the same backend.

### 13.2. Transaction-Only Scope

If a query runs outside an explicit transaction, PostgreSQL runs each statement in an implicit transaction; `SET LOCAL` must be inside a proper transaction block to affect the subsequent statement.

### 13.3. Exception/Rollback

If a transaction rolls back, the local setting is also reverted. This is why `SET LOCAL` is generally safer for per-request tuning.

### 13.4. Keep Transactions Short

Do not hold a transaction open just to keep a `work_mem` setting for a long time. Long transactions hold snapshots/locks and cause vacuum issues.

## 14. work_mem per Role

You can set a default for a database role:

```sql
ALTER ROLE reporting_user
SET work_mem = '64MB';
```

The setting takes effect for new sessions logging in with that role. Existing open sessions generally do not pick up the new default automatically.

### 14.1. Reporting Role

A role dedicated to reporting can have a higher `work_mem` if concurrency and query patterns are controlled.

### 14.2. OLTP Role

A role serving high-concurrency APIs should have a conservative baseline; specific heavy endpoints can use `SET LOCAL` individually.

### 14.3. Inspecting Role Defaults

```sql
SELECT
    rolname,
    rolconfig
FROM pg_roles
WHERE rolname IN ('reporting_user', 'api_user');
```

### 14.4. ALTER ROLE IN DATABASE

You can scope the default to a specific database:

```sql
ALTER ROLE reporting_user IN DATABASE analytics
SET work_mem = '96MB';
```

Check session settings and precedence order when multiple configuration sources exist.

## 15. work_mem per Database

You can set a database default:

```sql
ALTER DATABASE analytics
SET work_mem = '48MB';
```

### 15.1. When to Use a Database Default?

When a database has a distinct workload profile and most sessions in that database share similar requirements.

### 15.2. Not All Roles Are the Same

A database may serve API, reporting, and background jobs. Role-specific defaults or transaction-level settings may be more precise.

### 15.3. Existing Sessions

`ALTER DATABASE SET` affects sessions logging in after the change, not already connected backends automatically.

### 15.4. Document the Policy

Put defaults into configuration management/migration processes. Avoid manual unowned changes.

## 16. Precedence and Effective Configuration

The effective value can come from:
- Compiled/default configuration.
- `postgresql.conf` or include files.
- `ALTER DATABASE` / `ALTER ROLE` defaults.
- Connection startup options.
- `SET` within a session.
- `SET LOCAL` within a transaction.

Check the current value:

```sql
SHOW work_mem;
SHOW hash_mem_multiplier;
```

Or:

```sql
SELECT
    name,
    setting,
    unit,
    source,
    sourcefile,
    sourceline,
    pending_restart
FROM pg_settings
WHERE name IN ('work_mem', 'hash_mem_multiplier');
```

### 16.1. source

`pg_settings.source` shows where the value originated, subject to context/version and privileges to view `sourcefile`.

### 16.2. Role/Database Defaults

An `ALTER ROLE` or `ALTER DATABASE` can override the server default for new sessions.

### 16.3. Session SET

`SET` within a session overrides the loaded default.

### 16.4. SET LOCAL

`SET LOCAL` overrides within the current transaction and automatically reverts when the transaction ends.

## 17. work_mem Is Not shared_buffers

| Parameter | Purpose | Scope |
|---|---|---|
| work_mem | Sort/hash/query execution operations | Per operation/process |
| shared_buffers | Shared cache for database pages | Instance-wide |
| maintenance_work_mem | Certain maintenance operations | Operation/maintenance worker |
| autovacuum_work_mem | Memory for autovacuum workers | Per worker per config |
| temp_buffers | Local buffers for temporary tables | Per session |
| logical_decoding_work_mem | Logical decoding changes pending spill | Logical decoding process |
| wal_buffers | WAL records before writing WAL | Shared instance |

### 17.1. shared_buffers

Used to cache database pages. Increasing `shared_buffers` does not directly increase the sort/hash memory budget.

### 17.2. maintenance_work_mem

Used for maintenance operations such as VACUUM (parts of it), CREATE INDEX, and appropriate maintenance tasks. Do not use it in place of `work_mem` for SELECT queries.

### 17.3. autovacuum_work_mem

Can tune memory separately for autovacuum workers. When set to `-1`, behavior may inherit `maintenance_work_mem` depending on version/configuration.

### 17.4. temp_buffers

Used for temporary tables, not the sort spill budget. Do not increase `temp_buffers` to fix external sorts.

### 17.5. logical_decoding_work_mem

Has its own scope for logical decoding transaction changes. Do not confuse it with query executor memory.

## 18. How Do Parallel Queries Multiply Memory Pressure?

A parallel query can use a leader and multiple worker processes. Workers execute portions of the work and may each run their own sort/hash operators.

```text
Parallel plan
      |
      v
 Gather / Gather Merge
      |
      +-- Leader process
      |
      +-- Worker 1
      |     +-- Sort / Hash
      |
      +-- Worker 2
      |     +-- Sort / Hash
      |
      +-- Worker 3
            +-- Sort / Hash
```

### 18.1. work_mem per Process/Operator

Each process executing an operation may require its own budget. Thus, a parallel query can consume memory equal to multiple times `work_mem`.

### 18.2. Workers Planned and Launched

EXPLAIN ANALYZE can show `Workers Planned` and `Workers Launched`. The actual number of launched workers does not always match what the planner requested.

### 18.3. Leader Participation

The leader may participate in processing tuples in addition to gathering results from workers, depending on the plan and workload. Capacity planning must include the leader when it executes operators.

### 18.4. Parallel Hash

Some parallel hash plans use a shared parallel hash table and coordination mechanisms among workers. Memory is not always strictly equal to the number of workers multiplied by a full independent hash table; read the plan and observe actual memory behavior.

## 19. Estimating Memory for Parallel Queries

A conservative capacity model:

```text
Potential memory
  ≈ active parallel processes
    × simultaneously active memory operators
    × per-operator budget
```

For hash operators, multiply by `hash_mem_multiplier` according to version semantics.

### 19.1. Example

A query has 4 launched workers, the leader also participates, each process has one active sort operation, and `work_mem = 32 MB`:

```text
(4 workers + 1 leader) × 32 MB
= 160 MB modeled sort budget
```

This is a conservative estimate, not a guaranteed exact RAM allocation.

### 19.2. Adding Concurrency

If 10 similar parallel queries run simultaneously, the modeled budget scales with concurrency. This is why workload and parallelism limits are necessary.

### 19.3. max_parallel_workers_per_gather

This setting limits the number of workers for a Gather/Gather Merge according to configuration. Increasing workers can improve throughput but increases CPU, memory, and I/O demand.

### 19.4. Parallel Queries Can Worsen Latency

If the host is already CPU/memory saturated, adding workers creates contention and can slow down all queries.

## 20. When Is Increasing work_mem the Right Choice?

Consider increasing it when:
- The plan shows significant sort/hash spills.
- The query has high latency due to temp I/O.
- The query has relatively accurate cardinality estimates.
- The host has memory headroom.
- Concurrency is controlled.
- The workload can be scoped by role/session/transaction.

### 20.1. Required Evidence

Capture EXPLAIN ANALYZE, actual rows, sort/hash details, temp blocks, query duration, concurrency, and host memory before making changes.

### 20.2. Increase in Small Steps

Try increasing from 16 MB to 32 MB or 64 MB for the specific transaction, re-measure, and stop once there is no meaningful improvement.

### 20.3. Check the Whole Workload

Making one query faster is not worth it if other API queries suffer OOM/swap or connection failures.

### 20.4. Compare Throughput and Latency

Evaluate p95/p99, total throughput, temp I/O, peak memory, and error rate.

## 21. When Should You NOT Increase work_mem?

Do not increase it just because:
- CPU is high.
- The database host has lots of RAM.
- A query is slow but is waiting on locks.
- The query plan scans too many rows due to missing indexes.
- Statistics are stale/wrong.
- The connection pool is saturated.
- Disk/network is the bottleneck.
- The query returns far more rows than needed.
- Many concurrent queries are already causing memory pressure.

### 21.1. Lock Wait

Increasing `work_mem` does not release a blocking transaction. Inspect the lock graph.

### 21.2. Bad Query Plan

An unreasonable full table scan or nested loop requires query/index/statistics analysis.

### 21.3. Network Bottleneck

If the query is fast in the database but the response is slow due to transferring millions of rows, reduce output/round trips.

### 21.4. Pool Saturation

If requests are waiting for connections, increasing `work_mem` will not help; it may even make running queries consume more RAM.

## 22. Optimize the Query Before Increasing Memory

Ways to reduce memory demand:
- `SELECT` only the necessary columns.
- Reduce rows before sort/aggregate.
- Create indexes supporting filters/ordering.
- Write predicates that can use indexes.
- Check join keys and cardinality.
- Avoid unnecessary `DISTINCT`.
- Batch or partition aggregations.
- Update statistics.
- Reduce N+1 query patterns.
- Avoid materializing large datasets unnecessarily.

### 22.1. Push Filters Down Early

Reducing the number of rows entering a sort/hash can drastically reduce memory and temp I/O.

### 22.2. Index Order

An appropriate index can eliminate a Sort node. Weigh the trade-offs of write amplification, storage, and index maintenance.

### 22.3. Join Order and Estimates

Check actual rows, loops, and join algorithms. The planner may choose an inappropriate build side when statistics are inaccurate.

### 22.4. Query Rewrite

A sensible query rewrite can reduce row count/width or avoid a heavy operator. Measure before/after plans with representative data.

## 23. Monitoring Temp Files at the Database Level

`pg_stat_database` provides cumulative counters:

```sql
SELECT
    datname,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_stat_database
ORDER BY temp_bytes DESC;
```

### 23.1. temp_files

The number of temporary files created per database since stats reset.

### 23.2. temp_bytes

Total bytes written to temporary files. Use deltas to compute the temp write rate.

### 23.3. Counters Do Not Identify Which Query

Use `pg_stat_statements` `temp_blks_written` or logs to attribute spills to specific queries.

### 23.4. Reset Awareness

If `stats_reset` changes or the server/database is reset, do not compute deltas across the reset.

## 24. Monitoring Temp Blocks with pg_stat_statements

If the extension/version supports the corresponding fields:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    temp_blks_read,
    temp_blks_written,
    shared_blks_read,
    shared_blks_hit
FROM pg_stat_statements
ORDER BY temp_blks_written DESC
LIMIT 20;
```

### 24.1. temp_blks_written

Helps find queries that have written many temporary blocks since stats reset.

### 24.2. temp_blks_read

Indicates queries reading temporary blocks. A spilling operation typically both writes and reads temp data.

### 24.3. Computing Deltas

These columns are cumulative counters. Use consecutive samples to see which queries are spilling heavily in the current window.

### 24.4. Query Identity and Resets

Record `queryid`, `calls`, and `stats_reset`. Query entries may be deallocated/reset depending on configuration/version.

## 25. log_temp_files

`log_temp_files` lets PostgreSQL log created temporary files based on a size threshold.

Configuration check example:

```sql
SHOW log_temp_files;
```

Illustrative values:
- `-1`: do not log temp files.
- `0`: log all temp files.
- Positive number: log temp files at or above the threshold in KB.

### 25.1. Use in Investigations

You can set a threshold to detect queries creating large temp files. Combine with PID/query context and statement logs.

### 25.2. Log Volume

Setting `0` on a system with frequent spills can generate massive log volume. Choose an appropriate threshold and retention.

### 25.3. Parameter Context

Whether it can be changed at session/system level and required privileges depend on parameter context/version. Check `pg_settings` before changing.

### 25.4. Logs Do Not Replace EXPLAIN

Logs show that a temp file was created, but the plan is needed to understand which operator caused the spill.

## 26. temp_file_limit

`temp_file_limit` limits the amount of disk space a process can use for temporary files according to PostgreSQL semantics.

### 26.1. Role

It acts as a guardrail so a single process cannot consume excessive temp disk. When exceeded, the statement can be terminated.

### 26.2. Not a Fix for Spills

A low limit can turn a slow query into a failing query. It does not make the query use less memory.

### 26.3. Per-Process Semantics

Read the documentation for your exact version to understand per-process accounting and the impact of parallel workers. Do not treat it as a single instance-wide total quota.

### 26.4. Capacity Planning

Monitor temp filesystem free space, temp bytes rate, and concurrent queries. `temp_file_limit` is a last-resort guardrail, not a substitute for monitoring.

## 27. Memory Contexts in PostgreSQL

PostgreSQL uses memory contexts to manage allocations by lifetime. When a context is reset/freed, many related allocations are released together.

In supported versions, you can inspect the contexts of the current backend:

```sql
SELECT
    name,
    ident,
    parent,
    level,
    total_bytes,
    free_bytes,
    used_bytes
FROM pg_backend_memory_contexts
ORDER BY total_bytes DESC;
```

### 27.1. Current Backend

This view describes the memory contexts of the backend running the query, not a dashboard of total memory across all backends.

### 27.2. Do Not Confuse used_bytes with RSS

Memory context accounting does not include every type of memory/OS overhead and does not directly equal resident set size.

### 27.3. pg_log_backend_memory_contexts

Some versions provide a function to request another backend to log its memory contexts to the server log. Requires appropriate privileges and log volume control.

### 27.4. Use for Deep Diagnostics

Memory contexts are useful when suspecting a memory leak or abnormal allocation, but they do not replace host/cgroup memory metrics.

## 28. Monitoring Host and Container Memory

Database process memory must be evaluated alongside host/container memory.

Monitor:
- Available memory.
- RSS/working set.
- Swap in/out.
- Page faults.
- OOM kill events.
- Container/cgroup `memory.current` and `memory.max`.
- Memory pressure/stall signals if supported by the platform.
- Shared memory usage.

### 28.1. OOM Killer

If total demand exceeds the memory limit, Linux or the container runtime may kill a backend or postmaster depending on the situation. Consequences can be query errors or a database restart.

### 28.2. Swap

Swap activity can cause latency to spike sharply. PostgreSQL queries can become slow even when CPU is not busy.

### 28.3. Container Limits

Even if the host still has free RAM, hitting the container `memory.max` can still trigger an OOM kill.

### 28.4. Shared Memory Accounting

Do not naively sum the RSS of all backends because shared memory mappings can be double-counted. Use cgroup/OS accounting and understand how your exporter measures memory.

## 29. Capacity Model for work_mem

One way to build a budget:
1. Determine memory reserved for the OS and page cache.
2. Subtract `shared_buffers` and instance-level regions.
3. Reserve baseline backend memory, autovacuum, maintenance, replication, and monitoring.
4. Estimate how many sessions can concurrently run memory-heavy queries.
5. Estimate simultaneous operators per process.
6. Account for `hash_mem_multiplier`.
7. Account for parallel workers and the leader.
8. Leave headroom for spikes and unpredictable workloads.

```text
Host / container memory limit
    |
    +-- OS + kernel + page cache reserve
    +-- shared_buffers / WAL shared memory
    +-- backend baseline memory
    +-- maintenance / autovacuum workers
    +-- parallel query workers
    +-- work_mem consumers
    +-- extensions / monitoring / safety headroom
```

### 29.1. Do Not Dedicate All RAM to PostgreSQL Query Memory

The OS needs page cache, kernel memory, and headroom. Containers may also run sidecars/agents alongside the database.

### 29.2. Concurrency Matters More Than a Single Peak work_mem

One 256 MB query may be fine if run exclusively. One hundred concurrent 64 MB queries can be dangerous.

### 29.3. Base the Model on Real Workloads

Use active query concurrency, plan distribution, workers launched, and observed memory/temp I/O.

### 29.4. Capacity Reserve

Keep headroom for deployments, backups, autovacuum, failover/recovery, and unexpected traffic bursts.

## 30. Example: Choosing work_mem for OLTP

OLTP typically has many short transactions and high concurrency. Many queries do not need large sorts/hashes, but total active sessions can be very high.

Strategy:
- Use a conservative baseline `work_mem`.
- Keep pool concurrency bounded.
- Optimize indexes to avoid sorts.
- Use `SET LOCAL` for special endpoints/reports.
- Monitor temp spills and p95/p99.
- Do not raise the global setting just to fix one query.

### 30.1. Baseline Example

Suppose the API role uses `work_mem` of 8–16 MB (as an example only). An export endpoint running in its own transaction might be granted 64 MB after load testing.

### 30.2. Controlling Concurrency

If an export job runs 20 concurrent workers, potential memory consumption can be large. Limit job concurrency and parallel workers.

### 30.3. Separate Pools

You can use a dedicated pool for reporting/export so heavy workloads do not exhaust OLTP connection slots.

### 30.4. Prioritize Query Optimization

Reducing rows/columns and leveraging indexes is usually more sustainable than increasing `work_mem`.

## 31. Example: Choosing work_mem for Reporting/Analytics

Reporting queries typically:
- Sort many rows.
- Group across many dimensions.
- Hash join large datasets.
- Use window functions.
- Run in parallel.

Strategy:
- Dedicated role/database.
- Higher `work_mem` within bounded limits.
- Low pool concurrency.
- Controlled parallelism.
- Sufficiently sized temp filesystem.
- Query plans and memory measured before/after.

### 31.1. Do Not Let Reporting Starve OLTP Memory

Separate connection pools and limit concurrency. If sharing an instance, set explicit resource budgets.

### 31.2. Pre-Aggregation

Materialized views, summary tables, or ETL can reduce the memory required by interactive queries.

### 31.3. Partition Pruning

Filtering on the partition key can reduce the rows entering sorts/hashes.

### 31.4. Workload Scheduling

Run heavy reports during appropriate windows and monitor their impact on backups, vacuum, and replication.

## 32. Example: Tuning with SET LOCAL

Suppose a specific report spills heavily and you have verified the host has memory headroom.

```sql
BEGIN;

SET LOCAL work_mem = '96MB';
SET LOCAL hash_mem_multiplier = 2.0;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT customer_id, date_trunc('month', created_at) AS month,
       sum(total)
FROM orders
WHERE created_at >= DATE '2026-01-01'
GROUP BY customer_id, date_trunc('month', created_at)
ORDER BY month, customer_id;

COMMIT;
```

This is a testing example. Use realistic queries, representative data volumes, and measure memory/temp I/O. EXPLAIN ANALYZE executes the query.

### 32.1. Compare Against Baseline

Run the same query with the baseline setting, recording duration, temp blocks, plan, actual rows, and memory evidence.

### 32.2. Test One Variable at a Time

Change `work_mem` first, then consider `hash_mem_multiplier`. Changing multiple parameters at once makes it hard to tell what caused the improvement.

### 32.3. Does Rollback Revert Settings After COMMIT?

`SET LOCAL` automatically expires when the transaction ends, including COMMIT. No `RESET` is needed after the transaction.

### 32.4. Test Under Concurrency

A single report running faster is not enough. Run multiple reports concurrently and observe host memory and OLTP latency.

## 33. Tuning by Role and Pool

Role configuration example:

```sql
ALTER ROLE analytics_reader
SET work_mem = '64MB';

ALTER ROLE api_reader
SET work_mem = '12MB';
```

### 33.1. New Sessions

Role defaults are applied when a session logs in. Recycle pool connections if needed for them to pick up the new configuration.

### 33.2. Per-Request Override

A heavy endpoint can use `SET LOCAL` inside a transaction without changing the entire role.

### 33.3. Pool Reset

Check whether the pooler resets session state after check-in. Otherwise, one request can leave a setting behind for the next request.

### 33.4. Do Not Split Roles Just for Higher Memory

Roles should reflect security and workload ownership. Avoid proliferating roles if the application cannot manage them cleanly.

## 34. Parallel Workers and Concurrency Limits

Related settings:
- `max_parallel_workers_per_gather`.
- `max_parallel_workers`.
- `max_worker_processes`.
- `parallel_setup_cost`.
- `parallel_tuple_cost`.

### 34.1. max_parallel_workers_per_gather

Limits the number of workers for a Gather/Gather Merge. Increasing it can increase CPU and memory pressure.

### 34.2. max_parallel_workers

Limits the total parallel workers that can run concurrently on the instance per configuration.

### 34.3. max_worker_processes

Limits overall worker processes, including certain background workers and parallel workers. Check which worker types share this limit.

### 34.4. Worker Launch Failure

If workers are unavailable, a query can still run with fewer workers than planned. EXPLAIN ANALYZE reveals `Workers Planned`/`Workers Launched`.

### 34.5. Parallelism Does Not Replace Memory Planning

Reducing parallel workers can lower memory/CPU pressure but make an individual query take longer. Measure overall throughput, not just single-query runtime.

## 35. work_mem and Temp Filesystem Capacity

When queries spill, temporary files use storage on PostgreSQL's temp path or database tablespaces according to configuration.

### 35.1. Temp I/O Latency

Fast disks can make external sorts less harmful, but they still consume bandwidth/IOPS and compete with data/WAL I/O.

### 35.2. Free Space

Monitor free bytes on the filesystem holding temp files, especially for reporting/batch workloads.

### 35.3. Temp Tablespaces

If `temp_tablespaces` is configured, monitor each tablespace/mount. Temp spills can be distributed according to configuration.

### 35.4. Disk Full

Temporary file creation failures can cause queries to fail. Do not rely on `temp_file_limit` in place of capacity alerts.

## 36. Autovacuum and Maintenance Memory Are Not work_mem

VACUUM/CREATE INDEX and maintenance tasks have their own budgets. Do not raise `work_mem` to fix slow autovacuum.

### 36.1. maintenance_work_mem

Can affect the speed/capability of certain maintenance operations. Account for concurrency of maintenance commands.

### 36.2. autovacuum_work_mem

Autovacuum workers can run concurrently. Total memory must account for the number of workers and the corresponding setting.

### 36.3. CREATE INDEX

Some index build operations use `maintenance_work_mem`. Parallel index builds involve additional process/resource behavior depending on version.

### 36.4. Vacuum Memory vs. work_mem

Do not apply `work_mem` formulas to every process. Use the right parameter and view for each operation type.

## 37. work_mem and Memory Leaks / Long-Lived Sessions

Completed queries generally free operation memory according to context lifetime. However, backends can retain memory contexts/cache structures across a session depending on implementation.

### 37.1. Long-Lived Sessions

Monitor backend memory, transaction state, and session churn. A long-lived session alone does not prove a leak.

### 37.2. Prepared Statements

Generic/custom plans and prepared statements affect plan reuse; they do not turn `work_mem` into a fixed per-session quota.

### 37.3. Memory Contexts

When suspecting memory growth, inspect per-backend contexts and host RSS/cgroup metrics. Do not conclude from a single snapshot.

### 37.4. Restarting Is Not Tuning

Restarting to free memory causes downtime/connection disruption. Identify the allocation source and query pattern first.

## 38. Monitoring Dashboard for work_mem

A useful dashboard includes:
1. Query p50/p95/p99 duration.
2. Top query `temp_blks_written`.
3. Database `temp_files`/`temp_bytes` rate.
4. Sort Method `external merge` count/rate if collected from plans/logs.
5. Hash batches > 1 from plan samples.
6. Active memory-heavy queries/concurrency.
7. Parallel workers planned/launched.
8. Host/container memory available/working set.
9. Swap/OOM/cgroup events.
10. Temp filesystem free space and I/O latency.
11. Pool active/waiters.
12. Query throughput and error rate.

### 38.1. No Built-In Instance-Wide Gauge for Current work_mem Used

`work_mem` is an operational budget, not a simple global counter. Combine plan/log instrumentation, selective memory contexts, process/host metrics, and a workload model.

### 38.2. Sampling Query Plans

You do not need to EXPLAIN every query in production. Use `pg_stat_statements` to pick candidates, selective slow logs/`auto_explain`, and tracing.

### 38.3. Query Text Cardinality

Do not put raw SQL or user parameters into metric labels. Use `queryid`/normalized query class and protect sensitive information.

### 38.4. Correlate with Deployments

A release that changes query shapes or planner estimates can increase spills. Annotate deployments and migrations.

## 39. Alerting for Memory and Temp Spills

Example alert conditions that should be tuned to your baseline:
- Sustained low host/container available memory.
- Rising swap in/out.
- OOM kill events occurring.
- Sudden spike in temp bytes/s.
- Temp filesystem free space below threshold.
- p95 query latency and temp I/O rising together.
- Increasing pool waiters while active query count is high.
- Parallel worker contention.
- A query class repeatedly generating large temp files.

### 39.1. Symptom Alerts

p95 latency breaching SLO is user impact. Use it as a paging signal.

### 39.2. Cause/Risk Alerts

Low memory headroom, nearly full temp disk, and OOM events are risk signals requiring action.

### 39.3. Do Not Alert Simply Because Temp Files Exist

Spilling can be normal behavior. Alert on rate, size, latency, and capacity.

### 39.4. Preventing Alert Noise

Use duration, hysteresis, and severity levels. A reporting query spilling 20 MB may not be worth paging if SLOs are still met.

## 40. Troubleshooting: Query Sort Spill

Symptoms:
- Query duration increases.
- EXPLAIN shows `external merge`.
- `temp_blks_written` increases.

Procedure:
1. Save the query plan and sanitized parameters.
2. Inspect actual rows and width.
3. Check filter selectivity.
4. Check whether an index can satisfy `ORDER BY`.
5. Check `LIMIT`/top-N behavior.
6. Check sort spill bytes and temp filesystem.
7. Test small increases with `SET LOCAL work_mem` in staging/load tests.
8. Measure query latency and memory under concurrency.
9. Choose query rewrite/index or a scoped setting.
10. Monitor for regressions after deployment.

### 40.1. If Actual Rows Exceed Estimate

Run ANALYZE, inspect skew/extended stats, and check plan stability.

### 40.2. If an Index Eliminates the Sort

Evaluate the write cost/storage of the index and the workload mix before creating it.

### 40.3. If Only One Report Spills

Use transaction/role scope instead of a global setting.

## 41. Troubleshooting: Hash Join / Hash Aggregate Spill

Symptoms:
- Hash Batches greater than 1.
- Temp blocks increase.
- Query has a large Hash/HashAggregate node.

Procedure:
1. Identify the hash node and build side.
2. Compare planned rows vs. actual rows.
3. Inspect row width and group cardinality.
4. Check statistics.
5. Check join keys/indexes/filters.
6. Check effective `hash_mem_multiplier` and `work_mem`.
7. Test scoped adjustments.
8. Measure batches, temp I/O, latency, and memory.
9. Evaluate concurrency/parallel workers.
10. Choose a solution that benefits the whole workload.

### 41.1. Large Hash Table Due to Many Groups

May require pre-aggregation, partitioning, or query rewrite.

### 41.2. Poor Build Side Choice

Inaccurate estimates can cause the planner to pick a large build side. Update stats and check join order.

### 41.3. Do Not Permanently Force Enable/Disable Hash Joins

Planner switches are useful for diagnosis, not a substitute for root-cause analysis. Avoid turning temporary workarounds into system-wide configuration.

## 42. Troubleshooting: Memory Pressure / OOM

Symptoms:
- Container memory near limit.
- Swap increasing.
- OOM kills.
- Query failures or backend restarts.
- Latency rising across multiple workloads.

Procedure:
1. Check host/container memory limit and available memory.
2. Check OOM/cgroup events and process RSS.
3. Count active sessions/parallel workers.
4. Identify workloads running sort/hash-heavy queries.
5. Inspect effective `work_mem`/`hash_mem_multiplier` by role/session.
6. Check pool concurrency and batch job parallelism.
7. Reduce concurrency or parallel workers per incident policy.
8. Lower overly high settings at the appropriate scope.
9. Verify latency/throughput and error rate recovery.
10. Update the capacity model and guardrails.

### 42.1. Do Not Just Slash Global work_mem Immediately

If the workload needs memory, dropping it sharply can trigger a temp I/O explosion. Prioritize finding the sessions/roles causing pressure and make controlled changes.

### 42.2. Do Not Kill Sessions Arbitrarily

Identify the business operation, transaction safety, and owner before canceling/terminating a backend.

### 42.3. OOM Evidence

Preserve timestamps, cgroup memory, process list, PostgreSQL logs, active queries, and settings. Use the evidence to calibrate capacity.

## 43. Test Strategy for work_mem Changes

A change should be tested with:
- Representative queries and production-equivalent data volumes.
- Baseline and candidate `work_mem`.
- Realistic concurrency.
- Parallel workers planned/launched.
- Temp I/O.
- Peak memory/working set.
- p50/p95/p99 latency.
- TPS/throughput.
- Errors/OOM/swap.
- Impact on OLTP and background jobs.

### 43.1. Single-Query Tests Are Not Enough

One query running alone does not simulate the memory pressure of 20 concurrent queries.

### 43.2. Test Peak Windows

Use peak-hour workload mixes, batch overlaps, and reporting concurrency.

### 43.3. Compare the Same Data State

Statistics, cache state, dataset, and query parameters affect plans/performance. Record test conditions.

### 43.4. Rollback Criteria

Predefine thresholds for memory, latency, temp disk, and error rate that trigger a revert.

## 44. Best Practices by Scope

| Scope | How to use | Recommendation |
|---|---|---|
| Global | postgresql.conf | Conservative baseline for mixed workloads |
| Database | ALTER DATABASE | Only when the database workload is relatively homogeneous |
| Role | ALTER ROLE | Differentiate API/reporting roles |
| Session | SET | Use carefully with pooled connections |
| Transaction | SET LOCAL | Often ideal for query-specific tuning |
| Parallel query | Worker-aware budget | Account for workers and concurrency |
| Hash operations | hash_mem_multiplier | Tune separately after inspecting the plan |

### 44.1. Low Baseline, Targeted Overrides

Keep the default safe and grant extra memory to workloads with evidence.

### 44.2. Limit Concurrency

A small reporting pool can be safer than letting hundreds of sessions run memory-heavy queries.

### 44.3. Document the Owner

Every override needs an owner, rationale, scope, review date, and rollback plan.

### 44.4. Validate After Upgrades

New PostgreSQL major versions can change planner/executor behavior. Re-test memory assumptions after upgrading.

## 45. Common Misconceptions

1. **work_mem is the maximum RAM for a single query.** False: one query can have multiple operators.
2. **work_mem is the RAM for a single connection.** False: the setting applies per eligible operation.
3. **Increasing work_mem always makes queries faster.** False: it may have no effect or increase memory pressure.
4. **Every Sort node spills.** False: many sorts run in memory.
5. **Hash Batches = 1 means the query is guaranteed optimal.** False: you still need to examine CPU, row estimates, and latency.
6. **temp_bytes is current disk usage.** False: it is a cumulative counter.
7. **work_mem includes shared_buffers.** False: the two regions serve different purposes.
8. **temp_buffers fixes sort spills.** False: `temp_buffers` is for temporary tables.
9. **Parallel queries only use one work_mem.** False: multiple processes/operators can consume separate budgets.
10. **Multiplying workers × work_mem always gives exact RAM.** False: plan/operator behavior and shared parallel structures complicate reality.
11. **ALTER ROLE updates already open sessions.** Usually false; defaults apply at new logins.
12. **SET in a connection pool is always safe.** False if state is not reset.
13. **SET LOCAL persists after COMMIT.** False: local settings expire when the transaction ends.
14. **Hash multiplier increases memory for all sorts.** False: it scales the budget for hash-based operations.
15. **Temp files are always errors.** False: spilling can be a normal trade-off.
16. **Low CPU means there is plenty of memory.** False: the system could be swapping or waiting on I/O.
17. **A single-query benchmark is enough to pick a setting.** False: you must test concurrency.
18. **work_mem replaces maintenance_work_mem.** False: each parameter has its own purpose.
19. **Lowering work_mem has no risk.** False: temp I/O and latency can rise.
20. **You only need to look at free RAM.** False: you need cgroup limits, shared memory, swap, process concurrency, and headroom.

## 46. Practice Exercises with Answers

### Exercise 1. What is work_mem?

**Answer:** The memory budget per eligible query operation, primarily sort and hash operations, before spilling/batching strategies are required.

### Exercise 2. Is work_mem the total memory limit for a query?

**Answer:** No. A single query can contain multiple memory-consuming operators.

### Exercise 3. Does work_mem apply per connection or per operation?

**Answer:** Per eligible operation in the executor; each backend/process can run multiple operations depending on the plan.

### Exercise 4. Why can increasing work_mem globally be dangerous?

**Answer:** Multiple sessions, operators, and parallel workers can simultaneously use separate budgets, causing total memory demand to grow large.

### Exercise 5. What is a sort spill?

**Answer:** A sort exceeding its memory budget and using temporary files / external sort.

### Exercise 6. What indicators of external sort can EXPLAIN show?

**Answer:** Sort Method such as `external merge` and `Disk` usage.

### Exercise 7. What does Hash Batches greater than 1 suggest?

**Answer:** The hash operation split data into multiple batches, typically involving spilling/temp I/O.

### Exercise 8. What does a hash join use memory for?

**Answer:** The build-side hash table and related structures.

### Exercise 9. Why does hash aggregate need memory?

**Answer:** It maintains a hash table for grouping keys and aggregate states.

### Exercise 10. What is hash_mem_multiplier used for?

**Answer:** Multiplies `work_mem` to determine the relative memory limit for hash-based operations.

### Exercise 11. work_mem = 32 MB, hash_mem_multiplier = 2; what is the approximate base hash budget?

**Answer:** Around 64 MB according to the corresponding version/semantics.

### Exercise 12. Does increasing hash_mem_multiplier increase the sort budget?

**Answer:** No; it applies to hash operations.

### Exercise 13. Why do actual rows matter?

**Answer:** Actual cardinality determines the volume of tuples entering sorts/hashes and can differ from the planner estimate.

### Exercise 14. What can stale statistics cause?

**Answer:** Inaccurate planner estimates, leading to suboptimal plans and unexpected memory behavior.

### Exercise 15. Does EXPLAIN ANALYZE execute the query?

**Answer:** Yes. Be careful with DML and side effects.

### Exercise 16. Is pg_stat_database.temp_bytes a counter or a gauge?

**Answer:** A cumulative counter; compute delta over time to obtain the temp write rate.

### Exercise 17. How does pg_stat_statements temp_blks_written help?

**Answer:** Identifies query entries writing large numbers of temporary blocks.

### Exercise 18. What does log_temp_files = 0 mean?

**Answer:** Log all temporary files according to the parameter's semantics.

### Exercise 19. Does temp_file_limit make a query use less memory?

**Answer:** No. It limits the temp disk space a process can use; exceeding it can cause the query to fail.

### Exercise 20. Whose memory does pg_backend_memory_contexts report?

**Answer:** The backend/session running the query on that view, not the whole instance.

### Exercise 21. Why can summing RSS across all backends double-count?

**Answer:** Shared memory mappings can be counted in the RSS of multiple processes.

### Exercise 22. What scope does SET work_mem affect?

**Answer:** The current session and subsequent queries until reset or the session ends.

### Exercise 23. How does SET LOCAL differ from SET?

**Answer:** `SET LOCAL` persists only within the current transaction and automatically expires upon COMMIT/ROLLBACK.

### Exercise 24. Why is SET LOCAL well-suited for connection pooling?

**Answer:** It scopes the setting to the transaction, reducing the risk of leaking session state to the next request.

### Exercise 25. When does ALTER ROLE SET work_mem take effect?

**Answer:** As the default for new sessions logging in with that role; already open sessions do not automatically receive the change.

### Exercise 26. Does ALTER DATABASE SET change all currently running backends?

**Answer:** No. The default generally applies to new sessions.

### Exercise 27. How does shared_buffers differ from work_mem?

**Answer:** `shared_buffers` is the shared page cache; `work_mem` is the budget for query operations.

### Exercise 28. What is maintenance_work_mem used for?

**Answer:** Certain maintenance operations such as VACUUM/CREATE INDEX according to version semantics.

### Exercise 29. What is temp_buffers used for?

**Answer:** Local buffers for temporary tables, not the sort spill budget.

### Exercise 30. How can parallel queries multiply memory pressure?

**Answer:** The leader and workers can execute memory-consuming operators with their own budgets.

### Exercise 31. What is the difference between Workers Planned and Workers Launched?

**Answer:** Planned is the number expected by the planner; Launched is the number actually started.

### Exercise 32. Does Parallel Hash always allocate a separate hash table per worker?

**Answer:** No. Some plans use shared parallel hash structures; check the implementation/plan.

### Exercise 33. Modeled sort budget formula for 4 workers and a leader, with work_mem 32 MB?

**Answer:** Around 5 × 32 = 160 MB if all 5 processes have one sort operation active simultaneously; this is a conservative estimate.

### Exercise 34. Should you sum every Sort/Hash node in a plan?

**Answer:** Not mechanically. Inspect node lifetimes and which operations are actually active at the same time.

### Exercise 35. When might increasing work_mem be the right choice?

**Answer:** When evidence shows sort/hash spills causing latency, estimates are reasonable, the host has headroom, and concurrency is controlled.

### Exercise 36. When should you not increase work_mem?

**Answer:** When the bottleneck is locks, CPU, network, pool queueing, a bad query plan, or when host memory is already scarce.

### Exercise 37. How can an index help reduce work_mem demand?

**Answer:** An appropriate index can eliminate an explicit sort or reduce the rows that must be processed.

### Exercise 38. Why can SELECT * make a sort use more memory?

**Answer:** Wider tuples increase the amount of data that must be held and sorted.

### Exercise 39. What strategy should OLTP use?

**Answer:** A conservative baseline, bounded pool concurrency, query optimization, and scoped overrides for heavy queries.

### Exercise 40. How should reporting be managed?

**Answer:** Dedicated role/pool, bounded concurrency and parallelism, and monitored temp capacity and memory.

### Exercise 41. Why is testing a single query insufficient?

**Answer:** It does not simulate multiple concurrent sessions/workers consuming memory simultaneously.

### Exercise 42. Which metrics should be inspected on an OOM event?

**Answer:** Host/cgroup memory, swap, OOM events, process RSS, active sessions, workers, and settings.

### Exercise 43. What is the trade-off of increasing max_parallel_workers_per_gather?

**Answer:** It can increase query parallelism, but it also raises CPU, memory, and I/O demand.

### Exercise 44. Does work_mem replace autovacuum_work_mem?

**Answer:** No. Autovacuum has its own memory configuration.

### Exercise 45. Why are temp files not always an incident?

**Answer:** Spilling is a mechanism for handling queries that exceed their memory budget; it only warrants intervention when causing latency/capacity impact.

### Exercise 46. Does hash Batches = 1 guarantee a fast query?

**Answer:** No. CPU, scans, locks, I/O, and the plan can still be bottlenecks.

### Exercise 47. How many variables should be changed at a time when tuning work_mem?

**Answer:** Test one variable/small group at a time so you can attribute the cause and keep rollback clear.

### Exercise 48. After changing a role default, what must be done with pool connections?

**Answer:** Recycle/reconnect sessions if needed to pick up the new default, and verify session state reset.

### Exercise 49. What does a good work_mem alert include?

**Answer:** Temp spill trend, query latency, host memory/headroom, temp disk capacity, duration, and a runbook.

### Exercise 50. What is the exit condition for work_mem tuning?

**Answer:** The query/workload meets target latency under representative concurrency without causing memory/OOM/temp capacity regressions, with a clear rollback and owner.

## 47. work_mem Tuning Checklist

| Step | Question |
|---|---|
| Query | Which operator is consuming memory? |
| Plan | Is it Sort, Hash, HashAggregate, or tuplestore? |
| Spill | External sort, batches, or temp blocks/files? |
| Estimate | Are planned rows close to actual rows? |
| Width | Are extra unnecessary columns being selected? |
| Index | Can a sort be avoided or the build side reduced? |
| Stats | Are ANALYZE/extended stats appropriate? |
| Scope | Global, database, role, session, or transaction? |
| Concurrency | How many memory-heavy queries run simultaneously? |
| Parallel | Workers planned/launched and leader participation? |
| Hash | What is the effective `hash_mem_multiplier`? |
| Host | Available memory, swap, cgroup limit, OOM? |
| Disk | Temp filesystem free space and latency? |
| Pool | Active sessions/waiters and job concurrency? |
| Test | Baseline/candidate tested under representative load? |
| Outcome | p95/p99, throughput, temp I/O, memory? |
| Safety | Are timeouts, rollback, and an owner in place? |
| Rollback | Is there a way to restore the previous setting? |
| Review | Is there version-specific validation after upgrades? |

## 48. Official PostgreSQL Documentation

- [Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html) — `work_mem`, `hash_mem_multiplier`, `shared_buffers`, and memory settings.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — reading sort/hash nodes, estimates, and actual execution.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — `pg_stat_database`, `pg_stat_activity`, and statistics.
- [pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html) — query-level execution/temp block statistics.
- [Parallel Query](https://www.postgresql.org/docs/current/parallel-query.html) — leader, workers, and parallel execution behavior.
- [Resource Consumption: Memory](https://www.postgresql.org/docs/current/runtime-config-resource.html#RUNTIME-CONFIG-RESOURCE-MEMORY) — memory parameters.
- [ALTER ROLE](https://www.postgresql.org/docs/current/sql-alterrole.html) — role-level defaults.
- [ALTER DATABASE](https://www.postgresql.org/docs/current/sql-alterdatabase.html) — database-level defaults.
- [SET](https://www.postgresql.org/docs/current/sql-set.html) — session and transaction-local configuration.
- [Logging Configuration](https://www.postgresql.org/docs/current/runtime-config-logging.html) — `log_temp_files` and query logging.
- [Monitoring I/O](https://www.postgresql.org/docs/current/monitoring-stats.html) — I/O stats by version.

Parameters, EXPLAIN fields, parallel memory behavior, and statistics views may vary across PostgreSQL major versions. Check `server_version`, `pg_settings`, view definitions, and the documentation for your exact version before putting configurations into production.

## 49. Summary: Allocate Memory in the Right Place, for the Right Duration

```text
Query plan
   |
   +-- Sort node       -> work_mem
   |
   +-- Hash node       -> work_mem × hash_mem_multiplier
   |
   +-- More operators  -> more possible consumers
   |
   +-- Parallel workers/leader -> more processes
   |
   v
Concurrent sessions and workloads
   |
   v
Total memory pressure + temp I/O
   |
   v
Measure -> scope setting -> load test -> verify
```

Key principles to remember:

1. **work_mem applies per operation.** A single query can have multiple sort/hash consumers.
2. **A session is not the only unit.** Multiple sessions and parallel workers can consume memory simultaneously.
3. **Hash operations have their own multiplier.** Check `hash_mem_multiplier` and your version.
4. **Spills are a signal to analyze.** External sorts, hash batches, and temp blocks show that an operator is using disk.
5. **Actual rows and row width matter.** Stale statistics or selecting unnecessary columns can drive up memory demand.
6. **SET LOCAL enables scoped tuning.** It works well for specific queries/requests and connection pooling when transactions are managed properly.
7. **Role/database defaults apply to new sessions.** Existing pool connections may retain previously loaded settings.
8. **Parallel queries increase resource demand.** Inspect Workers Launched, leader participation, and concurrency.
9. **Do not confuse work_mem with shared_buffers or maintenance_work_mem.** Each parameter has a distinct role.
10. **Optimize queries before increasing memory.** Indexes, filters, join strategies, and statistics can reduce demand.
11. **Monitor both RAM and temp disk.** Increasing memory can reduce spills but create OOM risk; lowering memory can increase temp I/O.
12. **Test under concurrent load.** A single query running alone does not represent production concurrency.

**One sentence to remember:** *`work_mem` is a per-operation budget, so choose defaults based on concurrency and only increase it in a controlled manner at the needed session/transaction scope after measuring the plan, spills, parallel workers, and memory headroom.*
