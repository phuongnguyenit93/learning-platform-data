# Identifying CPU, I/O, Redo, Undo, and Temporary Space Bottlenecks in Oracle Database

A slow Oracle system does not automatically mean the database server lacks CPU or storage is slow. To pinpoint the real bottleneck, you need to determine where sessions spend their time, which SQL statements generate the load, which operations consume resources, and whether those resources are actually saturated.

There are five resource categories commonly investigated:

- **CPU:** time spent processing SQL/PLSQL, parsing, joining, sorting, computing, and parallel execution.
- **I/O:** reading/writing datafiles, indexes, tempfiles, and redo logs on storage.
- **Redo:** recording changes for database recovery and confirming COMMITs.
- **Undo:** retaining before-images for rollbacks and consistent reads.
- **Temporary space (TEMP):** intermediate storage when sorts, hashes, analytic operations, or certain LOB operations cannot complete entirely in memory.

These areas interact closely. For instance, a single SQL statement might consume heavy CPU processing millions of rows, spill a sort to TEMP, generate heavy I/O, and simultaneously increase redo/undo if it performs DML. Therefore, measure the workload over the exact same time window, identify where sessions spend time, and only then choose a remediation.

This guide uses Oracle Database 19c as its baseline. Some views require dictionary read privileges; AWR, ASH, and ADDM fall under the Oracle Diagnostics Pack per applicable licensing terms. Verify your environment's licenses before using pack features.

## 1. What Constitutes a Bottleneck?

### 1.1. High Utilization Is Not Necessarily a Bottleneck

A system can run at 80% CPU during peak hours and still meet SLAs. Conversely, CPU may sit at just 25% while the application is slow because sessions are waiting on I/O, redo logs, locks, or an external service.

A **bottleneck** is the resource or processing step constraining throughput or extending response time for the target workload. To establish one, correlate at least:

- Resource utilization levels.
- Wait time or processing time.
- Volume of completed work.
- Latency observed from the application.
- Changes relative to a baseline for the same workload type.

Do not draw conclusions solely from a single CPU percentage, a top wait event, or a single TEMP check.

### 1.2. DB Time and DB CPU

Oracle uses time model metrics to separate database processing time from CPU time.

- **DB time:** total time foreground sessions spend on database work, comprising CPU and non-idle wait time.
- **DB CPU:** the portion of time foreground sessions actually spend running on CPU.

DB time is summed across sessions, so it can exceed wall-clock elapsed time when multiple sessions operate concurrently. Rising DB time can stem from CPU, I/O, commits, locks, or other wait types.

You can inspect cumulative instance figures:

~~~sql
SELECT stat_name,
       value / 1000000 AS seconds
FROM   v$sys_time_model
WHERE  stat_name IN ('DB time', 'DB CPU')
ORDER  BY stat_name;
~~~

Time model values are stored in microseconds. These are cumulative figures since instance startup or counter reset; to measure load over a time window, take two snapshots and compute the delta.

### 1.3. A Wait Event Is Not Automatically a Bottleneck

A wait event with high total wait time may simply reflect a high-request workload. Examine:
- Wait count.
- Total wait time.
- Average time per wait.
- Number of concurrent sessions.
- Impact on response time.
- Whether the wait belongs to the Idle class.

One session waiting once for 10 seconds differs from 10,000 sessions each waiting 1 millisecond. Both can produce large total wait times, yet their root causes and fixes are completely different.

### 1.4. A Repeatable Investigation Workflow

~~~text
Define symptoms and timeframe
                 |
                 v
Measure DB time, DB CPU, and workload
                 |
                 v
Are sessions running on CPU or WAITING?
          /                    \
       CPU                      WAIT
        |                         |
        v                         v
Top SQL, parsing,        Classify wait events
plans, parallelism       I/O / redo / undo / TEMP
        |                         |
        +------------+------------+
                     |
                     v
Correlate OS, storage, PGA/TEMP,
redo/undo, and application metrics
                     |
                     v
Identify evidence-backed root cause
                     |
                     v
Test one controlled change
                     |
                     v
Re-measure same workload against baseline
~~~

## 2. Capturing a Baseline Before Investigating

### 2.1. Document the Symptoms

Before running diagnostic queries, record:
- Slow application or service.
- Affected SQL/APIs.
- Start and end timestamps.
- Request count, transaction count, or batch size.
- Application p50/p95/p99 latencies if available.
- Session count and concurrency level.
- Recent deployments, statistics updates, index changes, parameter changes, or overlapping batch jobs.

Without knowing whether the workload itself changed, it is easy to blame the database even when request volume multiplied severalfold.

### 2.2. Take Deltas Instead of Reading Cumulative Totals Alone

Many columns in V$SYSSTAT, V$SYSTEM_EVENT, and V$SQL are cumulative counters. For example, TOTAL_WAITS or TIME_WAITED_MICRO grow continuously from instance startup.

To measure a 5-minute window:
1. Capture the starting snapshot.
2. Let the workload continue for 5 minutes.
3. Capture the second snapshot.
4. Compute the difference.
5. Divide by elapsed time or transactions to obtain appropriate rates/averages.

Do not compare counters from different instances or across counter resets without normalization.

### 2.3. Capture Baseline Metrics

~~~sql
SELECT name,
       value
FROM   v$sysstat
WHERE  name IN (
           'user commits',
           'user rollbacks',
           'redo size',
           'redo writes',
           'redo buffer allocation retries',
           'parse count (total)',
           'parse count (hard)',
           'CPU used by this session',
           'session logical reads',
           'physical reads',
           'physical writes'
       )
ORDER  BY name;
~~~

Statistic names may vary by release or context. These are cumulative snapshots, so save them with timestamps to compute deltas.

### 2.4. Inspect Active Sessions

~~~sql
SELECT sid,
       serial#,
       username,
       status,
       sql_id,
       event,
       wait_class,
       state,
       seconds_in_wait,
       blocking_session,
       module,
       action
FROM   v$session
WHERE  type = 'USER'
AND    status = 'ACTIVE'
ORDER  BY wait_class, seconds_in_wait DESC;
~~~

ACTIVE does not automatically mean running on CPU. A session with STATUS ACTIVE may be waiting on an event. When STATE is WAITING, EVENT and WAIT_CLASS show what it is waiting on; when running on CPU, `event` may not represent a current wait.

To investigate a specific timeframe, take repeated snapshots rather than a single point-in-time read.

### 2.5. Verify Privileges and Permitted Tools

V$ views normally require `SELECT_CATALOG_ROLE` or direct read grants issued by the DBA. Grant only least privilege to monitoring accounts.

AWR/ASH/ADDM and certain SQL monitoring features carry separate licensing requirements. Without appropriate licenses, use permitted V$ views, DBMS_XPLAN, and OS tools; never assume every diagnostic feature is included.

## 3. Identifying CPU Bottlenecks

### 3.1. Common Signs

CPU is likely a bottleneck when you observe concurrently:
- Host CPU saturation during the incident window.
- High run queue or runnable processes waiting for CPU.
- Sharp rise in DB CPU alongside degrading latency/throughput.
- Multiple foreground/background processes consuming CPU.
- SQL with high CPU_TIME, large buffer gets, or high parse CPU.
- Non-CPU wait events failing to account for most of DB time.

High CPU utilization alone is insufficient. Check how many CPUs the database sees, CPU quotas/VM limits, and load from other processes on the host.

### 3.2. DB CPU and DB Time

~~~sql
SELECT stat_name,
       ROUND(value / 1000000, 2) AS seconds
FROM   v$sys_time_model
WHERE  stat_name IN ('DB time', 'DB CPU');
~~~

Compute deltas across two snapshots to see how much DB CPU and DB time increased during the window. If DB CPU dominates DB time and OS CPU is saturated, CPU contention is a strong hypothesis.

If DB time is high but DB CPU is low, focus on wait events. If DB CPU is high while the host retains ample CPU headroom, SQL is consuming CPU without necessarily creating a system-wide CPU bottleneck.

### 3.3. Inspecting CPU and OS Statistics

~~~sql
SELECT stat_name,
       value
FROM   v$osstat
WHERE  stat_name IN (
           'NUM_CPUS',
           'NUM_CPU_CORES',
           'BUSY_TIME',
           'IDLE_TIME',
           'USER_TIME',
           'SYS_TIME',
           'IOWAIT_TIME',
           'LOAD'
       )
ORDER  BY stat_name;
~~~

Statistic names and units are platform-dependent. Consult the Oracle Database Reference to verify units, especially when deriving percentages from counters.

Correlate with OS tools:
- Linux: `top`, `vmstat`, `mpstat`, `sar`.
- Windows: Performance Monitor, CPU utilization, processor queue, process CPU.
- VM/container: check vCPU quotas, CPU limits, and host contention.

### 3.4. Finding CPU-Consuming SQL

~~~sql
SELECT sql_id,
       child_number,
       executions,
       ROUND(cpu_time / 1000000, 2) AS cpu_seconds,
       ROUND(elapsed_time / 1000000, 2) AS elapsed_seconds,
       buffer_gets,
       disk_reads,
       rows_processed,
       SUBSTR(sql_text, 1, 120) AS sql_text
FROM   v$sql
WHERE  executions > 0
ORDER  BY cpu_time DESC
FETCH FIRST 20 ROWS ONLY;
~~~

CPU_TIME and ELAPSED_TIME in V$SQL are cumulative per cursor. A SQL statement with many executions may top the list due to large aggregate work. To evaluate a single execution, divide delta CPU/elapsed by delta executions over the same interval; do not look solely at totals.

You can add CPU per execution:

~~~sql
SELECT sql_id,
       child_number,
       executions,
       ROUND(cpu_time / NULLIF(executions, 0) / 1000, 2)
           AS avg_cpu_ms,
       ROUND(elapsed_time / NULLIF(executions, 0) / 1000, 2)
           AS avg_elapsed_ms,
       buffer_gets,
       rows_processed
FROM   v$sql
WHERE  executions > 0
ORDER  BY cpu_time / NULLIF(executions, 0) DESC
FETCH FIRST 20 ROWS ONLY;
~~~

These are cumulative averages since cursor load, which may not reflect the specific incident window. For shifting workloads, use snapshot deltas or time-series monitoring tools.

### 3.5. CPU from Parsing

Hard parsing and frequent parsing can burn CPU. Inspect:
- `parse count (total)`.
- `parse count (hard)`.
- `parse time cpu`.
- `executions` and `parse_calls` in V$SQL.
- Child cursor count and `version_count`.

~~~sql
SELECT name,
       value
FROM   v$sysstat
WHERE  name IN (
           'parse count (total)',
           'parse count (hard)',
           'parse time cpu'
       );
~~~

A high hard-parse ratio in repetitive SQL workloads often suggests literal concatenation, failure to reuse prepared statements, or incompatible child cursors. Do not look at ratios alone; compare against execution counts and actual load.

### 3.6. CPU from Poor SQL Plans

SQL can consume excessive CPU due to:
- Full scans over excessive data.
- Joins producing huge intermediate row counts.
- Non-sargable predicates or implicit data type conversions.
- Sorts/hashes on large datasets.
- PL/SQL invoking SQL repeatedly row-by-row.
- Bad cardinality estimates causing the optimizer to pick unsuitable join methods.
- Parallel execution spawning many workers and increasing total CPU.

Use `DBMS_XPLAN.DISPLAY_CURSOR` to inspect plans and runtime statistics. Focus on A-Rows, E-Rows, Starts, Buffers, and high-volume operations.

### 3.7. CPU and Parallel Execution

Parallel query can shorten elapsed time for large tasks by utilizing multiple CPUs, yet total CPU consumption can increase. If multiple parallel queries run concurrently, the system can become oversubscribed.

Check:
- Actual Degree of Parallelism (DOP).
- Number of active PX servers.
- Queues and waits related to parallel execution.
- Host and database CPU.
- Overall throughput, not just single-query duration.

Do not raise DOP simply because one query runs slowly. Increasing parallelism can degrade concurrent OLTP workloads.

### 3.8. CPU Remediation Measures

Prioritize based on evidence:
1. Tune top CPU-consuming SQL.
2. Reduce unnecessary rows and columns processed.
3. Fix join cardinalities, predicates, and data types.
4. Reduce hard parses using bind variables and statement reuse.
5. Inspect row-by-row PL/SQL and convert to set-based processing where appropriate.
6. Right-size parallelism for the workload.
7. Scale CPU capacity only after confirming legitimate load exceeds current capacity.

## 4. Identifying I/O Bottlenecks

### 4.1. Distinguishing I/O Types

Oracle reads/writes multiple file types:
- Datafiles containing table/index segments.
- Tempfiles containing temporary segments when needed.
- Online redo logs receiving redo records.
- Archive logs holding redo copies for recovery/standby.

A wait event indicates the type of operation waiting, not automatically that storage is faulty. Correlate with latency, throughput, queue depth, and physical devices.

### 4.2. Common Wait Events

| Wait event | Typical meaning | Investigation direction |
| --- | --- | --- |
| db file sequential read | Single-block read, common in index lookups or table access by ROWID | Index access, random I/O, cache hit, storage latency |
| db file scattered read | Multiblock read, common in full scans or multiblock reads | Scan volume, segment size, multiblock throughput |
| direct path read | Direct read into PGA, common in large/parallel scans | Data volume, storage throughput, parallelism |
| direct path read temp | Reading intermediate data from TEMP | Sort/hash spills, PGA, tempfile latency |
| direct path write temp | Writing intermediate data to TEMP | Workarea spills, volume, tempfile throughput |
| log file parallel write | LGWR writing redo log members | Redo storage latency, log configuration |
| control file sequential read | Reading control file blocks | Control file I/O, workload, and storage |
| db file parallel read | Multiple blocks read in one operation | Batch/index access, storage response |

Event meanings can vary by operation type, release, and platform. Verify exact definitions in the Oracle Database Reference.

### 4.3. db file sequential read Is Not an Error by Default

Index range scans naturally perform many single-block reads and may be the optimal access path. If blocks already reside in the buffer cache, no physical read is needed.

Check:
- Wait count and total wait time.
- Average wait time.
- Physical reads vs. logical reads.
- Number of blocks accessed.
- Associated SQL_ID and plan operations.
- Storage latency during the same window.

If SQL performs millions of index lookups taking a few milliseconds each, total elapsed time can be huge even when storage per-request latency is normal.

### 4.4. db file scattered read and Full Scans

Full table scans typically use multiblock reads. This is not inherently bad: sequentially scanning a large table can outperform millions of random index lookups.

Verify:
- Are selective predicates still triggering a full table scan?
- Is partition pruning occurring?
- Is the segment abnormally bloated?
- Is the scan an expected reporting/batch job?
- Is storage throughput sufficient?
- Can data volume be reduced or only needed columns projected?

### 4.5. Reading Instance I/O Waits

~~~sql
SELECT event,
       wait_class,
       total_waits,
       ROUND(time_waited_micro / 1000000, 2) AS wait_seconds,
       ROUND(
           time_waited_micro / NULLIF(total_waits, 0) / 1000,
           3
       ) AS avg_wait_ms
FROM   v$system_event
WHERE  wait_class = 'User I/O'
ORDER  BY time_waited_micro DESC
FETCH FIRST 20 ROWS ONLY;
~~~

V$SYSTEM_EVENT contains cumulative counters. Take deltas over the incident window to avoid mistaking long-lived historical events for current bottlenecks. Some I/O events belong to other wait classes depending on operation; inspect all relevant events rather than filtering one class blindly.

### 4.6. Correlating with OS/Storage Metrics

On Linux, use:
- `iostat -x`: per-device utilization, await, queue depth, and throughput.
- `vmstat`: runnable processes, blocked processes, swap, and CPU.
- `sar`: CPU/I/O trends over time.
- `multipath` or SAN/cloud provider tools to inspect paths and volumes.

On Windows, use Performance Monitor to check:
- Physical Disk: Avg. Disk sec/Read and Avg. Disk sec/Write.
- Disk Reads/sec, Writes/sec, Bytes/sec.
- Current Disk Queue Length.
- CPU, memory, and paging.

Counter names and interpretations vary by platform. Match the exact volume holding datafiles, tempfiles, or redo logs; never use an unrelated disk as evidence.

### 4.7. I/O Latency, IOPS, and Throughput

Distinguish three concepts:
- **Latency:** time to complete a single I/O request.
- **IOPS:** number of I/O requests per second.
- **Throughput:** bytes read/written per second.

A volume may deliver high throughput yet suffer high random-read latency. A sequential workload can achieve good throughput with lower IOPS. Examine both I/O size and access pattern.

### 4.8. I/O Remediation Measures

- Optimize SQL to reduce blocks read.
- Inspect indexes, partition pruning, and clustering factor.
- Avoid repeated scans caused by inappropriate nested loops/subqueries.
- Separate batch and OLTP workloads if they contend on storage.
- Size buffer cache based on workload measurements rather than guessing SGA increases.
- Inspect storage configuration, queue depth, multipathing, and provider latency.
- Do not split redo/data/temp across volumes purely by name; measure workload and device characteristics first.

## 5. Identifying REDO and COMMIT Bottlenecks

### 5.1. What Is Redo Used For?

Redo records the changes needed for Oracle to recover the database after a failure. When a transaction modifies blocks, Oracle generates redo records. LGWR flushes the redo buffer to online redo logs per database mechanisms.

Redo differs from undo:
- Redo supports roll-forward/recovery.
- Undo stores before-images for rollbacks and consistent reads.

A single transaction can generate both redo and undo.

### 5.2. log file sync

Foreground sessions wait on `log file sync` during COMMIT or operations requiring confirmation that LGWR has written redo to the required point.

If `log file sync` is high, investigate:
- Application committing too frequently.
- Tiny transactions with high commit rates.
- LGWR slowed by redo storage.
- CPU scheduling or process contention.
- RAC/standby/commit configurations adding confirmation latency.
- Concurrent bursts of commits across many sessions.

Do not conclude high `log file sync` automatically means slow redo disks. Correlate with `log file parallel write` and OS storage latency.

### 5.3. log file parallel write

This is LGWR's wait while writing redo log files. If write times are elevated during the same window as high `log file sync`, redo storage is a strong suspect.

Check:
- Redo device latency.
- Number of redo log members and their storage locations.
- I/O contention from data/temp/backups.
- Storage cache/persistence policies.
- Network/storage paths if using ASM or shared storage.

### 5.4. log buffer space

Foreground sessions wait on `log buffer space` when requesting space in the redo log buffer and LGWR has not cleared buffer space quickly enough.

Potential causes:
- LGWR falling behind on redo writes.
- Sudden surge in redo generation.
- High storage latency.
- Log buffer pressure or unusual workload patterns.

Inspect `redo buffer allocation retries`, `redo size`, `log writes`, and concurrent wait events. Do not enlarge `LOG_BUFFER` as a knee-jerk reaction; determine whether the cause is LGWR/storage or excessive redo generation.

### 5.5. log file switch waits

Wait events related to redo log switches include:
- `log file switch (checkpoint incomplete)`: checkpoint must finish before reusing the log group.
- `log file switch (archiving needed)`: log must be archived before reuse.
- `log file switch completion`: session waiting for log switch to finish.

You may need to:
- Check redo log group sizes and counts.
- Check log switch frequency.
- Inspect checkpoints and DBWR.
- Inspect ARCH processes and archive destinations.
- Check if archive destination is full or slow.

Do not increase redo log size blindly. Base sizing on redo generation rate, switch intervals, checkpoints, and recovery requirements.

### 5.6. Inspecting Redo Statistics

~~~sql
SELECT name,
       value
FROM   v$sysstat
WHERE  name IN (
           'redo size',
           'redo writes',
           'redo entries',
           'redo buffer allocation retries',
           'user commits',
           'user rollbacks'
       )
ORDER  BY name;
~~~

These counters are cumulative. Compute deltas to determine redo bytes/second, commits/second, and retries within the measurement window.

Redo bytes per transaction can be informative:

~~~text
Redo per commit = delta redo size / delta user commits
~~~

This is a composite metric for comparing workloads, not a fixed good/bad threshold.

### 5.7. Inspecting Redo Log Configuration

~~~sql
SELECT group#,
       thread#,
       sequence#,
       bytes,
       members,
       archived,
       status
FROM   v$log
ORDER  BY thread#, group#;
~~~

Inspect member paths:

~~~sql
SELECT group#,
       type,
       member,
       status
FROM   v$logfile
ORDER  BY group#, member;
~~~

In RAC, each instance thread has its own redo logs. Check THREAD# and verify the right instance/thread.

### 5.8. Commit Batching and Transaction Design

If an application commits after every row in a large batch, it can trigger excessive `log file sync` waits. Grouping related changes into reasonably sized transactions reduces commits and improves throughput.

However, oversized transactions increase:
- Undo consumption.
- Duration of held row/table locks.
- Long rollback risk.
- Concurrency and recovery impact.

Choose batch sizes based on SLAs, rollback tolerance, and business independence.

### 5.9. Never Disable Redo for Speed

Do not use NOLOGGING or alter FORCE LOGGING merely to reduce `log file sync`. NOLOGGING does not apply to all operations and can compromise media recovery/standby databases. Never disable ARCHIVELOG or weaken redo protection without evaluating recovery requirements.

## 6. Identifying UNDO Issues

### 6.1. What Is Undo Used For?

Undo stores information needed to:
- Roll back transactions.
- Provide consistent reads for running queries.
- Support certain Flashback operations.
- Restore pre-change state within a transaction.

When updating or deleting many rows, Oracle generates undo for the changes. Undo also generates redo so undo data itself is protected for recovery.

### 6.2. Undo Pressure and Common Errors

Two errors must be distinguished:

- `ORA-01555: snapshot too old`. A query needed an older version of data, but the required undo was overwritten or no longer available.
- `ORA-30036: unable to extend segment in undo tablespace`. A transaction could not allocate additional undo extents in the undo tablespace.

These errors can relate to:
- Long-running queries.
- DML generating large undo volumes.
- Undersized undo tablespace or unsuitable autoextend settings.
- Undo retention insufficient for the workload.
- Sudden spikes in concurrent transactions.
- `RETENTION GUARANTEE` paired with limited free space.

### 6.3. ORA-01555 Is Not Simply Missing Disk Space

Snapshot too old typically happens when a query requires undo older than how long undo can be retained. Causes include:
- A long-running query scanning a table undergoing heavy concurrent updates.
- Insufficient undo tablespace capacity to hold required undo.
- Retention configured too low for query duration.
- Sudden burst in write workload.

Increasing space or retention can help, but first identify which queries run long and the undo generation rate.

### 6.4. ORA-30036

This error indicates a transaction cannot extend an undo segment in the undo tablespace. Check:
- Remaining free space in the undo tablespace.
- Whether datafiles have autoextend enabled and what MAXSIZE is set to.
- Which transactions are consuming heavy undo.
- Undo generation rate and concurrency.
- Whether `RETENTION GUARANTEE` is enabled.

Never manually drop undo extents or manipulate internal segments to reclaim space.

### 6.5. Inspecting V$UNDOSTAT

~~~sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       maxqueryid,
       tuned_undoretention,
       ssolderrcnt,
       nospaceerrcnt,
       unxpstealcnt,
       expstealcnt
FROM   v$undostat
ORDER  BY begin_time DESC
FETCH FIRST 24 ROWS ONLY;
~~~

V$UNDOSTAT provides statistics over intervals (typically 10 minutes). Useful columns:
- UNDOBLKS: undo blocks consumed during the interval.
- TXNCOUNT: transaction count.
- MAXQUERYLEN: longest query duration.
- TUNED_UNDORETENTION: Oracle-tuned retention period.
- SSOLDERRCNT: count of snapshot-too-old errors.
- NOSPACEERRCNT: count of undo space errors.
- UNXPSTEALCNT/EXPSTEALCNT: extent stealing counts by expiration status.

Confirm exact column details and units in the Oracle Database Reference for your release. Older intervals age out as the view wraps.

### 6.6. Inspecting Transactions Consuming Undo

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.sql_id,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM   v$transaction t
JOIN   v$session s
       ON s.taddr = t.addr
ORDER  BY t.used_ublk DESC;
~~~

USED_UBLK and USED_UREC show current undo usage per active transaction. This is a point-in-time snapshot; completed transactions disappear from V$TRANSACTION.

### 6.7. Inspecting Undo Extents

~~~sql
SELECT tablespace_name,
       status,
       COUNT(*) AS extent_count,
       SUM(bytes) / 1024 / 1024 AS size_mb
FROM   dba_undo_extents
GROUP  BY tablespace_name, status
ORDER  BY tablespace_name, status;
~~~

Common statuses are ACTIVE, UNEXPIRED, and EXPIRED. ACTIVE is in use by a live transaction; UNEXPIRED is still within retention; EXPIRED is eligible for reuse. Do not assume UNEXPIRED space can never be reused under any configuration.

### 6.8. UNDO_RETENTION and RETENTION GUARANTEE

`UNDO_RETENTION` sets the target duration to retain undo. Without retention guarantee, Oracle may reuse unexpired undo when space is needed, depending on conditions and settings.

`RETENTION GUARANTEE` enforces retaining undo until retention expires, meaning DML may fail if space runs out rather than overwriting retained undo. This is a trade-off between guaranteeing consistent reads/Flashback and write availability.

Check the tablespace:

~~~sql
SELECT tablespace_name,
       retention,
       status,
       contents
FROM   dba_tablespaces
WHERE  contents = 'UNDO';
~~~

Never enable GUARANTEE solely to cure `ORA-01555` without sizing capacity and accounting for undo generation rates.

### 6.9. Undo Remediation Measures

- Shorten queries requiring consistent reads where possible.
- Reduce open transaction durations.
- Break large DML batches into appropriate sizes.
- Calculate undo generation rates and required retention capacity.
- Tune `UNDO_RETENTION` to match query/Flashback duration needs.
- Review datafile autoextend, maxsize, and tablespace capacity.
- Consider `RETENTION GUARANTEE` only with clear business requirements and ample capacity.
- Optimize SQL to avoid prolonged scans over heavily mutated data.

## 7. Identifying TEMPORARY SPACE Bottlenecks

### 7.1. What Is TEMP Used For?

Temporary tablespaces store temporary segments for operations such as:
- Large sorts.
- Hash join or hash aggregation spills.
- Analytic/window processing.
- `DISTINCT` and intermediate operations.
- Certain LOB or temporary LOB operations.
- Index builds and other SQL tasks.

TEMP is not the undo tablespace. TEMP holds transient working data; undo retains data versions required for transactions and consistent reads.

### 7.2. TEMP Exhaustion and ORA-01652

`ORA-01652` typically reports that Oracle cannot extend a temporary segment in a tablespace. Possible causes:
- Insufficient TEMP tablespace capacity.
- Tempfiles lack autoextend or hit MAXSIZE.
- Multiple sessions spilling concurrently.
- A single SQL producing an oversized intermediate sort/hash.
- Workarea/PGA undersized for the workload.
- Intermediate data blowing up due to a bad plan or join cardinality.

Not every `ORA-01652` is fixed by adding a tempfile. First identify which SQL and operations are consuming TEMP.

### 7.3. Inspecting Sessions Using TEMP

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.sql_id,
       u.tablespace,
       u.segtype,
       u.blocks,
       u.extents
FROM   v$tempseg_usage u
JOIN   v$session s
       ON s.saddr = u.session_addr
      AND s.serial# = u.session_num
ORDER  BY u.blocks DESC;
~~~

V$TEMPSEG_USAGE identifies the session and temporary segment type. BLOCKS is in blocks, not bytes; multiply by the tablespace block size to convert. One session can hold multiple segments or metadata rows.

### 7.4. Checking TEMP Capacity

~~~sql
SELECT tablespace_name,
       SUM(bytes_used) / 1024 / 1024 AS used_mb,
       SUM(bytes_free) / 1024 / 1024 AS free_mb
FROM   v$temp_space_header
GROUP  BY tablespace_name
ORDER  BY tablespace_name;
~~~

V$TEMP_SPACE_HEADER shows space status per tempfile. This is a point-in-time snapshot; usage shifts rapidly as queries finish or sessions spill.

Check tempfiles:

~~~sql
SELECT tablespace_name,
       file_name,
       bytes / 1024 / 1024 AS size_mb,
       autoextensible,
       maxbytes / 1024 / 1024 AS max_size_mb
FROM   dba_temp_files
ORDER  BY tablespace_name, file_name;
~~~

### 7.5. Workareas: Optimal, One-Pass, and Multi-Pass

Sort/hash operations use PGA workareas:
- **Optimal:** completes entirely in memory with zero spill to TEMP.
- **One-pass:** spills and processes through a single pass over intermediate partitions.
- **Multi-pass:** must read/write multiple passes because the workarea is too small; significantly higher cost.

These states describe how an operator executes, not an overall state of the tablespace.

### 7.6. Inspecting Workareas by SQL

~~~sql
SELECT sql_id,
       child_number,
       operation_type,
       policy,
       estimated_optimal_size,
       last_memory_used,
       last_tempseg_size,
       optimal_executions,
       onepass_executions,
       multipasses_executions
FROM   v$sql_workarea
ORDER  BY last_tempseg_size DESC NULLS LAST;
~~~

V$SQL_WORKAREA provides workarea data per cursor/operator. These metrics reflect cursor-level last execution details and cumulative counters; read them alongside SQL_ID, child_number, and measurement timestamps.

Active workareas:

~~~sql
SELECT sid,
       sql_id,
       operation_type,
       actual_mem_used,
       max_mem_used,
       number_passes,
       tempseg_size
FROM   v$sql_workarea_active
ORDER  BY tempseg_size DESC NULLS LAST;
~~~

The active view shows only operations executing at query time. A completed sort will no longer appear.

### 7.7. Inspecting PGA Statistics

~~~sql
SELECT name,
       value,
       unit
FROM   v$pgastat
WHERE  name IN (
           'aggregate PGA target parameter',
           'total PGA allocated',
           'total PGA inuse',
           'maximum PGA allocated',
           'over allocation count',
           'cache hit percentage'
       )
ORDER  BY name;
~~~

`cache hit percentage` is an aggregate PGA workarea indicator and should not be used in isolation to draw conclusions. A rising `over allocation count` signals a need to inspect configuration and workload, but must be correlated with timestamps and other metrics.

### 7.8. Rising TEMP Does Not Mean You Must Increase PGA

PGA target and TEMP address different aspects. Increasing PGA can reduce spills if memory pressure is the cause, yet total PGA also depends on concurrency and process count. With many concurrent queries, larger per-operation PGA allocations can push total memory past host capacity.

Before increasing PGA:
- Check active workarea counts.
- Check spilling operations and pass counts.
- Check concurrency.
- Check whether SQL processes excessive rows.
- Check PGA aggregate target/limit and host memory.
- Re-measure under comparable load.

### 7.9. TEMP Remediation Measures

1. Identify the SQL_ID/session consuming TEMP.
2. Inspect the execution plan for SORT, HASH JOIN, HASH GROUP BY, or WINDOW SORT.
3. Compare E-Rows and A-Rows to spot cardinality misestimates.
4. Reduce input rows where semantically valid.
5. Eliminate row-multiplying joins.
6. Project only needed columns to shrink row width.
7. Tune PGA/workarea sizing after evaluating concurrency.
8. Expand TEMP if legitimate workloads require more capacity.
9. Check autoextend, maxsize, tempfile I/O, and storage space.
10. Re-monitor after changes.

## 8. Distinguishing REDO, UNDO, and TEMP

| Component | Stored Content | Purpose | Used When | Common Errors/Issues |
| --- | --- | --- | --- | --- |
| Redo | Records describing recoverable changes | Crash/media recovery, redo transport | DML and many database operations | `log file sync`, `log buffer space`, log switch waits |
| Undo | Pre-change before-images | Rollback, read consistency, Flashback | DML transactions and consistent reads | `ORA-01555`, `ORA-30036` |
| TEMP | Transient intermediate data | Sorts/hashes/windows and temporary operations | SQL operations needing workspace beyond PGA | `ORA-01652`, heavy TEMP spills |

A single large UPDATE can:
- Use CPU to locate and modify rows.
- Read data blocks from storage.
- Generate undo for old values.
- Generate redo protecting the changes.
- Flush redo via LGWR.
- Use TEMP if the plan involves intermediate sorts/hashes.

You cannot resolve bottlenecks by enlarging an arbitrary tablespace type. Identify which data type and operation are actually constrained.

## 9. Wait Events and Reading Context Properly

### 9.1. Inspecting Cumulative Wait Events

~~~sql
SELECT event,
       wait_class,
       total_waits,
       ROUND(time_waited_micro / 1000000, 2) AS wait_seconds,
       ROUND(
           time_waited_micro / NULLIF(total_waits, 0) / 1000,
           3
       ) AS avg_wait_ms
FROM   v$system_event
WHERE  wait_class <> 'Idle'
ORDER  BY time_waited_micro DESC
FETCH FIRST 30 ROWS ONLY;
~~~

Counters are cumulative. Capture two snapshots and compute deltas to spot waits growing during the incident window. Never directly compare a long-running instance with a freshly restarted one.

### 9.2. Inspecting Waiting Sessions

~~~sql
SELECT sid,
       serial#,
       username,
       sql_id,
       event,
       wait_class,
       state,
       seconds_in_wait,
       p1text,
       p1,
       p2text,
       p2,
       p3text,
       p3
FROM   v$session
WHERE  status = 'ACTIVE'
AND    type = 'USER'
AND    state = 'WAITING'
ORDER  BY seconds_in_wait DESC;
~~~

P1/P2/P3 are event-specific parameters. Interpret them according to wait event documentation; never apply one uniform meaning across all events.

### 9.3. Average Wait Can Mislead

An event with a tiny average wait can accumulate huge total time if triggered millions of times. Conversely, an event with a large average wait occurring once may barely affect overall workload.

Always examine total wait time, wait count, active sessions, and request latency together.

### 9.4. Wait Class Is Not a Final Diagnosis

For example:
- High User I/O: could be SQL reading too much or slow storage.
- High Commit: could be overly frequent commits or redo write latency.
- High Concurrency: could be mutex/latch contention or structural contention.
- High Application: could be locks held by application transactions.

Class names only categorize symptoms. Trace down to the exact SQL, session, and resource.

## 10. Combining Database Metrics with OS Metrics

### 10.1. CPU and Memory

Correlate:
- Per-core CPU utilization.
- Run queue.
- Oracle processes vs. other OS processes.
- Available memory.
- Paging/swap.
- PGA allocation and memory pressure.

High host CPU caused by antivirus, backups, agents, or other processes is not a SQL bug. Identify which OS processes consume CPU at the exact incident timestamp.

### 10.2. Storage

Correlate devices hosting:
- Datafiles.
- Redo logs.
- Tempfiles.
- Archive destinations.
- Control files.

Track read/write latency, queue depth, IOPS, and throughput per volume. Shared storage volumes can see backups or batch jobs slow down redo or datafiles.

### 10.3. Network

If the application is slow while DB time is low, check:
- Round-trip latency between app and database.
- Round trips per request.
- Fetch size and rows transferred.
- Large LOB payloads.
- Connection pool behavior and connection acquisition time.
- Network retransmissions or packet loss.

Not all application latency is captured inside DB time.

### 10.4. RAC and Cluster Environments

In RAC, use GV$ views when cross-instance visibility is needed and preserve INST_ID. Global cache/interconnect waits such as `gc current`/`cr block` events may reflect block contention or interconnect networking. Do not lump them into standard storage I/O.

Inspect the exact instance, service, node, and redo thread. A single node saturated on CPU or interconnect can degrade a service even while other nodes have spare capacity.

## 11. Symptom and Investigation Matrix

| Symptom | Initial Suspect | Evidence to Gather | Potential Remediation |
| --- | --- | --- | --- |
| High host CPU, high DB CPU | CPU-bound SQL or parallelism | Top CPU SQL, plans, run queue | Tune SQL, reduce work, adjust DOP |
| High DB time, low DB CPU | Sessions waiting on resources | Top non-idle waits, active sessions | Classify waits, fix underlying resource |
| High `db file sequential read` | Heavy single-block reads | SQL plans, buffers, I/O latency | Reduce lookups, check index/access patterns |
| High `db file scattered read` | Heavy multiblock scans | Full scan volume, partition pruning | Reduce scanned data, optimize reports |
| High `log file sync` | Commit latency | `log file parallel write`, commits/sec | Batch transactions reasonably, inspect redo storage |
| `log buffer space` | LGWR not freeing buffer fast enough | Redo generation, LGWR waits, storage | Identify redo bursts and LGWR bottlenecks |
| `log file switch` waits | Slow checkpoint/archive or small logs | V$LOG, archive destination, DBWR | Tune logs/checkpoints/archiving based on data |
| `ORA-01555` | Undo unable to retain required versions | V$UNDOSTAT, query duration, DML rate | Shorten queries, adjust sizing/retention |
| `ORA-30036` | Undo cannot allocate more extents | Undo free space, active transactions | Capacity, autoextend, transaction size |
| `ORA-01652` | TEMP cannot extend | V$TEMPSEG_USAGE, workareas, tempfiles | Tune SQL, right-size PGA, expand TEMP |
| Large TEMP spills | Undersized sort/hash workareas or oversized input | V$SQL_WORKAREA, plans, A-Rows | Reduce input, fix plans, evaluate PGA |
| App slow, low DB time | Network/app/connection pool | App tracing, network, pool metrics | Investigate outside the database |

This is a directional guide, not a strict rule that one symptom has only one cause.

## 12. Common Pitfalls When Handling Bottlenecks

### 12.1. Adding CPU Before Inspecting SQL

If a SQL statement reads 100 million rows due to a poor predicate, adding CPU only burns through unnecessary work slightly faster. Optimizing the access path and cardinality often yields far greater gains.

### 12.2. Resizing SGA/PGA Based on a Single Metric

Buffer cache hit ratio or PGA cache hit percentage is not a standalone basis for adding memory. Evaluate physical I/O, workarea spills, host memory, concurrency, and SLAs.

### 12.3. Expanding TEMP Without Finding the Session

Adding tempfiles resolves immediate out-of-space errors but fails to fix queries generating massive intermediate sets or joins with bad cardinality. Identify the SQL_ID and operation consuming TEMP first.

### 12.4. Raising UNDO_RETENTION Without Adding Capacity

Higher retention requires matching undo space. Without guarantee, Oracle still reuses unexpired undo under space pressure. With guarantee, DML can fail once space runs out.

### 12.5. Enlarging Redo Logs Without Checking Archiving/Checkpoints

Frequent log switches may point to undersized logs, but switch waits can also stem from checkpoint or archive backlogs. Identify the exact wait event and redo rate.

### 12.6. Relying on the All-Time Top-1 Wait Event

An event leading since instance startup may be unrelated to the current incident. Use interval deltas and link them to specific SQL and sessions.

### 12.7. Flushing Shared Pool or Buffer Cache for Testing

Flushing triggers mass hard parses or physical reads, impacting the entire workload. Never use flushing as a routine diagnostic step in production.

### 12.8. Ignoring Transactions and Application Behavior

Over-frequent commits, long-held transactions, tiny fetch sizes, misconfigured connection pools, or chattiness can create bottlenecks even on a well-configured database. Collect application-tier and database-tier traces for the same request.

## 13. Ordered Incident Investigation Runbook

### Step 1 — Define the Incident Window

Record timestamps, service, SQL/API, latency, and request count. Compare against the same time window on normal days if workload is cyclical.

### Step 2 — Evaluate DB Time and DB CPU

Take V$SYS_TIME_MODEL deltas. If DB CPU dominates DB time, investigate CPU. Otherwise, classify waits.

### Step 3 — Identify Sessions and SQL

Use V$SESSION for SQL_ID, event, wait class, module/action, and blocking sessions. Find top SQL by CPU, elapsed time, buffer gets, disk reads, and executions.

### Step 4 — Inspect Actual Execution Plans

Use `DBMS_XPLAN.DISPLAY_CURSOR` with `ALLSTATS LAST`, `PREDICATE`, and appropriate options. Compare E-Rows/A-Rows, Starts, Buffers, and operations.

### Step 5 — Categorize Resource Pressure

- CPU: DB CPU, OS CPU, run queue, top SQL.
- I/O: wait events, latency, and queue depth per volume.
- Redo: `log file sync`, `log file parallel write`, redo rate, and commit rate.
- Undo: V$UNDOSTAT, active transactions, extent usage.
- TEMP: V$TEMPSEG_USAGE, V$SQL_WORKAREA, tempfile capacity.

### Step 6 — Check External Factors

Inspect storage, network, OS processes, VM/container limits, backups, batch jobs, and concurrency.

### Step 7 — Pick One Hypothesis-Driven Change

Examples:
- SQL reading excess rows → fix predicates/indexes/partition pruning.
- Excessive commits → batch transactions safely.
- Sort spills from oversized inputs → reduce inputs or fix cardinality.
- Undo exhaustion from long transactions → tune batch/queries/retention and capacity.
- TEMP exhaustion from valid workloads → expand capacity after verifying root cause.

### Step 8 — Re-Measure

Use identical SQL, bind distributions, datasets, concurrency, and window duration. Compare latency, throughput, DB time, CPU, waits, I/O, and redo/undo/TEMP. Keep the change only when metrics improve without unacceptable regression to other workloads.

## 14. Consolidated Diagnostic Query Examples

### 14.1. Top Active Sessions

~~~sql
SELECT sid,
       serial#,
       username,
       sql_id,
       event,
       wait_class,
       state,
       seconds_in_wait,
       module,
       action
FROM   v$session
WHERE  type = 'USER'
AND    status = 'ACTIVE'
ORDER  BY seconds_in_wait DESC;
~~~

### 14.2. Top SQL by CPU

~~~sql
SELECT sql_id,
       child_number,
       executions,
       ROUND(cpu_time / 1000000, 2) AS cpu_seconds,
       ROUND(elapsed_time / 1000000, 2) AS elapsed_seconds,
       buffer_gets,
       disk_reads,
       rows_processed
FROM   v$sql
WHERE  executions > 0
ORDER  BY cpu_time DESC
FETCH FIRST 20 ROWS ONLY;
~~~

### 14.3. Wait Events by Time

~~~sql
SELECT event,
       wait_class,
       total_waits,
       ROUND(time_waited_micro / 1000000, 2) AS wait_seconds,
       ROUND(time_waited_micro / NULLIF(total_waits, 0) / 1000, 3)
           AS avg_wait_ms
FROM   v$system_event
WHERE  wait_class <> 'Idle'
ORDER  BY time_waited_micro DESC
FETCH FIRST 30 ROWS ONLY;
~~~

### 14.4. Redo Rate and Commit Rate

Capture V$SYSSTAT twice and compute:

~~~text
Redo bytes per second = delta(redo size) / elapsed seconds
Commits per second    = delta(user commits) / elapsed seconds
Redo per commit       = delta(redo size) / delta(user commits)
~~~

These formulas are only valid when counters did not reset between snapshots and scope/workload match.

### 14.5. Undo Trend

~~~sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt,
       nospaceerrcnt
FROM   v$undostat
ORDER  BY begin_time DESC
FETCH FIRST 24 ROWS ONLY;
~~~

### 14.6. TEMP Consumers

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.sql_id,
       u.tablespace,
       u.segtype,
       u.blocks
FROM   v$tempseg_usage u
JOIN   v$session s
       ON s.saddr = u.session_addr
      AND s.serial# = u.session_num
ORDER  BY u.blocks DESC;
~~~

### 14.7. Workarea Spills

~~~sql
SELECT sql_id,
       child_number,
       operation_type,
       last_execution,
       last_memory_used,
       last_tempseg_size,
       optimal_executions,
       onepass_executions,
       multipasses_executions
FROM   v$sql_workarea
ORDER  BY last_tempseg_size DESC NULLS LAST;
~~~

### 14.8. Undo Extent Distribution

~~~sql
SELECT tablespace_name,
       status,
       COUNT(*) AS extents,
       SUM(bytes) / 1024 / 1024 AS size_mb
FROM   dba_undo_extents
GROUP  BY tablespace_name, status
ORDER  BY tablespace_name, status;
~~~

## 15. Practice Exercises

Run exercises in a test schema/database with sufficiently large data. Never generate heavy load or alter tablespaces/parameters in production for experimentation.

### Exercise 1 — Measuring DB Time and DB CPU

Capture two V$SYS_TIME_MODEL snapshots five minutes apart. Compute delta DB time and DB CPU. Compare against application latency.

### Exercise 2 — Identifying CPU-Bound SQL

Run a query processing many rows. Inspect V$SQL ordered by CPU_TIME and use `DBMS_XPLAN.DISPLAY_CURSOR` to identify CPU-intensive operations.

### Exercise 3 — Hard Parsing

Create a test workload using varying literals, then switch to one SQL statement with bind variables. Compare parse counts, SQL_IDs, and child cursors.

### Exercise 4 — Single-Block and Multiblock I/O

Test an index-lookup query and a full-scan query on a test table. Observe `db file sequential read`, `db file scattered read`, or `direct path read` depending on the plan.

### Exercise 5 — Storage Correlation

During the same test query window, capture `iostat` or Performance Monitor metrics. Compare database waits with latency and queue depth on the exact underlying volume.

### Exercise 6 — Redo Generation

Execute batch INSERT/UPDATE runs with different batch sizes. Measure redo size, commits, `log file sync`, and throughput.

### Exercise 7 — Commit Frequency

Compare row-by-row commits with reasonable batch commits. Record `log file sync`, elapsed time, undo usage, and rollback behavior.

### Exercise 8 — Log Switches

In a test database, observe V$LOG, log switches, and archiver processes under heavy redo load. Distinguish `archiving needed` from `checkpoint incomplete`.

### Exercise 9 — Undo Pressure

Run a long-running read query while concurrently executing DML against the same table. Observe V$UNDOSTAT, query duration, and undo extent distribution.

### Exercise 10 — Undo-Heavy Transactions

Run a multi-row UPDATE transaction in a test schema. Inspect `V$TRANSACTION.USED_UBLK` and `USED_UREC`. Roll back after measuring.

### Exercise 11 — TEMP Spills

Run a sort or hash operation over a sufficiently large dataset. Inspect V$SQL_WORKAREA, V$SQL_WORKAREA_ACTIVE, and V$TEMPSEG_USAGE.

### Exercise 12 — PGA and Concurrency

Execute multiple concurrent sort/hash queries in a test environment. Observe PGA statistics, `number_passes`, and TEMP usage. Do not simply raise PGA and draw premature conclusions.

### Exercise 13 — Incident Classification

Use a test load window to collect DB time, CPU, wait events, redo, undo, and TEMP metrics. Write a bottleneck hypothesis grounded in metrics, not a single event name.

### Exercise 14 — Before/After Report

Select an identified bottleneck. Document baseline, hypothesis, change, re-measurement results, and impact on other workloads. Explicitly state which evidence confirms or refutes the hypothesis.

## 16. Oracle Reference Documentation

- [Oracle Database Performance Tuning Guide 19c](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/): tuning methodology, CPU, I/O, memory, and database performance.
- [Oracle Database Reference — V$SYS_TIME_MODEL](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SYS_TIME_MODEL.html): DB time, DB CPU, and time model statistics.
- [Oracle Database Reference — V$SYSTEM_EVENT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SYSTEM_EVENT.html): wait event counters.
- [Oracle Database Reference — V$SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html): session state, SQL_ID, and wait information.
- [Oracle Database Reference — V$UNDOSTAT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-UNDOSTAT.html): undo usage, retention, and snapshot-too-old counters.
- [Oracle Database Administrator's Guide — Managing Undo](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-undo.html): undo tablespaces, retention, and transaction behavior.
- [Oracle Database Reference — V$TEMPSEG_USAGE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-TEMPSEG_USAGE.html): temporary segment usage by session.
- [Oracle Database Reference — V$SQL_WORKAREA](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL_WORKAREA.html): workarea statistics for SQL operators.
- [Oracle Database Reference — V$PGASTAT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-PGASTAT.html): PGA statistics.
- [Oracle Database Reference — V$LOG](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOG.html): online redo log groups and status.
- [Oracle Database Reference — V$LOGFILE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOGFILE.html): redo log members.

Bottleneck identification must rely on metrics captured within the exact load window. CPU is confirmed by DB CPU alongside host saturation; I/O requires correlating waits with storage latency and throughput; redo requires distinguishing `log file sync` from LGWR writes and log switches; undo requires checking transactions, retention, and snapshot/space errors; TEMP requires identifying sessions, SQL, and workarea spills. **Locate the operation generating the pressure, measure before and after under the same workload, and only adjust configuration when evidence proves that resource is limiting the system.**
