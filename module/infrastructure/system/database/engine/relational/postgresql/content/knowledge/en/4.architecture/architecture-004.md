# Shared Buffers, Session Private Memory, and OS Memory in PostgreSQL

When an application executes a `SELECT` statement, data is not always read from physical disk. The data page may already reside in PostgreSQL's **shared buffers**; if not, the operating system may still hold it in the **OS page cache**. Meanwhile, the backend process executing the query needs private memory to sort, join, and aggregate data. When demand exceeds an operation's memory budget, PostgreSQL can spill to **temporary files** on storage.

These three layers must be kept distinct. Increasing `shared_buffers` does not directly give more memory to `SORT`; increasing `work_mem` does not create a larger shared cache; and `effective_cache_size`, despite having "cache" in its name, only provides an **estimate for the planner** and allocates zero RAM. A configuration that runs a single report quickly can cause out-of-memory failures when hundreds of connections execute concurrent sorts and hashes.

This lesson belongs to the **PostgreSQL Architecture** chapter. The goal is to trace a data page through the cache layers, understand a backend process's memory layout, budget RAM safely, and use observability tools to tell whether a bottleneck lies in caching, query working memory, or I/O.

## 1. PostgreSQL Memory Map

Traditional PostgreSQL organizes the server into a main supervisor process and **backend processes** serving connections, alongside background processes such as the checkpointer, background writer, WAL writer, autovacuum workers, and others depending on configuration.

At a conceptual level:

~~~text
                  PostgreSQL host or container
+----------------------------------------------------------------+
|                              RAM                               |
|                                                                |
| +------------------------------+ +----------------------------+ |
| | PostgreSQL shared memory     | | Process private memory     | |
| |                              | |                            | |
| | shared_buffers               | | Backend A: sort, hash      | |
| | - heap/table pages           | | Backend B: aggregate       | |
| | - index pages                | | Backend C: session state   | |
| |                              | | Autovacuum / maintenance   | |
| | WAL buffers, locks, metadata | | Background processes       | |
| +------------------------------+ +----------------------------+ |
|                                                                |
| +------------------------------------------------------------+ |
| | Operating system: filesystem page cache, kernel memory...  | |
| +------------------------------------------------------------+ |
+----------------------------------------------------------------+
                               |
                               v
+----------------------------------------------------------------+
| Data files, index files, WAL, temporary files, tablespaces     |
+----------------------------------------------------------------+
~~~

This is a **logical diagram**, not strictly separated RAM boxes in how the operating system accounts for memory. Shared memory is mapped into multiple processes, and OS process-accounting tools may double-count shared pages.

| Layer | Who manages it? | What is it for? | Related parameters |
|---|---|---|---|
| **Shared buffers** | PostgreSQL | Shared cache for data and index pages | `shared_buffers` |
| **Backend private memory** | PostgreSQL and per-process allocator | Query execution, sort, hash, session state, temp tables | `work_mem`, `temp_buffers` |
| **OS page cache** | Kernel / operating system | File page caching, reducing physical disk reads | No single simple GUC that allocates it directly |
| **WAL buffers** | PostgreSQL shared memory | Buffering WAL records | `wal_buffers` |
| **Maintenance memory** | Process performing maintenance | VACUUM, CREATE INDEX... | `maintenance_work_mem`, `autovacuum_work_mem` |
| **Dynamic shared memory** | PostgreSQL | Data-exchange structures among parallel workers | Depends on parallel plan, not a single parameter |

A single query can touch multiple layers simultaneously. You cannot compute total required RAM from `shared_buffers + work_mem` alone.

## 2. What Are Shared Buffers?

**Shared buffers** form the relation page buffer pool in **shared memory**, shared across all backends of the same PostgreSQL instance.

Suppose PostgreSQL needs a B-tree page to look up an order:

~~~text
Backend needs to read index page
             |
             v
    Look up shared buffers
         /          \
       HIT          MISS
        |             |
        v             v
  Page present   Read via OS/file
        |             |
        |        Load into buffer
        +------+------+
               |
               v
           Use data
~~~

On a **hit**, the backend accesses the page directly in shared buffers. On a **miss**, PostgreSQL loads the page through the I/O layer. However, **a miss in shared buffers does not automatically mean a physical disk read**: the operating system may already have that file page in its cache.

Shared buffers are not a cache of **SQL query results**. They primarily hold **data pages** such as heap pages and index pages. Two completely different SQL queries can hit the same buffered pages when accessing the same relation.

### 2.1. Page size

PostgreSQL is typically compiled with a default **8 KiB** block/page size. Check your instance's build:

~~~sql
SHOW block_size;
~~~

With an 8 KiB page size and `shared_buffers = 128MB`, the intuitive buffer page count is:

~~~text
128 MiB / 8 KiB = 16,384 pages
~~~

This approximates the cached page slots; PostgreSQL also uses memory for buffer descriptors, locks, and management structures. Do not equate `shared_buffers` with the server's total shared memory allocation.

### 2.2. Objects cached in shared buffers

Shared buffers can hold pages from:

- Regular heap tables.
- Indexes such as B-tree, GIN, and other index types.
- Certain relation forks and internal engine metadata pages.

When a backend modifies data, buffered pages can be marked **dirty**. A dirty page does not necessarily flush immediately to data files upon transaction commit.

By contrast, **temporary tables** use per-session **local buffers / `temp_buffers`**; temporary files generated by sort/hash spills are also not regular relation pages kept in shared buffers.

### 2.3. Shared buffers are shared instance-wide

A single PostgreSQL instance can host multiple databases and connections. `shared_buffers` is shared across the whole instance, not:

- 4 GiB per database when configured to 4 GiB.
- 4 GiB per connection.
- Private per role or per schema.

Because it is shared, backend B can benefit from pages backend A already loaded into cache if both access the same pages. Conversely, other workloads can evict hot pages through replacement pressure.

## 3. Path of a SELECT Statement

Example:

~~~sql
SELECT order_id, customer_id, amount
FROM shop.orders
WHERE order_id = 1001;
~~~

Assuming a primary key on `order_id`, the optimizer may pick an index scan. At a high level, the backend performs:

1. Parsing and permission checks for the SQL statement.
2. Planning or selecting an appropriate plan.
3. Reading relevant index pages.
4. Reading required heap pages if the plan needs columns from the heap.
5. Checking tuple visibility under MVCC.
6. Returning results to the application.

When reading heap/index pages, the cache path can be:

~~~text
               PostgreSQL Backend
                       |
                       v
               Shared buffers
                 /          \
                / HIT        \ MISS
               v              v
          Return page     Read request
                                 |
                                 v
                          OS page cache
                           /       \
                         HIT       MISS
                          |          |
                          |      SSD/HDD/storage
                          |          |
                          +-----+----+
                                |
                                v
                      Load into shared buffers
~~~

Thus there are **two distinct hit levels**. Shared-buffer hit counters do not measure OS page cache hits.

### 3.1. Hot working set

The **working set** is the set of data and index pages frequently accessed over a period. A 500 GiB table does not necessarily require 500 GiB of RAM: if queries frequently touch only 2 GiB of hot data, a much smaller cache can still perform well.

Conversely, if many queries perform random reads across a massive working set, cache miss pressure can remain high even after increasing `shared_buffers`.

Distinguish clearly:

- **Table size:** how much data sits on disk.
- **Working set size:** how many pages are accessed frequently.
- **Cache capacity:** how many pages fit in memory.
- **Query selectivity:** how many pages must be examined to produce the result.

Never estimate RAM needs solely from total database size on disk.

### 3.2. Page replacement is not a simple LRU

PostgreSQL manages buffers based on usage counts, commonly described via a **clock-sweep** algorithm and **buffer access strategies**. It does not simply use a single global LRU queue for every operation.

Large sequential reads can use ring-buffer access strategies to avoid wiping out the entire shared cache. Therefore, do not assume a single sequential scan automatically flushes out every hot page.

## 4. Write Path: Dirty Buffers, WAL, and Checkpoints

An `UPDATE` modifies records in PostgreSQL-managed pages. Modified pages in shared buffers become **dirty**.

~~~text
UPDATE orders
      |
      v
 Modify page in shared buffers
      |
      +----> Generate required WAL records
      |
      v
 Dirty page
      |
      +----> May be written by background writer
      |
      +----> May be written by backend / checkpointer
      |
      v
 Data files updated per server mechanisms
~~~

### 4.1. Why does COMMIT not mean every heap page is written immediately?

PostgreSQL uses **WAL — Write-Ahead Logging**. To guarantee recovery/durability per configuration, WAL records must be durably written in the proper order before modified data pages are considered durably persisted.

Consequently, a transaction can `COMMIT` successfully while modified heap/index pages still reside in shared buffers and are written to data files later. If the server crashes, PostgreSQL replays WAL to recover consistent state.

**WAL does not replace backups.** An accidental committed `DELETE` is recorded in WAL and replicated to standbys. You still need independent backups and restore procedures.

### 4.2. WAL buffers differ from shared buffers

| Area | What it holds | Role |
|---|---|---|
| `shared_buffers` | Data and index pages | Caching and handling data reads/writes |
| `wal_buffers` | Buffered WAL records | Supports logging and crash recovery |
| OS page cache | File pages cached by kernel | Can reduce physical storage reads |

Do not add WAL buffer pages to data buffer pages as if they stored the same kind of objects.

### 4.3. Background writer, checkpointer, and backend writes

- **Background writer** proactively writes some dirty buffers to make clean buffers reusable.
- **Checkpointer** performs work needed for checkpoints and recovery bounds.
- **Backends** may also write pages themselves when necessary.
- **WAL writer** participates in writing WAL data according to PostgreSQL mechanics.

Write latency is shaped by workload, WAL, storage I/O, background processes, and caching. Increasing `shared_buffers` can shift write and checkpoint patterns, but does not automatically fix every write latency issue.

## 5. Configuring shared_buffers

Check the current setting:

~~~sql
SHOW shared_buffers;
~~~

Or query configuration metadata:

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name = 'shared_buffers';
~~~

`shared_buffers` is configured at the server level and typically requires a **PostgreSQL restart** to take effect. You cannot resize the instance-wide shared cache with `SET shared_buffers` inside an ordinary session.

### 5.1. Choosing a starting size

On a dedicated PostgreSQL machine, a commonly cited starting point is **around 25% of RAM** for `shared_buffers`, followed by measurement and tuning. This is not an optimal formula for every workload.

Example on a 32 GiB RAM host:

~~~text
Reference starting point:
  shared_buffers ~= 8 GiB

Remaining RAM is still needed for:
  - Backend processes and query execution
  - Sorts, hashes, aggregates
  - Autovacuum and maintenance
  - WAL / other shared memory
  - OS page cache
  - Kernel, monitoring agents, other services
~~~

If PostgreSQL runs inside a container with an 8 GiB memory limit on a 64 GiB host, budget against the **container limit**, not total host RAM.

### 5.2. Why not set shared_buffers to 90% of RAM?

When `shared_buffers` consumes too much RAM:

1. OS page cache loses headroom.
2. Private query working memory faces tighter contention.
3. Autovacuum, maintenance, parallel workers, and background processes can be starved.
4. If the bottleneck is CPU, locks, or scanning unnecessary data, adding cache will not cure it.
5. Memory pressure or OOM kills can occur during peak load.

Sensible configuration balances **all RAM consumers**, rather than maximizing one parameter.

## 6. Backend Process Private Memory

In the traditional model, each client connection has a backend process. Each backend allocates private memory for:

- SQL parsing, planning, and execution.
- Transaction and session state.
- Structures for sorts, hash joins, hash aggregates, and other operators.
- Temporary table buffers when used.
- Internal memory contexts.
- Structures belonging to enabled extensions or features.

~~~text
Backend A: e-commerce app
   session state
   executor
   small sort / hash

Backend B: analytical reporting
   session state
   large sorts / hashes

Backend C: idle connection
   baseline process/session memory

Shared buffers:
   one shared cache pool for A, B, C
~~~

**Each backend does not get its own copy of shared_buffers.** Nevertheless, many backends still impose substantial RAM pressure due to per-process baseline overhead and working memory.

### 6.1. Idle connections do not automatically allocate full work_mem

An `idle` backend still consumes baseline process/session memory. However, it is **not pre-allocated a full `work_mem`** merely for being connected.

Conversely, an active backend running a complex query can allocate multiple multiples of `work_mem` because a query may contain multiple memory-using nodes.

### 6.2. Memory contexts

PostgreSQL uses **memory contexts** to manage allocation lifetimes inside a backend.

Example:

~~~text
Backend process
  |
  +-- Session-level contexts
  |     |
  |     +-- Query/Executor contexts
  |     |      +-- Tuples, expression state
  |     |      +-- Sort/Hash allocations
  |     |
  |     +-- Transaction contexts
  |
  +-- Other internal contexts
~~~

When a query or transaction completes, associated contexts can be freed or reset per their lifecycle. However, **OS-reported RSS** does not necessarily drop byte-for-byte immediately due to allocator and virtual memory page management.

## 7. work_mem: Per-Operation Memory, Not a Whole-Session Budget

`work_mem` sets the base memory budget for **each processing operation** such as a sort or hash table before PostgreSQL must switch strategies, including spilling to temporary disk files for eligible algorithms.

~~~sql
SHOW work_mem;
~~~

False statements to avoid:

- "`work_mem` is the maximum RAM for all of PostgreSQL."
- "Each connection uses at most one `work_mem`."
- "Opening a connection allocates `work_mem` immediately."
- "Increasing `work_mem` enlarges shared buffers."

### 7.1. One query can have multiple memory-consuming nodes

Example:

~~~sql
SELECT
    c.region,
    COUNT(*) AS order_count,
    SUM(o.amount) AS revenue
FROM shop.orders AS o
JOIN shop.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
GROUP BY c.region
ORDER BY revenue DESC;
~~~

Depending on the plan, PostgreSQL may use a hash join, a hash aggregate, and a sort:

~~~text
Sort (ORDER BY revenue)           -> memory area 1
        |
HashAggregate (GROUP BY)          -> memory area 2
        |
Hash Join                         -> memory area 3
        |
  Scan orders + customers
~~~

Several of these areas can hold memory simultaneously during execution. Thus a query's total RAM demand can exceed a single `work_mem`.

### 7.2. hash_mem_multiplier

PostgreSQL provides the parameter:

~~~sql
SHOW hash_mem_multiplier;
~~~

Hash-based operations may be permitted a memory budget calculated as `work_mem * hash_mem_multiplier`, subject to version rules and operator type.

Illustrative example:

~~~text
work_mem = 64 MiB
hash_mem_multiplier = 2

A hash operation may receive a higher budget,
around 128 MiB, under applicable rules.
~~~

That **does not mean every hash always allocates 128 MiB**. Nor does it cap the entire query at 128 MiB, since a query can have multiple nodes and parallel workers.

### 7.3. Parallel workers expand the calculation

A parallel query plan can involve a leader plus multiple workers. Many plan steps consume memory within each worker, while other structures use dynamic shared memory.

~~~sql
SHOW max_parallel_workers_per_gather;
~~~

Do not apply one fixed multiplier blindly across all queries because different plan nodes behave differently. When budgeting memory, always account for **parallelism and concurrent queries**.

### 7.4. When a sort does not fit in RAM

~~~text
ORDER BY over many rows
          |
          v
  Sort memory enough?
      /       \
    Yes        No
     |           |
     v           v
 In-memory    External sort
   sort      and temp files
      \         /
       \       /
        v     v
     Return results
~~~

Sorting that spills to disk introduces I/O and slows queries. Raising `work_mem` can help, yet raising it server-wide easily causes trouble if dozens of concurrent queries each run multiple sort/hash nodes.

## 8. temp_buffers for Temporary Tables

`temp_buffers` sets the **per-session** buffer limit for pages of **temporary tables**.

~~~sql
CREATE TEMP TABLE recent_order_ids (
    order_id BIGINT PRIMARY KEY
);

INSERT INTO recent_order_ids
VALUES (101), (102), (103);

SELECT *
FROM recent_order_ids;
~~~

~~~sql
SHOW temp_buffers;
~~~

Key points:

- Temporary table buffers are **local buffers**, separate from the shared buffers mechanism used for regular tables.
- Memory is allocated on demand; opening a connection does not pre-allocate the full `temp_buffers` amount.
- Changing `temp_buffers` inside a session has timing constraints: set it before the session's first access to any temporary table.
- Temporary tables can still spill to disk storage when needed; not every temp table fits entirely in RAM.

### 8.1. Do not confuse temp_buffers with ORDER BY temporary files

| Workload | Relevant memory / storage mechanism |
|---|---|
| Temporary table | Local temp buffers and temp relation storage |
| Sort/Hash spill | `work_mem`, hash multiplier, temporary files |
| Regular table cache | `shared_buffers` |
| OS file cache | OS page cache |

If a query shows `Sort Method: external merge`, raising `temp_buffers` is not the direct fix. Inspect `work_mem`, the query plan, and how many rows are being sorted first.

### 8.2. temp_file_limit

~~~sql
SHOW temp_file_limit;
~~~

`temp_file_limit` caps the disk space certain types of temporary files may consume per process, preventing runaway queries from filling storage. It is **not a RAM limit** and does not apply identically to all forms of temporary relation storage.

Setting it too low can cancel legitimate queries; setting it too high or unlimited risks running out of disk space without I/O and capacity controls.

## 9. maintenance_work_mem and autovacuum_work_mem

Maintenance tasks also consume memory:

~~~sql
SHOW maintenance_work_mem;
SHOW autovacuum_work_mem;
~~~

**`maintenance_work_mem`** sets the memory budget for eligible maintenance operations such as `VACUUM` or `CREATE INDEX` per applicable rules.

**`autovacuum_work_mem`** governs memory for autovacuum workers; a value of `-1` normally inherits `maintenance_work_mem`.

~~~text
Autovacuum worker A -> maintenance memory
Autovacuum worker B -> maintenance memory
SQL Report X        -> sort/hash
SQL Report Y        -> sort/hash
Shared buffers      -> shared pool
OS page cache       -> OS-reclaimable memory
~~~

Total resource usage must fit available RAM. If multiple autovacuum workers run concurrently, memory demand scales across active workers and their tasks.

Do not assume every `CREATE INDEX` or every parallel maintenance worker strictly uses exactly one `maintenance_work_mem`. Details vary by operation and PostgreSQL version.

## 10. What Is the OS Page Cache?

When PostgreSQL reads data files, the operating system can cache file contents in RAM. This is the **OS page cache**, distinct from the shared buffers managed by PostgreSQL.

~~~text
Backend query
    |
    v
Shared buffers ---- HIT ---> Return page
    |
   MISS
    |
    v
OS page cache ----- HIT ---> Return page
    |
   MISS
    |
    v
Storage device
    |
    v
Load data into cache
~~~

With standard filesystem-backed I/O, the same data page can reside in both PostgreSQL's buffer pool and the OS page cache. The two layers have different management policies and goals.

### 10.1. The OS page cache is reclaimable

Operating systems typically use otherwise idle RAM for file caching. When processes request RAM, the kernel can reclaim suitable cache pages.

Hence on Linux, **low "free" RAM does not automatically mean low memory**. Most RAM may sit in reclaimable page cache while `available` memory remains healthy.

However, sustained memory pressure—constant page cache thrashing, rising swap in/out, or OOM kills—degrades performance and stability.

### 10.2. Do not treat OS cache as completely free RAM

Even though OS page cache is reclaimable, it provides real performance value. If increasing `shared_buffers` starves the OS file cache, total physical I/O may **fail to drop** or even worsen.

Always measure PostgreSQL cache stats, available memory, and physical I/O metrics together—not just the shared-buffer hit ratio.

### 10.3. Containers and cgroups

When PostgreSQL runs in a container, resources are typically constrained by cgroups. A 64 GiB host does not allow an 8 GiB-capped container to exceed 8 GiB.

Monitor:

- Actual container memory limit.
- Memory usage and cgroup metrics.
- Swap and OOM-kill events.
- Backend private memory and shared memory.
- File cache charged against the container budget under the host platform.

Evaluate `shared_buffers` against the **workload's available memory limit**, not raw host RAM alone.

## 11. effective_cache_size Does Not Allocate RAM

~~~sql
SHOW effective_cache_size;
~~~

**`effective_cache_size`** gives the **query planner an estimate** of how much total cache is likely available to assist data access. It reflects the combined expectation of shared buffers, OS page cache, and effectively usable memory, but **allocates no memory**.

Example:

~~~text
shared_buffers       = 4 GiB
effective_cache_size = 10 GiB
~~~

You must not conclude PostgreSQL has allocated **14 GiB**. Here, `4 GiB` is the internal buffer cache configuration, while `10 GiB` is an assumption the planner uses when estimating plan costs.

### 11.1. Why does this parameter affect EXPLAIN?

When the planner expects many pages to be cached, it prices index access paths differently than when it expects expensive random disk I/O.

This can shift plan choices between candidate paths, yet raising `effective_cache_size` does not load extra pages into RAM or magically turn a slow query fast.

### 11.2. What value should you set?

Do not apply one rigid formula to every system. Estimate how much cache can serve the workload's data after accounting for backend private memory, maintenance, OS overhead, and co-located services.

Many guidelines start with a substantial share of RAM on dedicated database servers, but the final choice should reflect actual configuration, OS cache, query patterns, and empirical measurements.

## 12. Why Is `RAM = shared_buffers + connections × work_mem` Wrong?

A commonly seen multiplication:

~~~text
Expected RAM = shared_buffers + max_connections * work_mem
~~~

This is **not an accurate formula** because:

1. Not every connection is running a query or allocating `work_mem`.
2. A single query can execute **multiple sort/hash operations**.
3. Hash operations may receive larger budgets via `hash_mem_multiplier`.
4. Parallel workers add per-worker memory and dynamic shared memory.
5. Temporary tables use `temp_buffers` and other resources.
6. Backends always retain private memory contexts/state outside `work_mem`.
7. Autovacuum and maintenance tasks have their own budgets.
8. WAL, locks, and other shared memory structures consume RAM.
9. OS page cache, kernel, and non-PostgreSQL services require RAM.
10. Cgroups can enforce memory limits below physical RAM.

While no single formula fits all, you can model **concurrent workload scenarios** to estimate headroom.

### 12.1. Example 16 GiB RAM host

Suppose:

| Component | Illustrative value |
|---|---|
| Total RAM | 16 GiB |
| shared_buffers | 4 GiB |
| effective_cache_size | 10 GiB — planner assumption only |
| Open backend connections | 100 |
| Concurrent reporting queries | 8 |
| Sort nodes holding RAM concurrently per query | 2 |
| work_mem | 64 MiB |

In an idealized scenario, sorts alone could need:

~~~text
8 queries x 2 sorts x 64 MiB = 1,024 MiB (~1 GiB)
~~~

This figure is **neither actual measured usage nor an upper bound for the whole workload**. Adding hash nodes, parallel workers, or more concurrent memory-holding operators increases demand.

The machine still needs baseline memory for 100 backends, autovacuum, other shared memory, OS cache, and the kernel. **Do not add the 10 GiB `effective_cache_size`**, because it is never allocated.

### 12.2. Concurrency matters more than connection limit

Two systems with `max_connections = 300` can behave completely differently:

- System A: most connections sit idle, with only 10 light queries running at once.
- System B: 100 concurrent analytical queries heavy on hashes, sorts, and parallel workers.

RAM, CPU, and I/O pressure on System B is vastly higher. Measure **active concurrency and query profiles**, rather than inferring load from `max_connections`.

### 12.3. Connection pools

An application-side pool or external proxy bounds actual backend count and lowers the cost of keeping excess sessions open. However, pooling does not fix a memory-hungry query; you must still limit concurrent heavy reports and tune execution plans.

When using transaction pooling, understand its constraints regarding session state, prepared statements, and temporary tables per the pooler's implementation.

## 13. Inspecting Settings Directly via pg_settings

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'shared_buffers',
    'wal_buffers',
    'work_mem',
    'hash_mem_multiplier',
    'temp_buffers',
    'maintenance_work_mem',
    'autovacuum_work_mem',
    'effective_cache_size',
    'max_connections',
    'max_parallel_workers_per_gather',
    'huge_pages'
)
ORDER BY name;
~~~

| Column | How to read it |
|---|---|
| `name` | Setting name |
| `setting` | Raw value reported by PostgreSQL |
| `unit` | Associated unit, if applicable |
| `context` | Scope/timing allowed for changes |
| `source` | Configuration source determining current value |
| `pending_restart` | Whether a pending change requires restart to take effect |

**Do not read `setting = 16384` and assume 16,384 MiB** without checking `unit`. For quick human inspection, `SHOW work_mem;` and `SHOW shared_buffers;` are usually easier to read.

### 13.1. Changing work_mem locally

Inside a test transaction:

~~~sql
BEGIN;

SET LOCAL work_mem = '32MB';

SHOW work_mem;

-- Run the test query here.

ROLLBACK;
~~~

`SET LOCAL` applies only within the current transaction. Once the transaction ends, the local setting does not persist server-wide.

For an individual heavy report that needs more sort memory, raising it locally can be safer than increasing `work_mem` for every backend. Still account for multiple nodes and concurrent executions.

### 13.2. shared_buffers normally requires a restart

Do not try `SET LOCAL shared_buffers` to enlarge the shared cache. It is a server-startup / shared-memory setting. Check `pg_settings.context` and schedule a proper restart and rollback plan when genuinely changing it.

## 14. What Does the Shared-Buffer Hit Ratio Measure?

PostgreSQL provides the `pg_stat_database` statistics view:

~~~sql
SELECT
    datname,
    blks_read,
    blks_hit,
    ROUND(
        100.0 * blks_hit
        / NULLIF(blks_hit + blks_read, 0),
        2
    ) AS shared_buffer_hit_pct,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
~~~

- `blks_hit`: block accesses satisfied from the shared buffer cache within the tracked scope.
- `blks_read`: block accesses requiring reads through the tracked relation read path.
- This ratio is a **shared-buffers cache hit metric**, not the fraction of PostgreSQL operations that "avoided SSD reads."

### 14.1. Why does a 99% hit ratio not guarantee a fast system?

- Queries may spend heavy CPU filtering or computing expressions.
- Sorts/hashes may be spilling to temporary files.
- Transactions may be waiting on row locks or DDL locks.
- One critical query may suffer severe cache misses masked by millions of hits from another query.
- Counters are **cumulative** over hours/days or since the last reset.
- WAL, checkpoints, and other I/O are not captured by this single ratio.

Never tune a database based solely on a single high or low hit ratio.

### 14.2. blks_read does not equal physical disk reads

A shared-buffer miss triggers a PostgreSQL read call, yet the OS page cache may already hold that block. Therefore `blks_read` does not prove the underlying storage device executed that exact number of physical reads.

To verify physical device I/O, combine filesystem, OS, and cloud storage metrics alongside detailed PostgreSQL I/O stats where available.

### 14.3. Snapshotting over a time window

To measure the ratio over one hour, take the delta between two snapshots:

~~~text
hits_in_window  = hits_at_end  - hits_at_start
reads_in_window = reads_at_end - reads_at_start

hit_pct_window =
  100 * hits_in_window /
  (hits_in_window + reads_in_window)
~~~

Check `stats_reset` before subtracting; if counters were reset between snapshots, the delta calculation will be invalid.

## 15. Per-Table Cache Statistics

To inspect user tables:

~~~sql
SELECT
    schemaname,
    relname,
    heap_blks_read,
    heap_blks_hit,
    idx_blks_read,
    idx_blks_hit,
    toast_blks_read,
    toast_blks_hit
FROM pg_statio_user_tables
WHERE schemaname = 'public'
ORDER BY
    COALESCE(heap_blks_read, 0) +
    COALESCE(idx_blks_read, 0) DESC
LIMIT 20;
~~~

Metric groups:

- `heap_blks_read/hit`: reads/hits for the table's heap.
- `idx_blks_read/hit`: reads/hits across the table's indexes.
- `toast_blks_read/hit`: TOAST storage when oversized column values are stored out-of-line.

These cumulative counters help spot tables with heavy block accesses, but **cannot identify which queries caused them**. Pair them with query logging, `pg_stat_statements` (if enabled), and `EXPLAIN`.

Do not compare raw hit counts between two tables to conclude one has better or worse caching; total access frequency and working set sizes differ.

## 16. EXPLAIN (ANALYZE, BUFFERS): Seeing Cache Activity in a Plan

Example:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, customer_id
FROM shop.orders
WHERE customer_id = 42;
~~~

Output may include:

~~~text
Buffers: shared hit=120 read=15
~~~

How to read it:

- `shared hit=120` indicates buffer accesses served from shared buffers in the reported scope.
- `read=15` means 15 blocks had to be read through the relation I/O path.
- This is not exact proof of physical storage device read count.

**`EXPLAIN (ANALYZE)` actually executes the SQL statement**. For DML, this performs real changes. Never run `EXPLAIN (ANALYZE) DELETE ...` in production treating it as read-only.

### 16.1. Reading plan nodes

Plans contain parent/child node hierarchies. Buffer numbers on parent lines already aggregate subtree totals, so do not blindly sum numbers across every line to produce a new total.

Some outputs also show `Buffers: local ...` or `Buffers: temp ...`, corresponding to local buffers or temporary spill files.

### 16.2. Spotting in-memory sort vs. disk spill

A node may report:

~~~text
Sort Method: quicksort  Memory: 2048kB
~~~

or:

~~~text
Sort Method: external merge  Disk: 8192kB
Buffers: shared hit=... read=..., temp read=... written=...
~~~

`external merge` and `temp read/written` indicate the sort spilled to temporary files. `Memory` on a sort node is not the backend's total RAM.

If a query is slow primarily due to sort spills, increasing `shared_buffers` is not the direct fix. Look at `work_mem`, row counts, the planner, and whether an index can supply pre-sorted order.

## 17. Practice with a Sample Table

Run these commands in a **lab PostgreSQL database**, never production. Objects live in schema `memory_lab` to avoid colliding with application data.

### 17.1. Creating the table

~~~sql
CREATE SCHEMA IF NOT EXISTS memory_lab;

CREATE TABLE memory_lab.sale_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL
);
~~~

Generate 50,000 sample rows:

~~~sql
INSERT INTO memory_lab.sale_events (
    customer_id, category, amount, occurred_at
)
SELECT
    (g % 1000) + 1,
    'category-' || (g % 20),
    ((g % 25000) / 100.0)::NUMERIC(12, 2),
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + g * INTERVAL '1 second'
FROM generate_series(1, 50000) AS g;

ANALYZE memory_lab.sale_events;
~~~

You may reduce the row count if your learning machine has limited resources. Small synthetic data is not a production performance benchmark.

### 17.2. Inspecting table and index sizes

~~~sql
SELECT
    pg_size_pretty(
        pg_relation_size('memory_lab.sale_events')
    ) AS heap_size,
    pg_size_pretty(
        pg_indexes_size('memory_lab.sale_events')
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size('memory_lab.sale_events')
    ) AS total_size;
~~~

Relation size on disk does not mean all that data currently resides in shared buffers.

### 17.3. Reading data by primary key

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, customer_id, amount
FROM memory_lab.sale_events
WHERE event_id BETWEEN 1000 AND 2000;
~~~

Re-running the query in the lab may show hit/read numbers shifting as pages enter the cache. Exact plans and counts are not guaranteed to match across every system.

### 17.4. Testing sort with low work_mem

~~~sql
BEGIN;

SET LOCAL work_mem = '64kB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    event_id,
    customer_id,
    category,
    amount,
    occurred_at
FROM memory_lab.sale_events
ORDER BY category, amount DESC, occurred_at;

ROLLBACK;
~~~

With enough rows, `external merge` and temporary file I/O can appear. Exact behavior depends on dataset size, planner decisions, parallelism, and available memory.

### 17.5. Testing with a larger budget

~~~sql
BEGIN;

SET LOCAL work_mem = '16MB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    event_id,
    customer_id,
    category,
    amount,
    occurred_at
FROM memory_lab.sale_events
ORDER BY category, amount DESC, occurred_at;

ROLLBACK;
~~~

Comparing outputs:

| Indicator | Low work_mem | Larger work_mem |
|---|---|---|
| Sort Method | Likely external merge | Likely quicksort / in-memory |
| Temp read/written | Likely higher | Likely lower or zero |
| Memory on sort node | Constrained by budget | May be higher |
| Execution Time | May suffer from temp file I/O | May improve; measure to verify |
| Server-wide RAM | Not inferred from one query | Risk increases if applied globally |

Both transactions changed `work_mem` **locally**; the `sale_events` table created earlier still exists.

## 18. Tracking Temporary Files Over Time

~~~sql
SELECT
    datname,
    temp_files,
    pg_size_pretty(temp_bytes) AS temp_bytes_written,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
~~~

`temp_files` and `temp_bytes` are cumulative counters, **not the temporary disk space currently occupied at query time**.

If these counters climb rapidly, look for SQL statements causing:

- Large sorts.
- Hash joins/aggregates exceeding budget.
- Huge intermediate result sets from poorly selective JOINs or filters.
- Parallel reports or many concurrent sessions.

### 18.1. log_temp_files

~~~sql
SHOW log_temp_files;
~~~

When configured appropriately, PostgreSQL logs temporary files exceeding a threshold. This helps pinpoint spilling queries. However, setting the threshold too low can flood logs, impacting I/O and security.

Do not enable verbose temp-file logging in production without evaluating log retention and data exposure.

### 18.2. pg_stat_statements

When the `pg_stat_statements` extension is installed and configured, it aggregates metrics by normalized query pattern, including shared/temp block counters in supported versions.

Notes:

- Not every server enables this extension.
- It may require startup configuration (`shared_preload_libraries`) and appropriate permissions.
- Counters accumulate since the last reset.
- Query text can contain sensitive literals depending on configuration.

You do not need to install this extension merely to understand the three memory layers.

## 19. Observing Backends and Connections

A simple query:

~~~sql
SELECT
    backend_type,
    state,
    COUNT(*) AS process_count
FROM pg_stat_activity
GROUP BY backend_type, state
ORDER BY backend_type, state;
~~~

To count client connections specifically:

~~~sql
SELECT
    state,
    COUNT(*) AS session_count
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY state
ORDER BY state;
~~~

Common states:

- `active`: backend is executing or processing a request.
- `idle`: waiting for a new command.
- `idle in transaction`: a transaction remains open even though the session is not running SQL right now.

You cannot infer exact memory footprint from `state`. An idle session does not necessarily consume large RAM, though it retains baseline overhead and may retain allocator memory after previous queries.

### 19.1. Long-running transactions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Long transactions impact MVCC/VACUUM and locking. That is a related operational issue, though not direct evidence that the session is holding large sort memory.

Never terminate production backends based solely on transaction age without verifying ownership and impact.

## 20. Memory Inside a Backend: pg_backend_memory_contexts

On PostgreSQL versions supporting **`pg_backend_memory_contexts`** with sufficient privileges:

~~~sql
SELECT
    name,
    parent,
    level,
    pg_size_pretty(total_bytes) AS total_size,
    pg_size_pretty(used_bytes) AS used_size,
    pg_size_pretty(free_bytes) AS free_size
FROM pg_backend_memory_contexts
ORDER BY total_bytes DESC
LIMIT 20;
~~~

This view reports memory contexts for the **current backend only**, not a server-wide summary of all backends.

Columns show memory allocated to each context, used bytes, and free bytes within that context. They do not map one-to-one with OS-level RSS.

Some versions also provide functions to log another backend's memory contexts with proper privileges; that is an advanced diagnostic step with security and overhead considerations, not a routine beginner check.

## 21. Reading Memory from the Operating System

On Linux, operators commonly run:

~~~bash
free -h
vmstat 1 5
ps -eo pid,rss,cmd
~~~

Metrics to understand:

| Metric | What to check |
|---|---|
| Memory available | RAM kernel estimates can still be allocated without swapping |
| Page cache/buffers | RAM currently used by the OS for file caching |
| Process RSS | Resident memory seen per process; may include shared pages |
| Swap in/out | Swapping activity, especially if continuously rising |
| OOM-kill | Indicator of exceeding memory limits or severe RAM exhaustion |
| Disk latency/throughput | Corroborating data to confirm physical I/O pressure |

### 21.1. Summing RSS across all PostgreSQL processes double-counts memory

Shared memory is mapped into many backends. Summing RSS across 100 processes **counts the same shared pages repeatedly**.

To evaluate system memory usage accurately, combine system-wide/cgroup metrics with tools distinguishing private vs. shared memory. On Linux, PSS (*proportional set size*) can help where supported.

### 21.2. Low free RAM does not automatically mean RAM exhaustion

Linux puts spare RAM to work as file cache. A server with low `free` but high `available` and virtually zero swap activity can be completely healthy.

Conversely, persistently low `available`, rising swap activity, spiking latency, or container OOM kills indicate a real memory budget issue.

### 21.3. Huge pages

~~~sql
SHOW huge_pages;
~~~

Huge pages reduce page-table management overhead for large shared memory allocations on supported platforms. However, they require proper OS pre-configuration; forcing `huge_pages = on` without available huge pages prevents the server from starting.

Do not confuse explicit huge pages with OS transparent huge pages (THP). Plan operational changes carefully.

## 22. Diagnostic Scenarios

### 22.1. High shared-buffer reads, slow queries

Possible causes include a large working set or queries scanning far more pages than needed. Before enlarging `shared_buffers`:

- Inspect `WHERE` conditions and indexes.
- Check rows and blocks scanned.
- Determine whether sequential scanning is truly needed.
- Inspect OS page cache and physical I/O.
- Check whether hot data could reasonably fit if cache is increased modestly.

Tuning SQL often yields far greater gains than adding RAM when a query reads unnecessary data.

### 22.2. High hit ratio, yet queries remain slow

Possible causes:

- Heavy CPU work filtering or computing over many tuples.
- Sorts/hashes spilling to temporary files.
- Lock waits or deadlocks.
- Suboptimal join plans.
- Huge result sets slowing network transfer or client processing.

Inspect `EXPLAIN (ANALYZE, BUFFERS)`, temp counters, and wait events.

### 22.3. Single report runs fast, peak hours hit OOM

Multiple memory-intensive queries are likely running concurrently. Check:

1. Active query count.
2. `work_mem` per operation.
3. `hash_mem_multiplier`.
4. Parallel workers.
5. Backend private memory.
6. Autovacuum/maintenance activity.
7. Cgroup limit and OS available RAM.

Do not raise global `work_mem` further before identifying the root cause.

### 22.4. High temporary file usage

Sort/hash spills are not solved directly by `temp_buffers`. Inspect the query plan, sorts, hashes, intermediate row counts, `work_mem`, and index design.

### 22.5. I/O spikes around checkpoints

If I/O surges follow dirty-page writes and checkpoints, inspect checkpoint stats, WAL settings, backend writes, and device capacity for your PostgreSQL version.

Do not assume raising `work_mem` or `temp_buffers` will fix checkpoint I/O.

### 22.6. OS cache shrinks after raising shared_buffers

On a host with fixed RAM, enlarging `shared_buffers` reduces headroom for the OS file cache and backends. Overall performance may improve or degrade depending on access patterns.

Measure the whole system before and after, not just a single setting.

## 23. Safe Memory Tuning Workflow

An operational sequence:

**Step 1 — Identify the symptom.** Slow queries, heavy temp files, high physical I/O, or OOM kills?

**Step 2 — Record current settings.**

~~~sql
SELECT name, setting, unit, context, source
FROM pg_settings
WHERE name IN (
    'shared_buffers',
    'work_mem',
    'hash_mem_multiplier',
    'temp_buffers',
    'maintenance_work_mem',
    'effective_cache_size',
    'max_connections'
)
ORDER BY name;
~~~

**Step 3 — Observe the workload.** Active backend count, concurrent reports, sort/hash nodes, and maintenance tasks.

**Step 4 — Analyze key queries.** Use `EXPLAIN (ANALYZE, BUFFERS)` in a safe environment to check shared hits/reads and temp reads/writes.

**Step 5 — Build a RAM budget.** Account for shared memory, backend private memory, maintenance, OS cache, and safety headroom; use container limits when applicable.

**Step 6 — Make the smallest-scope change.** If only one report needs extra sort memory, try `SET LOCAL work_mem` under controlled concurrency before changing global settings.

**Step 7 — Plan restarts when changing shared_buffers.** Coordinate maintenance windows, verify OS memory headroom, and prepare a rollback config.

**Step 8 — Measure before and after.** Compare latency, disk/temp I/O, available memory, swap, OOMs, CPU, workload behavior, and stability.

Never change every parameter at once. Raising `shared_buffers`, `work_mem`, `max_connections`, and parallel workers simultaneously makes it nearly impossible to tell which change helped or broke stability.

## 24. Common Mistakes

### 24.1. "Shared buffers are the only cache"

False. The OS page cache also caches file pages. A shared-buffer miss does not guarantee a physical disk read.

### 24.2. "effective_cache_size allocates RAM"

False. It is a planner cost-estimation hint, not an allocated memory pool.

### 24.3. "work_mem is a per-session cap"

False. It applies per eligible operation; a single query can have multiple nodes and parallel workers.

### 24.4. "Every connection allocates full work_mem at connect time"

False. Sort/hash working memory is allocated on demand, though connections still carry baseline overhead.

### 24.5. "Raising temp_buffers fixes ORDER BY spills"

Not directly. Sort/hash spills depend primarily on `work_mem` and the plan; `temp_buffers` serves temporary table pages.

### 24.6. "blks_read equals physical disk reads"

Not necessarily. The OS page cache can satisfy reads even after a shared-buffer miss is recorded.

### 24.7. "A 99% hit ratio proves the system is completely healthy"

Insufficient. Queries still incur CPU, lock waits, temp I/O, WAL overhead, and more.

### 24.8. "Summing postgres process RSS gives true RAM usage"

This double-counts shared memory. Use system-wide/cgroup metrics and tools separating private vs. shared pages.

### 24.9. "Low free RAM always means memory exhaustion"

No. OS file cache is reclaimable. Check `available`, swap activity, and memory pressure.

### 24.10. "Larger shared_buffers is always faster"

No such rule exists. Over-allocating shrinks headroom for everything else.

### 24.11. "Autovacuum runs automatically so maintenance RAM doesn't matter"

Autovacuum workers still consume memory, can run concurrently, and must be included in RAM budgets.

### 24.12. "Higher max_connections proportionally increases throughput"

Not necessarily. Excess backends increase RAM, CPU, and I/O contention; connection pooling usually scales far better.

### 24.13. "EXPLAIN ANALYZE only analyzes without executing"

False. It actually executes the SQL. On DML, it modifies data.

### 24.14. "Setting work_mem to hundreds of MB globally is the fastest optimization"

It can trigger OOM when concurrent queries run multiple sort/hash nodes. Tune according to workload, queries, and concurrency.

## 25. Core Parameter Comparison Table

| Parameter | Role | Scope / note |
|---|---|---|
| `shared_buffers` | Caches table/index pages | Instance-wide shared pool; usually requires restart |
| `wal_buffers` | Buffers WAL records | Shared memory; supports logging/recovery |
| `work_mem` | Base memory per sort/hash operation | Per operation, not per session |
| `hash_mem_multiplier` | Multiplier for hash operation budgets | Not a separate pre-allocated cache |
| `temp_buffers` | Caches temporary table pages | Session-local, allocated on demand |
| `maintenance_work_mem` | Memory for maintenance operations | Depends on operation and configuration |
| `autovacuum_work_mem` | Memory for autovacuum workers | Can inherit `maintenance_work_mem` |
| `effective_cache_size` | Cache estimate for query planner | **Allocates no RAM** |
| `max_connections` | Connection limit | Affects concurrency and backend overhead |
| `max_parallel_workers_per_gather` | Parallel worker cap per gather node | Can multiply memory consumption |
| `temp_file_limit` | Caps certain temporary disk files | Not RAM, and doesn't cover every temp storage type |
| `huge_pages` | Shared memory page-management mode on supported OSes | May require OS preparation |

## 26. Applied Exercises

### Exercise 1 — Cache hits and disk reads

A query reports `Buffers: shared hit=300 read=40`. Can you conclude the SSD performed exactly 40 physical reads?

**Hint:** No. The OS page cache may satisfy blocks not held in shared buffers.

### Exercise 2 — effective_cache_size

A server has `shared_buffers = 2GB` and `effective_cache_size = 8GB`. Has PostgreSQL allocated 10 GiB across these two settings?

**Hint:** No. `effective_cache_size` is a planner estimate.

### Exercise 3 — Multiple work_mem allocations

A query has two sort nodes and one hash join. Why can a single session consume more than one `work_mem`?

**Hint:** Multiple independent operations and `hash_mem_multiplier`; several nodes can hold memory concurrently.

### Exercise 4 — Temp tables vs. sort spills

Which scenario involves `temp_buffers`, and which involves `work_mem`: creating a temporary table to hold IDs, or sorting one million rows that spill to a temporary file?

**Hint:** Temp tables use local buffers; sorting uses `work_mem`.

### Exercise 5 — 200 connections

A server has `max_connections = 200` with only 15 active backends. Can you multiply `200 * work_mem` to determine current RAM usage?

**Hint:** No, because `work_mem` is allocated per active operation on demand; idle backends still carry baseline memory.

### Exercise 6 — Reading sorts in EXPLAIN

You see `Sort Method: external merge` and a large `temp written`. Which settings and factors should you inspect first?

**Hint:** `work_mem`, query plan, intermediate row count, indexes, parallelism, and concurrency.

### Exercise 7 — OS page cache

Linux reports low `free` RAM, high `available` RAM, and zero swap growth. Can you conclude the host is out of memory?

**Hint:** Not yet. The OS may be using RAM for reclaimable page cache.

### Exercise 8 — Commits and WAL

A transaction commits successfully while a dirty heap page still sits in shared buffers. Does this undermine durability?

**Hint:** No. WAL and durability settings allow data pages to be flushed to files later per PostgreSQL mechanics.

### Exercise 9 — Peak-hour OOM

After raising `work_mem` globally, a single report runs faster, yet the server hits OOM when 30 reports run concurrently. Propose ways to reduce risk.

**Hint:** Lower the global setting, raise locally only for jobs that need it, cap report concurrency, review parallel workers and `hash_mem_multiplier`, and tune SQL.

### Exercise 10 — Measuring shared hits

Write a query retrieving the shared-buffer hit ratio and `stats_reset` from `pg_stat_database`. Why compare differences between two snapshots?

**Hint:** Cumulative counters mask recent shifts; after a reset, establish a fresh baseline.

### Exercise 11 — Memory budgeting

A server has 32 GiB RAM and `shared_buffers = 8 GiB`. Name at least six other RAM categories to evaluate before raising `shared_buffers` to 24 GiB.

**Hint:** OS page cache, backend state, sorts/hashes, autovacuum, WAL/shared structures, parallel workers, kernel/agents, and safety headroom.

### Exercise 12 — Measuring backend memory

Does `pg_backend_memory_contexts` report memory across all connections in the cluster?

**Hint:** No. It reports memory contexts of the current backend only, subject to privileges and supported versions.

## 27. Quick Reference

| Question | Answer |
|---|---|
| What do shared buffers hold? | Shared cached table and index pages |
| Are shared buffers allocated per connection? | No, per PostgreSQL instance |
| Does a shared-buffer miss mean an SSD read? | Not necessarily; OS page cache sits underneath |
| Does a high cache hit ratio mean queries are always fast? | No |
| What is `work_mem` a budget for? | Each eligible sort/hash operation |
| Can one query use multiple `work_mem` budgets? | Yes, across multiple nodes/workers |
| What is `temp_buffers` for? | Session-scoped temporary tables |
| Does a sort spill directly involve `temp_buffers`? | No; check `work_mem` and the plan |
| What is `maintenance_work_mem` for? | Eligible maintenance operations |
| Does `effective_cache_size` allocate memory? | No, it informs the planner |
| Are WAL buffers the same as shared buffers? | No |
| Where do you inspect hits/reads? | `pg_stat_database`, `pg_statio...`, `EXPLAIN BUFFERS` |
| Where do you inspect temp files? | `pg_stat_database`, `EXPLAIN`, and `log_temp_files` |
| Should you sum RSS across all backends? | Not naively, as shared pages get counted multiple times |
| Does `max_connections` equal concurrent heavy queries? | No |
| Is raising `shared_buffers` always better? | No, balance across all memory consumers |
| Where do you inspect configuration? | `SHOW` and `pg_settings` |
| Does `EXPLAIN ANALYZE` execute the query? | Yes |
| What to check during an OOM? | OS/cgroups, backend concurrency, `work_mem`, maintenance, parallel workers, and plans |

---

## Conclusion

PostgreSQL relies on **multiple cooperating memory layers**. **Shared buffers** cache relation pages across backends; **backend private memory** supports session state and operators like sorts and hashes; and the **OS page cache** caches file pages at the operating-system level, often avoiding physical disk reads even after a shared-buffer miss. WAL buffers and other shared structures serve distinct engine duties.

When tuning memory, distinguish **actual memory-allocating parameters** from **estimation hints** like `effective_cache_size`; distinguish **per-operation `work_mem`** from a whole-session cap; and distinguish **cache misses** from **physical device reads**. A fast single report never guarantees stability when concurrent queries contend for RAM.

The reliable approach is checking settings via `pg_settings`, shared hits/reads and temp files via statistics views, execution plans via `EXPLAIN (ANALYZE, BUFFERS)`, and correlating with OS `available` memory, swap, I/O, and container limits. Only make changes after understanding the workload and headroom. Mastering these three memory layers lets you tune PostgreSQL by measurement rather than guesswork.
