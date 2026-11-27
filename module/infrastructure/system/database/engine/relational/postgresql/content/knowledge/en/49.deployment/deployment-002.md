# PostgreSQL Infrastructure Capacity Planning: CPU, RAM, IOPS, Storage Capacity, and Data Growth Rate

A stable PostgreSQL deployment starts with understanding what kind of workload the system will handle, what response times it must meet, and how data will grow. CPU, RAM, storage speed, and disk capacity are closely interrelated. A server with many CPUs can still be slow if queries wait on disk reads; a disk with high IOPS cannot solve insufficient RAM forcing the operating system to repeatedly reload data; a cluster running smoothly today can still run out of space when WAL, tables, indexes, or temporary data grow rapidly.

Therefore, infrastructure planning must be based on realistic workload metrics, with headroom for peak hours, maintenance, and growth. There is no fixed CPU, RAM, or IOPS configuration that fits every PostgreSQL system.

## 1. Define the Workload Before Choosing a Server

Before selecting a configuration, describe how the application uses the database. Two systems with the same data volume can require vastly different resources.

| Workload Characteristic | Common Behavior | Resources to Watch |
|---|---|---|
| OLTP, many small transactions | Many short queries, single-row updates, high connection concurrency | Single-core CPU, disk latency, RAM for working set and indexes |
| Read-heavy | Lookups, searches, repeated read reports | RAM, cache, read IOPS, CPU |
| Write-heavy | Continuous INSERT/UPDATE, heavy WAL generation | CPU, write and fsync latency, write throughput, WAL capacity |
| Data analytics | Large table scans, JOINs, GROUP BY, sorting | RAM for hash/sort, multi-core CPU, read throughput, temp space |
| Mixed OLTP and analytics | Online transactions competing for resources with reports | Workload isolation, query limits, replicas, or dedicated resources |

Collect at least the following information:

- Transactions or queries per second at average and peak hours.
- Concurrent connections, active query-running sessions, and idle connections.
- Read/write ratio, transaction size, and batch write bursts.
- Query latency at P50, P95, and P99 percentiles, not just average time.
- Size of data, indexes, largest tables, and frequently accessed data.
- Schedules for reports, ETL, backups, VACUUM, index creation, and maintenance jobs.
- RPO/RTO objectives, data retention period, backup policy, and replica count.

If no live system exists yet, build a representative workload scenario. The scenario needs data with realistic distribution and size; testing on a few thousand small rows rarely reflects the behavior of a system with hundreds of millions of rows.

## 2. Sizing CPU

CPU handles query planning and execution, expressions, JOINs, sorting, encryption, compression, constraint checking, VACUUM, and many other background tasks. When CPU is insufficient, queries can stall even when disk still has capacity to serve.

### 2.1. Core Count and Single-Core Speed

PostgreSQL typically runs multiple backend processes; each connection is served by a dedicated process. A normal query does not automatically distribute its work evenly across all CPU cores. Some queries can use parallel query, but parallelism depends on query type, execution plan, configuration, and cost estimates.

Therefore, evaluate both:

- **Per-core performance:** important for short transactions, sequential queries, or execution steps that cannot be parallelized.
- **Total core count:** useful when there are many concurrent queries, background processes, or analytical queries that can run in parallel.
- **Actual CPU performance:** vCPUs on virtual machines may share resources with other machines; CPU bursts may be throttled after credits are exhausted. Check provider limits.
- **Resources reserved for the OS:** PostgreSQL is not the only process using CPU. The operating system, monitoring agents, backups, compression, and encryption also consume resources.

Do not size CPU solely based on total connection count. Distinguish open connections from actively running queries. Connection pooling helps limit the number of active backends and reduces context-switching overhead when applications open too many connections.

### 2.2. Recognizing CPU as a Bottleneck

Signs to monitor:

- Sustained high CPU utilization while query latency rises.
- OS run queue consistently exceeds CPU processing capacity.
- Many backends actively executing with little I/O wait time.
- CPU-intensive queries such as large JOINs, complex expressions, sorts, or aggregates dominate execution time.
- Increasing core count improves throughput in controlled tests.

High CPU for a brief burst is not necessarily a problem. Correlate with latency, throughput, wait events, and peak hours. If CPU is low but queries are slow, the cause may be I/O, locks, memory pressure, network, or suboptimal query plans.

### 2.3. How to Estimate and Validate

There is no reliable rule of thumb like "every 1,000 transactions needs one core." CPU cost depends on SQL statements, data, indexes, cache, and concurrency. The practical approach is:

1. Run a representative workload on a test configuration.
2. Measure throughput, P95/P99 latency, CPU, and run queue at peak load.
3. Step up load incrementally to find the point where latency rises sharply or throughput stops scaling proportionally.
4. Repeat with another CPU configuration to determine the benefit of more cores or higher clock speed.
5. Reserve capacity for backups, VACUUM, index creation, failover, and load growth.

For analytical queries, evaluate parallel query and limit parallel workers so multiple concurrent queries do not spawn excessive workers competing for CPU and RAM.

## 3. Sizing RAM

RAM lets PostgreSQL keep frequently accessed data and index pages in memory, reducing reads from storage devices. RAM is also used for backend processes, sorting, hash joins, maintenance, and OS cache.

Distinguish the main memory consumers:

| Component | Purpose | How to Account When Planning |
|---|---|---|
| shared_buffers | Shared memory to cache PostgreSQL data pages | Instance-wide configuration |
| OS cache | Caches files and data pages outside shared_buffers | Leave RAM available for the OS |
| work_mem | Memory per sort or hash operation in a query | Can be allocated multiple times per query and across concurrent queries |
| maintenance_work_mem | Memory for maintenance operations like index creation and VACUUM | Estimate by concurrent maintenance tasks |
| autovacuum_work_mem | Memory per autovacuum worker when configured separately | Calculate by active autovacuum workers |
| Backend memory | Private memory per connection process | Scales with backend count and query characteristics |
| wal_buffers | WAL buffer in shared memory | Configure per write demand and version |

### 3.1. shared_buffers and OS Cache

`shared_buffers` is the shared memory region PostgreSQL uses across processes. On a dedicated server, around 25% of RAM is often used as a starting point for testing, though this is not a mandatory quota. The right size depends on total RAM, working set, workload type, and OS caching behavior.

Do not allocate all RAM to `shared_buffers`. The OS still needs memory for page cache, background processes, and operational services. Over-allocating `shared_buffers` can starve other memory needs and does not guarantee faster queries.

`effective_cache_size` is an estimation parameter for the query planner indicating how much cache may be available from PostgreSQL and the OS. This parameter does not allocate RAM. Setting it too low or too high can cause the planner to misestimate data-read costs.

### 3.2. work_mem Is Per-Operation Memory

A common mistake is treating `work_mem` as a fixed allowance per connection. In reality, it applies to each sort or hash operation in a query plan. One query can contain multiple such operations; multiple concurrent queries can allocate memory simultaneously.

Illustrative example: if `work_mem` is 32 MB, 30 queries run concurrently, and each query has an average of 3 sort/hash operations needing memory, theoretical usage can reach:

32 MB × 30 × 3 = 2,880 MB

This is only a risk estimate, not a guaranteed allocation: operations do not always hit the maximum limit or run simultaneously. Still, the example shows that raising `work_mem` globally can cause out-of-memory issues as concurrency rises.

Measure how many queries spill sorts/hashes to disk, inspect execution plans, and consider setting `work_mem` per session or per role for specialized query groups. Do not raise `work_mem` globally just because a single query ran faster with more RAM.

### 3.3. Connection Count and Connection Pooling

Each PostgreSQL backend carries its own memory overhead. Setting `max_connections` too high can increase baseline RAM usage and cause many queries to contend for CPU, memory, and I/O. Do not use `max_connections` as a catch-all fix for connection issues.

For applications with many instances or short-lived connections, consider application-side connection pools or PgBouncer. A pool limits actual connections to PostgreSQL and reuses backends. Choose a pooling mode that matches how the application uses sessions, transactions, prepared statements, and session-state features.

### 3.4. Signs of Insufficient RAM

- The OS starts swapping frequently or shows memory pressure.
- Processes are terminated by the OOM killer.
- Many sort/hash operations spill temporary data to disk.
- Cache hit ratio drops alongside rising disk reads and latency.
- Performance degrades sharply once the working set exceeds cache memory.

A high cache hit ratio alone does not prove RAM is sufficient. PostgreSQL can read from the OS page cache after missing a page in `shared_buffers`. Combine PostgreSQL metrics, OS metrics, and query latency.

## 4. Evaluating Storage: Capacity, IOPS, Throughput, and Latency

These four concepts are related but not interchangeable:

- **Capacity:** the total amount of data that can be stored.
- **IOPS:** the number of read/write operations per second a device can serve under defined conditions.
- **Throughput:** the volume of data read/written per second, typically measured in MB/s or GB/s.
- **Latency:** the time to complete one I/O operation; track high percentiles such as P95/P99.

A disk with high sequential throughput does not necessarily have high random IOPS. A device achieving high IOPS in a synthetic benchmark may not perform well if latency spikes under deep queues or when running concurrently with backups.

### 4.1. What Types of I/O Does PostgreSQL Generate?

Common activities include:

- Reading table and index pages, often via random access in OLTP.
- Writing modified data pages to storage.
- Writing WAL to ensure crash recovery.
- Syncing WAL to storage via `fsync` or equivalent mechanisms.
- Reading/writing temporary files when sorts or hashes do not fit in memory.
- Reading data sequentially during table scans, backups, or reports.
- I/O from checkpoints, VACUUM, index creation, and maintenance tasks.

WAL tends to be more sequential than data-page access. However, WAL write and sync latency are critical for transactions requiring durable commits. A device with high throughput but slow `fsync` can still increase commit times.

### 4.2. Estimating IOPS from Workload

Do not derive IOPS by multiplying queries per second by a fixed constant. A query may be served entirely from cache, read one page, or scan millions of pages. Page size, cache hit rate, access patterns, checkpoints, and concurrency all influence I/O.

Measure on a representative workload:

1. Record reads/writes per second and I/O sizes.
2. Track read, write, and `fsync` latency.
3. Observe I/O queue depth; sustained queue growth often indicates storage saturation or throttling.
4. Measure peak hours, backups, checkpoints, and maintenance separately.
5. Test with near-production data size and expected concurrency.

For cloud storage, check maximum IOPS and throughput per volume size, burst limits, credits, per-instance limits, and aggregate VM limits. Advertised performance may only apply under specific configuration conditions.

### 4.3. Choosing Device Types and Data Layout

SSDs or NVMe drives generally suit PostgreSQL workloads with heavy random access and low-latency requirements. However, evaluate endurance, stability, power-loss data protection, and provider service quality.

Separating WAL and data onto separate devices can help when the two I/O streams contend significantly and the infrastructure allows independent control. Simply separating directories does not improve performance if they still sit on the same physical device or share the same IOPS cap. Implement this only after measuring a bottleneck and verifying the benefit.

Backups, WAL archives, and temporary files also generate I/O load. Account for them in the design, throttle bandwidth, or schedule them appropriately so backups do not slow online transactions.

## 5. Calculating Required Storage Capacity

Database capacity is not just the sum of business data size. When planning, include the following components:

| Component | Items to Account For |
|---|---|
| Data tables | Main data, large columns, and TOAST data |
| Indexes | Primary keys, unique indexes, query-serving indexes |
| WAL | Peak-hour generation rate, retention time, and accumulation risk |
| Temporary data | Disk-spilling sorts/hashes, temp tables, and ETL jobs |
| Logs | PostgreSQL logs, OS logs, and monitoring logs if on the same volume |
| Maintenance space | Headroom for VACUUM, index creation/rebuilds, migrations, and table rewrites |
| Backups and archives | Local backups, snapshots, WAL archives; clearly define storage location |
| Operational headroom | Buffer to handle unexpected growth and incidents |

Backups can be stored on a separate system. If stored outside the data volume, do not add full backups to the database volume size; however, you must still plan capacity and cost for the backup destination, retention period, and restore speed.

### 5.1. Planning Formula

An initial estimation model can be used:

Provisioned capacity = Projected data + WAL reserve + Temp data & logs + Operational headroom

Where:

Projected data = Current data + Net daily growth rate × Forecast days

If growth varies seasonally or by user count, use low, baseline, and high scenarios. For percentage-based growth, use a compound growth model rather than assuming a constant GB/day.

Operational headroom must suffice for peak WAL, index rebuilds, migrations, VACUUM, and abnormal spikes. Do not wait until the filesystem is nearly full to expand: PostgreSQL may fail to write WAL or data files when a volume runs out of space, causing service disruption.

### 5.2. Capacity Calculation Example

Suppose a system has the following figures:

- Current tables, TOAST, and indexes: 1.0 TB.
- Measured net growth rate: 8 GB/day.
- Forecast horizon: 180 days.
- WAL reserve for high-load periods: 80 GB.
- Expected temp data and logs on the same volume: 40 GB.
- Operational headroom: 25% of projected data.

Data portion after 180 days:

1.0 TB + (8 GB × 180) = approx. 2.44 TB

Operational headroom:

2.44 TB × 25% = approx. 0.61 TB

Estimated total capacity:

2.44 TB + 0.08 TB + 0.04 TB + 0.61 TB = approx. 3.17 TB

Select a volume with usable capacity larger than this figure, then verify using the provider's GB/TB unit definitions. This example assumes the 8 GB/day growth rate already includes table and index growth, and that backups are stored elsewhere. In real deployments, add any omitted components if they reside on the same volume.

### 5.3. Tracking Data Growth Rate

Do not inspect total capacity just once. Store periodic daily or weekly measurements to calculate net growth rates and spot tables growing abnormally.

Size of each database:

~~~sql
SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS database_size
FROM pg_database
ORDER BY pg_database_size(datname) DESC;
~~~

Largest tables, including indexes and TOAST data:

~~~sql
SELECT
    schemaname,
    relname,
    pg_size_pretty(pg_total_relation_size(
        format('%I.%I', schemaname, relname)::regclass
    )) AS total_size,
    pg_size_pretty(pg_relation_size(
        format('%I.%I', schemaname, relname)::regclass
    )) AS table_size,
    pg_size_pretty(pg_indexes_size(
        format('%I.%I', schemaname, relname)::regclass
    )) AS indexes_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(
    format('%I.%I', schemaname, relname)::regclass
) DESC
LIMIT 20;
~~~

Store results over time to compute:

Average daily growth rate = (Ending size − Starting size) / Number of days

Track tables, indexes, WAL, and filesystem usage separately. Database size can grow due to new data, new indexes, bloat, or storage layout changes; these causes require different actions.

## 6. Managing WAL and Disk-Full Scenarios

WAL is used for recovery and replication. WAL usage can grow rapidly under heavy write workloads, checkpoint or archiving issues, lagging replicas, or replication slots retaining unconsumed WAL.

Monitor:

- WAL generation rate over time and during peak hours.
- WAL space consumed on the filesystem.
- WAL archiving status and archive failures.
- Standby replication lag.
- Inactive replication slots or slots retaining large amounts of WAL.
- Checkpoints occurring too frequently or taking excessively long to write.

An abandoned replication slot can retain WAL longer than expected and fill the disk. Never delete slots or WAL files manually to free space; identify the consumer, check replication status, and handle via PostgreSQL operational procedures. Deleting files in the data directory can break cluster recoverability.

## 7. Measuring with PostgreSQL and OS Metrics

Capacity planning is only reliable with continuous measurements. Combine internal PostgreSQL statistics with host and storage metrics.

### 7.1. I/O Statistics in PostgreSQL

On PostgreSQL 16 and later, the `pg_stat_io` view provides I/O statistics by backend type, object, and context:

~~~sql
SELECT
    backend_type,
    object,
    context,
    reads,
    read_time,
    writes,
    write_time,
    fsyncs,
    fsync_time
FROM pg_stat_io
ORDER BY backend_type, object, context;
~~~

Timing columns are meaningful when `track_io_timing` is enabled. Evaluate measurement overhead in your environment and compare metrics over equal time intervals. This view reports cumulative statistics, so sample periodically and compute deltas between samples.

On older versions, you can start with `pg_stat_database`:

~~~sql
SELECT
    datname,
    blks_read,
    blks_hit,
    temp_files,
    temp_bytes,
    deadlocks
FROM pg_stat_database
ORDER BY datname;
~~~

The shared buffers hit ratio can be approximated by:

100 × blks_hit / (blks_hit + blks_read)

This is only a reference indicator. `blks_read` is the number of blocks PostgreSQL had to request into `shared_buffers`, not necessarily physical disk reads; the OS may serve them from page cache. Do not rely on this ratio alone to conclude storage or RAM is sufficient.

### 7.2. Tracking WAL

Inspect WAL statistics with `pg_stat_wal` on versions supporting this view:

~~~sql
SELECT
    wal_records,
    wal_fpi,
    pg_size_pretty(wal_bytes) AS wal_generated,
    wal_buffers_full,
    wal_write,
    wal_sync,
    wal_write_time,
    wal_sync_time
FROM pg_stat_wal;
~~~

Sample periodically to compute WAL generated per minute or per hour. When comparing, remember statistics can be reset and timing figures depend on I/O timing configuration.

### 7.3. Tracking Connections and Wait Events

~~~sql
SELECT
    state,
    wait_event_type,
    wait_event,
    count(*) AS sessions
FROM pg_stat_activity
GROUP BY state, wait_event_type, wait_event
ORDER BY sessions DESC;
~~~

This query helps distinguish running, idle, and waiting backends. Interpret wait events alongside SQL, wait duration, and load context; the mere presence of a wait event does not automatically mean an error.

If `pg_stat_statements` is installed, use it to find SQL queries consuming high total execution time, having high call counts, or showing high variance. Tuning queries and indexes often reduces CPU, RAM, and I/O demand more effectively than simply upgrading server hardware.

### 7.4. OS and Provider Metrics

At a minimum, monitor:

- CPU utilization, CPU steal on VMs, run queue, and load.
- Available RAM, swap, page faults, and OOM indicators.
- Read/write IOPS, throughput, latency, queue depth, and volume limits/burst.
- Filesystem space, inodes, and growth rate over time.
- Network throughput, packet loss, and latency between application, primary, and replicas.
- Backup duration, WAL archive lag, replication lag, and VACUUM completion times.

Tools such as `iostat`, `vmstat`, `sar`, or provider metric systems help correlate PostgreSQL with host activity. When the database reports rising read times, storage metrics help determine whether it is device latency, IOPS throttling, or contention from another process.

## 8. Load Testing and Validating the Right Configuration

A configuration should only be finalized after testing on a representative workload. You can use `pgbench` for baseline tests or an application workload replay tool to preserve realistic query distributions.

Testing workflow:

1. Prepare data with near-production size and distribution.
2. Use the same PostgreSQL version, key parameters, and intended storage type.
3. Ramp up load gradually, recording throughput and P95/P99 latency.
4. Simulate concurrent reads/writes, reports, backups, and maintenance.
5. Monitor CPU, RAM, IOPS, throughput, storage latency, WAL, and temporary space.
6. Test when the working set exceeds cache to observe I/O behavior.
7. Verify recoverability and backup restore duration if required for deployment.
8. Repeat after changing one resource group to know what actually caused an improvement.

Do not change CPU, RAM, storage, and multiple PostgreSQL parameters simultaneously and guess which change yielded the improvement. Changing one factor or controlled group at a time isolates root causes clearly.

## 9. Reserving Capacity for Operations and Growth

Resources must serve both business workloads and operational tasks. Plan for these scenarios:

- Full and incremental backups running during peak hours.
- VACUUM, autovacuum, ANALYZE, and index rebuilds.
- Migrations creating large tables or indexes.
- End-of-day reports, ETL, and batch imports.
- Seasonal, campaign, or user-growth traffic spikes.
- Primary role switchovers or replica promotion to primary.
- Data restores, WAL replay, and replica resynchronization.

With standby systems, each replica also needs sufficient CPU, RAM, and storage for its expected role. Read replicas can offload some read queries, but do not automatically solve write load on the primary. Replication also adds network, WAL, and storage overhead.

You can scale vertically by adding CPU, RAM, or storage; or scale architecturally using connection pooling, read replicas, partitioning, historical data archiving, and separating analytical workloads. Each option has its own costs and trade-offs. Use partitioning only when you have suitable partition keys, queries, and data lifecycle strategies; partitioning does not automatically make all queries faster.

## 10. Setting Actionable Alerts with Lead Time

Capacity alerts should be based on growth rate and the time operations needs to expand volumes or clean up valid data. For example, a 70% warning threshold and an 85% critical threshold can serve as a starting point for discussion, but must be adjusted for growth rate, provisioning lead time, and platform limits.

Alert before running out of headroom for:

- Data filesystem and WAL filesystem.
- Abnormal WAL growth or archiving failures.
- Replication slots retaining WAL too long.
- Replication lag exceeding business thresholds.
- Storage IOPS, throughput, or latency approaching limits.
- Sustained high CPU and RAM usage.
- Rising swap, OOM events, or abnormal temporary space growth.
- Data growth rate exceeding forecasts.

Good alerts state which metric crossed the threshold, since when, its rate of change, and estimated time to exhaustion. For capacity, estimate remaining days by dividing free space by average net growth rate; also check peak-hour or high-growth scenarios to avoid overly optimistic estimates.

## 11. Common Mistakes

- **Sizing servers by current database size:** ignoring indexes, WAL, temp files, maintenance, and growth.
- **Looking only at average CPU:** missing short load spikes, CPU steal, or a saturated single core.
- **Raising `work_mem` globally:** many concurrent queries can push total memory past available RAM.
- **Raising `max_connections` to fix all connection errors:** increases backends and resource contention; consider pooling instead.
- **Using advertised IOPS as the sole metric:** failing to check latency, throughput, queue depth, burst, and per-instance limits.
- **Treating `blks_read` as physical disk reads:** ignoring OS page cache.
- **Ignoring WAL and replication slots:** can fill volumes even when business data grows slowly.
- **Benchmarking only with small datasets:** working set and access patterns do not resemble production.
- **Leaving no headroom for maintenance and recovery:** the system runs normally at steady state but fails during backups, migrations, or failover.

## 12. Pre-Deployment Checklist

- [ ] Described workload type, throughput, concurrency, and peak hours.
- [ ] Defined P95/P99 latency, RPO, RTO, and retention objectives.
- [ ] Benchmarked CPU with representative data and queries.
- [ ] Calculated RAM for `shared_buffers`, OS, backends, `work_mem`, and maintenance.
- [ ] Decided connection limits and connection pooling mechanism.
- [ ] Measured IOPS, throughput, latency, and queue depth on the target storage type.
- [ ] Accounted for tables, TOAST, indexes, WAL, temp files, logs, and operational headroom.
- [ ] Forecasted growth for at least one appropriate operational planning horizon.
- [ ] Defined storage destinations for backups and WAL archives, along with retention capacity.
- [ ] Configured metrics, alerts, and runbooks for abnormal storage or WAL growth.
- [ ] Tested backup/restore, maintenance, and failover scenarios per service requirements.
- [ ] Documented configuration, assumptions, benchmark metrics, and review schedule.

## Conclusion

Sizing CPU, RAM, IOPS, and storage for PostgreSQL is a process of measurement and forecasting. CPU must match concurrency and query types; RAM must cover the working set while leaving room for the OS and per-query operations; storage must simultaneously meet IOPS, throughput, and latency needs; capacity must account for data, indexes, WAL, temporary files, maintenance, and growth.

Start with the workload and measured metrics, test on a near-production configuration, and set alert thresholds early enough for operations to act. As workloads and data evolve, re-measure and update the plan rather than treating the initial sizing as fixed.
