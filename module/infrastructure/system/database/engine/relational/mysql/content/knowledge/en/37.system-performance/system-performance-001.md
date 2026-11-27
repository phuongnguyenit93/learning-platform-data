# Distinguishing CPU, I/O, Memory, Lock, and Network Bottlenecks

In the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, execution plan reading, query optimization, privilege management, backups, and handling relational database operational issues. When MySQL is slow, the symptoms at the application level often look the same: long-running requests, timeouts, growing queues, and dropping throughput. However, the root cause may lie in CPU, storage devices, memory, lock contention, or network links. Choosing the wrong layer as the cause often leads to ineffective configuration changes, or even makes the system more unstable.

This lesson guides you on how to distinguish five bottleneck categories by combining MySQL metrics with operating system and application metrics. Each category is examined through its symptoms, measurements, inspection commands, and remediation approaches. The goal is to identify which resource is saturated or building a queue, then verify the hypothesis with data from the same time window.

## 1. Objectives and Diagnostic Principles

After this lesson, learners will be able to:

- Distinguish CPU saturation, storage I/O pressure, memory pressure, lock contention, and network bottlenecks.
- Collect status counters and Performance Schema data appropriate for each hypothesis.
- Correlate MySQL metrics with host or container CPU, RAM, disk, and network metrics.
- Recognize commonly misinterpreted metrics, such as `Threads_running`, buffer pool hit ratio, or `SUM_TIMER_WAIT`.
- Locate statements, files, transactions, or connections associated with slowdowns.
- Establish a baseline, take time-windowed snapshots, and compute deltas.
- Select remediation actions based on evidence and verify effectiveness after changes.

### 1.1. A Bottleneck Is a Resource Limiting Throughput or Latency

A resource becomes a bottleneck when demand approaches or exceeds available capacity, forcing work to wait. CPU may saturate, storage devices may develop long I/O queues, memory exhaustion may cause the OS to swap, transactions may wait on locks, or clients may wait for data over the network.

Not every high metric proves a bottleneck:

- High CPU may reflect a legitimate workload increase; inspect run queue, processing time, and latency.
- High disk throughput may mean the device is working efficiently; inspect latency and queue depth.
- A high buffer pool hit ratio does not rule out log write or flush I/O bottlenecks.
- High `Threads_running` does not mean every thread is consuming CPU; some threads may be waiting.
- High socket waits do not by themselves prove an external network failure; the server may be waiting for clients to read results.

Look for the relationship between demand, queues, wait times, and impact on requests.

### 1.2. Measure the Same Time Window

A meaningful comparison should record:

- Start and end timestamps.
- MySQL uptime and time of the most recent restart.
- Throughput, connection count, and workload type.
- CPU, memory, disk latency, and network metrics.
- Prominent statements, wait events, and transactions.
- Deployments, backups, batch jobs, or configuration changes within the same window.

Do not compare a cumulative counter since server startup against an OS chart covering only one minute. For cumulative counters, take two snapshots and calculate the difference.

## 2. General Triage Workflow

When receiving a report that MySQL is slow, follow this sequence:

1. Confirm scope: one endpoint, one tenant, one SQL query, all connections, or the entire instance.
2. Confirm timing: when the issue started, whether it is continuous or periodic.
3. Measure impact: request latency, timeouts, throughput, queue depth, and connection count.
4. Check the host: CPU, run queue, RAM, swap, disk latency, IOPS, network errors, and retransmissions.
5. Check MySQL: `Threads_running`, connection counters, InnoDB status, Performance Schema waits, and statement summaries.
6. Identify the dominant wait category: CPU execution, file I/O, memory reclaim, lock, or socket.
7. Locate the specific object: statement digest, file instance, transaction, metadata lock, or client connection.
8. Formulate a testable hypothesis and choose one next measurement.
9. Change only one group of factors per test whenever possible.
10. Compare before and after on an equivalent workload; roll back if results worsen.

### 2.1. Diagnostic Flowchart

~~~mermaid
flowchart TD
    A[MySQL slow or timing out] --> B[Measure latency and throughput]
    B --> C[Correlate CPU, RAM, disk, network]
    C --> D{Which resource has a queue or prominent waits?}
    D -->|CPU| E[Top process, run queue, statement digest]
    D -->|Disk I/O| F[Disk latency, IOPS, file summary, InnoDB]
    D -->|Memory| G[Available RAM, swap, OOM, memory summary]
    D -->|Locks| H[Data lock, metadata lock, transaction]
    D -->|Network| I[RTT, retransmit, socket waits, bytes]
    E --> J[Verify hypothesis]
    F --> J
    G --> J
    H --> J
    I --> J
    J --> K[Controlled change and re-measure]
~~~

### 2.2. Collecting Initial MySQL Status

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Uptime',
    'Questions',
    'Queries',
    'Threads_connected',
    'Threads_running',
    'Max_used_connections',
    'Connections',
    'Aborted_connects',
    'Bytes_received',
    'Bytes_sent',
    'Innodb_buffer_pool_read_requests',
    'Innodb_buffer_pool_reads',
    'Innodb_data_reads',
    'Innodb_data_writes',
    'Innodb_data_read',
    'Innodb_data_written',
    'Innodb_log_waits',
    'Innodb_row_lock_waits',
    'Innodb_row_lock_time',
    'Innodb_deadlocks'
);
~~~

Some status variables may differ by version or storage engine. If a name is missing, check the variable list for your exact version. Save the output with a timestamp and take a second snapshot after a representative workload window.

### 2.3. Do Not Infer from a Single Snapshot

`Threads_running` equal to 80 at a single point in time does not tell you what those 80 threads are doing. `Innodb_buffer_pool_reads` accumulated since boot also does not show the current physical read rate. A large `Bytes_sent` may simply reflect that the server has been running for a long time.

For cumulative counters:

~~~text
delta_counter = new_counter - old_counter
rate_per_second = delta_counter / elapsed_seconds
~~~

If the server restarted, counters were reset, or Performance Schema was reset during the measurement window, do not subtract directly. Record uptime and reset boundaries.

## 3. Identifying CPU Bottlenecks

A CPU bottleneck occurs when CPU demand exceeds available capacity for a sustained period. MySQL may be processing heavy joins, sorts, expressions, JSON operations, encryption, condition evaluations, or an excessive number of statements.

### 3.1. Common Symptoms

- Host user/system CPU stays high while latency increases.
- Run queue grows and the `mysqld` process consumes most of the CPU.
- Throughput does not increase even as the number of active threads rises.
- SQL queries have high `rows examined`, sorts, joins, or CPU-intensive expressions.
- CPU drops noticeably when the SQL workload decreases, while disk latency and network remain normal.

Short bursts of high CPU are not enough to draw a conclusion. Compressed backups, replication apply, antivirus, or another process may also consume CPU.

### 3.2. Checking on Linux

~~~bash
uptime
top -H -p "$(pidof mysqld)"
pidstat -u -p "$(pidof mysqld)" 1
vmstat 1
~~~

- `uptime` shows load average, which must be compared against the number of logical CPUs.
- `top -H` displays threads and CPU usage of the `mysqld` process.
- `pidstat` tracks per-process CPU utilization.
- `vmstat` shows the run queue, blocked processes, and CPU breakdown.

With appropriate permissions and tools, `perf top` or a profiler can help identify functions consuming CPU. Production profiling requires evaluating overhead and following operational procedures.

On Windows, use Task Manager or Performance Monitor to monitor `mysqld` CPU, total CPU, processor queue length, and competing processes. In containers, compare CPU usage against quota/CPU limits; a container can be throttled even when the host still has idle CPU.

### 3.3. Reading MySQL Metrics

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Threads_running',
    'Threads_connected',
    'Questions',
    'Queries',
    'Slow_queries',
    'Created_tmp_tables',
    'Created_tmp_disk_tables',
    'Select_scan',
    'Sort_rows',
    'Sort_merge_passes'
);
~~~

These variables are workload signals, not a CPU meter. For example, `Threads_running` counts threads that are not sleeping, including some threads that are waiting. Correlate them with process CPU and wait events.

### 3.4. Finding Time-Consuming Statements

~~~sql
SELECT
    SCHEMA_NAME,
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 2) AS total_elapsed_seconds,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS average_elapsed_seconds,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    SUM_SORT_ROWS,
    SUM_CREATED_TMP_TABLES,
    SUM_CREATED_TMP_DISK_TABLES
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

`SUM_TIMER_WAIT` measures statement elapsed time, not pure CPU time. This time may include I/O or lock wait time. Use it to identify candidates for investigation, then correlate with wait events and OS CPU metrics.

### 3.5. Handling CPU Bottlenecks

- Optimize query plans to reduce rows examined, join fan-out, and unnecessary sorts.
- Add or adjust indexes after evaluating selectivity and write overhead.
- Avoid calling the same lookup repeatedly; consider batching or appropriate caching.
- Reduce N+1 queries at the application layer.
- Inspect expressions, implicit type conversions, functions, and large data processing in SQL.
- Adjust concurrency and connection pools if too many queries compete for CPU.
- Add CPU or scale the instance when a legitimate workload exceeds machine capacity.

Do not increase thread counts or `max_connections` merely because CPU is high. More concurrent queries can worsen CPU contention.

## 4. Identifying Storage I/O Bottlenecks

A storage bottleneck occurs when reading or writing data, redo logs, binary logs, temporary files, or tablespaces must wait on storage devices. Throughput may be high or low; the key metrics are latency, queue depth, IOPS, and I/O type.

### 4.1. Common Symptoms

- Disk await/latency increases during the same period MySQL slows down.
- Device queue length grows or I/O utilization nears saturation.
- MySQL shows increasing file I/O waits, especially on data files or log files.
- InnoDB frequently performs physical reads because the working set does not fit in the buffer pool.
- Slow flushes or redo log writes force transaction commits to wait.
- On-disk temporary tables rise alongside query latency.

A device with high `%util` is not necessarily a bottleneck on every storage type; SSD, NVMe, SAN, and cloud volumes behave differently. Examine latency and queue depth alongside platform IOPS/throughput limits.

### 4.2. Checking on Linux

~~~bash
iostat -xz 1
vmstat 1
pidstat -d -p "$(pidof mysqld)" 1
~~~

`iostat -xz` reports per-device read/write throughput, await, queue depth, and utilization. `pidstat -d` shows which processes are performing I/O. `vmstat` shows blocked processes and swap activity.

In cloud or container environments, also collect volume latency, burst balance, IOPS/throughput throttling, and host-level storage metrics. On Windows, use Performance Monitor to track `Avg. Disk sec/Read`, `Avg. Disk sec/Write`, `Disk Reads/sec`, `Disk Writes/sec`, and queue length.

### 4.3. Checking the InnoDB Buffer Pool

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Innodb_buffer_pool_read_requests',
    'Innodb_buffer_pool_reads',
    'Innodb_data_reads',
    'Innodb_data_writes',
    'Innodb_data_read',
    'Innodb_data_written',
    'Innodb_buffer_pool_pages_dirty',
    'Innodb_buffer_pool_pages_flushed',
    'Innodb_log_waits'
);
~~~

- `Innodb_buffer_pool_read_requests`: logical read requests from the buffer pool.
- `Innodb_buffer_pool_reads`: reads that had to fetch pages from storage because they were not in the buffer pool.
- `Innodb_data_reads` and `Innodb_data_writes`: count of InnoDB data read/write operations.
- `Innodb_data_read` and `Innodb_data_written`: cumulative bytes read/written.
- `Innodb_buffer_pool_pages_dirty`: dirty pages waiting to be flushed.
- `Innodb_log_waits`: number of times a wait occurred because the log buffer could not be written as needed.

Read deltas of these variables over the same window. A high buffer pool hit ratio does not prove all I/O is healthy: redo logs, flushing, binary logs, doublewrite, or temporary files may still be bottlenecked.

### 4.4. Viewing File I/O in Performance Schema

If file instruments are enabled and collected:

~~~sql
SELECT
    EVENT_NAME,
    FILE_NAME,
    COUNT_READ,
    SUM_NUMBER_OF_BYTES_READ,
    ROUND(SUM_TIMER_READ / 1000000000000, 3) AS read_seconds,
    COUNT_WRITE,
    SUM_NUMBER_OF_BYTES_WRITE,
    ROUND(SUM_TIMER_WRITE / 1000000000000, 3) AS write_seconds
FROM performance_schema.file_summary_by_instance
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

The `file_summary_by_instance` table aggregates activity by file instance. Results depend on enabled instruments; timer values represent measured wait time, not CPU time. You can group by `EVENT_NAME` to see which file type stands out.

### 4.5. Distinguishing Data I/O and Log I/O

Data page reads typically relate to buffer pool misses and data files. Transaction writes may involve redo logs, binary logs, doublewrite, and dirty page flushing. Slow commits are not necessarily caused by slow data file reads.

Check:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

Read the `LOG`, `BUFFER POOL AND MEMORY`, `FILE I/O`, and `TRANSACTIONS` sections. Correlate with Performance Schema file summaries and device metrics.

### 4.6. Handling I/O Bottlenecks

- Optimize queries to reduce random reads and the number of pages accessed.
- Review redundant or poorly suited indexes that increase write amplification.
- Evaluate buffer pool sizing against the working set and actual RAM.
- Inspect checkpoints, dirty pages, redo logs, and flush rates.
- Separate read/write workloads or logs architecturally when justified.
- Check storage throttling, burst credits, queues, and volume limits.
- Choose storage devices with suitable latency and IOPS.

Do not increase `innodb_buffer_pool_size` if the host is swapping or short on RAM. Do not increase log size solely because commits are slow before identifying the root cause.

## 5. Identifying Memory Bottlenecks

Memory pressure occurs when MySQL and other processes require more RAM than can be stably allocated. The OS may reclaim cache, swap, kill processes via OOM, or increase latency due to page faults.

### 5.1. Common Symptoms

- Available memory steadily drops while `mysqld` RSS grows.
- Swap in/out increases and major page faults appear.
- Kernel logs record OOM kills or memory allocation failures.
- Containers hit their memory limit even though the host has free RAM.
- MySQL raises memory allocation errors or queries fail temporarily.
- Latency rises simultaneously with memory reclaim and swap I/O.

Do not conclude RAM is exhausted just because Linux uses a lot of memory for page cache. Inspect available memory, swap activity, reclaim, process RSS, and container limits.

### 5.2. Checking the Operating System

~~~bash
free -h
vmstat 1
cat /proc/meminfo
~~~

Also check kernel logs according to permissions and environment policies:

~~~bash
dmesg -T
~~~

On Windows, use Task Manager or Performance Monitor to check `Available MBytes`, committed bytes, paging file usage, and `mysqld` working set. In containers, inspect `memory.current`, `memory.max`, or the corresponding runtime statistics.

### 5.3. Distinguishing Global Memory and Session Memory

Some MySQL settings consume global memory:

- `innodb_buffer_pool_size`.
- `innodb_log_buffer_size`.
- `key_buffer_size` if there is a MyISAM workload.
- Performance Schema memory.
- Server caches and metadata structures.

Some buffers are allocated per operation or session, such as:

- `sort_buffer_size`.
- `join_buffer_size`.
- `read_buffer_size`.
- `read_rnd_buffer_size`.
- Thread stack and connection/session overhead.
- Memory for internal temporary tables.

Do not multiply all session variables by `max_connections` and treat that as guaranteed pre-allocated RAM; many buffers are allocated only when needed. However, many concurrent sessions performing large sorts/joins can cause total memory to spike sharply.

### 5.4. Monitoring Memory in MySQL

If Performance Schema memory instruments are enabled:

~~~sql
SELECT
    EVENT_NAME,
    CURRENT_NUMBER_OF_BYTES_USED,
    HIGH_NUMBER_OF_BYTES_USED
FROM performance_schema.memory_summary_global_by_event_name
ORDER BY CURRENT_NUMBER_OF_BYTES_USED DESC
LIMIT 20;
~~~

View by account:

~~~sql
SELECT
    USER,
    EVENT_NAME,
    CURRENT_NUMBER_OF_BYTES_USED,
    HIGH_NUMBER_OF_BYTES_USED
FROM performance_schema.memory_summary_by_account_by_event_name
ORDER BY CURRENT_NUMBER_OF_BYTES_USED DESC
LIMIT 20;
~~~

Some memory summary tables only contain data when memory instrumentation is supported and enabled. Performance Schema values do not necessarily include every allocation outside instrumented scopes. Correlate with RSS/process memory and OS metrics.

You can use the `sys.memory_global_by_current_bytes` or `sys.memory_global_total` views if the `sys` schema is installed and compatible with your version.

### 5.5. Handling Memory Pressure

- Identify the largest global memory consumers and session workloads allocating buffers.
- Reduce concurrency or limit the connection pool when too many sessions run heavy queries simultaneously.
- Tune per-session buffers after measuring actual demand.
- Inspect large temporary tables and queries creating intermediate sorts/groups.
- Size the buffer pool based on RAM dedicated to the database, rather than consuming all host memory.
- Check for memory leaks or abnormal growth in processes and plugins.
- Set container memory limits with headroom and monitor OOM events.

Avoid raising session buffers across the board because a single query is slow. Larger buffers can cause many concurrent sessions to consume significantly more RAM.

## 6. Identifying Lock Bottlenecks and Concurrency Contention

Lock contention occurs when transactions must wait for other transactions to release locks. Metadata locks can also force DDL or queries to wait because a transaction is holding metadata on an object.

### 6.1. Common Symptoms

- `Threads_running` rises without a corresponding increase in CPU.
- Query latency climbs and many sessions are in `Waiting for ... lock` states.
- Some transactions remain open for a long time or have not committed/rolled back.
- Deadlocks or lock wait timeouts increase.
- DDL waits for a metadata lock and causes subsequent queries to queue behind it.
- Throughput drops as concurrent sessions increase.

This is a case easily mistaken for a CPU bottleneck: thread count increases, yet most of the time may be spent waiting on locks.

### 6.2. Checking InnoDB Lock Counters

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Innodb_row_lock_current_waits',
    'Innodb_row_lock_time',
    'Innodb_row_lock_time_avg',
    'Innodb_row_lock_time_max',
    'Innodb_row_lock_waits',
    'Innodb_deadlocks'
);
~~~

Read counter deltas over a time window. Deadlocks are events requiring analysis of transactions and lock ordering; do not just look at the total count since server startup.

### 6.3. Viewing Data Lock Waits on MySQL 8.0+

~~~sql
SELECT
    r.ENGINE_TRANSACTION_ID AS waiting_trx,
    r.OBJECT_SCHEMA,
    r.OBJECT_NAME,
    r.INDEX_NAME,
    r.LOCK_TYPE AS waiting_lock_type,
    b.ENGINE_TRANSACTION_ID AS blocking_trx,
    b.LOCK_TYPE AS blocking_lock_type
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS r
  ON r.ENGINE = w.ENGINE
 AND r.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS b
  ON b.ENGINE = w.ENGINE
 AND b.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
~~~

The `data_locks` and `data_lock_waits` tables show waiting locks and blocking locks. Join additional transaction or thread information to identify the associated sessions and SQL statements. Verify column names and availability against your version.

### 6.4. Viewing Pending Metadata Locks

~~~sql
SELECT
    OBJECT_TYPE,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    LOCK_TYPE,
    LOCK_DURATION,
    LOCK_STATUS,
    OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE LOCK_STATUS = 'PENDING';
~~~

A `PENDING` metadata lock may indicate DDL or a statement waiting on another transaction. Find the owner thread and transaction holding the lock; do not assume every slow query is caused by row locks.

### 6.5. Viewing Transactions and InnoDB Status

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

InnoDB status includes `TRANSACTIONS` and `LATEST DETECTED DEADLOCK` sections useful for inspecting waiting transactions and details of the most recent deadlock. Note that the latest deadlock record can be overwritten by a newer event.

### 6.6. Handling Lock Contention

- Shorten transactions and commit/roll back early.
- Maintain consistent table/row access order across transactions.
- Add appropriate indexes to reduce the number of rows locked during lookups or updates.
- Split large batch updates into smaller controlled batches.
- Avoid keeping transactions open while waiting on user input or external service calls.
- Review isolation levels and query ranges after understanding consistency requirements.
- Handle deadlocks with bounded retries at the application layer when operations are safely retryable.
- Schedule DDL carefully to avoid prolonged metadata locks.

Do not increase `innodb_lock_wait_timeout` as a root fix. A higher timeout only makes sessions wait longer if the blocking transaction remains unresolved.

## 7. Identifying Network Bottlenecks

A network bottleneck may lie between the application and MySQL, between MySQL and storage/network services, or at a proxy/load balancer. Network latency, packet loss, retransmissions, bandwidth limits, and excessive round trips can all slow down requests.

### 7.1. Common Symptoms

- The application is slow while MySQL CPU, RAM, and disk are not saturated.
- Connection time or result-reading time increases.
- High RTT, packet loss, or TCP retransmissions increase.
- The server sends large amounts of data over the network.
- Many small sequential queries generate excessive round trips.
- Some clients or subnets are affected while other clients remain normal.

A slow network can cause MySQL threads to wait on sockets or clients to read data slowly. However, server-side socket waits alone do not distinguish an external network issue from a client processing data slowly.

### 7.2. Checking MySQL Metrics

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Connections',
    'Threads_connected',
    'Threads_running',
    'Aborted_connects',
    'Bytes_received',
    'Bytes_sent',
    'Connection_errors_accept',
    'Connection_errors_internal',
    'Connection_errors_max_connections',
    'Connection_errors_peer_address'
);
~~~

The bytes variables are cumulative counters. Compute deltas to determine the amount of data received/sent during the window:

~~~text
delta_bytes_sent = Bytes_sent_B - Bytes_sent_A
delta_bytes_received = Bytes_received_B - Bytes_received_A
average_bytes_per_second = delta_bytes / elapsed_seconds
~~~

Check socket summary if Performance Schema socket instruments are being collected:

~~~sql
SELECT
    EVENT_NAME,
    COUNT_READ,
    SUM_NUMBER_OF_BYTES_READ,
    COUNT_WRITE,
    SUM_NUMBER_OF_BYTES_WRITE
FROM performance_schema.socket_summary_by_event_name
ORDER BY SUM_NUMBER_OF_BYTES_WRITE DESC
LIMIT 20;
~~~

Socket summary table or column names may vary by version. Some systems use `socket_summary_by_instance` to inspect individual sockets. Socket wait is socket operation time measured at the server, not an end-to-end RTT measurement.

### 7.3. Checking from the OS and Application

On Linux:

~~~bash
ss -ti
sar -n DEV,TCP,ETCP 1
ping <mysql-host>
~~~

Monitor RTT, retransmissions, drops, throughput, and TCP states. `ping` may be restricted by firewalls or network policies; ping results do not replace TCP connection measurements to the MySQL port.

On Windows, use `ping`, `tracert`, `Test-NetConnection`, and Performance Monitor to inspect network interface throughput, errors, and TCP retransmissions where appropriate counters exist.

In cloud environments, correlate network throughput, packet drops, flow logs, load balancer, and proxy metrics. Check both the path from the application to the proxy and from the proxy to MySQL.

### 7.4. Handling Network Bottlenecks

- Place the application close to MySQL in network topology and deployment zone.
- Reduce round trips with batching, prepared statements, and proper request design.
- Avoid `SELECT` queries returning unnecessary columns or rows.
- Paginate and limit result sets.
- Consider compression when payloads are large and CPU has headroom; measure compression/decompression cost as well.
- Check DNS, TLS handshakes, proxies, firewalls, NAT, and connection pools.
- Verify MTU, retransmissions, packet loss, and bandwidth limits.

Do not raise `max_allowed_packet` to fix every connection error. This variable limits the accepted packet size; it does not fix RTT, packet loss, or slow-reading clients.

## 8. Quick Comparison Table of the Five Bottleneck Categories

| Category | Host-Side Symptoms | MySQL-Side Symptoms | Confirming Measurements |
|---|---|---|---|
| CPU | High user/system CPU and run queue | Many active statements, high rows examined or expression processing | top/pidstat, statement summary, execution plan |
| Storage I/O | Rising disk await/latency and queue | File I/O waits, physical reads, flush or log waits | iostat, file_summary_by_instance, InnoDB status |
| Memory | Low available RAM, swap/reclaim/OOM | Rising memory allocation, many sessions using buffers, large temp memory | free/vmstat, process RSS, memory_summary |
| Lock | CPU may be low despite high latency | Data lock/metadata lock waits, long transactions, deadlocks | data_lock_waits, metadata_locks, innodb_trx |
| Network | Abnormal RTT/retransmit/drop/throughput | Increasing socket waits, bytes sent/received, or connection errors | ss/sar, socket summary, application tracing |

A single incident can involve multiple cascading bottlenecks. For example, a query reading too much data increases disk I/O, and then transmitting a large result set increases network time. Identify both the root cause and cascading effects.

## 9. Combining Performance Schema and sys Schema

Performance Schema provides detailed metrics on statements, waits, files, sockets, memory, and transactions. The `sys` schema presents some of this information in a more readable form.

Useful views depending on version and configuration:

- `sys.statement_analysis`: groups statements by digest and latency.
- `sys.innodb_lock_waits`: waiting transactions and blocking transactions.
- `sys.io_global_by_file_by_bytes`: files with large I/O volume.
- `sys.io_global_by_file_by_latency`: files with high I/O time.
- `sys.memory_global_by_current_bytes`: memory allocation by event.
- `sys.processlist`: sessions and current states.

Example viewing files with high I/O latency:

~~~sql
SELECT *
FROM sys.io_global_by_file_by_latency
ORDER BY total_latency DESC
LIMIT 20;
~~~

Example viewing lock waits:

~~~sql
SELECT *
FROM sys.innodb_lock_waits;
~~~

The `sys` views are built on Performance Schema and may change across releases. If a view does not exist or columns differ, check the view definition on the server in use.

## 10. Distinguishing Easily Confused Cases

### 10.1. High CPU vs. Lock Waits

High CPU with high throughput may indicate a compute-bound workload. If `Threads_running` rises while CPU stays low and many sessions show lock wait events, the issue may be contention. Check thread states and Performance Schema waits before adding CPU.

### 10.2. High I/O vs. Memory Pressure

Swap I/O caused by memory pressure differs from InnoDB data file I/O. Use `iostat` to see busy devices, but use `vmstat`, swap counters, file summaries, and process memory to tell them apart.

### 10.3. Network Wait vs. Slow Client Processing

MySQL may wait on a socket write because the client reads results slowly. Check bytes sent, result size, application traces, and client CPU. Do not conclude the network is dropping packets solely from socket waits.

### 10.4. Disk Latency vs. Commit Latency

Slow commits may involve redo log flushing or binary log synchronization. Check log waits, file summaries, and durability settings. Do not assume all slow commits are caused by data page reads.

### 10.5. Many Connections vs. CPU Exhaustion

High `Threads_connected` indicates many open connections; it does not mean all of them are active. Correlate `Threads_running`, connection pools, wait events, and CPU. Capping the pool can help prevent overload.

## 11. Building a Baseline and Comparing Before/After

A single isolated measurement is not enough to prove a change improved the system. A baseline should include:

- A representative workload and fixed measurement duration.
- Request rate, throughput, and p50/p95/p99 latency at the application tier.
- CPU utilization, run queue, and throttling.
- Available memory, swap in/out, and `mysqld` RSS.
- Disk read/write latency, IOPS, throughput, and queue depth.
- Network RTT, retransmissions, packet loss, and bytes.
- MySQL status counters, statement summaries, and wait summaries.

After a change, keep constant or document any differing factors: data volume, warm/cold cache, concurrency, client count, background jobs, and backup timing. Compare counter deltas and latency distributions, not just a single total.

### 11.1. Measurement Recording Template

| Item | Before Change | After Change |
|---|---|---|
| Measurement window | Window A | Window B |
| Request rate | Record metric | Record metric |
| p95 latency | Record metric | Record metric |
| CPU and run queue | Record metric | Record metric |
| Available RAM and swap | Record metric | Record metric |
| Disk latency and queue | Record metric | Record metric |
| Network RTT/retransmit | Record metric | Record metric |
| Threads_running and waits | Record metric | Record metric |
| Top statements and rows examined | Record metric | Record metric |

Do not enter hypothetical numbers into production reports. Record the source, unit, and time range for every metric.

## 12. Rules for Safe Changes

1. Record the initial configuration and status.
2. Define a specific hypothesis, e.g., high disk read latency due to buffer pool misses.
3. Choose a measurement that can falsify that hypothesis.
4. Change one configuration group or one query at a time.
5. Define success criteria and rollback conditions before applying.
6. Run an equivalent workload and re-collect the same metrics.
7. Check side effects such as RAM, write latency, replication lag, and application errors.
8. Save the results to compare against future adjustments.

Avoid tuning multiple variables simultaneously—such as buffer pool, thread count, timeouts, and indexes in one batch. If performance changes, it will be hard to know the cause.

## 13. Lab Exercise: Evidence-Based Diagnosis

Perform in a lab or staging environment. Do not generate heavy load, do not run stress tests in production, and do not modify OS limits on shared machines.

### 13.1. Collecting a MySQL Baseline

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Uptime',
    'Threads_connected',
    'Threads_running',
    'Questions',
    'Bytes_received',
    'Bytes_sent',
    'Innodb_buffer_pool_read_requests',
    'Innodb_buffer_pool_reads',
    'Innodb_data_reads',
    'Innodb_data_writes',
    'Innodb_log_waits',
    'Innodb_row_lock_waits',
    'Innodb_deadlocks'
);
~~~

Save the output and timestamp. Wait for a steady workload window and take a second snapshot. Compute deltas for cumulative counters.

### 13.2. Checking Statements and Waits

~~~sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS elapsed_seconds,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 10;
~~~

If there is a high-latency statement, pick a representative query and read `EXPLAIN`. Correlate with CPU, file I/O, and lock waits over the same period.

### 13.3. Reading Wait Events

~~~sql
SELECT
    EVENT_NAME,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_wait_seconds
FROM performance_schema.events_waits_summary_global_by_event_name
WHERE COUNT_STAR > 0
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

Wait summary tables may not collect data if wait instruments are disabled. A wait event identifies the instrumented wait type; it does not by itself explain causes at the application or OS layer.

### 13.4. Formulating Hypotheses

For each phenomenon, document:

- Suspected resource.
- Metrics supporting the hypothesis.
- Metrics that could refute the hypothesis.
- Next measurement.
- Candidate change to test.
- Rollback criteria.

For example: if CPU is high while disk latency is low, inspect query CPU cost and concurrency before upgrading storage. If CPU is low while many transactions wait on locks, find the blocking transaction instead of adding CPU.

### 13.5. Cleaning Up the Lab

Delete only objects created by the exercise itself. Do not reset the entire Performance Schema on a shared server and do not delete application data.

## 14. Runbook When MySQL Suddenly Slows Down

1. Confirm whether the incident affects one instance, one endpoint, or the whole system.
2. Record the timestamp, uptime, request rate, p95/p99, and error count.
3. Check CPU, run queue, memory, swap, disk latency, and network errors.
4. Check `Threads_running`, `Threads_connected`, and connection errors.
5. Inspect statement summaries, wait summaries, and InnoDB status.
6. If CPU is saturated, identify the processes and statements consuming CPU.
7. If disk latency is high, identify file I/O, data/log workload, and storage throttling.
8. If under memory pressure, check RSS, swap, OOM, and session buffers.
9. If lock waits increase, identify blocking transactions and metadata locks.
10. If network behavior is abnormal, correlate RTT, retransmissions, socket metrics, and result sizes.
11. Choose the smallest testable change and prepare a rollback.
12. Re-measure in an equivalent window, documenting results and side effects.

## 15. Operational Checklist

### When Starting an Investigation

- [ ] Timestamp and incident time range captured.
- [ ] Request rate, throughput, and latency distribution captured.
- [ ] MySQL uptime and status snapshots recorded.
- [ ] CPU, memory, disk, and network metrics collected for the same window.
- [ ] Background workloads such as backups, batch jobs, or deployments checked.

### When Identifying the Bottleneck

- [ ] CPU confirmed via process usage and run queue.
- [ ] I/O confirmed via latency, queue, and file-level data.
- [ ] Memory confirmed via available RAM, swap, reclaim, or OOM.
- [ ] Locks confirmed via wait/lock tables and transaction owner.
- [ ] Network confirmed via RTT, retransmissions, drops, or socket/client evidence.
- [ ] Root cause distinguished from cascading symptoms.

### After Making a Change

- [ ] Pre-change baseline exists.
- [ ] Only the scope tied to a clear hypothesis was changed.
- [ ] Re-measured with the same metrics and workload.
- [ ] Side effects and replication checked.
- [ ] Results, data sources, and rollback conditions documented.

## 16. Key Principles to Remember

- CPU bottlenecks must be confirmed using CPU usage, run queue, and process/thread activity; `Threads_running` is not a CPU meter.
- Performance Schema statement timers measure elapsed time, which can include wait time, not pure CPU time.
- Storage bottlenecks require inspecting latency, queues, IOPS, and file I/O types; high throughput alone is inconclusive.
- Buffer pool read counters must be read as deltas; a high hit ratio does not rule out log or flush I/O bottlenecks.
- Memory pressure manifests through available RAM, swap/reclaim, OOM, and process/container memory, not total used RAM alone.
- Per-session buffers may be allocated when a query needs them; many concurrent sessions running heavy queries can spike memory.
- Lock contention makes threads wait; locate blocking transactions, metadata locks, and deadlocks before increasing concurrency.
- Network bottlenecks require evidence of RTT, packet loss, retransmissions, bandwidth, or client/socket behavior.
- Server-side MySQL socket waits do not by themselves distinguish a slow network from a slow-reading client.
- Cumulative counters require snapshots and deltas; restarts or resets invalidate direct comparisons.
- Combine MySQL metrics, OS metrics, and application tracing to pinpoint the cause.
- Change one group of factors at a time and verify on an equivalent workload.

Effective MySQL performance diagnosis starts by distinguishing CPU, I/O, memory, locks, and network using evidence from the same time window. Once the resource creating a queue is accurately identified, operators can focus on the relevant statements, files, transactions, or connections, test a controlled change, and re-measure results instead of tuning configuration by guesswork.
