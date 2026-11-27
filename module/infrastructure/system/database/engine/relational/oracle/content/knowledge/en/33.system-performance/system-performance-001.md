# Reading V$SESSION, V$SQL, V$SQLSTATS, and Cumulative Counters in Oracle Database

When a database is slow, the first questions are usually: which session is active, which SQL statement is that session running, how much CPU/I/O is that SQL consuming, and how much has resource usage increased during the observation window?

Oracle provides dynamic performance views to answer these questions. Four views commonly used together are:

- **V$SESSION:** current status and activity of each session, including SQL_ID, wait event, module/action, and blocker information.
- **V$SQL:** statistics for each child cursor in the shared SQL area, including execution count, CPU, elapsed time, logical reads, physical reads, and plan hash.
- **V$SQLSTATS:** summary statistics by SQL_ID, which is fast and can retain metrics longer than V$SQL when a cursor is aged out of the shared pool.
- **V$SESSTAT and V$SYSSTAT:** cumulative statistic counters per session and per instance; must be joined with V$STATNAME to read statistic names.

In addition, V$SESS_TIME_MODEL and V$SYS_TIME_MODEL provide time counters such as DB time and DB CPU in microseconds.

The key when reading these views is distinguishing **a snapshot of current state**, **cumulative figures since the cursor/session/instance started**, and **the increase over a time interval**. A large number alone does not prove the system is slow right now. To measure the rate of increase or average cost, you need to take snapshots at two points in time and compute the delta.

## 1. What Are Dynamic Performance Views?

Views prefixed with V$ display status and performance information maintained by Oracle in memory. They are commonly called dynamic performance views or fixed views.

Characteristics:

- Reflect the runtime state of the instance, sessions, cursors, waits, and other components.
- Many counters are cumulative, not values for the current second alone.
- Some information only exists while the session or cursor remains in memory.
- These views are not long-term historical repositories. For long-term trend analysis, a snapshot/monitoring system or appropriate historical sources are needed.
- Querying V$ views also consumes resources; avoid polling too frequently or selecting unnecessary columns.

### 1.1 V$ and GV$

In Oracle RAC:

- V$ typically displays information for the current instance.
- GV$ displays information across instances and adds the INST_ID column.

Example:

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       status
FROM gv$session
WHERE type = 'USER';
~~~

When using GV$, always keep INST_ID in the session identifier key and when joining cluster-wide views. SID can overlap across instances.

### 1.2 CDB/PDB and CON_ID

In a multitenant environment, many dynamic performance views have a CON_ID column:

- 0: data belongs to the entire CDB or a non-CDB.
- 1: data belongs to the CDB root.
- Other values: the corresponding container.

When aggregating metrics, do not combine rows with different CON_ID values if the goal is to analyze a single PDB. Some views also include CON_DBID to identify the PDB's database.

### 1.3 Access Privileges

To read dynamic performance views, an account needs appropriate privileges, typically SELECT_CATALOG_ROLE or direct SELECT privileges on the corresponding SYS.V_$ objects according to DBA policy. You should not grant SYSDBA just to run routine monitoring queries.

## 2. Map of Essential Views

| View | Scope | Primary Content |
|---|---|---|
| V$SESSION | Connected sessions | Status, current/previous SQL, waits, blocker, module/action |
| V$SQL | Individual child cursors | SQL text, child number, plan hash, executions, and resource counters |
| V$SQLSTATS | One row per SQL_ID | Summary SQL statistics, good performance, and longer retention than V$SQL |
| V$SESSTAT | Individual sessions | Cumulative statistics for a session |
| V$SYSSTAT | Instance | System-level statistics |
| V$STATNAME | Statistic names | Maps STATISTIC# to NAME |
| V$SESS_TIME_MODEL | Individual sessions | DB time, DB CPU, and time by activity type |
| V$SYS_TIME_MODEL | Instance | DB time, DB CPU, and instance-wide cumulative time |
| V$SESSION_EVENT | Individual sessions | Wait counts and total wait time by event |
| V$SESSION_LONGOPS | Long operations | Progress of certain long-running operations |
| V$SQL_MONITOR | Monitored execution | Runtime metrics of SQL execution; subject to conditions and licensing |

These views answer questions at different scopes. Do not add V$SESSION, V$SQL, and V$SYSSTAT together as if they were three independent sources; they describe different layers of the same database activity.

## 3. Reading V$SESSION: Who Is Doing What?

V$SESSION has one row per current session. It is the starting point when you need to know which session is running, waiting, or being blocked.

### 3.1 Important Columns

| Column | Meaning |
|---|---|
| SID | Session identifier within the instance |
| SERIAL# | Serial number to distinguish a session lifetime from another session that may reuse the SID |
| USERNAME | Database username |
| STATUS | ACTIVE, INACTIVE, KILLED, SNIPED, or related status |
| TYPE | USER or BACKGROUND |
| MACHINE / PROGRAM / OSUSER | Client/process connection details |
| SERVICE_NAME | Database service of the session |
| SQL_ID | Currently executing SQL statement |
| SQL_CHILD_NUMBER | Child cursor of the current SQL |
| PREV_SQL_ID | Previously executed SQL statement |
| SQL_EXEC_START | Start time of the current execution |
| SQL_EXEC_ID | Execution identifier, when available |
| MODULE / ACTION | Module and action names set by the application |
| CLIENT_IDENTIFIER | Client/user identifier set by the application |
| LAST_CALL_ET | Seconds the session has been in its current ACTIVE or INACTIVE state |
| EVENT / WAIT_CLASS | Most recent or current wait event and wait class |
| STATE | Wait state |
| BLOCKING_SESSION | SID of the blocking session, if identified |
| FINAL_BLOCKING_SESSION | Final session in the blocker chain, if identified |

### 3.2 ACTIVE Does Not Mean Using CPU

STATUS = ACTIVE means the session is currently executing a database call. The session may be:

- Running on CPU.
- Waiting on I/O reads.
- Waiting on a lock or enqueue.
- Waiting on the network or another resource.

To understand the actual state, check EVENT, WAIT_CLASS, STATE, and wait time. ACTIVE only indicates the session is inside a call, not whether that call is consuming CPU or waiting.

### 3.3 LAST_CALL_ET Is Not Session Age

LAST_CALL_ET is in seconds:

- When STATUS = ACTIVE: seconds since the session transitioned to ACTIVE.
- When STATUS = INACTIVE: seconds since the session transitioned to INACTIVE.

Do not use LAST_CALL_ET to conclude how long a session has existed. LOGON_TIME shows when the session logged on.

### 3.4 SQL_ID and PREV_SQL_ID

SQL_ID identifies the current statement. When a session has no SQL executing, SQL_ID may be NULL or may not represent a running statement; PREV_SQL_ID helps inspect the most recent previous SQL.

If a session is executing PL/SQL, SQL_ID may represent the SQL running inside the PL/SQL block. The columns PLSQL_ENTRY_OBJECT_ID, PLSQL_OBJECT_ID, and PLSQL_SUBPROGRAM_ID help identify the related PL/SQL stack.

### 3.5 Viewing ACTIVE Sessions and Current SQL

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.status,
       s.machine,
       s.program,
       s.module,
       s.action,
       s.sql_id,
       s.sql_child_number AS child_number,
       s.sql_exec_start,
       s.last_call_et,
       s.event,
       s.wait_class,
       s.state,
       q.plan_hash_value,
       SUBSTR(q.sql_text, 1, 120) AS sql_text
FROM v$session s
LEFT JOIN v$sql q
  ON q.sql_id = s.sql_id
 AND q.child_number = s.sql_child_number
WHERE s.type = 'USER'
  AND s.status = 'ACTIVE'
ORDER BY s.last_call_et DESC;
~~~

Join V$SQL using both SQL_ID and SQL_CHILD_NUMBER to match the exact child cursor. Joining on SQL_ID alone can produce multiple rows if the SQL has multiple child cursors.

### 3.6 Viewing Both Current SQL and Previous SQL

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.status,
       s.sql_id,
       s.sql_child_number,
       s.prev_sql_id,
       s.prev_child_number,
       s.last_call_et,
       s.module,
       s.action
FROM v$session s
WHERE s.type = 'USER'
ORDER BY s.logon_time;
~~~

For INACTIVE sessions, PREV_SQL_ID is often more useful than SQL_ID for finding the SQL just executed. Correlate it with session status and sampling time.

### 3.7 Finding Waiting Sessions and Blockers

~~~sql
SELECT w.sid                  AS waiting_sid,
       w.serial#              AS waiting_serial,
       w.username             AS waiting_user,
       w.event,
       w.wait_class,
       w.state,
       w.wait_time_micro,
       w.blocking_session_status,
       w.blocking_instance,
       w.blocking_session,
       b.serial#              AS blocker_serial,
       b.username             AS blocker_user,
       b.status               AS blocker_status,
       b.sql_id               AS blocker_sql_id,
       b.event                AS blocker_event
FROM v$session w
LEFT JOIN v$session b
  ON b.sid = w.blocking_session
WHERE w.blocking_session_status = 'VALID'
ORDER BY w.wait_time_micro DESC;
~~~

BLOCKING_SESSION is only meaningful when BLOCKING_SESSION_STATUS = VALID. With RAC, use GV$SESSION and also join on BLOCKING_INSTANCE/INST_ID. If there are multiple layers of blockers, FINAL_BLOCKING_SESSION helps locate the root session in the wait chain.

### 3.8 Interpreting Waits

Some common wait classes:

| WAIT_CLASS | General Meaning |
|---|---|
| User I/O | Waiting for data reads/writes for user operations |
| Application | Typically related to locks caused by the application or transactions |
| Concurrency | Waiting on concurrency resources such as latches/mutexes or enqueues in this class |
| Cluster | Waiting on inter-instance resources in RAC |
| Commit | Waiting for commit completion, such as log file sync |
| Network | Waiting on transmission/reception over Oracle Net |
| Idle | Session is idle, waiting on the client or an event that does not represent database work |

WAIT_CLASS is only a category. EVENT is the specific wait name. For example, Application may include `enq: TX - row lock contention`; Commit may include `log file sync`. Do not draw conclusions about root cause from the class name alone.

## 4. Reading V$SQL: Statistics by Child Cursor

V$SQL displays statistics for SQL cursors in the shared SQL area. Each row corresponds to a child cursor of the parent SQL text.

A single SQL_ID can have multiple child cursors due to differences in bind metadata, optimizer environment, object resolution, authorization, adaptive cursor sharing, or other cursor-sharing mismatches.

### 4.1 Important Columns

| Column | Meaning |
|---|---|
| SQL_ID | Parent SQL cursor identifier |
| CHILD_NUMBER | Child cursor sequence number |
| PLAN_HASH_VALUE | Hash representing the execution plan |
| SQL_TEXT | First 1,000 characters of the SQL text |
| SQL_FULLTEXT | Full SQL text as a CLOB |
| EXECUTIONS | Number of executions since the cursor was loaded into the library cache |
| END_OF_FETCH_COUNT | Number of times the cursor was fetched to completion |
| PARSE_CALLS | Number of parse calls |
| LOADS | Number of times the cursor was loaded or reloaded |
| INVALIDATIONS | Number of times the child cursor was invalidated |
| BUFFER_GETS | Number of logical buffer gets |
| DISK_READS | Number of recorded disk reads |
| ROWS_PROCESSED | Total rows processed/returned by the cursor |
| CPU_TIME | CPU time, microseconds |
| ELAPSED_TIME | Elapsed database time, microseconds |
| USER_IO_WAIT_TIME | User I/O wait time, microseconds |
| APPLICATION_WAIT_TIME | Application wait time, microseconds |
| CONCURRENCY_WAIT_TIME | Concurrency wait time, microseconds |
| CLUSTER_WAIT_TIME | Cluster wait time in RAC, microseconds |
| MODULE / ACTION | Module/action when the statement was parsed |
| IS_BIND_SENSITIVE / IS_BIND_AWARE | Adaptive cursor sharing status |
| IS_REOPTIMIZABLE | Whether the child cursor can trigger reoptimization on a subsequent run |

### 4.2 V$SQL Contains Cumulative Cursor Metrics

EXECUTIONS, CPU_TIME, ELAPSED_TIME, BUFFER_GETS, and other counters are not figures for a single execution. They accumulate from the time the cursor is loaded into the library cache.

Therefore:

- A SQL running 100,000 times can have a high total elapsed time even if each execution is very fast.
- A SQL running only once for 20 minutes might have a lower total elapsed time than a frequently executed SQL.
- Cursor aging out or reloads can change the counter lifecycle.
- Use averages or deltas when comparing cost per execution or across a time interval.

### 4.3 When Are Metrics Updated?

Statistics in V$SQL are normally updated when query execution finishes. For long-running queries, Oracle updates metrics periodically, roughly every 5 seconds, so impact can be observed while the query is still running.

Do not assume every counter of an active SQL statement is updated instantaneously on every view read.

### 4.4 Viewing All Child Cursors of a SQL_ID

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       end_of_fetch_count,
       parse_calls,
       loads,
       invalidations,
       buffer_gets,
       disk_reads,
       rows_processed,
       ROUND(cpu_time / 1000000, 3) AS cpu_seconds,
       ROUND(elapsed_time / 1000000, 3) AS db_elapsed_seconds,
       ROUND(
           elapsed_time / NULLIF(executions, 0) / 1000,
           3
       ) AS avg_elapsed_ms,
       last_active_time,
       sql_text
FROM v$sql
WHERE sql_id = :p_sql_id
ORDER BY child_number;
~~~

This query shows how many child cursors a SQL_ID has, how plan hashes differ, and the cumulative cost of each child.

### 4.5 Why Is END_OF_FETCH_COUNT Important?

EXECUTIONS counts how many times the cursor was executed. END_OF_FETCH_COUNT only increments when the cursor is fetched to completion. If the application fetches only part of the result set and closes the cursor, the execution is still counted, but it is not counted as fully fetched.

Accordingly:

- END_OF_FETCH_COUNT smaller than EXECUTIONS can indicate many executions did not fetch all rows.
- This is not automatically an error; the application may intentionally retrieve only a subset of results.
- When evaluating workloads that return many rows, inspect EXECUTIONS, END_OF_FETCH_COUNT, FETCHES, and ROWS_PROCESSED together.

### 4.6 Parse Calls Do Not Equal Hard Parses

PARSE_CALLS is the number of parse calls, including calls that may be resolved via soft parse. Do not use PARSE_CALLS as the hard parse count.

To track hard parses at the session or instance scope, check the `parse count (hard)` statistic in V$SESSTAT/V$SYSSTAT. You can compare it against `parse count (total)` to understand the parse ratio.

### 4.7 ELAPSED_TIME Is Not Always Wall-Clock Time

CPU_TIME and ELAPSED_TIME in V$SQL are in microseconds. ELAPSED_TIME is the database time for parsing, executing, and fetching.

With parallel execution, ELAPSED_TIME is the sum of the query coordinator's time plus the parallel query workers' time. Thus the value can exceed the actual wall-clock time the user waited. Do not take ELAPSED_TIME of parallel SQL to directly infer wall-clock duration.

## 5. Reading V$SQLSTATS: Summary Statistics by SQL_ID

V$SQLSTATS provides basic performance statistics for SQL cursors and has one row per unique SQL_ID.

Compared with V$SQL and V$SQLAREA:

- Faster and scales better.
- Longer retention; statistics may still appear after the cursor has aged out of the shared pool.
- Contains only a subset of columns from V$SQL/V$SQLAREA.
- Well suited for finding resource-intensive SQL at an overview level.

When you need to analyze child cursors, bind sensitivity, or multiple plan hashes, switch to V$SQL.

### 5.1 Commonly Used Metrics

| Column | How to Read |
|---|---|
| SQL_ID | SQL statement |
| PLAN_HASH_VALUE | Plan hash currently represented in the statistics |
| EXECUTIONS | Cumulative executions |
| PARSE_CALLS | Cumulative parse calls |
| BUFFER_GETS | Cumulative logical reads |
| DISK_READS | Cumulative disk reads |
| ROWS_PROCESSED | Total rows processed |
| CPU_TIME | CPU microseconds |
| ELAPSED_TIME | Database elapsed microseconds |
| USER_IO_WAIT_TIME | User I/O wait microseconds |
| APPLICATION_WAIT_TIME | Application wait microseconds |
| CONCURRENCY_WAIT_TIME | Concurrency wait microseconds |
| CLUSTER_WAIT_TIME | Cluster wait microseconds |
| LAST_ACTIVE_TIME | Most recent time a contributing cursor's statistics were updated |
| SQL_TEXT / SQL_FULLTEXT | SQL text |

### 5.2 Finding SQL with High Total Elapsed Time

~~~sql
SELECT sql_id,
       plan_hash_value,
       executions,
       ROUND(elapsed_time / 1000000, 2) AS total_db_seconds,
       ROUND(cpu_time / 1000000, 2) AS total_cpu_seconds,
       ROUND(
           elapsed_time / NULLIF(executions, 0) / 1000,
           2
       ) AS avg_elapsed_ms,
       ROUND(
           buffer_gets / NULLIF(executions, 0),
           2
       ) AS avg_buffer_gets,
       disk_reads,
       rows_processed,
       parse_calls,
       last_active_time,
       SUBSTR(sql_text, 1, 120) AS sql_text
FROM v$sqlstats
WHERE executions > 0
ORDER BY elapsed_time DESC
FETCH FIRST 20 ROWS ONLY;
~~~

This lists SQL statements with high total database elapsed time among the metrics still retained by the view. It helps identify workloads consuming significant total resources, not necessarily the slowest individual executions.

### 5.3 Finding SQL with High CPU Time

~~~sql
SELECT sql_id,
       executions,
       ROUND(cpu_time / 1000000, 2) AS cpu_seconds,
       ROUND(cpu_time / NULLIF(executions, 0) / 1000, 2)
           AS avg_cpu_ms,
       buffer_gets,
       rows_processed,
       last_active_time,
       SUBSTR(sql_text, 1, 120) AS sql_text
FROM v$sqlstats
WHERE executions > 0
ORDER BY cpu_time DESC
FETCH FIRST 20 ROWS ONLY;
~~~

High CPU time suggests a CPU-intensive workload. Examine execution count, CPU per execution, row count, plan, and parallelism to understand the cause.

### 5.4 Finding SQL with High Logical Reads

~~~sql
SELECT sql_id,
       executions,
       buffer_gets,
       ROUND(buffer_gets / NULLIF(executions, 0), 2)
           AS avg_buffer_gets,
       disk_reads,
       rows_processed,
       SUBSTR(sql_text, 1, 120) AS sql_text
FROM v$sqlstats
WHERE executions > 0
ORDER BY buffer_gets DESC
FETCH FIRST 20 ROWS ONLY;
~~~

BUFFER_GETS is the number of logical buffer accesses. A high value can result from full scans, repeated nested loops, wide index range scans, or a workload legitimately processing many rows. Inspect the execution plan and row counts to distinguish them.

### 5.5 DELTA_* Columns in V$SQLSTATS

V$SQLSTATS includes columns such as:

- DELTA_EXECUTION_COUNT
- DELTA_BUFFER_GETS
- DELTA_DISK_READS
- DELTA_CPU_TIME
- DELTA_ELAPSED_TIME
- DELTA_ROWS_PROCESSED
- DELTA_USER_IO_WAIT_TIME
- DELTA_PARSE_CALLS

The DELTA_* columns represent the increment since the most recent AWR snapshot. They do not automatically represent an arbitrary custom window you just picked. If you need the delta between two custom monitoring timestamps, capture snapshots at both points yourself.

## 6. Comparing V$SQL and V$SQLSTATS

| Criterion | V$SQL | V$SQLSTATS |
|---|---|---|
| Row granularity | One row per child cursor | One row per unique SQL_ID |
| Level of detail | Specific child cursor and plan | Overview by SQL_ID |
| Plan information | CHILD_NUMBER, PLAN_HASH_VALUE, and rich metadata | Has PLAN_HASH_VALUE, but does not replace child cursor detail |
| Bind/adaptive cursor | Has IS_BIND_SENSITIVE, IS_BIND_AWARE, and reoptimization columns | Not as complete as V$SQL |
| Metrics | Cumulative per child cursor since load | Aggregated statistics for the SQL statement |
| Retention | Cursor can age out of the shared pool | Statistics can persist after the cursor ages out |
| Use when | Analyzing plans/child cursors | Ranking and finding resource-intensive SQL |

A sound workflow is to use V$SQLSTATS to identify notable SQL_IDs, then use V$SQL to inspect child cursors, plan hashes, bind-sensitive state, and execution details.

## 7. Session-Level Cumulative Counters: V$SESSTAT

V$SESSTAT displays statistics per session. Each row contains:

- SID: session identifier.
- STATISTIC#: statistic number.
- VALUE: statistic value.
- CON_ID: related container in a multitenant environment.

To get the statistic name, join with V$STATNAME:

~~~sql
SELECT s.sid,
       se.serial#,
       n.name,
       s.value
FROM v$sesstat s
JOIN v$statname n
  ON n.statistic# = s.statistic#
JOIN v$session se
  ON se.sid = s.sid
WHERE s.sid = :p_sid
  AND n.name IN (
      'session logical reads',
      'physical reads',
      'parse count (total)',
      'parse count (hard)',
      'execute count',
      'user commits',
      'redo size',
      'sorts (disk)',
      'sorts (memory)',
      'SQL*Net roundtrips to/from client'
  )
ORDER BY n.name;
~~~

### 7.1 Commonly Used Statistics

| Statistic Name | Meaning |
|---|---|
| session logical reads | Logical reads of the session |
| physical reads | Physical read blocks recorded for the session |
| parse count (total) | Total parse calls |
| parse count (hard) | Hard parse calls |
| execute count | Number of executions |
| user commits | Commits performed by the user session |
| redo size | Bytes of redo generated |
| sorts (memory) | Sorts completed in memory |
| sorts (disk) | Sorts that spilled to disk |
| SQL*Net roundtrips to/from client | Oracle Net round-trips with the client |

VALUE does not share a single unit across all statistics. For example, `redo size` is in bytes, some time counters use centiseconds or microseconds depending on the view/statistic, while other counters represent counts or blocks. Always check the description of each statistic instead of assuming a unit.

### 7.2 Why Join V$STATNAME?

STATISTIC# is not guaranteed to remain unchanged across Oracle releases. Monitoring scripts should rely on NAME rather than hard-coding statistic numbers.

Oracle documents V$STATNAME.NAME as stable across releases; DISPLAY_NAME may change. Therefore, use NAME as the key in scripts.

### 7.3 Lifecycle of Session Statistics

V$SESSTAT reflects only currently existing sessions. When a session disconnects:

- Its session statistics are rolled into V$SYSSTAT.
- The session's values are cleared until a new session reuses that slot.

If a SID is reused, you cannot rely on SID alone to identify the same session across two snapshots. You must check SERIAL# and, in RAC, INST_ID.

## 8. Instance-Wide Cumulative Counters: V$SYSSTAT

V$SYSSTAT displays system statistics for the instance. It contains STATISTIC#, NAME, CLASS, VALUE, STAT_ID, and CON_ID.

Example:

~~~sql
SELECT name,
       value,
       class,
       con_id
FROM v$sysstat
WHERE name IN (
    'session logical reads',
    'physical reads',
    'redo size',
    'user commits',
    'execute count',
    'parse count (total)',
    'parse count (hard)',
    'user calls'
)
ORDER BY name;
~~~

V$SYSSTAT is instance-scoped. It does not represent a single user or SQL statement. Some statistics include foreground session activity; some background-related statistics have specific semantics. Check the individual statistic descriptions.

### 8.1 Why Is V$SYSSTAT Useful?

It helps answer system-level questions:

- Are logical reads increasing rapidly?
- Is a large amount of redo being generated?
- Are hard parses spiking unusually?
- How are executions and user calls growing?
- Are disk sorts increasing with workload?

These are cumulative counters. A value of 1,000,000 is only meaningful when you know since when it has accumulated and how much it increased over the analysis window.

### 8.2 V$SYSSTAT in RAC

In RAC, use GV$SYSSTAT to retrieve metrics per instance:

~~~sql
SELECT inst_id,
       name,
       value
FROM gv$sysstat
JOIN gv$statname
  USING (inst_id, statistic#)
WHERE name IN (
    'session logical reads',
    'physical reads',
    'redo size',
    'user commits'
)
ORDER BY inst_id, name;
~~~

Preserve INST_ID when taking snapshots. Do not subtract one instance's value from another's.

## 9. Time Model: DB Time and DB CPU

V$SESSTAT/V$SYSSTAT have many counters, but when you need time spent on database calls, the time model is often easier to interpret.

- V$SESS_TIME_MODEL: cumulative time per session.
- V$SYS_TIME_MODEL: instance-wide cumulative time.

Time model values are stored in microseconds.

### 9.1 DB Time

DB time is the total elapsed time spent performing database user-level calls. It includes CPU time and non-idle wait time of user calls; it excludes background process time such as PMON except in background-specific statistics.

DB time is summed across user sessions. Because multiple sessions run concurrently, DB time in one minute can exceed 60 seconds.

### 9.2 DB CPU

DB CPU is the CPU time consumed by database user-level calls. It excludes CPU consumed by background processes such as PMON.

Comparing DB CPU with DB time:

- DB CPU close to DB time: the workload is heavily CPU-bound.
- DB time significantly higher than DB CPU: substantial time is spent in non-idle waits.

This is a high-level indicator; inspect wait classes/events to see where the waiting occurs.

### 9.3 Viewing Instance-Wide Time Model

~~~sql
SELECT stat_name,
       value,
       ROUND(value / 1000000, 2) AS seconds
FROM v$sys_time_model
WHERE stat_name IN (
    'DB time',
    'DB CPU',
    'sql execute elapsed time',
    'parse time elapsed',
    'PL/SQL execution elapsed time'
)
ORDER BY stat_name;
~~~

### 9.4 Viewing Time Model for a Session

~~~sql
SELECT sid,
       stat_name,
       value,
       ROUND(value / 1000000, 3) AS seconds
FROM v$sess_time_model
WHERE sid = :p_sid
  AND stat_name IN (
      'DB time',
      'DB CPU',
      'sql execute elapsed time',
      'parse time elapsed',
      'PL/SQL execution elapsed time'
  )
ORDER BY stat_name;
~~~

### 9.5 Update Latency

Time model counters may be buffered before being displayed. For long timed operations, the view can lag by up to roughly 5 seconds of newly accrued time. Therefore, do not treat the time model as a real-time clock with exact per-second precision.

## 10. Cumulative Counters, Snapshots, and Deltas

This is the most important principle when reading cumulative counters.

Suppose a counter has:

| Timestamp | BUFFER_GETS |
|---|---:|
| 10:00:00 | 1,000,000 |
| 10:05:00 | 1,250,000 |

The current value is 1,250,000, but the logical reads in the past 5 minutes are:

\[
\Delta = 1{,}250{,}000 - 1{,}000{,}000 = 250{,}000
\]

Average growth rate:

\[
\text{Rate} = \frac{\Delta}{\text{elapsed seconds}}
= \frac{250{,}000}{300}
\approx 833.33 \text{ gets/second}
\]

### 10.1 Basic Formulas

For counter C:

\[
\Delta C = C_{after} - C_{before}
\]

\[
\text{Rate} = \frac{\Delta C}{t_{after}-t_{before}}
\]

When execution count is available:

\[
\text{Average per execution}
= \frac{\Delta C}{\Delta executions}
\]

### 10.2 Taking Two V$SYSSTAT Snapshots

Run the following query at time T0 and save the output:

~~~sql
SELECT SYSTIMESTAMP AS sample_time,
       n.name,
       s.value
FROM v$sysstat s
JOIN v$statname n
  ON n.statistic# = s.statistic#
WHERE n.name IN (
    'session logical reads',
    'physical reads',
    'redo size',
    'user commits',
    'execute count',
    'parse count (hard)'
)
ORDER BY n.name;
~~~

After the measurement interval, run the exact same query at T1. Subtract VALUE at T0 from VALUE at T1 for the same statistic, same instance, and same CON_ID.

### 10.3 Taking Two V$SESSTAT Snapshots

For a specific session:

~~~sql
SELECT SYSTIMESTAMP AS sample_time,
       s.sid,
       se.serial#,
       n.name,
       s.value
FROM v$sesstat s
JOIN v$statname n
  ON n.statistic# = s.statistic#
JOIN v$session se
  ON se.sid = s.sid
WHERE s.sid = :p_sid
  AND n.name IN (
      'session logical reads',
      'physical reads',
      'execute count',
      'parse count (total)',
      'parse count (hard)',
      'redo size'
  )
ORDER BY n.name;
~~~

When subtracting two snapshots, verify that SID and SERIAL# match. If the session disconnected or the SID was reused, do not compute a delta across two different sessions.

### 10.4 Conditions for a Meaningful Delta

- Both snapshots share the same scope: same SID/SERIAL#, same INST_ID, same CON_ID, or same SQL_ID/child cursor.
- Same statistic name.
- Same instance/session/cursor lifecycle.
- Elapsed time between snapshots is accurately recorded.
- If a counter decreases, investigate resets/restarts/reloads or lifecycle changes before interpreting.

Never take cumulative values from two different instances or two different child cursors to compute a single delta.

## 11. Snapshotting SQL Statistics to Measure an Interval

V$SQLSTATS provides DELTA_* columns calculated since the latest AWR snapshot, but if you need a custom measurement window, you can store snapshots of V$SQLSTATS into a monitoring table.

### 11.1 Example Snapshot Table Creation

~~~sql
CREATE TABLE perf_sql_snapshot (
    sample_time     TIMESTAMP WITH TIME ZONE,
    inst_id         NUMBER,
    con_id          NUMBER,
    sql_id          VARCHAR2(13),
    plan_hash_value NUMBER,
    executions      NUMBER,
    buffer_gets     NUMBER,
    disk_reads      NUMBER,
    cpu_time        NUMBER,
    elapsed_time    NUMBER,
    rows_processed  NUMBER
);
~~~

This table is only an example for a monitoring/lab schema. In production, configure appropriate retention, access controls, and storage capacity.

### 11.2 Capturing the First Snapshot

~~~sql
INSERT INTO perf_sql_snapshot
SELECT SYSTIMESTAMP,
       inst_id,
       con_id,
       sql_id,
       plan_hash_value,
       executions,
       buffer_gets,
       disk_reads,
       cpu_time,
       elapsed_time,
       rows_processed
FROM gv$sqlstats
WHERE sql_id = :p_sql_id;

COMMIT;
~~~

After the measurement interval, run the same INSERT again. The two snapshot rows will have different timestamps.

### 11.3 Computing Deltas Between Consecutive Snapshots

~~~sql
WITH samples AS (
    SELECT p.*,
           LAG(sample_time) OVER (
               PARTITION BY inst_id, con_id, sql_id, plan_hash_value
               ORDER BY sample_time
           ) AS previous_time,
           LAG(executions) OVER (
               PARTITION BY inst_id, con_id, sql_id, plan_hash_value
               ORDER BY sample_time
           ) AS previous_executions,
           LAG(buffer_gets) OVER (
               PARTITION BY inst_id, con_id, sql_id, plan_hash_value
               ORDER BY sample_time
           ) AS previous_buffer_gets,
           LAG(disk_reads) OVER (
               PARTITION BY inst_id, con_id, sql_id, plan_hash_value
               ORDER BY sample_time
           ) AS previous_disk_reads,
           LAG(cpu_time) OVER (
               PARTITION BY inst_id, con_id, sql_id, plan_hash_value
               ORDER BY sample_time
           ) AS previous_cpu_time,
           LAG(elapsed_time) OVER (
               PARTITION BY inst_id, con_id, sql_id, plan_hash_value
               ORDER BY sample_time
           ) AS previous_elapsed_time,
           LAG(rows_processed) OVER (
               PARTITION BY inst_id, con_id, sql_id, plan_hash_value
               ORDER BY sample_time
           ) AS previous_rows_processed
    FROM perf_sql_snapshot p
)
SELECT inst_id,
       con_id,
       sql_id,
       plan_hash_value,
       sample_time,
       executions - previous_executions AS delta_executions,
       buffer_gets - previous_buffer_gets AS delta_buffer_gets,
       disk_reads - previous_disk_reads AS delta_disk_reads,
       ROUND((cpu_time - previous_cpu_time) / 1000000, 3)
           AS delta_cpu_seconds,
       ROUND((elapsed_time - previous_elapsed_time) / 1000000, 3)
           AS delta_db_elapsed_seconds,
       rows_processed - previous_rows_processed AS delta_rows,
       ROUND(
           (buffer_gets - previous_buffer_gets)
           / NULLIF(executions - previous_executions, 0),
           2
       ) AS avg_buffer_gets_per_exec,
       ROUND(
           (elapsed_time - previous_elapsed_time)
           / NULLIF(executions - previous_executions, 0)
           / 1000,
           2
       ) AS avg_db_elapsed_ms_per_exec,
       ROUND(
           (CAST(sample_time AS DATE) - CAST(previous_time AS DATE))
           * 86400,
           2
       ) AS interval_seconds
FROM samples
WHERE previous_time IS NOT NULL
ORDER BY sample_time DESC;
~~~

Partition by INST_ID, CON_ID, SQL_ID, and PLAN_HASH_VALUE to avoid mixing metrics from different instances, PDBs, or plans. If the SQL changes its plan, it starts a separate snapshot series for the new plan hash.

### 11.4 Limitations of SQL Snapshots

- V$SQLSTATS tracks statistics by SQL_ID, not one row per execution.
- If you need to analyze specific child cursors, snapshot V$SQL using a key containing INST_ID, CON_ID, SQL_ID, and CHILD_NUMBER.
- If a cursor is aged out/reloaded or counters reset, deltas may lose continuity.
- When the plan hash changes, do not compute differences across two plans as one continuous series.
- Elapsed time in parallel execution is the combined database time of the coordinator and workers, which can exceed wall-clock duration.

## 12. Reading Counters with the Right Perspective

### 12.1 Total Time vs. Average per Execution

Total elapsed time helps find SQL consuming heavy resources across the overall workload. Average elapsed time helps find SQL that is slow on each individual run.

Example:

| SQL | Executions | Total elapsed | Average |
|---|---:|---:|---:|
| A | 100,000 | 10,000 s | 100 ms |
| B | 10 | 2,000 s | 200 s |

SQL A accounts for greater total database time. SQL B has much slower individual executions. Different tuning goals will produce different prioritization orders.

### 12.2 Logical Reads and Physical Reads

- BUFFER_GETS: number of times Oracle accessed logical buffers in the buffer cache.
- DISK_READS: number of recorded disk reads.
- PHYSICAL_READ_REQUESTS: number of physical read requests; a request may be served from Database Smart Flash Cache and is not necessarily a disk read.
- PHYSICAL_READ_BYTES: number of bytes read from disk.

High logical reads can cause CPU/buffer contention even when physical reads are low. High physical reads can reflect a working set larger than the cache or queries needing to read large volumes of data.

### 12.3 CPU Time and Elapsed Time

CPU_TIME measures CPU time. ELAPSED_TIME measures database elapsed time for parse/execute/fetch, which may include CPU and waits. If elapsed time is much higher than CPU time, examine wait-time columns and wait events.

### 12.4 Rows Processed and Fetch Count

ROWS_PROCESSED is the cumulative number of rows processed/returned by the cursor. FETCHES is the number of fetch calls, not the number of rows. END_OF_FETCH_COUNT counts executions that fetched all results.

An application fetching small batches can generate many fetch calls. An application retrieving only part of the result set may see EXECUTIONS increase without a corresponding increase in END_OF_FETCH_COUNT.

### 12.5 Parse Calls and Executions

If PARSE_CALLS is close to or greater than EXECUTIONS, the application may be parsing SQL frequently. However, parse_calls do not equal hard parses. Check `parse count (hard)` in session/system stats and inspect cursor sharing.

### 12.6 Wait Time Categories

V$SQL contains Application, Concurrency, Cluster, and User I/O wait time counters. They are stored in microseconds and accumulated on the cursor. These values help distinguish CPU-bound SQL from wait-bound SQL.

Do not mechanically add wait categories to derive elapsed time without understanding how Oracle categorizes waits and their relationships.

## 13. SQL Identification and Child Cursors

### 13.1 SQL_ID

SQL_ID identifies the parent cursor of a SQL text in the library cache. SQL statements with different text typically have different SQL_IDs. SQL_ID does not identify a single execution.

### 13.2 CHILD_NUMBER

A single SQL_ID can have multiple child cursors. Each child can have a different plan or different cursor-sharing conditions. When reading V$SQL, preserve CHILD_NUMBER and PLAN_HASH_VALUE.

### 13.3 PLAN_HASH_VALUE

PLAN_HASH_VALUE provides a quick way to compare cursor plans. The same SQL_ID can exhibit multiple plan hashes across child cursors or over time. When the plan hash changes, inspect the execution plan to understand the actual change.

### 13.4 SQL_EXEC_START and SQL_EXEC_ID

In V$SESSION, SQL_EXEC_START and SQL_EXEC_ID help identify the current execution. This is useful when correlating a running session with V$SQL_MONITOR or SQL plan monitoring, if that feature is in use and properly licensed.

## 14. Module, Action, and Client Identifier

Applications can label their activity using DBMS_APPLICATION_INFO:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_API',
        action_name => 'CONFIRM_ORDER'
    );

    DBMS_APPLICATION_INFO.SET_CLIENT_INFO(
        client_info => 'batch-worker-03'
    );
END;
/
~~~

V$SESSION reflects the session's current module/action. V$SQL stores the session's module/action at the time the SQL statement was first parsed for that cursor. Thus, module/action in V$SQL does not necessarily reflect the current action if the cursor is shared across multiple calls.

CLIENT_IDENTIFIER can be used to identify users/requests in applications using connection pools. Set and reset its value when borrowing/returning connections to avoid misattributing requests.

## 15. RAC: Using GV$ and Preserving INST_ID

In RAC, a SID is only meaningful within one instance. When querying across multiple instances:

~~~sql
SELECT s.inst_id,
       s.sid,
       s.serial#,
       s.username,
       s.status,
       s.sql_id,
       s.sql_child_number,
       s.event,
       s.wait_class,
       q.plan_hash_value,
       SUBSTR(q.sql_text, 1, 100) AS sql_text
FROM gv$session s
LEFT JOIN gv$sql q
  ON q.inst_id = s.inst_id
 AND q.sql_id = s.sql_id
 AND q.child_number = s.sql_child_number
WHERE s.type = 'USER'
  AND s.status = 'ACTIVE'
ORDER BY s.inst_id, s.last_call_et DESC;
~~~

For blockers:

~~~sql
SELECT w.inst_id AS waiting_inst_id,
       w.sid AS waiting_sid,
       w.serial# AS waiting_serial,
       w.event,
       w.blocking_instance,
       w.blocking_session,
       b.serial# AS blocker_serial,
       b.username AS blocker_username,
       b.sql_id AS blocker_sql_id
FROM gv$session w
LEFT JOIN gv$session b
  ON b.inst_id = w.blocking_instance
 AND b.sid = w.blocking_session
WHERE w.blocking_session_status = 'VALID';
~~~

Never join GV$SESSION on SID alone; always include INST_ID. Similarly, when computing deltas on GV$SYSSTAT or GV$SQLSTATS, partition by INST_ID.

## 16. Multitenant: Preserving CON_ID When Aggregating

If querying from the CDB root, views may return data across multiple containers. To gather statistics for a single PDB, filter by CON_ID or query within the target container according to privileges and intended scope.

Example:

~~~sql
SELECT con_id,
       sql_id,
       executions,
       buffer_gets,
       cpu_time,
       elapsed_time,
       SUBSTR(sql_text, 1, 100) AS sql_text
FROM v$sqlstats
WHERE con_id = :p_con_id
ORDER BY elapsed_time DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Do not merge SQL_IDs with identical text from different PDBs if the goal is per-tenant measurement. Keep CON_ID and, if needed, CON_DBID in snapshot tables.

## 17. Combining V$SESSION, V$SQL, and V$SQLSTATS in a Diagnostic Workflow

A common workflow:

1. Use V$SESSION to identify ACTIVE sessions, what event they are waiting on, whether there is a blocker, and what the current SQL_ID is.
2. Join SQL_ID + SQL_CHILD_NUMBER to V$SQL to inspect the child cursor, plan hash, and execution statistics.
3. Use V$SQLSTATS to rank SQL by total elapsed time, CPU, buffer gets, or average per execution.
4. Use V$SESSTAT/V$SESS_TIME_MODEL to understand a session's resource consumption over a time interval.
5. Use V$SYSSTAT/V$SYS_TIME_MODEL to see how instance-wide counters are growing.
6. Take snapshots at two points in time, compute deltas/rates, and compare under similar workload conditions.
7. Once notable SQL is identified, use DBMS_XPLAN.DISPLAY_CURSOR to read the execution plan and runtime row-source statistics.

### 17.1 Example: A Slow Session

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.sql_id,
       s.sql_child_number,
       s.sql_exec_start,
       s.last_call_et,
       s.event,
       s.wait_class,
       s.state,
       s.blocking_session_status,
       s.blocking_session,
       q.plan_hash_value,
       q.executions,
       q.buffer_gets,
       q.disk_reads,
       ROUND(q.cpu_time / 1000000, 2) AS cpu_seconds,
       ROUND(q.elapsed_time / 1000000, 2) AS elapsed_db_seconds,
       q.sql_text
FROM v$session s
LEFT JOIN v$sql q
  ON q.sql_id = s.sql_id
 AND q.child_number = s.sql_child_number
WHERE s.sid = :p_sid;
~~~

Read the wait event and blocker first. Then inspect the cursor and plan. If the session is running PL/SQL, SQL_ID may be a SQL statement inside PL/SQL; check PLSQL_ENTRY_OBJECT_ID and MODULE/ACTION as well.

### 17.2 Example: Finding High Cumulative Cost SQL

~~~sql
SELECT sql_id,
       executions,
       ROUND(elapsed_time / 1000000, 2) AS db_seconds,
       ROUND(cpu_time / 1000000, 2) AS cpu_seconds,
       ROUND(buffer_gets / NULLIF(executions, 0), 2)
           AS avg_gets_per_exec,
       ROUND(elapsed_time / NULLIF(executions, 0) / 1000, 2)
           AS avg_db_ms,
       plan_hash_value,
       last_active_time,
       SUBSTR(sql_text, 1, 120) AS sql_text
FROM v$sqlstats
WHERE executions > 0
ORDER BY elapsed_time DESC
FETCH FIRST 30 ROWS ONLY;
~~~

Select the SQL_ID to investigate, then inspect all child cursors using V$SQL.

### 17.3 Example: Comparing a Session Before and After a Workload

Before the workload, record the values in V$SESSTAT and V$SESS_TIME_MODEL for the target SID/SERIAL#. Run the workload, then read the same statistics again.

Example of reading the time model:

~~~sql
SELECT stat_name,
       value / 1000000 AS seconds
FROM v$sess_time_model
WHERE sid = :p_sid
  AND stat_name IN ('DB time', 'DB CPU');
~~~

Capture both readings and compute deltas for DB time and DB CPU. If delta DB time is much larger than DB CPU, check V$SESSION_EVENT or V$SESSION to identify the relevant wait classes/events.

## 18. Common Misconceptions

| Misconception | Reality |
|---|---|
| STATUS = ACTIVE means using CPU | An ACTIVE session may be waiting on a wait event |
| LAST_CALL_ET is session age | It is the time spent in the current ACTIVE/INACTIVE state |
| SQL_ID identifies one execution | SQL_ID identifies the SQL statement; executions also have SQL_EXEC_START/SQL_EXEC_ID |
| V$SQL has one row per SQL_ID | V$SQL has one row per child cursor |
| V$SQLSTATS has one row per child cursor | V$SQLSTATS has one row per unique SQL_ID |
| ELAPSED_TIME is wall-clock duration | For parallel SQL, this is the sum of coordinator and workers' DB time |
| PARSE_CALLS equals hard parses | Parse calls include soft parses; inspect `parse count (hard)` separately |
| END_OF_FETCH_COUNT equals EXECUTIONS | Incomplete fetches may not increment END_OF_FETCH_COUNT |
| BUFFER_GETS means physical reads | BUFFER_GETS means logical buffer gets |
| DISK_READS is the same as PHYSICAL_READ_REQUESTS | Physical read requests may be served from flash cache; the columns measure different things |
| V$SQLSTATS is permanent history | Retention is better than V$SQL, but it is still dynamic performance data, not a replacement for a historical repository |
| VALUE in V$SESSTAT always uses the same unit | Units depend on the specific statistic |
| STATISTIC# is stable across releases | Use NAME from V$STATNAME instead of hard-coding statistic numbers |
| Any two snapshots can be subtracted | Only subtract when sharing the same instance/session/cursor and counter lifecycle |
| SID alone identifies a session in RAC | Must preserve INST_ID; also need SERIAL# to distinguish session reuse |

## 19. Common Mistakes When Writing Monitoring Queries

| Issue | Cause | Resolution |
|---|---|---|
| One session appears multiple times when joining V$SQL | Joined only on SQL_ID without child number | Join on SQL_ID + SQL_CHILD_NUMBER |
| Blocker not found | BLOCKING_SESSION_STATUS is not VALID or blocker has ended | Check status and re-snapshot |
| Negative delta | Instance restart, session reuse, cursor reload, or counter reset | Check STARTUP_TIME, SID/SERIAL#, child cursor, and plan |
| Total elapsed exceeds wall-clock time | Parallel execution sums workers' DB time | Distinguish database time from wall-clock time |
| SQL has many executions but low END_OF_FETCH_COUNT | Application fetches partially or errors before full fetch | Inspect client fetch behavior and ROWS_PROCESSED |
| SQL_ID missing from V$SQL | Cursor aged out of shared pool | Try V$SQLSTATS; use historical sources if configured |
| Top SQL shifts between two reads | Cumulative counters keep growing or new cursors appear | Take snapshots and compute deltas over the same interval |
| Summing GV$ into an incorrect total | Merging instances or containers | Preserve INST_ID and CON_ID |
| Wait time does not match elapsed time | Wait categories have specific semantics and do not cover all time | Read wait events/time model and avoid mechanical addition |
| Monitoring queries cause overhead | Excessive polling, scanning entire V$ views | Select only needed columns, filter by SQL_ID/SID, and reduce frequency |

## 20. Notes on Historical Data and Licensing

V$SESSION, V$SQL, V$SQLSTATS, V$SESSTAT, and V$SYSSTAT primarily serve runtime observation. If historical analysis over hours or days is required, you need an appropriate snapshot mechanism or repository.

Common sources include:

- Custom monitoring tables created by the application/DBA to store periodic snapshots.
- Automatic Workload Repository (AWR) and DBA_HIST_SQLSTAT for historical SQL statistics.
- Active Session History (ASH) for analyzing sampled historical activity/waits.
- SQL Monitor and DBMS_SQL_MONITOR for certain long-running or parallel executions.

Some historical and monitoring features belong to the Oracle Diagnostics Pack or Tuning Pack. Before using AWR, ASH, SQL Monitor, or related reports in production, verify your environment's entitlements and licensing. Do not assume that being able to query a view means the organization is licensed to use all related features.

## 21. Checklist When Reading Performance Views

Before concluding that a SQL statement or session has a problem, verify:

1. Is the observation scope a session, child cursor, SQL_ID, or entire instance?
2. If on RAC, have you preserved INST_ID?
3. If on a CDB, have you filtered or separated CON_ID?
4. Is the session STATUS ACTIVE, and is it on CPU or waiting on an event?
5. Are SQL_ID and SQL_CHILD_NUMBER joined accurately to V$SQL?
6. Are there multiple child cursors or differing plan hashes?
7. Do EXECUTIONS and END_OF_FETCH_COUNT differ significantly?
8. Is PARSE_CALLS being confused with hard parses?
9. Have CPU_TIME and ELAPSED_TIME been converted properly from microseconds?
10. Does parallel execution cause elapsed database time to exceed wall-clock time?
11. Is BUFFER_GETS being confused with physical reads?
12. Is the counter cumulative or a delta?
13. Do the two snapshots belong to the same session/cursor/instance/container?
14. Did an instance restart, session reuse, or cursor reload occur between snapshots?
15. Have you calculated average per execution and rate per second where needed?
16. Did you use V$SQLSTATS for overview and V$SQL for child cursor analysis?
17. Have you checked wait classes/events and the blocker chain?
18. Have you checked historical sources/licensing if long-term analysis is needed?

## 22. Summary

To read Oracle performance accurately:

- **V$SESSION** shows which sessions are active, current SQL, wait events, module/action, and blockers. ACTIVE does not automatically mean consuming CPU.
- **V$SQL** provides statistics per child cursor, useful for comparing child numbers, plan hashes, bind sensitivity, and counters.
- **V$SQLSTATS** provides one row per SQL_ID, is faster, and offers better retention than V$SQL; suited for finding high total resource-consuming SQL.
- **V$SESSTAT** and **V$SYSSTAT** are session-level and instance-level counters. Join V$STATNAME by NAME rather than hard-coding STATISTIC#.
- **V$SESS_TIME_MODEL** and **V$SYS_TIME_MODEL** help analyze DB time and DB CPU in microseconds.
- Counters such as executions, buffer gets, CPU time, and elapsed time typically accumulate over the session/cursor/instance lifecycle. To measure an interval, take two snapshots and calculate the delta.
- When computing deltas, preserve INST_ID, CON_ID, SID/SERIAL#, SQL_ID/CHILD_NUMBER, and plan hash; check for resets/reloads before interpreting.
- Always distinguish cumulative total resources, average cost per execution, growth rate per second, and actual wall-clock wait time experienced by users.

A sound diagnostic workflow starts from V$SESSION to identify current activity, uses V$SQL/V$SQLSTATS to locate resource-intensive SQL, and then uses cumulative counters and snapshot deltas to determine whether the issue is growing within the observation window.

## 23. Oracle Reference Documentation

- Oracle Database 19c Database Reference, “V$SESSION”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html
- Oracle Database 19c Database Reference, “V$SQL”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL.html
- Oracle Database 19c Database Reference, “V$SQLSTATS”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQLSTATS.html
- Oracle Database 19c Database Reference, “V$SESSTAT”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSTAT.html
- Oracle Database 19c Database Reference, “V$SYSSTAT”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SYSSTAT.html
- Oracle Database 19c Database Reference, “V$STATNAME”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-STATNAME.html
- Oracle Database 19c Database Reference, “V$SESS_TIME_MODEL”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESS_TIME_MODEL.html
- Oracle Database 19c Database Reference, “V$SYS_TIME_MODEL”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SYS_TIME_MODEL.html
- Oracle Database 19c Database Reference, “Displaying Statistics”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/displaying-statistics.html
- Oracle Database 19c Database Reference, “Statistics Descriptions”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/statistics-descriptions-2.html
- Oracle Database 19c SQL Tuning Guide, “Monitoring Database Operations”: https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/monitoring-database-operations.html
