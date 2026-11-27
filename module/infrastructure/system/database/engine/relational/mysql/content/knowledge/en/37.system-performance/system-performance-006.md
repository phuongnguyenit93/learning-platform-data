# `innodb_io_capacity`, Background Flushing, and Storage Device Characteristics

InnoDB writes changes to the redo log first to ensure recoverability, and then modified data pages are gradually written from the buffer pool to data files. This background page-writing work is called background flushing. If flushing is too slow, dirty pages and checkpoint age can grow to the point where InnoDB must flush urgently, slowing down foreground queries. If flushing is too aggressive, background activity competes for I/O with read/write queries serving the application.

Two key configuration variables for throttling background work are **innodb_io_capacity** and **innodb_io_capacity_max**. They help InnoDB estimate how much I/O capacity the device can dedicate to background tasks such as flushing dirty pages and merging the change buffer. Appropriate values depend on device type, actual IOPS and throughput, latency, workload, storage configuration, and I/O consumed by other processes.

This lesson belongs to the **System Performance** chapter of the **DATABASE_MYSQL** module. Within the scope of mastering MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control, understanding background flushing and device characteristics enables evidence-based InnoDB tuning, keeps checkpoints stable, and protects workload latency.

## 1. The Path of a Modification in InnoDB

When a transaction modifies a record, InnoDB updates the corresponding page in the buffer pool and marks that page as a dirty page. Redo information describing the change is written to the redo log so InnoDB can recover after a crash. The data page in the tablespace can be written to storage later.

This process separates two types of work:

- **Redo logging** records the information needed to recover changes. It is part of the commit path and is governed by durability settings.
- **Data page flushing** writes dirty pages from the buffer pool to data files. InnoDB can perform this in the background based on clean-page demand, checkpoint pressure, and flushing thresholds.

Therefore, a successful `COMMIT` does not mean every dirty page from the transaction was immediately written to its final position in the data file. With proper durability settings, the redo log has been written/flushed per commit rules; dirty pages may be written afterward. On a crash, InnoDB uses redo to roll forward necessary changes and handle recovery.

High-level diagram:

~~~text
Application UPDATE / INSERT / DELETE
              |
              v
       InnoDB buffer pool
       (dirty data pages)
              |
              +----------------------+
              |                      |
              v                      v
         Redo log              Background flush
      (log records)            (dirty data pages)
              |                      |
              v                      v
      Commit durability          Data files
      and crash recovery         / tablespaces
~~~

Redo logging and data page flushing are closely related, yet they are not the same I/O stream. Raising `innodb_io_capacity` does not automatically make redo log commits more durable and does not replace `innodb_flush_log_at_trx_commit` or `sync_binlog`.

## 2. Dirty Pages, Flush List, and LRU Flushing

A page in the buffer pool becomes dirty when its in-memory contents differ from what is written to the data file. InnoDB must write dirty pages to storage to free memory, advance checkpoints, and ensure enough clean pages exist to serve queries.

Two flushing goals must be distinguished:

**LRU flushing** creates additional clean pages at the tail/head of the LRU list so the buffer pool can load new pages when needed. If no clean pages are available and a query needs to read a new page, a foreground thread may have to wait for InnoDB to flush a dirty page.

**Flush-list flushing** writes dirty pages in an order aligned with checkpoint progress. Pages are ordered using LSN metadata related to their earliest/most recent modifications. As older pages are written to data files, the checkpoint can advance and free redo log space no longer needed for crash recovery.

These two goals can produce different I/O patterns. LRU flushing focuses on maintaining a supply of clean pages; flush-list flushing helps control checkpoint age. When reading statistics, do not assume every flush serves the same purpose.

InnoDB's page cleaner threads perform most dirty page flushing. InnoDB also has other background activities such as purging undo history and merging the change buffer. `innodb_io_capacity` is an I/O budget parameter across multiple background tasks, not for a single specific write statement.

## 3. Checkpoints and Redo Log Pressure

The redo log stores change information for recovery. Each change is associated with a Log Sequence Number (LSN). A checkpoint can be understood as the point prior to which InnoDB has guaranteed that changes needed for recovery have been written to data files.

Checkpoint age is commonly approximated as:

\[
\text{Checkpoint age} =
\text{Current LSN} - \text{Last checkpoint LSN}
\]

When the application generates redo faster than InnoDB can flush dirty pages, checkpoint age grows. If it approaches the redo log capacity limit, InnoDB must ramp up flushing to avoid exhausting reusable redo space. This can sharply increase background I/O and hurt foreground latency.

Signs to observe:

- Dirty page percentage rising continuously instead of stabilizing within a range.
- Checkpoint age rising quickly or frequently approaching redo capacity limits.
- I/O write latency increasing while background flushing ramps up.
- Foreground threads waiting for clean pages; `Innodb_buffer_pool_wait_free` increasing.
- Application write throughput dropping as InnoDB performs urgent flushing.
- Logs or InnoDB status indicating the checkpoint advances slowly compared to redo generation rate.

Do not look solely at dirty page percentage to conclude checkpoint pressure. A buffer pool with a high dirty ratio can still be stable if the flush rate is fast enough and checkpoint age remains far from limits. Conversely, a moderate dirty percentage combined with a workload generating redo very rapidly can still cause checkpoint pressure.

## 4. What Does `innodb_io_capacity` Control?

`innodb_io_capacity` represents an estimate of the number of I/O operations per second InnoDB may allocate to background tasks. This parameter influences how proactively InnoDB performs work such as:

- Flushing dirty pages from the buffer pool to data files.
- Performing part of change buffer merging work.
- Throttling background activities related to maintaining clean pages and checkpoints.

It is a budget/estimate for background work. It is not a hard cap on total device IOPS, not a cap on all I/O generated by MySQL, and does not directly control reads requested by foreground queries.

For example, setting `innodb_io_capacity` to 2,000 does not mean all of MySQL is limited to at most 2,000 I/Os per second. Read queries, synchronous redo writes, binlog, backups, the filesystem, and other processes still generate I/O through their own mechanisms. This value helps InnoDB estimate capacity available for background tasks.

Check the current value:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_io_capacity';
~~~

Or:

~~~sql
SELECT
    @@global.innodb_io_capacity AS io_capacity,
    @@global.innodb_io_capacity_max AS io_capacity_max;
~~~

Defaults and valid ranges depend on the MySQL version. Read the actual server values and version-specific documentation before changing anything; never copy a number from another server without measuring your device and workload.

## 5. `innodb_io_capacity_max` Is the Ceiling for Aggressive Flushing

`innodb_io_capacity_max` defines the maximum background I/O level InnoDB may use when it needs to flush more aggressively than the normal level guided by `innodb_io_capacity`.

You can think of it as:

- `innodb_io_capacity` is the normal background operating budget.
- `innodb_io_capacity_max` is the higher ceiling available during periods requiring accelerated flushing.

If `capacity_max` is too low for actual demand, InnoDB may struggle to keep pace with dirty page creation or redo generation during heavy write periods. If it is too high relative to device capability or the I/O share left for the application, background flushing can saturate the storage queue, raising foreground read/write latency.

Check both variables:

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'innodb_io_capacity',
    'innodb_io_capacity_max'
);
~~~

Do not set `capacity_max` to a huge number just to force dirty pages down quickly. Verify whether the device can sustain that IOPS/throughput level over a prolonged period and whether latency remains within SLO.

A configuration with low `capacity` but very high `capacity_max` can create aggressive flush bursts when checkpoint pressure builds. If storage has burst limits or gets throttled after a short interval, these bursts can cause severe latency swings. Observe both average and p95/p99 I/O latency.

## 6. Adaptive Flushing and Dirty Page Thresholds

InnoDB does not flush only at a fixed rate. Adaptive flushing adjusts the flush rate based on redo log state, redo generation speed, and checkpoint pressure.

Related variables include:

| Variable | Role |
|---|---|
| `innodb_adaptive_flushing` | Enables/disables adaptive flushing |
| `innodb_adaptive_flushing_lwm` | Low-water mark of redo log capacity to trigger adaptive flushing behavior as defined by the version |
| `innodb_max_dirty_pages_pct` | Target/limit percentage of dirty pages in the buffer pool used by InnoDB to regulate flushing |
| `innodb_max_dirty_pages_pct_lwm` | Dirty-page low-water mark to start flushing earlier per configuration |
| `innodb_io_capacity` | Normal background I/O budget |
| `innodb_io_capacity_max` | Maximum background I/O level for periods requiring aggressive flushing |

Check actual values:

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'innodb_adaptive_flushing',
    'innodb_adaptive_flushing_lwm',
    'innodb_max_dirty_pages_pct',
    'innodb_max_dirty_pages_pct_lwm',
    'innodb_io_capacity',
    'innodb_io_capacity_max'
);
~~~

Adaptive flushing helps avoid waiting until dirty pages or redo logs are nearly full before writing aggressively. It can accelerate flushing when redo generation is fast or checkpoint age nears limits.

Do not disable adaptive flushing merely because background I/O looks high. That I/O may be preventing checkpoint pressure from turning into a foreground outage. Before changing anything, check dirty page trends, redo generation, checkpoint age, storage latency, and application load.

Detailed thresholds and behaviors may vary by version. Do not treat `innodb_max_dirty_pages_pct` as a target the server must hold at all times; InnoDB flushes for multiple reasons and the dirty percentage fluctuates.

## 7. `innodb_flush_sync` and Checkpoint-Driven Flush Bursts

`innodb_flush_sync` controls whether InnoDB is permitted to ignore `innodb_io_capacity` during intense I/O bursts triggered by checkpoints. When enabled, InnoDB can flush beyond normal capacity limits to catch up with checkpoint pressure.

This explains why real-world observations sometimes show background I/O exceeding `innodb_io_capacity`. The capacity parameter is not a hard throttle under all conditions.

Check:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_flush_sync';
~~~

If storage is IOPS-limited or highly latency-sensitive, watch flushing behavior when checkpoint age grows. Do not rush to disable `innodb_flush_sync` just to force I/O below a fixed threshold; doing so can make checkpoints fall too far behind and risk exhausting redo capacity.

When adjusting this parameter, understand the trade-off between protecting short-term latency and maintaining stable checkpoints. Test on staging with a representative write workload and have a rollback plan.

## 8. Characteristics of HDD, SSD, NVMe, and Network Storage

`innodb_io_capacity` must reflect the actual capability of the storage system, not just the device category name.

| Storage Type | Typical Characteristics | Impact on InnoDB |
|---|---|---|
| HDD | Slow random I/O due to seek; sequential throughput can be decent; latency varies with head position | Flushing scattered pages incurs seek cost; writing neighboring pages can help |
| SATA SSD | Faster random I/O than HDD, lower latency, device-bound throughput and IOPS | Handles more random flushes than HDD; still measure as queue depth rises |
| NVMe SSD | Low latency, multiple queues, high parallelism | Can support higher background I/O, though concurrent workloads can still raise tail latency |
| Cloud block volume | IOPS and throughput often depend on volume type, size, provisioned limits, burst credits, or quotas | Can experience throttling; short benchmarks may not reflect sustained performance |
| SAN/RAID | Performance depends on drive count, striping, controller, cache, write policy, and shared load | Cannot sum nominal per-drive IOPS while ignoring controller, parity, and contention |

HDDs are sensitive to random writes and seeks. Flushing neighboring pages can reduce seek counts in some workloads. SSDs and NVMe drives have no mechanical read/write heads, so the benefit of neighbor flushing is usually lower; many SSD setups disable neighbor flushing. Still, decisions should rest on benchmarks and version defaults.

Network or cloud storage can achieve high IOPS briefly via bursting, then drop sharply once credits are exhausted. A volume can hit limits on either IOPS or MB/s throughput; workloads writing 16 KB pages may hit IOPS limits first, while sequential writes or backups may hit throughput limits first.

Beyond device type, inspect:

- p50, p95, and p99 I/O latency.
- Actual read/write IOPS and MB/s throughput.
- Queue depth and I/O wait times.
- Volume, controller, or cloud tier limits.
- Other workloads sharing the same device.
- Filesystem, mount options, caching, and `fsync` behavior.
- Placement of data files, redo logs, binary logs, relay logs, and backups.

Do not estimate usable IOPS for InnoDB by summing advertised drive IOPS without measuring the full path from MySQL to storage.

## 9. `innodb_flush_neighbors` and Coalescing Neighboring Pages

`innodb_flush_neighbors` controls whether InnoDB also flushes neighboring dirty pages when flushing a page. Values are typically defined as:

- 0: do not flush neighbor pages.
- 1: flush neighboring dirty pages within the same extent.
- 2: flush neighboring dirty pages within the same extent and contiguous extents.

Check:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_flush_neighbors';
~~~

On HDDs, neighbor flushing can reduce seeks by writing nearby pages in one operation. On SSDs and NVMe, this benefit is usually smaller because random access is fast; flushing extra unneeded pages can increase write I/O. The right value depends on storage type, workload, and MySQL version.

Do not toggle this variable purely on an HDD = 1 and SSD = 0 rule of thumb. RAID, SAN, or cloud storage may behave differently from a single physical drive. Test under reproducible conditions and measure both write throughput and foreground latency.

## 10. Measuring Dirty Pages and Flushing Activity

You can capture a snapshot of these InnoDB variables:

~~~sql
SELECT
    NOW(6) AS captured_at,
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.global_status
WHERE VARIABLE_NAME IN (
    'Innodb_buffer_pool_pages_data',
    'Innodb_buffer_pool_pages_dirty',
    'Innodb_buffer_pool_pages_free',
    'Innodb_buffer_pool_pages_flushed',
    'Innodb_buffer_pool_wait_free',
    'Innodb_data_writes',
    'Innodb_data_written',
    'Innodb_data_fsyncs',
    'Innodb_data_pending_writes',
    'Innodb_data_pending_fsyncs',
    'Innodb_os_log_written',
    'Innodb_log_waits'
)
ORDER BY VARIABLE_NAME;
~~~

Some variables are gauges and some are counters. Classify them before calculating deltas:

| Metric | Type | Interpretation |
|---|---|---|
| `Innodb_buffer_pool_pages_dirty` | Gauge | Current number of dirty pages |
| `Innodb_buffer_pool_pages_free` | Gauge | Current number of clean/free pages |
| `Innodb_buffer_pool_pages_data` | Gauge | Number of data pages in the buffer pool |
| `Innodb_buffer_pool_pages_flushed` | Counter | Cumulative number of flushed pages |
| `Innodb_buffer_pool_wait_free` | Counter | Number of times InnoDB had to wait for a clean page |
| `Innodb_data_writes` | Counter | Number of data file write operations per status variable |
| `Innodb_data_written` | Counter | Bytes of data written per status variable |
| `Innodb_data_fsyncs` | Counter | Number of data file `fsync` calls |
| `Innodb_data_pending_writes` | Gauge | Number of pending write I/Os |
| `Innodb_data_pending_fsyncs` | Gauge | Number of pending `fsync` operations |
| `Innodb_os_log_written` | Counter | Bytes of redo log written |
| `Innodb_log_waits` | Counter | Number of times the log buffer had to wait for a flush to proceed |

Variable names and availability may vary by version. If a variable does not exist, check `SHOW GLOBAL STATUS LIKE 'variable_name'` and version-specific documentation; do not invent substitute metrics with different meanings.

To track the dirty page ratio, you need the total pages in the buffer pool:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Innodb_buffer_pool_pages_dirty',
    'Innodb_buffer_pool_pages_total'
);
~~~

Approximate dirty page percentage:

\[
\text{Dirty page percentage} =
\frac{\text{Pages dirty}}{\text{Pages total}} \times 100
\]

This is a point-in-time ratio. Plot it as a time series and inspect trends rather than reading a single sample.

The delta of `Innodb_buffer_pool_pages_flushed` over 60 seconds indicates how many pages were flushed during that interval. With a 16 KiB page size, you can approximate flushed page data as delta pages × page size, though physical I/O bytes may differ due to the filesystem, doublewrite, write coalescing, and storage layers.

## 11. Observing Checkpoints and InnoDB Status

Basic diagnostic command:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

In the `mysql` client, vertical format is easier to read:

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

Focus on the `LOG`, `BUFFER POOL AND MEMORY`, `FILE I/O`, and `TRANSACTIONS` sections. Depending on version, the output may show:

- Current log sequence number.
- Log flushed up to.
- Last checkpoint at.
- Pending log flushes or pending checkpoint writes.
- Buffer pool size, free buffers, database pages, and modified db pages.
- Pending reads/writes and flush counts.
- I/O thread activity.

Compare the current LSN with the checkpoint LSN to understand checkpoint age. If the checkpoint advances slowly while the LSN grows rapidly, the system may be generating redo faster than it can write dirty pages.

`SHOW ENGINE INNODB STATUS` is a snapshot at query execution time. For trends, save outputs over intervals or extract key values into a monitoring system. Never compare two outputs without recording timestamps, `server_uuid`, uptime, and corresponding redo log configurations.

For finer detail, you can check InnoDB metrics tables in `INFORMATION_SCHEMA.INNODB_METRICS` when available and enabled. These metrics can have separate enable/reset states; verify names and definitions on your actual version before building dashboards around them.

## 12. Redo Log Durability vs. Background Page Flushing

Do not use `innodb_io_capacity` to directly explain `COMMIT` latency. The commit path is also influenced by redo log writes/flushes, the binary log, and group commit.

Two variables to understand separately:

**`innodb_flush_log_at_trx_commit`**

- 1: writes and flushes the redo log to storage on every transaction commit, using group commit when applicable.
- 2: writes the redo log to file on every commit, but physical flushing typically occurs on roughly a one-second cycle.
- 0: writes and flushes the redo log roughly every second rather than on every commit.

Values 0 or 2 can lose recent transactions on OS or host crashes, even though a MySQL process crash may behave differently. The choice depends on durability requirements and acceptable data loss.

**`sync_binlog`**

Controls how often the binary log is synchronized to storage. A value of 1 is commonly used when strong per-commit binlog durability is required; other values trade off performance against potential loss of binlog events on crash.

`innodb_io_capacity` does not replace these two durability variables. Never lower durability to mask a background flushing or storage latency problem without a data risk assessment and business approval.

When investigating slow `COMMIT`s, separate the components: redo log write/fsync, binlog sync, group commit, storage latency, lock waits, and page flushing activity. A system with stable dirty pages can still have slow `COMMIT`s due to `fsync` latency.

## 13. Impact of Redo Log Capacity and Write Workloads

Redo log capacity determines how much redo InnoDB can retain before reclaiming space via checkpoints. Larger capacity can help absorb write bursts and reduce urgent flushing in the short term. However, it does not make storage write faster and does not eliminate the need to flush dirty pages.

In newer MySQL 8.0 versions, `innodb_redo_log_capacity` is the primary variable for managing redo log capacity. Older versions use log file size and number of redo log files with a different configuration mechanism. Check your version before putting commands into runbooks.

When increasing redo capacity, consider:

- Time required for the checkpoint to reach a steady state.
- Amount of dirty pages that can accumulate in the buffer pool.
- Crash recovery time.
- Filesystem capacity dedicated to redo logs.
- Redo generation rate during peak workloads.
- Sustained storage IOPS and throughput.

A large redo log lets the system absorb longer bursts, but can also leave more redo to process during recovery. This is a capacity planning decision, not a substitute for choosing an appropriate `innodb_io_capacity`.

## 14. Impact of Storage Queues and Shared Workloads

Nominal IOPS do not tell the whole story of query experience. When many I/Os wait on one device, queue depth increases and latency can climb rapidly. Background flushing can compete with:

- Random reads from buffer pool misses.
- Data page writes and doublewrite.
- Redo log writes/flushes.
- Binary logs and relay logs.
- Backups, snapshots, exports, and filesystem scans.
- Replication apply or batch jobs.
- Other processes on the same volume or storage pool.

For example, a cloud volume might achieve 10,000 IOPS but sustain only a fixed throughput. If background flushing writes small pages at high queue depth, foreground random reads may suffer higher p99 latency even before total IOPS hit the cap. Conversely, sequential backups may saturate MB/s throughput without maxing out IOPS.

Separating data files and redo logs onto separate volumes can reduce contention in some architectures, though it does not guarantee the two volumes do not share the same backend storage pool or instance bandwidth limit. Measure both the host and the storage service.

Do not rely on CPU utilization alone to judge MySQL health. A server with low CPU yet high storage latency can still experience slow queries due to I/O waits. Correlate MySQL metrics with `iostat`, OS monitoring, or cloud volume telemetry.

## 15. Choosing `innodb_io_capacity` Based on Measurements

No single number fits every SSD, NVMe drive, or cloud volume. The selection process should start from the actual workload and I/O budget:

1. Measure sustained storage IOPS and throughput under production-equivalent conditions.
2. Determine the I/O share InnoDB can allocate to background tasks after accounting for foreground workloads, redo/binlog, backups, and shared processes.
3. Measure baselines for dirty pages, pages flushed, checkpoint age, `buffer_pool_wait_free`, and I/O latency.
4. Pick a conservative initial `innodb_io_capacity` matching the sustainable background I/O share.
5. Set `innodb_io_capacity_max` higher than normal capacity while staying within device limits and latency budgets.
6. Observe during normal write workloads and representative bursts.
7. Adjust in small increments, comparing dirty page trends, checkpoint age, foreground latency, and storage queues.
8. Document before/after values, timestamps, node, workload, and rollback steps.

A device rated at 50,000 IOPS does not mean InnoDB should be given 50,000 for `innodb_io_capacity`. A share of IOPS must be reserved for foreground queries, redo, binlog, backups, and other workloads. Moreover, random-read benchmarks can differ significantly from write benchmarks across block sizes, queue depths, and read/write ratios.

If background flushing is too low, dirty pages and checkpoint age can accumulate. If too high, query latency can rise due to storage contention. A good value keeps checkpoints steady without degrading application SLOs.

## 16. Controlled Tuning Workflow

Before making changes:

- Confirm the exact node, `server_uuid`, MySQL version, and role.
- Record `innodb_io_capacity`, `innodb_io_capacity_max`, adaptive flushing, and flush-neighbor settings.
- Capture dirty page percentage, checkpoint LSN/age, buffer pool waits, and status counters.
- Save baseline IOPS, throughput, p95/p99 latency, and queue depth at the storage layer.
- Record workload characteristics: QPS, write rate, batch jobs, backups, replication apply, and peak hours.
- Define the approver, observation period, and rollback conditions.

Check current variables:

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'innodb_io_capacity',
    'innodb_io_capacity_max',
    'innodb_adaptive_flushing',
    'innodb_adaptive_flushing_lwm',
    'innodb_flush_sync',
    'innodb_flush_neighbors',
    'innodb_max_dirty_pages_pct',
    'innodb_max_dirty_pages_pct_lwm'
);
~~~

For dynamic variables on supported versions, you can change them at runtime:

~~~sql
SET GLOBAL innodb_io_capacity = 1500;
SET GLOBAL innodb_io_capacity_max = 3000;
~~~

The numbers above are syntax examples only, not recommendations for every server. Check privileges, dynamic scope, valid ranges, and version-specific documentation before running. Runtime changes may not survive restarts.

To persist settings across restarts, MySQL 8.0 offers `SET PERSIST` for supported variables:

~~~sql
SET PERSIST innodb_io_capacity = 1500;
SET PERSIST innodb_io_capacity_max = 3000;
~~~

Do not use `SET PERSIST` in production exercises without a change record and approval. Know how to remove persisted overrides and restore prior values per your system's configuration management workflow.

After making changes, observe long enough for the workload to pass through flush and checkpoint cycles. Compare equivalent load periods rather than comparing one minute immediately after the change against a different peak window.

## 17. Interpreting Results After Tuning

| Observation | Possible Interpretation | Next Step |
|---|---|---|
| Dirty pages decline gradually, checkpoint age stabilizes, foreground latency does not rise | Flush budget may be better suited | Continue monitoring through peak hours |
| Dirty pages and checkpoint age still rise under write workloads | Background flushing may still lag or storage is capped | Check `capacity`, `max`, adaptive flushing, IOPS, and throughput |
| Dirty pages drop yet p95/p99 latency rises | Background flushing may be competing for storage with foreground traffic | Lower budget or inspect storage queues and shared workloads |
| `Innodb_buffer_pool_wait_free` increases | Periods without clean pages for read demand | Check LRU flushing, dirty pages, storage latency, and buffer pool pressure |
| Pending writes/fsyncs stay elevated | Storage or write path may be bottlenecked | Correlate OS I/O latency, queue depth, redo/binlog, and hardware |
| Low checkpoint age yet `COMMIT` remains slow | Cause may be redo/binlog `fsync` or lock waits | Check durability settings, `fsync` latency, group commit, and locks |
| Background I/O exceeds `innodb_io_capacity` | Possibly due to `innodb_flush_sync` or special checkpoint demand | Check settings and InnoDB status; do not assume it is a bug |

Do not change multiple variables at once. If you raise capacity, change `flush_neighbors`, and resize redo capacity together, you will not know which change caused the outcome. Each experiment needs a hypothesis, success metric, stop condition, and rollback plan.

## 18. Storage Characteristics and Other Related Variables

Beyond `io_capacity`, several variables affect the I/O path:

**`innodb_flush_method`** relates to how InnoDB opens and performs I/O on data files and, depending on OS/version, log files. Options and defaults depend on platform. Do not switch from buffered I/O to direct I/O or vice versa based on a single benchmark; account for OS cache, filesystem, workload, and version recommendations.

**`innodb_flush_neighbors`** controls writing neighboring pages as covered in Section 9. Evaluate based on random I/O and device characteristics.

**`innodb_doublewrite`** protects against partial page writes during power loss/crashes. Some storage systems or configurations supporting atomic writes may have version-specific mechanisms. Never disable doublewrite just to boost benchmark scores without verifying data protection and platform support.

**`innodb_flush_log_at_trx_commit`** and **`sync_binlog`** affect redo/binlog durability, not the background page flushing budget. Evaluate them separately based on RPO and recovery requirements.

**`innodb_redo_log_capacity`** governs how much redo can be held before checkpoints must advance. Larger capacity absorbs bursts, but cannot fix storage with low sustained throughput.

**`innodb_buffer_pool_size`** determines the size of the in-memory data/index cache. Enlarging the buffer pool can reduce physical reads if the working set fits, but does not directly make background flushing faster and can increase the maximum dirty pages that may accumulate.

Read current variables before changing anything and document the supported version. Never treat a configuration variable as a substitute for storage-layer measurement.

## 19. Lab Exercise: Observing Flushing Under a Write Workload

Use a test environment or a replica permitted to run load tests. Never run write benchmarks directly on production volumes without planning and approval.

**Part A — Record configuration baseline**

~~~sql
SELECT
    @@hostname AS server_host,
    @@server_uuid AS server_uuid,
    VERSION() AS mysql_version,
    @@global.innodb_io_capacity AS io_capacity,
    @@global.innodb_io_capacity_max AS io_capacity_max,
    @@global.innodb_adaptive_flushing AS adaptive_flushing,
    @@global.innodb_flush_neighbors AS flush_neighbors;
~~~

Also record adaptive flushing, dirty-page threshold, `flush_sync`, and redo capacity variables if supported by your version.

**Part B — Capture counters and gauges**

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Innodb_buffer_pool_pages_dirty',
    'Innodb_buffer_pool_pages_total',
    'Innodb_buffer_pool_pages_flushed',
    'Innodb_buffer_pool_wait_free',
    'Innodb_data_writes',
    'Innodb_data_written',
    'Innodb_data_fsyncs',
    'Innodb_data_pending_writes',
    'Innodb_data_pending_fsyncs',
    'Innodb_os_log_written',
    'Innodb_log_waits'
);
~~~

Record the timestamp, `server_uuid`, and `Uptime`. Wait for a defined measurement interval, then capture again. Compute deltas for counters and read gauges as instantaneous state values.

**Part C — Observe InnoDB and storage**

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

Record LSN, checkpoint, dirty pages, pending writes, and `FILE I/O` sections. At the OS or cloud layer, record read/write IOPS, throughput, queue depth, and p95/p99 latency for the same time window.

**Part D — Generate a representative workload**

Use a write workload with batch sizes, insert/update ratios, and key distributions similar to the target system. Do not extrapolate from a simple tight write loop to production if real workloads involve secondary indexes, large transactions, replication, and concurrent backups.

**Part E — Test incremental changes**

In the test environment, adjust `innodb_io_capacity` or `innodb_io_capacity_max` in one controlled step. Keep all other variables unchanged. Re-run the same workload for the same duration.

**Part F — Conclusion**

Compare:

- Dirty page trends and checkpoint age.
- Pages flushed/second and redo bytes/second.
- `Innodb_buffer_pool_wait_free`.
- Pending writes/fsyncs.
- Storage IOPS, throughput, queue depth, and tail latency.
- Foreground transaction latency, p95/p99, and throughput.
- Impact on read, write, and replication workloads.

Keep the new configuration only if it improves the defined objective without degrading other protective metrics. Record old values, new values, test conditions, and rollback steps.

## 20. Common Tuning Mistakes

**Treating `innodb_io_capacity` as a server-wide IOPS limit.** It is a budget/estimate for background tasks, not a cap on foreground or OS I/O.

**Setting capacity to the volume's advertised IOPS.** The device must also serve queries, redo, binlog, backups, and other workloads; cloud storage may also enforce throughput or burst caps.

**Setting `capacity_max` too high to force dirty pages down.** Background flushing can saturate queues and spike query p99 latency.

**Setting capacity too low to protect read latency.** Dirty pages and checkpoint age can accumulate, leading to urgent flushing and foreground stalls later.

**Disabling adaptive flushing when I/O rises.** Background I/O may be necessary to keep the checkpoint within bounds. Check redo generation and checkpoint age.

**Assuming I/O exceeding capacity is a bug.** `innodb_flush_sync` can allow flushing past capacity during checkpoint pressure. Inspect variables and status before concluding.

**Using the same `flush_neighbors` across all storage.** HDD, SSD, NVMe, and SAN have different characteristics. Measure before and after on a representative workload.

**Confusing dirty page percentage with checkpoint pressure.** You must examine redo generation rate, checkpoint age, and flush capacity, not just dirty percentage.

**Increasing redo capacity to compensate for slow storage.** Redo capacity absorbs bursts; it does not increase sustained IOPS or throughput.

**Using `innodb_io_capacity` to fix slow `COMMIT`s.** Inspect redo/binlog `fsync`, durability settings, storage latency, and lock waits.

**Disabling doublewrite or lowering durability to hit benchmark numbers.** Measured speed does not justify data loss or corruption risks if durability requirements disallow it.

**Changing multiple variables at once.** It becomes impossible to isolate each variable's effect and harder to roll back. Change incrementally and record baselines.

## 21. Checklist for Choosing and Validating I/O Capacity

- Have the exact server, version, and storage paths been verified?
- Is the device HDD, SSD, NVMe, SAN, RAID, or a cloud block volume?
- Have sustained IOPS, throughput, and latency been measured?
- Are there burst limits, quotas, or throttling?
- Do data files, redo, binlog, backups, and other workloads share the same backend?
- What are the current `innodb_io_capacity` and `innodb_io_capacity_max` values?
- What are the states of adaptive flushing, `flush_sync`, and dirty-page thresholds?
- Are dirty page percentage and checkpoint age trending upward?
- How do pages flushed, redo bytes, `wait_free`, and pending writes change?
- Do storage queues and p95/p99 latency rise during heavy background flushing?
- Are slow `COMMIT`s truly caused by page flushing, or by redo/binlog `fsync` or lock waits?
- Were changes tested incrementally with a representative workload?
- Are there a baseline, stop conditions, rollback plan, and approver?
- After the change, are checkpoints stable and foreground latency within SLO?

`innodb_io_capacity` and `innodb_io_capacity_max` help InnoDB throttle background I/O, but effectiveness depends on how dirty pages, redo, and checkpoints interact with the storage device. Measure redo generation rate, flush capacity, storage latency, and foreground workloads over the same time window. When capacity accurately reflects the I/O share available for background tasks, InnoDB can maintain steady checkpoints without triggering flush spikes that unnecessarily disrupt application queries.
