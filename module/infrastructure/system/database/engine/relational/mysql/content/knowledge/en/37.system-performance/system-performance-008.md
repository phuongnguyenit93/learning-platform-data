# `sort_buffer_size`, `join_buffer_size`, and Per-Connection Memory Multiplication

A MySQL server can still have plenty of free RAM yet hit memory allocation errors when load spikes suddenly. The cause often lies in how many concurrent sessions perform sorts, joins, scans, or create temporary tables simultaneously. Variables like `sort_buffer_size` and `join_buffer_size` control part of the working memory for those operations. They can speed up a specific query, but if set too high at the `GLOBAL` level, total memory consumption when many queries run concurrently can far exceed expectations.

This lesson explains how MySQL allocates per-connection and per-operation memory, the roles of `sort_buffer_size` and `join_buffer_size`, how to distinguish local memory from global memory, and how to budget memory based on concurrency. Examples target MySQL 8.0/8.4; join algorithms, metric names, and some variables may vary by version. Always verify configuration and execution plans on the exact version in operation.

## 1. Learning Outcomes

After this lesson, learners will be able to:

- Explain why connection count does not equate to the number of large buffers currently allocated.
- Describe when `sort_buffer_size` and `join_buffer_size` are used.
- Identify other per-session buffers such as `read_buffer_size`, `read_rnd_buffer_size`, and `net_buffer_length`.
- Distinguish per-connection memory, per-operation memory, and server-wide shared memory.
- Estimate peak memory from concurrent operations instead of mechanically multiplying every variable by `max_connections`.
- Use Performance Schema, `sys` schema, status variables, and OS tools to measure memory.
- Read `EXPLAIN` to locate sorts, full joins, and why queries require large memory.
- Test variable changes at `SESSION` scope, measure results, and promote settings to `GLOBAL` only with evidence.

## 2. Memory Model of a MySQL Server

No single variable represents all RAM used by MySQL. Memory can be divided into three categories:

1. **Global memory**: shared or serving the entire server, such as InnoDB buffer pool, log buffer, key buffer, data dictionary, table cache, and some Performance Schema structures.
2. **Per-connection or per-thread memory**: serves a client session, such as thread stack, network buffers, and certain session structures.
3. **Per-operation memory**: allocated when a query needs to sort, join, scan, read randomly, or create an internal temporary table. A single session can need multiple operation buffers within one query.

In the default one-thread-per-connection configuration, each served connection is typically paired with one thread. The thread cache can reuse threads after clients disconnect; the thread pool plugin changes execution scheduling. Thus, "per-connection memory" is a convenient budgeting model, while actual thread counts and allocation behavior depend on server configuration.

~~~mermaid
flowchart TB
    A[MySQL process memory] --> B[Global memory]
    A --> C[Connection and thread memory]
    A --> D[Operation memory]
    B --> B1[InnoDB buffer pool]
    B --> B2[Log buffer and caches]
    B --> B3[Performance Schema and metadata]
    C --> C1[Thread stack]
    C --> C2[Network buffers]
    D --> D1[Sort buffer]
    D --> D2[Join buffers]
    D --> D3[Read buffers and temporary tables]
    E[Operating system and other processes] --> F[Available physical or cgroup memory]
    A --> F
~~~

An idle session does not necessarily hold all sort and join buffers at maximum size. Many buffers are allocated only when an operation needs them. However, when many queries sort or join concurrently, many memory allocations can coexist. Some structures are retained or reused over the session lifecycle; memory usage after a query may not immediately drop back to its exact initial baseline.

## 3. Classification of Key Memory Variables

| Variable | Usage Scope | When to Pay Attention |
|---|---|---|
| `sort_buffer_size` | Sort buffer for a session performing a sort | `ORDER BY`, `GROUP BY`, or `filesort` |
| `join_buffer_size` | Buffer for certain join algorithms not using an index directly, including hash join/BKA cases depending on version and plan | Joins requiring scans or hashing data |
| `read_buffer_size` | Sequential read buffer for certain table scans | Large scans, sequential reads |
| `read_rnd_buffer_size` | Buffer for reading rows in order after certain sort operations | Reading rows back in sorted order |
| `thread_stack` | Stack for worker threads | Thread count, call stack depth, and system limits |
| `net_buffer_length` | Initial size of the communication buffer | Client/server connections and packets |
| `max_allowed_packet` | Packet/message size limit | Transferring BLOB, JSON, or large statements |
| `tmp_table_size` | Size limit for certain in-memory internal temporary tables | `GROUP BY`, `DISTINCT`, `UNION`, and intermediate queries |
| `max_heap_table_size` | Limit for `MEMORY` tables; also participates in capping certain internal temporary tables | `MEMORY` tables and engine-specific temporary tables |
| `temptable_max_ram` | RAM budget for the `TempTable` engine on supporting versions | Internal temporary tables using `TempTable` |
| `binlog_cache_size` | Transaction buffer for the binary log | Transactions writing large amounts of data before commit |

Do not sum all values in the table to compute mandatory RAM per connection. Variables have different trigger conditions and scopes, and some limits apply per engine or server-wide. Check documentation for your exact version before putting a variable into a budget model.

## 4. `sort_buffer_size`

`sort_buffer_size` defines the size of the sort buffer a session can use when MySQL performs a sort operation. The buffer is allocated when sorting is needed; a connection that does not sort does not automatically consume this entire amount simply because the variable is set high.

Situations commonly requiring sorting include:

- `ORDER BY` that cannot obtain ordering directly from an index.
- `GROUP BY` requiring sorting under a given execution plan.
- Certain `DISTINCT`, `UNION`, or intermediate processing operations.
- Part of a join plan or result processing requiring `filesort`.

MySQL can use an index to satisfy ordering. When it cannot, the optimizer may choose the `filesort` algorithm. The name "filesort" does not mean every sort writes to disk: the algorithm can finish in memory or use temporary files when data does not fit in the buffer or requires multiple merge passes.

### 4.1. Sort Signals Worth Investigating

Useful status variables:

- `Sort_rows`: number of sorted rows.
- `Sort_scan`: number of sorts performed by scanning the table.
- `Sort_range`: number of sorts performed using ranges.
- `Sort_merge_passes`: number of merge passes the sort algorithm had to perform.

These variables are typically cumulative counters. Measure deltas or rates over the same time window. If `Sort_merge_passes` climbs quickly alongside latency and temporary I/O, the buffer may be too small for that workload; however, this alone is not sufficient evidence to raise the setting. First inspect row counts, row widths, indexes, and the execution plan.

Example check:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Sort_rows',
  'Sort_scan',
  'Sort_range',
  'Sort_merge_passes'
);

SHOW SESSION STATUS
WHERE Variable_name IN (
  'Sort_rows',
  'Sort_scan',
  'Sort_range',
  'Sort_merge_passes'
);
~~~

Global status helps observe the whole server; session status is ideal for measuring one query inside the running session. Record values before and after running the query and compute the difference. Avoid comparing post-restart global counters against pre-restart data without accounting for resets.

### 4.2. Reading `EXPLAIN`

Example:

~~~sql
EXPLAIN
SELECT customer_id, SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY customer_id
ORDER BY revenue DESC
LIMIT 20;
~~~

If `Extra` or the execution tree shows `filesort`, check:

- Is there an appropriate index for the filter predicates and grouping order?
- Are too many rows surviving the `WHERE` clause?
- Can filtering happen earlier or can fewer columns be carried?
- Does `ORDER BY` on an aggregated expression force sorting an intermediate result?
- Is the query returning more rows than actually needed?

`EXPLAIN ANALYZE` executes the query to measure actual time and row counts. Use it only on appropriate environments and datasets, because it runs the real query. Compare estimated rows with actual rows to spot stale statistics or wrong optimizer assumptions.

### 4.3. Increasing Sort Buffer Has Limits

Raising `sort_buffer_size` can reduce merge passes for some large sorts, but gains are usually bounded. Once a sort fits in the buffer, raising it further does not meaningfully speed up the query. Overly large values allow each concurrent sort to hold a lot of RAM, shrinking memory available for the buffer pool or the OS.

If only one large report needs a bigger buffer, test adjusting it at `SESSION` scope for that specific session. Never raise `GLOBAL` just for one special query. Also review indexes, cardinality, `filesort`, row counts, and report design.

## 5. `join_buffer_size`

`join_buffer_size` governs the buffer size used in certain join operations. The classic case is a join that cannot use an appropriate index for the join predicate and must process many rows from one side. Newer MySQL versions can use hash joins; BKA (Batched Key Access) and other join algorithms may also use the join buffer depending on conditions and optimizer choices.

Practical meaning depends on the chosen join algorithm:

- For nested-loop joins, missing indexes can force MySQL to repeatedly scan the inner table; the join buffer reduces accesses by processing in batches.
- For hash joins, memory is used to build or process the hash table; if data does not fit in memory, the algorithm may need to batch or spill to temporary resources.
- For BKA, the join buffer batches keys for bulk index lookups.

Across MySQL 8.0 releases, the optimizer and join algorithms evolved from release to release. Do not infer the algorithm solely from `join_buffer_size`; read `EXPLAIN FORMAT=TREE` or `EXPLAIN ANALYZE` on your running version.

### 5.1. One Buffer May Not Serve the Whole Query

A query can have multiple joins. Depending on the plan, MySQL may need multiple join buffers for different steps. Therefore, do not model cost as a single `join_buffer_size` per connection in all cases.

If the join buffer is too small for the dataset being processed, the query may need multiple batches and run slower. Raising the buffer can help some queries, but a large join buffer does not fix missing indexes, non-selective join conditions, or poor schema design.

### 5.2. Inspecting Problematic Joins

Helpful status variables:

- `Select_full_join`: number of joins that do not use indexes.
- `Select_range_check`: number of joins where the optimizer checks range indexes row by row.

These are cumulative counters. Inspect deltas over time, then find matching query digests in Performance Schema.

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Select_full_join',
  'Select_range_check'
);

SELECT
  DIGEST_TEXT,
  COUNT_STAR,
  SUM_SELECT_FULL_JOIN,
  SUM_SELECT_RANGE_CHECK,
  SUM_ROWS_EXAMINED,
  SUM_TIMER_WAIT
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY SUM_SELECT_FULL_JOIN DESC, SUM_ROWS_EXAMINED DESC
LIMIT 20;
~~~

If a query performs an indexless join, check data types of both join columns, collations, expressions or functions applied to columns, join order, and composite indexes. Incompatible data types can prevent the optimizer from using an index as expected.

### 5.3. Join Plan Example

~~~sql
EXPLAIN FORMAT=TREE
SELECT
  c.customer_id,
  c.segment,
  o.order_id,
  o.total_amount
FROM customers AS c
JOIN orders AS o
  ON o.customer_code = c.customer_code
WHERE c.segment = 'business'
  AND o.created_at >= '2026-01-01';
~~~

If both tables are large and `customer_code` on `orders` lacks an appropriate index, the optimizer may fall back to a hash join or an expensive scan plan. Inspect estimated/actual rows, filter selectivity, and access paths before raising `join_buffer_size`.

A candidate index might be:

~~~sql
CREATE INDEX ix_orders_customer_code_created_at
  ON orders (customer_code, created_at);
~~~

The index above is an example only. Choose column order based on query predicates, selectivity, write workload, and other queries. Use `EXPLAIN` to confirm the optimizer actually chooses the index; do not create indexes based solely on a single hypothetical query.

## 6. Other Per-Session Buffers

`sort_buffer_size` and `join_buffer_size` are only part of a query's working memory.

### 6.1. `read_buffer_size`

`read_buffer_size` provides buffering for certain sequential table scans. Each session performing such a scan may need this memory. Increasing it can help some large sequential scans, though unnecessary scans are usually better fixed with indexes or earlier filtering.

### 6.2. `read_rnd_buffer_size`

`read_rnd_buffer_size` is used in certain cases when reading rows in order after a sort. Large values can help workloads reading randomly in sorted order, but also increase memory overhead when many concurrent sessions run such operations.

### 6.3. `thread_stack`

`thread_stack` sets the stack size per thread. This is baseline memory that must be counted when estimating concurrent threads. Raise the stack only with evidence of call stack depth needs or stack overflow errors; setting it too high multiplied across threads can consume substantial RAM.

### 6.4. `net_buffer_length` and `max_allowed_packet`

`net_buffer_length` is the initial size of the communication buffer. The buffer can grow as needed for large messages up to `max_allowed_packet`. `max_allowed_packet` is a packet ceiling, not an amount immediately pre-allocated for every connection.

When applications transfer BLOBs, JSON, or large statements, examine payload size, concurrent client count, and packet errors. Do not set `max_allowed_packet` excessively high if the application does not need it; likewise, do not treat it as an exact predictor of allocated RAM.

### 6.5. Internal Temporary Tables

`GROUP BY`, `DISTINCT`, `UNION`, and certain intermediate queries can create internal temporary tables. Limits and storage paths depend on engine and version:

- `tmp_table_size` and `max_heap_table_size` govern limits for certain in-memory temporary tables.
- MySQL 8.0 uses the `TempTable` engine for many internal temporary tables; `temptable_max_ram` and related variables can govern server-wide `TempTable` budgets.
- Temporary tables exceeding memory limits may be converted to another storage format or spill to temporary disk resources, depending on version and data types.

Do not apply one universal formula to all temporary tables. Read the internal temporary tables documentation for your specific version and monitor `Created_tmp_tables`, `Created_tmp_disk_tables`, and `TempTable` metrics if supported by your exporter.

### 6.6. `binlog_cache_size`

When binary logging is enabled, transactions may use the binlog cache to buffer events before commit. Large transactions can exceed the initial buffer and spill to temporary files. Monitor `Binlog_cache_use` and `Binlog_cache_disk_use` to observe cache usage and disk spills. This is a per-transaction cache/buffer group, not a reason to raise sort or join buffers.

## 7. Global Memory and Non-MySQL Memory

Server budgeting must also include shared regions:

- `innodb_buffer_pool_size`: the largest data and index cache in most InnoDB systems.
- `innodb_log_buffer_size`: redo log buffer.
- `key_buffer_size`: MyISAM index cache.
- `table_open_cache` and `table_definition_cache`: metadata and table handle caches.
- Performance Schema: memory for instrumentation, histories, and summaries.
- Data dictionary, connection manager, replication, plugins, and other internal structures.

Beyond `mysqld`, the host needs RAM for the kernel, filesystem cache, monitoring agents, backups, proxies, sidecars, and other processes. In containers, cgroup limits may be lower than physical machine RAM. A process can be OOM-killed even when the host has free RAM if the container hits `memory.max`.

Do not equate `mysqld` RSS directly with the logical sum of individual variable sizes. RSS, virtual memory, page cache, shared memory, and instrumented memory are accounted for differently. Cross-check multiple sources.

## 8. Budgeting Memory by Concurrency

A simple estimation model:

~~~text
M_peak ≈ M_global
       + N_threads × M_base_thread
       + N_active_sorts × sort_buffer_size
       + N_active_join_buffers × join_buffer_size
       + M_internal_temp_tables
       + M_other
~~~

Where:

- `M_global` is MySQL's shared global memory.
- `N_threads` is the thread count to budget for at peak load; may be near active connections, though not always equal to `max_connections`.
- `M_base_thread` is baseline thread/session memory, including stack and actual connection buffers.
- `N_active_sorts` is the number of concurrently running sorts, not total connections.
- `N_active_join_buffers` is the actual number of join buffers held by concurrently running joins; one query can require more than one buffer.
- `M_internal_temp_tables` is total memory across active temporary tables and intermediate structures.
- `M_other` covers allocator overhead, plugins, replication, uninstrumented memory, and other components.

This is a model for asking questions and sizing headroom, not a strict MySQL limit. Components may be allocated conditionally, reused, or overlap in ways that cannot be deduced solely from configuration values.

### 8.1. Why `max_connections` Is Not the Multiplier for Every Buffer

Multiplying `max_connections × sort_buffer_size × join_buffer_size` is usually wrong because:

1. Idle connections are not running sorts or joins.
2. Not every query needs the same buffers.
3. Some buffers are allocated when an operation starts, not at connect time.
4. One query can allocate multiple operations/buffers; another needs none of those buffers.
5. Some limits apply to temporary tables or engines at a different scope.
6. `max_connections` is a cap on allowed connections, not a forecast of concurrent operations.

Still, using `max_connections` for worst-case analysis can be helpful if the model explicitly assumes many concurrent active sessions. Never treat that worst-case product as RAM guaranteed to be pre-allocated or as typical live usage.

### 8.2. Illustrative Budget Example

Suppose an instance has a 12 GiB buffer pool and other global regions measured at roughly 2 GiB. During peak hours, observations show:

- 80 active threads or threads holding session resources.
- 20 concurrent sorts running simultaneously, with a 2 MiB sort buffer.
- 35 join buffers in active use, with a 1 MiB join buffer.
- Temporary tables and intermediate structures using roughly 1 GiB.
- Other regions, allocator overhead, and unclassified memory needing 2 GiB of reserve.

Summary of listed items:

| Component | Estimate |
|---|---:|
| Buffer pool | 12 GiB |
| Other global memory | 2 GiB |
| Sort buffers: 20 × 2 MiB | 40 MiB |
| Join buffers: 35 × 1 MiB | 35 MiB |
| Temporary tables | 1 GiB |
| Headroom for other allocations | 2 GiB |

This example does not yet detail baseline memory for the 80 threads; measure and add it to `M_base_thread`. The 20 sorts and 35 join buffers represent observed concurrent operations, not all 80 connections using buffers simultaneously. If the sort buffer were raised to 16 MiB, 20 concurrent sorts alone would need about 320 MiB instead of 40 MiB. The impact scales with concurrency.

### 8.3. Reserves and Headroom

Do not budget right up to physical RAM. Leave headroom for bursts, large transactions, backups, replication catch-up, restarts, and cache warm-up. For containers, keep reserve headroom below `memory.max` to prevent OOM kills. On shared hosts, reserve RAM for the kernel and other processes.

Model at least three scenarios:

- Normal: typical concurrency and query mix.
- Peak: elevated concurrent sorts, joins, and temporary tables.
- Incident or failover: traffic concentrating onto the primary or surviving node.

## 9. Measuring Memory with Performance Schema and `sys` Schema

Performance Schema provides memory summary tables when the corresponding instrumentation is supported and enabled. These figures show instrumented memory and do not necessarily cover every process allocation.

Check memory instruments:

~~~sql
SELECT NAME, ENABLED, TIMED
FROM performance_schema.setup_instruments
WHERE NAME LIKE 'memory/%'
ORDER BY NAME
LIMIT 50;
~~~

Aggregate by event:

~~~sql
SELECT
  EVENT_NAME,
  CURRENT_NUMBER_OF_BYTES_USED,
  HIGH_NUMBER_OF_BYTES_USED
FROM performance_schema.memory_summary_global_by_event_name
ORDER BY CURRENT_NUMBER_OF_BYTES_USED DESC
LIMIT 20;
~~~

View by thread and join with session info:

~~~sql
SELECT
  t.PROCESSLIST_ID,
  t.PROCESSLIST_USER,
  t.PROCESSLIST_HOST,
  m.EVENT_NAME,
  m.CURRENT_NUMBER_OF_BYTES_USED,
  m.HIGH_NUMBER_OF_BYTES_USED
FROM performance_schema.memory_summary_by_thread_by_event_name AS m
JOIN performance_schema.threads AS t
  ON t.THREAD_ID = m.THREAD_ID
WHERE m.CURRENT_NUMBER_OF_BYTES_USED > 0
ORDER BY m.CURRENT_NUMBER_OF_BYTES_USED DESC
LIMIT 30;
~~~

The `sys` schema provides convenient views such as `sys.memory_global_by_current_bytes`, `sys.memory_global_total`, and `sys.memory_by_thread_by_current_bytes`. For example:

~~~sql
SELECT *
FROM sys.memory_by_thread_by_current_bytes
ORDER BY current_allocated DESC
LIMIT 20;
~~~

View column names may vary across `sys` schema versions. Check `DESCRIBE` or the view definition on your server if sample queries do not match.

### 9.1. Limitations of Instrumented Metrics

Performance Schema reports only allocations covered by supported and enabled instruments. If memory instruments are off or a library allocates outside instrumented paths, reported values may be lower than process RSS. Never conclude MySQL is not using RAM just because summaries look empty.

When enabling instruments to investigate, record the initial state, enable only the needed group, measure overhead, and restore configuration per procedure. Do not enable instruments wholesale in production without evaluating their cost first.

## 10. Reading Status and Correlating with Queries

To inspect sort/join metrics:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Sort_rows',
  'Sort_scan',
  'Sort_range',
  'Sort_merge_passes',
  'Select_full_join',
  'Select_range_check',
  'Created_tmp_tables',
  'Created_tmp_disk_tables',
  'Threads_connected',
  'Threads_running'
);
~~~

Performance Schema digests help locate query groups with sorts or full joins:

~~~sql
SELECT
  DIGEST_TEXT,
  COUNT_STAR,
  SUM_SORT_ROWS,
  SUM_SORT_MERGE_PASSES,
  SUM_SELECT_FULL_JOIN,
  SUM_ROWS_EXAMINED,
  SUM_TIMER_WAIT
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY SUM_SORT_MERGE_PASSES DESC, SUM_SELECT_FULL_JOIN DESC
LIMIT 20;
~~~

Summaries reset on server restart or when truncated/reset. They typically accumulate since startup or the last reset; record timestamps when comparing. Do not turn `DIGEST_TEXT` into a high-cardinality metric label; query Performance Schema directly or inspect logs during investigation.

## 11. Finding Root Causes Before Increasing Buffers

When sorts or joins are slow, follow this sequence:

1. Identify the query/digest and execution frequency.
2. Read `EXPLAIN` or `EXPLAIN FORMAT=TREE`; use `EXPLAIN ANALYZE` in an appropriate environment to measure actual row counts.
3. Check indexes, join predicates, data types, collations, and expressions on columns.
4. Inspect rows read, sorted, joined, temporary tables, and rows examined.
5. Measure `Sort_merge_passes`, `Select_full_join`, and before/after latency on the same workload.
6. Test changing a session buffer only if you have a hypothesis that the buffer is the bottleneck.
7. Measure execution time, memory peak, disk I/O, and impact on concurrent queries.

A full scan on a huge table can remain slow even if the join buffer is multiplied many times over. An `ORDER BY` returning millions of rows may need pagination or index redesign. Fixing the access path is usually far more durable than adding memory.

## 12. `SESSION` and `GLOBAL` Scopes

`sort_buffer_size`, `join_buffer_size`, and many buffer variables have both `GLOBAL` and `SESSION` scopes. The `GLOBAL` value sets the default for new sessions; changing `GLOBAL` does not necessarily alter `SESSION` values already established in existing connections. The `SESSION` value affects the current connection.

Check both scopes:

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'sort_buffer_size',
  'join_buffer_size',
  'read_buffer_size',
  'read_rnd_buffer_size',
  'thread_stack',
  'net_buffer_length',
  'max_allowed_packet',
  'tmp_table_size',
  'max_heap_table_size'
);

SHOW SESSION VARIABLES
WHERE Variable_name IN (
  'sort_buffer_size',
  'join_buffer_size',
  'read_buffer_size',
  'read_rnd_buffer_size'
);
~~~

Test in one session:

~~~sql
SET SESSION sort_buffer_size = 2 * 1024 * 1024;
SET SESSION join_buffer_size = 2 * 1024 * 1024;

SELECT @@SESSION.sort_buffer_size,
       @@SESSION.join_buffer_size;
~~~

The 2 MiB value is a lab example only, not a production recommendation. Compare results against the baseline session and record RAM usage. When finished, close the session or restore the original values.

`SET GLOBAL` changes the default for new sessions and may require appropriate administrative privileges. `SET PERSIST` can save changes across restarts on supporting versions. Global changes require review, rollback verification, and concurrency impact assessment. Never run `SET GLOBAL`/`SET PERSIST` in production just to test a single query.

## 13. Testing Sort Buffer in a Single Session

Create appropriately sized test data in a lab environment. Query that forces a `filesort`:

~~~sql
EXPLAIN
SELECT order_id, customer_id, total_amount
FROM orders
WHERE created_at >= '2026-01-01'
ORDER BY total_amount DESC
LIMIT 1000;
~~~

Record `SESSION` status before running:

~~~sql
SHOW SESSION STATUS
WHERE Variable_name IN (
  'Sort_rows',
  'Sort_merge_passes'
);
~~~

Run the query, then record execution time and status afterward. Repeat with `sort_buffer_size` at its baseline value and at a controlled test value. Keep data, cache state, and background load as constant as possible. Compare:

- Execution time.
- `Sort_merge_passes` and `Sort_rows`.
- Rows examined and rows returned.
- Process RAM or session instrumentation if available.
- Impact on other queries under concurrency.

If merge passes drop without improving latency, the bottleneck may lie in I/O, scans, or CPU. If the query speeds up in isolation yet the server runs out of RAM under concurrency, the change is unsuitable for production.

## 14. Testing Join Buffer in a Single Session

Select a join query on lab data. Read `EXPLAIN FORMAT=TREE` to see whether the optimizer uses nested loop, hash join, or another access path:

~~~sql
EXPLAIN FORMAT=TREE
SELECT
  a.code,
  a.description,
  b.amount
FROM source_a AS a
JOIN source_b AS b
  ON b.code = a.code
WHERE a.category = 'active';
~~~

If the query requires a join buffer, record execution time, rows read, actual rows, memory, and the plan. Test changing `join_buffer_size` at `SESSION` scope in a separate session and re-run under the same conditions.

Next, test an index matching the join predicate on the inner table, if data and business rules permit. Compare:

- Join plan before and after.
- Rows scanned and rows examined.
- Latency and I/O.
- Concurrent memory usage.
- Write overhead and disk footprint of the new index.

The goal is to understand why the optimizer chose an algorithm and how the buffer affects execution. Do not assume hash joins or join buffers are always faster than index lookups.

## 15. Choosing an Approach by Workload

| Workload | What to Observe | How to Tune |
|---|---|---|
| High-connection OLTP | Connection concurrency, latency, memory peak, pool waits | Keep buffers moderate; prioritize indexes and short queries |
| Large reporting | Sort rows, merge passes, temporary tables, scans | Test session buffers for dedicated jobs; optimize filtering, grouping, and pagination |
| ETL/batch | Batch concurrency, packet size, binlog cache, temporary tables | Cap concurrent jobs; measure per batch and transaction |
| Large-data joins | Full joins, hash joins, rows examined, indexes | Check access paths, statistics, and indexes before increasing join buffer |
| Memory-limited containers | cgroup memory, OOM events, RSS, and headroom | Budget against the container limit, not host RAM |

An OLTP instance typically prioritizes stability when many connections run concurrently. A specialized reporting query may need more memory, yet should run under controlled concurrency or on an analytical replica. Isolating workloads is usually easier to manage than setting huge global buffers for all sessions.

## 16. Alerting and Operational Monitoring

No single metric reveals that `sort_buffer_size` or `join_buffer_size` is exhausting RAM. Monitor a combination of:

- Concurrent threads and connections.
- `mysqld` RSS/working set, `memory.current`, and `memory.max` if running in a container.
- OS available memory, swap, major page faults, and OOM events.
- Growth rates of `Sort_merge_passes`, `Select_full_join`, and `Created_tmp_disk_tables`.
- Performance Schema current/high-water-mark memory by event and thread.
- Query latency, rows examined, disk I/O, and active reporting jobs.

Alert on symptoms: sustained low memory headroom, OOM kills, rising swap, rising latency, or disk temporary table spills coinciding with service impact. A single rising counter alone may be normal workload behavior.

When building dashboards, use stable labels such as `environment`, `cluster`, `instance`, and `role`. Avoid creating a time series per connection ID or SQL literal. Session and digest details should be queried from Performance Schema or logs during investigations.

## 17. Common Configuration Mistakes

### 17.1. Raising `sort_buffer_size` Globally to Fix One Report

If many sessions sort concurrently, total memory grows with active operations. Test `SESSION` on one connection, measure peak memory, and consider limiting report concurrency.

### 17.2. Raising `join_buffer_size` to Hide Missing Indexes

A large join without a good access path still has to process many rows. Check data types, indexes, join order, and `EXPLAIN` before raising the buffer.

### 17.3. Multiplying Every Buffer by `max_connections`

This is a conservative estimate that easily misleads if treated as actual allocation. Model concurrent sorts, joins, scans, and temporary tables, while still testing burst scenarios where many sessions are active simultaneously.

### 17.4. Looking Only at RSS or Only at Performance Schema

RSS can include allocator arenas, retained pages, and uninstrumented regions. Performance Schema can omit uninstrumented allocations. Use both MySQL and OS metrics to explain discrepancies.

### 17.5. Ignoring Container Limits

MySQL can be OOM-killed when hitting cgroup memory limits even if the physical host has spare RAM. Budget against actual process/container limits and reserve headroom for sidecars, agents, and page cache.

## 18. Runbook When MySQL Memory Grows Abnormally

1. Identify the instance, role, start time, and application impact.
2. Check available RAM, swap, OOM logs, cgroup limits, and `mysqld` RSS/working set.
3. Check `Threads_connected`, `Threads_running`, active queries, and application connection pools.
4. Inspect Performance Schema memory summaries by event and thread; verify enabled instruments.
5. Inspect statement digests, `Sort_merge_passes`, `Select_full_join`, and temporary tables.
6. Check recent deployments, batch jobs, new reports, large transactions, or configuration changes.
7. Gather `EXPLAIN`/`EXPLAIN ANALYZE` as appropriate and identify queries causing large sorts/joins/scans.
8. Reduce concurrency or pause jobs per runbook if OOM risk is imminent; avoid restarting hastily before collecting evidence.
9. Test index/query optimization or `SESSION` limits for specific jobs.
10. Monitor peak memory, latency, and error rates after changes; document configuration and rollback plan.

If the server is near OOM, prioritize controlled load shedding and protecting service availability. Never change multiple memory variables simultaneously, as it becomes hard to identify which change caused the effect.

## 19. Self-Check Exercises

1. Why does a server with 500 idle connections not necessarily have 500 sort buffers allocated?
2. A query has three joins requiring a join buffer. Why can modeling one `join_buffer_size` per connection underestimate memory?
3. `EXPLAIN` displays `filesort`. Does that prove data was sorted entirely on disk?
4. `Sort_merge_passes` climbs rapidly while latency remains steady. What additional metrics would you check?
5. A query uses a hash join. How would you verify the role of `join_buffer_size` and peak memory?
6. Why does raising `max_allowed_packet` not mean every session immediately allocates that much RAM?
7. Build a memory budget for 100 threads, with 15 sorts and 20 join buffers active concurrently.
8. If Performance Schema memory summary is lower than `mysqld` RSS, what reasons might explain the difference?
9. When should you use `SET SESSION` instead of `SET GLOBAL`?
10. A container is OOM-killed even though the host has spare RAM. How would you inspect `memory.max`, `memory.current`, and headroom?

## 20. Checklist Before Changing Buffers

- [ ] Identified the query or workload that genuinely needs a sort/join buffer.
- [ ] Read `EXPLAIN` or `EXPLAIN ANALYZE` and inspected indexes/access paths.
- [ ] Measured concurrency and active buffer operations.
- [ ] Recorded current `SESSION` and `GLOBAL` values.
- [ ] Verified units, scope, and behavior of variables on the running MySQL version.
- [ ] Tested `SESSION` changes first and compared against the same workload.
- [ ] Measured latency, rows examined, merge passes, I/O, and memory peak.
- [ ] Accounted for headroom for bursts, failover, and container limits.
- [ ] Prepared a rollback plan and assigned an owner for the change.
- [ ] Applied `GLOBAL`/`PERSIST` only after test evidence confirmed the improvement.

## 21. References

- [MySQL 8.4 Reference Manual — Server System Variables](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html)
- [MySQL 8.4 Reference Manual — Optimizing Server Parameters](https://dev.mysql.com/doc/refman/8.4/en/optimization-server-parameters.html)
- [MySQL 8.4 Reference Manual — ORDER BY Optimization](https://dev.mysql.com/doc/refman/8.4/en/order-by-optimization.html)
- [MySQL 8.4 Reference Manual — Nested-Loop Joins](https://dev.mysql.com/doc/refman/8.4/en/nested-loop-joins.html)
- [MySQL 8.4 Reference Manual — Hash Joins](https://dev.mysql.com/doc/refman/8.4/en/hash-joins.html)
- [MySQL 8.4 Reference Manual — Performance Schema Memory Summary Tables](https://dev.mysql.com/doc/refman/8.4/en/performance-schema-memory-summary-tables.html)
- [MySQL 8.4 Reference Manual — Internal Temporary Tables](https://dev.mysql.com/doc/refman/8.4/en/internal-temporary-tables.html)
- [MySQL 8.4 Reference Manual — Connection Interfaces](https://dev.mysql.com/doc/refman/8.4/en/connection-interfaces.html)

Variable names, optimizer algorithms, and instrumentation levels may vary by version. Use documentation matching the running server and inspect actual execution plans before changing configuration.
