# shared_buffers and Its Relationship with the OS Cache in PostgreSQL

PostgreSQL can keep data pages in memory across multiple layers. The layer managed by PostgreSQL is **shared_buffers**; the layer managed by the kernel and operating system is typically the **filesystem page cache**. When a query reads a block, PostgreSQL checks shared_buffers first. If the block is not there, PostgreSQL asks the operating system to read the relation file; the data may already reside in the OS page cache or may need to be read from storage.

Therefore, a read counted as a cache miss in PostgreSQL does not necessarily generate a physical read from disk. The block may be served very quickly from the OS page cache. Conversely, a larger shared_buffers does not always make queries faster: it competes for RAM with the page cache, backend processes, sort/hash operations, autovacuum, and other components.

Clearly distinguish the memory areas:

- **shared_buffers:** Cache of database pages shared by PostgreSQL across backends.
- **OS page cache:** Cache of file contents managed by the kernel, including PostgreSQL relation files accessed through the filesystem.
- **work_mem:** Memory for certain sort/hash operations; can be allocated multiple times within a query and across multiple sessions.
- **temp_buffers:** Per-session private buffers for temporary tables.
- **wal_buffers:** Buffer area for WAL, separate from the table/index page cache.
- **effective_cache_size:** Planner estimate of available cache memory; does not allocate RAM.

~~~text
               Query reads a table/index block
                            |
                            v
                 PostgreSQL shared_buffers
                       /          \
                  cache hit      cache miss
                     |               |
                     v               v
                Use page       Kernel reads file
                 in RAM              |
                                     v
                           OS filesystem page cache
                              /             \
                         cache hit        cache miss
                            |                 |
                            v                 v
                         OS RAM         Storage device
                            \                 /
                             \               /
                              v             v
                          Block returned to PostgreSQL
                                    |
                                    v
                              shared_buffers

The two cache layers have different purposes and management policies.
~~~

This lesson belongs to the **Database Engine Relational PostgreSQL** module, chapter **Resource Tuning**, covering the topic **"shared_buffers and Its Relationship with the OS Cache"**. It focuses on the read/write path, how the two cache layers coordinate, sizing choices, measuring cache behavior, and controlled tuning verification methods.

---

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the role of shared_buffers in PostgreSQL.
2. Distinguish the PostgreSQL shared buffer cache from the OS filesystem page cache.
3. Describe the path of a block during a shared buffer hit, OS cache hit, and storage read.
4. Explain why a PostgreSQL cache miss does not equal a physical disk read.
5. Describe how PostgreSQL manages buffer pages and dirty buffers.
6. Distinguish data buffers from work_mem, temp_buffers, and wal_buffers.
7. Understand how reads, writes, checkpoints, and WAL interact with the two cache layers.
8. Explain the meaning and limitations of the cache hit ratio.
9. Use pg_stat_database, pg_statio_*, and pg_stat_io to observe I/O.
10. Use EXPLAIN (ANALYZE, BUFFERS) to inspect shared/local/temp buffer activity.
11. Know when pg_buffercache and pg_prewarm are useful.
12. Understand effective_cache_size and why it does not allocate memory.
13. Choose an initial shared_buffers size based on RAM, workload, and operating system.
14. Budget memory for shared_buffers, backends, and the OS cache.
15. Recognize memory pressure, swap, and OOM risk.
16. Evaluate the impact of shared_buffers on checkpoints and writeback.
17. Change shared_buffers safely and know when a restart is required.
18. Design warm/cold benchmarks and compare before/after tuning.
19. Avoid common pitfalls when interpreting cache metrics.
20. Build a tuning and monitoring checklist for production.

**Scope:** Modern PostgreSQL on Linux, Windows, and cloud/container environments. PostgreSQL normally uses the OS filesystem cache alongside shared_buffers. I/O statistics details vary by major version; pg_stat_io is available starting in PostgreSQL 16. Sizing values in this lesson are starting points for experimentation, not mandatory configurations for every workload.

---

## 2. What is shared_buffers?

shared_buffers is the shared memory area that PostgreSQL reserves to cache pages from relation files. Backends access this shared buffer area together instead of each session maintaining its own separate page copy.

### 2.1. One buffer usually holds one database page

PostgreSQL is typically built with an 8 KB block size. A shared buffer holds one block of data corresponding to a page of a table, index, or other relation. The block size is set when PostgreSQL is built and can be checked with:

~~~sql
SHOW block_size;
~~~

The actual size of shared_buffers is configured with the parameter of the same name:

~~~sql
SHOW shared_buffers;
~~~

### 2.2. It is a database-level cache

shared_buffers holds pages read from relations or pages modified by the database. It is not a SELECT result cache, not an execution plan cache, and does not store entire objects as standalone copies.

One query can read many pages; one page can be used by many queries and sessions.

### 2.3. Shared across backends

PostgreSQL backends coordinate access to the shared buffer pool using internal synchronization mechanisms. When a backend needs a page, it looks up the buffer mapping, pins the buffer so the page cannot be evicted while in use, and updates related metadata.

### 2.4. The buffer pool is finite

If a new page is needed while the buffer pool is full, PostgreSQL must find a reusable buffer. If the chosen buffer is dirty, the page must be written out first or handled according to the appropriate writeback/checkpoint mechanism.

### 2.5. shared_buffers is not PostgreSQL's total RAM

PostgreSQL also uses memory for backend processes, query execution, maintenance, WAL, shared memory structures, extensions, and other activities. shared_buffers cannot be treated as representing the entire memory footprint.

---

## 3. What is the OS Filesystem Page Cache?

The filesystem page cache is memory managed by the kernel to hold file contents that have been recently read or written. PostgreSQL stores table/index data in relation files on the filesystem; when PostgreSQL reads these files through the OS, the kernel can return data from the page cache.

### 3.1. The OS cache is independent of shared_buffers

PostgreSQL does not directly control the OS's entire page cache. The kernel decides which pages are retained, reclaimed, or flushed to storage based on memory pressure, access patterns, and operating system policies.

### 3.2. A block can appear in both layers

When PostgreSQL reads a page from a file into shared_buffers, the data may simultaneously remain in the OS page cache. Thus, the same content can occupy memory in both layers.

### 3.3. The OS cache can help after a shared buffer miss

If a page is evicted from shared_buffers but remains in the OS page cache, PostgreSQL still must perform a file read operation, yet the kernel can return the data from RAM without reading the storage device.

### 3.4. The kernel manages the page cache system-wide

The OS page cache can be used by PostgreSQL, backup tools, file scanners, monitoring agents, and other processes. Another process reading files can warm the OS cache; memory pressure from another process can cause cached pages to be reclaimed.

### 3.5. The OS cache is not memory dedicated exclusively to PostgreSQL

You do not configure the page cache by setting a PostgreSQL parameter. Monitor memory availability and cache behavior via OS or cloud platform tools.

---

## 4. How Do the Two Cache Layers Coordinate?

To understand performance, trace a block when PostgreSQL needs to read it.

### 4.1. Case A: shared buffer hit

1. A backend needs a table/index block.
2. PostgreSQL finds the block in shared_buffers.
3. The backend pins the buffer and reads the page from shared memory.
4. No OS call is needed to read the relation file for that block.

This is the fastest read path across the two cache layers.

### 4.2. Case B: shared buffer miss, OS page cache hit

1. The backend does not find the block in shared_buffers.
2. PostgreSQL needs to bring the block into the buffer pool.
3. PostgreSQL asks the kernel to read the relation file.
4. The kernel finds the file page in the page cache.
5. The kernel copies/maps the data into PostgreSQL's buffer.
6. PostgreSQL uses the block and updates buffer metadata.

In this case `pg_stat_database.blks_read` may increase, yet the storage device may not perform a physical read.

### 4.3. Case C: miss in both layers

1. The backend does not find the block in shared_buffers.
2. The kernel also does not have the corresponding page in the page cache.
3. The OS sends an I/O request to the storage device.
4. Storage returns the data.
5. The kernel and PostgreSQL receive the block.
6. The page may be retained in both the OS page cache and shared_buffers.

This is typically the slower read path, though latency also depends on SSD/HDD, network storage, queue depth, block size, and concurrency.

### 4.4. Comparison table

| State | PostgreSQL shared_buffers | OS page cache | Storage device read |
| --- | --- | --- | --- |
| Shared hit | Has page | No access needed | No |
| Shared miss, OS hit | Does not have page | Has page | Usually no |
| Miss in both | Does not have page | Does not have page | Yes, unless another storage-layer cache exists |

### 4.5. More cache layers may exist

Cloud storage, storage controllers, RAID controllers, NVMe controllers, and SANs may have their own caches. An OS read does not necessarily hit physical media. When identifying physical I/O, inspect metrics at the appropriate storage layer.

---

## 5. Why Doesn't shared_buffers Replace the OS Page Cache?

The two cache layers play complementary roles.

### 5.1. PostgreSQL understands database page semantics

PostgreSQL manages page usage, buffer pins, dirty pages, WAL ordering, checkpoints, and database-specific operations. The OS page cache does not understand transaction or relation semantics.

### 5.2. The OS cache keeps file pages outside shared_buffers

The OS page cache can retain data pages evicted by PostgreSQL from shared_buffers. This helps reduce physical I/O when the workload reads those pages again.

### 5.3. PostgreSQL still needs its own cache

If it relied solely on the OS page cache, PostgreSQL would lose the ability to manage a buffer pool tailored to the database engine's needs. shared_buffers allows PostgreSQL to coordinate page pinning, dirty page tracking, and background writing.

### 5.4. Do not try to eliminate the OS cache by default

PostgreSQL is normally designed to work alongside the filesystem cache. Trying to force the OS cache down or selecting special I/O modes must be based on specific version, workload, and benchmark data.

### 5.5. Double caching is a trade-off

The same page can occupy RAM in both shared_buffers and the OS page cache. In return, two layers can reduce storage reads and support different access patterns. The tuning goal is balancing memory, latency, and throughput, not maximizing a single cache.

---

## 6. The Write Path

Reads and writes have different semantics. In particular, commit does not mean all data pages have been written immediately to storage.

### 6.1. UPDATE creates a dirty buffer

When a transaction updates a row, PostgreSQL modifies the page in shared_buffers and marks the buffer dirty. WAL records describing the change are generated per write-ahead logging rules.

### 6.2. WAL must precede the data page

WAL must be written/flushed according to durability requirements before the corresponding data page is written durably. This is the write-ahead logging principle.

### 6.3. COMMIT usually waits for WAL flush

Under standard durability settings, PostgreSQL flushes WAL through the commit record before reporting commit success. Modified data pages may still remain in shared_buffers in a dirty state.

### 6.4. Dirty pages are written later

The background writer, checkpointer, or a backend can write dirty pages to files. When writing to a file, data passes through the OS and may reside in the page cache before being synced to storage as part of the durability process.

### 6.5. Checkpoint

Checkpoints ensure dirty pages and WAL meet the conditions required for recovery to start from an appropriate checkpoint. Checkpoints can create I/O bursts if dirty data volume is large or storage lacks sufficient throughput.

### 6.6. Write path diagram

~~~text
UPDATE row
   |
   +--> Modify page in shared_buffers (dirty)
   |
   +--> Generate WAL record
           |
           v
       WAL buffers
           |
           v
       WAL file / flush per commit policy
           |
           v
       COMMIT confirmed
           |
           | Data page may still be dirty
           v
   Background writer / checkpointer / backend
           |
           v
       Write relation file through OS
           |
           v
       OS page cache / filesystem
           |
           v
       fsync and storage durability per checkpoint
~~~

### 6.7. shared_buffers is not a write-through cache

A transaction does not need to write all modified data pages to disk immediately at COMMIT. WAL enables PostgreSQL to redo changes after a crash. That is why commit latency is usually tied directly to WAL flush rather than the time to write all table pages.

### 6.8. The OS page cache is also involved in durability

Writing to a file may only update the kernel page cache. PostgreSQL uses fsync or an equivalent synchronization mechanism to ensure required data reaches storage per the semantics supported by the system. Storage must honor flush/barrier contracts properly.

---

## 7. Other Memory Areas Not to Confuse with shared_buffers

### 7.1. work_mem

work_mem is used for certain sorts, hash joins, hash aggregations, and similar operations. One query can use multiple work_mem allocations; many concurrent sessions can cause memory usage to spike sharply.

### 7.2. temp_buffers

temp_buffers is a private buffer pool for temporary tables per session. It is not shared_buffers and is typically allocated when a session needs it.

### 7.3. wal_buffers

wal_buffers holds WAL records before they are written to WAL files. This is not a table/index page cache. It relates to the write path and WAL throughput.

### 7.4. maintenance_work_mem

Used for certain maintenance tasks such as VACUUM and CREATE INDEX. Autovacuum can have its own budget via autovacuum_work_mem.

### 7.5. Backend-local memory

Each backend also has memory contexts, executor state, tuple slots, sort/hash state, and other allocations. Total memory depends on query complexity and concurrency.

### 7.6. effective_cache_size

This is a planner estimate of memory available for caching data, usually including shared_buffers and the accessible portion of the OS cache after accounting for contention. It does not allocate RAM and does not create a cache.

### 7.7. Summary

| Component | Scope | Purpose |
| --- | --- | --- |
| shared_buffers | Shared across PostgreSQL backends | Cache relation pages |
| OS page cache | System-wide OS | Cache file pages |
| work_mem | Per operation/backend | Sort/hash execution |
| temp_buffers | Per session | Temporary table buffers |
| wal_buffers | Shared WAL buffer area | Buffer WAL records |
| maintenance_work_mem | Maintenance operation | VACUUM/index maintenance |
| effective_cache_size | Planner estimate | Estimate usable cache |

---

## 8. How Does shared_buffers Affect Performance?

### 8.1. Can reduce reads from the OS

If a workload frequently accesses the same set of pages and that set fits in shared_buffers, cache hits can be higher and latency more stable.

### 8.2. Can reduce storage reads

A page retained in shared_buffers does not need to be re-read from a file. This reduces OS calls and can lower I/O load.

### 8.3. Can increase writeback pressure

A large shared_buffers allows more dirty pages to accumulate. Checkpoints must process that dirty data volume. If storage throughput is insufficient, checkpoints can drag on or create latency spikes.

### 8.4. Can shrink the OS page cache

If shared_buffers consumes too much RAM, the kernel has less memory left to cache PostgreSQL file pages and other applications. A shared buffer miss may then hit storage more easily.

### 8.5. Can reduce memory for query execution

If too much RAM is dedicated to shared_buffers, backend operations, autovacuum, the OS, and monitoring agents may run short on memory.

### 8.6. Benefits have diminishing returns

Increasing shared_buffers from very small to a reasonable size can improve cache-sensitive workloads. Increasing further may yield little benefit, or even worsen overall performance if memory pressure increases.

### 8.7. Not every workload is cache-friendly

- Large sequential scans may read vast amounts of data only once.
- Analytics workloads have working sets larger than RAM.
- Random OLTP workloads can benefit when the hot set fits in cache.
- Index-heavy workloads may repeatedly access a set of index pages.
- Batch jobs can alter the cache residency of interactive workloads.

Determine the working set and access pattern before sizing.

---

## 9. Choosing an Initial shared_buffers Size

PostgreSQL documentation commonly cites around **25% of RAM** as a reasonable starting point on a dedicated database server. Levels above roughly **40% of RAM** often do not deliver proportional gains because PostgreSQL still relies on the OS cache. This is a starting guideline, not a fixed rule.

### 9.1. Rough sizing examples

| Physical RAM | 25% of RAM as Starting Point | Notes |
| ---: | ---: | --- |
| 8 GB | 2 GB | Check memory headroom carefully |
| 16 GB | 4 GB | Balance backends and OS cache |
| 32 GB | 8 GB | Measure working set and I/O |
| 64 GB | 16 GB | Do not automatically bump to 32 GB |
| 128 GB | 32 GB | Requires realistic workload benchmarking |

These numbers only illustrate the 25% calculation. They do not account for container memory limits, OS services, connection concurrency, query memory, or other processes.

### 9.2. Dedicated server

If the machine runs only PostgreSQL, a larger share of RAM can be allocated to PostgreSQL compared to a host running multiple applications. Even so, the OS still needs RAM for page cache and kernel overhead.

### 9.3. Shared host

If the host runs PostgreSQL alongside applications, agents, backup processes, or multiple database instances, calculate total memory across all workloads before setting shared_buffers.

### 9.4. Containers

Cgroup/container limits may be lower than host physical RAM. Sizing must follow the actual memory limit visible to and usable by the PostgreSQL process, while leaving headroom for sidecars and kernel accounting per the environment.

### 9.5. Managed databases

Cloud providers may set shared_buffers automatically based on instance class and service limits. Check effective parameters and provider policies before tuning.

### 9.6. Operating system

Windows and certain environments have different memory/shared memory characteristics than Linux. Do not copy sizing verbatim from one OS to another without measuring.

---

## 10. Overall RAM Budget

Setting shared_buffers requires accounting for other memory consumers.

### 10.1. Components to budget for

- shared_buffers.
- WAL buffers and shared memory structures.
- Backend process memory.
- work_mem for concurrent sort/hash operations.
- temp_buffers for sessions using temporary tables.
- maintenance_work_mem.
- autovacuum workers and parallel workers.
- Extensions and background workers.
- OS kernel, filesystem page cache, and monitoring agents.
- Backup/compression tools running on the same host.
- Container sidecars if present.

### 10.2. work_mem can multiply

work_mem is not a single pool divided evenly. A single query can have multiple sort/hash nodes and multiple parallel workers. Many concurrent sessions can allocate it many times over.

### 10.3. Conceptual budget formula

~~~text
Required RAM
  >= shared_buffers
   + shared/WAL/process overhead
   + peak concurrent query memory
   + maintenance/autovacuum memory
   + OS/kernel/page cache headroom
   + non-PostgreSQL processes
~~~

This is a grouping for budgeting, not an exact formula summing every maximum configuration value. Use actual concurrency and measure peak memory.

### 10.4. Avoid swap as a RAM extension mechanism

Heavy swap-in/out can sharply increase latency and trigger cascading failures. A database server short on RAM should be addressed via workload/concurrency/configuration/capacity, rather than relying on swap to sustain throughput.

### 10.5. OOM risk

If the kernel/container OOM killer terminates a PostgreSQL backend or critical process, query failures or server restarts can occur. Monitor OOM events alongside memory pressure.

---

## 11. effective_cache_size: Planner Estimate, Not Allocation

effective_cache_size is a planner parameter used to estimate how much cache is available to a query. The planner uses this estimate when weighing the cost of an index scan versus a sequential scan and other plan choices.

### 11.1. Consumes no RAM

Setting effective_cache_size = 24GB does not allocate 24GB and does not enlarge the OS cache.

### 11.2. Covers multiple cache layers

The estimate generally includes shared_buffers plus the portion of the OS page cache usable by the database, minus memory consumed by competing workloads.

### 11.3. Too-low estimate

The planner may underestimate the likelihood of pages staying in cache and pick a suboptimal plan for certain workloads.

### 11.4. Too-high estimate

The planner may assume index access is cheaper than reality, choosing plans based on cache assumptions that do not hold under high memory pressure.

### 11.5. Do not equate with shared_buffers

shared_buffers is an actual allocation; effective_cache_size is a planner hint. The two parameters serve two different purposes.

### 11.6. View current values

~~~sql
SHOW effective_cache_size;
SHOW shared_buffers;
~~~

Base the estimate on RAM, shared_buffers, OS cache, competing workloads, and observed memory behavior.

---

## 12. Buffer Replacement and Dirty Pages

shared_buffers is a finite pool. PostgreSQL must decide which pages remain in the pool and which can be replaced.

### 12.1. Buffer mapping

PostgreSQL looks up a block by relation/fork/block identity to find the buffer holding that page.

### 12.2. Pinning

A backend pins a buffer while using it so the page cannot be reused while an operation needs it. A pinned buffer cannot be arbitrarily evicted.

### 12.3. Usage count

PostgreSQL uses usage count metadata to estimate which pages are likely to be accessed again. A clock-sweep mechanism scans the buffer pool to find a suitable candidate.

### 12.4. Dirty buffer

A page modified in memory and not yet written to the relation file is called dirty. A dirty buffer must be handled before its buffer slot can be safely reused.

### 12.5. Background writer

The background writer can write out some dirty buffers before a backend needs a new buffer, helping reduce cases where backends have to write pages themselves in the foreground.

### 12.6. Checkpointer

The checkpointer ensures dirty pages and WAL satisfy checkpoint requirements. Checkpoints can write large volumes of buffers, so monitor write/sync time and storage throughput.

### 12.7. Do not interpret replacement as pure LRU

PostgreSQL uses its own buffer management mechanism with pinning and usage counts. It does not simply evict the least-recently-used page from a pure LRU list.

---

## 13. Detailed Read Path

### 13.1. Query needs a block

The executor needs a heap or index page. PostgreSQL identifies the relation and block number.

### 13.2. Check shared_buffers

If the block is present, the backend uses the page. If not, the buffer manager needs a free buffer or a reusable buffer.

### 13.3. Read via filesystem

PostgreSQL performs I/O on the relation file using the I/O path of the version/build. On the standard path, the OS page cache may return the data.

### 13.4. OS cache hit

There is no physical storage read at that moment, though there is still syscall/OS work and a copy into the shared buffer.

### 13.5. OS cache miss

The kernel sends a request to storage. Wait time can depend on queue depth, latency, network storage, and device cache.

### 13.6. Page placed into shared_buffers

Once read completes, PostgreSQL updates buffer metadata and the query continues processing the page.

### 13.7. Read-ahead and sequential access

The OS/storage can prefetch data when sequential access is detected. PostgreSQL also has I/O mechanisms suited for certain access patterns. As a result, some sequential scans can perform well even with a low cache hit ratio.

---

## 14. Detailed Write Path

### 14.1. Page modified in shared_buffers

UPDATE/INSERT/DELETE can modify heap/index pages in the buffer pool.

### 14.2. WAL record generated

WAL describes the changes needed for crash recovery and replication.

### 14.3. Commit and durability

With typical default synchronous_commit, PostgreSQL waits for local WAL flush per durability policy before confirming commit. Other settings can change when confirmation occurs.

### 14.4. Data pages are not necessarily flushed yet

A transaction can commit while data pages remain dirty in shared_buffers. Crash recovery will use WAL to redo necessary changes.

### 14.5. Writeback

Background writer/checkpointer/backends write dirty pages to files. The OS can keep file pages in the page cache and perform writeback to storage.

### 14.6. Checkpoint sync

Checkpoints must ensure required writes are synced per the durability contract. Storage controllers/devices must honor flush semantics.

### 14.7. Caching does not eliminate durability requirements

Do not disable fsync or full_page_writes just to boost benchmarks. Those settings relate to data safety and recovery.

---

## 15. Checkpoints and shared_buffers Size

Increasing shared_buffers can change the amount of dirty data and how checkpoints generate I/O.

### 15.1. More buffers

A larger pool can hold more pages, but can also accumulate more dirty pages depending on the workload.

### 15.2. Checkpoint pressure

Checkpoints must process dirty pages within a time/cycle limit. If dirty data volume is high, storage is slow, or checkpoint settings are poorly tuned, latency can spike.

### 15.3. Checkpoint completion target

checkpoint_completion_target paces checkpoint writes across the checkpoint interval. This parameter governs write behavior, not a direct way to raise cache hit ratio.

### 15.4. max_wal_size

max_wal_size influences checkpoint scheduling/pressure, but is not a hard limit for all WAL retention and does not replace replication slot/archive planning.

### 15.5. Monitor checkpoint stats

Depending on PostgreSQL version, inspect pg_stat_bgwriter and/or pg_stat_checkpointer. Starting in PostgreSQL 17, checkpoint statistics are separated more clearly than in earlier versions.

### 15.6. Do not raise shared_buffers to fix slow checkpoints

If checkpoints are slow due to low storage throughput, enlarging the buffer pool can make matters worse. Inspect write/sync time, dirty buffers, disk latency, and WAL rate.

---

## 16. Measuring Cache Hit Ratio and Interpreting It Correctly

A common metric is the database-level buffer cache hit ratio.

~~~sql
SELECT
    datname,
    blks_hit,
    blks_read,
    round(
        100.0 * blks_hit / NULLIF(blks_hit + blks_read, 0),
        2
    ) AS shared_buffer_hit_pct,
    stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname IS NOT NULL;
~~~

### 16.1. blks_hit

The number of blocks found in PostgreSQL's shared buffer cache according to database statistics.

### 16.2. blks_read

The number of blocks PostgreSQL had to read into shared buffers. It does not equate to physical reads from the storage device.

### 16.3. Hit ratio is an aggregate

A database with many fast queries and one very slow query can still show a high overall hit ratio. Drill down to tables/queries and latency.

### 16.4. A low hit ratio can be normal

A large sequential scan over non-cache-friendly data can generate many block reads and still be efficient. Analytics workloads typically have different patterns from OLTP.

### 16.5. A high hit ratio does not guarantee good performance

Queries can be slow due to CPU, lock waits, bad plans, memory spills, network, serialization, or application pool waits even if every page is found in shared_buffers.

### 16.6. There is no magic threshold

Do not set a universal target of 99% or 99.9% for every system. Evaluate based on latency SLOs, physical I/O, workload patterns, and capacity.

### 16.7. Counters must be read over time

blks_hit and blks_read are cumulative counters. Take deltas between snapshots and check stats_reset to observe behavior within the observation window.

---

## 17. pg_statio Views

The pg_statio_* views provide block I/O statistics at the table/index/database level.

### 17.1. Table statistics

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
FROM pg_catalog.pg_statio_user_tables
ORDER BY heap_blks_read DESC
LIMIT 20;
~~~

### 17.2. Index statistics

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_blks_read,
    idx_blks_hit
FROM pg_catalog.pg_statio_user_indexes
ORDER BY idx_blks_read DESC
LIMIT 20;
~~~

### 17.3. Interpretation

- heap_blks_hit: heap blocks found in PostgreSQL shared buffers.
- heap_blks_read: heap blocks read into shared buffers.
- idx_blks_hit/idx_blks_read: analogous counters for index blocks.
- toast fields: statistics related to TOAST storage.

### 17.4. Limitations

These counters do not prove a physical device read occurred. A PostgreSQL block read may have been served from the OS cache.

### 17.5. Finding hot objects

Comparing hit/read deltas by table/index helps locate objects with high read counts. Combine with query stats and latency to identify objects actually impacting performance.

---

## 18. pg_stat_io on PostgreSQL 16 and Above

pg_stat_io adds I/O statistics by backend type, object, and context on PostgreSQL 16 and later.

~~~sql
SELECT *
FROM pg_catalog.pg_stat_io;
~~~

### 18.1. Backend type

Shows which backend group performed the I/O, such as client backend, background writer, checkpointer, or other backend types depending on version.

### 18.2. Object/context

Distinguishes the object type and I/O context tracked. Check the schema on your server for exact groupings.

### 18.3. Counters

The view can report reads/writes, bytes, writebacks, extends, hits, evictions, reuses, and fsyncs depending on columns/version.

### 18.4. Timing

Columns such as read_time/write_time/extend_time/fsync_time must be interpreted alongside timing collection settings like track_io_timing. Check pg_settings and version documentation.

### 18.5. Not physical device telemetry

pg_stat_io describes I/O performed by PostgreSQL from the database perspective. It does not replace OS/cloud metrics on device latency, queue depth, throttling, or physical caches.

### 18.6. Version compatibility

Do not run queries referencing pg_stat_io on PostgreSQL prior to 16. Exporters should check the server version and only enable compatible collectors.

---

## 19. EXPLAIN (ANALYZE, BUFFERS)

EXPLAIN with BUFFERS helps inspect buffer activity for a specific query.

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM public.orders
WHERE customer_id = 42;
~~~

### 19.1. shared hit

Number of shared buffers found in PostgreSQL's buffer pool.

### 19.2. shared read

Number of shared buffers read into the pool. Do not assume all of those blocks were read from physical disk.

### 19.3. shared dirtied

Number of shared buffers marked dirty by the query.

### 19.4. shared written

Number of shared buffers written out during query execution per EXPLAIN/version semantics. Do not treat this as the query's total I/O if background activity is present.

### 19.5. local/temp buffers

Local buffers relate to temporary tables; temp buffers in EXPLAIN can indicate temporary buffer file/block activity depending on operation type. Read the output in the context of your version.

### 19.6. EXPLAIN ANALYZE executes the query

For SELECT, the query actually runs and consumes resources. For DML, side effects can occur. Run only in an appropriate environment; transactions and rollback may be used in safe cases, but do not assume rollback eliminates every external side effect.

### 19.7. Compare under identical conditions

Run multiple times, maintain equivalent workload, and record cache state. The first cold-ish run and subsequent warm-cache runs can differ.

---

## 20. pg_buffercache to Inspect Shared Buffer Contents

The pg_buffercache extension allows observing which pages are currently in shared_buffers.

### 20.1. Install the extension

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_buffercache;
~~~

The extension must be installed/permitted per environment. Access to the view/function may be restricted.

### 20.2. Inspect buffer distribution by fork

~~~sql
SELECT
    CASE
        WHEN relforknumber = 0 THEN 'main'
        WHEN relforknumber = 1 THEN 'fsm'
        WHEN relforknumber = 2 THEN 'vm'
        WHEN relforknumber = 3 THEN 'init'
        ELSE 'other'
    END AS fork_name,
    count(*) AS buffers
FROM pg_catalog.pg_buffercache
WHERE reldatabase = (
    SELECT oid
    FROM pg_catalog.pg_database
    WHERE datname = current_database()
)
GROUP BY relforknumber
ORDER BY buffers DESC;
~~~

### 20.3. Count buffers by relation

You can join pg_buffercache with pg_class/pg_namespace to see which relations occupy buffer pages. Handle relation mapping carefully and treat it strictly as a snapshot.

### 20.4. It is a snapshot, not history

pg_buffercache shows the buffer pool contents at the instant of the query. To observe trends, scrape sparingly and account for overhead.

### 20.5. Do not manually pin every table

A relation having many pages in cache does not by itself mean it must be pinned. Buffer replacement still needs to manage the pool for the system-wide workload.

---

## 21. pg_prewarm and Cache Warm-Up

pg_prewarm can load relation blocks into cache before the main workload begins.

### 21.1. Install the extension

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_prewarm;
~~~

### 21.2. Prewarm into shared buffers

~~~sql
SELECT pg_prewarm('public.orders', 'buffer');
~~~

### 21.3. Reading through the OS cache

Modes such as read or prefetch have different semantics and depend on version/platform. Read the extension documentation for your version before running.

### 21.4. When is it useful?

- After a restart, warming up select hot relations.
- Before a known batch window.
- Benchmarks deliberately requiring a warm cache.
- Reducing latency spikes after planned maintenance/restarts.

### 21.5. Risks

Prewarming a large table can evict other useful pages from cache, create an I/O burst, and increase startup load. Do not blindly prewarm the entire database.

### 21.6. Warm cache is not durability

Cache contents can be lost on restart or evicted. Do not use prewarm as a substitute for backups, WAL, or durability.

---

## 22. Factors Determining the Working Set

The working set is the subset of data frequently accessed by the workload over a given period.

### 22.1. Database size does not equal working set

A 2 TB database may have a 20 GB hot set; a 100 GB database may randomly access nearly all of its data.

### 22.2. Access frequency

Frequently accessed pages are more valuable to retain in cache than pages read once, though large scans can still affect buffer residency.

### 22.3. Index working set

Index root/upper pages and hot index leaf pages can be accessed continuously. Index size and access patterns affect cache requirements.

### 22.4. Data skew

A few tenants or accounts can generate most traffic. Workload averages hide hot keys.

### 22.5. Time-of-day

Batch jobs, reports, and business peaks can shift the working set by hour of day.

### 22.6. Churn

If the workload continually accesses new pages, cache turnover is high. Increasing shared_buffers may help if the working set is only slightly larger than the pool, but will not save continuous scans over datasets many times larger than RAM.

---

## 23. Sequential Scans and Cache Behavior

Sequential scans can read many pages within a short time.

### 23.1. Large scans are not automatically bugs

If a query needs most of a table, a sequential scan can be cheaper than an index scan. An efficient sequential read can leverage read-ahead and storage throughput.

### 23.2. Buffer ring strategy

PostgreSQL has buffer access strategies for certain large scans to avoid evicting the entire hot working set from shared_buffers. Implementation details vary by version.

### 23.3. Hit ratio may drop after a batch scan

A batch scan can increase blks_read, lowering the aggregate hit ratio. That does not necessarily slow down interactive workloads if hot pages remain cached.

### 23.4. Measure per query/table

Use pg_stat_statements, pg_statio_user_tables, and EXPLAIN (BUFFERS) to identify which scans generate heavy reads.

### 23.5. Do not tune shared_buffers to fix a poor query plan

If the planner chooses a sequential scan due to statistics/index/selectivity issues, enlarging the cache may not fix the root cause. Inspect the plan and cardinality estimates.

---

## 24. Sizing by Workload

### 24.1. OLTP with a hot set

Transactional workloads frequently access a recurring set of table/index pages. A shared_buffers large enough to hold the hot set can reduce latency and I/O.

### 24.2. Analytics

Analytics workloads can read large volumes of data that regularly exceed cache. Storage throughput, parallelism, and query plans can matter more than endlessly enlarging the buffer pool.

### 24.3. Mixed workload

Interactive queries need low latency while batches/reports read large volumes. Consider buffer churn, query scheduling, resource groups (if available), and storage capacity.

### 24.4. Read-heavy workload

Cache hits can be high if the hot set is stable. Even so, the OS page cache can also serve pages evicted from shared_buffers.

### 24.5. Write-heavy workload

Focus on dirty buffer pressure, WAL throughput, checkpoint behavior, storage write latency, and replication. Larger shared_buffers does not necessarily improve commit latency.

### 24.6. Multiple PostgreSQL instances on one host

Each instance has its own shared_buffers. Sum the allocations across all instances and leave RAM for the OS, page cache, and other services.

---

## 25. Systematic shared_buffers Tuning Workflow

Do not change shared_buffers solely based on a cache hit ratio.

### Step 1: Record the baseline

Collect:
- Current shared_buffers.
- RAM and memory limits.
- Application latency p50/p95/p99.
- Throughput and concurrency.
- blks_hit/blks_read deltas.
- pg_stat_io or OS I/O metrics.
- CPU, memory, swap, and disk latency.
- Checkpoint write/sync behavior.
- Query mix and top statements.

### Step 2: Identify the bottleneck

If latency is mostly due to lock waits or pool waits, shared_buffers may not help. If storage reads rise alongside query latency and the working set is cacheable, testing has a stronger basis.

### Step 3: Choose a step change

Increase/decrease in controlled increments. Do not change shared_buffers, work_mem, effective_cache_size, checkpoint settings, and query plans simultaneously if you want to know which change produced the result.

### Step 4: Check memory headroom

Estimate peak backend/query memory, maintenance, OS cache, and other services. Do not push the host near OOM.

### Step 5: Apply the configuration

shared_buffers is a parameter that requires restarting PostgreSQL to take effect. Prepare a maintenance plan and confirm restart/rollback procedures.

### Step 6: Warm up consistently

After a restart, caches are generally colder. Do not compare metrics immediately after a restart with a system running steadily for hours without explicitly noting cache state.

### Step 7: Run an equivalent workload

Use the same dataset, concurrency, request mix, and measurement duration. Ideally run multiple trials and allow enough time for caches to stabilize.

### Step 8: Compare results

Compare p95/p99, throughput, OS physical I/O, pg buffer reads, CPU, memory pressure, swap, checkpoints, and storage latency.

### Step 9: Choose the best level for the whole system

Choose the configuration that balances user latency, throughput, durability, OS headroom, and cost—not just maximizing the cache hit ratio.

### Step 10: Document the decision

Save the configuration, version, hardware, workload, test method, results, and rollback value so you have a reliable baseline next time.

---

## 26. Configuring shared_buffers

### 26.1. Check current values

~~~sql
SHOW shared_buffers;

SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_catalog.pg_settings
WHERE name IN (
    'shared_buffers',
    'effective_cache_size',
    'work_mem',
    'maintenance_work_mem',
    'temp_buffers',
    'wal_buffers'
)
ORDER BY name;
~~~

### 26.2. Edit in postgresql.conf

Example:

~~~conf
shared_buffers = 4GB
effective_cache_size = 12GB
~~~

Values are illustrative for a host with suitable RAM. Do not copy verbatim into production.

### 26.3. Check context

~~~sql
SELECT name, setting, context, pending_restart
FROM pg_catalog.pg_settings
WHERE name = 'shared_buffers';
~~~

Context generally indicates whether a parameter requires a restart or can be reloaded/set at runtime.

### 26.4. Restart

After changing shared_buffers, PostgreSQL must be restarted. Use your environment's service manager or operational procedure. After restart, confirm the effective value with SHOW.

### 26.5. Do not confuse reload with restart

Reload re-reads configurations that can change at runtime. It does not recreate the shared memory allocation of shared_buffers.

### 26.6. Check logs and memory

After restart, verify PostgreSQL logs, startup success, shared memory allocation, and OS/container memory headroom.

---

## 27. Observing the OS Page Cache and Memory Pressure

PostgreSQL metrics alone cannot describe the entire page cache.

### 27.1. Linux

Common sources:
- /proc/meminfo: MemAvailable, Cached, Buffers, SReclaimable.
- vmstat: memory, paging, swap, and run queue.
- free: memory snapshot.
- iostat: device utilization, throughput, queue, and latency.
- cgroup memory files: container limits and usage.
- Cloud metrics: volume IOPS, throughput, latency, and throttling.

Examples:

~~~bash
free -h
vmstat 1
iostat -xz 1
~~~

Commands must be run on the host according to operational permissions.

### 27.2. MemAvailable matters more than free alone

Linux can use free RAM for caching. Low free memory does not necessarily indicate memory pressure if MemAvailable remains sufficient and reclaim operates normally.

### 27.3. Swap activity

Continuous swap-in/swap-out alongside rising latency is a sign that requires investigation. Non-zero swap used does not always mean thrashing; inspect activity over time.

### 27.4. Windows

Performance Monitor/Resource Monitor can be used to observe available memory, cache bytes, page faults, disk reads/writes, latency, and process memory.

### 27.5. Containers

Inspect cgroup memory usage/limit, memory events, and OOM counters. The host may still have plenty of RAM while the container has hit its limit.

### 27.6. Do not simply sum RSS

Multiple PostgreSQL processes map the same shared memory. Summing RSS across every process can count the same shared pages multiple times. Use PSS/cgroup/container metrics appropriately.

---

## 28. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| shared_buffers is all of PostgreSQL's RAM | There are backends, work_mem, maintenance, WAL, and many other areas |
| OS page cache is unnecessary when shared_buffers exists | PostgreSQL normally relies on both layers |
| blks_read is always a physical disk read | It may be served from the OS page cache |
| A 99% cache hit ratio is always good | Does not fully reflect latency, tail behavior, or workload |
| A low cache hit ratio is always bad | Sequential scans and analytics can legitimately generate many reads |
| Increasing shared_buffers always makes queries faster | Has diminishing returns and memory pressure |
| Large shared_buffers replaces the OS cache | The two layers have different policies and scopes |
| effective_cache_size allocates RAM | It is a planner estimate |
| work_mem is a server-wide memory pool | It can be allocated multiple times per operation/session |
| COMMIT writes every table page to disk | Commit usually waits for WAL flush; data pages may remain dirty |
| An OS cache hit has zero cost | Still involves syscalls, copying, and kernel work |
| A shared buffer miss means storage must be read | The OS page cache may serve it |
| Database size equals working set | Working set depends on access patterns |
| Prewarm keeps the cache warm permanently | Pages can be evicted or lost on restart |
| Restart and reload have the same effect | shared_buffers requires a restart |
| Rising cache hit ratio proves tuning succeeded | Must compare latency, throughput, physical I/O, and memory |
| Plenty of free disk space means I/O cannot be slow | Latency/queue/IOPS can saturate before capacity |
| Summing RSS gives exact PostgreSQL memory | Shared mappings can be double-counted |
| Disabling fsync makes caching safely faster | Can compromise durability |
| Larger shared_buffers always reduces checkpoint work | Dirty page volume and writeback pressure must still be measured |

---

## 29. Lab 1: Observing shared_buffers and Database Counters

Use a dedicated database or test environment for the lab.

### 29.1. Check configuration

~~~sql
SHOW shared_buffers;
SHOW block_size;
SHOW effective_cache_size;
~~~

Record the results and server version.

### 29.2. Take a counter snapshot

~~~sql
SELECT
    datname,
    blks_hit,
    blks_read,
    stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname = current_database();
~~~

### 29.3. Create a test table to read

~~~sql
CREATE TABLE IF NOT EXISTS public.cache_lab (
    id BIGINT PRIMARY KEY,
    payload TEXT NOT NULL
);

INSERT INTO public.cache_lab(id, payload)
SELECT g, repeat('x', 200)
FROM generate_series(1, 200000) AS g
ON CONFLICT (id) DO NOTHING;

ANALYZE public.cache_lab;
~~~

### 29.4. Run a read query

~~~sql
SELECT sum(length(payload))
FROM public.cache_lab;
~~~

### 29.5. Take a second snapshot

Re-run the counter query. Calculate the delta for blks_hit and blks_read. Repeated queries may produce more hits if the pages remain in shared_buffers.

### 29.6. Interpretation

Do not infer physical disk reads from blks_read. OS/storage metrics are required to know whether the device actually performed reads.

---

## 30. Lab 2: Distinguishing Shared Buffer Misses from Physical I/O

### 30.1. Preparation

Use a table larger than shared_buffers in the lab if space permits. Record the dataset size and host RAM.

### 30.2. Capture PostgreSQL counters

Record pg_stat_database and pg_statio_user_tables before running the query.

### 30.3. Capture OS metrics

On Linux, record device read bytes/operations/latency and page cache/memory metrics. Do not drop OS caches on production.

### 30.4. Run the workload

Read a set of pages larger than the buffer pool or scan the table in a repeatable way.

### 30.5. Compare

If blks_read rises while physical device reads do not rise proportionally, the OS page cache may have served most of the block reads.

### 30.6. Limitations

Storage controllers, hypervisors, and cloud providers may have their own caches. Distinguishing OS cache hits from physical media accesses requires telemetry at the appropriate layer.

---

## 31. Lab 3: Using EXPLAIN (ANALYZE, BUFFERS)

### 31.1. Run a filtered query

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM public.cache_lab
WHERE id BETWEEN 10000 AND 11000;
~~~

### 31.2. Record buffer counts

Record shared hit, shared read, dirtied, and written if present. Save the query plan and execution time.

### 31.3. Re-run

Re-run the same query under similar conditions. Compare hit/read counts and latency.

### 31.4. Try a sequential scan

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sum(length(payload))
FROM public.cache_lab;
~~~

### 31.5. Interpretation

A buffer read means a page was brought into shared buffers. It does not confirm a physical storage read. Combine with OS metrics.

### 31.6. Safety

Do not run EXPLAIN ANALYZE on production DML without controlling side effects and load.

---

## 32. Lab 4: pg_buffercache and pg_prewarm

### 32.1. Install extensions in the lab

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_buffercache;
CREATE EXTENSION IF NOT EXISTS pg_prewarm;
~~~

### 32.2. Observe buffer residency

~~~sql
SELECT
    count(*) AS buffers_for_cache_lab
FROM pg_catalog.pg_buffercache AS b
JOIN pg_catalog.pg_class AS c
    ON c.relfilenode = b.relfilenode
WHERE c.relname = 'cache_lab';
~~~

This illustrative query should be refined if schemas, tablespaces, or relation mappings are complex. In practice, join full database/tablespace/relation identity to avoid filenode collisions.

### 32.3. Prewarm the table

~~~sql
SELECT pg_prewarm('public.cache_lab', 'buffer');
~~~

### 32.4. Run a query after prewarm

Capture EXPLAIN BUFFERS and database counters to observe the changes.

### 32.5. Observe impact on other workloads

Prewarming a large table can evict other pages. Compare hot query latency before/after if the lab has multiple relations.

### 32.6. Conclusion

pg_buffercache is a snapshot of shared_buffers; pg_prewarm proactively reads relation pages. Neither creates persistent caching nor replaces backups.

---

## 33. Lab 5: Controlled Sizing Experiment

This lab requires a dedicated host/database and restart privileges. Do not modify production just to experiment.

### 33.1. Record baseline

Save shared_buffers, effective_cache_size, RAM, container limit, CPU, memory pressure, disk I/O, query mix, and latency percentiles.

### 33.2. Choose a repeatable workload

Use the same dataset, concurrency, request mix, and duration. Select a workload slice representative of production.

### 33.3. Change one parameter

Pick a new shared_buffers level within your memory budget. Do not change work_mem and checkpoint settings at the same time.

### 33.4. Restart and verify

Restart PostgreSQL according to your runbook. Check SHOW shared_buffers and startup logs.

### 33.5. Warm-up

Run a controlled warm-up workload. Record the cold-cache phase and steady state separately.

### 33.6. Measure

Compare p50/p95/p99, throughput, blks_hit/read deltas, physical I/O, CPU, MemAvailable, swap, checkpoint time, and disk latency.

### 33.7. Evaluate

Only keep the change if improvements are repeatable and memory headroom remains safe. If results are unfavorable, roll back to the previous value.

---

## 34. Practice Exercises

### Exercise 1 — Definition

Explain shared_buffers in database engine terms. What kind of data does it cache?

### Exercise 2 — Two cache layers

Diagram the read path through shared_buffers, the OS page cache, and the storage device.

### Exercise 3 — Shared hit

What happens when PostgreSQL finds a block in shared_buffers?

### Exercise 4 — OS cache hit

Why can blks_read increase without physical disk reads increasing?

### Exercise 5 — Cache miss

Describe the path when a block is absent from both cache layers.

### Exercise 6 — Double caching

Why can a page occupy RAM in both shared_buffers and the OS page cache? State the trade-off.

### Exercise 7 — Dirty buffers

Explain dirty pages, buffer pins, and why a dirty buffer cannot be immediately reused.

### Exercise 8 — WAL ordering

Why must WAL be flushed before the corresponding data page is written durably?

### Exercise 9 — Commit path

A transaction commits while a data page is still dirty. Why can the data still be recovered after a crash?

### Exercise 10 — Memory areas

Distinguish shared_buffers, work_mem, temp_buffers, wal_buffers, and maintenance_work_mem.

### Exercise 11 — effective_cache_size

Why does setting effective_cache_size = 32GB not allocate 32GB of RAM?

### Exercise 12 — Sizing

A dedicated host has 64GB RAM. Calculate the 25% starting point and list the memory components that need headroom.

### Exercise 13 — Containers

A host has 128GB RAM, but the PostgreSQL container limit is 16GB. Why shouldn't shared_buffers be sized based on host RAM?

### Exercise 14 — Cache hit ratio

Calculate the shared buffer hit ratio from blks_hit=9,000,000 and blks_read=1,000,000. State the limitations of this result.

### Exercise 15 — Low hit ratio

An analytics system has a 65% hit ratio, yet latency meets its SLO. Why is increasing shared_buffers not necessarily required?

### Exercise 16 — High hit ratio

An API's p99 spikes despite a 99.8% hit ratio. List causes other than cache misses.

### Exercise 17 — pg_statio

Write a query to find the tables with the highest heap_blks_read and explain why this is not yet a physical I/O ranking.

### Exercise 18 — pg_stat_io

State the role of pg_stat_io and the PostgreSQL version that introduced this view.

### Exercise 19 — EXPLAIN BUFFERS

Explain shared hit, shared read, dirtied, and written in EXPLAIN.

### Exercise 20 — pg_buffercache

When is the pg_buffercache extension useful? Why can't a snapshot replace time-series metrics?

### Exercise 21 — pg_prewarm

Give one useful case for pg_prewarm and one risk of prewarming a large relation.

### Exercise 22 — Sequential scan

Why can a sequential scan lower the hit ratio and still be a good query plan?

### Exercise 23 — Checkpoints

Explain the relationship between dirty buffers, checkpoints, and storage write throughput.

### Exercise 24 — Tuning

Design a benchmark comparing shared_buffers at 4GB vs. 8GB. Which conditions must be held constant?

### Exercise 25 — Restart

Why does changing shared_buffers require a restart instead of a reload?

### Exercise 26 — Memory pressure

A host has low MemAvailable and rising swap-in. Propose investigation steps before increasing shared_buffers.

### Exercise 27 — Backend concurrency

Why can work_mem produce much higher memory usage than expected when many queries/parallel workers run concurrently?

### Exercise 28 — Multiple instances

One host runs three PostgreSQL instances. Budget total shared_buffers and OS cache headroom.

### Exercise 29 — OS metrics

List the Linux/Windows metrics to inspect to understand filesystem page cache and physical I/O.

### Exercise 30 — Storage cache

A cloud volume has its own read cache. Why does an OS read not prove the physical media was accessed?

### Exercise 31 — Working set

A database is 1TB, while the hot set is 30GB. How does this affect sizing?

### Exercise 32 — Write-heavy workload

shared_buffers is increased, yet commit latency does not drop. Which metrics should be examined next?

### Exercise 33 — Checkpoint regression

After increasing shared_buffers, checkpoint duration increases. Propose how to identify dirty page pressure and storage bottlenecks.

### Exercise 34 — Planner estimate

Which plan might the planner choose if effective_cache_size is set too high, and why?

### Exercise 35 — Cache warm-up

Design a method to measure cold-cache and warm-cache performance after a restart without dropping OS caches on production.

### Exercise 36 — Stats reset

An exporter calculates the cache hit ratio incorrectly after a stats reset. Explain how to store snapshots and handle resets.

### Exercise 37 — Buffer churn

A batch sequential scan slows down hot API queries. Propose metrics to inspect and an experiment to test.

### Exercise 38 — Ineffective cache tuning

Latency is primarily lock wait. Why does increasing shared_buffers fail to solve the root cause?

### Exercise 39 — Capacity review

A server has 32GB RAM, 20GB shared_buffers, 400 connections, and 64MB work_mem. Analyze the memory risks that must be evaluated.

### Exercise 40 — End-to-end tuning

A PostgreSQL OLTP system has 800ms p99, 99.5% hit ratio, 35% CPU, rising disk read latency, low MemAvailable, and swap activity appearing. Design an investigation sequence covering the two cache layers, working set, memory budget, I/O, query plans, and propose a controlled shared_buffers benchmark.

---

## 35. shared_buffers and OS Cache Operations Checklist

| Item | What to Verify |
| --- | --- |
| PostgreSQL version | Major version and build block size |
| shared_buffers | Current value and memory allocation |
| OS/container limit | Actual RAM PostgreSQL is permitted to use |
| OS page cache | MemAvailable/cache behavior |
| effective_cache_size | Reasonable planner estimate |
| work_mem | Peak concurrent sort/hash memory |
| temp_buffers | Temporary table usage |
| wal_buffers | WAL buffer configuration |
| Backend concurrency | Number of sessions/parallel workers |
| Memory pressure | Swap, reclaim, OOM events |
| shared buffer hit/read | Workload-aligned deltas |
| Physical device reads | OS/cloud storage metrics |
| pg_statio | Hot tables/indexes |
| pg_stat_io | Supported in current version? |
| EXPLAIN BUFFERS | Query-level buffer activity |
| pg_buffercache | Snapshot when investigating |
| pg_prewarm | Intentional and workload-scoped |
| Dirty buffers | Writeback/checkpoint pressure |
| Checkpoint metrics | Write/sync time and frequency |
| WAL rate | Bytes/s and archive/replication load |
| Disk latency | Read/write latency and queue |
| Working set | Size and access pattern |
| Sequential scans | Any large scans/churn? |
| Query latency | p50/p95/p99 |
| Throughput | Is workload comparable? |
| Tuning experiment | Change one variable at a time |
| Restart plan | Maintenance/rollback plan in place |
| Warm-up | Cold/warm phases clearly recorded |
| Restore safety | Durability settings not disabled |
| Decision record | Save baseline, results, and config |

## Conclusion

shared_buffers is the page cache managed by PostgreSQL, while the OS page cache is the file cache managed by the kernel. When PostgreSQL does not find a block in shared_buffers, the operating system may still return that block from RAM. Therefore, a PostgreSQL buffer read does not equal a physical disk read, and the cache hit ratio cannot replace metrics for storage, latency, and memory pressure.

Key principles to remember:

1. **shared_buffers caches database pages.** It is shared across PostgreSQL backends and has mechanisms for buffer management, pinning, dirty pages, and replacement.
2. **The OS page cache is an independent layer.** It can serve a PostgreSQL shared-buffer miss without reading the storage device.
3. **A page can exist in both layers.** Double caching consumes RAM, yet allows PostgreSQL and the kernel to manage caches for their respective purposes.
4. **blks_read does not equal physical reads.** Combine pg_stat_database/pg_statio with OS and storage telemetry.
5. **COMMIT usually waits for WAL flush.** Data pages can remain dirty in shared_buffers and be written later by checkpoints/writeback.
6. **effective_cache_size is only a planner estimate.** It allocates no RAM and does not alter shared_buffers.
7. **25% of RAM is a starting point, not a rule.** Evaluate working set, OS, container limits, concurrency, and workload.
8. **The memory budget must include query memory.** work_mem can be used multiple times by one query and across many sessions.
9. **Hit ratio is not an SLO.** A system with a low hit ratio can still be fast; a high hit ratio can still be slow due to locks, CPU, or I/O.
10. **Measure from multiple angles.** pg_stat_database, pg_statio, pg_stat_io, EXPLAIN BUFFERS, pg_buffercache, and OS metrics complement one another.
11. **Tuning requires controlled benchmarks.** Keep the workload equivalent, separate cold/warm caches, and change one parameter at a time.
12. **Never trade durability for speed.** Keep WAL, fsync, and recovery settings aligned with data requirements.

A good shared_buffers configuration is not the one that consumes the largest share of RAM. It is the configuration that retains the useful working set, coordinates well with the OS page cache, leaves enough memory for queries and maintenance, and improves latency/throughput without creating memory pressure or checkpoint bottlenecks.
