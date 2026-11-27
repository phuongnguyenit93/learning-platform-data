# Buffer Pool Hit/Miss, Dirty Pages, and Flush Activity

InnoDB uses the **buffer pool** as a memory cache for data and index pages read from tablespaces. When a query needs a page already in the buffer pool, the engine can read it directly from RAM; if the page is absent, InnoDB must load it from the storage layer into memory. When a transaction modifies a page, that page becomes a **dirty page** and must eventually be written to the data file via flushing.

Evaluating the buffer pool is not just about looking at a high hit ratio. A DBA must monitor logical reads, physical reads, dirty page counts, flush rates, free buffers, waits for free pages, and checkpoint progress together. This lesson is part of MySQL **System Performance**, focusing on how to read these metrics, understand LRU/flush lists, and tune page cleaner activity for your workload.

## 1. Where Does the Buffer Pool Sit in the Query Path?

InnoDB stores clustered indexes, secondary indexes, and data pages in tablespaces. The buffer pool holds actively used page copies in RAM to reduce storage access.

```text
SQL statement
    |
    v
Optimizer chooses access path
    |
    v
InnoDB needs an index/data page
    |
    v
Is page in buffer pool?
    |                         |
   Yes                        No
    |                         |
    v                         v
Read page in RAM         Read page from storage
    |                         |
    +------------+------------+
                 |
                 v
           Process record
                 |
        UPDATE / INSERT / DELETE
                 |
                 v
           Page becomes dirty
                 |
                 v
     Page cleaner writes page to data file
```

The buffer pool is not the sole durable storage location. When the server stops, pages in RAM do not replace data files and redo logs. InnoDB uses write-ahead logging to ensure required redo information is written before the corresponding dirty page is flushed to its final location in the data file.

## 2. Logical Reads, Physical Reads, Hits, and Misses

Two fundamental counters:

- `Innodb_buffer_pool_read_requests`: number of logical page read requests from the buffer pool.
- `Innodb_buffer_pool_reads`: number of times InnoDB had to read a page into the buffer pool because the needed page was not already in the pool.

Check them:

```sql
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_read%';
```

In the output, `Innodb_buffer_pool_read_requests` is usually much larger than `Innodb_buffer_pool_reads` when the working set is well cached. However, these are cumulative counters; compute differences over a defined time interval instead of comparing absolute totals after days of uptime.

### Estimating Buffer Pool Hit Ratio

You can estimate the proportion of logical reads served without reading a new page from storage:

\[
\text{Hit ratio} \approx
\left(1 - \frac{\Delta\text{physical reads}}
{\Delta\text{logical read requests}}\right) \times 100\%
\]

For example, in 5 minutes:

- Logical read requests increase by 10,000,000.
- Physical reads increase by 50,000.

Then:

\[
\left(1 - \frac{50,000}{10,000,000}\right) \times 100
= 99.5\%
\]

This is a high-level metric. It does not mean 99.5% of queries are fast or that storage is not a bottleneck. One query can read millions of pages even when most pages are cached; a small number of physical reads on a latency-sensitive query path can still drive p99 latency up sharply.

### Using Deltas Instead of Cumulative Counters

Capture metrics at two points separated by a representative interval:

```sql
SELECT
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.global_status
WHERE VARIABLE_NAME IN (
    'Innodb_buffer_pool_read_requests',
    'Innodb_buffer_pool_reads'
);
```

Record the T1 result, wait for the measurement window, and run it again at T2. Compute the delta for each variable. If `delta read_requests` equals 0, do not compute the hit ratio for that window. If the server restarted or status counters were reset between T1 and T2, the delta calculation is no longer valid.

`Innodb_buffer_pool_reads` is the number of pages InnoDB had to read into the buffer pool; it is not the number of missed `SELECT` statements and does not necessarily equal the number of times physical hardware platters/flash were accessed. OS caches, storage caches, and read-ahead can affect the actual I/O path.

## 3. Important Buffer Pool Counters

Retrieve a common group of status counters:

```sql
SHOW GLOBAL STATUS WHERE Variable_name IN (
    'Innodb_buffer_pool_read_requests',
    'Innodb_buffer_pool_reads',
    'Innodb_buffer_pool_pages_data',
    'Innodb_buffer_pool_pages_dirty',
    'Innodb_buffer_pool_pages_free',
    'Innodb_buffer_pool_pages_total',
    'Innodb_buffer_pool_pages_flushed',
    'Innodb_buffer_pool_wait_free',
    'Innodb_buffer_pool_read_ahead',
    'Innodb_buffer_pool_read_ahead_evicted',
    'Innodb_buffer_pool_pages_made_young',
    'Innodb_buffer_pool_pages_not_made_young'
);
```

| Counter | How to Interpret |
| --- | --- |
| `Innodb_buffer_pool_read_requests` | Logical read requests; rapid growth is normal under read-heavy workloads. |
| `Innodb_buffer_pool_reads` | Pages read into the buffer pool because they were absent; inspect delta and correlate with latency/I/O. |
| `Innodb_buffer_pool_pages_data` | Number of data pages currently in the buffer pool. |
| `Innodb_buffer_pool_pages_dirty` | Number of modified pages not yet flushed to data files. |
| `Innodb_buffer_pool_pages_free` | Number of free page frames available for allocation. |
| `Innodb_buffer_pool_pages_total` | Total page frames in the buffer pool. |
| `Innodb_buffer_pool_pages_flushed` | Number of flushed pages; use delta to compute flush rate. |
| `Innodb_buffer_pool_wait_free` | Number of times InnoDB had to wait for a free page; steady growth may indicate allocation/flush pressure. |
| `Innodb_buffer_pool_read_ahead` | Number of pages prefetched into the buffer pool. |
| `Innodb_buffer_pool_read_ahead_evicted` | Prefetched pages evicted from the pool before being accessed; high values may suggest unhelpful read-ahead. |
| `Innodb_buffer_pool_pages_made_young` | Number of pages moved to the young sublist of the LRU. |
| `Innodb_buffer_pool_pages_not_made_young` | Number of pages not promoted to the young sublist under LRU policy. |

Counter names and granularity may vary by version. Before building dashboards, verify the actual variable list on your server.

## 4. LRU: Which Pages Are Kept?

The buffer pool manages pages with an LRU (Least Recently Used) list divided into old and young sublists. Accessed pages can be promoted to the young sublist if they meet promotion rules; less-used pages gradually move toward the tail of the list and can be evicted when space is needed.

Splitting into old/young sublists helps prevent a single large table scan from pushing the entire hot working set out of the buffer pool. Pages freshly read by a scan can be placed in the old sublist and promoted to young only when there is qualifying evidence of reuse.

Key concepts:

- **Young pages:** the hotter portion of the LRU, typically containing recently accessed pages that qualified for promotion.
- **Old pages:** the portion of the LRU used to isolate newly read or less-hot pages, limiting scan pollution.
- **Page eviction:** removing a page from the buffer pool to free a frame. If the page is dirty, InnoDB must flush it before reusing the frame.
- **Read-ahead:** prefetching pages that InnoDB predicts a query will soon need, based on sequential access patterns or index ranges.

Do not conclude the buffer pool is too small simply because the young/old ratio shifts. Examine `read_ahead_evicted`, physical reads, `wait_free`, and workload latency together.

### Monitoring Page Distribution by Schema/Table

The `sys` schema provides views to inspect pages currently in the buffer pool by schema or table, if installed:

```sql
SELECT *
FROM sys.innodb_buffer_stats_by_schema
ORDER BY allocated DESC;

SELECT *
FROM sys.innodb_buffer_stats_by_table
ORDER BY allocated DESC
LIMIT 20;
```

These views are useful for identifying which schema or table occupies the buffer pool. They describe pages currently cached at the time of observation, not the full table size on disk. Check column names with `DESCRIBE` if the `sys` schema version differs.

## 5. What Is a Dirty Page?

When InnoDB modifies a page's contents in the buffer pool, the page is marked dirty. A dirty page holds newer data than the corresponding page in the data file. It must be flushed to storage before InnoDB can reuse that frame as a clean page.

Operations that can create dirty pages:

- `INSERT`: adds records and modifies associated data/index pages.
- `UPDATE`: modifies records, potentially changing multiple pages and indexes.
- `DELETE`: marks records as deleted and updates index structures.
- Certain internal InnoDB operations: metadata/page changes for storage management.

A dirty page does not imply an uncommitted transaction. A committed transaction can still have dirty pages not yet flushed; the redo log enables InnoDB to recover those changes if a crash occurs before the pages are written to data files.

Conversely, an uncommitted transaction may also have dirtied pages in the buffer pool. During crash recovery, redo can replay needed changes and then undo uncommitted transactions. Therefore, commit state cannot be inferred solely from whether a page has been flushed.

### Dirty Page Ratio

Estimate the dirty page ratio against total page frames:

\[
\text{Dirty page ratio} =
\frac{\text{Innodb\_buffer\_pool\_pages\_dirty}}
{\text{Innodb\_buffer\_pool\_pages\_total}} \times 100\%
\]

For example, 8,000 dirty pages out of 100,000 page frames gives a ratio of 8%. This is an instantaneous ratio, not an hourly average dirty page ratio. Observe the trend and compare against configured thresholds.

## 6. Why Must InnoDB Flush Dirty Pages?

Flushing dirty pages serves several goals:

1. **Freeing frames:** when a new page frame is needed and the pool lacks clean pages, InnoDB must find and flush suitable dirty pages.
2. **Advancing checkpoints:** checkpoints can advance past redo changes only once the older required pages have been written to data files.
3. **Keeping redo log space available:** if the checkpoint falls too far behind the current LSN, redo space fills up and creates log write pressure.
4. **Reducing shutdown/recovery work:** steady background flushing bounds the amount of dirty pages to process, though crash recovery still relies on redo/undo.

InnoDB does not wait until the buffer pool is full to flush. Page cleaners run in the background, coordinating the flush list and LRU list to maintain clean pages and advance checkpoints.

## 7. Flush List, LRU Flush, and Checkpoint

InnoDB has different flushing mechanisms:

- **Flush list:** holds dirty pages ordered by modification LSN. Flushing the oldest pages advances the checkpoint.
- **LRU list:** when a free frame is needed, InnoDB looks at the less-hot end. If the chosen page is dirty, it must be flushed before the frame can be freed.
- **Single-page flush:** an individual page may be flushed when necessary; pending counts and related activity appear in InnoDB status.

A checkpoint is the redo point prior to which all necessary modified pages have been written to data files. As old dirty pages are flushed, the checkpoint advances and frees reusable redo log space.

### Viewing Checkpoints and Flushes in InnoDB Status

```sql
SHOW ENGINE INNODB STATUS\G
```

In the `BUFFER POOL AND MEMORY` section, pay attention to:

- `Buffer pool size`: total page frames.
- `Free buffers`: currently free frames.
- `Database pages`: data/index pages in the pool.
- `Modified db pages`: dirty pages.
- `Pending reads`: pending page reads.
- `Pending writes: LRU`, `flush list`, `single page`: pending writes by category.
- `Pages made young` and `not young`: LRU promotion statistics.

In the `LOG` section, note these markers:

- `Log sequence number`: current LSN.
- `Log flushed up to`: position to which redo has been flushed.
- `Last checkpoint at`: LSN of the latest checkpoint.
- `Pending log flushes` and `pending checkpoint writes`: pending log/checkpoint work.

The gap between the current LSN and the checkpoint LSN reflects how much redo has not yet been passed by a checkpoint. Read this alongside redo log capacity, write rate, and flush rate; do not judge from a single snapshot.

## 8. Page Cleaners and Adaptive Flushing

Page cleaners are background threads responsible for flushing dirty pages. InnoDB can adjust how many pages to flush based on dirty page levels, redo generation rate, and checkpoint distance. This mechanism is commonly called **adaptive flushing**.

Key configuration variables:

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'innodb_max_dirty_pages_pct',
    'innodb_max_dirty_pages_pct_lwm',
    'innodb_io_capacity',
    'innodb_io_capacity_max',
    'innodb_lru_scan_depth',
    'innodb_page_cleaners',
    'innodb_flush_neighbors',
    'innodb_redo_log_capacity'
);
```

| Variable | Role |
| --- | --- |
| `innodb_max_dirty_pages_pct` | Target maximum dirty page percentage threshold before InnoDB increases flush pressure. |
| `innodb_max_dirty_pages_pct_lwm` | Low-water mark where adaptive flushing begins working more aggressively once dirty pages exceed the lower threshold. |
| `innodb_io_capacity` | Estimated background I/O capacity available to InnoDB for background tasks like flushing. |
| `innodb_io_capacity_max` | Higher limit used when more aggressive flushing is needed. |
| `innodb_lru_scan_depth` | Number of pages scanned in the LRU per pass to find usable/flushable pages, per buffer pool instance configuration. |
| `innodb_page_cleaners` | Number of page cleaner threads in versions that support this variable. |
| `innodb_flush_neighbors` | Controls flushing neighboring pages when flushing a page; value semantics depend on version. |
| `innodb_redo_log_capacity` | Target redo log capacity in versions supporting this variable. |

Do not copy a set of values from another server. `innodb_io_capacity` must reflect the storage device's actual IOPS capability and workload; setting it too low can allow dirty pages/checkpoints to accumulate, while setting it too high can steal I/O from foreground queries.

### Why Do Dirty Pages Grow Continuously?

Common causes:

- Write workload generates dirty pages faster than page cleaners can flush them.
- Storage has high latency or low IOPS.
- `innodb_io_capacity` is configured lower than device capability.
- Overly large batch transactions create write bursts.
- Checkpointing falls behind due to a high redo generation rate.
- The system concurrently runs backups, sorts, scans, or heavy I/O tasks.

Correlate redo generation rate, dirty pages, flush rate, pending writes, and storage latency to distinguish the cause.

## 9. Measuring Flush Rate and I/O Pressure

Collect counters before and after a measurement window:

```sql
SHOW GLOBAL STATUS WHERE Variable_name IN (
    'Innodb_buffer_pool_pages_flushed',
    'Innodb_data_reads',
    'Innodb_data_writes',
    'Innodb_data_fsyncs',
    'Innodb_os_log_written',
    'Innodb_log_waits'
);
```

Average flush rate:

\[
\text{Flush pages/sec} =
\frac{\Delta\text{Innodb\_buffer\_pool\_pages\_flushed}}
{\Delta t\ (seconds)}
\]

Similarly, compute redo bytes generated per second from the delta of `Innodb_os_log_written` divided by elapsed time. Compare the redo generation rate against flush/checkpoint progress to see whether the system is generating changes faster than it can durably persist them.

Rising `Innodb_log_waits` can indicate transactions waiting for the log buffer/redo log to be processed; inspect it alongside redo capacity, log writes/flushes, and checkpoints. Do not treat every counter increment as an incident if latency and throughput remain within SLA.

### Monitoring File I/O in Performance Schema

You can view per-file I/O statistics:

```sql
SELECT
    FILE_NAME,
    EVENT_NAME,
    COUNT_READ,
    ROUND(SUM_TIMER_READ / 1000000000000, 3) AS read_seconds,
    COUNT_WRITE,
    ROUND(SUM_TIMER_WRITE / 1000000000000, 3) AS write_seconds,
    COUNT_MISC
FROM performance_schema.file_summary_by_instance
WHERE FILE_NAME LIKE '%ibdata%'
   OR FILE_NAME LIKE '%.ibd'
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 30;
```

File names and paths depend on configuration. Timers are cumulative; take deltas over a benchmark window. This table requires file I/O instruments to be enabled to yield useful data.

## 10. Viewing Buffer Pool Details via INFORMATION_SCHEMA

MySQL provides `INFORMATION_SCHEMA.INNODB_BUFFER_POOL_STATS` to view metrics per buffer pool instance:

```sql
SELECT
    POOL_ID,
    POOL_SIZE,
    FREE_BUFFERS,
    DATABASE_PAGES,
    OLD_DATABASE_PAGES,
    MODIFIED_DATABASE_PAGES,
    PENDING_READS,
    PENDING_FLUSH_LRU,
    PENDING_FLUSH_LIST,
    NUMBER_PAGES_READ,
    NUMBER_PAGES_WRITTEN,
    HIT_RATE
FROM information_schema.INNODB_BUFFER_POOL_STATS
ORDER BY POOL_ID;
```

`POOL_SIZE` is the number of page frames in the instance; `MODIFIED_DATABASE_PAGES` is the number of dirty pages; `FREE_BUFFERS` is the number of free page frames. `HIT_RATE` is an internal aggregate calculated by InnoDB; for time-window analysis, still prefer global status counter deltas and workload latency.

### Avoid Unnecessary Scans of `INNODB_BUFFER_PAGE`

`INFORMATION_SCHEMA.INNODB_BUFFER_PAGE` can list every page currently in the buffer pool, including schema, table, index, and page state. This table can be huge on servers with multi-gigabyte buffer pools, and querying it can incur significant overhead.

Use it only for targeted investigations, filter early by schema/table, and run it in an appropriate window. For routine per-table distribution checks, prefer `sys.innodb_buffer_stats_by_table` or `sys.innodb_buffer_stats_by_schema`.

## 11. Buffer Pool Sizing and Working Set

A buffer pool that is too small for the working set can increase physical reads, cause hot pages to be evicted frequently, and force queries to re-read from storage. However, increasing the buffer pool does not always improve performance.

When evaluating size, consider:

- Total physical RAM and container/VM memory limits.
- Memory for connections, sort/join buffers, Performance Schema, table cache, and other components.
- Size of the frequently accessed working set, not just total data file size.
- Read/write ratio and sequential vs. random query patterns.
- OS and storage caching capabilities.
- Reserve capacity to avoid swapping and memory pressure.

Check:

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'innodb_buffer_pool_size',
    'innodb_buffer_pool_instances',
    'innodb_buffer_pool_chunk_size'
);
```

Some MySQL versions have changed the role of or removed the need to manually configure `innodb_buffer_pool_instances`; check whether the variable exists in your version. Dynamic resizing of buffer pool size may be subject to chunk/instance constraints and consume significant RAM during resizing. Plan according to your version and monitor memory after changes.

### Signs the Buffer Pool May Be Undersized

- High delta physical reads during normal load hours.
- Hot working set repeatedly re-read from storage.
- `Innodb_buffer_pool_wait_free` increases alongside pending flushes or storage latency.
- p95/p99 read query latency rises when the working set exceeds the pool.
- `sys.innodb_buffer_stats_by_table` shows hot tables/indexes substantially larger than the pool can retain.

Do not rely solely on a low hit ratio to decide to add RAM. First verify whether queries are scanning too many pages, indexes are appropriate, the workload is reading cold data, or batch scans are polluting the cache.

## 12. Read-Ahead and Cache Pollution

Read-ahead prefetches pages when InnoDB detects sequential access patterns or index ranges likely to be read next. It benefits large scans and some analytical workloads. However, if predictions miss, prefetched pages may be evicted from the buffer pool before they are used.

Monitor:

```sql
SHOW GLOBAL STATUS WHERE Variable_name IN (
    'Innodb_buffer_pool_read_ahead',
    'Innodb_buffer_pool_read_ahead_evicted',
    'Innodb_buffer_pool_pages_made_young',
    'Innodb_buffer_pool_pages_not_made_young'
);
```

If `read_ahead_evicted` grows rapidly relative to read-ahead pages, many loaded pages may not be accessed before eviction. This is a signal to inspect scan queries, working set, and read-ahead settings; do not disable read-ahead automatically without benchmarking.

A reporting query scanning a large table can push OLTP hot pages out of the cache. You can reduce cache pollution by optimizing filter predicates, running reports on a replica, batching, or adjusting schedules. Partitioning and covering indexes can reduce pages read when appropriate for the query.

## 13. Experiment: Measuring Hit Ratio and Dirty Pages

Create a test table with an index:

```sql
CREATE TABLE buffer_pool_lab (
    id BIGINT NOT NULL,
    category_id INT NOT NULL,
    payload VARCHAR(200) NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY ix_category_updated (category_id, updated_at)
) ENGINE = InnoDB;
```

Load enough data to observe multiple pages, then run:

```sql
ANALYZE TABLE buffer_pool_lab;

SHOW GLOBAL STATUS WHERE Variable_name IN (
    'Innodb_buffer_pool_read_requests',
    'Innodb_buffer_pool_reads',
    'Innodb_buffer_pool_pages_dirty',
    'Innodb_buffer_pool_pages_flushed',
    'Innodb_buffer_pool_wait_free'
);
```

**Experiment A — repeated reads of a small working set:**

```sql
SELECT id, payload
FROM buffer_pool_lab
WHERE id BETWEEN 1 AND 1000;
```

Run repeatedly. The first run may need to load pages; subsequent runs typically utilize the cache better if the working set stays in the buffer pool and is not pushed out by other workloads.

**Experiment B — large range scan:**

```sql
SELECT COUNT(*), SUM(category_id)
FROM buffer_pool_lab;
```

Observe logical reads, physical reads, read-ahead, and evicted page rates. Vary the table size and repeat to observe the effect when the working set exceeds the pool.

**Experiment C — generating dirty pages:**

```sql
UPDATE buffer_pool_lab
SET payload = CONCAT(payload, '-updated'),
    updated_at = CURRENT_TIMESTAMP
WHERE id BETWEEN 1 AND 5000;

COMMIT;
```

Record `Innodb_buffer_pool_pages_dirty` and `Innodb_buffer_pool_pages_flushed` before and after, then watch as page cleaners flush in the background. Dirty pages can remain after commit; do not expect all of them to disappear immediately.

When finished with the experiment, drop the lab table if no longer needed:

```sql
DROP TABLE buffer_pool_lab;
```

Do not run large scan tests or bulk updates in production just to generate metrics. Use a test environment whose RAM, storage, and data closely match the workload being evaluated.

## 14. Interpreting an Operational Scenario

| Symptom | Possibilities to Check | Next Action |
| --- | --- | --- |
| Low hit ratio and rising physical reads | Working set exceeds pool, large scans, suboptimal indexes, or cold cache. | Inspect query digests, `EXPLAIN ANALYZE`, tables/indexes in pool, and I/O latency. |
| High hit ratio yet queries remain slow | Scanning too many logical pages, CPU, lock waits, sorts, network, or large result sets. | Inspect rows examined, stages/waits, locks, and returned data volume. |
| Continuously rising dirty pages | Write rate exceeds flush capacity or checkpoint is falling behind. | Measure redo rate, flush rate, pending writes, and storage IOPS/latency. |
| Rising `Innodb_buffer_pool_wait_free` | Lack of clean pages when allocating frames or flushing cannot keep up. | Correlate free buffers, dirty pages, LRU flushes, page cleaners, and scan workloads. |
| Rising pending flush list | Pages needing flush to advance checkpoint are piling up. | Check LSN/checkpoint age, redo capacity, and I/O speed. |
| Rising read-ahead evicted | Prefetched pages not used in time or scans causing cache pollution. | Inspect access patterns, read-ahead, and scan queries before changing config. |
| Aggressive flushing raises write latency | Page cleaners competing for I/O with foreground workload. | Evaluate `innodb_io_capacity`, `innodb_io_capacity_max`, storage, and batch sizes. |

These symptoms are investigation starting points, not single-cause conclusions. Compare deltas over the same time interval and workload.

## 15. Safe Tuning Process

1. Collect a baseline under representative load: read requests, physical reads, dirty pages, pages flushed, `wait_free`, redo written, and storage latency.
2. Identify whether the issue is cache misses, cache pollution, lack of free pages, checkpoint pressure, or storage saturation.
3. Check queries and indexes before increasing the buffer pool or I/O capacity.
4. Change only one group of related variables in a test environment or approved change window.
5. Re-measure throughput, p95/p99 latency, physical reads, dirty page trends, flush rate, and lock waits.
6. Monitor long enough to observe peak cycles, checkpoints, and batch activity; avoid concluding from the first few seconds after a change.
7. Document old values, new values, MySQL version, storage type, and rollback conditions.

Do not set `innodb_max_dirty_pages_pct` overly low just to force dirty pages near zero; that can trigger continuous flushing and I/O contention. Do not set `innodb_io_capacity` to an advertised IOPS number without measuring actual capacity under concurrent workloads. Do not grow the buffer pool to the point where the OS must swap.

## 16. Common Misinterpretation Mistakes

- **A 99% hit ratio means the database is healthy.** A high ratio can still coexist with large scans, high CPU, lock waits, or poor p99 latency.
- **Every miss is a slow physical device access.** InnoDB reads pages into the pool; OS/storage caches may serve reads without hitting physical media in a simple 1-to-1 way.
- **Dirty pages mean uncommitted transactions.** Pages can remain dirty after transactions have committed.
- **Commit means pages are written to data files.** Commit durability primarily relies on redo flushing per configuration; dirty data pages can be flushed later.
- **The lower the dirty pages, the better.** Overly aggressive flushing causes I/O contention; balance checkpoints, redo, and workload.
- **Increasing the buffer pool always improves speed.** Poor scan queries, wrong indexes, or lock contention are not solved by adding RAM alone.
- **Rising `Innodb_buffer_pool_wait_free` definitely means the pool is too small.** Slow flushing, large scans, or bursty workloads can also create page frame pressure.
- **`INNODB_BUFFER_PAGE` is always safe to scan.** The table can be huge and the observation query itself adds overhead.
- **Cumulative counters can be compared directly between two points.** You must compute deltas and confirm the server did not restart or reset counters in between.

## 17. Self-Check Exercises

1. Distinguish a logical read request from a physical page read.
2. Calculate the hit ratio if logical reads increase by 20 million and physical reads increase by 100 thousand in the same interval.
3. Why must deltas be used instead of cumulative counter totals?
4. When are dirty pages created? Can a committed transaction still have dirty pages?
5. Distinguish the flush list from LRU flushing.
6. How does a checkpoint relate to LSN and redo log reuse?
7. What does a continuous increase in `Innodb_buffer_pool_wait_free` suggest?
8. How do `innodb_io_capacity` and `innodb_io_capacity_max` affect background activity?
9. Why can read-ahead increase cache pollution?
10. Design a before/after measurement to determine whether the buffer pool is causing high latency.

Evaluating the buffer pool properly requires combining **logical reads and physical reads → working set/LRU → dirty pages → flush list and checkpoints → I/O capacity → actual latency**. The hit ratio is a useful signal, but tuning decisions must rest on trends and workload impact.
