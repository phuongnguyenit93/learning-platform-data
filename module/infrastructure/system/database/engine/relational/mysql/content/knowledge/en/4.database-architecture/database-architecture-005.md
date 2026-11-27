# Shared Memory, Per-Connection Memory, and Work Areas

MySQL needs memory to hold frequently accessed data pages, manage metadata, accept connections, execute SQL statements, sort results, and handle temporary tables. These memory areas have different lifetimes and sharing scopes. Some areas are shared across many connections for most of the server process's lifetime; some are tied to individual connections; and some are allocated only when a running query needs to perform a specific operation.

Distinguishing these three groups is fundamental to reading MySQL configuration, estimating safe connection counts, and investigating elevated RAM usage. Treating every memory configuration variable as a fixed per-connection allocation easily leads to misestimation. Conversely, looking only at shared memory such as the InnoDB buffer pool can overlook the extra RAM consumed when many heavy queries run concurrently.

This article focuses on MySQL 8.x with InnoDB as the primary storage engine. Some memory areas and configuration variables apply only to other engines or behave differently across versions.

## 1. Three Memory Groups in MySQL

Memory can be categorized by usage scope into three groups:

| Group | Scope | Lifetime | Examples |
|---|---|---|---|
| Shared memory (global/shared memory) | Used across many connections or the entire server | Typically exists for most of the mysqld process lifetime | InnoDB buffer pool, redo log buffer, metadata cache |
| Per-connection memory (connection/session memory) | Bound to a client session or its serving thread | From connection creation until termination, depending on structure | Thread stack, network buffer, session context |
| Work area (execution/work area) | A specific operation or active query | Allocated on demand and freed after the operation | Sort buffer, join buffer, read buffer, internal temporary table |

Conceptual diagram:

~~~text
MySQL Server Process (mysqld)
|
+-- Shared memory
|   +-- InnoDB buffer pool
|   +-- InnoDB redo log buffer
|   +-- Metadata cache / table definition / table open
|   +-- Performance Schema and server management structures
|
+-- Client connections
    |
    +-- Connection A
    |   +-- Thread / session context
    |   +-- Network buffer
    |   +-- Work areas when queries need them
    |
    +-- Connection B
    |   +-- Thread / session context
    |   +-- Network buffer
    |   +-- Work areas when queries need them
    |
    +-- Connection C ...
~~~

This is a classification for reasoning and capacity planning. In the codebase, certain structures may belong to threads, sessions, engines, or allocators; not every allocation fits neatly into a single box.

## 2. Shared Memory

Shared memory is allocated by MySQL or a storage engine to serve multiple connections. Each connection does not need its own private copy of this entire region. For example, thousands of InnoDB sessions can concurrently access pages residing in a single buffer pool.

### 2.1. InnoDB Buffer Pool

The InnoDB buffer pool is typically the largest and most important memory region in a MySQL configuration using InnoDB. It stores data and index pages read from tablespaces or recently modified. When a query needs a page already in the buffer pool, InnoDB can read it from RAM instead of issuing a storage device read.

The buffer pool holds pages in page units, not a complete mirror of every table. Pages are loaded and evicted based on access patterns. A page modified in memory but not yet written to its tablespace is a dirty page; InnoDB flushes these pages to storage via background mechanisms and checkpoints.

Primary configuration variable:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_buffer_pool_size';
~~~

Example configuration in an options file:

~~~ini
[mysqld]
innodb_buffer_pool_size=8G
~~~

The value 8G is an illustration only, not a recommendation for every host. The right size depends on available physical RAM, active working set size, query workload, connection count, OS memory needs, and other MySQL components. Dedicated database servers typically allocate a large portion of RAM to the buffer pool, while still leaving sufficient headroom for everything else and avoiding swap.

### 2.2. InnoDB Redo Log Buffer

The redo log buffer is a shared memory area holding redo records before they are written to redo log files. When a transaction modifies data, InnoDB generates the redo information needed for recovery. The redo log buffer batches log records in memory before writing them out according to InnoDB's logging mechanism.

Configuration variable:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_log_buffer_size';
~~~

The redo log buffer is not the buffer pool. The buffer pool holds data and index pages; the redo log buffer holds log information required to recover changes. Increasing the redo log buffer can help when large transactions generate substantial redo before flushing, but over-allocating it does not automatically make all transactions faster.

### 2.3. Metadata Caches and Table Management Structures

MySQL and InnoDB retain various structural metadata in memory to avoid repeatedly reading and re-parsing definitions. Examples include:

- The table definition cache stores loaded table definitions.
- The table open cache holds open table objects for reuse.
- The InnoDB data dictionary and internal structures hold information about schemas, tables, columns, indexes, and tablespaces.

Related variables:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'table_open_cache';
SHOW GLOBAL VARIABLES LIKE 'table_definition_cache';
~~~

These variables set cache limits or capacity targets; do not assume MySQL immediately reserves all bytes corresponding to the configured numbers. Actual cache usage grows with the number of accessed objects and how the server manages them.

### 2.4. Index Buffers of Other Storage Engines

If the server still uses MyISAM, `key_buffer_size` controls the memory region caching MyISAM index blocks. This is not InnoDB's index cache. InnoDB stores both data pages and index pages inside the buffer pool.

Therefore, do not raise `key_buffer_size` to improve queries on InnoDB tables. Before tuning, verify the storage engine of the tables generating load.

### 2.5. Performance Schema and Internal Memory

Performance Schema uses memory to collect data on activity, events, statements, waits, and memory instruments. It provides server observability but carries its own memory footprint. The broader the enabled instruments and consumers, the more memory observability data may consume.

Not all `mysqld` memory is tracked by Performance Schema. Memory instrumentation output reflects only instrumented allocations currently being tracked. Comparing against the process RSS or OS-reported RAM may show discrepancies due to allocators, libraries, plugins, uninstrumented structures, and memory mappings.

## 3. Per-Connection Memory

When a client connects, MySQL creates a session context to track account, privileges, default database, session variables, transaction state, prepared statements, and state needed to handle requests. In the common one-thread-per-connection model, one thread serves one connection for the duration of the session.

### 3.1. Thread Stack and Session Context

Each thread requires its own stack and management structures. The `thread_stack` variable controls the stack size of connection-handling threads. Beyond the stack, MySQL maintains internal objects storing session state, authentication info, transactions, active statements, and associated resources.

The thread cache reuses threads after a connection closes. It reduces thread creation cost for subsequent connections; it is not shared memory for query contents and does not mean every cached thread has been completely freed from memory.

If a thread pool is deployed, the relationship between connection count and worker thread count differs from one thread per connection. Consequently, you cannot simply multiply connection count by `thread_stack` and treat that as total connection memory.

### 3.2. Network Buffers

MySQL needs buffers to receive and send data over connections. The `net_buffer_length` variable sets the initial size of the communication buffer; the buffer can grow when a statement or packet requires more space, up to the corresponding `max_allowed_packet` limit.

`max_allowed_packet` caps the packet or payload size accepted by client/server in certain operations. It does not mean every connection immediately allocates a RAM block equal to that full value.

Inspect configuration:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'net_buffer_length';
SHOW GLOBAL VARIABLES LIKE 'max_allowed_packet';
~~~

If an application sends large BLOBs, JSON payloads, or large batches, check packet limits on both client and server. Increasing `max_allowed_packet` only raises the size limit; it does not replace controlling payload size and memory usage when handling large data.

### 3.3. Session Variables and Transaction State

MySQL has variables with `GLOBAL`, `SESSION`, or both scopes. `SESSION` variables apply to the current connection. `GLOBAL` variables typically set defaults for new connections for session-scoped variables; changing a global value does not necessarily alter the session value of already open connections immediately.

You can inspect both scopes explicitly:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'sort_buffer_size';
SHOW SESSION VARIABLES LIKE 'sort_buffer_size';
~~~

When testing an adjustment for a single test connection:

~~~sql
SET SESSION sort_buffer_size = 524288;
~~~

Do not increase session variables globally just to speed up a single query. Each session can have its own value, and large settings can cause total RAM usage to surge when many concurrent queries allocate their corresponding work areas.

## 4. Query Execution Work Areas

Work areas are memory regions MySQL allocates to complete a specific operation. They generally appear only when a query needs sorting, joining, scanning, or internal temporary tables. This is the memory group most prone to sudden RAM spikes when many heavy queries run concurrently.

### 4.1. Sort Buffer

`sort_buffer_size` sets the buffer size used for sorting operations by a thread. When a query needs `ORDER BY` or another operation requiring a sort that cannot be satisfied directly by an index, MySQL may allocate a sort buffer.

Example:

~~~sql
SELECT order_id, created_at, total
FROM orders
WHERE status = 'PENDING'
ORDER BY created_at DESC;
~~~

If no index satisfies the required filter and ordering, the execution plan may require a sort. You can inspect the plan with `EXPLAIN`; in MySQL 8.0.18 and later, `EXPLAIN ANALYZE` shows actual execution metrics for a `SELECT` statement.

Inspect values:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'sort_buffer_size';
SHOW SESSION VARIABLES LIKE 'sort_buffer_size';
~~~

Do not immediately increase `sort_buffer_size` whenever a query shows filesort. First inspect indexes, row counts being sorted, sort columns, and query shape. A larger sort buffer can help some sorts, but if many connections sort simultaneously, allocated RAM can climb rapidly.

### 4.2. Join Buffer

`join_buffer_size` is used in certain joins when MySQL cannot use an appropriate index to look up rows in the joined table. A join buffer may be allocated for each join operation that needs it; a query with multiple unindexed joins can require multiple buffer allocations.

Example:

~~~sql
SELECT o.order_id, c.full_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PENDING';
~~~

In this example, the primary key on `customers` and an index on `orders.customer_id` can support access. If the JOIN condition or filter lacks a matching index, the optimizer may pick a more expensive join strategy that uses a join buffer.

Inspect configuration:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'join_buffer_size';
SHOW SESSION VARIABLES LIKE 'join_buffer_size';
~~~

The preferred solution is designing indexes that match JOIN and filter conditions while reviewing access order in the execution plan. Raising `join_buffer_size` should only be considered after understanding the join type, data volume, and query concurrency.

### 4.3. Read Buffer and Read-Rnd Buffer

Two commonly encountered variables:

- `read_buffer_size` assists sequential reads during certain table or index scans.
- `read_rnd_buffer_size` assists reading rows in sorted order after a sort in certain execution plans.

They are work areas tied to read operations, not shared caches across all connections. Raising them can increase memory usage when multiple sessions perform those operations concurrently.

~~~sql
SHOW GLOBAL VARIABLES LIKE 'read_buffer_size';
SHOW GLOBAL VARIABLES LIKE 'read_rnd_buffer_size';
~~~

If a query scans large volumes of data, examine filter predicates, indexes, partitions, and returned row counts before tuning buffers. Reading unnecessary rows still consumes I/O and CPU even with larger buffers.

### 4.4. Internal Temporary Tables

MySQL can create internal temporary tables when a query needs to store intermediate results, such as in certain `GROUP BY`, `DISTINCT`, `UNION`, or complex result-processing cases. Temporary tables may stay in memory or spill to on-disk storage when exceeding limits or when incompatible with the in-memory temporary engine.

Commonly involved variables include:

| Variable | Meaning |
|---|---|
| `tmp_table_size` | Size limit for internal in-memory temporary tables in versions where this applies to TempTable |
| `max_heap_table_size` | Size limit for `MEMORY` tables; for some `MEMORY` temporary tables, the effective limit is the smaller of this variable and `tmp_table_size` |
| `temptable_max_ram` | Overall RAM threshold the TempTable engine may use before switching to another mechanism |
| `temptable_max_mmap` | Limit on memory-mapped file space TempTable may use before falling back to InnoDB |

Exact details depend on the version. Starting in MySQL 8.0, TempTable is the default engine for many internal temporary tables; starting in MySQL 8.0.28, `tmp_table_size` enforces a per-table limit on internal in-memory temporary tables using TempTable. Tables exceeding limits can spill to InnoDB. For `MEMORY` tables, limits involving `tmp_table_size` and `max_heap_table_size` still apply.

On-disk temporary tables do not mean MySQL is malfunctioning. They can be normal behavior when queries process large datasets. However, an unusually high rate of on-disk temporary tables can signal queries, data structures, or memory limits that warrant review.

Inspect configuration and statistics:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'tmp_table_size';
SHOW GLOBAL VARIABLES LIKE 'max_heap_table_size';
SHOW GLOBAL VARIABLES LIKE 'temptable_max_ram';
SHOW GLOBAL VARIABLES LIKE 'temptable_max_mmap';

SHOW GLOBAL STATUS LIKE 'Created_tmp_tables';
SHOW GLOBAL STATUS LIKE 'Created_tmp_disk_tables';
~~~

Both `Created_tmp_tables` and `Created_tmp_disk_tables` are cumulative counters since server startup or the last appropriate status reset. To evaluate trends, measure deltas over a time window and compare against query volume rather than looking at a single absolute number.

## 5. Which Memory Areas Does a Query Use?

Consider a query with filtering, JOIN, and sorting:

~~~sql
SELECT c.customer_id, c.full_name, o.order_id, o.created_at
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PENDING'
ORDER BY o.created_at DESC
LIMIT 100;
~~~

Conceptual path:

1. The connection already has a session context and network buffer.
2. MySQL parses the SQL, checks privileges, and builds an execution plan.
3. InnoDB reads required pages from the buffer pool; if not yet in RAM, the engine loads them from tablespaces.
4. If the JOIN requires a strategy without a matching index, the executor may use a join buffer.
5. If result ordering cannot be read directly from an index, the executor may need a sort buffer.
6. If the query must store intermediate results, MySQL may create an internal temporary table.
7. Results are transmitted to the client through the network buffer.

Not every query uses all of the memory areas above. The optimizer may pick a different plan; a suitable index may eliminate sorting or reduce joined rows. Work areas can also be allocated on demand and do not necessarily coexist at maximum size throughout the entire session.

## 6. Why Does Connection Count Affect RAM?

Every connection carries baseline memory overhead. When a query starts, it may require additional work areas. Thus, two servers with the exact same connection count can consume vastly different amounts of RAM:

- Host A has many idle connections and few active queries.
- Host B has the same connection count, but many concurrent queries sorting, joining, and creating temporary tables.

Host B can consume significantly more RAM because work areas scale with active query execution. You cannot simply multiply a fixed number like `sort_buffer_size` by `max_connections` to forecast usage accurately; each buffer has different allocation conditions, lifetimes, and invocation counts.

A mental estimation model:

~~~text
MySQL RAM at a point in time
  ≈ shared memory
  + total baseline memory of existing connections
  + total work areas of currently active queries
  + plugins, allocators, and other internal structures
~~~

This is a directional model, not an exact measurement formula. Some regions are shared, some are reused, and some are not instrumented by Performance Schema; the OS also needs RAM for page cache, filesystem, monitoring agents, and other services.

### 6.1. max_connections Is Not Preallocated Memory

`max_connections` caps the number of concurrent client connections allowed. It does not mean MySQL preallocates the maximum possible memory for every connection at startup.

However, raising `max_connections` increases the connection load the server can accept. When many concurrent connections execute heavy queries, RAM demand can exceed expectations. Without sufficient RAM, the OS may swap, the `mysqld` process may be terminated by the OOM killer, or the host may become severely slow.

~~~sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Max_used_connections';
~~~

`Max_used_connections` shows the peak number of simultaneous connections used since server startup or status reset. Use actual metrics alongside query load to set limits, rather than increasing `max_connections` just to mask connection pool bugs or unclosed connections.

### 6.2. Connection Pools Help Control Load

A connection pool reuses a bounded number of connections. It avoids repeatedly creating and tearing down connections while capping how many queries can concurrently hit the database from one application.

Pools do not eliminate per-connection memory cost. An oversized pool still holds many sessions, and multiple pools across many application instances can add up to a very large connection count. Size pools based on total instance count, server capacity, query duration, and concurrency needs.

When an application does not need to keep a transaction open, commit or roll back early and return the connection to the pool. Long-lived transactions hold state and may retain locks, read views, or related resources longer than necessary.

## 7. Observing Memory with Performance Schema

MySQL 8.x provides memory instrumentation through Performance Schema. Aggregation tables can be queried to view current and high-water-mark allocations per event.

### 7.1. Viewing Server-Wide Allocations

~~~sql
SELECT
    event_name,
    current_number_of_bytes_used,
    high_number_of_bytes_used
FROM performance_schema.memory_summary_global_by_event_name
ORDER BY current_number_of_bytes_used DESC
LIMIT 20;
~~~

Results help identify which instrumented memory event groups currently use the most memory. Event names may change across versions, and some events may not be enabled for collection.

### 7.2. Viewing Memory by Thread

~~~sql
SELECT
    t.processlist_id,
    t.processlist_user,
    SUM(m.current_number_of_bytes_used) AS current_bytes
FROM performance_schema.memory_summary_by_thread_by_event_name AS m
JOIN performance_schema.threads AS t
  ON t.thread_id = m.thread_id
WHERE t.type = 'FOREGROUND'
GROUP BY t.thread_id, t.processlist_id, t.processlist_user
ORDER BY current_bytes DESC
LIMIT 20;
~~~

This query aggregates instrumented allocations by foreground thread. `processlist_id` can be correlated with the client connection ID. InnoDB background threads or administrative threads may not appear in the foreground list.

### 7.3. Using the sys Schema for an Overview

If the `sys` schema is installed and the corresponding memory instruments are active, views like these make results easier to read:

~~~sql
SELECT * FROM sys.memory_global_total;

SELECT *
FROM sys.memory_by_thread_by_current_bytes
LIMIT 20;
~~~

`sys` views are a presentation layer over Performance Schema data. Privileges, version, and instrument status can affect results.

### 7.4. When Data Is Incomplete

If results are empty or far lower than `mysqld`'s RSS:

1. Check whether Performance Schema is enabled.
2. Check whether required memory instruments are enabled in `performance_schema.setup_instruments`.
3. Identify which allocations are uninstrumented.
4. Compare with metrics from the OS, container runtime, or monitoring systems.
5. Observe trends over time instead of drawing conclusions from a single snapshot.

Do not enable all instruments in a high-load environment without evaluating observability overhead. Enable only the groups needed for investigation and disable or narrow them afterward if operational policy requires.

## 8. How to Read and Tune Memory Variables

When adjusting configuration, know which scope a variable belongs to and what a change impacts:

| Variable | Primary usage scope | What to examine |
|---|---|---|
| `innodb_buffer_pool_size` | Global, InnoDB | Fit with working set and host RAM |
| `innodb_log_buffer_size` | Global, InnoDB | Transactions generating large amounts of redo |
| `thread_stack` | Connection-handling thread | Stack needs and thread configuration |
| `net_buffer_length` | Connection communication buffer | Typical message exchange sizes |
| `max_allowed_packet` | Packet/data size limit | Large payloads, BLOBs, or batches |
| `sort_buffer_size` | Work area for sorts | Actual sorting and concurrency |
| `join_buffer_size` | Work area for certain joins | Joins lacking suitable indexes |
| `read_buffer_size` | Sequential read area | Sequential data scans |
| `read_rnd_buffer_size` | Post-sort ordered read area | Reading rows after a sort operation |
| `tmp_table_size` | Internal temporary table / `MEMORY` depending on version | In-memory temporary table sizes |
| `temptable_max_ram` | Global, TempTable engine | Total RAM TempTable may use |
| `temptable_max_mmap` | Global, TempTable engine | Limit on memory-mapped temporary data |

### 8.1. Checking Before Making Changes

Record current values and identify scopes:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_buffer_pool_size';
SHOW GLOBAL VARIABLES LIKE 'sort_buffer_size';
SHOW SESSION VARIABLES LIKE 'sort_buffer_size';
SHOW GLOBAL VARIABLES LIKE 'join_buffer_size';
SHOW GLOBAL VARIABLES LIKE 'tmp_table_size';
~~~

Some variables can be changed dynamically, while others require a restart or take effect only for new connections. Check documentation for the exact version before making changes. When altering a `GLOBAL` variable that has a `SESSION` counterpart, existing sessions may retain their own values.

### 8.2. Evidence-Based Tuning

A safe workflow:

1. Identify the symptom: RAM exhaustion, swapping, OOM, slow sorts, slow joins, or increasing on-disk temporary tables.
2. Gather metrics from Performance Schema, status variables, slow query log, and the OS.
3. Locate queries or workload types causing large allocations.
4. Inspect execution plans, indexes, filter predicates, and intermediate data volumes.
5. Test small changes in a staging environment or on a controlled session.
6. Re-measure query latency, throughput, RAM, swap, and on-disk temporary table counts.
7. Roll out broadly only when measurements prove benefit and peak RAM usage remains within safe bounds.

For example, if an `ORDER BY` query creates a large sort, check whether an index can satisfy both the filter predicates and sort order. If a `JOIN` needs a large join buffer, check indexes on JOIN columns. If temporary tables spill to disk, inspect intermediate row counts and how `GROUP BY` or `DISTINCT` is written before raising memory limits.

## 9. Common Mistakes

**"Every buffer variable is fully allocated for every connection as soon as it opens."** Incorrect. Many work areas are allocated only when a query needs them; exact allocation and reuse depend on each component.

**"Total RAM equals buffer pool plus `max_connections` times the sum of all buffer variables."** This is an overly crude estimate. Variables have different scopes and allocation rules; some buffers are allocated per sort or join operation, some regions are shared, and some limits are caps rather than allocated RAM.

**"Increasing `sort_buffer_size` and `join_buffer_size` always makes queries faster."** Incorrect. If the bottleneck lies in indexes, intermediate row counts, or the execution plan, larger buffers may only increase RAM usage without reducing actual work.

**"`max_allowed_packet` is RAM pre-reserved for every connection."** Incorrect. It is a packet or data size limit; communication buffers grow as needed.

**"The buffer pool is per-connection memory."** Incorrect. The InnoDB buffer pool is shared memory across InnoDB connections.

**"Performance Schema shows the entire process's RAM."** Incorrect. It reports instrumented allocations; always cross-reference with the OS and monitoring tools.

**"Raising `max_connections` fixes all connection errors."** Incorrect. If the application fails to return connections to the pool or holds long transactions, raising the limit can worsen memory pressure and lock contention.

## 10. Memory Assessment Workflow for a MySQL System

When deploying or operating a relational database, evaluate in order:

1. Determine available RAM, container limits, and co-located processes sharing the machine.
2. Measure actual `mysqld` memory usage and OS swap/OOM status.
3. Review global regions, especially the InnoDB buffer pool, redo log buffer, and metadata caches.
4. Check current connection counts, peak connections, thread model, and connection pool configurations.
5. Identify active queries with large sorts, joins, scans, or internal temporary tables.
6. Use Performance Schema and the `sys` schema to analyze instrumented allocations.
7. Tune indexes and queries before broadly raising work area buffers.
8. Set connection limits and pool sizes according to real concurrency, reserving RAM for the OS and uninstrumented memory.
9. Monitor after changes under representative workloads including peak traffic periods.

What needs optimizing is the system as a whole: queries finish within acceptable latency, the server does not swap, RAM has headroom for load spikes, and connections do not spawn work areas exceeding host capacity.

## Conclusion

MySQL uses memory across multiple scopes. Shared memory such as the InnoDB buffer pool and redo log buffer serves multiple connections; per-connection memory holds threads, network buffers, and session state; work areas such as sort buffers, join buffers, read buffers, and temporary tables are allocated on demand during execution.

Connection count and query complexity jointly drive RAM pressure. Therefore, distinguish configuration limits from actual allocated memory, monitor both global and per-thread usage, and examine queries and indexes before increasing buffers. A well-tuned configuration balances the working set, concurrency, work areas, RAM limits, and OS requirements.
