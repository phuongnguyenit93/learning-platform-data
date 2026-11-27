# ORA-00018, ORA-00020, and Session/Process Limits

Oracle Database limits the number of concurrent sessions and processes to protect instance resources. When those limits are reached, applications encounter ORA-00018 (maximum number of sessions exceeded) or ORA-00020 (maximum number of processes exceeded). These two errors are related yet distinct: a session is a logical working state inside the database, while a process is an operating-system Oracle process serving a session or background task.

In a dedicated server architecture, each user session typically requires its own server process. Increasing connection pool sizes therefore raises both `sessions` and `processes` together. With shared server, DRCP, or multiplexing models, the session-to-process relationship differs. Beyond user connections, an instance also requires processes for background tasks, scheduler jobs, parallel execution, database links, and administrative operations.

Proper remediation begins by identifying which resource hit its limit, which instance is affected, and which group of sessions/processes consumes capacity. Only then should you decide whether to clean up sessions, fix connection leaks/pool sizing, adjust workloads, or raise parameters. Increasing `PROCESSES` without verifying RAM, OS process limits, and total load may merely shift the failure to the operating system layer.

After this lesson, you will be able to:

- Distinguish database session, Oracle process, client process, and connection.
- Explain the causes and symptoms of ORA-00018/ORA-00020.
- Read `V$RESOURCE_LIMIT`, `V$SESSION`, `V$PROCESS`, and `GV$` views in RAC.
- Analyze sessions by user, status, machine, program, module, and service.
- Identify oversized connection pools, connection leaks, and login storms.
- Understand `PROCESSES`, `SESSIONS`, and how to configure parameters.
- Troubleshoot incidents when new connections cannot be opened.
- Design capacity for dedicated/shared server, RAC, and CDB/PDB.
- Test limits safely in a lab environment.
- Establish monitoring, alerting, runbooks, and capacity-expansion plans.

> Parameter names, PDB configurability, view/column availability, and behavior may vary by Oracle Database release. Examples use SQL*Plus and common Oracle JDBC patterns. Verify against the Oracle Database Reference, Licensing Guide, and your actual architecture before modifying production.

## 1. Session, Process, and Connection

### 1.1. Database Session

A session is the working state of a user or program logged into the database. A session carries state such as:

- User/schema and active privileges.
- Session parameters such as NLS, timezone, and optimizer settings.
- Current transaction and held locks.
- Currently executing or last executed SQL.
- Package state, application context, and temporary state.
- Client identifier, module/action, and service.

One application can open multiple sessions under the same database user. A session can also stay alive for a long time even when no SQL is executing at the moment of inspection.

### 1.2. Oracle Process

A process is an Oracle operating-system process. The instance uses processes for:

- Foreground/server processes serving user sessions.
- Background processes such as DBWn, LGWR, CKPT, SMON, PMON, ARCn, and many others.
- Job queue / scheduler slaves.
- Parallel execution servers.
- Recovery, networking, memory, and administrative tasks.

Not every process maps to a user session. Some processes serve the instance itself, and some sessions lack dedicated server processes in a shared server architecture.

### 1.3. Client Process

A client process is an application process outside Oracle, such as a JVM running Spring Boot, a batch worker, SQL*Plus, or a monitoring agent. It connects over Oracle Net to a listener/service. A client process is not an Oracle server process.

A single JVM can hold many JDBC connections; each connection can map to a database session. Counting JVMs or pods alone is therefore insufficient to know the database session count.

### 1.4. Connection

A JDBC `Connection` is a client-side handle. With a connection pool, a logical connection borrowed and returned to the pool can reuse the same physical database session across sequential requests. While the connection stays open in the pool, the session usually remains present on the database even when the application is not sending SQL.

A connection pool with a max size of 20 typically opens up to 20 database sessions per pool instance under dedicated server, though total sessions also depend on connection creation behavior, shared pools, DRCP, and other pools.

### 1.5. Dedicated Server

In dedicated server mode, each client session is served by its own Oracle server process. This model is simple and widely used with JDBC applications and connection pools.

Advantages:

- Each session has its own server process, making tracking straightforward.
- Session workloads are isolated at the process level.
- Fits applications with properly bounded connection pools.

In return, high concurrent session counts bring high server process counts, memory stacks, and OS resource consumption.

### 1.6. Shared Server

Shared server lets multiple sessions share a pool of shared server processes via dispatchers. It reduces the number of server processes needed for many idle sessions or high-concurrency, short-duration workloads.

Shared server does not eliminate sessions. Sessions still consume session resources and can hold transactions/locks. Some workloads require dedicated server or are unsuitable for shared server; check driver/service configuration and feature support before switching.

### 1.7. DRCP

Database Resident Connection Pooling (DRCP) manages a server-side pool so many client connections can share pooled servers. It reduces server process/session memory footprints for applications with numerous short-lived client connections when workload and connection classes align.

DRCP does not replace every client-side connection pool and does not fix transaction leaks. Verify DRCP support, connection classes, purity, and lifecycle per Oracle JDBC/DRCP documentation.

### 1.8. Overall Relationship

```text
CLIENT APPLICATIONS
  JVM A       JVM B       Batch / Admin
    |           |              |
    +-----------+--------------+
                |
          JDBC CONNECTIONS
                |
          Oracle Listener
                |
          DATABASE SERVICE
                |
       +--------+---------+
       |                  |
   DEDICATED            SHARED
   SERVER               SERVER
       |                  |
       v                  v
    SESSION             SESSION
       |                  |
       +------ DATABASE --+

Instance also has background/parallel/job processes
```

## 2. ORA-00018: maximum number of sessions exceeded

### 2.1. Meaning

ORA-00018 indicates the database cannot create another session because the session limit has been reached. This is typically enforced by the `SESSIONS` initialization parameter or an applicable resource/session policy, depending on message and context.

When it occurs, applications fail to log in or operations requiring new sessions fail. Existing sessions can continue running; the error does not necessarily halt the entire instance.

### 2.2. Common Causes

- Sum of JDBC pool max sizes across multiple JVMs/pods is too large.
- Connections are not closed/returned to the pool due to leaks.
- Applications hold connections while calling external services or waiting on users.
- Batch/scheduler jobs spawn many concurrent sessions.
- Monitoring, ETL, reporting, and DBA tools open additional sessions.
- Login storms after restarts or failovers.
- Long-lived inactive sessions holding slots.
- A specific user or service experiencing a concurrency spike.

### 2.3. INACTIVE Sessions Still Consume Slots

`INACTIVE` only means the session is not currently executing SQL; the session remains logged in and occupies a session slot. Connection pools keep idle connections open for reuse, so session counts often exceed active request counts.

Do not assume every `INACTIVE` session is a leak. Distinguish valid pool idle connections, sessions waiting on clients, sessions holding open transactions, and genuinely abandoned sessions.

### 2.4. ORA-00018 vs. SESSIONS_PER_USER

A profile enforcing `SESSIONS_PER_USER` can raise ORA-02391 (`exceeded simultaneous SESSIONS_PER_USER limit`), which differs from ORA-00018 (instance/session resource limit). When diagnosing, check user profiles and resource limits so the two causes are not confused.

### 2.5. Application Symptoms

- Pool reports unable to acquire connections or hits acquisition timeouts.
- New logins/connections fail with ORA-00018.
- Session count approaches `limit_value` in `V$RESOURCE_LIMIT`.
- Connection count scales up with replica/pod count or after deployments.
- `INACTIVE` session count climbs steadily despite stable request rates.

## 3. ORA-00020: maximum number of processes exceeded

### 3.1. Meaning

ORA-00020 indicates Oracle cannot spawn another process because the `PROCESSES` limit has been reached. This can occur when spawning a server process for a user connection or when the instance needs a process for background, parallel, or job tasks.

### 3.2. Common Causes

- `PROCESSES` set too low for actual concurrency.
- Sudden surge in dedicated server connections.
- Cumulative connection pools across multiple apps exceeding capacity.
- Parallel queries/DML spawning numerous PX servers.
- Too many scheduler jobs or batch jobs running concurrently.
- Database links or remote workloads spawning additional server processes.
- Background processes or instance features requiring extra processes.
- Session/process leaks or connection storms.

### 3.3. Process Limit Can Exhaust Even When Session Count Looks Low

The process limit covers more than foreground session processes. Background, parallel execution, job queue, and other processes all consume `PROCESSES`. Thus a `V$SESSION` count below `PROCESSES` does not prove free process slots remain.

### 3.4. Dedicated Server vs. Shared Server

Under dedicated server, each user session typically adds roughly one server process. Shared server can serve many sessions using fewer shared server processes, though it still needs dispatchers/shared server processes and session slots. Architectural changes must match the workload, not merely dodge ORA-00020.

### 3.5. Application and Database Symptoms

- Listener accepts requests, yet the database cannot spawn server processes.
- New connections fail, often reporting ORA-00020.
- `V$RESOURCE_LIMIT` shows `processes` approaching its limit.
- `V$PROCESS` count is high; inspect background/foreground composition.
- Parallel query or job concurrency surges.
- Alert log records process limit errors and details on the process that failed to start.

## 4. Distinguishing ORA-00018 and ORA-00020

| Criterion | ORA-00018 | ORA-00020 |
| --- | --- | --- |
| Exhausted resource | Sessions | Processes |
| Key parameter | `SESSIONS` | `PROCESSES` |
| Counted unit | Database sessions | Oracle processes |
| Inactive session | Still consumes a session slot | May still hold a server process |
| Background process | Has distinct session/resource behavior; not identical to user sessions | Consumes a process |
| Shared server | Still bound by session limit | Reduces server processes per session, though process limits still apply |
| First investigation step | `V$RESOURCE_LIMIT` sessions, `V$SESSION` | `V$RESOURCE_LIMIT` processes, `V$PROCESS` |

### 4.1. Both Errors Can Occur Together

In dedicated server mode, session and process counts are tightly coupled. If both resources near exhaustion, whichever hits its cap first determines which error surfaces. Scaling up a pool increases both session counts and server process counts simultaneously.

### 4.2. Look Beyond a Single Service's Connections

Limits are usually enforced at the instance level, whereas connections arrive from multiple services, schemas, applications, batches, admin tools, and background tasks. Compare the total across all workloads against instance capacity.

## 5. Checking Parameters and Resource Limits

### 5.1. SHOW PARAMETER

In SQL*Plus:

```sql
SHOW PARAMETER processes;
SHOW PARAMETER sessions;
SHOW PARAMETER transactions;
SHOW PARAMETER shared_servers;
SHOW PARAMETER dispatchers;
SHOW PARAMETER resource_limit;
```

Inspect effective values. `SHOW PARAMETER` displays values from the current instance/session context; in RAC, verify each instance.

### 5.2. V$PARAMETER

```sql
SELECT
    name,
    value,
    isdefault,
    isses_modifiable,
    issys_modifiable
FROM v$parameter
WHERE name IN (
    'processes',
    'sessions',
    'transactions',
    'shared_servers',
    'dispatchers'
)
ORDER BY name;
```

Metadata columns show whether parameters can be altered dynamically at session or system level; `PROCESSES` is static and requires a restart to take effect. Verify against your release and active SPFILE/PFILE.

### 5.3. V$RESOURCE_LIMIT

This is the key view for tracking resource utilization:

```sql
SELECT
    resource_name,
    current_utilization,
    max_utilization,
    initial_allocation,
    limit_value
FROM v$resource_limit
WHERE resource_name IN ('processes', 'sessions', 'transactions')
ORDER BY resource_name;
```

- `CURRENT_UTILIZATION`: resources currently in use at query time.
- `MAX_UTILIZATION`: peak usage since instance startup or since counters were reset per Oracle rules.
- `INITIAL_ALLOCATION`: initial allocation.
- `LIMIT_VALUE`: active limit or unlimited depending on resource.

`MAX_UTILIZATION` is a high-water mark, not the current count. Compare both current and max against the limit to understand both live state and peaks.

### 5.4. Monitoring Over Time

Persist periodic snapshots of `V$RESOURCE_LIMIT` to a monitoring repository. Querying once after an incident subsides may show normal `current_utilization`, while `max_utilization` preserves the peak.

### 5.5. RAC: GV$RESOURCE_LIMIT

In RAC, inspect each instance:

```sql
SELECT
    inst_id,
    resource_name,
    current_utilization,
    max_utilization,
    initial_allocation,
    limit_value
FROM gv$resource_limit
WHERE resource_name IN ('processes', 'sessions', 'transactions')
ORDER BY inst_id, resource_name;
```

Never sum utilization across all instances and compare it against a single-instance limit. Evaluate each instance and service placement individually.

## 6. Counting Sessions and Analyzing Sources

### 6.1. Total Sessions by TYPE/STATUS

```sql
SELECT
    type,
    status,
    COUNT(*) AS session_count
FROM v$session
GROUP BY type, status
ORDER BY type, status;
```

`TYPE` usually separates `USER` and `BACKGROUND`. Inspect user and background sessions separately rather than treating all sessions as application connections. `ACTIVE`/`INACTIVE` reflects status at snapshot time.

### 6.2. By Username

```sql
SELECT
    username,
    status,
    COUNT(*) AS session_count
FROM v$session
WHERE type = 'USER'
GROUP BY username, status
ORDER BY session_count DESC;
```

### 6.3. By Machine/Program

```sql
SELECT
    username,
    machine,
    program,
    module,
    service_name,
    status,
    COUNT(*) AS session_count
FROM v$session
WHERE type = 'USER'
GROUP BY
    username, machine, program, module,
    service_name, status
ORDER BY session_count DESC;
```

This query helps pinpoint which application, pod, or agent opens the most sessions. `MACHINE`/`PROGRAM` may be missing or self-reported by clients; correlate with `module`, `action`, `client_identifier`, and pool metrics.

### 6.4. ACTIVE Sessions

```sql
SELECT
    sid,
    serial#,
    username,
    status,
    machine,
    program,
    module,
    action,
    sql_id,
    event,
    last_call_et
FROM v$session
WHERE type = 'USER'
  AND status = 'ACTIVE'
ORDER BY last_call_et DESC;
```

`ACTIVE` does not strictly mean running on CPU; the session may be waiting on a wait event. Check `EVENT`, `WAIT_CLASS`, `SQL_ID`, and `blocking_session`.

### 6.5. Long-Idle INACTIVE Sessions

```sql
SELECT
    sid,
    serial#,
    username,
    machine,
    program,
    module,
    service_name,
    last_call_et,
    sql_id,
    status
FROM v$session
WHERE type = 'USER'
  AND status = 'INACTIVE'
ORDER BY last_call_et DESC
FETCH FIRST 100 ROWS ONLY;
```

`LAST_CALL_ET` measures seconds elapsed since the session entered its current `ACTIVE`/`INACTIVE` state. Long-idle sessions can be legitimate pool idle connections; check pool max/idle settings and transaction state before calling them leaks.

### 6.6. Sessions with Open Transactions

```sql
SELECT
    s.sid,
    s.serial#,
    s.username,
    s.status,
    s.machine,
    s.program,
    s.module,
    s.last_call_et,
    t.start_time,
    t.used_ublk,
    t.used_urec
FROM v$session s
JOIN v$transaction t
  ON t.ses_addr = s.saddr
ORDER BY t.start_time;
```

## 7. Counting Processes and Analyzing Server Processes

### 7.1. Total Oracle Processes

```sql
SELECT
    COUNT(*) AS process_count
FROM v$process;
```

`V$PROCESS` lists current Oracle processes in the instance. Compare against `V$RESOURCE_LIMIT` processes; the two views offer different perspectives and can shift between snapshots.

### 7.2. Classifying Processes

```sql
SELECT
    pname,
    background,
    program,
    COUNT(*) AS process_count
FROM v$process
GROUP BY pname, background, program
ORDER BY process_count DESC;
```

`pname`/`background` identify background processes; `program` typically shows executable/client or server process details. Never judge a process abnormal solely from its program name.

### 7.3. Mapping Sessions to Processes

```sql
SELECT
    s.sid,
    s.serial#,
    s.username,
    s.status,
    s.server,
    s.machine,
    s.program,
    s.module,
    p.pid AS oracle_pid,
    p.spid AS os_pid,
    p.program AS server_program
FROM v$session s
LEFT JOIN v$process p
  ON p.addr = s.paddr
WHERE s.type = 'USER'
ORDER BY s.username, s.sid;
```

Dedicated server sessions usually map 1:1 to a server process. Shared server and other models differ; do not use this join as a substitute for `V$PROCESS` when counting processes.

### 7.4. Session Server Mode

```sql
SELECT
    server,
    status,
    COUNT(*) AS session_count
FROM v$session
WHERE type = 'USER'
GROUP BY server, status
ORDER BY server, status;
```

`SERVER` reflects `DEDICATED`, `SHARED`, or `PSEUDO` depending on mode and release. Use it to verify how sessions are being served.

### 7.5. Parallel Execution

Parallel queries/DML spawn PX server processes. Check:
```sql
SELECT
    qcsid,
    qcserial#,
    server_group,
    server_set,
    degree,
    req_degree,
    COUNT(*) AS px_servers
FROM v$px_session
GROUP BY
    qcsid, qcserial#, server_group, server_set,
    degree, req_degree
ORDER BY px_servers DESC;
```

`V$PX_SESSION` maps query coordinators to parallel servers. Parallel workloads can spike process usage sharply without a matching rise in user sessions.

### 7.6. Scheduler Jobs

```sql
SELECT
    owner,
    job_name,
    session_id,
    running_instance,
    elapsed_time,
    cpu_used
FROM dba_scheduler_running_jobs
ORDER BY owner, job_name;
```

Compare concurrent running jobs against scheduler configuration and workload windows. Job queue slaves consume processes; never cancel jobs merely because process counts look high before assessing business impact.

### 7.7. Background vs. Foreground

Background processes are essential to the instance. Never kill processes simply because of an unfamiliar name or high process count. Use the alert log, `V$BGPROCESS`, `V$PROCESS`, and Oracle documentation to confirm a process's role.

### 7.8. Why V$SESSION Does Not Equal V$PROCESS

`V$SESSION` counts sessions; `V$PROCESS` counts Oracle processes. Background processes do not correspond to user sessions; shared server multiplexes many sessions onto fewer processes; parallel execution spawns extra processes. Differences between the two counts are normal and depend on architecture.

## 8. PROCESSES and SESSIONS Parameters

### 8.1. PROCESSES

`PROCESSES` sets the instance's process limit. It must accommodate foreground server processes, background processes, and processes spawned by active workloads/features, plus headroom.
 
`PROCESSES` is a static parameter in common Oracle releases: changing it requires updating the SPFILE/PFILE and restarting the instance to take effect. Verify against the Oracle Database Reference for your release first.

### 8.2. SESSIONS

`SESSIONS` sets the concurrent session limit. By default, Oracle derives it from `PROCESSES`; the commonly documented default formula is:
```text
SESSIONS = (1.5 * PROCESSES) + 22
```

This is a reference default, not a substitute for checking actual settings via `SHOW PARAMETER`/`V$PARAMETER`. Shared server, RAC, release differences, and application requirements can necessitate explicit sizing.

### 8.3. SESSIONS Is Not Just Max Pool Connections

`SESSIONS` must cover both user sessions and other internal sessions/resources Oracle counts toward the limit. Never set `SESSIONS` equal to total max connection pool size without adding DBA, monitoring, scheduler, and headroom capacity.

### 8.4. Checking Effective Settings and SPFILE

```sql
SHOW PARAMETER spfile;

SELECT
    name,
    value,
    issys_modifiable,
    isdefault
FROM v$parameter
WHERE name IN ('processes', 'sessions');
```

`V$PARAMETER` shows effective values in the current instance. `V$SPPARAMETER` shows settings persisted in the SPFILE when booted from an SPFILE.

### 8.5. Checking SPFILE Configuration

```sql
SELECT
    sid,
    name,
    value,
    isspecified
FROM v$spparameter
WHERE name IN ('processes', 'sessions')
ORDER BY sid, name;
```

If the database boots from a PFILE, write changes to that file and restart using the exact file. Always back up SPFILE/PFILE before editing.

### 8.6. Changing PROCESSES

Single-instance example:
```sql
ALTER SYSTEM SET PROCESSES = 800 SCOPE = SPFILE;
```

RAC example configuring across all instances:
```sql
ALTER SYSTEM SET PROCESSES = 800
  SCOPE = SPFILE SID = '*';
```

Numbers are illustrative only. The new `PROCESSES` value takes effect only after restarting the instance. In RAC, plan instance-by-instance rolling restarts appropriately and verify parameter consistency requirements for your release and topology.

### 8.7. Derived SESSIONS

If `SESSIONS` is not explicitly set, Oracle derives a default from `PROCESSES`. After changing `PROCESSES`, inspect the effective `SESSIONS` value. Do not set `SESSIONS` below required concurrency or raise it alone without considering the process limit.

### 8.8. TRANSACTIONS

`TRANSACTIONS` relates to `SESSIONS` and transaction concurrency. When altering `PROCESSES`/`SESSIONS`, check the effective `TRANSACTIONS` value and parameter documentation. Do not scale every parameter identically without understanding requirements and limits.

### 8.9. Restart and Verification

After restarting:
```sql
SHOW PARAMETER processes;
SHOW PARAMETER sessions;

SELECT
    resource_name,
    current_utilization,
    max_utilization,
    limit_value
FROM v$resource_limit
WHERE resource_name IN ('processes', 'sessions', 'transactions');
```

Verify that the instance is `OPEN`, services are registered, listeners route properly, background processes are healthy, applications reconnect, and monitoring reports no errors. Restarts cause downtime or role transitions; follow change control.

### 8.10. Raising Limits Does Not Fix Leaks

If session/process counts climb steadily after every request or deployment, find the leak first. Raising limits only postpones the failure while inflating memory/process pressure and worsening the eventual outage.

## 9. Capacity Planning for Sessions and Processes

### 9.1. Summing Pools System-Wide

Never size a single pool in isolation. Estimate total demand:
```text
Total JDBC connection demand
  = Σ (maximumPoolSize of each pool × maximum replica count)
  + batch/job connections
  + admin/monitoring connections
  + integration/DB link workload
  + operational headroom
```

If each pod runs multiple DataSources, sum every pool. If rolling deployments run old and new pods simultaneously, include the overlap window. Use max autoscaling replicas rather than average replicas.

### 9.2. Dedicated Server Process Budget

Estimate process demand:
```text
PROCESSES demand
  = dedicated foreground server processes
  + background processes
  + parallel execution processes
  + scheduler/job processes
  + database link/feature processes
  + peak operational headroom
```

Do not use `SESSIONS` as a substitute for `PROCESSES`. Calibrate estimates using observed peaks in `V$RESOURCE_LIMIT` and `V$PROCESS`.

### 9.3. Headroom

Reserve headroom for:
- DBAs and emergency logins.
- Monitoring/backups/maintenance.
- Login bursts after restarts or failovers.
- Parallel query/job peaks.
- Scale-outs or rolling deployments.
- New background processes when enabling features.
- Connection retries after network recovery.

Base headroom on measured peaks and projected workload growth rather than picking arbitrary percentages.

### 9.4. Example Pool Budget

Suppose a system runs 6 API pods with max pool 30 each, 2 worker pods with max 12 each, and 1 batch pool with max 20:
```text
API:       6 × 30 = 180
WORKER:    2 × 12 =  24
BATCH:     1 × 20 =  20
-----------------------
Configured client maximum = 224
```

`224` excludes admin, monitoring, background, PX, scheduler, and other applications. It is the configured client upper bound, not necessarily the current active session count.

### 9.5. Rolling Deployments and Autoscaling

If 6 old pods and 6 new pods coexist during a rollout, API pool demand temporarily nearly doubles. Account for autoscaling surge/maxUnavailable settings and pools per pod.
 
### 9.6. Pool Size Should Not Equal Thread Count

An application with hundreds of request threads rarely needs hundreds of DB connections. Optimal database concurrency depends on CPU, I/O, lock contention, and SQL workload. Oversized pools increase context switching, session counts, and contention without improving throughput.
 
### 9.7. Measuring Pool Utilization

Collect:
- Active connections.
- Idle connections.
- Pending/waiting threads.
- Acquisition latency/timeouts.
- Connection creation/validation failures.
- Usage duration and leak detection logs.
- Max pool size and current replica count.
 
Correlate pool metrics with `V$SESSION` via `MODULE`/`SERVICE`/`MACHINE`.
 
### 9.8. Sizing by Actual Concurrency

Determine needed database concurrency via load testing and production telemetry. Adjust pool sizes incrementally while measuring throughput, latency, DB CPU, and wait events. Do not enlarge pools merely to eliminate acquisition timeouts when the root cause is slow SQL or lock waits.
 
## 10. Causes of Abnormal Session/Process Growth

### 10.1. Connection Leaks

An application borrows a connection and fails to close it on all success/error paths. The session stays open and the pool cannot reclaim it. Symptoms include rising active/pending counts, pool utilization failing to return to baseline, and climbing request latency.

### 10.2. Transaction Leaks

A connection is returned or retained while its transaction stays open. The session may appear `INACTIVE` yet hold row locks/undo and extend transaction durations. Check `V$TRANSACTION`, `V$LOCK`, and the application transaction manager.

### 10.3. Oversized Pool Configuration

Each pod has a high max pool size, autoscaling adds replicas, and worker/batch DataSources add more, pushing total sessions beyond capacity. Calculate the sum of max pool sizes across the entire system.

### 10.4. Login Storms

After a restart or failover, many JVMs reopen all connections simultaneously. Without retry jitter and bounded pool warm-up, rapid connection creation can drive processes/sessions to the ceiling.

### 10.5. Code Failing to Return Sessions

Leak-prone patterns:
- Omitting try-with-resources.
- Exceptions thrown before `Connection.close()`.
- Long-lived `ResultSet`/`Statement` objects holding connections open.
- Holding connections across HTTP/RPC calls or file I/O.
- Blocked threads retaining open transactions.
- Unterminated async tasks or cancellations without cleanup.
 
### 10.6. Scheduler and Batch Overlaps

Jobs running longer than their schedule interval overlap multiple executions, each opening its own connections. Check running jobs, job queue settings, batch concurrency, and overlap prevention locks.

### 10.7. Parallel Execution

One parallel query can consume many PX servers; concurrent queries create process spikes. Check degree, parallel statement queuing, Resource Manager, and workload windows before raising `PROCESSES`.

### 10.8. Database Links and Integrations

Remote queries/database links, gateways, and integration workloads spawn additional processes/sessions on either the local or remote database. Investigate both sides rather than looking only at the local application pool.

### 10.9. Legitimate Idle Sessions

Connection pools retain idle connections for reuse. A steady, bounded `INACTIVE` count matching configured pool sizes is normal. Leaks typically trend upward uncontrollably, hold transactions, or exceed configured pool bounds.

### 10.10. Profiles and Resource Policies

## 11. RAC and Per-Instance Limits

### 11.1. Resource Limits in RAC

`PROCESSES` and resource limits apply per instance. One node can hit its limit while another still has spare capacity. Client load balancing does not guarantee even session/process distribution, especially with preferred/available service settings or long-lived pooled connections.

### 11.2. Use GV$ Instead of V$

```sql
SELECT
    inst_id,
    resource_name,
    current_utilization,
    max_utilization,
    limit_value
FROM gv$resource_limit
WHERE resource_name IN ('processes', 'sessions')
ORDER BY inst_id, resource_name;
```

### 11.3. Sessions by Instance/Service

```sql
SELECT
    inst_id,
    service_name,
    username,
    machine,
    program,
    status,
    COUNT(*) AS session_count
FROM gv$session
WHERE type = 'USER'
GROUP BY
    inst_id, service_name, username,
    machine, program, status
ORDER BY inst_id, session_count DESC;
```

Identify which services/pools concentrate sessions onto one instance. Compare against load-balancing goals, service configuration, and connection lifetimes.

### 11.4. Processes by Instance

```sql
SELECT
    inst_id,
    COUNT(*) AS process_count
FROM gv$process
GROUP BY inst_id
ORDER BY inst_id;
```

Read process counts alongside `GV$RESOURCE_LIMIT`. Never compare cluster-wide totals against a single-instance limit.

### 11.5. Killing Sessions in RAC

When terminating a session in RAC, specify the exact instance:
```sql
ALTER SYSTEM KILL SESSION 'sid,serial#,@inst_id' IMMEDIATE;
```

`SID` and `SERIAL#` must come from the same snapshot as `INST_ID`. Never copy a bare `SID` and kill it on a different instance.

### 11.6. Service Failover

When an instance fails, services relocate to surviving instances. Mass client reconnects can push surviving nodes past `PROCESSES`/`SESSIONS`. Capacity plans must account for failover peaks when one instance absorbs another's workload.

### 11.7. Rolling Maintenance

During rolling patching/maintenance, session distribution and service placement shift. Verify capacity on every target node before relocating services; avoid funneling all pools onto a node with little headroom.

## 12. CDB/PDB and Session/Process Limits

### 12.1. Instance Level vs. PDB Level

`PROCESSES` is an instance/container-database process resource. A PDB does not have a completely independent OS process pool from the CDB. Sessions across multiple PDBs share instance resources; inspect both CDB totals and per-PDB breakdowns.

### 12.2. Viewing Sessions by Container

```sql
SELECT
    con_id,
    username,
    service_name,
    status,
    COUNT(*) AS session_count
FROM gv$session
WHERE type = 'USER'
GROUP BY con_id, username, service_name, status
ORDER BY con_id, session_count DESC;
```

`CON_ID` identifies the PDB. From CDB root, appropriate privileges are required to view sessions across containers; verify current container and common vs. local users.

### 12.3. CDB Views

`CDB_` views expose cross-PDB metadata when queried from CDB root with appropriate privileges. Never query inside one PDB and assume the results represent the entire CDB.

### 12.4. Resource Manager

CDB Resource Manager allocates and constrains resources across PDBs, consumer groups, and workloads. Use release-supported plans/directives to prevent one PDB or service from monopolizing CPU, parallel servers, or managed session capacity.

Resource Manager does not replace instance `PROCESSES` sizing. Verify directives and session management capabilities for your release; never apply unverified settings.

### 12.5. PDB Services

Applications should connect via services mapped to the right PDB workload. Track sessions by `SERVICE_NAME`/`CON_ID` to see which PDB generates connections. Separating services aids observability and governance, though it does not create separate OS process caps.

### 12.6. PDB Close/Open and Pools

When a PDB closes or relocates, existing connections to that PDB break or become unusable. Pools must evict invalid connections and reconnect once the service is ready. After relocation, verify total sessions/processes on the target instance.

## 13. Handling Incidents Near or At Limits

### 13.1. Confirm Exact Error Details

Collect:
- Full ORA error code and timestamp.
- Service, database, instance, and container.
- Application/pod/client issuing requests.
- Pool acquisition/connection errors.
- Alert log and listener log.
- `V$RESOURCE_LIMIT` current/max/limit.

Do not begin by blindly raising parameters or mass-killing sessions.

### 13.2. Diagnose Which Resource Is Exhausted

Run:
```sql
SELECT
    resource_name,
    current_utilization,
    max_utilization,
    limit_value
FROM v$resource_limit
WHERE resource_name IN ('sessions', 'processes', 'transactions');
```

If `sessions` hit the limit, analyze `V$SESSION` by user/program/status. If `processes` hit the limit, analyze `V$PROCESS`, background, PX, and scheduler processes. Both may be near their ceilings simultaneously.

### 13.3. Identify Top Consumers

```sql
SELECT
    username,
    machine,
    program,
    module,
    service_name,
    COUNT(*) AS total_sessions,
    SUM(CASE WHEN status = 'ACTIVE' THEN 1 ELSE 0 END) AS active_sessions,
    SUM(CASE WHEN status = 'INACTIVE' THEN 1 ELSE 0 END) AS inactive_sessions
FROM v$session
WHERE type = 'USER'
GROUP BY username, machine, program, module, service_name
ORDER BY total_sessions DESC;
```

Look for abnormal spikes, while verifying whether clients populate `MACHINE`/`PROGRAM`/`MODULE` accurately.

### 13.4. Identify Blockers / Long Transactions

```sql
SELECT
    s.sid,
    s.serial#,
    s.username,
    s.status,
    s.machine,
    s.module,
    s.event,
    s.blocking_session,
    s.last_call_et,
    t.start_time,
    t.used_ublk,
    t.used_urec
FROM v$session s
LEFT JOIN v$transaction t
  ON t.ses_addr = s.saddr
WHERE s.type = 'USER'
ORDER BY t.start_time NULLS LAST, s.last_call_et DESC;
```

A session holding a long transaction ties up both locks and connection pool slots. Investigate the application request/thread before terminating the session.

### 13.5. Prioritize Service Recovery

When new connections cannot open:
1. Keep an existing DBA session open if one is connected.
2. Identify the instance and resource at its limit.
3. Pause scale-outs, retry storms, or non-essential batch jobs.
4. Throttle connection creation rates on applications.
5. Identify idle/leaked sessions or stuck transactions.
6. Terminate only verified sessions whose owners and rollback impact are understood.
7. Confirm resource utilization drops and new connections succeed.
8. Plan pool/capacity fixes once service stabilizes.

### 13.6. When DBAs Cannot Log In

Depending on setup, local administrative connections, OS authentication, or reserved administrative access may work. However, if the process limit is exhausted, spawning a new server process can still fail. Never assume `SYSDBA` always gets an unlimited bypass slot.

Prepare emergency access/runbooks ahead of time, alert before hitting limits, and understand supported access paths in your environment. Never kill Oracle OS processes directly to free a slot unless guided by Oracle Support or a verified runbook.

### 13.7. Check Listener and Services

The listener may stay up while the database cannot spawn sessions/processes. Inspect listener status/logs and database service registration; distinguish listener errors, unknown service errors, and network timeouts from database ORA-00018/ORA-00020 errors.

### 13.8. Do Not Use OS Kill on Processes

Never use `kill`/`taskkill` to terminate server or background processes in normal incidents. OS kills cause complex cleanup/recovery or crash the instance. Use SQL/Oracle-supported administrative commands to end sessions; if a process hangs, follow Oracle escalation/runbooks.

## 14. Terminating Sessions Safely

### 14.1. Identify the Exact Session

Before terminating, capture `SID`, `SERIAL#`, `USERNAME`, `MACHINE`, `PROGRAM`, `MODULE`, `SERVICE_NAME`, `SQL_ID`, `STATUS`, `LOGON_TIME`, `LAST_CALL_ET`, transaction details, and blockers. In RAC, capture `INST_ID` as well.

### 14.2. KILL SESSION

Single-instance example:
```sql
ALTER SYSTEM KILL SESSION '123,4567' IMMEDIATE;
```

RAC example:
```sql
ALTER SYSTEM KILL SESSION '123,4567,@2' IMMEDIATE;
```

Values are illustrative only. This requires `ALTER SYSTEM` privilege and must target the exact session. `IMMEDIATE` instructs Oracle to terminate the session; transaction rollback/cleanup may continue afterward.

### 14.3. DISCONNECT SESSION

Oracle also supports:
```sql
ALTER SYSTEM DISCONNECT SESSION '123,4567' IMMEDIATE;
```

`DISCONNECT SESSION` behaves differently from `KILL SESSION` depending on server mode and options. Consult the Oracle SQL Language Reference before choosing `POST_TRANSACTION`/`IMMEDIATE`.

### 14.4. KILLED Status

After `KILL SESSION`, `V$SESSION` may display `KILLED` for some time while Oracle completes cleanup. The session row does not necessarily vanish immediately. Monitor resource counts, transaction rollback, and the alert log; do not issue repeated kills in a loop.

### 14.5. Selecting Sessions to Terminate

Terminate only when:
- The owner/application is identified.
- Held transactions and rollback impact are known.
- It is not a background/internal session.
- There is evidence of an idle leak or non-essential workload.
- Notification/approval follows your organization's incident process.

### 14.6. Never Kill Based Solely on STATUS=INACTIVE

`INACTIVE` can represent legitimate idle pool connections, sessions awaiting client work, or sessions holding open transactions. Inspect `V$TRANSACTION`, locks, module, pool configuration, and last activity before terminating.

### 14.7. Post-Termination Verification

Verify:
- The session ended or cleanup is progressing.
- Transactions/locks are released.
- The pool detects the killed connection and evicts it.
- Applications do not trigger a retry storm.
- Resource counts drop.
- Business operations are reconciled if clients lost responses.

## 15. Connection Pools and Preventing Session Leaks

### 15.1. Use try-with-resources

```java
String sql = "SELECT status FROM orders WHERE order_id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, orderId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            return rs.getString(1);
        }
    }
}
```

Closing the logical connection returns it to the pool. Closing `Statement`/`ResultSet` releases cursors/resources.

### 15.2. Transaction Cleanup

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        updateOrder(connection);
        insertAudit(connection);
        connection.commit();
    } catch (SQLException | RuntimeException e) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            e.addSuppressed(rollbackError);
        }
        throw e;
    }
}
```

With framework transaction managers, let the framework manage commit/rollback. Never mix manual transaction boundaries with `@Transactional` without understanding propagation and connection binding.

### 15.3. Never Hold Connections Across External Service Calls

Avoid doing the following inside a database transaction/connection whenever possible:
- Calling slow HTTP/REST services.
- Sending emails or calling message brokers.
- Waiting on user input.
- Reading large files or network streams.
- Sleeping or waiting on application-level locks.

Prepare data before starting transactions, keep transactions short, and write to an outbox for post-commit side effects.

### 15.4. Budget Maximum Pool Sizes Globally

Sum max pool sizes across all DataSources × maximum replica counts. Subtract headroom for admin, monitoring, scheduler, and other workloads. Never size max pools mechanically based on app-node CPU count or HTTP thread count.

### 15.5. Pool Acquisition Timeouts

Pool acquisition timeouts bound how long the application waits for a pooled connection; they do not directly reduce session counts. When a pool is exhausted, timeouts let requests fail fast rather than spawning unbounded connections. Investigate why connections are held so long before enlarging the pool.

### 15.6. Idle Timeouts and Max Lifetimes

Pools close idle or expired connections to reclaim resources and recycle stale connections. Pick values aligned with firewall, NAT, and DB idle policies. When a pool closes a physical connection, the Oracle session is freed once disconnect/cleanup completes.

### 15.7. Leak Detection

Some pools support leak detection thresholds or logging connection borrow stack traces. Enable carefully in staging/production per policy; thresholds set too low cause false positives on legitimate long queries. Use stack traces to pinpoint unclosed code paths.

### 15.8. Reset Connection State

Before returning a connection to a pool, transactions must finish and session state must be reset per pool/framework behavior. `AutoCommit`, isolation, schema, NLS, timezone, client identifier, and module/action can leak into subsequent requests.

### 15.9. Never Create Pools Per Request

DataSources/pools must be created and managed at the application lifecycle level, never instantiated per request. Many tiny pools with high aggregate max sizes still exhaust sessions and processes.

### 15.10. Isolate Pools by Service

Separate pools for API, batch, and reporting if isolation is needed, while summing total capacity across all of them. Use services, consumer groups, and Resource Manager to govern workloads; never let a batch pool consume the entire connection budget.

## 16. Login Storms and Retry Storms

### 16.1. Login Storms

A login storm happens when many clients open new connections simultaneously within a short window, typically after database restarts, network recoveries, deployments, or failovers. This spikes processes, sessions, and CPU spent on authentication/logon.

### 16.2. Exponential Backoff and Jitter

Retry connections using bounded exponential backoff plus randomized jitter. If every pod retries every 1 second in lockstep, they hammer the listener and database the moment service recovers.

### 16.3. Circuit Breakers

When connection failures exceed a threshold, a circuit breaker pauses new connection/request attempts, waits through a cooldown, and probes gently before reopening. It mitigates retry storms, provided timeouts and fallbacks are configured appropriately.

### 16.4. Pool Warm-Up

Do not necessarily open the entire `maximumPoolSize` immediately at application startup. Ramp up connection creation, bound initialization concurrency, and stagger pod restarts/deployments when full simultaneous rollout is unnecessary.

### 16.5. Connection Lifetime Jitter

If all connections open together at pod startup with identical `maxLifetime`, they expire simultaneously and trigger a reconnect spike. Some pools include lifetime attenuation/jitter; verify implementation and settings.

### 16.6. After RAC / Data Guard Failover

Many pools simultaneously discard stale connections and open new ones to the relocated service/instance. Ensure services are ready before opening reconnect floods, use jittered retries, and test Application Continuity behavior.

### 16.7. Autoscaling

Scaling out application pods multiplies pools. Capacity controllers must factor in database headroom; CPU-based app autoscaling without connection limits can overwhelm the database. Use admission control or cap DB-bound concurrency in the application.

### 16.8. Never Retry ORA-00018/ORA-00020 Infinitely

Once the database reports resource exhaustion, opening connections endlessly solves nothing. Pause or throttle connection attempts until resources free up or capacity is restored. Retries must always be bounded and guarded by circuit breakers.
## 17. OS Resources and Oracle Process Capacity

### 17.1. PROCESSES Is Not the Only Limit

Even when `PROCESSES` still has headroom, the OS enforces process/task limits, memory limits, file descriptor limits, and user resource caps. Oracle processes need OS resources to run; if the OS refuses to fork a process or allocate memory, failures occur before `PROCESSES` hits its cap.

### 17.2. Linux Process/User Limits

On Linux, DBAs and OS admins can inspect user and service limits:
```bash
ulimit -u
ulimit -n
cat /proc/<oracle_pid>/limits
ps -u oracle -o pid,ppid,stat,comm | wc -l
```

These commands are Linux examples; substitute the right `oracle_pid` for the instance process. Also check `systemd` `TasksMax`, cgroup `pids.max`, PAM limits, and OS policies. A DBA's interactive shell `ulimit` is not necessarily the limit applied to the running Oracle service.

### 17.3. Windows

On Windows, process/thread/resource limits and Oracle service accounts differ from Linux. Use Windows performance counters, Task Manager/Process Explorer, and platform-specific Oracle documentation. Never apply Linux `ulimit` assumptions to Windows.

### 17.4. Memory

Each process carries its own memory footprint, including process stacks and private allocations. Increasing `PROCESSES` raises potential memory and OS resource demand. Evaluate PGA, SGA, OS RAM, huge pages, and peak workloads before raising the limit.

### 17.5. File Descriptors and Networking

Each server/client connection consumes sockets, file descriptors, and OS resources. Inspect descriptor limits, ephemeral port ranges, firewall/NAT state tables, and network backlogs during connection spikes. Do not attribute every connection failure to ORA-00018/ORA-00020.

### 17.6. Cross-Checking Oracle and the OS

If `V$RESOURCE_LIMIT` shows process headroom yet the OS cannot spawn processes, investigate OS limits, memory, process tables, and Oracle alert/trace logs. Conversely, if the OS has plenty of headroom while `PROCESSES` is maxed out, address Oracle parameters or workload demand.

## 18. Listener and Related Connection Errors

### 18.1. ORA-00018/ORA-00020 vs. TNS Listener Errors

ORA-00018/ORA-00020 are returned by the database when session/process resources are exhausted. Listener errors occur before the database creates a session or when the listener cannot locate an available handler. Always read the complete error stack.

### 18.2. ORA-12516

The listener could not find an available handler with a matching protocol stack at request time. It can involve handler/service state or connection acceptance capacity. Check listener services, registered handlers, database resource limits, and the alert log.

### 18.3. ORA-12519

The listener found no appropriate service handler for the request type. Check service registration, handler state, dedicated/shared server config, and resource capacity. Do not assume this is always `PROCESSES`.

### 18.4. ORA-12520

The listener could not find an available handler for the requested server type. Check listener status, dynamic registration, service configuration, dedicated/shared server handlers, and instance resource limits.

### 18.5. ORA-12514

The listener does not know the requested service. This is typically a `SERVICE_NAME`, registration, or registration-timing issue rather than a session/process limit. Check `lsnrctl services`, `LOCAL_LISTENER`/`REMOTE_LISTENER`, and service startup.

### 18.6. TNS-12518

The listener failed to hand off a client connection. This can relate to server process creation failures or OS resource exhaustion; check both the listener log and database alert log for root cause.

### 18.7. Differentiation Workflow

- Listener rejects or does not know the service: check network, listener, service name, and registration.
- Listener receives requests but handlers lack capacity: check handlers, shared/dedicated config, and process/session limits.
- Database returns ORA-00018/ORA-00020: focus on `V$RESOURCE_LIMIT` and session/process composition.
- Client times out before response: check timeout layers and server-side outcome.

## 19. Monitoring and Alerting

### 19.1. Resource Limit Snapshots

Persist periodically:
```sql
SELECT
    SYSTIMESTAMP AS sample_time,
    resource_name,
    current_utilization,
    max_utilization,
    initial_allocation,
    limit_value
FROM v$resource_limit
WHERE resource_name IN ('processes', 'sessions', 'transactions');
```

Store samples in a monitoring repository to track hourly/daily peaks and capacity trends.

### 19.2. Calculating Utilization Percentages

`LIMIT_VALUE` is typically returned as text; validate before converting to numeric:
```sql
SELECT
    resource_name,
    current_utilization,
    max_utilization,
    limit_value,
    CASE
      WHEN REGEXP_LIKE(limit_value, '^[0-9]+$')
      THEN ROUND(
        current_utilization / TO_NUMBER(limit_value) * 100,
        1
      )
    END AS current_pct
FROM v$resource_limit
WHERE resource_name IN ('processes', 'sessions');
```

If `limit_value` is not a finite number, the percentage returns `NULL`. Set thresholds according to service SLAs and headroom rather than one generic threshold.

### 19.3. Multi-Tier Alerting

Illustrative model:
| Severity | Condition | Action |
| --- | --- | --- |
| Notice | Current utilization rising faster than baseline | Monitor trend |
| Warning | Current or peak exceeds configured capacity threshold | Identify source of session/process growth |
| Critical | Near limit and connection failures begin appearing | Trigger incident runbook |
| Recovery | Utilization drops steadily and new connections succeed | Verify backlog/request recovery |

Specific percentage thresholds must reflect instance size, peak workloads, and required background/admin headroom. Never wait until 100% to alert.

### 19.4. Rate-of-Change Alerts

A resource at 70% climbing 1% per hour differs sharply from one jumping 20% in one minute. Track slope, rate of change, peaks, and connection failures to catch login storms and leaks early.

### 19.5. Session Source Dashboard

Break down session counts by:
- Instance and container.
- Service and username.
- Machine/program/module.
- Active/inactive.
- Dedicated/shared.
- With/without open transaction.
- Application pool name/replica.

### 19.6. Process Source Dashboard

Display process counts by instance, foreground/background, `program`/`pname`, and parallel execution. Correlate with scheduler jobs, PX activity, and `V$RESOURCE_LIMIT`.

### 19.7. Alert Log

Monitor the alert log for ORA-00018, ORA-00020, process creation errors, listener handoff errors, and background process failures. Keep timestamps synchronized with application logs and monitoring systems.

### 19.8. Monitoring Must Not Cause Incidents

Monitoring agents open sessions too. Cap exporter/agent connections, reuse connections, and avoid polling too aggressively with heavy queries. Include monitoring sessions in your capacity budget.

## 20. Procedure for Handling ORA-00018

### 20.1. Immediate Triage

1. Confirm ORA-00018 and database/instance/container/service.
2. Check `V$RESOURCE_LIMIT` sessions current/max/limit.
3. Inspect `V$SESSION` by username, machine, program, module, and status.
4. Identify the pool/service creating high session counts.
5. Check for sessions holding open transactions or locks.
6. Throttle sources opening new connections if counts are surging.

### 20.2. Freeing Slots

If abandoned sessions or non-essential workloads exist, work with owners to close logical connections in the app or terminate verified sessions. Prioritize pausing bursty batches/jobs and throttling pool acquisitions/reconnects. Never mass-kill inactive sessions.

### 20.3. Verifying Recovery

After cleanup, re-check `V$RESOURCE_LIMIT`, test a fresh connection from the affected application, and verify pool metrics return to normal. Check transaction rollbacks and impacted business operations.

### 20.4. Root Cause

Compare session counts per pool/replica against configured maximums; check leak detection, rolling deployments, retry storms, scheduler overlaps, and session profiles. If legitimate concurrency grew, plan a capacity change rather than periodically killing sessions.

## 21. Procedure for Handling ORA-00020

### 21.1. Immediate Triage

1. Confirm ORA-00020 and the instance.
2. Check `V$RESOURCE_LIMIT` processes.
3. Count `V$PROCESS` and separate background vs. foreground.
4. Inspect session-to-process mappings.
5. Check PX servers, scheduler jobs, and database links.
6. Inspect alert/listener logs and OS resource metrics.

### 21.2. Reducing Process Demand

Pause non-essential jobs/batches or cap parallel workloads if they drive process spikes, with owner confirmation. Throttle pool creation and retry storms. Never terminate background processes.

### 21.3. Releasing Session Processes

If processes map to abnormal application sessions, verify the sessions and terminate them via SQL if needed. For orphan processes without sessions or background processes, follow Oracle diagnostics; never kill OS PIDs routinely.

### 21.4. Assessing OS Capacity

Check OS process/task limits, memory, and service managers. If Oracle `PROCESSES` has headroom while the OS refuses to spawn processes, raising `PROCESSES` will not fix the root cause.

### 21.5. Increasing PROCESSES with Evidence

If legitimate workload exceeds designed capacity, recalculate foreground/background/PX/job demand, headroom, memory, and OS limits. Update the parameter in SPFILE and schedule a restart; do not expect immediate effect without restart.

## 22. Lab: Observing Sessions and Processes

Run only on a dedicated lab database with proper permissions and capacity. Never intentionally hit limits on production or shared development instances.

### 22.1. Baseline

Run:
```sql
SELECT resource_name, current_utilization, max_utilization, limit_value
FROM v$resource_limit
WHERE resource_name IN ('sessions', 'processes');

SELECT type, status, COUNT(*)
FROM v$session
GROUP BY type, status;

SELECT COUNT(*) AS process_count FROM v$process;
```

Record the baseline and sample timestamp.

### 22.2. Open a Session and Keep It Connected

From SQL*Plus or a Java test client, open one connection, run a small query, and leave it open. Observe `V$SESSION` before/after. In dedicated server mode, inspect the matching process in `V$PROCESS`.

### 22.3. Open a Bounded Number of Connections

Java harness:
```java
List<Connection> held = new ArrayList<>();
try {
    for (int i = 0; i < connectionCount; i++) {
        held.add(dataSource.getConnection());
    }
    // Hold connections so the DBA can observe V$SESSION/V$PROCESS.
    new CountDownLatch(1).await();
} finally {
    for (Connection connection : held) {
        try {
            connection.close();
        } catch (SQLException ignored) {
            // log in a real test harness
        }
    }
}
```

Keep `connectionCount` small, configured for the lab, with cleanup in `finally`. Never run infinite loops or connection storms on shared environments.

### 22.4. Observe Inactive Sessions

Hold connections open without executing SQL. Observe `STATUS=INACTIVE` and verify sessions still occupy slots. Close connections, wait for pool/server cleanup, and verify counts drop.

### 22.5. Observe Open Transactions

In the lab, start a transaction, update a row, and leave it uncommitted. Observe `INACTIVE`/`ACTIVE` session state and `V$TRANSACTION`. Roll back and confirm locks/transactions are released.

### 22.6. Compare Dedicated and Shared Server

If the lab configures both modes, connect via dedicated and shared services. Compare session counts, process counts, server mode, and throughput. Never alter production services for lab exercises.

## 23. Lab: Reproducing Limits on a Dedicated Instance

### 23.1. Prepare the Instance

Use a disposable Oracle instance with small `PROCESSES`/`SESSIONS` configured for the lab. Plan startup/shutdown and verify DBA access. Never lower parameters on a shared instance.

### 23.2. Test ORA-00018

Open multiple client connections and hold them until the lab session limit is hit. Record the error code, `V$RESOURCE_LIMIT`, `V$SESSION`, and pool behavior. Stop creating connections immediately once the error appears.

### 23.3. Test ORA-00020

In a dedicated server lab, set a deliberately low process budget accounting for background processes. Slowly open connections and watch `V$PROCESS`/`V$RESOURCE_LIMIT` until process creation fails. Do not assume ORA-00020 always triggers before ORA-00018; whichever triggers first depends on configuration.

### 23.4. Cleanup

Close all client connections, roll back lab transactions, and confirm session/process counts drop. If the instance needs a restart to restore parameters or test state, follow the lab runbook.

### 23.5. Record Evidence

Save:
- Database/instance/version.
- `PROCESSES`/`SESSIONS`.
- Server mode.
- Number of connections opened.
- Resource limits before/during/after the test.
- ORA error code and exception chain.
- Pool behavior and cleanup duration.

## 24. Operations and Capacity Review Checklists

### 24.1. Before Deploying an Application

- [ ] Total pool max size is calculated across maximum replicas.
- [ ] Rolling deployment and autoscaling surges are accounted for.
- [ ] Headroom is reserved for DBAs, monitoring, schedulers, and background tasks.
- [ ] Pools configure acquisition timeouts and bounded connection creation.
- [ ] Connections, statements, and result sets close properly in all lifecycles.
- [ ] Transaction cleanup executes on exceptions and cancellations.
- [ ] Retries use backoff/jitter and never retry ORA-00018/ORA-00020 endlessly.
- [ ] Module/action/client identifiers are set for observability.

### 24.2. Reviewing Database Capacity

- [ ] Effective `PROCESSES`/`SESSIONS` settings are recorded.
- [ ] `V$RESOURCE_LIMIT` current/max metrics are tracked over time.
- [ ] Peak sessions/processes per instance are measured.
- [ ] PX/job/background process demand is accounted for.
- [ ] OS process/task/memory limits have headroom.
- [ ] RAC failover capacity is sized for surviving instances.
- [ ] PDB/service distribution is monitored.
- [ ] Emergency access/runbooks are in place.

### 24.3. During ORA-00018/ORA-00020 Incidents

- [ ] Identified the exact resource and instance.
- [ ] Collected alert/listener/application logs.
- [ ] Identified top session/process sources.
- [ ] Checked for pool leaks, open transactions, and retry storms.
- [ ] Terminated only verified sessions.
- [ ] Avoided arbitrarily OS-killing Oracle background/server processes.
- [ ] Confirmed resource counts dropped and connections recovered.
- [ ] Documented root cause and action items.

### 24.4. After Parameter Changes

- [ ] Backed up SPFILE/PFILE.
- [ ] Assessed memory and OS capacity.
- [ ] Prepared maintenance/change plan and rollback.
- [ ] Restarted the appropriate instances/topology.
- [ ] Confirmed `PROCESSES`/`SESSIONS` took effect.
- [ ] Verified listener/service registration and connection pools.
- [ ] Monitored peak utilization post-deployment.

## 25. Self-Check Questions

1. How does a session differ from a process?
2. How does a client process differ from an Oracle server process?
3. Why does an `INACTIVE` session still consume a session slot?
4. How does dedicated server relate sessions and processes?
5. How does shared server change the session-to-process relationship?
6. Which resource has reached its limit on ORA-00018?
7. Which resource has reached its limit on ORA-00020?
8. Why does the `V$SESSION` count not equal the `V$PROCESS` count?
9. How do `current_utilization` and `max_utilization` in `V$RESOURCE_LIMIT` differ?
10. Why must you check `GV$RESOURCE_LIMIT` in RAC?
11. Does changing `PROCESSES` require a restart?
12. How is `SESSIONS` derived from `PROCESSES` by default?
13. Why should `SESSIONS` not be set equal to total max pool size?
14. How can parallel execution increase process counts?
15. How can scheduler jobs affect the process limit?
16. How do you detect an `INACTIVE` session holding an open transaction?
17. Why should you not kill every `INACTIVE` session?
18. When does ORA-02391 differ from ORA-00018?
19. How do ORA-12516/12519/12520 differ from ORA-00020?
20. Which replica count should be used when sizing pool max capacity?
21. Why can rolling deployments temporarily spike session peaks?
22. How do you mitigate login storms after failover?
23. When should `PROCESSES` be increased?
24. Why must OS process/memory limits be checked too?
25. What extra identifier is required when terminating a session in RAC?
26. Does a PDB have an independent OS process pool from the CDB?
27. Why can increasing pool size make the database slower?
28. When should shared server or DRCP be considered?
29. Why should you not routinely OS-kill Oracle processes for cleanup?
30. What lab demonstrates application connection cleanup after exceptions?

## 26. Mental Model Summary

```text
APPLICATION / CONNECTION POOLS
       |
       +-- Pool max × replica count
       +-- Batch / monitoring / admin
       +-- Retry / reconnect burst
       |
       v
ORACLE DATABASE INSTANCE
       |
       +-- SESSIONS
       |      ORA-00018
       |      V$SESSION / V$RESOURCE_LIMIT
       |
       +-- PROCESSES
       |      ORA-00020
       |      V$PROCESS / V$RESOURCE_LIMIT
       |
       +-- Background / PX / Scheduler / DB links
       |
       v
CAPACITY AND DIAGNOSTICS
       |
       +-- V$ / GV$ per instance
       +-- Session source and transaction state
       +-- OS process / memory limits
       +-- Listener and service state
       |
       v
REMEDIATION
       |
       +-- Stop connection storm
       +-- Fix pool/leak/transaction
       +-- Safely end confirmed sessions
       +-- Increase PROCESSES with restart plan
       +-- Verify recovery and headroom
```

**Key takeaways:** ORA-00018 is the session limit; ORA-00020 is the Oracle process limit. `V$RESOURCE_LIMIT` shows live usage and high-water marks; `V$SESSION` shows who is logged in, and `V$PROCESS` shows instance processes. Sum pools across all replicas and workloads, preserve headroom, fix leaks and retry storms before raising parameters, and terminate sessions only after understanding open transactions and impact.
