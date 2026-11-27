# Workload Classification and Bottleneck Identification

PostgreSQL resource tuning begins with understanding what work the database is doing and which resource is limiting its processing capacity.


## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish between OLTP, OLAP, reporting, batch, ETL, and mixed workloads.
- Describe workloads using throughput, latency percentiles, concurrency, read/write ratio, and data access patterns.
- Establish a baseline and compare metrics over the same time window.
- Use PostgreSQL statistics views to find queries and database activities that consume resources.
- Read wait events, locks, connection usage, buffer/cache behavior, and I/O statistics.
- Identify CPU, memory, storage, network, WAL, checkpoint, and connection bottlenecks.
- Use EXPLAIN/EXPLAIN ANALYZE to analyze query costs.
- Distinguish query-level problems from system-wide resource saturation.
- Formulate hypotheses, test, and confirm bottlenecks using controlled changes.
- Estimate capacity and design benchmarks suited to the workload.
- Avoid pitfalls such as increasing work_mem, max_connections, or shared_buffers without measuring.
- Build dashboards, alerts, and a repeatable performance troubleshooting workflow.

## 2. What is a Workload?

A workload is the set of database activities over a period of time: SQL statements, transaction patterns, data volume, concurrency, background tasks, and replication/maintenance work.

### 2.1. Query mix

Record the types of statements: SELECT, INSERT, UPDATE, DELETE, DDL, bulk loads, reporting queries, and stored procedures.

### 2.2. Transaction profile

Transactions can be very short with a few statements, or long with many reads/writes. Transaction duration affects locks, snapshots, vacuum, and connection occupancy.

### 2.3. Data access pattern

A workload may access a few rows frequently, scan large tables, read by time range, join multiple tables, or update a set of hot keys.

### 2.4. Concurrency

The number of concurrent clients and running requests affects queueing, locks, CPU scheduling, memory, and I/O.

### 2.5. Time variation

Workloads vary by hour, day, month-end, campaign, batch window, or backup window. A single snapshot does not describe the entire load.

## 3. Common Workload Classes

| Workload | Characteristics | Common Goals |
|---|---|---|
| OLTP | Many small transactions, concurrent reads/writes | Low latency, correctness |
| OLAP | Scans/joins/aggregates on large datasets | Throughput and query completion |
| Reporting | Periodic reads, potentially heavy | Freshness and predictable runtime |
| Batch | Many writes/updates in batches | Completion within a time window |
| ETL/ELT | Extract/transform/load | Data throughput and restartability |
| Mixed | Multiple workload types on the same cluster | Isolation and predictable SLOs |

### 3.1. OLTP

Examples include order creation, account lookup, and inventory updates. Usually sensitive to p95/p99 latency, lock contention, and connection queueing.

### 3.2. OLAP

Queries that scan many rows, perform large joins, and aggregate. They can leverage parallel query but consume significant CPU, memory, and storage bandwidth.

### 3.3. Reporting

Dashboards and scheduled reports may repeat the same query shape. Consider materialized views, summary tables, or read replicas if the workload impacts OLTP.

### 3.4. Batch processing

Batch jobs can create WAL bursts, dead tuples, checkpoint pressure, and lock contention. Batch size/commit frequency can matter more than average query count.

### 3.5. Mixed workloads

A cluster may serve latency-sensitive APIs while running analytics at the same time. One workload can monopolize resources and increase latency for another even when total CPU has not reached 100%.

## 4. Which Metrics Characterize a Workload?

Do not classify solely by application name. Describe the workload using measurable dimensions.

### 4.1. Throughput

Requests/transactions/queries per second (QPS/TPS) indicate the volume completed. Distinguish offered load (sent to the database) from completed throughput (finished processing).

### 4.2. Latency percentiles

Measure p50, p95, p99, and max. Averages can hide a group of very slow requests; p99 is especially important for user-facing OLTP.

### 4.3. Concurrency and queue depth

Record active requests, active database sessions, pool waiters, and queued requests. Throughput may stop increasing as concurrency rises due to queueing.

### 4.4. Read/write mix

Read/write ratio, row changes, WAL bytes, and transaction mix affect cache, storage, WAL, and vacuum.

### 4.5. Query shape

Record query fingerprints/normalized statements, joins, sorts, aggregates, rows scanned/returned, temp files, and plan stability.

### 4.6. Data distribution

Cardinality, skew, hot keys, tenant size, partition size, and correlation affect planner estimates and contention.

### 4.7. Freshness/consistency requirement

One read may tolerate stale data by a few seconds; a read-after-write cannot. This requirement affects routing and replication capacity.

## 5. Throughput, Latency, and Concurrency

These three metrics are related through queueing behavior.

~~~text
Incoming requests
       |
       v
   Waiting queue
       |
       v
 Active database work
       |
       v
 Completed responses
~~~

### 5.1. Offered load

The number of requests sent by the application. If offered load exceeds service capacity, the queue will grow.

### 5.2. Completed throughput

The number of requests actually completed. When resources are saturated, increasing offered load typically increases latency without significantly increasing throughput.

### 5.3. Queueing latency

A request can spend time waiting for a connection pool, lock, CPU, I/O, or worker slot before executing.

### 5.4. Little's Law

In steady state, the average number of requests in the system equals throughput multiplied by average response time: L = lambda × W. When W increases while throughput stays constant, the number of in-flight requests increases.

### 5.5. Do not optimize a single metric in isolation

Increasing throughput via large batches can worsen OLTP p99 latency. Reducing the latency of one query can increase total CPU if it causes the app to generate more requests.

## 6. Defining SLOs and Workload Classes

Before tuning, define what each workload needs to achieve.

### 6.1. User-facing OLTP

Set target p95/p99 latency, error rate, and transaction success. Distinguish database execution time from end-to-end request time.

### 6.2. Reporting

You can set query completion time, data freshness, and concurrency limits instead of requiring p99 under tens of milliseconds.

### 6.3. Batch

Set completion windows, rows/second, WAL volume, and limits on impact to foreground traffic.

### 6.4. Background maintenance

Vacuum, analyze, index maintenance, and backups need sufficient runtime without exhausting storage/CPU during peak traffic.

### 6.5. Workload isolation

Use separate connection pools, query timeouts, orchestration-layer resource groups, read replicas, or scheduling to reduce interference. PostgreSQL core does not provide a general-purpose resource group scheduler for all workloads.

## 7. Collecting a Baseline Before Tuning

A baseline is a set of metrics representing the system in normal operation and during peak windows.

### 7.1. Choose the observation window

Collect across full daily/weekly cycles and batch windows. A few minutes do not represent month-end or campaign periods.

### 7.2. Record version and configuration

Save the PostgreSQL version, hardware, storage type, parameters, extensions, connection pool settings, and topology. Metrics without context easily lead to wrong conclusions.

### 7.3. Synchronize timestamps

Use a consistent timezone, ideally UTC, to correlate application, PostgreSQL, OS, and cloud metrics.

### 7.4. Log workload events

Mark deployments, data loads, vacuum, backups, failovers, schema changes, and traffic campaigns on the timeline.

### 7.5. Compare under the same conditions

Compare before/after with the same query mix, data size, concurrency, and cache state whenever possible. If the workload differs, a performance change cannot be attributed to a single parameter.

## 8. Metric Layers to Observe

| Layer | Typical Metrics | Question |
|---|---|---|
| Application | Request rate, latency, pool wait, errors | Where are users waiting? |
| PostgreSQL | Query stats, sessions, waits, locks | What is the database doing? |
| OS/VM | CPU, memory, run queue, disk, network | What limits the host? |
| Storage | IOPS, throughput, latency, queue depth | Which I/O is slow? |
| Replication | WAL rate, lag, slots, archive | Is the replica keeping up? |
| Business | Orders/sec, jobs, freshness | What is the business impact? |

### 8.1. Correlate instead of reading in isolation

High CPU alongside high query time may be CPU-bound; low CPU alongside high latency may be lock/I/O/network wait. Align metrics across the same time range.

### 8.2. Separate foreground and background

API queries, batch jobs, autovacuum, checkpoints, and backups can compete for resources. Know which activities increase at the same time.

### 8.3. Track rates and absolute values

A counter increasing from 1 million to 1.1 million requires calculating delta/time. A cumulative value does not show the current rate.

### 8.4. Resetting statistics

Some statistics counters reset on restart/stats reset. Record stats_reset and uptime to avoid comparing non-equivalent intervals.

### 8.5. Sampling interval

Intervals that are too long hide spikes; intervals that are too short create noise and overhead. Choose an interval matching your latency/SLO and retain history long enough.


## 9. PostgreSQL Statistics: Database and Table Activity

Statistics views provide an overview of database activity. They are cumulative counters or estimates, so take deltas over time and examine them alongside uptime/reset time.

~~~sql
SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    tup_returned,
    tup_fetched,
    tup_inserted,
    tup_updated,
    tup_deleted,
    temp_files,
    temp_bytes,
    deadlocks,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
~~~

### 9.1. Transactions

xact_commit/xact_rollback help estimate transaction volume and rollback trends. Do not equate one transaction with one HTTP request.

### 9.2. Buffer hits and reads

blks_hit represents blocks retrieved from shared buffers according to statistics; blks_read represents blocks read into database buffers. The OS page cache can still serve a block read without physical disk I/O.

### 9.3. Tuples

tup_returned/fetched/inserted/updated/deleted help understand database-level read/write activity. These are aggregate counters and do not replace query-level analysis.

### 9.4. Temporary files

Increasing temp_files/temp_bytes can indicate sorts/hashes spilling to disk or operations using temp storage. Check which queries generate temp files and plan memory requirements.

### 9.5. Deadlocks

Increasing deadlocks signal concurrency/transaction design issues that require investigation, not simply a CPU bottleneck.

## 10. Table-Level Statistics and Bloat Clues

The `pg_stat_user_tables</BT> view shows table activity and vacuum/analyze history.

~~~sql
SELECT
    schemaname,
    relname,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch,
    n_live_tup,
    n_dead_tup,
    n_mod_since_analyze,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY seq_tup_read DESC;
~~~

### 10.1. Sequential scans

Seq scans are not inherently bad. Scanning an entire small table can be faster than using an index; large tables repeatedly scanned for small lookups warrant investigation.

### 10.2. Index scans

idx_scan and idx_tup_fetch show index activity, but do not prove that an index is useful or that the query plan is optimal.

### 10.3. Dead tuples

n_dead_tup is an estimate. Long-term growth can be linked to autovacuum lag, long transactions, or update/delete churn.

### 10.4. Analyze freshness

Stale stats can cause the planner to misestimate. Track n_mod_since_analyze and last_autoanalyze alongside plan changes.

### 10.5. Table size

Combine `pg_total_relation_size</BT>, `pg_relation_size</BT>, and index sizes to find tables/indexes growing rapidly or consuming most of storage.

## 11. Query-Level Statistics with pg_stat_statements

The `pg_stat_statements</BT> extension aggregates execution statistics by normalized query identity, useful for finding queries consuming the most total time or having high latency.

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    min_exec_time,
    max_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_written,
    wal_bytes,
    query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

### 11.1. Total time and mean time

A query with a 1 ms mean running one million times can consume substantial total CPU. A query running once for 30 seconds may be an outlier needing separate handling.

### 11.2. Calls and rows

Calls/rows help determine query frequency and output volume. A query returning too many rows can consume network/application memory even if database execution is fast.

### 11.3. Shared blocks

shared_blks_hit/read suggest buffer activity. Read counters do not necessarily mean physical disk reads because the OS cache may serve the data.

### 11.4. Temp blocks

temp_blks_written helps identify spilling sorts/hash aggregates. Combine EXPLAIN and log_temp_files to pinpoint the cause.

### 11.5. Statistics do not retain every execution

Entries are aggregates and can be reset/evicted. Query text may be normalized/truncated depending on configuration; do not use it as an audit log.

## 12. Enabling and Managing pg_stat_statements

The extension requires preloading the library and creating it in the database per version documentation.

### 12.1. shared_preload_libraries

~~~conf
shared_preload_libraries = 'pg_stat_statements'
pg_stat_statements.max = 10000
pg_stat_statements.track = all
~~~

If extensions already exist in shared_preload_libraries, append the library name rather than overwriting the existing list.

### 12.2. Create the extension

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

### 12.3. Track level

`pg_stat_statements.track</BT> can track top-level statements or also nested statements depending on configuration. Nested tracking increases detail and overhead.

### 12.4. Controlled reset

`pg_stat_statements_reset()</BT> clears the corresponding statistics. Snapshot/export a baseline before resetting if comparison is needed.

### 12.5. Privacy

Query text may contain literals depending on normalization/settings and version. Control access to views, logs, and dashboards according to data policy.

## 13. Active Sessions with pg_stat_activity

This view helps identify running sessions, waiting sessions, and transaction age.

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    now() - xact_start AS transaction_age,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
~~~

### 13.1. active and idle

active means the backend is executing a query; idle means the session is waiting for the client. idle in transaction can hold snapshots/locks even while not running a query.

### 13.2. Query age

A long-running query is not necessarily a bottleneck. It may be a legitimate report; you need to know the query type, resource consumption, and impact on other workloads.

### 13.3. Transaction age

Old transactions can hold locks/snapshots, block vacuum cleanup, and cause bloat. Pay special attention to idle in transaction.

### 13.4. Wait events

wait_event_type/wait_event indicate what the backend is waiting for. The absence of a wait event does not by itself prove CPU saturation; take multiple samples to distinguish.

### 13.5. Query visibility

Permission to view query text of other sessions depends on privileges and PostgreSQL version. Avoid granting broad privileges solely to display SQL on dashboards.

## 14. Wait Events: Seeing Where Backends Spend Time Waiting

Wait events classify time when a backend is not making CPU progress because it is waiting for a resource/event.

| Wait category | Example | Investigation Direction |
|---|---|---|
| Lock | relation, transactionid | Blocking sessions, transaction order |
| LWLock | buffer/contention locks | Shared memory contention, workload |
| IO | DataFileRead/Write, WAL I/O | Storage latency/queue |
| Client | ClientRead/Write | Client/network/backpressure |
| IPC | Parallel worker coordination | Parallel execution/workers |
| Timeout | Various timeout waits | Timers and workload behavior |

### 14.1. Lock wait

A query can be slow because it is waiting on another transaction, even when CPU/disk are low. Find the blocker chain before tuning SQL.

### 14.2. I/O wait

Rising IO waits alongside storage latency/queue can indicate a disk bottleneck. Distinguish data files, WAL, temp files, and relation extension.

### 14.3. Client wait

The backend is waiting for the client to send commands or receive results. ClientRead is common in idle sessions; ClientWrite can increase when the client/network reads slowly.

### 14.4. LWLock

Contention on shared memory structures can appear at high concurrency. Examine the specific wait event, version, and workload; this is not solved by increasing disk throughput.

### 14.5. Sampling

Wait events represent state at the moment of observation. Use continuous sampling or historical monitoring to see the proportion of time by category.

## 15. Lock Contention and Blocking Chains

Lock contention is often mistaken for a query CPU bottleneck because users only observe increased latency.

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.application_name AS blocked_app,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    now() - blocker.xact_start AS blocker_xact_age,
    left(blocked.query, 200) AS blocked_query,
    left(blocker.query, 200) AS blocker_query
FROM pg_stat_activity AS blocked
JOIN pg_stat_activity AS blocker
  ON blocker.pid = ANY (pg_blocking_pids(blocked.pid))
ORDER BY blocker.xact_start NULLS FIRST;
~~~

### 15.1. Blocking query and blocker

The waiting query may not be the one causing the issue. Find the blocker transaction holding the lock for a long time.

### 15.2. Transaction design

Overly long transactions, calling external APIs inside a transaction, or waiting for user input can hold locks for a long time. Shortening transactions often matters more than adding CPU.

### 15.3. Lock modes

DDL, row updates, foreign keys, and explicit locking use different lock modes. Read pg_locks alongside pg_stat_activity to understand conflicts.

### 15.4. Deadlock

A deadlock is a cycle in the lock wait graph. PostgreSQL detects and aborts one transaction; check logs and design a consistent lock acquisition order.

### 15.5. Do not kill backends on intuition

Before running pg_cancel_backend/pg_terminate_backend, identify the transaction, owner, side effects, and rollback cost. Termination can trigger a large rollback and generate additional I/O.


## 16. CPU Bottleneck

A CPU bottleneck occurs when the database has more runnable work than the CPU capacity can process. Typical signs are sustained high CPU utilization, a growing run queue, and rising query execution time even when lock/I/O waits do not account for most of the time.

### 16.1. OS CPU metrics

Track user/system CPU, CPU steal in VM environments, load average, and run queue. A high load average does not automatically mean CPU is saturated; check core count and I/O wait.

### 16.2. PostgreSQL process distribution

PostgreSQL typically uses backend processes for client connections and background processes. Check process-level CPU to find queries/backends or autovacuum/checkpointer consuming high CPU.

### 16.3. Query CPU

Sorts, hash aggregates, JSON processing, regex, expression evaluation, large joins, and sequential scans can be CPU-intensive. Use pg_stat_statements to find total time/calls, then EXPLAIN ANALYZE to identify plan nodes.

### 16.4. Concurrency and context switching

Too many active sessions can increase context switching and cache contention. Increasing max_connections does not give the CPU more capacity.

### 16.5. Parallel query

Parallel workers can shorten certain scans/aggregates but increase total CPU and worker contention. Check parallel plans, worker availability, and impact on OLTP.

## 17. Distinguishing CPU-Bound from Wait-Bound

A query with long elapsed time but low CPU time may be waiting on locks, I/O, or clients. Do not infer the bottleneck from duration alone.

### 17.1. CPU-bound symptoms

High CPU utilization, query execution consuming CPU, large run queue, and wait events not explaining most of the latency.

### 17.2. I/O-bound symptoms

Backends frequently waiting on IO, rising storage latency/queue, high cache misses, or high temp I/O. CPU may not be busy.

### 17.3. Lock-bound symptoms

Many active sessions with wait_event_type=Lock and a clear blocking chain. Overall CPU may be low while latency is very high.

### 17.4. Client-bound symptoms

Sessions waiting on ClientRead/ClientWrite or high application pool wait. The database may not be the primary source of delay.

### 17.5. Mixed bottleneck

A query can be both CPU-intensive and I/O-intensive; lock waits can also be a consequence of a query holding a transaction open for too long. Analyze the timeline and multiple samples.

## 18. Memory: shared_buffers, work_mem, and Memory Pressure

PostgreSQL uses multiple memory areas with different lifecycles. No single "memory used by PostgreSQL" number reflects the entire requirement.

### 18.1. shared_buffers

Shared buffers is PostgreSQL's internal cache for data pages. Increasing it too much can reduce memory for the OS page cache and other processes; benefits depend on working set, storage, and OS cache behavior.

### 18.2. work_mem

work_mem is the base memory limit per sort/hash operation before it may spill to temporary files. A query with multiple nodes or parallel workers can use multiple multiples of work_mem.

### 18.3. Do not calculate work_mem based on a single connection

One session can run multiple sort/hash operations; many concurrent sessions and parallel workers can allocate simultaneously. Potential total memory can be much larger than work_mem multiplied by max_connections.

### 18.4. maintenance_work_mem

Used for certain maintenance operations such as VACUUM and index creation. Multiple concurrent maintenance jobs can consume memory at the same time.

### 18.5. Backend/process memory

Each backend and background worker has private memory. Extensions, PL runtimes, query execution structures, and application concurrency increase total RSS.

## 19. Identifying Memory Pressure

Memory pressure can cause the OS to reclaim pages, swap, trigger OOM kills, or increase database latency.

### 19.1. OS metrics

Monitor available memory, swap-in/swap-out, page faults, OOM events, and process RSS. Low free memory is not automatically an error if the OS is using RAM for cache; look at available memory and pressure.

### 19.2. Swap activity

Sustained swap-in/out often causes unpredictable latency. PostgreSQL workloads are sensitive to page faults; avoid designing total memory allocation above physical RAM.

### 19.3. Temporary file growth

Growing temp files can indicate sort/hash spills. Check log_temp_files and query plans to decide whether to change the query, index, or work_mem.

### 19.4. Hash memory

Hash joins/aggregates can use significant memory; they spill into multiple batches if insufficient. Increasing work_mem may help one query while causing many concurrent queries to trigger OOM.

### 19.5. Memory accounting

Review shared_buffers, OS cache, backend RSS, autovacuum/maintenance workers, and extension memory together. Avoid double-counting shared memory in RSS metrics.

## 20. Storage I/O Bottleneck

Storage can limit throughput or create tail latency. Distinguish IOPS, throughput, latency, and queue depth.

### 20.1. IOPS

IOPS is the number of operations per second. Random small reads/writes are usually IOPS-limited rather than sequential throughput-limited.

### 20.2. Throughput

MB/s measures the volume of bytes transferred. Sequential scans, backups, WAL archiving, and bulk loads can hit throughput limits.

### 20.3. Latency

High disk latency makes queries wait longer, especially for random reads and synchronous writes. Observe p95/p99 storage latency, not just average.

### 20.4. Queue depth

Rising queue depth can indicate storage is already busy or the host is issuing too much I/O. Large queues can increase latency; adding concurrency does not always increase throughput.

### 20.5. Storage classes

Local NVMe, network block storage, SAN, and cloud volumes have different latency/throughput/IOPS characteristics. Benchmark on the exact storage class and provisioned limits.


## 21. PostgreSQL I/O Statistics

Since PostgreSQL 16, the pg_stat_io view provides I/O statistics by backend type, object, and context. Availability/columns depend on the major version.

~~~sql
SELECT
    backend_type,
    object,
    context,
    reads,
    read_time,
    writes,
    write_time,
    extends,
    fsyncs,
    fsync_time
FROM pg_stat_io
ORDER BY backend_type, object, context;
~~~

### 21.1. Backend type

Distinguish client backends, autovacuum workers, background writer, checkpointer, and other backend types depending on version.

### 21.2. Object and context

Helps inspect I/O related to relations, temporary files, or contexts such as normal/bulkread/bulkwrite per catalog version.

### 21.3. Timings

Read/write/fsync timings are only useful if I/O timing collection is supported/enabled per version/config. Check pg_settings and the major version documentation.

### 21.4. Counters and deltas

Take snapshots over time to calculate rates. A large counter after many days does not prove a current bottleneck.

### 21.5. Combine with OS metrics

pg_stat_io does not replace OS/cloud disk metrics. Combine device latency, throughput, queue, filesystem, and volume throttling.

## 22. track_io_timing and Timing Overhead

PostgreSQL can collect I/O timing to aid analysis.

~~~sql
SHOW track_io_timing;
~~~

### 22.1. Enabling timing

track_io_timing can be enabled depending on version and deployment policy. Measure overhead on a realistic workload before enabling broadly on latency-sensitive systems.

### 22.2. I/O time in query stats

Some statistics views/EXPLAIN outputs can display I/O timing when enabled. Use this to find queries spending time waiting on I/O.

### 22.3. Timing does not equal raw device latency

Values may reflect call/OS path time and how the platform measures it. Cross-check against independent storage metrics.

### 22.4. Virtualized storage

Cloud storage has throttling, burst credits, and a network path. Check volume limits/credits alongside disk queue.

### 22.5. When to disable?

If measured overhead is significant or instrumentation is no longer needed, adjust per policy; retain sufficient metrics for recurring performance investigations.

## 23. Query Plans: EXPLAIN and EXPLAIN ANALYZE

EXPLAIN shows how the planner intends to execute a query. EXPLAIN ANALYZE actually runs the query and reports actual rows/timing; only use it when execution side effects and load have been considered.

~~~sql
EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS)
SELECT
    customer_id,
    count(*)
FROM public.orders
WHERE created_at >= now() - interval '7 days'
GROUP BY customer_id;
~~~

### 23.1. Estimated rows and actual rows

Large discrepancies between estimated rows and actual rows can cause the planner to choose an unsuitable join/order strategy. Check statistics, skew, and correlation.

### 23.2. Cost is not milliseconds

Planner cost is a relative unit used to compare plans based on cost parameters. Do not read cost=1000 as 1000 ms.

### 23.3. Buffers

BUFFERS shows shared/local/temp buffer hits/reads/writes at plan nodes. It helps identify plans reading many pages, though a shared read is not necessarily a physical disk read.

### 23.4. WAL

Depending on version and statement, the WAL option can show WAL records/FPI/bytes generated by execution. Useful for write-heavy statements.

### 23.5. SETTINGS

Displays non-default planner-related settings affecting the plan. Useful for detecting session-level tuning or environment differences.

## 24. Reading Plan Nodes to Find Cost

A plan should be read from the root down to child nodes, comparing estimated/actual rows, loops, buffers, and time.

### 24.1. Seq Scan

Seq Scan reads pages of a relation sequentially. Suitable for small tables or queries needing most rows; can be expensive if the table is large and filter selectivity is high.

### 24.2. Index Scan and Index Only Scan

Index Scan uses an index to locate tuples but may access the heap many times. Index Only Scan can avoid heap fetches when the visibility map allows.

### 24.3. Bitmap Heap Scan

A Bitmap plan can group heap locations and then read pages more efficiently for many matches. It is not always faster than Index Scan.

### 24.4. Nested Loop

Nested Loop can work well when the outer side is small and the inner lookup has an index. If outer rows are large, many inner loops can cause substantial random I/O.

### 24.5. Hash Join and Merge Join

Hash Join builds a hash table and can spill; Merge Join requires inputs sorted by join keys. Plan choice depends on cardinality, memory, and ordering.

### 24.6. Sort and Aggregate

Sort/HashAggregate can consume memory/temp I/O. Inspect sort method, memory, disk usage, and rows processed.

## 25. Query-Plan Red Flags

A node with high execution time is not automatically a bug; you need to understand the data and query semantics.

### 25.1. Large row estimate discrepancies

Wrong planner estimates can result from stale statistics, skew, correlated columns, or parameter-sensitive plans.

### 25.2. Very high loops

A Nested Loop with an inner scan repeated hundreds of thousands of times can generate a lot of work. Check indexes, join order, and cardinality.

### 25.3. Large rows removed by filter

Many rows read and then discarded can suggest an index/selectivity problem, though a seq scan may still be reasonable if most of the table is needed.

### 25.4. Sort spill

Sort Method external merge or large temp blocks indicate the sort is using disk. Consider an index/ordering, reducing rows earlier, or memory policy.

### 25.5. Heap fetches on Index Only Scan

High heap fetches can occur when the visibility map is not sufficiently all-visible, often linked to update churn/vacuum. Index Only Scan does not guarantee zero heap I/O.

## 26. Query Optimization or Resource Scaling?

Not every bottleneck is solved by adding CPU/RAM/disk.

### 26.1. Query-specific bottleneck

A single query accounts for most of total_exec_time or generates many reads/temp files. Optimizing SQL/indexes/plans usually has a direct impact.

### 26.2. System-wide bottleneck

Many independent queries slow down simultaneously, with rising resource saturation and queueing. Scaling or workload isolation may be needed.

### 26.3. Connection/pool bottleneck

The application waits for a connection while the database still has headroom. Adjust pool sizing, concurrency, and transaction lifecycle before scaling the database.

### 26.4. Lock bottleneck

Latency rises due to a blocker transaction. Adding CPU will not make locks release faster if transaction logic does not change.

### 26.5. Storage bottleneck

If the query plan is already sound but storage latency/throttling is high, consider storage tier, IOPS/throughput limits, data locality, and caching strategy.

## 27. Checkpoint and WAL Pressure

Write-heavy workloads can be impacted by WAL generation, checkpoint cadence, and storage write throughput.

### 27.1. WAL generation rate

Bulk loads, UPDATE/DELETE churn, index builds, and frequent commits can generate heavy WAL. Monitor pg_stat_wal and archive/replication rates per version.

### 27.2. Checkpoint activity

Checkpoints write dirty buffers and generate I/O. Checkpoints that are too frequent or write bursts can increase latency; review checkpoint stats/logs per major version.

### 27.3. max_wal_size

max_wal_size is a soft limit related to checkpoint scheduling, not an absolute hard cap for pg_wal. Archive/replication slots and checkpoint conditions affect actual retention.

### 27.4. checkpoint_timeout and completion target

These settings control checkpoint timing and pacing. Tuning must be based on WAL rate, storage throughput, and recovery requirements.

### 27.5. Full-page images

After a checkpoint, page modifications can generate full-page images in WAL depending on wal_log_hints/checksum/full_page_writes conditions. Workload write patterns affect WAL volume.

## 28. Vacuum and Autovacuum as a Workload

Vacuum is necessary work to reclaim reusable space, maintain the visibility map, and prevent transaction ID wraparound. It consumes I/O/CPU and can compete with foreground queries.

### 28.1. Update/delete churn

Tables with heavy updates/deletes generate dead tuples. Autovacuum must run fast enough to keep up with churn.

### 28.2. Long-running transactions

Old snapshots can prevent vacuum from removing tuple versions. Locate long transactions and idle-in-transaction sessions.

### 28.3. Autovacuum workers

Monitor worker count, vacuum duration, table size, dead tuples, and logs. Increasing workers can increase concurrent I/O; capacity is required.

### 28.4. Analyze

Planner statistics need to be kept up to date. Analyze can become a bottleneck if tables are large and statistics targets are high, but stale stats also lead to poor query plans.

### 28.5. Vacuum is not always the root cause

An autovacuum running at the same time as a latency spike is only correlation. Confirm with I/O/CPU, table activity, and the timeline before changing settings.


## 29. Connection Bottlenecks and Connection Pooling

Each PostgreSQL connection typically corresponds to one backend process. Too many concurrent connections can increase memory usage, process scheduling overhead, and contention.

### 29.1. Connection count

Monitor total sessions, active, idle, idle in transaction, and connection counts by application_name/user. Compare against max_connections and reserved slots.

~~~sql
SELECT
    application_name,
    usename,
    state,
    count(*) AS sessions
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY application_name, usename, state
ORDER BY sessions DESC;
~~~

### 29.2. Active sessions do not equal useful throughput

Many active sessions may all be waiting on locks or I/O. Measure completed TPS and wait events rather than just counting active connections.

### 29.3. Pool wait time

If the app pool runs out of connections, requests wait in the application before reaching PostgreSQL. Instrument pool acquisition latency and queue length.

### 29.4. Pool sizing

Choose pool size based on database capacity, query concurrency, and number of application instances. An oversized pool per pod can multiply into thousands of connections.

### 29.5. PgBouncer

A connection pooler can reduce backend count and connection churn. Transaction pooling has limitations with session state, temp tables, prepared statements, and session-level features; verify application compatibility.

## 30. Network Bottleneck

The network can limit query responses, replication, backups, or app-to-database throughput.

### 30.1. Latency and bandwidth

RTT affects round trips for chatty queries. Bandwidth limits large result sets, COPY, replication, and backups.

### 30.2. Query result size

A query returning millions of rows may execute quickly on the database yet have a slow client response due to network and serialization. Only return columns/rows the application actually needs.

### 30.3. Client-side processing

The application may read the entire result and then process it sequentially. Measure database execution time, transfer time, and application processing time separately.

### 30.4. Packet loss and retransmits

Packet loss/retransmissions increase latency even before average bandwidth reaches its limit. Monitor network metrics at both the host and cloud/network layer.

### 30.5. Cross-region calls

Database round trips across regions have high RTT. Reduce chatty queries, batch operations appropriately, or place the application near the database.

## 31. Replication and Backup as Workload Consumers

Replication/backups also consume CPU, disk, and network on the same infrastructure.

### 31.1. WAL sender/receiver

Physical replication ships WAL continuously; logical replication decodes/applies changes. Monitor sender/receiver lag and network throughput.

### 31.2. Logical decoding

Logical decoding has a CPU/I/O cost, and replication slots retain WAL. A slow consumer can cause retained WAL to grow.

### 31.3. Backup load

Base backups and logical dumps read many pages, generate network egress, and can compete with query workloads.

### 31.4. Archive commands

WAL archiving must complete fast enough. An archive backlog can increase pg_wal usage; check archive status and external storage latency.

### 31.5. Schedule and throttle

Schedule heavy backups/batches outside peak periods if policy permits. Use tooling bandwidth/IO limits to reduce interference while still meeting RPO/RTO.

## 32. Temp Files and Temporary I/O

Temporary files are typically created by sort/hash spills, materialization, or operations needing temp storage.

### 32.1. log_temp_files

log_temp_files can be configured to log temp files exceeding a threshold. Choose an appropriate threshold to avoid creating excessive log noise.

### 32.2. Query-level attribution

Use pg_stat_statements temp_blks_written and EXPLAIN ANALYZE BUFFERS to find queries generating temp I/O.

### 32.3. Sort spill

An external sort indicates the sorted data exceeds allocated memory. You can reduce rows before sorting, add an appropriate index, or adjust memory in a controlled way.

### 32.4. Hash batches

Hash operations can use multiple batches when memory is insufficient. Check the plan output and cardinality estimates.

### 32.5. Application temp tables

Applications may create temp tables and hold sessions open for a long time. Monitor session lifecycles and temp storage; transaction pooling may be incompatible with temp table/session assumptions.


## 33. Query Planning and Statistics Problems

A slow query is not necessarily caused by a lack of resources. The planner may choose an unsuitable plan due to statistics or parameter behavior.

### 33.1. Stale statistics

Changing data distribution without running analyze can skew estimates. Check last_autoanalyze, n_mod_since_analyze, and the plan.

### 33.2. Data skew

One tenant/key may have far more rows than the rest. Histogram/MCV stats may not fully capture skew or correlated columns.

### 33.3. Extended statistics

Extended statistics can help the planner estimate dependencies, n-distinct, or most-common value combinations across multiple columns. Create them based on query/data evidence, then analyze.

### 33.4. Generic and custom plans

Prepared statements may use a generic plan or a custom plan depending on behavior/version/settings. A plan good for an average parameter can be very bad for a large tenant.

### 33.5. Plan regression

After deploys, data growth, analyze, version upgrades, or parameter changes, plans can change. Save representative EXPLAIN outputs and query latency history.

## 34. Index Workload and Write Amplification

Indexes help reads but make writes more expensive.

### 34.1. Index maintenance

INSERT/UPDATE/DELETE must update related indexes. Many indexes on a write-heavy table increase WAL, CPU, and storage I/O.

### 34.2. Unused indexes

Rarely used indexes still consume disk/cache and add write cost. Check pg_stat_user_indexes, but verify reset windows, constraints, and periodic jobs before dropping.

### 34.3. Missing indexes

Lookup/selective filter queries without an index may scan many rows. Index design must align with predicates, joins, ordering, and data distribution.

### 34.4. Index bloat

Index bloat increases pages read and cache footprint. Perform index maintenance based on evidence; REINDEX can cause I/O/space spikes and requires planning.

### 34.5. Covering indexes

INCLUDE columns can support index-only access but increase index size/write cost. Only add columns valuable to important workloads.

## 35. Partitioning and Workload Distribution

Partitioning can reduce scan/maintenance scope and support retention, but does not automatically make queries faster.

### 35.1. Partition pruning

Queries must have predicates compatible with the partition key so the planner eliminates unneeded partitions. Verify the actual plan.

### 35.2. Too many partitions

Many partitions can increase planning overhead, catalog size, and operational complexity. Partition count should be based on data volume/retention/query patterns.

### 35.3. Partition-wise operations

Certain joins/aggregates can execute per partition when settings and partition keys match. Check the plan and worker availability.

### 35.4. Hot partition

One partition receiving most writes can become a hotspot even when the overall database has capacity. Evaluate key distribution and partition boundaries.

### 35.5. Maintenance per partition

Vacuum/analyze/index operations and retention can be managed per partition. Maintenance schedules should avoid creating simultaneous I/O bursts.

## 36. Workload Interference and Resource Isolation

One workload can slow down another even if individual queries have no issues.

### 36.1. Noisy neighbor

Large batch scans can evict useful cache pages, consume I/O, and raise OLTP p99 latency.

### 36.2. Connection isolation

Use separate pools/users to set concurrency caps and query timeouts for reporting/batch. Separate connection pools alone do not isolate CPU/disk.

### 36.3. Read replicas

Offloading reporting/read-heavy work to replicas can reduce primary load, but replication lag, replica conflicts, and network capacity must be accounted for.

### 36.4. Scheduling

Run batch/backup/vacuum-intensive tasks during designated windows if business requirements allow. Do not delay maintenance to the point of creating bloat/wraparound risk.

### 36.5. Query governance

Set appropriate statement_timeout/lock_timeout by role/application class. Limit runaway queries and ensure timeouts do not trigger a retry storm.

## 37. Bottleneck Patterns: Symptoms and Hypotheses

| Symptom | First Hypothesis | Evidence to Look For |
|---|---|---|
| CPU 95%, high run queue | CPU saturation | Process CPU, query total time, plan |
| Low CPU, high latency | Lock/I/O/network wait | Wait events, blockers, storage |
| Increasing temp bytes | Sort/hash spill | Query stats, EXPLAIN, temp logs |
| High disk latency | Storage bottleneck | IOPS, queue, volume throttling |
| High pool wait, idle DB | Undersized app pool | Pool metrics, active sessions |
| Connections near limit | Connection pressure | Session states, pool sizing |
| Growing WAL disk | Slot/archive/checkpoint issue | Slots, archive status, WAL rate |
| Increasing replica lag | Network/replay bottleneck | Sender/receiver LSN, CPU/I/O |
| p99 spikes during batch | Workload interference | Query timeline, I/O/CPU overlap |
| One query slow after deploy | Plan regression | Query fingerprint, plan diff |

### 37.1. One symptom can have multiple causes

High latency can be caused by connection waits, locks, I/O, or CPU. Select a hypothesis only after inspecting wait/resource evidence.

### 37.2. One cause can have multiple symptoms

Storage saturation can slow down queries, delay autovacuum, lengthen checkpoints, and increase replication lag.

### 37.3. Identify the primary bottleneck

Find the resource or dependency whose limitation prevents throughput from increasing. Secondary bottlenecks may disappear once the primary bottleneck is resolved.

### 37.4. Do not confuse correlation with causation

CPU and latency rising together can be due to a traffic spike; CPU may be the cause or the effect of a retry storm. A timeline and controlled test are required.

### 37.5. Record confidence

Distinguish measured facts, hypotheses, and confirmed causes. Without evidence, do not label something as the root cause.

## 38. Systematic Bottleneck Investigation Workflow

A consistent workflow helps avoid changing multiple parameters at once.

1. Identify the affected service/workload and violated SLO.
2. Select the start/end time window and record workload events.
3. Identify relevant query fingerprints, applications, and tenants.
4. Collect PostgreSQL sessions, wait events, locks, and statistics deltas.
5. Collect OS CPU/memory/disk/network and cloud storage metrics.
6. Categorize the bottleneck hypothesis: CPU, memory, I/O, lock, connection, network, WAL, or plan.
7. Inspect query plans and data distribution when query-specific.
8. Apply one small controlled change or run a reproducible benchmark.
9. Compare latency, throughput, resource usage, and side effects.
10. Keep or roll back the change according to defined criteria.
11. Update dashboards/alerts/runbooks and the capacity model.

### 38.1. Identify impact first

Select the query class, API, database, or tenant with failing SLOs. Do not tune the entire cluster when only one report query is slow.

### 38.2. Collect over the same time window

Gather application traces, pg_stat_statements deltas, pg_stat_activity samples, and OS metrics with aligned timestamps.

### 38.3. Check for workload changes

Traffic rate, data size, deployments, batch jobs, query parameters, or cache warmness may have changed.

### 38.4. Formulate a specific hypothesis

For example: p99 increased because query X switched from an index scan to a seq scan after data growth. A good hypothesis specifies expected metrics/plans to verify.

### 38.5. One variable at a time

Change an index, query, work_mem, or storage configuration step by step whenever possible. Multiple simultaneous changes make it impossible to attribute the cause.


## 39. Confirming Bottlenecks with Controlled Experiments

A hypothesis only becomes a conclusion when it can be reproduced or verified via controlled changes.

### 39.1. Choose a representative workload

Use a query mix, parameter distribution, concurrency, and data volume close to production. A single query does not simulate a mixed workload.

### 39.2. Hold other variables constant

Keep version, schema, dataset, hardware, storage, connection pool, cache state, and background jobs as constant as possible.

### 39.3. Measure before and after

Record throughput, p50/p95/p99 latency, CPU, memory, disk, network, locks, temp I/O, and WAL. A good change must improve the SLO without causing severe regressions in other workloads.

### 39.4. Repeat

Run multiple iterations to distinguish noise from a steady change. Clearly note warm-cache and cold-cache scenarios.

### 39.5. Rollback criteria

Define rollback conditions in advance: rising p99, rising error rate, abnormal WAL/slot growth, shrinking disk headroom, or replica lag exceeding SLO.

## 40. Benchmarking with pgbench

pgbench is a tool bundled with PostgreSQL to generate transaction workloads and measure throughput/latency.

~~~bash
pgbench -i -s 50 appdb
pgbench -c 32 -j 8 -T 300 -P 10 appdb
~~~

The commands above are lab examples. Initialize will create/write benchmark data; do not run on a production database.

### 40.1. Scale factor

The scale factor affects dataset size. The dataset must be large enough to exercise the cache/storage behavior you want to measure.

### 40.2. Clients and threads

-c sets the number of clients, -j sets the number of pgbench worker threads. Increase clients to find the saturation point, rather than assuming more is always better.

### 40.3. Duration and progress

-T sets test duration; -P prints progress intervals. Run long enough to observe steady state and checkpoint/maintenance effects.

### 40.4. Latency and TPS

Record TPS, average/percentile latency if provided in output, failed transactions, and connection behavior. Compare using identical options and environment.

### 40.5. Custom scripts

Use pgbench scripts to simulate a transaction mix close to your application: reads, writes, think time, and parameter distributions.

## 41. Benchmarks Differ from Production

A benchmark may look great while production remains slow if the workload is not equivalent.

### 41.1. Data shape

Benchmark datasets are often more uniform than production. Skew, hot tenants, large rows, and long-tail queries can be missed.

### 41.2. Cache state

Warm-cache tests may not reflect restart/failover/cold-start behavior. Explicitly document cache conditions.

### 41.3. Concurrency pattern

Production exhibits burstiness, retries, pool waits, external API latency, and user think time. Constant-rate load does not simulate everything.

### 41.4. Background activity

Autovacuum, checkpoints, backups, replication, and scheduled jobs can create interference. Include representative background tasks in tests when appropriate.

### 41.5. Test environment parity

CPU generation, storage class, network, kernel, PostgreSQL version, and config must be similar enough for results to be meaningful.

## 42. Capacity Planning from Workloads

Capacity planning estimates the resources needed to meet current workloads and projected growth.

### 42.1. CPU capacity

Estimate CPU seconds/transaction and peak TPS. Reserve headroom for bursts, maintenance, failover catch-up, and background jobs.

### 42.2. Memory capacity

Account for shared_buffers, OS cache, backend private memory, concurrent sort/hash operations, maintenance workers, and OS reserve. Do not simply multiply work_mem by max_connections.

### 42.3. Storage capacity

Account for data, indexes, WAL, temp files, backups, archive staging, bloat, and growth/retention. Separate capacity from IOPS/throughput requirements.

### 42.4. Network capacity

Estimate query result egress, replication/WAL, backup transfers, and cross-region traffic. Add burst/headroom and protocol overhead.

### 42.5. Growth model

Use trends in data volume, TPS, index growth, and tenant count. Build monthly/quarterly forecasts and validate against actuals.

## 43. Headroom and Saturation Point

Do not operate continuously near resource limits if the workload has bursts or failure modes.

### 43.1. Headroom

Keep capacity in reserve for peak traffic, vacuum/checkpoint, backups, replication catch-up, and failover. Exact headroom depends on workload/SLO.

### 43.2. Saturation curve

Run increasing load and record throughput/latency. The saturation point is typically where throughput nearly stops growing while latency/queue rises rapidly.

### 43.3. Safe operating range

Set operating limits below the saturation point to provide a buffer for bursts. A node may reach 100% CPU in a benchmark, but that is not a continuous operating target.

### 43.4. Failover capacity

When the primary fails, the surviving node may have to absorb the entire workload while running catch-up/maintenance. HA capacity must be tested under failure modes.

### 43.5. Scale trigger

Define triggers based on sustained latency, queue, resource utilization, disk forecast, and growth rate; avoid scaling solely for a brief spike.


## 44. Evidence-Based Parameter Tuning

Parameter tuning must follow the specific bottleneck, PostgreSQL version, and deployment environment.

| Parameter/area | Can affect | Measure beforehand |
|---|---|---|
| shared_buffers | Buffer cache | Working set, OS cache, memory |
| work_mem | Sort/hash spill | Concurrent operations, temp files |
| max_connections | Session capacity | Pool wait, backend count, memory |
| effective_cache_size | Planner estimates | Available cache estimate |
| random_page_cost | Planner cost model | Storage/cache characteristics |
| checkpoint settings | Write pacing/WAL | WAL rate, checkpoint logs, I/O |
| autovacuum settings | Cleanup/analyze rate | Churn, dead tuples, I/O headroom |
| parallel settings | Parallel query workers | CPU headroom, query mix |

### 44.1. shared_buffers

Increase shared_buffers only when cache behavior and memory budget show a benefit. Check restart requirements and OS page cache.

### 44.2. work_mem

Adjusting it can reduce temp spills for suitable queries. Use role/session-specific settings where possible; estimate concurrency before raising the global default.

### 44.3. max_connections

Raising the limit can increase process/memory pressure. Use a pooler and concurrency control before raising the limit if the application creates too many sessions.

### 44.4. Planner cost parameters

random_page_cost/effective_cache_size affect planner estimates and do not directly speed up disk. Poor tuning can make plans worse.

### 44.5. Checkpoint/autovacuum settings

Increases/decreases must be based on WAL rate, dirty buffers, vacuum backlog, and storage capacity. Do not disable maintenance to mask symptoms.

## 45. Monitoring Dashboard and Alert Design

Dashboards need to show what state the workload is in and which resource is limiting.

### 45.1. Workload panel

TPS/QPS, query class, p50/p95/p99, errors, pool wait, active sessions, and transaction duration.

### 45.2. PostgreSQL panel

Top queries by total time, mean time, calls, temp blocks, buffers, WAL bytes, wait events, blockers, and deadlocks.

### 45.3. Host/storage panel

CPU/run queue, available memory/swap, disk latency/IOPS/throughput/queue, filesystem free space, and network throughput/retransmits.

### 45.4. Maintenance/replication panel

Autovacuum activity, dead tuples, checkpoint/WAL rate, archive lag, replication lag, and slot retention.

### 45.5. SLO- and trend-based alerts

Alert on sustained p99/throughput/error violations, disk forecast, slot WAL growth, blocked transaction age, and replica freshness. Set duration/thresholds to reduce noise.

## 46. Anti-Patterns When Finding Bottlenecks

1. Increasing shared_buffers just because RAM has free space.
2. Increasing work_mem globally because one query spills.
3. Increasing max_connections to cure pool waits.
4. Creating an index for every filter without accounting for write amplification.
5. Running EXPLAIN ANALYZE on statements with side effects or under uncontrolled load.
6. Treating blks_read as guaranteed physical disk reads.
7. Assuming low CPU means the database has no bottleneck.
8. Assuming high CPU always means more cores are needed.
9. Killing the longest-running backend without checking the blocker/transaction owner.
10. Disabling autovacuum to reduce I/O.
11. Running backups/batches during peak without measuring interference.
12. Benchmarking on a dataset that is too small or with an always-warm cache.
13. Comparing cumulative metrics instead of deltas/rates.
14. Reading a single wait event snapshot as the full history.
15. Changing multiple parameters at once and then not knowing which change worked.
16. Optimizing average latency while ignoring p99.
17. Looking only at query time without measuring pool wait/network/application time.
18. Scaling storage without identifying whether IOPS, throughput, or latency is the limit.
19. Scaling CPU while queries are waiting on locks.
20. Having no rollback criteria or post-change monitoring.

## 47. Lab: Workload Classification and Establishing a Baseline

Use a test database with a query mix close to a real application.

### 47.1. Describe the workload

List API transactions, reporting queries, batch writes, and background maintenance. Record frequency, concurrency, read/write mix, and freshness requirements.

### 47.2. Collect a baseline

Capture pg_stat_database, pg_stat_user_tables, pg_stat_activity, pg_stat_statements, and OS metrics during a peak window.

### 47.3. Mark events

Record deployments, batches, vacuum, backups, and traffic spikes on the same timeline.

### 47.4. Create a workload profile

Summarize TPS, p50/p95/p99, active sessions, top queries, temp bytes, CPU, memory, disk, and network.

### 47.5. Formulate a hypothesis

Select one bottleneck with evidence, state which metric should change if the hypothesis is true, and what would refute it.

## 48. Lab: Finding CPU, I/O, and Lock Bottlenecks

### 48.1. CPU workload

Run aggregate/join queries on a lab dataset, increasing concurrency step by step. Monitor process CPU, run queue, TPS, and latency.

### 48.2. I/O workload

Use a dataset larger than memory cache or scan many pages. Monitor wait events, pg_stat_io (PostgreSQL 16+), storage latency, and queue.

### 48.3. Lock workload

Open a transaction updating a row and hold the transaction open in the lab. From another session, update the same row and inspect pg_blocking_pids/pg_stat_activity.

### 48.4. Compare symptoms

Record CPU, I/O waits, lock waits, and latency in each test. Identify why the same high-latency symptom has different causes.

### 48.5. Cleanup

Rollback/commit lab transactions and stop the workload generator. Do not leave sessions holding locks/snapshots after the test.


## 49. Lab: Finding Expensive Queries and Verifying Tuning

### 49.1. Collect top queries

Use pg_stat_statements to find queries by total_exec_time, calls, mean time, temp blocks, and shared reads.

### 49.2. Capture plans

Run EXPLAIN first; use EXPLAIN ANALYZE in the lab when safe. Record estimated/actual rows, loops, buffers, temp I/O, and execution time.

### 49.3. Try one change

For example, update statistics, fix a predicate, add an appropriate index, or reduce rows before sorting. Change only one variable at a time.

### 49.4. Re-benchmark

Run with the same data, query parameters, concurrency, and cache conditions. Compare p95/p99, throughput, and resource consumption.

### 49.5. Record trade-offs

An index may improve SELECT while slowing down INSERT/UPDATE. Evaluate the full query mix before keeping the change.

## 50. Bottleneck Identification Checklist

- [ ] Have workload classes and SLOs been defined?
- [ ] Is there a sufficiently long baseline with synchronized timestamps?
- [ ] Have throughput, p50/p95/p99, and queue depth been measured?
- [ ] Are top query fingerprints/calls/total time known?
- [ ] Have wait events and blocking chains been checked?
- [ ] Are CPU/run queue/memory/swap data available for the same time window?
- [ ] Have storage latency/IOPS/throughput/queue been measured?
- [ ] Have network/pool wait/result size been reviewed?
- [ ] Are WAL/checkpoint/autovacuum/replication causing interference?
- [ ] Have query plans and estimated/actual rows been cross-checked?
- [ ] Does the hypothesis have supporting evidence and a way to refute it?
- [ ] Does the representative benchmark share the same workload/data shape?
- [ ] Are rollback criteria and post-change monitoring in place?
- [ ] Are SLOs and capacity headroom met after the change?

## 51. Quick Reference Table

| Component | Used to Understand |
|---|---|
| OLTP | Small transactions, latency-sensitive |
| OLAP | Large data scans/joins/aggregates |
| Throughput | Work completed per unit of time |
| p95/p99 latency | Tail response time |
| pg_stat_database | Database-level counters |
| pg_stat_user_tables | Table scans, tuples, vacuum/analyze |
| pg_stat_statements | Query-level aggregates |
| pg_stat_activity | Sessions, states, waits |
| pg_blocking_pids | Blocking sessions |
| pg_stat_io | I/O stats by backend/object/context on PostgreSQL 16+ |
| pg_stat_wal | WAL activity stats by version |
| EXPLAIN | Estimated execution plan |
| EXPLAIN ANALYZE | Actual execution and timing |
| BUFFERS | Buffer activity in plan |
| work_mem | Base memory budget for a sort/hash operation |
| shared_buffers | PostgreSQL shared buffer cache |
| max_connections | Client connection limit |
| IOPS | Storage operations/second |
| Throughput | Bytes/second |
| Queue depth | Pending/in-progress I/O requests |
| WAL | Write-Ahead Log |
| Checkpoint | Writing dirty buffers by checkpoint process |
| Autovacuum | Automatic cleanup/analyze |
| Connection pool | Reusing and limiting sessions |
| Bottleneck | Resource/dependency limiting throughput or latency |
| Headroom | Reserve capacity below saturation |
| pgbench | Benchmark workload generator |

## 52. Conclusion

**Classify the workload first, measure the bottleneck next, and only then choose how to optimize.** OLTP, OLAP, reporting, and batch have different goals; describe them by query mix, transaction duration, throughput, latency percentiles, concurrency, data distribution, and consistency requirements. Baselines must cover peak windows and be plotted on the same timeline as deployments, backups, vacuum, and batch events.

PostgreSQL provides statistics views to understand database/query activity; OS and storage metrics show where the host is constrained; EXPLAIN/EXPLAIN ANALYZE help find plan nodes and cardinality errors. High CPU, I/O waits, lock waits, pool waits, temp files, and WAL pressure require different lines of investigation. A slow query is not necessarily a resource shortage, and low host CPU does not mean the database has no bottleneck.

An effective workflow is to identify SLO/impact, collect synchronized metrics, form a specific hypothesis, verify with plans or controlled benchmarks, change one variable at a time, and re-measure the full workload. Capacity planning must include peaks, background maintenance, replication, backups, failover, and headroom. Tuning shared_buffers, work_mem, max_connections, or storage is only meaningful when backed by evidence of the limit being hit.

Operational principle: **measure the right workload, separate execution from waiting, identify bottlenecks using multiple data sources, and prove improvements with representative benchmarks alongside SLOs.**
