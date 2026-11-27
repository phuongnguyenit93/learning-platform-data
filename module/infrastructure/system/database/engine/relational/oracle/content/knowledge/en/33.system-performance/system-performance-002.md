# Wait Events, Wait Classes, DB Time, and Distinguishing CPU from Wait Time

When a SQL statement is slow, the first question is usually: "Is Oracle using CPU or waiting?" A session may be spending time running on CPU, or waiting on I/O, locks, redo commits, network, RAC resources, or another component. Looking solely at the SQL statement's elapsed time makes it very difficult to tell which part can be optimized in SQL and which part requires addressing storage, concurrency, application logic, or system configuration.

Oracle records foreground session activity using time model metrics and records waits using wait events. A **wait event** describes a specific wait condition; a **wait class** groups events with similar characteristics; and **DB time** measures total database call time for foreground sessions, consisting of CPU and non-idle waits. Comparing DB time with DB CPU and wait time helps pinpoint where the system is spending its time.

This lesson covers:
- Wait events, wait classes, foreground/background sessions, and ON CPU/WAITING states.
- DB time, DB CPU, non-idle wait time, and Average Active Sessions (AAS).
- Distinguishing CPU-bound, I/O-bound, lock-bound, commit-bound, and network-bound workloads.
- Common wait events in Oracle.
- Reading V$SESSION, V$SYSTEM_EVENT, V$SYSTEM_WAIT_CLASS, and V$SYS_TIME_MODEL.
- Measuring interval deltas instead of reading cumulative counters once.
- Using ASH/AWR/ADDM and SQL trace within proper scope, with privilege/licensing notes.
- Investigation workflow from system level down to session, SQL, and operation.
- Hands-on lab and diagnostic checklist.

Examples use Oracle Database 19c. Event names, views, and instrumentation details may vary by release, platform, RAC, and configuration; consult the Reference for your exact version. Some AWR/ASH/ADDM and SQL Monitor features belong to the Diagnostics Pack or Tuning Pack; verify licensing before use.

## 1. What Is a Wait Event?

A wait event is an event recorded by Oracle when a session must pause to wait for a resource or a condition to complete. For example:
- Waiting for a data block to be read from storage.
- Waiting for another session to release a row lock.
- Waiting for LGWR to write redo and confirm a COMMIT.
- Waiting for a message or data over the network.
- Waiting for a latch/mutex protecting a shared memory structure.
- Waiting for CPU resources under Resource Manager.

A wait event has a specific name, often accompanied by P1/P2/P3 parameters describing the target object or resource being waited on. A wait event does not automatically mean the system has an error. Some waits are normal workload activity; examine duration, frequency, session, SQL, and user impact.

### 1.1. Example of a SELECT Statement

A session runs:

~~~sql
SELECT *
FROM orders
WHERE order_id = :p_order_id;
~~~

During execution, the session may:
1. Run on CPU to parse, optimize, and process logic.
2. Wait for index or table blocks from storage.
3. Wait for a block held or currently being read by another session.
4. Return to CPU to process rows.
5. Send results to the client.

The request's elapsed time is the sum of phases along the execution path. Wait events help identify the portion of time the session was blocked by a specific condition.

### 1.2. Wait Does Not Equal Error

For example, **db file sequential read** is a normal wait event when Oracle reads a block via single-block I/O, commonly seen during index access. It is only noteworthy when read count, latency, or total time impacts the workload.

Similarly, **log file sync** is part of the COMMIT process. A certain amount of waiting is normal. Only when latency or commit frequency is excessive does it warrant investigation.

### 1.3. Foreground and Background Sessions

- Foreground sessions serve client requests or perform foreground database work. DB time is defined based on foreground session time inside database calls.
- Background processes such as DBWn, LGWR, CKPT, PMON, and SMON perform background work. Background process CPU/waits are not directly added to foreground DB time under the time model definition.

This is crucial: DB time is not the sum of every CPU and wait second across all OS processes on the host. When LGWR writes redo, foreground sessions may wait on **log file sync**; LGWR's own file write time is measured in separate background events/contexts.

## 2. What Is a Wait Class?

A wait class is a grouping of wait events with similar characteristics. Instead of scanning hundreds of individual events upfront, DBAs can identify which class consumes the most time and then drill down into specific events.

Common wait classes in Oracle include:

| Wait class | General meaning | Example event |
| --- | --- | --- |
| Administrative | Waits caused by administrative operations | Certain maintenance/DDL operations |
| Application | Waits caused by application logic or application locks | enq: TX - row lock contention |
| Cluster | Waits for inter-instance communication/synchronization in RAC | gc current request, gc cr request |
| Commit | Waits for commit completion | log file sync |
| Concurrency | Waits for shared structure synchronization or concurrent resources | buffer busy waits, mutex waits |
| Configuration | Waits related to system configuration/resources | Certain log file switch waits |
| Idle | Session is idle, waiting on client or timer | SQL*Net message from client |
| Network | Network/protocol waits | SQL*Net more data to client |
| Other | Waits not belonging to other common classes | Event-dependent |
| Scheduler | Scheduler/Resource Manager waits | resmgr:cpu quantum |
| System I/O | I/O for system/background operations | control file sequential read, log file parallel write |
| User I/O | I/O serving user data access | db file sequential read, db file scattered read |

The exact event list and classification should be checked in V$EVENT_NAME of your actual database. Do not classify events from memory based on a different release.

### 2.1. Why Exclude Idle Waits?

A session waiting for the client to send the next command typically shows **SQL*Net message from client**. This is an idle wait: the database is not performing work needed to complete a request during that interval.

Adding idle waits into total wait time to conclude the database is slow yields incorrect conclusions. DB time excludes idle waits. When analyzing workloads, focus on active sessions and non-idle waits.

### 2.2. Wait Class Is Only a Starting Point

If User I/O accounts for significant time, identify the specific event, SQL, object, and storage latency. If Application waits are high, locate the blocker and the lock-holding transaction. If Commit waits are high, check commit frequency, redo path, and LGWR. If Concurrency waits are high, identify the specific latch/mutex/buffer contention.

Never alter configuration based solely on a wait class name.

## 3. DB Time and DB CPU

The Oracle time model provides time counters at the database and session levels.

### 3.1. DB Time

DB time is the total time foreground sessions spend in database calls. It includes:
- Time foreground sessions spend running on CPU during database calls.
- Time foreground sessions spend waiting on non-idle wait events.

DB time is accumulated across all foreground sessions. Consequently, within one wall-clock minute, DB time can increase by more than 60 seconds if multiple sessions are active concurrently.

Example:
- 10 sessions each active for 6 seconds within the same minute.
- Total DB time can be 60 seconds, even though 60 seconds elapsed on the clock.
- If 100 sessions are active concurrently, DB time can grow many times faster than elapsed wall-clock time.

DB time is aggregated session time, not single-user response time and not instance uptime.

### 3.2. DB CPU

DB CPU is the total CPU time consumed by foreground sessions while executing database calls. It does not include all host CPU, such as CPU used by background processes, agents, OS, or other applications.

DB CPU is a subset of DB time. The remainder is primarily time foreground sessions spend waiting on non-idle events.

Approximate relationship over a measurement interval:

~~~text
DB time ≈ DB CPU + non-idle wait time
~~~

This relationship holds at the aggregated time-model level. When comparing across different views and measurement windows, discrepancies may arise due to timing, sampling, foreground/background scope, and counter aggregation behavior.

### 3.3. Querying the Time Model

~~~sql
SELECT
    stat_name,
    ROUND(value / 1000000, 2) AS seconds
FROM v$sys_time_model
WHERE stat_name IN ('DB time', 'DB CPU')
ORDER BY stat_name;
~~~

V$SYS_TIME_MODEL stores VALUE in microseconds. Divide by 1,000,000 to convert to seconds.

These values are cumulative counters since instance startup or counter initialization. Do not use absolute values to compare workloads between two days; compute deltas between two timestamps.

### 3.4. Session-Level Time Model

~~~sql
SELECT
    s.sid,
    s.serial#,
    s.username,
    tm.stat_name,
    ROUND(tm.value / 1000000, 3) AS seconds
FROM v$sess_time_model tm
JOIN v$session s
  ON s.sid = tm.sid
WHERE s.type = 'USER'
  AND tm.stat_name IN ('DB time', 'DB CPU')
ORDER BY s.sid, tm.stat_name;
~~~

This query shows cumulative DB time/DB CPU per session. For long-lived sessions, counters grow continuously; take snapshots at two points in time to measure consumption during the analysis window.

## 4. Average Active Sessions (AAS)

AAS is the average number of active sessions in the database over a given interval. A session is considered active when it is running on CPU or waiting on a non-idle wait event.

Formula:

~~~text
AAS = Delta DB Time (seconds) / Delta Elapsed Time (seconds)
~~~

Example over one minute:
- DB time increases by 240 seconds.
- Elapsed time is 60 seconds.
- AAS = 240 / 60 = 4.

This means an average of four foreground sessions were active throughout the measurement interval.

### 4.1. AAS and DB CPU AAS

Similarly:

~~~text
DB CPU AAS = Delta DB CPU / Delta Elapsed
Non-idle Wait AAS ≈ AAS - DB CPU AAS
~~~

Example:
- DB time increases by 300 seconds in 60 seconds.
- DB CPU increases by 180 seconds.
- AAS = 5.
- DB CPU AAS = 3.
- Non-idle wait AAS is approximately 2.

Interpretation: on average, about three sessions were consuming CPU and two sessions were waiting on non-idle events during the interval. This is an average model; at any specific instant, session counts may differ.

### 4.2. AAS Can Exceed the Number of CPU Cores

AAS includes waiting sessions. Therefore, AAS = 30 on a host with 8 vCPUs does not mean the machine needs 30 CPU cores. Four sessions may be running on CPU while 26 sessions wait on I/O, locks, commits, or network.

DB CPU AAS approximates the number of CPU cores consumed on average by the foreground database workload. To conclude CPU saturation, compare against available CPUs, OS CPU utilization, run queue, CPU throttling, and other processes on the host.

### 4.3. AAS Is Not Connection Count

An idle connection does not contribute to AAS. A connection executing SQL or waiting on a non-idle event does contribute. Connection pool size can be very large while AAS remains low.

## 5. Distinguishing CPU-Bound from Wait-Bound

Do not conclude "the database is slow because of CPU" solely from high CPU utilization, or "slow because of I/O" from a single wait event. Compare DB time, DB CPU, non-idle waits, AAS, and host metrics over the same time window.

### 5.1. CPU-Bound

Common signs:
- DB CPU makes up the majority of DB time.
- DB CPU AAS is high relative to available CPU cores.
- OS CPU utilization is high, run queue grows, or CPU throttling occurs.
- Wait time does not dominate DB time.
- SQL performs heavy computation, parsing, function calls, joins/sorts/hashes, or processes excessive rows.

Investigation direction:
- Find SQL with high DB CPU/elapsed time.
- Inspect execution plans, E-Rows/A-Rows, rows processed, and buffer gets.
- Check parse calls, hard parses, and PL/SQL/function overhead.
- Reduce the volume of data read and processed.
- Use set-based SQL and avoid repetitive round-trip queries from the application.
- Check whether parallelism is increasing CPU contention.

High CPU does not automatically mean more CPUs are needed. A single SQL statement can consume heavy CPU because it processes millions of unnecessary rows or uses a suboptimal plan.

### 5.2. Wait-Bound

Signs:
- DB time is high, while DB CPU accounts for a smaller share.
- Non-idle wait AAS is high.
- One or a few wait classes/events dominate total time.
- OS CPU may not be saturated, yet requests remain slow.

Next, classify the waits:
- User I/O: data block access.
- Application: locks or waits caused by application logic.
- Commit: redo commit synchronization.
- Concurrency: latches, mutexes, buffer contention.
- Network: data transfer/waiting on client.
- Cluster: cache communication between RAC instances.
- Scheduler: Resource Manager CPU allocation.

Being wait-bound does not mean the database server lacks hardware resources. The application might be issuing COMMIT too frequently, holding transactions open too long, returning too much data, or one session may be blocking many others.

### 5.3. Quick Comparison Table

| Metric/Indicator | CPU-bound | Wait-bound |
| --- | --- | --- |
| DB CPU / DB time | Usually high | Usually lower |
| DB CPU AAS | May approach CPU limit | Usually lower than AAS |
| Non-idle wait AAS | Relatively low | High |
| Host CPU | May be saturated / high run queue | May still have idle CPU |
| Wait event | No single dominant event | Dominant event/class present |
| Remediation direction | Reduce CPU work, fix SQL/plan | Identify resource/session causing waits |
| Example | Oversized sorts/hashes, heavy parsing | I/O latency, row locks, log file sync |

These are guiding indicators, not absolute rules. A system can be both CPU-bound and suffer from contention waits simultaneously.

## 6. Common Wait Events

### 6.1. User I/O

| Event | Meaning | Investigation direction |
| --- | --- | --- |
| db file sequential read | Single-block read, common in index access | Index access pattern, random I/O latency, lookup count |
| db file scattered read | Multiblock read, common in full scans/buffered multiblock reads | Is full scan appropriate, table size, MBRC, storage throughput |
| direct path read | Direct read into PGA/private buffers bypassing buffer cache | Large scans, parallel queries, direct path workload |
| direct path read temp | Reading data from temporary tablespace | Sort/hash spills, PGA, workarea sizing |
| read by other session | Session waiting for a block currently being read by another session | Hot blocks/read concurrency, I/O latency |

`db file sequential read` does not necessarily mean an index is misused; primary key lookups may be expected behavior. Check total wait count, average latency, and rows returned.

### 6.2. Commit and Redo

| Event | Meaning | Investigation direction |
| --- | --- | --- |
| log file sync | Foreground waiting for LGWR to confirm commit redo is written | Commit frequency, redo write latency, LGWR workload |
| log file parallel write | LGWR waiting to complete writing redo log files | Redo storage latency, I/O path, log configuration |
| log buffer space | Session cannot write new redo because log buffer lacks suitable free space | Redo generation rate, LGWR throughput, redo path |
| log file switch completion | Waiting for redo log group switch to complete | Log sizing, checkpoint/archive throughput |

`log file sync` is a foreground wait; `log file parallel write` is typically a background LGWR wait. If foreground `log file sync` is high, correlate it with LGWR write latency, but do not sum the two counters as independent portions of DB time.

A common root cause is an application issuing COMMIT after every single row. Batching multiple DML operations in one transaction can reduce commit round trips and `log file sync`, while preserving required atomicity and lock duration constraints.

### 6.3. Application and Row Locks

| Event | Meaning | Investigation direction |
| --- | --- | --- |
| enq: TX - row lock contention | Session waiting for another transaction to release a row lock | Blocker session, long-running transactions, concurrent updates on same row |
| enq: TM - contention | Enqueue wait related to table/DML locks | DDL/DML, table locks, foreign keys/indexes, and transactions |
| enq: TX - allocate ITL entry | Waiting for a transaction slot in a block | Concurrent modifications, INITRANS, block contention |

To locate the blocker, inspect BLOCKING_SESSION, FINAL_BLOCKING_SESSION, ROW_WAIT_*, and the blocker's transaction. Do not immediately kill a session upon seeing a lock wait; determine business ownership and rollback impact first.

### 6.4. Concurrency, Latches, and Mutexes

| Event | Meaning | Investigation direction |
| --- | --- | --- |
| buffer busy waits | Waiting for a buffer block currently being used/modified by another session | Hot blocks, segment contention, concurrent DML |
| cursor: pin S wait on X | Waiting on cursor mutex/pin | Parsing/DDL/invalidations and SQL concurrency |
| library cache: mutex X | Waiting on mutex protecting library cache | Hard parsing, cursor contention, shared SQL |
| latch: cache buffers chains | Waiting on latch over buffer cache chains | Hot blocks, access patterns, and concurrent reads |

Do not treat every concurrency wait by increasing INITRANS or adding indexes. Identify the exact resource, segment, SQL, and access pattern first.

### 6.5. Network

| Event | Meaning | Investigation direction |
| --- | --- | --- |
| SQL*Net more data to client | Database sending additional data to the client | Large result sets, fetch patterns, network throughput |
| SQL*Net more data from client | Database waiting for additional data from the client | Payload/client send behavior, application latency |
| SQL*Net message from client | Database waiting for client to send next command; usually idle | Do not count as a DB time bottleneck |

If `SQL*Net more data to client` is high, check row/column counts returned, LOBs, fetch size, and network. If `SQL*Net message from client` is high, the session is usually idle between requests; do not conclude the database is network-bottlenecked from this event alone.

### 6.6. RAC Cluster

Common events in RAC:
- gc current request
- gc cr request
- gc buffer busy acquire
- gc current block busy
- gc cr block busy

These relate to Global Cache Service and retrieving current/consistent-read blocks from another instance. Analyze by instance, object/block, interconnect latency, and distributed workload. Do not apply RAC diagnostics to single-instance databases.

### 6.7. Scheduler and Resource Manager

Events like `resmgr:cpu quantum` indicate a session is being throttled under a Resource Manager plan. It is not identical to waiting purely on physical CPU. Check consumer groups, plan directives, CPU utilization, and workload priorities.

## 7. Viewing Current Session Wait Events

V$SESSION displays the current state and wait information of sessions.

~~~sql
SELECT
    sid,
    serial#,
    username,
    status,
    sql_id,
    event,
    wait_class,
    state,
    seconds_in_wait,
    blocking_session,
    final_blocking_session,
    module,
    action
FROM v$session
WHERE type = 'USER'
  AND status = 'ACTIVE'
ORDER BY seconds_in_wait DESC;
~~~

Meaning:
- STATUS = ACTIVE indicates the session is in a database call; it may be running on CPU or waiting on a non-idle event.
- EVENT is the current or most recent event depending on state.
- WAIT_CLASS categorizes the event.
- STATE indicates whether the session is currently WAITING or whether the wait has completed.
- BLOCKING_SESSION is the blocker SID if Oracle has identified one.
- MODULE/ACTION helps associate the session with an application/endpoint.

Do not read a single snapshot and conclude that event accounts for most of the request time. A session can switch events rapidly; observe over an interval or use tracing/sampling.

### 7.1. Viewing Only Sessions Currently WAITING

~~~sql
SELECT
    sid,
    serial#,
    username,
    sql_id,
    event,
    wait_class,
    seconds_in_wait,
    state,
    p1text,
    p1,
    p2text,
    p2,
    p3text,
    p3
FROM v$session
WHERE type = 'USER'
  AND state = 'WAITING'
  AND wait_class <> 'Idle'
ORDER BY seconds_in_wait DESC;
~~~

P1/P2/P3 are event-specific parameters. Their meaning varies by event; check V$EVENT_NAME for parameter names and the corresponding event documentation.

### 7.2. Sessions Running on CPU May Not Show a Wait Event

When a session is performing CPU work, it may not be in the WAITING state. V$SESSION.STATUS may be ACTIVE, while EVENT/STATE does not indicate an ongoing wait. Therefore:
- ACTIVE does not imply waiting.
- Seeing no wait event does not imply the session is idle.
- To measure CPU time, use time model/session stats or appropriate sampling.

## 8. Viewing Wait Classes at the System Level

V$SYSTEM_WAIT_CLASS aggregates wait counts and wait time by wait class since instance startup.

~~~sql
SELECT
    wait_class,
    total_waits,
    ROUND(time_waited_micro / 1000000, 2) AS wait_seconds,
    ROUND(
        time_waited_micro / NULLIF(total_waits, 0) / 1000,
        3
    ) AS avg_wait_ms
FROM v$system_wait_class
WHERE wait_class <> 'Idle'
ORDER BY time_waited_micro DESC;
~~~

These counters are cumulative. If the instance has been running for days, the top wait class may reflect historical workload rather than the current issue. To analyze an incident, capture two snapshots and compute deltas for the incident window.

### 8.1. Viewing Specific Events

~~~sql
SELECT
    e.event,
    n.wait_class,
    e.total_waits,
    ROUND(e.time_waited_micro / 1000000, 2) AS wait_seconds,
    ROUND(
        e.time_waited_micro / NULLIF(e.total_waits, 0) / 1000,
        3
    ) AS avg_wait_ms
FROM v$system_event e
JOIN v$event_name n
  ON n.name = e.event
WHERE n.wait_class <> 'Idle'
ORDER BY e.time_waited_micro DESC
FETCH FIRST 30 ROWS ONLY;
~~~

V$EVENT_NAME describes events and wait classes. If versions differ in view columns or multitenant scope, check the Data Dictionary Reference for your release.

### 8.2. Average Wait Alone Is Not Enough to Rank Issues

An event with a 50 ms average wait that occurs only twice may have far less impact than a 1 ms event occurring 2 million times. Inspect simultaneously:
- Total wait time.
- Wait count.
- Average wait.
- Waits/second during the measurement window.
- Associated sessions/SQL/objects.
- Impact on response time.

## 9. Measuring Deltas Over Time

Counters in V$SYS_TIME_MODEL and V$SYSTEM_EVENT accumulate continuously. Performance analysis requires comparing across the same time window.

### 9.1. Capturing Start and End Snapshots

At time T1, record:
- DB time and DB CPU from V$SYS_TIME_MODEL.
- Total waits and TIME_WAITED_MICRO from V$SYSTEM_EVENT or V$SYSTEM_WAIT_CLASS.
- Wall-clock timestamp T1.

After the observation window, at T2 record the same values. Compute deltas:

~~~text
Delta DB time = DB time(T2) - DB time(T1)
Delta DB CPU  = DB CPU(T2) - DB CPU(T1)
Elapsed       = T2 - T1
AAS           = Delta DB time / Elapsed
DB CPU AAS    = Delta DB CPU / Elapsed
~~~

Only compare snapshots from the same instance and same container/scope. If the instance restarts between snapshots, counters may reset; deltas are then invalid.

### 9.2. Capturing a Time Model Snapshot

~~~sql
SELECT
    SYSTIMESTAMP AS captured_at,
    stat_name,
    value
FROM v$sys_time_model
WHERE stat_name IN ('DB time', 'DB CPU');
~~~

Save results to a file/monitoring system or a DBA-managed snapshot table. Do not create snapshot tables in business schemas just for a one-off diagnosis.

### 9.3. Capturing a Wait Class Snapshot

~~~sql
SELECT
    SYSTIMESTAMP AS captured_at,
    wait_class,
    total_waits,
    time_waited_micro
FROM v$system_wait_class
WHERE wait_class <> 'Idle';
~~~

At T2, run the same query again. For each class:

~~~text
Delta wait seconds =
    (TIME_WAITED_MICRO_T2 - TIME_WAITED_MICRO_T1) / 1,000,000
~~~

Then divide the delta by elapsed time to obtain approximate wait-class AAS. Preserve the same instance/container scope and handle counter resets.

### 9.4. Do Not Sum Absolute Counters Across Multiple Sources

Do not add DB time and total wait time as two independent quantities: wait time is already part of DB time. Nor should you add foreground `log file sync` waits with background `log file parallel write` waits to compute DB time; they describe two sides of the same redo activity.

## 10. Session-Level Time Model and Wait Events

When a system serves many users, identify which sessions contribute the most DB time or wait time.

### 10.1. Session Time Model

~~~sql
SELECT
    s.sid,
    s.serial#,
    s.username,
    s.module,
    s.action,
    tm.stat_name,
    ROUND(tm.value / 1000000, 3) AS seconds
FROM v$sess_time_model tm
JOIN v$session s
  ON s.sid = tm.sid
WHERE s.type = 'USER'
  AND tm.stat_name IN ('DB time', 'DB CPU')
ORDER BY tm.value DESC;
~~~

These are cumulative counters per session. With connection pools, a single session may serve many requests over time. Tagging MODULE/ACTION and taking deltas per request/window enables more accurate analysis.

### 10.2. Session Events

~~~sql
SELECT
    se.sid,
    s.serial#,
    s.username,
    s.sql_id,
    se.event,
    n.wait_class,
    se.total_waits,
    ROUND(se.time_waited_micro / 1000000, 2) AS wait_seconds,
    ROUND(
        se.time_waited_micro / NULLIF(se.total_waits, 0) / 1000,
        3
    ) AS avg_wait_ms
FROM v$session_event se
JOIN v$session s
  ON s.sid = se.sid
JOIN v$event_name n
  ON n.name = se.event
WHERE s.type = 'USER'
  AND n.wait_class <> 'Idle'
ORDER BY se.time_waited_micro DESC;
~~~

V$SESSION_EVENT aggregates waits per session since session creation or counter initialization. A long-lived connection-pool session may carry history from many requests. Read deltas or trace per request rather than treating the counter as belonging solely to the current request.

### 10.3. Finding Blockers

~~~sql
SELECT
    sid,
    serial#,
    username,
    sql_id,
    event,
    wait_class,
    blocking_session,
    blocking_session_status,
    final_blocking_session,
    seconds_in_wait,
    module,
    action
FROM v$session
WHERE state = 'WAITING'
  AND wait_class <> 'Idle'
  AND blocking_session IS NOT NULL
ORDER BY seconds_in_wait DESC;
~~~

After identifying the blocker SID, query the blocker's details:

~~~sql
SELECT
    sid,
    serial#,
    username,
    status,
    sql_id,
    event,
    wait_class,
    last_call_et,
    module,
    action
FROM v$session
WHERE sid = :p_blocker_sid;
~~~

Check open transactions, start times, previous SQL, and the application owning the session. Do not terminate a blocker without evaluating rollback consequences and obtaining operational approval.

## 11. ASH and AWR: Observing Over Time

A single V$SESSION snapshot only shows the state at one instant. To understand how workload evolves over an interval, Oracle offers Active Session History (ASH) and Automatic Workload Repository (AWR).

### 11.1. ASH

ASH periodically samples active sessions. Each sample can show:
- Session state: ON CPU or WAITING.
- Wait class/event.
- SQL_ID and plan line.
- Module/action.
- Blocking session.
- Object or related metadata depending on the sample.

ASH helps answer "during the incident window, where did active sessions spend their time?" rather than viewing only one event at query execution time.

Example query on V$ACTIVE_SESSION_HISTORY:

~~~sql
SELECT
    wait_class,
    event,
    session_state,
    COUNT(*) AS samples
FROM v$active_session_history
WHERE sample_time >= SYSTIMESTAMP - INTERVAL '10' MINUTE
GROUP BY wait_class, event, session_state
ORDER BY samples DESC;
~~~

This example illustrates how to group recent samples. It is not microsecond-exact timing; sample counts estimate the distribution of active time. Ensure the right time zone, container, instance, and SQL/module scope are selected.

### 11.2. ON CPU in ASH

ASH records `SESSION_STATE = 'ON CPU'` when a session is running on CPU at the sample instant. When WAITING, the event and wait class show what the session is waiting on.

A session absent from ASH because it is idle is not missing; ASH focuses on active sessions. Because sampling can miss very short waits, do not treat sample counts as a complete audit of every wait.

### 11.3. AWR

AWR stores performance statistics snapshots over time, supporting workload comparison between two intervals and report generation. AWR is commonly used to inspect:
- DB time, DB CPU, and load profile.
- Top foreground wait events.
- Wait class distribution.
- SQL ordered by elapsed time, CPU, gets, or reads.
- Instance activity and time model.

AWR/ASH/ADDM are features of the Oracle Diagnostics Pack under Oracle licensing policy. Before running reports or querying the corresponding historical views, verify licensing/entitlements and the `control_management_pack_access` parameter with the DBA. Do not assume every environment is licensed to use them.

### 11.4. AWR Does Not Replace Detailed Tracing

AWR helps locate problem areas at the system/time-interval level. SQL trace/TKPROF or application instrumentation provides detail for a specific session/request. Combining multiple layers yields more reliable conclusions.

## 12. SQL Trace and DBMS_MONITOR

SQL Trace records parse, execute, fetch, waits, and statistics for a session/SQL. TKPROF formats trace files to analyze call counts, elapsed time, CPU, disk reads, query/current gets, and wait events.

DBMS_MONITOR can enable tracing by session, client identifier, or service/module/action depending on API and privileges. Example tracing a session:

~~~sql
BEGIN
    DBMS_MONITOR.SESSION_TRACE_ENABLE(
        session_id => 123,
        serial_num => 456,
        waits      => TRUE,
        binds      => FALSE
    );
END;
/
~~~

Disable tracing after collection:

~~~sql
BEGIN
    DBMS_MONITOR.SESSION_TRACE_DISABLE(
        session_id => 123,
        serial_num => 456
    );
END;
/
~~~

SID and SERIAL# must come from the target session. Do not enable binds unless necessary, as bind data can contain sensitive values. Tracing creates files and overhead; enable only for the required duration, restrict file access, and clean up files per retention policy.

## 13. Complementary Metrics to Distinguish CPU from Waits

### 13.1. Host CPU

DB CPU is not total host CPU utilization. Compare:
- Host CPU user/system/idle.
- Run queue/load average.
- CPU ready/steal/throttling in VMs/cloud.
- Available CPU cores/vCPUs.
- CPU consumed by Oracle foreground and background processes.

If host CPU is high while DB CPU is low, other processes or background workloads may be consuming CPU. If DB CPU is high while the host still has headroom, capacity may remain or the workload may be spread across many cores.

### 13.2. I/O Latency and Throughput

For User I/O, check:
- Physical read count.
- Average read latency.
- IOPS and throughput.
- Queue depth.
- Storage tier and ASM/diskgroup.
- SQL/objects generating the I/O.

Do not conclude storage is slow simply because `db file sequential read` tops the list. The event count may be high due to millions of small lookups; average latency may still be good while total time is large.

### 13.3. Redo and Commit

For `log file sync`, inspect:
- Commit count and commits per transaction.
- Redo size/rate.
- LGWR write latency.
- `log file parallel write`.
- Storage path of online redo logs.
- Whether the application commits row-by-row.

Increasing the log buffer is not a default fix for `log file sync`. If latency stems from redo storage or overly frequent commits, resizing the buffer may not address the root cause.

### 13.4. Lock Contention

For row locks:
- Identify the blocker and waiter.
- Inspect the SQL holding the transaction.
- Look for long transactions, user think time inside transactions, or missing rollbacks on error.
- Check whether the same row/key is updated concurrently by many requests.
- Verify appropriate foreign keys/indexes for the DML involved.

Do not kill a blocker solely because it leads a wait report. A session running a business transaction may trigger a massive rollback and cause broader impact.

### 13.5. Network and Fetch

If Network waits increase:
- Measure application/database round trips.
- Check row/column counts returned.
- Inspect LOBs and large payloads.
- Check fetch size, batch fetching, and N+1 queries.
- Distinguish database waiting for client commands from database sending data to the client.

`SQL*Net message from client` is typically an idle wait and does not contribute to DB time. `SQL*Net more data to client` is a different event and may reflect large result transfers.

## 14. Diagnostic Workflow from System to SQL

When receiving a report that "Oracle is slow", proceed in order:

### Step 1: Define the Incident Window

Record:
- Start/end timestamps.
- Database, instance, PDB/service.
- Affected endpoints or batch jobs.
- User/request volume.
- Any recent deployments, data loads, or maintenance.

All counters must be compared over the same time window and scope.

### Step 2: Compute DB Time, DB CPU, and AAS

Capture V$SYS_TIME_MODEL deltas. Calculate:
- DB time/elapsed.
- DB CPU/elapsed.
- AAS.
- DB CPU AAS.
- Approximate non-idle wait AAS.

If DB time is low yet users still experience slowness, check network/client/application/connection pool; time spent outside database calls is not captured in DB time.

### Step 3: Inspect Wait Classes and Events

Capture V$SYSTEM_WAIT_CLASS and V$SYSTEM_EVENT deltas, excluding Idle. Identify:
- Wait classes consuming the most time.
- Events with large total wait time.
- Average wait and wait count.
- Events spiking abnormally compared to baseline.

### Step 4: Identify Sessions and SQL

Use V$SESSION, V$SESSION_EVENT, V$SESS_TIME_MODEL, tracing, or ASH/AWR if licensed. Correlate SQL_ID, module/action, blocking sessions, and objects.

### Step 5: Read Execution Plans

Use DBMS_XPLAN.DISPLAY_CURSOR when authorized and the cursor is available. If runtime stats are present, compare E-Rows/A-Rows/Starts, Buffers, Reads, and A-Time.

### Step 6: Form Hypotheses by Bottleneck Type

| Evidence | Investigation direction |
| --- | --- |
| High DB CPU AAS, saturated host CPU | SQL CPU, plan, parsing, parallelism |
| User I/O waits rising, high read latency | Storage, access path, data volume |
| High User I/O wait time but low latency | Excessive reads/lookups, SQL/index design |
| Application waits/row locks rising | Blocker, transaction duration, hot rows |
| Commit waits rising | Commit frequency, redo write latency |
| Concurrency waits rising | Hot blocks, latches/mutexes, parse contention |
| Network send-data waits rising | Result size, fetch size, round trips |
| Scheduler waits rising | Resource Manager, consumer groups, CPU allocation |
| RAC Cluster waits rising | Interconnect, hot blocks, service placement |

### Step 7: Validate Changes

Change only one factor at a time when possible. Compare under the same workload:
- DB time and DB CPU.
- AAS and wait classes.
- SQL elapsed/CPU/buffers/reads.
- Application p95/p99 latency.
- Error rate and throughput.

Do not declare success just because one wait event drops; the workload may have shifted the bottleneck elsewhere.

## 15. Lab: Observing DB Time, DB CPU, and Wait Classes

This lab only reads dynamic performance views and runs lightweight queries. Read access to V$ views is required. If you lack privileges, ask the DBA to run them or grant minimal read privileges in a practice environment.

### 15.1. Reading DB Time and DB CPU

~~~sql
SELECT
    stat_name,
    ROUND(value / 1000000, 3) AS seconds
FROM v$sys_time_model
WHERE stat_name IN ('DB time', 'DB CPU')
ORDER BY stat_name;
~~~

Record the results at T1. Run the lab workload for a defined period, then query again at T2. Subtract to find the difference for each statistic.

### 15.2. Computing AAS

Suppose you recorded:
- DB time T1 and T2 in seconds.
- DB CPU T1 and T2 in seconds.
- Elapsed time between snapshots is 60 seconds.

Calculate:

~~~text
DB time delta = DB time T2 - DB time T1
DB CPU delta  = DB CPU T2 - DB CPU T1
AAS           = DB time delta / 60
DB CPU AAS    = DB CPU delta / 60
Wait AAS      = AAS - DB CPU AAS
~~~

If Wait AAS is noticeably negative, check for mismatched snapshot scopes, counter resets, or unit errors. In principle, DB CPU is a component of DB time.

### 15.3. Viewing Wait Classes

~~~sql
SELECT
    wait_class,
    total_waits,
    ROUND(time_waited_micro / 1000000, 2) AS wait_seconds,
    ROUND(
        time_waited_micro / NULLIF(total_waits, 0) / 1000,
        3
    ) AS avg_wait_ms
FROM v$system_wait_class
WHERE wait_class <> 'Idle'
ORDER BY time_waited_micro DESC;
~~~

Save snapshots at two timestamps and compute deltas. Do not use absolute numbers since startup to describe a short incident.

### 15.4. Viewing Detailed Events

~~~sql
SELECT
    e.event,
    n.wait_class,
    e.total_waits,
    ROUND(e.time_waited_micro / 1000000, 2) AS wait_seconds
FROM v$system_event e
JOIN v$event_name n
  ON n.name = e.event
WHERE n.wait_class <> 'Idle'
ORDER BY e.time_waited_micro DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Pick a top event and record its wait count, total time, and average wait. Determine whether the event stems from your lab workload or historical workload.

### 15.5. Viewing Waiting Sessions

~~~sql
SELECT
    sid,
    serial#,
    username,
    sql_id,
    event,
    wait_class,
    state,
    seconds_in_wait,
    blocking_session,
    module,
    action
FROM v$session
WHERE type = 'USER'
  AND state = 'WAITING'
  AND wait_class <> 'Idle'
ORDER BY seconds_in_wait DESC;
~~~

Run this query while a workload is active. A single snapshot can miss short waits; take multiple snapshots or use appropriate tracing/sampling.

## 16. Lab: Creating Controlled Wait Scenarios

Perform this in an isolated lab database/schema, never on production business tables. Some scenarios require two SQL*Plus/SQLcl sessions.

### 16.1. Create the Lock Table

~~~sql
CREATE TABLE lab_wait_lock (
    id NUMBER PRIMARY KEY,
    value NUMBER
);

INSERT INTO lab_wait_lock VALUES (1, 100);
COMMIT;
~~~

### 16.2. Create a Row Lock

Session A:

~~~sql
UPDATE lab_wait_lock
SET value = value + 1
WHERE id = 1;
-- Do not COMMIT or ROLLBACK yet.
~~~

Session B:

~~~sql
UPDATE lab_wait_lock
SET value = value + 10
WHERE id = 1;
~~~

Session B will wait on the row lock. From an observer session, inspect V$SESSION for EVENT `enq: TX - row lock contention`, WAIT_CLASS, and BLOCKING_SESSION.

After observing, in Session A:

~~~sql
ROLLBACK;
~~~

Session B will resume. Then roll back Session B to restore the lab to its initial state.

### 16.3. Create a Read Workload

Run a query scanning many rows in a larger lab table, or create a lab table with sufficient data and indexes. Observe User I/O events. Results depend on the buffer cache and storage; if data is already cached, significant physical read waits may not appear.

Do not use hints or flush the system-wide buffer cache merely to force I/O. Flushing affects other workloads and requires DBA privileges.

### 16.4. Observe Commit Waits

Execute a batch of DML and then COMMIT in a lab session. Inspect `log file sync` in V$SESSION/V$SYSTEM_EVENT over the measurement interval. The wait may be very brief and hard to catch in a single snapshot; use tracing or controlled repeated runs if needed.

Do not intentionally flood a shared database with heavy COMMITs just to induce waits. Only observe authorized lab workloads.

### 16.5. Clean Up the Lab Table

~~~sql
DROP TABLE lab_wait_lock PURGE;
~~~

## 17. Common Mistakes When Reading Waits

| Symptom | Misinterpretation | Correct Interpretation |
| --- | --- | --- |
| `SQL*Net message from client` is at the top | The database is network-bottlenecked | Usually an idle wait; session is waiting on the client |
| `db file sequential read` appears | Indexes are always bad | This is a normal single-block read; check latency and volume |
| `log file sync` is high | Increasing log buffer will definitely fix it | Check commit frequency and redo write latency |
| AAS exceeds CPU count | Database needs more CPUs than AAS | AAS includes CPU and waits; compare DB CPU AAS with host CPU |
| DB time exceeds elapsed time | Broken counter | DB time sums time across multiple concurrent foreground sessions |
| DB CPU is low, requests still slow | Database has no problem | Could be wait-bound or waiting outside the database |
| A wait event has a high average | It must be the biggest bottleneck | Check total wait time, wait count, and impact |
| V$SYSTEM_EVENT time is huge | This is the current incident's wait time | Counter accumulates since startup; compute deltas |
| Session is ACTIVE | Session is running on CPU | ACTIVE may be waiting on a non-idle event |
| No wait event visible | Session is inactive | Session may be ON CPU |
| `enq: TX` is high | Kill the blocker immediately | Identify blocker, transaction, and rollback impact |
| `direct path read temp` is high | Datafile storage is slow | Likely sort/hash spilling to TEMP |
| `gc` waits are high | Disk I/O is slow | In RAC, inspect Global Cache/interconnect |
| `resmgr:cpu quantum` | CPU hardware is failing | Check Resource Manager consumer groups/plans |
| Adding DB time and wait time | Total active time | Wait time is already inside DB time; do not double-count |

## 18. Performance Report Checklist

A wait analysis report should include:
- Time window and timezone.
- Database, instance, PDB/service.
- Affected request counts and workloads.
- Delta DB time and DB CPU.
- AAS, DB CPU AAS, and non-idle wait AAS.
- Top wait classes and events by delta.
- Relevant SQL_ID/child cursor and module/action.
- Blocker/session/object if lock waits are involved.
- Runtime plan and cardinalities if available.
- Host CPU, run queue, I/O latency, and network metrics.
- Root-cause hypotheses and supporting evidence.
- Tested changes and before/after results.
- Privileges/licensing status of any historical tools used.

Do not send bind values, SQL text, or trace files containing sensitive data outside authorized boundaries.

## 19. Practice Exercises

### Exercise 1 — Time Model

Query DB time and DB CPU at two timestamps one minute apart. Compute the deltas and explain why cumulative counters cannot be used directly as incident duration.

### Exercise 2 — AAS

A 120-second interval has a DB time delta of 600 seconds and a DB CPU delta of 420 seconds. Compute AAS, DB CPU AAS, and non-idle wait AAS. Interpret the average active session counts.

### Exercise 3 — CPU-Bound

Create a CPU workload in a lab schema and observe DB CPU AAS and host CPU. Propose a method to locate top CPU-consuming SQL.

### Exercise 4 — User I/O

Run a query reading a large table. Compare `db file sequential read`, `db file scattered read`, and `direct path read` if they appear. Record counts, total time, and average latency.

### Exercise 5 — Row Lock

Perform the two-session lab in Section 16. Locate the waiter and blocker, and record SQL_ID, SID, SERIAL#, and event. Explain why the waiter cannot proceed.

### Exercise 6 — Commit

Compare row-by-row commit workloads with batched commits in a lab schema. Observe `log file sync` counts, elapsed time, and transaction semantics.

### Exercise 7 — Idle vs. Non-Idle

Locate sessions showing `SQL*Net message from client`. Explain why this event should not be included in database bottleneck analysis.

### Exercise 8 — Wait Classes

Take two snapshots of V$SYSTEM_WAIT_CLASS and compute deltas for each class. Rank classes by wait AAS and state which events require further investigation.

### Exercise 9 — Session Tracing

Set MODULE/ACTION, enable SQL trace for a lab session, and disable trace after execution. Use TKPROF to inspect parse/execute/fetch, CPU, elapsed, and wait statistics.

### Exercise 10 — Incident Report

Write a brief report covering DB time, DB CPU, AAS, top wait classes/events, relevant SQL, hypotheses, and additional evidence to collect. Clearly distinguish proven facts from hypotheses.

## 20. Cleanup and Environment Restoration

- Roll back any open transactions in lab sessions.
- Drop the LAB_WAIT_LOCK table and any objects you created.
- Disable SQL trace after collection.
- Restore STATISTICS_LEVEL if modified.
- Turn off unneeded instrumentation.
- Protect/delete trace files according to policy.
- Never flush the buffer cache, kill sessions, or alter Resource Manager on shared databases just to reproduce lab scenarios.

## Summary

Wait events describe individual session waits; wait classes group related events; and DB time is the total time foreground sessions spend in database calls, comprising DB CPU and non-idle waits. DB time can exceed wall-clock elapsed time because multiple sessions operate concurrently. AAS is computed as delta DB time divided by elapsed time; DB CPU AAS shows average CPU usage, while the difference between AAS and DB CPU AAS estimates active wait time.

To distinguish CPU-bound from wait-bound workloads, take snapshots with matching scope, compute deltas, exclude idle waits, and correlate DB time, DB CPU, wait classes, and host CPU/I/O/network metrics. Then drill down from wait class to event, session, SQL_ID, and execution plan. `log file sync`, row locks, User I/O, concurrency, network, and RAC cluster waits have different root causes; never tune configuration based solely on event names. Use V$ views for current observations/counters, SQL trace for specific sessions, and ASH/AWR where properly authorized and licensed. Always verify changes with before/after workload and latency measurements.

## Oracle Reference Documentation

- [Oracle Database Performance Tuning Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/) — performance methodology, wait events, time model, and tuning.
- [Oracle Database Reference — V$SYS_TIME_MODEL (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SYS_TIME_MODEL.html) — DB time, DB CPU, and time model statistics.
- [Oracle Database Reference — V$SESS_TIME_MODEL (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESS_TIME_MODEL.html) — session-level time model.
- [Oracle Database Reference — V$SYSTEM_WAIT_CLASS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SYSTEM_WAIT_CLASS.html) — wait totals by wait class.
- [Oracle Database Reference — V$SYSTEM_EVENT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SYSTEM_EVENT.html) — wait counters by event.
- [Oracle Database Reference — V$EVENT_NAME (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-EVENT_NAME.html) — event names, parameters, and wait classes.
- [Oracle Database Reference — V$SESSION (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html) — session state, current wait, and blocking session.
- [Oracle Database Reference — V$ACTIVE_SESSION_HISTORY (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-ACTIVE_SESSION_HISTORY.html) — active session samples; Diagnostics Pack note.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_MONITOR (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_MONITOR.html) — SQL trace by session/service/module/client identifier.
- [Oracle Database Licensing Information User Manual (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/) — licensing terms for Diagnostics Pack and Tuning Pack.

When deploying on Oracle releases other than 19c, consult the Performance Tuning Guide and Data Dictionary Reference for your exact version, particularly regarding time model definitions, wait classes/events, multitenant scope, ASH/AWR, and licensing terms.
