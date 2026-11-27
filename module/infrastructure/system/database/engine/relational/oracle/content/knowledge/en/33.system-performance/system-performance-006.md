# Diagnosing with Dynamic Views, Tracing, or Statspack Within Authorized Scope

When Oracle Database slows down, you need to determine which session, which SQL statement, which wait type, and which time window are involved. Oracle provides several diagnostic sources: dynamic performance views (V$ and GV$), SQL Trace/TKPROF, and Statspack. Each tool answers a different set of questions.

- **Dynamic views** show current state or cumulative counters at the instance/session level.
- **SQL Trace** records parse, execute, fetch, and wait activity for a selected workload; TKPROF makes the trace readable.
- **Statspack** stores statistical snapshots to compare load between two points in time.

Sound diagnosis requires limiting scope to authorized privileges, collecting over a representative time window, and protecting sensitive data. Not every Oracle view or diagnostic feature is permitted under every license agreement. Specifically, AWR, ASH, and ADDM fall under the Oracle Diagnostics Pack; SQL Tuning Advisor and Real-Time SQL Monitoring fall under the Oracle Tuning Pack per applicable product terms. Confirm usage rights against your contract and licensing documentation for your deployed version before accessing or running those features.

## 1. Start from the Diagnostic Question

Do not open dozens of views and read every number blindly. Define the symptom and the specific question to answer:

| Symptom | First Question |
|---|---|
| One slow request | Which session executes the request? What is the SQL_ID? |
| Many slow requests concurrently | Is there a CPU, I/O, lock, network, or Resource Manager bottleneck? |
| One unusually slow SQL | Which execution plan and bind values are running? |
| Hung transaction | Which session is blocking? Is an open transaction holding locks long-term? |
| Slow during a specific time window | How do load and wait profile in that window differ from normal? |
| Rapid TEMP growth | Which SQL uses large sort/hash workareas? |
| High CPU | Which sessions/SQL consume CPU, and over what interval? |
| Database just changed plan | Was there a stats refresh, deployment, different bind, or new child cursor? |

A practical diagnostic workflow:

1. Record the timestamp, service, module/action, and blast radius.
2. Identify active sessions and SQL using dynamic views.
3. Inspect waits, blocking, and resource counters.
4. Retrieve execution plans and runtime statistics if privileges permit.
5. If per-call detail is needed, enable SQL Trace with clear scope and duration.
6. If comparing load across intervals is needed, use Statspack or licensed tools.
7. Correlate findings with application, data, and configuration changes.

## 2. What Are Dynamic Performance Views?

Oracle provides dynamic performance views to inspect operational details of the instance, sessions, SQL, locks, memory, and other components. View names typically begin with V$.

Examples:

- V$SESSION: connected sessions.
- V$SQL: SQL cursors in the shared pool.
- V$SQLSTATS: aggregated SQL statistics.
- V$SESSION_WAIT: session wait information in releases providing this view; many wait fields are now available directly in V$SESSION.
- V$SYSTEM_EVENT: aggregated wait time by event.
- V$SYSSTAT: cumulative system statistics.
- V$SESSTAT: session statistics.
- V$LOCK: lock information.
- V$TRANSACTION: active transactions.
- V$TEMPSEG_USAGE: temporary segment usage.
- V$PGASTAT: PGA statistics.
- V$SQL_WORKAREA_ACTIVE: currently active workareas.
- V$DIAG_INFO: diagnostic repository paths and metadata.

These views reflect in-memory structures and runtime activity. They are not regular business tables and must never be modified directly.

### 2.1 V$ and GV$

In a single-instance environment, V$ is normally the starting point to view current instance state.

In Oracle RAC:

- V$ typically displays information for the instance to which your session is connected.
- GV$ provides global data across instances, adding the INST_ID column.

Example:

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       status,
       sql_id
FROM gv$session
WHERE username IS NOT NULL
ORDER BY inst_id, sid;
~~~

In RAC, preserve INST_ID when correlating sessions, SQL, waits, and locks to avoid confusing SIDs across instances.

### 2.2 Dynamic Views Are Not Historical Snapshots

V$SESSION reflects near-current state. A session can terminate before you run your next query.

V$SYSSTAT and V$SYSTEM_EVENT generally hold cumulative counters since instance startup or their respective reset points. A large number does not tell you how fast it grew over the past 5 minutes.

To analyze a time interval, you need to:

- Capture two readings at two timestamps.
- Compute counter deltas.
- Record startup time and instance.
- Compare matching durations and workloads.

## 3. Access Privileges and the Principle of Least Privilege

Dynamic performance views are typically accessed via V$ synonyms pointing to internal fixed views, e.g., V$SESSION maps to V_$SESSION.

A standard application account may not have SELECT privileges on these views. A DBA can grant minimal read access on specific required views:

~~~sql
GRANT SELECT ON SYS.V_$SESSION TO diag_reader;
GRANT SELECT ON SYS.V_$SQL TO diag_reader;
GRANT SELECT ON SYS.V_$SQL_PLAN TO diag_reader;
GRANT SELECT ON SYS.V_$SYSTEM_EVENT TO diag_reader;
GRANT SELECT ON SYS.V_$SYSSTAT TO diag_reader;
~~~

Exact object names and required grants must be verified by the DBA in the target environment. The example above illustrates a restricted read-privilege model.

### 3.1 Do Not Grant Overly Broad Privileges Just for Diagnosis

Do not grant by default:

- DBA.
- SYSDBA.
- SELECT ANY DICTIONARY.
- Full access to all diagnostic data for an application account.

Instead, create a dedicated role such as DIAG_READER, grant only needed views, restrict membership, and audit usage.

`SELECT_CATALOG_ROLE` grants access to many dictionary/performance views, which is often broader than an application requires. Evaluate direct per-object grants against internal security policy.

### 3.2 Package and Trace Privileges

Enabling trace for the current session, another session, or a service/module may require different package privileges. DBAs should execute or grant scoped package privileges appropriately:

- Current session: `DBMS_SESSION` package within authorized sessions.
- Another session: `DBMS_MONITOR` with exact SID/SERIAL#.
- Service/module/action/client identifier: `DBMS_MONITOR` with exact filters.

Do not grant system-wide tracing privileges to application users unless necessary.

## 4. Identifying Active Sessions with V$SESSION

V$SESSION is a practical starting point to see who is connected and which SQL is executing.

~~~sql
SELECT sid,
       serial#,
       username,
       status,
       osuser,
       machine,
       program,
       module,
       action,
       client_identifier,
       sql_id,
       sql_child_number,
       prev_sql_id,
       event,
       wait_class,
       state,
       seconds_in_wait,
       blocking_session,
       final_blocking_session
FROM v$session
WHERE username IS NOT NULL
ORDER BY status, sid;
~~~

Key columns:

- SID and SERIAL#: instance-local session identifiers; use both when targeting a session.
- USERNAME: database user.
- STATUS: ACTIVE or INACTIVE along with session state.
- MACHINE/PROGRAM: connecting client/host/program.
- MODULE/ACTION: application tags set via DBMS_APPLICATION_INFO.
- CLIENT_IDENTIFIER: request/user identifier set by the application.
- SQL_ID: current SQL statement.
- PREV_SQL_ID: prior SQL statement in certain states.
- EVENT/WAIT_CLASS/STATE: current wait or most recent wait state.
- BLOCKING_SESSION: directly blocking session if identified.
- FINAL_BLOCKING_SESSION: root blocker in the chain if identified.

### 4.1 ACTIVE Does Not Mean Using CPU

A session with `STATUS = 'ACTIVE'` may be:

- Running on CPU.
- Waiting on I/O.
- Waiting on locks.
- Waiting on network or other resources.

Read STATE, EVENT, and WAIT_CLASS alongside STATUS. An ACTIVE session is not automatically generating heavy CPU load.

### 4.2 Idle Sessions and Idle Waits

INACTIVE sessions are normally not executing SQL. Waits such as `SQL*Net message from client` are idle waits: the database is waiting for the client to send the next command.

Do not conclude the database has a bottleneck merely because an event has a high wait count. Distinguish idle waits from waits affecting execution time.

### 4.3 Tagging MODULE/ACTION in the Application

Applications can set tags so DBAs can filter workloads:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_SERVICE',
        action_name => 'CREATE_ORDER'
    );
END;
/
~~~

Switch action between phases:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_ACTION('VALIDATE');
    -- Validate request.

    DBMS_APPLICATION_INFO.SET_ACTION('INSERT_HEADER');
    -- Insert order header.

    DBMS_APPLICATION_INFO.SET_ACTION('INSERT_ITEMS');
    -- Insert order items.
END;
/
~~~

When a request ends or a connection returns to the pool, the application should reset module/action/client identifier per established convention. Otherwise, reused sessions may retain tags from the previous request.

### 4.4 CLIENT_IDENTIFIER

`DBMS_SESSION.SET_IDENTIFIER` attaches a client identifier:

~~~sql
BEGIN
    DBMS_SESSION.SET_IDENTIFIER('request-7f3a2');
END;
/
~~~

Use only non-sensitive request IDs or internal identifiers. Never put passwords, tokens, card numbers, or personal data into MODULE, ACTION, or CLIENT_IDENTIFIER, as these values appear in diagnostic views and traces.

## 5. Identifying Running SQL with V$SQL

V$SQL contains SQL cursor metadata in the shared pool. A single SQL text may have multiple child cursors, each with its own plan or optimizer environment.

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       parse_calls,
       rows_processed,
       elapsed_time,
       cpu_time,
       buffer_gets,
       disk_reads,
       last_active_time,
       is_bind_sensitive,
       is_bind_aware,
       sql_text
FROM v$sql
WHERE sql_id = :sql_id
ORDER BY child_number;
~~~

`elapsed_time` and `cpu_time` in many dynamic SQL views are measured in microseconds. They are typically cumulative values for the child cursor, not the duration of a single execution.

### 5.1 Computing Averages Only for Screening

You can calculate:

~~~sql
SELECT sql_id,
       child_number,
       executions,
       ROUND(elapsed_time / 1e6, 3) AS elapsed_seconds_total,
       ROUND(cpu_time / 1e6, 3) AS cpu_seconds_total,
       ROUND(elapsed_time / NULLIF(executions, 0) / 1e6, 4)
           AS avg_elapsed_seconds,
       ROUND(buffer_gets / NULLIF(executions, 0), 1)
           AS avg_buffer_gets
FROM v$sql
WHERE sql_id = :sql_id
ORDER BY child_number;
~~~

Averages can hide outliers. A SQL running fast 99 times and very slowly once still shows a benign-looking average. Combine with tracing, application latency, or suitable monitoring tools.

### 5.2 V$SQLSTATS

V$SQLSTATS provides aggregated statistics by SQL_ID and generally offers better retention than relying solely on child cursors in V$SQL, though it is still not a permanent historical archive.

~~~sql
SELECT sql_id,
       plan_hash_value,
       executions,
       ROUND(elapsed_time / 1e6, 3) AS elapsed_seconds,
       ROUND(cpu_time / 1e6, 3) AS cpu_seconds,
       buffer_gets,
       disk_reads,
       rows_processed,
       last_active_time
FROM v$sqlstats
WHERE sql_id = :sql_id;
~~~

Verify column metadata and units for your version. Do not sum figures from V$SQL and V$SQLSTATS as though they were two independent workloads.

### 5.3 SQL_ID Does Not Uniquely Identify a Plan

One SQL_ID can have multiple child cursors and `plan_hash_value`s. During an investigation, record all of:

- SQL_ID.
- CHILD_NUMBER.
- PLAN_HASH_VALUE.
- Bind context if applicable.
- Module/action and execution timestamp.

Recording SQL_ID alone may be insufficient to reproduce the exact problematic plan.

### 5.4 SQL Text May Contain Sensitive Data

`V$SQL.SQL_TEXT`/`SQL_FULLTEXT` can contain literal values embedded in SQL statements. Avoid copying SQL text into public tickets/logs if it exposes personal or confidential business data.

## 6. Inspecting Cursor Execution Plans

Once you have SQL_ID and child number, inspect the plan using DBMS_XPLAN:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        sql_id          => :sql_id,
        cursor_child_no => :child_number,
        format          => 'TYPICAL +PREDICATE +ALIAS'
    )
);
~~~

If runtime statistics were collected, use:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        sql_id          => :sql_id,
        cursor_child_no => :child_number,
        format          => 'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

`ALLSTATS LAST` requires runtime plan statistics to have been gathered, e.g., via `GATHER_PLAN_STATISTICS` or appropriate configuration. Otherwise, A-Rows and runtime columns may not appear.

Read the components:

- Operation: table access, index access, join, sort, hash.
- E-Rows: estimated rows.
- A-Rows: actual rows.
- Starts: number of times the operation started.
- Buffers: logical reads.
- Reads: physical reads.
- Predicate Information: access/filter predicates.
- Alias: query block and row source.

If E-Rows differs from A-Rows by orders of magnitude, inspect statistics, histograms, bind values, and column correlations.

## 7. Reading Wait Events in V$SESSION

A simple query:

~~~sql
SELECT sid,
       serial#,
       username,
       sql_id,
       state,
       wait_class,
       event,
       seconds_in_wait
FROM v$session
WHERE status = 'ACTIVE'
  AND username IS NOT NULL
ORDER BY wait_class, event;
~~~

A wait event describes what the session is waiting on at sampling time or the wait state reported by the view. One sample alone is insufficient to establish root cause.

### 7.1 Common Wait Events

| Wait/event or group | Potential association | Further investigation needed |
|---|---|---|
| db file sequential read | Single-block read, common in index/table lookups | Read count, object, plan, cache, storage latency |
| db file scattered read | Multiblock read, common in full scans | Block count, whether full scan is appropriate, I/O subsystem |
| direct path read/write | Direct read/write, often scan, TEMP, or LOB | SQL, operation, data size, TEMP |
| direct path read temp / write temp | Sort/hash spill to TEMP | Workarea, cardinality, PGA, TEMP I/O |
| log file sync | Session waiting for commit redo confirmation | Commit frequency, redo writes, log file parallel write |
| log file parallel write | LGWR writing redo | Storage latency, redo volume, concurrency |
| enq: TX - row lock contention | Waiting on transaction/row lock | Blocker, lock-holding transaction, application commits |
| enq: TM - contention | Waiting on table enqueue in certain operations | DDL, constraints, table locks, and concurrency |
| library cache lock/pin | Library cache contention in certain operations | Parsing/DDL/invalidations and version |
| latch: shared pool | Shared pool latch contention | Parsing, shared pool pressure, and SQL reuse |
| resmgr:cpu quantum | Resource Manager CPU throttling | Consumer group, plan, and CPU allocation |
| SQL*Net message from client | Usually idle wait for client | Do not treat as a DB bottleneck if session is idle |

An event name is only a signal. For instance, `db file sequential read` does not automatically mean an index is poorly designed; a valid query may legitimately need many single-block reads. Combine wait count, wait time, SQL, object, and plan.

### 7.2 Wait Class

Oracle groups wait events into wait classes such as User I/O, System I/O, Concurrency, Application, Commit, Network, Configuration, and Idle.

Wait classes guide investigation, not conclusions. A single session can alternate between CPU and multiple wait events within one execution.

### 7.3 CPU Does Not Appear as a Normal Wait Event

When a session runs on CPU, V$SESSION may reflect ON CPU in STATE in appropriate contexts or show no current wait. The absence of a large wait event does not prove a query is fast. Check CPU statistics, SQL elapsed/CPU, and deltas of session/system stats.

## 8. Finding Blocking and Blocked Sessions

V$SESSION provides BLOCKING_SESSION, BLOCKING_INSTANCE, FINAL_BLOCKING_SESSION, and FINAL_BLOCKING_INSTANCE in supported releases.

Example:

~~~sql
SELECT sid,
       serial#,
       username,
       sql_id,
       event,
       blocking_session,
       blocking_instance,
       final_blocking_session,
       final_blocking_instance
FROM v$session
WHERE blocking_session IS NOT NULL
   OR final_blocking_session IS NOT NULL;
~~~

In RAC, use GV$SESSION and preserve INST_ID.

### 8.1 Inspecting Locks

~~~sql
SELECT l.sid,
       s.serial#,
       s.username,
       s.sql_id,
       l.type,
       l.id1,
       l.id2,
       l.lmode,
       l.request,
       l.block
FROM v$lock l
LEFT JOIN v$session s
  ON s.sid = l.sid
ORDER BY l.sid, l.type;
~~~

Columns:

- LMODE: lock mode currently held by the session.
- REQUEST: lock mode requested by the session.
- BLOCK: indicator that this lock may be blocking another session in certain cases.
- TYPE/ID1/ID2: resource type and identifiers.

Do not interpret ID1/ID2 as an object ID for every lock type; encoding depends on TYPE.

### 8.2 Inspecting Open Transactions

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.status,
       s.sql_id,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM v$transaction t
JOIN v$session s
  ON s.taddr = t.addr;
~~~

Long-running transactions hold locks and generate undo. Check what the application is processing, whether the transaction legitimately needs to remain open, or if a batch operation failed to commit.

### 8.3 Never Kill a Session Based on a Single Query Row

Before asking a DBA to terminate a session, verify:

- Exact SID, SERIAL#, and INST_ID.
- Whether the session is the blocker or merely waiting.
- Whether the transaction holds critical uncommitted work.
- Whether rollback could be lengthy and induce heavy additional I/O.
- That application owners and incident procedures have been notified.

Terminating a session is an impactful operational action; it must only be performed by authorized personnel following standard procedure.

## 9. Reading System and Session Counters

V$SYSSTAT contains cumulative system statistics. Example:

~~~sql
SELECT name,
       value
FROM v$sysstat
WHERE name IN (
    'DB time',
    'DB CPU',
    'user calls',
    'execute count',
    'parse count (total)',
    'parse count (hard)',
    'session logical reads',
    'physical reads',
    'physical writes',
    'redo size'
)
ORDER BY name;
~~~

Exact statistic names may vary across versions. Query V$STATNAME to confirm which names exist.

### 9.1 Deltas Matter More Than Cumulative Totals

Suppose `physical reads` is currently 10,000,000. That figure does not tell you whether 100 or 1,000,000 reads happened in the last 5 minutes.

Take two samples:

~~~sql
SELECT name, value
FROM v$sysstat
WHERE name IN ('physical reads', 'session logical reads', 'redo size');
~~~

Save results at time T1, run the workload, then query again at T2. Delta:

~~~text
Delta = Value(T2) - Value(T1)
Rate  = Delta / elapsed_seconds
~~~

If the instance restarted between samples or statistics reset, the delta may be invalid. Record startup time and instance alongside each sample.

### 9.2 DB Time and DB CPU

DB time is the total time database foreground sessions spend processing and waiting in database-related work; DB CPU is the CPU portion attributed to foreground database work per Oracle's definition. These metrics are commonly used in workload analysis.

Do not add DB time and DB CPU as two independent components: CPU time is already included inside DB time. The DB CPU/DB time ratio helps indicate whether a workload leans CPU-bound or wait-bound, but must be evaluated over matching windows and session scopes.

### 9.3 Session Statistics

Join V$SESSTAT with V$STATNAME to view counters for a specific session:

~~~sql
SELECT s.sid,
       n.name,
       st.value
FROM v$sesstat st
JOIN v$statname n
  ON n.statistic# = st.statistic#
JOIN v$session s
  ON s.sid = st.sid
WHERE s.sid = :sid
  AND n.name IN (
      'session logical reads',
      'physical reads',
      'physical writes',
      'CPU used by this session',
      'execute count',
      'parse count (total)'
  )
ORDER BY n.name;
~~~

These values also typically accumulate over the session's lifetime. To measure a single operation, capture before-and-after snapshots in the same session and compute the delta.

## 10. System Event Statistics

V$SYSTEM_EVENT aggregates wait counts and wait times by event:

~~~sql
SELECT event,
       wait_class,
       total_waits,
       time_waited_micro,
       average_wait
FROM v$system_event
WHERE wait_class <> 'Idle'
ORDER BY time_waited_micro DESC;
~~~

Columns and units can vary by version; check dictionary metadata. `TIME_WAITED_MICRO` is total wait time in microseconds in views providing this column.

### 10.1 Do Not Sort Only by TOTAL_WAITS

An event with millions of tiny waits may matter less than an event with fewer but much longer waits. Inspect:

- Total wait time.
- Wait count.
- Average wait.
- Delta within the target window.
- Associated sessions/SQL.

### 10.2 Capturing Wait Deltas Across an Interval

Just like V$SYSSTAT, snapshot V$SYSTEM_EVENT at T1 and T2 and compare `TOTAL_WAITS` and `TIME_WAITED_MICRO`. Store results in a dedicated diagnostic table or spool file per operational procedures.

Do not subtract two samples across an instance restart, counter reset, or differing INST_IDs.

## 11. Inspecting TEMP and Workareas

Sorts, hash joins, and other operations spill to TEMP when workarea memory is insufficient.

~~~sql
SELECT username,
       session_addr,
       session_num,
       sql_id,
       tablespace,
       segtype,
       blocks
FROM v$tempseg_usage
ORDER BY blocks DESC;
~~~

View columns can vary across versions. Join SESSION_ADDR to V$SESSION.SADDR to retrieve SID, SERIAL#, and SQL_ID.

### 11.1 Active Workareas

~~~sql
SELECT sid,
       sql_id,
       operation_type,
       operation_id,
       policy,
       actual_mem_used,
       max_mem_used,
       number_passes,
       tempseg_size
FROM v$sql_workarea_active
ORDER BY tempseg_size DESC NULLS LAST;
~~~

Check exact column definitions for your version. This view reflects workareas active at query time; an operation may finish before you sample.

### 11.2 High TEMP Usage Does Not Prove TEMP Space Is Insufficient

TEMP usage can climb due to:

- Hash join spills.
- Large sorts.
- `GROUP BY` or `DISTINCT`.
- Temporary LOBs.
- Other data-processing operations.

Locate the responsible SQL_ID and operation before enlarging TEMP or PGA. Adding TEMP space does not make the operation cheaper; it only prevents out-of-space errors if capacity is truly the limit.

## 12. PGA and Memory Statistics

V$PGASTAT provides aggregated PGA statistics:

~~~sql
SELECT name,
       value,
       unit
FROM v$pgastat
ORDER BY name;
~~~

Notable metrics include:

- `aggregate PGA target parameter`.
- `aggregate PGA auto target`.
- `total PGA allocated`.
- `total PGA inuse`.
- `maximum PGA allocated`.
- `over allocation count`.
- `extra bytes read/written`.

Exact metric names can vary by release. Read them alongside active workareas and running SQL.

PGA is critical for sort/hash workareas. However, do not enlarge PGA simply because a single query spills to TEMP. Consider total concurrency, host memory limits, cardinalities, and row-source sizes.

## 13. What Is SQL Trace?

SQL Trace records SQL activity within a session or selected scope. Tracing can capture:

- Parse.
- Execute.
- Fetch.
- CPU time.
- Elapsed time.
- Disk reads.
- Query/current buffer gets.
- Rows processed.
- Wait events when waits are enabled.
- Bind values when binds are enabled.

Tracing is valuable when dynamic views do not tell the whole story—such as how many times a SQL statement was called, how long each call took, how many rows were fetched, and which events it waited on.

SQL Trace adds overhead. Enable it only on the required scope, for a brief duration, and disable it immediately after collection.

## 14. Tracing the Current Session with DBMS_SESSION

With proper privileges, you can trace your own active session:

~~~sql
ALTER SESSION SET TRACEFILE_IDENTIFIER = 'ORDER_DIAG';

BEGIN
    DBMS_SESSION.SESSION_TRACE_ENABLE(
        waits => TRUE,
        binds => FALSE
    );
END;
/

-- Run the exact workload to investigate here.

BEGIN
    DBMS_SESSION.SESSION_TRACE_DISABLE;
END;
/
~~~

Explanation:

- `TRACEFILE_IDENTIFIER` helps identify the generated trace file.
- `waits => TRUE` records wait details.
- `binds => FALSE` avoids recording sensitive bind values in this example.

If execution is interrupted by an exception or client cancellation, ensure session tracing is disabled. Never leave tracing running beyond the investigation window.

### 14.1 Locating the Trace File

You can inspect the diagnostic trace directory and current file:

~~~sql
SELECT name,
       value
FROM v$diag_info
WHERE name IN (
    'Diag Trace',
    'Default Trace File'
);
~~~

This path is on the database server, not the client's local filesystem. File read permissions belong to the DBA/OS account per server administration policy.

## 15. Tracing Another Session with DBMS_MONITOR

When tracing a live application session, a DBA retrieves SID and SERIAL# from V$SESSION and enables targeted tracing:

~~~sql
BEGIN
    DBMS_MONITOR.SESSION_TRACE_ENABLE(
        session_id => :sid,
        serial_num => :serial_number,
        waits      => TRUE,
        binds      => FALSE
    );
END;
/
~~~

After collection completes:

~~~sql
BEGIN
    DBMS_MONITOR.SESSION_TRACE_DISABLE(
        session_id => :sid,
        serial_num => :serial_number
    );
END;
/
~~~

SID can be reused after session termination; SERIAL# identifies the exact session incarnation. In RAC, identify the right instance and use the version-appropriate API/identifiers.

### 15.1 Tracing by Service, Module, and Action

If the application sets service/module/action via `DBMS_APPLICATION_INFO`, the DBA can trace by that scope instead of a single SID.

Skeleton example:

~~~sql
BEGIN
    DBMS_MONITOR.SERV_MOD_ACT_TRACE_ENABLE(
        service_name => 'APP_SERVICE',
        module_name  => 'ORDER_SERVICE',
        action_name  => 'CREATE_ORDER',
        waits        => TRUE,
        binds        => FALSE
    );
END;
/
~~~

Disable:

~~~sql
BEGIN
    DBMS_MONITOR.SERV_MOD_ACT_TRACE_DISABLE(
        service_name => 'APP_SERVICE',
        module_name  => 'ORDER_SERVICE',
        action_name  => 'CREATE_ORDER'
    );
END;
/
~~~

This traces all sessions matching the filter. If the module/action is too broad or request volume is high, it can produce many trace files and significant overhead. Keep the service/module/action filter precise and the duration short.

### 15.2 Client Identifier Tracing

When applications set `CLIENT_IDENTIFIER`, `DBMS_MONITOR` can trace by client identifier in supported environments:

~~~sql
BEGIN
    DBMS_MONITOR.CLIENT_ID_TRACE_ENABLE(
        client_id => 'request-7f3a2',
        waits     => TRUE,
        binds     => FALSE
    );
END;
/
~~~

Disable via `CLIENT_ID_TRACE_DISABLE` with the same `client_id`. Verify syntax, privileges, and cross-instance tracing behavior in RAC for your release.

## 16. Protecting Bind Values and Data in Traces

Bind tracing can help reveal how input values influence plans, but traces may contain:

- Email addresses, phone numbers, physical addresses.
- Customer or order IDs.
- Financial data.
- Tokens or credentials if the application binds sensitive inputs.
- Confidential business content.

Therefore:

- Default to `binds => FALSE`.
- Enable bind tracing only with explicit approval and clear need.
- Target a single specific session/request.
- Store traces in locations with strict ACLs.
- Never attach raw traces to public tickets.
- Purge or archive per retention policy.
- Redact sensitive data before sharing reports.

Trace files are sensitive diagnostic artifacts, not harmless log files.

## 17. TKPROF: Turning Traces into Readable Reports

TKPROF is a utility that formats trace files into per-SQL statement reports.

Example run from a host/server with Oracle client/tools installed:

~~~text
tkprof input.trc output.prf sys=no
~~~

Where:

- `input.trc`: trace file.
- `output.prf`: output report.
- `sys=no`: omits recursive SQL issued by SYS from the standard report output.

Exact paths and commands depend on your Oracle client/server installation. TKPROF runs in an OS shell, not as a SQL command inside SQL Developer.

### 17.1 Columns in a TKPROF Report

Each SQL statement can display:

- `count`: number of parse/execute/fetch calls.
- `cpu`: CPU time.
- `elapsed`: elapsed time.
- `disk`: physical reads.
- `query`: consistent gets.
- `current`: current-mode gets.
- `rows`: rows processed.

TKPROF separates parse, execute, and fetch. This helps reveal:

- Excessive parsing.
- SQL executed repeatedly row-by-row.
- Long fetches because the client reads slowly or the result set is huge.
- CPU-heavy SQL.
- SQL waiting on I/O or wait events.

### 17.2 Distinguishing Parse, Execute, and Fetch

| Phase | Meaning |
|---|---|
| Parse | Oracle checks syntax, resolves objects, verifies privileges, and optimizes if needed |
| Execute | Executes the statement, potentially reading/writing data |
| Fetch | Returns result rows to the client |

A SELECT can execute once yet fetch many times. If the client fetches slowly, total operation elapsed time can grow even though the database is not continuously consuming CPU.

### 17.3 TKPROF Does Not Replace the Full Actual Execution Plan

TKPROF can display an execution plan if the trace includes the necessary data and options are specified. To view the cursor's plan and runtime statistics in the shared pool, use `DBMS_XPLAN.DISPLAY_CURSOR` while privileges and cursor data remain available.

Tracing and `DISPLAY_CURSOR` complement each other:

- Tracing shows the sequence of calls and waits.
- `DBMS_XPLAN` shows the operation tree and plan statistics.

## 18. Tracing Waits and Interpreting Time

When waits are enabled, traces record wait calls with event name, duration, and associated parameters.

A SQL statement may:

- Use CPU.
- Wait on block reads.
- Wait on redo/commit.
- Wait on locks.
- Wait on TEMP I/O.
- Wait on network or client fetches.

Do not look solely at total elapsed time. Compare CPU and wait time to locate where the bulk of time went.

Example:

| Metric | SQL A | SQL B |
|---|---:|---:|
| Elapsed | 12 s | 12 s |
| CPU | 11 s | 1 s |
| Wait time | 1 s | 11 s |

Both SQL statements have identical elapsed time, yet point in different investigative directions:

- SQL A is likely CPU-bound: plan, row volume, algorithm, parsing, or expressions.
- SQL B is likely wait-bound: I/O, locks, commits, TEMP, or network.

These numbers are illustrative examples, not real measurements.

## 19. What Is Statspack?

Statspack is a toolkit provided by Oracle to capture and store performance statistical snapshots, then generate reports comparing two snapshots.

Statspack is useful when:

- You need to examine database load over a time period.
- You want to identify top wait events.
- You want to compare SQL by CPU/elapsed/buffer gets.
- You need trend analysis without using AWR.
- The environment is not licensed for Diagnostics Pack, yet installing and running Statspack is permitted under applicable policy/licensing.

Statspack is not a complete replica of AWR and does not provide all capabilities of AWR/ASH/ADDM.

## 20. Installing Statspack

Installation is typically performed by a DBA using Oracle scripts in the Oracle Home. The standard script is:

~~~text
@?/rdbms/admin/spcreate.sql
~~~

The script may prompt for:

- `PERFSTAT` user password.
- Default tablespace.
- Temporary tablespace.

Once installed, the `PERFSTAT` schema owns the Statspack tables and packages.

### 20.1 Before Installing

The DBA should confirm:

- Correct Oracle Home and database.
- Sufficient tablespace capacity.
- Tablespace names and quotas.
- Privileges to create users/packages/objects.
- Backup and retention procedures.
- Whether Statspack is already installed.

Do not re-run the installation script casually on a production system that already has `PERFSTAT`. Check existing status and version documentation first.

### 20.2 Never Run Installation Scripts Under an Application Account

Statspack installation creates administrative schemas and objects. That is a DBA task governed by change management. Applications should only receive read access to required reports, never own the `PERFSTAT` schema.

## 21. Taking Statspack Snapshots

After installation, take snapshots using the `PERFSTAT.STATSPACK` package:

~~~sql
EXEC perfstat.statspack.snap;
~~~

Each snapshot records statistics at a point in time. Reports compare two snapshots to compute differences across the interval.

You can pass a snapshot level once configuration and privileges are understood:

~~~sql
EXEC perfstat.statspack.snap(i_snap_level => 5);
~~~

Higher snapshot levels collect additional detail and increase storage/collection cost. Verify exact levels and contents against Statspack documentation for your release; never raise levels blindly just to "get more data."

### 21.1 Choosing Snapshot Intervals

A simple workflow:

1. Take a snapshot before the workload begins.
2. Run the workload over a representative period.
3. Take a snapshot after the workload ends.
4. Generate a report between the two snapshots.

Too long a snapshot interval can dilute a brief spike. Too short an interval may yield insufficient data or make snapshot overhead a noticeable fraction.

### 21.2 Periodic Snapshots

DBAs can schedule periodic snapshots via a scheduler per operational policy. Ensure you:

- Choose an appropriate interval.
- Monitor `PERFSTAT` space consumption.
- Implement retention/purging.
- Avoid overly frequent snapshots.
- Log deployment, batch, backup, or incident timestamps.

## 22. Generating a Statspack Report

Standard report generation script:

~~~text
@?/rdbms/admin/spreport.sql
~~~

The script prompts for:

- Begin snapshot.
- End snapshot.
- Report filename.

The report is written to a file on the client/session running the script per SQL*Plus/SQLcl behavior. DBAs should archive it alongside the incident ID and chosen interval.

### 22.1 Common Report Contents

A Statspack report may include:

- Database/instance information.
- Snapshot interval.
- Load Profile.
- Instance Efficiency Percentages.
- Top Timed Events.
- Wait Events.
- SQL ordered by elapsed time.
- SQL ordered by CPU time.
- SQL ordered by buffer gets.
- SQL ordered by physical reads.
- Tablespace/segment statistics depending on level.

Not every section appears at every level or configuration.

### 22.2 Load Profile

Load Profile presents metrics normalized by time or transaction, such as:

- DB time.
- DB CPU.
- Logical reads.
- Physical reads.
- Parses.
- Executes.
- User calls.
- Redo size.

Rates allow comparing workloads across intervals of different lengths, while still requiring attention to total duration, transaction counts, and workload mix.

### 22.3 Top Timed Events

Top Timed Events identifies wait categories or CPU consuming the largest share of time within the snapshot interval.

Read in order:

1. Check DB CPU and major wait events.
2. Identify wait classes.
3. Compare total waits and time waited.
4. Inspect associated SQL/segments or sessions if provided in the report.
5. Correlate with application slowdown timestamps.

A top-ranked event is not automatically an error. Determine whether the event is idle, belongs to the target workload, and rose abnormally compared to baseline.

### 22.4 SQL Ordered by Elapsed/CPU/Buffer Gets

The SQL ordered sections pinpoint resource-heavy statements:

- Elapsed time: SQL accounting for large total time.
- CPU time: SQL consuming CPU.
- Buffer gets: SQL reading many logical blocks.
- Physical reads: SQL driving many physical reads.

A SQL with high elapsed time may run very often with slightly slow executions, or run once very slowly. Inspect execution counts and per-execution metrics where available.

## 23. Purging and Managing Statspack Data

Statspack stores snapshots in the `PERFSTAT` schema. Without purging, data grows over time.

Common purge script:

~~~text
@?/rdbms/admin/sppurge.sql
~~~

The script prompts for the snapshot range to delete. DBAs must define retention, ensuring snapshots needed for active incidents or audits are not removed.

Do not delete rows directly from `PERFSTAT` tables by guesswork without understanding table relationships and package/script procedures.

## 24. How Statspack Differs from AWR

| Criterion | Statspack | AWR |
|---|---|---|
| Purpose | Capturing performance statistic snapshots | Deeper integrated workload repository |
| Installation | DBA installs `PERFSTAT` schema | Built into Oracle Database |
| Snapshots | Package/scheduler calls per configuration | Automatic snapshot mechanism per configuration |
| Reporting | `spreport` and Statspack reports | AWR reports and related tools |
| ASH/ADDM | No equivalent feature suite | Integrated companion features |
| Licensing | Used per product terms/authorized rights | AWR/ASH/ADDM belong to Diagnostics Pack |

Statspack is a valuable option, but lacks the full data, granularity, and analytical capabilities of AWR/ASH. Do not treat a Statspack report as a complete 1-to-1 substitute for every AWR report.

## 25. Licensing Scope: Diagnostics Pack and Tuning Pack

Oracle separates certain advanced performance management features into packs. Before use, verify licensing terms applicable to your version, edition, deployment, and organizational agreement.

### 25.1 Diagnostics Pack

Features typically tied to Diagnostics Pack include:

- Automatic Workload Repository (AWR).
- Active Session History (ASH).
- Automatic Database Diagnostic Monitor (ADDM).
- Corresponding AWR/ASH historical views and reports.

Views such as `DBA_HIST_*` generally fall under AWR data. Never query or export them merely because an account has SELECT privileges; technical access does not equal license entitlement.

### 25.2 Tuning Pack

Features typically tied to Tuning Pack include:

- SQL Tuning Advisor.
- SQL Access Advisor.
- Real-Time SQL Monitoring and related SQL monitoring capabilities.
- Other integrated tuning features.

Tuning Pack typically carries a prerequisite dependency on Diagnostics Pack under Oracle policy. Verify current terms and your organization's contracts.

### 25.3 CONTROL_MANAGEMENT_PACK_ACCESS Is Not Proof of License

You can inspect the parameter:

~~~sql
SHOW PARAMETER control_management_pack_access
~~~

This parameter controls access to certain management pack features inside the database. A value enabling features does not prove the organization purchased or is licensed for them.

Do not alter this parameter on production to toggle features on your own. The DBA/license owner must confirm authorized scope.

### 25.4 Dynamic Views and SQL Trace

Many basic dynamic performance views and SQL Trace/TKPROF are standard diagnostic tools, yet certain additional views, reports, or capabilities may belong to specific packs. Verify licensing documentation for the exact feature; do not assume everything starting with V$ is free or that every diagnostic feature requires the same pack.

## 26. Diagnosing in Oracle RAC

In RAC, a service can run across multiple instances. A session SID is unique only within a single instance.

Use GV$ when cluster-wide visibility is needed:

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       status,
       sql_id,
       event,
       wait_class
FROM gv$session
WHERE username IS NOT NULL
ORDER BY inst_id, sid;
~~~

### 26.1 Blocking Sessions on Another Instance

When investigating blocking, preserve:

- INST_ID.
- SID.
- SERIAL#.
- Blocking instance/session.

Never use SID alone to identify a blocker in RAC.

### 26.2 Tracing in RAC

Trace files are written on the node/instance where the session executes. When tracing by service/module/client identifier, understand instance scope and how to consolidate trace files. DBAs can use ADRCI or appropriate centralized diagnostic administration tools.

## 27. Multitenant: CDB and PDB

In a multitenant environment:

- A CDB contains a root container and multiple PDBs.
- Sessions have a CON_ID.
- Some views contain container-scoped data.
- `CDB_*` dictionary views provide cross-container visibility according to privileges.

Example:

~~~sql
SELECT con_id,
       sid,
       serial#,
       username,
       status,
       sql_id,
       module
FROM v$session
WHERE username IS NOT NULL
ORDER BY con_id, sid;
~~~

When analyzing, record CON_ID and the current container. Do not combine statistics across multiple PDBs without preserving scope distinctions.

## 28. Workflow Combining Dynamic Views, Tracing, and Statspack

The three tools complement one another:

| Tool | Scope | Suitable Questions |
|---|---|---|
| V$SESSION/V$SQL | Current state and cursors in memory | Which sessions/SQL are running? |
| V$SYSTEM_EVENT/V$SYSSTAT | Cumulative counters | How did waits and resources grow over the interval? |
| SQL Trace/TKPROF | Selected session/request | What are the detailed parse/execute/fetch/waits for SQL? |
| Statspack | Two snapshots across an interval | How did database load and top SQL/waits change? |

An incident can be handled as follows:

1. Record the start time and affected service.
2. Query V$SESSION to identify ACTIVE sessions and SQL_IDs.
3. Check EVENT, WAIT_CLASS, blocking sessions, and module/action.
4. Inspect V$SQL/V$SQLSTATS and cursor plans.
5. Capture V$SYSSTAT/V$SYSTEM_EVENT deltas over a short window.
6. If needed, enable a scoped trace for one session or module/action.
7. Use TKPROF to inspect parse/execute/fetch/waits.
8. For a longer-range view, generate a Statspack report between two snapshots.
9. Correlate timing with deployments, batch jobs, data changes, and application load.
10. Document findings, SQL_ID, plan hash, metrics, and sampling timestamps.

## 29. Investigation Example: Slow Order Creation Request

Suppose the `CREATE_ORDER` API's latency jumped from 200 ms to 8 seconds.

### Step 1: Filter Sessions by Module/Action

~~~sql
SELECT sid,
       serial#,
       username,
       module,
       action,
       client_identifier,
       sql_id,
       status,
       event,
       wait_class,
       blocking_session
FROM v$session
WHERE module = 'ORDER_SERVICE'
  AND action = 'CREATE_ORDER';
~~~

### Step 2: Inspect SQL_ID

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       ROUND(elapsed_time / 1e6, 2) AS elapsed_seconds,
       ROUND(cpu_time / 1e6, 2) AS cpu_seconds,
       buffer_gets,
       disk_reads
FROM v$sql
WHERE sql_id = :sql_id
ORDER BY child_number;
~~~

### Step 3: Check Blocking

~~~sql
SELECT sid,
       serial#,
       sql_id,
       event,
       blocking_session,
       final_blocking_session
FROM v$session
WHERE sid IN (:target_sid, :blocking_sid);
~~~

### Step 4: Retrieve the Execution Plan

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :sql_id,
        :child_number,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

### Step 5: Scoped Tracing

If you need to analyze a reproducible request/session, the DBA enables `DBMS_MONITOR` trace for the approved SID/SERIAL# or client identifier. After reproducing, disable tracing and analyze with TKPROF.

### Step 6: Evidence-Based Conclusions

Possible diagnostic conclusions include:

- SQL waiting on row locks held by another long-running transaction.
- A statement invoked thousands of times inside a loop.
- CPU spiking due to an execution plan scanning excessive rows.
- Slow commits due to redo write latency.
- Extended fetches due to slow response/client consumption.

Never pick a root cause before inspecting the metrics.

## 30. Common Mistakes

| Mistake | Consequence | Correct Practice |
|---|---|---|
| Looking only at `STATUS = ACTIVE` | Confuses waiting sessions with CPU-burning sessions | Check EVENT, WAIT_CLASS, STATE, and CPU |
| Reading V$SYSSTAT totals as current rates | Unknown how fast metrics grew in the window | Take two snapshots and compute deltas |
| Using SID without SERIAL# | Risk of targeting wrong session after SID reuse | Record SID + SERIAL# + INST_ID |
| Omitting INST_ID in RAC | Misjoins sessions across instances | Use GV$ and preserve INST_ID |
| Treating every wait event as an error | Idle or normal waits get misinterpreted | Check duration, wait class, and workload |
| Killing a blocker immediately | Long rollback or lost critical transaction | Verify blocker and follow operational procedure |
| Enabling system-wide tracing | Overhead, huge files, and sensitive data exposure | Trace a specific session/module/client |
| Enabling bind tracing by default | Risks exposing confidential data | Default `binds => FALSE`; enable only when approved |
| Forgetting to disable trace | Tracing continues indefinitely and fills disk | Set time bounds, disable, and verify |
| Reading only total SQL elapsed time | Cannot separate parse/execute/fetch | Use trace/TKPROF when needed |
| Treating V$SQL as permanent history | Cursors can age out | Sample promptly and archive per process |
| Treating Statspack as identical to AWR | Misaligned expectations on data/tools | Understand each tool's scope and limits |
| Querying `DBA_HIST_*` without license verification | Compliance violation risk | Verify Diagnostics Pack entitlement first |
| Relying on `CONTROL_MANAGEMENT_PACK_ACCESS` as license proof | Parameter does not prove entitlement | Check contracts/licensing owner |
| Granting `SELECT ANY DICTIONARY` to applications | Overly broad privileges | Grant minimal views via a dedicated role |
| Looking only at Top Timed Events | Unknown which SQL/session caused the waits | Correlate SQL, sessions, and timestamps |
| Scheduling Statspack snapshots too frequently | Increases overhead and storage growth | Pick balanced intervals and purge periodically |

## 31. Self-Verification Practice Exercises

Run exercises in a test schema or an environment approved by the DBA.

### Exercise 1 — List Sessions

Query V$SESSION and filter by username. Record SID, SERIAL#, SQL_ID, MODULE, ACTION, EVENT, and WAIT_CLASS.

### Exercise 2 — Set Module/Action

Use `DBMS_APPLICATION_INFO.SET_MODULE`/`SET_ACTION` in a session. Query V$SESSION to confirm the labels appear.

### Exercise 3 — Inspect SQL Cursors

Run a SELECT statement with a SQL_ID. Read V$SQL and V$SQLSTATS, comparing executions, elapsed time, CPU, and buffers.

### Exercise 4 — Read Actual Plans

Run a query with `GATHER_PLAN_STATISTICS`, fetch all results, and inspect `DBMS_XPLAN.DISPLAY_CURSOR` with `ALLSTATS LAST`.

### Exercise 5 — Observe Waits

Create a data-reading workload in a test schema. Sample V$SESSION multiple times and distinguish ON CPU, User I/O, and idle waits.

### Exercise 6 — Observe Blocking

In two test sessions, have Session A update a row without committing, and Session B update the same row. Inspect the blocker via V$SESSION/V$LOCK, then roll back both in proper order.

### Exercise 7 — Compute System Stat Deltas

Take two V$SYSSTAT samples across a workload window. Compute deltas and rates for logical reads, physical reads, and redo size.

### Exercise 8 — Session Trace

In a test session, set `TRACEFILE_IDENTIFIER`, enable `DBMS_SESSION.SESSION_TRACE_ENABLE` with waits TRUE and binds FALSE, run a SQL statement, disable trace, and locate the file via V$DIAG_INFO.

### Exercise 9 — TKPROF

Format the trace file using TKPROF. Compare parse, execute, fetch, CPU, elapsed, disk, query, and rows.

### Exercise 10 — Trace Another Session

Have the DBA enable `DBMS_MONITOR.SESSION_TRACE_ENABLE` for a test SID/SERIAL#. Run a request, then disable tracing. Confirm the trace captured only the targeted session.

### Exercise 11 — Statspack

In an environment pre-configured by the DBA, take two snapshots, run a workload between them, and generate `spreport`. Identify Top Timed Events and SQL ordered by elapsed time.

### Exercise 12 — Privilege Scope

List the views/packages needed for diagnostic work. Design a `DIAG_READER` role with minimal privileges. Distinguish basic dynamic views, Statspack, and Diagnostics/Tuning Pack features.

## 32. Pre-Production Diagnosis Checklist

**Scope**

- Have you identified service, module, action, timeframe, and SQL_ID?
- Are you investigating one session, one service, or an entire instance?
- Do you need GV$ for RAC?
- Do you need to filter CON_ID in multitenant?

**Privileges**

- Does the user have read access only to the necessary V$ views?
- Have overly broad privileges been avoided?
- Is tracing of other sessions enabled only by a DBA or authorized operator?
- Are AWR/ASH/ADDM/SQL Monitoring features verified for licensing?

**Collection**

- Did you record SID, SERIAL#, and INST_ID?
- Did you distinguish current state from cumulative counters?
- Do you have two samples to compute deltas?
- Does the trace have a defined scope and duration?
- Was bind tracing evaluated for security?
- Is the Statspack snapshot interval appropriate?

**Analysis**

- Did you inspect SQL_ID, child cursor, and plan?
- Did you separate CPU from waits?
- Did you check blockers and open transactions?
- Did you inspect TEMP/PGA when sorts/hashes occur?
- Did you correlate timestamps with workloads/deployments?

**Wrap-up**

- Has tracing been disabled?
- Are trace/report files stored in a properly restricted location?
- Is sensitive data protected?
- Is Statspack retention/purging scheduled?
- Are conclusions backed by clear evidence, scope, and timestamps?

## 33. Key Takeaways

| Tool/Concept | Role |
|---|---|
| V$SESSION | Current sessions, SQL, waits, blockers |
| GV$SESSION | RAC-wide sessions, includes INST_ID |
| V$SQL | Cursors and statistics per child cursor |
| V$SQLSTATS | Aggregated statistics per SQL_ID |
| V$SYSTEM_EVENT | Cumulative wait statistics |
| V$SYSSTAT | Cumulative system counters |
| V$SESSTAT | Session counters |
| V$LOCK/V$TRANSACTION | Locks and transactions |
| V$TEMPSEG_USAGE | Temporary segment usage |
| V$PGASTAT | PGA statistics |
| V$DIAG_INFO | Diagnostic directory/file paths |
| DBMS_XPLAN.DISPLAY_CURSOR | Actual cursor execution plan |
| DBMS_SESSION.SESSION_TRACE_ENABLE | Trace the current session |
| DBMS_MONITOR | Trace by session/service/module/action/client ID |
| SQL Trace | Parse, execute, fetch, CPU, waits, and binds if enabled |
| TKPROF | Format and summarize traces |
| Statspack | Snapshots and statistical reports over intervals |
| AWR/ASH/ADDM | Diagnostics Pack features |
| SQL Tuning Advisor/SQL Monitoring | Tuning Pack features per applicable terms |
| Least privilege | Grant only needed access to the right people and scope |

Dynamic views reveal current state and cumulative counters; SQL Trace/TKPROF explains a targeted workload in detail; Statspack provides statistical visibility between two snapshots. Define the question first, preserve session/instance/container scope, compute deltas on cumulative counters, and protect trace files. SELECT privilege does not imply license entitlement: before using AWR, ASH, ADDM, or SQL Tuning/Monitoring, verify the pack and corresponding contract. Sound diagnosis relies on timestamped evidence, SQL_IDs, plans, wait/resource metrics, and authorized access.
