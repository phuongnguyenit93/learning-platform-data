# Buffer Pool, Working Set, and Measuring Actual Memory Demand

InnoDB uses the buffer pool to keep frequently accessed data and index pages in RAM. If the hot set of pages (the working set) fits in the buffer pool, many reads can be served from memory, reducing storage I/O. If the buffer pool is smaller than actual demand, pages are evicted and must be read back; if too much RAM is allocated to the buffer pool, MySQL may run short on memory for connections, temporary tables, Performance Schema, the operating system, and other processes.

Therefore, sizing the buffer pool is not simply taking a fixed percentage of RAM. You need to measure the working set under a representative workload, observe hits/misses, dirty pages, read-ahead, and I/O rates, and then budget for the entire `mysqld` process as well as the operating system. The goal is enough RAM for hot pages while preserving headroom when load spikes, DDL runs, or many sessions operate concurrently.

## Objectives

After this lesson, you will be able to:

- Explain what the buffer pool stores and how the working set differs from total database size.
- Measure logical reads, physical reads, buffer pool hit ratio, and eviction trends.
- Read free pages, dirty pages, read-ahead, and flush activity to spot memory/I/O pressure.
- Estimate the working set from table/index sizes and actual workloads.
- Budget RAM for the buffer pool, connections, sort/join buffers, TempTable, Performance Schema, and the operating system.
- Change `innodb_buffer_pool_size` in a controlled manner and verify effectiveness after resizing.
- Warm up the cache after a restart using buffer pool dump/load and recognize the limits of this mechanism.

Examples assume MySQL 8.0 or later, InnoDB, and the default 16 KiB page size. Some variables, online resize constraints, and status displays vary by version; verify the actual values on your instance before applying changes.

## 1. What Does the Buffer Pool Store?

The buffer pool is the largest memory area in many InnoDB-focused MySQL instances. It caches pages from tablespaces, primarily including:

- **Index pages:** pages of clustered indexes and secondary indexes.
- **Data pages:** in InnoDB, row data is stored in the leaf pages of the clustered index; reading a row usually means accessing the index page containing that row.
- **Undo-related pages and internal pages:** certain pages supporting storage structures and transactions are also cached in the buffer pool.
- **Newly read or modified pages:** pages loaded from tablespaces or modified in memory before being flushed to disk.

The buffer pool is not all the RAM used by `mysqld`. The redo log buffer, connection/thread structures, sort/join/read buffers, TempTable, Performance Schema, data dictionary, table cache, and many other structures reside outside the buffer pool page frames.

Check the configured size and page size:

```sql
SHOW VARIABLES LIKE 'innodb_buffer_pool_size';
SHOW VARIABLES LIKE 'innodb_page_size';
SHOW VARIABLES LIKE 'innodb_buffer_pool_instances';
SHOW VARIABLES LIKE 'innodb_buffer_pool_chunk_size';
```

With a 16 KiB page size, a 16 GiB buffer pool holds roughly one million page frames before accounting for metadata and management structures. This is purely a capacity conversion; it does not mean every page holds application data or is used at the same time.

## 2. Working Set vs. Total Database Size

The **working set** is the set of pages that the workload actually accesses frequently over a given period. It depends on queries, data distribution, time of day, application-tier caching, and background jobs.

For example, a database has 2 TiB of total data and indexes, but an order-processing system frequently accesses only the last 14 days of order data plus a few lookup indexes. The working set can be much smaller than the total database. Conversely, a report scanning the entire history can temporarily expand the working set and push transactional hot pages out of the buffer pool.

Three concepts to separate:

| Concept | Meaning | Used For |
|---|---|---|
| Database footprint | Total size of data and indexes on storage | Forecasting storage capacity and data limits |
| Working set | Pages accessed by the workload during an observation window | Estimating cache demand |
| Buffer pool size | Amount of RAM InnoDB allocates for the page cache | Limiting how many pages can be held simultaneously |

Do not increase the buffer pool solely because the total database is larger than RAM. Nor should you shrink the buffer pool just because the database is small: multiple indexes, concurrent queries, and write workloads may need headroom for page churn, dirty pages, and internal structures.

## 3. LRU, Old/Young Pages, and Eviction

InnoDB manages pages in the buffer pool using LRU lists. Newly read pages are typically inserted into the old sublist; pages accessed again under qualifying conditions are promoted to the young sublist. This mechanism helps pages likely to be reused stay longer, while pages read only once can be evicted sooner.

This midpoint insertion design helps reduce the chance that a sequential scan of a large table replaces the entire hot cache. Related variables include:

```sql
SHOW VARIABLES LIKE 'innodb_old_blocks%';
```

- `innodb_old_blocks_pct` controls the percentage of the LRU allocated to the old sublist.
- `innodb_old_blocks_time` controls how long a page must stay in the old sublist before a subsequent access can promote it to the young sublist.

Do not tune these variables by guesswork. If the workload includes full scans or large reports, first verify whether those queries increase read-ahead evictions and push hot pages out of the cache. Changing the LRU policy may help sequential-scan workloads, but it can also reduce cache efficiency for other queries.

When the buffer pool needs space for a new page and no free pages remain, InnoDB must pick an evictable page from the LRU. If that page is dirty, it must be flushed before reuse. Thus, buffer pool pressure can show up in both read I/O and flush I/O.

## 4. Measuring Logical Reads and Physical Reads

Two fundamental counters:

- `Innodb_buffer_pool_read_requests`: number of logical read requests to the buffer pool.
- `Innodb_buffer_pool_reads`: number of times InnoDB had to read a page into the buffer pool because the page was not present in cache.

Retrieve the metrics:

```sql
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_read%';
```

Hit ratio is commonly estimated over a measurement interval using the delta of the two counters:

\[
\text{Hit ratio} =
\left(1 - \frac{\Delta\text{physical reads}}
{\Delta\text{logical read requests}}\right) \times 100\%
\]

For example, in 10 minutes there are 100 million logical read requests and 50,000 buffer pool read misses:

\[
\left(1 - \frac{50{,}000}{100{,}000{,}000}\right) \times 100
= 99.95\%
\]

This is a reference ratio, not proof that queries are fast. A 99.95% hit ratio can still coincide with high latency if the 50,000 misses cluster into a few seconds, storage is slow, or the workload is experiencing lock waits. Conversely, a large batch scan may lower the ratio yet still complete within an acceptable time.

### Taking Deltas Correctly

GLOBAL counters typically accumulate since server startup or since the last status reset. Take two snapshots separated by a representative interval, record timestamps, and compute the delta. If the server restarted or counters were reset between the two snapshots, discard that measurement window and start over.

`Innodb_buffer_pool_reads` is the number of times InnoDB had to load a page into the buffer pool, not necessarily the exact physical IOPS hitting the device. OS caches, storage caches, and how the system performs I/O can affect device-level numbers. To measure actual physical I/O, combine OS and storage metrics.

## 5. Reading Page States and Buffer Pool Pressure

Useful status counters:

```sql
SHOW GLOBAL STATUS WHERE Variable_name IN (
    'Innodb_buffer_pool_pages_total',
    'Innodb_buffer_pool_pages_data',
    'Innodb_buffer_pool_pages_dirty',
    'Innodb_buffer_pool_pages_free',
    'Innodb_buffer_pool_pages_misc',
    'Innodb_buffer_pool_pages_flushed',
    'Innodb_buffer_pool_wait_free',
    'Innodb_buffer_pool_read_ahead',
    'Innodb_buffer_pool_read_ahead_evicted'
);
```

| Counter | How to Interpret |
|---|---|
| `Innodb_buffer_pool_pages_total` | Total number of page frames in the buffer pool |
| `Innodb_buffer_pool_pages_data` | Pages containing data counted in the buffer pool |
| `Innodb_buffer_pool_pages_dirty` | Modified pages not yet flushed |
| `Innodb_buffer_pool_pages_free` | Currently free page frames |
| `Innodb_buffer_pool_pages_misc` | Pages used for internal/metadata buffer pool purposes |
| `Innodb_buffer_pool_pages_flushed` | Number of flushed pages; track deltas |
| `Innodb_buffer_pool_wait_free` | Number of times InnoDB had to wait for a free page; inspect delta and workload |
| `Innodb_buffer_pool_read_ahead` | Pages prefetched into the buffer pool |
| `Innodb_buffer_pool_read_ahead_evicted` | Read-ahead pages evicted before being accessed; may suggest unhelpful prefetching |

Low `pages_free` does not automatically mean the buffer pool is out of RAM. InnoDB can use most of the pool for page caching and actively replace pages via LRU. More concerning signs are `Innodb_buffer_pool_wait_free` increasing during peak hours, rising read misses, flushing falling behind, and worsening read/write latency.

High `pages_dirty` is also not automatically an error. Dirty pages are data waiting to be flushed; observe the dirty percentage, flush rate, checkpoint pressure, and storage capacity. If dirty pages grow continuously while page cleaners cannot keep up, write workloads can put pressure on the buffer pool and redo log.

## 6. Read-Ahead and Cache Pollution

InnoDB can prefetch pages it predicts will be accessed next, for example when detecting sequential or extent-based access. Read-ahead reduces latency when the workload actually uses the subsequent pages.

If prefetched pages are not accessed, they may be evicted from the buffer pool. Monitor deltas of:

```sql
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_read_ahead%';
```

If `Innodb_buffer_pool_read_ahead_evicted` grows rapidly relative to `Innodb_buffer_pool_read_ahead`, the workload may be prefetching many unused pages. Look for large scan queries, full-table reports, or sequential read patterns. Do not conclude from a single ratio alone: some intentional batch jobs still generate read-ahead evictions.

Measures that are often more effective than immediately changing LRU settings:

- Run heavy reports during times with minimal impact on transactional workloads.
- Read only the required columns and data ranges.
- Use partition pruning and appropriate indexes to reduce scans.
- Batch operations by key ranges when business logic permits.
- Re-measure cache misses and latency across the entire workload before changing read-ahead/LRU variables.

## 7. Estimating Working Set Size

### Step 1: Estimate Data and Index Footprint

`INFORMATION_SCHEMA.TABLES` can be used to list large InnoDB tables:

```sql
SELECT TABLE_SCHEMA,
       TABLE_NAME,
       DATA_LENGTH,
       INDEX_LENGTH,
       DATA_FREE,
       DATA_LENGTH + INDEX_LENGTH AS data_and_index_bytes
FROM information_schema.tables
WHERE ENGINE = 'InnoDB'
  AND TABLE_SCHEMA = DATABASE()
ORDER BY data_and_index_bytes DESC
LIMIT 30;
```

`DATA_LENGTH` and `INDEX_LENGTH` are estimates from metadata/storage engine statistics; they do not tell you exactly which pages are hot. For partitioned tables, inspect per-partition figures as needed.

### Step 2: Identify Access Workloads

Classify queries by:

- Accessed tables and indexes.
- Data time range (e.g., the last 7 days vs. full history).
- Frequency and concurrency.
- Read/write ratio.
- Whether queries are point lookups, range scans, joins, aggregations, or full scans.

Combine query digests, slow logs, and `EXPLAIN` to see which tables/indexes are frequently accessed. The size of hot tables plus required indexes is a starting point for estimating the working set, not the final answer.

### Step 3: Measure Misses During Representative Load

Take deltas of `Innodb_buffer_pool_reads` and `Innodb_buffer_pool_read_requests` across multiple windows: peak hours, batch jobs, reporting, backups, and post-restart. If misses spike only during reports, workload isolation may be needed rather than increasing the pool for the entire server.

### Step 4: Test Different Sizes

In staging or a controlled window, change the pool in steps, run the same workload, and compare:

- p95/p99 query latency and transaction latency.
- Delta physical reads and logical read requests.
- Read IOPS, write IOPS, and storage latency.
- Dirty pages, pending flushes, and checkpoint pressure.
- `mysqld` RSS/working set, memory pressure, and swap.
- Throughput and error/timeout rates.

Increase the buffer pool only if reducing misses produces tangible improvement without increasing memory pressure at the OS/container layer.

## 8. Sizing the Buffer Pool and Instance-Wide RAM Budget

`innodb_buffer_pool_size` is the primary variable controlling buffer pool capacity. On dedicated MySQL servers, the buffer pool typically takes the largest share of RAM; ratios such as 50–75% of physical RAM can serve as a starting point for some workloads, but they are not a universal formula for every system.

Before choosing a value, budget for all components:

| Component | How RAM Is Consumed |
|---|---|
| InnoDB buffer pool | Large region, typically allocated per configuration |
| Redo log buffer and other InnoDB structures | Shared memory for transaction/storage operations |
| Connections/threads | Thread stacks, network buffers, session state, and connection structures |
| Per-operation buffers | Sort, join, read, read-rnd buffers; can be allocated per query and multiple times within one execution plan |
| TempTable | Global RAM budget and version-dependent thread-local allocations |
| Performance Schema | Instruments, histories, and memory summaries |
| Table/open cache, data dictionary, adaptive hash, and internal structures | Global and metadata memory |
| OS and other processes | Kernel, filesystem cache, agents, backups, monitoring, replication tools |

### Why Not Multiply Every Buffer by `max_connections`?

`max_connections` is a concurrent connection limit, not the count of every buffer pre-allocated at server startup. Many buffers are allocated when a query needs them; some are held per session or thread; a single execution plan can use multiple buffers for different operations.

A realistic estimate should be based on active concurrent sessions, query distribution, number of sort/join operations, result sizes, TempTable usage, and peak workloads. Use measured concurrency and observed memory high-water marks; do not sum every configured setting as if all of them were always used by every connection.

### Illustrative Budget Example

Suppose a machine has 64 GiB of RAM, where MySQL is the primary workload, alongside the OS, a backup agent, and monitoring. An initial plan might reserve 40 GiB for the buffer pool, leaving the rest for redo/undo structures, connection/query buffers, TempTable, Performance Schema, filesystem cache, and headroom. The 40 GiB figure only illustrates how to allocate; it must be replaced by measured peak memory and actual workload requirements.

You can budget in this order:

```text
Available RAM for host/container
- reserve for OS and non-mysqld processes
- headroom for peak workload and maintenance tasks
= expected maximum budget for mysqld

mysqld budget
- non-buffer-pool memory at peak concurrency
= starting upper bound for evaluating buffer pool size
```

Measure non-buffer-pool memory using a representative workload and memory instrumentation; do not treat the sum of per-operation configuration values as actual allocated memory.

Never let `mysqld` sit right against the container memory limit or physical RAM. When the kernel has to swap heavily or the container gets OOM-killed, latency can spike suddenly and the instance can be terminated.

## 9. Changing the Buffer Pool Size

`innodb_buffer_pool_size` supports dynamic resizing in modern MySQL versions:

```sql
SHOW VARIABLES LIKE 'innodb_buffer_pool_size';

SET GLOBAL innodb_buffer_pool_size = 42949672960;
```

The example value above is 40 GiB in bytes; use it only when the RAM budget allows. Online resizing can take time because InnoDB has to adjust page counts, flush, or evict pages. During resizing, some operations may be restricted or forced to wait.

Items to verify:

- `innodb_buffer_pool_chunk_size` and the number of buffer pool instances affect valid resize units on chunk-aware versions.
- The requested value may be rounded to a multiple of chunk/instance size; read the variable back after resizing to check the effective size.
- Not every change completes immediately; monitor the error log and InnoDB status.
- Do not shrink below what the active workload needs or cause the hot working set to be evicted en masse.
- A `GLOBAL` change affects only the running instance; to persist across restarts, configure startup/persisted settings according to operational policy.

Before resizing, record a baseline. After resizing, monitor latency, read misses, free/dirty pages, RSS, swap, and storage I/O across at least one representative workload cycle. If memory pressure increases or throughput drops, roll back to the previous value following your configuration procedure.

## 10. Buffer Pool Instances and Chunks

The buffer pool can be split into multiple instances to reduce internal structure contention in multi-threaded workloads. Each instance manages a subset of pages and its own metadata. In modern workloads, the benefit depends on concurrency and version; do not increase the instance count without measuring.

`innodb_buffer_pool_chunk_size` defines the allocation/resize chunk unit on versions using this mechanism. Combined with the instance count, it affects the effective buffer pool size and online resize granularity. Check:

```sql
SHOW VARIABLES LIKE 'innodb_buffer_pool_instances';
SHOW VARIABLES LIKE 'innodb_buffer_pool_chunk_size';
SHOW VARIABLES LIKE 'innodb_buffer_pool_size';
```

Instance count and chunk size have version-specific constraints and may only be configurable at startup. Consult the documentation for your exact version before making changes. More instances do not shrink the working set and do not by themselves speed up storage.

## 11. Dirty Pages, Page Cleaners, and Storage Capacity

When transactions modify pages, pages in the buffer pool become dirty. InnoDB must flush dirty pages to tablespaces based on checkpoints, free-page pressure, and flush policies. Related variables:

```sql
SHOW VARIABLES LIKE 'innodb_max_dirty_pages_pct';
SHOW VARIABLES LIKE 'innodb_io_capacity';
SHOW VARIABLES LIKE 'innodb_io_capacity_max';
SHOW VARIABLES LIKE 'innodb_page_cleaners';
```

`innodb_io_capacity` and `innodb_io_capacity_max` help InnoDB estimate background I/O capacity and bound flushing in certain situations. Setting them too low can cause dirty pages/checkpoints to accumulate; setting them too high can cause I/O contention with foreground queries. Measure actual storage capacity, latency, and dirty pages before tuning.

`Innodb_buffer_pool_pages_dirty` should be examined alongside `Innodb_buffer_pool_pages_data`, `Innodb_buffer_pool_pages_total`, the rate of `Innodb_buffer_pool_pages_flushed`, redo/checkpoint pressure, and write latency. A single snapshot is insufficient to conclude page cleaners are bottlenecked; a trend over time is needed.

## 12. Warming Up the Buffer Pool After Restart

After a restart, the buffer pool may be nearly empty. Early queries must read pages from tablespaces, causing higher latency until the hot working set is reloaded. MySQL supports dumping the list of pages in the buffer pool before shutdown and reloading them after startup:

```sql
SHOW VARIABLES LIKE 'innodb_buffer_pool_dump_at_shutdown';
SHOW VARIABLES LIKE 'innodb_buffer_pool_load_at_startup';
SHOW VARIABLES LIKE 'innodb_buffer_pool_dump_pct';
```

You can configure:

```ini
[mysqld]
innodb_buffer_pool_dump_at_shutdown=ON
innodb_buffer_pool_load_at_startup=ON
```

`innodb_buffer_pool_load_at_startup` is a startup-time option on modern versions; do not assume it can be enabled via `SET GLOBAL` on a running instance. To actively dump/load immediately at runtime, use the dynamic control variables:

```sql
SET GLOBAL innodb_buffer_pool_dump_now = ON;
SET GLOBAL innodb_buffer_pool_load_now = ON;
```

Dumping saves information about which pages to reload, not a copy of page contents. At startup, InnoDB reads those pages from tablespaces to warm up the cache. The dump file is typically stored in the data directory under the name `ib_buffer_pool`; exact location and handling depend on configuration/version.

Dump/load is not a backup and does not guarantee all hot pages will be loaded. `innodb_buffer_pool_dump_pct` can limit the percentage of pages dumped. After startup, monitor load progress, physical reads, and latency; the live workload still needs time to stabilize.

## 13. Monitoring Memory with Performance Schema and the OS

Performance Schema can report memory instruments if they are enabled:

```sql
SELECT EVENT_NAME,
       CURRENT_NUMBER_OF_BYTES_USED,
       HIGH_NUMBER_OF_BYTES_USED
FROM performance_schema.memory_summary_global_by_event_name
WHERE EVENT_NAME LIKE 'memory/innodb/%'
   OR EVENT_NAME LIKE 'memory/sql/%'
ORDER BY CURRENT_NUMBER_OF_BYTES_USED DESC
LIMIT 30;
```

Instruments may not cover every allocation or may not be enabled in the current configuration. Therefore, Performance Schema figures provide an instrument-level view and do not replace process RSS/working set and container/host memory usage.

Combine these sources:

- `innodb_buffer_pool_size`: configured pool size.
- `SHOW GLOBAL STATUS`: page counts, logical reads, physical reads, dirty pages, wait-free, and read-ahead.
- `SHOW ENGINE INNODB STATUS`: LRU, buffer pool, pending reads/flushes, and I/O info.
- Performance Schema memory summary: instrumented allocations.
- Operating system: process RSS/working set, available memory, swap-in/swap-out, and OOM events.
- Container/cgroup: current memory, memory limit, memory pressure, and OOM kill count if MySQL runs in a container.
- Storage: IOPS, throughput, queue depth, and read/write latency.

Do not deduce that the buffer pool is starved simply because `mysqld` RSS is large. An instance configured with a large pool will naturally have high RSS; what matters is memory pressure, swapping, OOM risk, and actual latency.

## 14. Process for Measuring and Adjusting the Working Set

1. Record physical RAM/container limits, buffer pool size, page size, max connections, and TempTable limits.
2. Gather per-table data/index sizes and identify hot tables/indexes from query digests and workload traces.
3. Choose representative windows including peak OLTP, batch/reporting, and post-restart workloads.
4. Capture two status snapshots separated by an interval; calculate deltas for logical reads, physical reads, wait-free, read-ahead, and pages flushed.
5. Correlate hit ratio with p95/p99 latency, storage I/O, dirty pages, and application throughput.
6. Inspect queries causing large scans, missing indexes, poor pagination, or unnecessary historical data access.
7. Build an instance-wide RAM budget accounting for peak connections/queries/TempTable and OS/container headroom.
8. Adjust the buffer pool in controlled steps on staging or during a maintenance window; verify the effective size.
9. Re-run an equivalent workload and compare latency, misses, I/O, RSS, swap, and OOM risk.
10. Save the baseline, chosen configuration, rationale, and rollback plan.

## 15. Common Misconceptions

| Misconception | Reality |
|---|---|
| The database is larger than RAM, so the buffer pool must equal all RAM | The working set can be smaller than the database; RAM must be reserved for other components |
| A 99.9% hit ratio means queries are fast | Misses may be clustered, storage may be slow, or queries may be waiting on locks |
| `pages_free = 0` means the buffer pool is out of memory | InnoDB uses LRU to reuse pages; inspect wait-free and latency |
| The lower the dirty pages, the better | Continuous flushing can raise write I/O; balance checkpoints and storage |
| Increasing the buffer pool always reduces I/O | It may only increase RSS, cause OS swapping, or fail to help the workload |
| `max_connections × every buffer` is the memory requirement | Many buffers are allocated on demand; use measured concurrency and workloads |
| Buffer pool dump is a backup | Dumping only saves a list of pages for warm-up; data remains in tablespaces/backups |
| More buffer pool instances are always better | Benefits depend on concurrency, version, and management overhead |

## 16. Lab Exercise

On a test MySQL instance with representative data:

1. Record `innodb_buffer_pool_size`, `innodb_page_size`, instance count, and chunk size.
2. Take two snapshots of `Innodb_buffer_pool_read_requests` and `Innodb_buffer_pool_reads` 10 minutes apart; compute the hit ratio from the deltas.
3. Record total/data/dirty/free pages, wait-free, and read-ahead counters. Explain why low free pages is not automatically an error.
4. Query `INFORMATION_SCHEMA.TABLES` to rank tables by data and index size; compare with tables/indexes that actually appear in the workload.
5. Run an OLTP workload and then run a large full scan; observe physical reads and read-ahead evictions before and after.
6. Compare latency and storage I/O when increasing the buffer pool on staging; monitor RSS, swap, and container memory limits.
7. Enable buffer pool dump/load in a test environment, restart, and measure warm-up time and initial-phase latency.
8. Create a RAM budget covering buffer pool, connections, query buffers, TempTable, Performance Schema, OS, and headroom; explain concurrency assumptions.
9. Write a runbook for when `Innodb_buffer_pool_wait_free` rises continuously and storage read latency is high.

## Key Takeaways

- The buffer pool caches InnoDB pages; the working set consists of pages the workload actually accesses, not the entire database footprint.
- Use deltas of logical reads and physical reads to estimate cache behavior; hit ratio does not replace latency and I/O metrics.
- `pages_free`, dirty pages, read-ahead evictions, and wait-free must be read together over time.
- Sizing must account for connection/query buffers, TempTable, Performance Schema, OS, container limits, and peak concurrency.
- Changing `innodb_buffer_pool_size` requires checking chunk/instance alignment, effective size, error logs, and impact on RSS/latency.
- Buffer pool dump/load assists warm-up after restart; it is not a backup and does not replace tablespace data.
- Only increase the buffer pool when metrics show the working set lacks cache and the host/container still has safe headroom.
