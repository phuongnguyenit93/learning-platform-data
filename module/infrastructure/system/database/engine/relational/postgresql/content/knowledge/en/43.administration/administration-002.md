# Inspecting Sessions, Transactions, and Background Tasks in PostgreSQL

PostgreSQL administration often begins with the question: **which processes are currently connected to the server, what are they doing, which transactions are still open, and which background tasks are running?** The answers lie in system views, especially **pg_stat_activity**, combined with lock views, transaction catalogs, progress views, and statistics for replication, WAL, autovacuum, and checkpoints.

Three concepts must be distinguished:

- **Session** is the connection/working session between a client and a PostgreSQL backend. A session can run many statements throughout its lifetime.
- **Transaction** is a unit of work bounded by BEGIN/COMMIT/ROLLBACK. A session may have a running transaction, an open but idle transaction, or no transaction.
- **Background task/process** is a process created by PostgreSQL or an external tool to perform work such as autovacuum, checkpointing, WAL writing, replication, parallel queries, or scheduled jobs.

A session may be in an idle state while still holding an open transaction. A query may be active while actually waiting on a lock or I/O. A transaction that has been PREPAREd may still exist after the original session disconnects. Therefore, inspecting sessions is only the first step; state, timestamps, wait events, locks, and backend type must be read together.

~~~text
                     PostgreSQL server
                            |
              +-------------+-------------+
              |             |             |
              v             v             v
          Client          Transaction   Background
          sessions        state         processes
              |             |             |
              v             v             v
       pg_stat_activity  xact_start   backend_type
              |             |             |
              +-------------+-------------+
                            |
              +-------------+-------------+
              |             |             |
              v             v             v
           Locks         Progress       Replication /
         pg_locks       pg_stat_progress  WAL / vacuum
              |             |             |
              +-------------+-------------+
                            |
                            v
                 Diagnosis and safe action
~~~

This lesson belongs to the **Database Engine Relational PostgreSQL** module, **Administration** chapter, on the topic **“Inspecting Sessions, Transactions, and Background Tasks”**. The content progresses from reading pg_stat_activity to analyzing transaction age, lock blockers, prepared transactions, background workers, progress views, monitoring privileges, and safe administrative actions.

---

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between a session, backend process, statement, and transaction.
2. Explain the role of pg_stat_activity.
3. Read the columns PID, user, database, application_name, client_addr, and backend_type.
4. Distinguish active, idle, idle in transaction, and idle in transaction (aborted).
5. Distinguish query_start, xact_start, backend_start, and state_change.
6. Find sessions running long queries.
7. Find long-open transactions even when the session is idle.
8. Read wait_event_type and wait_event.
9. Find blocked sessions and blocking sessions using pg_blocking_pids.
10. Use pg_locks to investigate lock modes and lock ownership.
11. Recognize transactions holding snapshots and their impact on vacuum.
12. Inspect prepared transactions no longer attached to a connected session.
13. Distinguish client backends from autovacuum, checkpointer, WAL, and replication workers.
14. Monitor vacuum, CREATE INDEX, COPY, and base backups using progress views.
15. Inspect replication sender/receiver and logical replication workers.
16. Recognize scheduled jobs running inside PostgreSQL versus jobs running outside the database.
17. Understand the limits of statistics snapshots and query text visibility.
18. Grant monitoring privileges following the least privilege principle.
19. Distinguish pg_cancel_backend from pg_terminate_backend.
20. Build an investigation procedure for sessions/transactions before intervening.
21. Monitor connection pools, long-running transactions, and backend capacity.
22. Design session administration dashboards and runbooks.
23. Practice finding blockers, observing background work, and handling sessions in a lab.
24. Avoid accidentally terminating critical sessions or interrupting maintenance tasks.

**Scope:** Modern PostgreSQL. Certain columns such as backend_type, leader_pid, query_id, and progress/statistics views depend on the major version. Before deploying monitoring queries across multiple versions, inspect the actual server schema. Cancel/terminate operations in this lesson are performed only on verified sessions and in accordance with operational permissions.

---

## 2. Session, Backend, Statement, and Transaction

These four concepts are related but not synonymous.

### 2.1. Session

A session is a client's connection session to PostgreSQL. In a typical configuration, one client connection is served by one backend process. A session exists from successful connection until disconnect or termination.

A session can:
- Wait for the client to send a query.
- Execute a statement.
- Wait on a lock or I/O.
- Be inside a transaction.
- Be idle after completing a transaction.
- Be disconnected due to network issues, timeouts, or administrative actions.

### 2.2. Backend Process

A backend is a PostgreSQL process performing work for a session or an internal task. PostgreSQL also has processes that do not represent client sessions, such as the checkpointer, background writer, WAL writer, and autovacuum launcher and workers.

In pg_stat_activity, process types can be distinguished via backend_type on supported versions.

### 2.3. Statement/Query

A statement is an SQL command sent for execution. A session can run many statements. When state is active, query is usually the currently executing statement. When a session is idle, query may still hold the last statement executed; do not mistake it for a currently executing query.

### 2.4. Transaction

A transaction consists of one or more statements and ends with COMMIT or ROLLBACK. A session can hold a transaction open even when it is not running a query at the moment of the snapshot.

Example:

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

-- Client pauses, has not yet issued COMMIT or ROLLBACK.
~~~

During this pause, the session may have state `idle in transaction`, yet the transaction remains open and may hold locks or a snapshot.

### 2.5. A Session Can Have Multiple States Over Time

~~~text
CONNECT
   |
   v
idle
   |
   v
active query
   |
   +----> idle
   |
   +----> transaction open
               |
               +----> active query
               |
               +----> idle in transaction
               |
               +----> COMMIT / ROLLBACK
                            |
                            v
                           idle
   |
   v
DISCONNECT
~~~

### 2.6. Why Separate These Concepts?

- A long-running query may be an execution or wait issue.
- A long-open transaction can cause vacuum lag even after the current query has finished.
- An idle session does not necessarily consume CPU, but idle in transaction can hold locks/snapshots.
- A background worker can be active without any corresponding client query.

---

## 3. pg_stat_activity: The Starting Point for Session Inspection

pg_stat_activity provides one row per server process, containing connection information, state, query, and wait event.

~~~sql
SELECT *
FROM pg_catalog.pg_stat_activity;
~~~

This is a quick way to explore the schema on the server. For long-term dashboards or runbooks, explicitly select the required columns rather than relying on SELECT *, because the schema can change across major versions.

### 3.1. Commonly Used Columns

| Column | Meaning |
| --- | --- |
| pid | Process ID of the backend/process |
| leader_pid | PID of the parallel group leader on supported versions |
| backend_type | Backend/process type on supported versions |
| datname | Connected database |
| usename | Session role/user |
| application_name | Application name sent in the connection |
| client_addr | Client address; may be NULL for internal processes or Unix sockets |
| client_port | Client port if applicable |
| backend_start | Timestamp when the backend started |
| xact_start | Timestamp when the current transaction started |
| query_start | Timestamp when the current query started if active |
| state_change | Timestamp of the most recent state change |
| state | Session/process state |
| wait_event_type | Category of event being waited on |
| wait_event | Specific event being waited on |
| backend_xid | Transaction ID assigned to the backend, if any |
| backend_xmin | Oldest xmin snapshot held by the backend, if any |
| query_id | Query identifier on supported versions/configurations |
| query | Current query text or most recent query depending on state |

### 3.2. PID Is Not a Durable Identifier

A PID can be reused after a process terminates. When logging an incident or preparing to terminate, also record backend_start, user, database, application_name, and a query sample to avoid targeting the wrong session.

### 3.3. application_name Is Very Useful

Setting application_name by service or job role helps distinguish:
- API service.
- Background worker.
- Migration tool.
- Reporting service.
- Admin console.
- Replication client.

Do not put a unique UUID/request ID into application_name if doing so causes monitoring cardinality to grow uncontrollably.

### 3.4. client_addr Can Be NULL

Internal processes, Unix-domain sockets, or certain special connections may not have a TCP client address. NULL does not automatically mean the session is broken.

### 3.5. Query Text May Be Restricted by Privileges

Regular users see the full queries of their own sessions. To see query text and full details of other sessions, appropriate monitoring privileges such as pg_read_all_stats/pg_monitor or superuser are required depending on the version.

---

## 4. Listing Sessions by Database and State

### 4.1. Counting Sessions by State

~~~sql
SELECT
    state,
    count(*) AS sessions
FROM pg_catalog.pg_stat_activity
GROUP BY state
ORDER BY sessions DESC NULLS LAST;
~~~

The result shows how many sessions are active, idle, or idle in transaction.

### 4.2. Counting by Database, User, and Application

~~~sql
SELECT
    datname,
    usename,
    application_name,
    state,
    count(*) AS sessions
FROM pg_catalog.pg_stat_activity
GROUP BY datname, usename, application_name, state
ORDER BY sessions DESC NULLS LAST;
~~~

### 4.3. Viewing Client Sessions

~~~sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    client_addr,
    client_port,
    backend_start,
    state,
    state_change
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'client backend'
ORDER BY backend_start;
~~~

If the server version does not have backend_type, omit this condition or use the appropriate schema.

### 4.4. Viewing Sessions by application_name

~~~sql
SELECT
    application_name,
    count(*) AS total_sessions,
    count(*) FILTER (WHERE state = 'active') AS active_sessions,
    count(*) FILTER (WHERE state = 'idle') AS idle_sessions,
    count(*) FILTER (
        WHERE state LIKE 'idle in transaction%'
    ) AS idle_in_transaction_sessions
FROM pg_catalog.pg_stat_activity
GROUP BY application_name
ORDER BY total_sessions DESC;
~~~

### 4.5. Do Not Confuse Session Count with Throughput

An idle session can stay open for hours. Session count indicates connection usage, not queries/transactions per second.

---

## 5. Understanding Session States

Common states in pg_stat_activity:

| State | Meaning | Notes |
| --- | --- | --- |
| active | Backend is executing a query | May be burning CPU or waiting on a wait event |
| idle | Waiting for client to send a new query | Usually normal with connection pools |
| idle in transaction | Transaction is open but no query is running | May hold locks/snapshot |
| idle in transaction (aborted) | Transaction errored but has not been rolled back/cleaned up | Client must ROLLBACK or close the session |
| fastpath function call | Executing a fast-path function call on supported versions | Usually a brief state |
| disabled | Statistics state tracking is disabled per configuration/version | Check setting |

### 5.1. active Does Not Mean Using CPU

A backend with state active and wait_event_type='Lock' is running a query but waiting on a lock. An active backend can be waiting on IO, Client, LWLock, or IPC.

### 5.2. idle Is Usually Not a Problem

Connection pools normally keep several idle sessions for reuse. A high idle session count alone is not enough to conclude there is a leak.

### 5.3. idle in transaction Requires Attention

The session ran BEGIN and has not issued COMMIT/ROLLBACK. It can:
- Hold row/table locks.
- Hold an old snapshot.
- Prevent vacuum from removing dead tuples.
- Increase bloat.
- Block other sessions.

### 5.4. idle in transaction (aborted)

A statement inside the transaction failed, such as a constraint violation. The transaction is in an aborted state, but the session remains open. Subsequent statements will fail until the client rolls back.

### 5.5. state and Wait Event Are Two Different Dimensions

State describes whether the backend is active or idle. Wait event describes what the backend is waiting for. Read both to understand the situation.

---

## 6. Inspecting Long-Running Queries

### 6.1. List of Active Queries

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    clock_timestamp() - query_start AS query_age,
    clock_timestamp() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    left(query, 300) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE state = 'active'
  AND pid <> pg_backend_pid()
ORDER BY query_start NULLS LAST;
~~~

### 6.2. Filtering Queries Exceeding a Threshold

~~~sql
SELECT
    pid,
    application_name,
    usename,
    datname,
    clock_timestamp() - query_start AS query_age,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE state = 'active'
  AND query_start < clock_timestamp() - interval '30 seconds'
ORDER BY query_start;
~~~

30 seconds is only an example. The appropriate threshold depends on workload and SLOs.

### 6.3. Query Age Differs from Transaction Age

A transaction can run multiple queries. The last query may take only 10 ms while the transaction has been open for 30 minutes. Therefore, inspect both query_start and xact_start.

### 6.4. query_start When a Session Is Idle

If state is not active, query_start may represent when the most recent query started, not a currently running query. Do not use query_age to alert on idle sessions as if they were active queries.

### 6.5. Query Text May Be Truncated

track_activity_query_size determines how much query text is retained in the activity view. Very long queries may appear only partially. Do not assume query samples are always complete.

---

## 7. Inspecting Long-Open Transactions

Transaction age is often more important than query age when investigating vacuum, locks, and connection leaks.

### 7.1. Finding Open Transactions

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    state,
    clock_timestamp() - xact_start AS transaction_age,
    clock_timestamp() - query_start AS query_age,
    backend_xid,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

### 7.2. Finding Long Idle Transactions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    datname,
    client_addr,
    clock_timestamp() - xact_start AS transaction_age,
    clock_timestamp() - state_change AS idle_age,
    backend_xmin,
    left(query, 200) AS last_query
FROM pg_catalog.pg_stat_activity
WHERE state LIKE 'idle in transaction%'
ORDER BY xact_start;
~~~

### 7.3. Why Are Long-Open Transactions Dangerous?

- Row/table locks may be held until COMMIT/ROLLBACK.
- Old snapshots can retain dead tuples.
- Autovacuum may not be able to reclaim row versions still visible to that snapshot.
- Transaction ID age can grow.
- The connection pool loses a usable connection.
- Other queries may wait on a blocker.

### 7.4. backend_xmin

backend_xmin reflects the xmin horizon held by the backend, when present. An old xmin can block vacuum cleanup. Not every session with a large transaction age holds an xmin in the same way; inspect the actual state and snapshot.

### 7.5. Read-Only Transactions Can Still Affect Vacuum

A long SELECT transaction can hold an old snapshot, preventing dead tuples from being removed. It is not only write transactions that cause vacuum retention.

### 7.6. Checking Oldest xmin

You can observe the age of backend xmin values:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    age(backend_xmin) AS xmin_age,
    clock_timestamp() - xact_start AS transaction_age,
    left(query, 160) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE backend_xmin IS NOT NULL
ORDER BY age(backend_xmin) DESC;
~~~

This is an investigative signal, not a single metric on which to decide termination.

---

## 8. Distinguishing Query Age, Transaction Age, and Session Age

| Age | Calculation | Question |
| --- | --- | --- |
| Query age | current time - query_start | How long has the current query been running? |
| Transaction age | current time - xact_start | How long has the transaction been open? |
| Session age | current time - backend_start | How long has the connection existed? |
| State age | current time - state_change | How long has the session been in its current state? |

### 8.1. Example

A session was created 4 hours ago, started a transaction 20 minutes ago, ran its last query 19 minutes ago, and has been idle in transaction for 18 minutes.

- Session age: 4 hours.
- Transaction age: 20 minutes.
- Query age: not an active query age; it is the timestamp of the most recent query.
- State age: 18 minutes.

### 8.2. Use clock_timestamp in Monitoring Queries

now()/transaction_timestamp() is fixed at the start of the transaction. Inside a long-running monitoring transaction, expressions like now() - query_start do not continue advancing. clock_timestamp() returns the current wall-clock time when the function is called, making it better suited for snapshot age.

### 8.3. Do Not Compare Timestamps with Different Meanings

backend_start measures connection age, query_start measures the query, and xact_start measures the transaction. Alerts must pick the right timestamp for the failure mode.

---

## 9. Wait Events: What Is the Session Waiting On?

The wait_event_type and wait_event columns help distinguish CPU-consuming queries from queries waiting on a resource.

### 9.1. Selected Wait Event Types

| Wait event type | General meaning | Investigation example |
| --- | --- | --- |
| Lock | Waiting on a heavyweight lock | Find blocking PID |
| LWLock | Waiting on an internal lightweight lock | Investigate contention in shared structures |
| IO | Waiting on I/O | Check storage latency/queue |
| Client | Waiting on client to send/receive data | Slow-reading client or held connection |
| IPC | Waiting on inter-process coordination | Parallel query or background process |
| BufferPin | Waiting for a buffer pin to be released | Long-held buffer by a query/scan |
| Activity | Waiting on an internal activity | Background worker coordination |
| Timeout | Waiting on a timer | Timeout/retry logic |
| Extension | Waiting on an extension-provided event | Inspect the specific extension |

The exact set of wait events depends on version and workload.

### 9.2. Counting Sessions by Wait Events

~~~sql
SELECT
    state,
    wait_event_type,
    wait_event,
    count(*) AS sessions
FROM pg_catalog.pg_stat_activity
WHERE wait_event IS NOT NULL
GROUP BY state, wait_event_type, wait_event
ORDER BY sessions DESC;
~~~

### 9.3. Active Yet Waiting

A query with state = 'active' and wait_event_type = 'Lock' is still an active query, but it is waiting on a lock. Counting active sessions as CPU-running sessions is misleading.

### 9.4. Waiting on Client

A backend can wait for the client to read results or send data. If the application reads slowly, the server process may be held for a long time even though database execution is nearly complete.

### 9.5. Wait Events Are Snapshots

Monitoring queries only observe the state at snapshot time. Short waits may not appear within a poll interval; use logs, tracing, or appropriate sampling when short events must be captured.

---

## 10. Finding Blocked Sessions and Blocking Sessions

### 10.1. Using pg_blocking_pids

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.usename AS blocked_user,
    blocked.application_name AS blocked_application,
    clock_timestamp() - blocked.query_start AS blocked_query_age,
    blocked.wait_event_type,
    blocked.wait_event,
    blocker.pid AS blocking_pid,
    blocker.usename AS blocking_user,
    blocker.application_name AS blocking_application,
    blocker.state AS blocking_state,
    clock_timestamp() - blocker.xact_start AS blocking_xact_age,
    left(blocked.query, 180) AS blocked_query,
    left(blocker.query, 180) AS blocking_query
FROM pg_catalog.pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(
    pg_catalog.pg_blocking_pids(blocked.pid)
) AS blocker_pid(pid)
JOIN pg_catalog.pg_stat_activity AS blocker
    ON blocker.pid = blocker_pid.pid
WHERE blocked.wait_event_type = 'Lock'
ORDER BY blocked.query_start;
~~~

### 10.2. Why Can a Blocker Be Idle?

A transaction may have executed an UPDATE and then entered idle in transaction while still holding a row lock. Other sessions wait on the lock while the blocker is running no query at that moment.

### 10.3. A Blocker Can Block Many Sessions

One blocking transaction can cause a cascade of blocked sessions. Prioritize finding the root blocker instead of handling individual waiters.

### 10.4. pg_blocking_pids

This function returns the PIDs of sessions currently blocking the specified backend. It is usually a convenient way to identify direct blockers without manually inferring the entire lock graph.

### 10.5. Prepared Transactions

Prepared transactions do not have an active backend PID like a normal session. If a lock is held by a prepared transaction, inspect pg_prepared_xacts and pg_locks to determine the cause.

---

## 11. Inspecting Locks with pg_locks

pg_locks displays the locks currently held or awaited by PostgreSQL.

~~~sql
SELECT
    l.pid,
    a.usename,
    a.application_name,
    a.state,
    l.locktype,
    l.mode,
    l.granted,
    l.relation,
    CASE
        WHEN l.relation IS NOT NULL
        THEN l.relation::regclass::text
    END AS relation_name,
    l.transactionid,
    l.virtualxid
FROM pg_catalog.pg_locks AS l
LEFT JOIN pg_catalog.pg_stat_activity AS a
    ON a.pid = l.pid
ORDER BY l.granted, l.pid;
~~~

### 11.1. granted

- true: the lock has been granted.
- false: the backend is waiting for the lock.

### 11.2. mode

Lock mode indicates conflict/concurrency level. Not all locks are table locks; there are row-level, transaction ID, virtual transaction, and other internal locks.

### 11.3. relation

When a lock is associated with a relation, you can cast the OID to regclass to display the relation name. Not every lock has a relation.

### 11.4. Row Locks

Row-level locks are typically represented via tuple metadata and transaction locks; pg_locks does not necessarily list a simple row-level lock as a separate row for each locked tuple. Use pg_blocking_pids and the lock graph to investigate.

### 11.5. Complex Lock Graphs

There can be multiple waiters, multiple blockers, or deadlock cycles. A snapshot can change as transactions commit/roll back. Collect data promptly and record timestamps.

---

## 12. Deadlocks and Lock Timeouts

### 12.1. Lock Wait

A session waits on a lock because another session holds a conflicting lock. The wait can end when the blocker commits/rolls back.

### 12.2. Deadlock

A deadlock occurs when transactions form a mutual wait cycle. PostgreSQL detects deadlocks after deadlock_timeout and aborts one transaction to break the cycle.

### 12.3. Deadlock Counter

~~~sql
SELECT
    datname,
    deadlocks,
    stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname IS NOT NULL;
~~~

This is a cumulative counter; take the delta to calculate deadlocks over a time window.

### 12.4. log_lock_waits

You can enable log_lock_waits to log lock waits exceeding deadlock_timeout. Tune according to log volume and investigative needs.

### 12.5. lock_timeout

lock_timeout limits how long a statement waits for a lock before being canceled. It can be set at session/transaction/role/database scope depending on policy.

### 12.6. statement_timeout

statement_timeout limits total statement duration. It includes execution and waits, not only lock waits.

### 12.7. Choose Timeouts Intentionally

A timeout set too low can cause normal workloads to fail. A timeout set too high can allow waiters to pile up for too long. Choose based on SLOs and transaction semantics.

---

## 13. Prepared Transactions and pg_prepared_xacts

A prepared transaction is a transaction that executed PREPARE TRANSACTION in two-phase commit and is awaiting COMMIT PREPARED or ROLLBACK PREPARED.

### 13.1. The Original Session May Be Gone

After PREPARE TRANSACTION, the transaction exists independently of the original session. Therefore, no corresponding PID may be found in pg_stat_activity.

### 13.2. Inspecting Prepared Transactions

~~~sql
SELECT
    transaction,
    gid,
    prepared,
    owner,
    database
FROM pg_catalog.pg_prepared_xacts
ORDER BY prepared;
~~~

### 13.3. Why Pay Attention?

Prepared transactions can hold locks and delay vacuum cleanup. If a transaction is abandoned, it can have long-lasting effects.

### 13.4. Do Not Commit/Roll Back Arbitrarily

Decide on COMMIT PREPARED or ROLLBACK PREPARED only after checking with the transaction coordinator, distributed transaction outcome, and owner. Acting improperly can cause data inconsistency across systems.

### 13.5. Monitoring

Alert on prepared transactions lingering past a threshold. Record gid, owner, database, prepared timestamp, and escalation owner.

---

## 14. Backend Types and Background Processes

On PostgreSQL versions with backend_type, this column distinguishes client backends from internal processes.

### 14.1. Client Backend

A process serving a normal client connection.

### 14.2. Autovacuum Launcher/Worker

The launcher manages starting autovacuum workers; workers perform automatic VACUUM/ANALYZE.

### 14.3. Background Writer

Writes dirty buffers via background writing mechanisms.

### 14.4. Checkpointer

Performs checkpoints and syncs required pages.

### 14.5. WAL Writer

Writes WAL buffers down to WAL files on schedule and as conditions require.

### 14.6. WAL Sender/Receiver

WAL sender serves replication clients on the primary; WAL receiver receives WAL on the standby.

### 14.7. Parallel Workers

Workers used by parallel queries or certain parallel operations. leader_pid can be linked to the parallel group on supported versions.

### 14.8. Logical Replication Workers

Launchers and workers handling logical replication subscriptions, apply, and related operations.

### 14.9. Extension Background Workers

Extensions can register their own background workers. Name/backend type and behavior depend on the extension.

### 14.10. Viewing Processes by backend_type

~~~sql
SELECT
    backend_type,
    state,
    wait_event_type,
    wait_event,
    count(*) AS processes
FROM pg_catalog.pg_stat_activity
GROUP BY backend_type, state, wait_event_type, wait_event
ORDER BY processes DESC;
~~~

If backend_type does not exist in an older version, use available columns or inspect the pg_stat_activity schema.

---

## 15. Monitoring Autovacuum

Autovacuum reclaims dead tuples, updates planner statistics, and protects against transaction ID wraparound.

### 15.1. Finding Autovacuum Workers

~~~sql
SELECT
    pid,
    backend_type,
    datname,
    usename,
    state,
    wait_event_type,
    wait_event,
    query_start,
    left(query, 240) AS task
FROM pg_catalog.pg_stat_activity
WHERE backend_type LIKE '%autovacuum%'
ORDER BY query_start;
~~~

### 15.2. Vacuum Progress

~~~sql
SELECT *
FROM pg_catalog.pg_stat_progress_vacuum;
~~~

This view shows which phase vacuum is in and progress counters on supported versions.

### 15.3. Table Vacuum History

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_catalog.pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

### 15.4. Autovacuum Launcher vs. Worker

The launcher coordinates; workers perform the actual work. Not seeing a worker at a single point in time does not mean autovacuum is disabled.

### 15.5. Why Does Vacuum Run Slowly?

- Large table or many dead tuples.
- Slow storage I/O.
- Long-running transaction holding xmin.
- Replication slot/standby feedback affecting the cleanup horizon.
- Autovacuum cost delay and worker capacity.
- Workload continuously generating updates/deletes.

### 15.6. Do Not Terminate Autovacuum Arbitrarily

Stopping a worker can allow dead tuples to accumulate, increasing bloat and wraparound risk. Before intervening, check the table, phase, blockers, resource bottlenecks, and XID age.

---

## 16. Monitoring Checkpointer, Background Writer, and WAL Writer

### 16.1. Listing Processes

~~~sql
SELECT
    pid,
    backend_type,
    state,
    wait_event_type,
    wait_event,
    backend_start
FROM pg_catalog.pg_stat_activity
WHERE backend_type IN (
    'background writer',
    'checkpointer',
    'walwriter'
)
ORDER BY backend_type;
~~~

Exact backend_type names and the process list depend on the PostgreSQL version.

### 16.2. Checkpoint Statistics

In modern versions, check pg_stat_checkpointer if available; prior to PostgreSQL 17, many checkpoint/background writer counters resided in pg_stat_bgwriter.

~~~sql
SELECT *
FROM pg_catalog.pg_stat_checkpointer;
~~~

On versions without this view, check pg_stat_bgwriter and the corresponding catalog.

### 16.3. WAL Statistics

~~~sql
SELECT *
FROM pg_catalog.pg_stat_wal;
~~~

Monitor WAL bytes, records, full-page images, and buffer pressure according to the version schema.

### 16.4. Do Not Confuse Background Writer with Checkpointer

The background writer writes dirty buffers during background activity. The checkpointer is responsible for checkpoint consistency. Their roles differ even though both can write data pages.

### 16.5. Monitor Duration and Throughput

Combine process activity with checkpoint write/sync time, WAL generation, storage latency, and disk queue depth. Simply seeing that a process exists does not tell you whether it is bottlenecked.

---

## 17. Inspecting Replication Processes

### 17.1. Primary: WAL Senders

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_catalog.pg_stat_replication;
~~~

### 17.2. Standby: WAL Receiver

~~~sql
SELECT *
FROM pg_catalog.pg_stat_wal_receiver;
~~~

### 17.3. Replication Slots

~~~sql
SELECT *
FROM pg_catalog.pg_replication_slots;
~~~

### 17.4. Logical Replication Workers

Workers can be observed via pg_stat_activity/backend_type and views such as pg_stat_subscription and pg_stat_subscription_stats on supported versions.

~~~sql
SELECT *
FROM pg_catalog.pg_stat_subscription;
~~~

### 17.5. Distinguish Connection from Replication Health

A connected WAL sender does not by itself prove the standby has replayed up to the current WAL. Inspect sent/write/flush/replay LSNs, lag, and slot retention.

### 17.6. Cascading Replication

The primary only shows standbys connected directly to it. To see downstream workers, query the corresponding upstream standby.

---

## 18. Progress Views for Long-Running Tasks

PostgreSQL provides progress views for several operations. They show which phase a task is in and how much work has been processed.

| View | Task |
| --- | --- |
| pg_stat_progress_vacuum | VACUUM |
| pg_stat_progress_analyze | ANALYZE |
| pg_stat_progress_create_index | CREATE INDEX / REINDEX |
| pg_stat_progress_cluster | CLUSTER / certain rewrite operations |
| pg_stat_progress_copy | COPY |
| pg_stat_progress_basebackup | Base backup |

Verify names, columns, and availability per major version.

### 18.1. Vacuum

~~~sql
SELECT *
FROM pg_catalog.pg_stat_progress_vacuum;
~~~

### 18.2. CREATE INDEX

~~~sql
SELECT *
FROM pg_catalog.pg_stat_progress_create_index;
~~~

### 18.3. COPY

~~~sql
SELECT *
FROM pg_catalog.pg_stat_progress_copy;
~~~

### 18.4. Base Backup

~~~sql
SELECT *
FROM pg_catalog.pg_stat_progress_basebackup;
~~~

### 18.5. Progress Is Not an Exact ETA

Different phases can run at different speeds. The ratio of blocks processed is not necessarily linear with remaining time. Use progress movement alongside workload/resource metrics.

### 18.6. A Long Task Is Not Necessarily Stuck

An index build on a large table can run for a long time while still making progress. Check phase, progress, waits, and logs before concluding it is stuck.

---

## 19. Scheduled Jobs and Tasks Outside PostgreSQL

Not every background task is an internal PostgreSQL process.

### 19.1. pg_cron

If using pg_cron, running jobs normally create database sessions and can be seen in pg_stat_activity with a corresponding application_name. The extension also has its own catalogs such as cron.job and cron.job_run_details.

### 19.2. External Schedulers

Cron, systemd timers, Windows Task Scheduler, Kubernetes CronJobs, Airflow, or orchestration tools appear in pg_stat_activity only while the job holds an open connection to PostgreSQL. A job waiting for its schedule does not necessarily have a backend session.

### 19.3. ETL and Batch Workers

Assign meaningful application_name values, such as `etl_orders` or `nightly_maintenance`, to identify sessions. Avoid using a generic name like `psql` for all automation whenever they can be distinguished.

### 19.4. Job History

Session views only show current state. For success/failure history, consult scheduler/job history, application logs, or extension catalogs.

### 19.5. External Tasks Are Not Database Backends

A backup process may read the database via pg_basebackup or storage snapshots while the orchestration process runs outside the host. Investigation requires checking OS processes, job schedulers, and backup tool logs.

---

## 20. Finding Sessions by User, Database, or Client

### 20.1. By Database

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    clock_timestamp() - backend_start AS session_age,
    left(query, 180) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE datname = 'appdb'
ORDER BY backend_start;
~~~

### 20.2. By User

~~~sql
SELECT
    pid,
    datname,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - xact_start AS transaction_age
FROM pg_catalog.pg_stat_activity
WHERE usename = 'app_user'
ORDER BY xact_start NULLS LAST;
~~~

### 20.3. By Client IP

~~~sql
SELECT
    client_addr,
    application_name,
    usename,
    state,
    count(*) AS sessions
FROM pg_catalog.pg_stat_activity
WHERE client_addr IS NOT NULL
GROUP BY client_addr, application_name, usename, state
ORDER BY sessions DESC;
~~~

### 20.4. Finding Connections Without application_name

~~~sql
SELECT
    pid,
    usename,
    datname,
    client_addr,
    backend_start,
    state
FROM pg_catalog.pg_stat_activity
WHERE COALESCE(application_name, '') = ''
ORDER BY backend_start;
~~~

These may be admin tools or clients that did not configure application_name. Identify the owner before requesting changes.

---

## 21. Connection Capacity and Session Pooling

### 21.1. Comparing Current Backends Against max_connections

~~~sql
SELECT
    count(*) AS current_backends
FROM pg_catalog.pg_stat_activity;
~~~

~~~sql
SHOW max_connections;
~~~

The current backend count does not necessarily equal the number of client requests being served.

### 21.2. Tracking Reserved Slots

PostgreSQL can configure reserved connection slots for superusers or appropriate roles. Account for the actual version and configuration; do not wait until all slots are exhausted before investigating.

### 21.3. Pooling

A connection pooler like PgBouncer can maintain fewer server connections than client connections. In that case, pg_stat_activity displays server-side sessions to PostgreSQL, not all client requests waiting at the pooler.

### 21.4. Pool Waiters

To understand waiting users, collect metrics from the application/pooler:
- Active/idle pool connections.
- Waiting clients.
- Acquisition latency.
- Queue timeouts.
- Server connection errors.

### 21.5. Connection Leaks

An application may open a connection and fail to return it to the pool. Symptoms can include growing session counts, long idle durations, and rising pool acquisition waits. Verify via application metrics and logs.

### 21.6. Do Not Mechanically Increase max_connections

Each backend carries memory/process overhead. Raising the limit can worsen memory pressure under high concurrency. Pool sizing/concurrency tuning usually needs to be evaluated together.

---

## 22. Statistics Snapshots and Reading Consistency

### 22.1. Activity Views vs. Cumulative Stats

pg_stat_activity reflects current process activity. Cumulative statistics views such as pg_stat_database/pg_stat_user_tables have their own snapshot/caching semantics.

### 22.2. Stats Snapshot Within a Transaction

A transaction may retain a statistics snapshot depending on stats_fetch_consistency. If queries are repeated within the same transaction, numbers may not update as expected.

### 22.3. Refreshing the Snapshot

You can use pg_stat_clear_snapshot() to clear the cached statistics snapshot in the session, depending on version semantics.

~~~sql
SELECT pg_catalog.pg_stat_clear_snapshot();
~~~

### 22.4. now() Is Fixed Within a Transaction

now() returns the transaction start timestamp. When elapsed time as of the query execution moment is needed, use clock_timestamp().

### 22.5. Poll Interval

Polling too frequently can add overhead and produce near-duplicate snapshots. Choose an interval balanced between incident detection time and monitoring load.

### 22.6. Do Not Use Polling to Replace Logs

A brief lock wait or transient process can disappear between two scrapes. Logs/progress history are needed to supplement snapshot metrics.

---

## 23. Privileges to View Sessions and Query Text

### 23.1. Default Privileges

A user can normally see full activity for their own sessions. Query text and details of other sessions may be restricted.

### 23.2. pg_monitor

The pg_monitor role is a convenient monitoring role that grants read access to many appropriate statistics and monitoring views. Evaluate its privilege scope per version.

Example grant by an administrator:

~~~sql
GRANT pg_monitor TO monitoring_user;
~~~

### 23.3. pg_read_all_stats

This role allows reading statistics for all sessions within PostgreSQL's defined scope. Do not grant broadly if only partial visibility is needed.

### 23.4. pg_signal_backend

This role allows sending signals to non-superuser backends within security boundaries. Superuser backends remain protected.

### 23.5. Least Privilege

Separate roles:
- Monitoring reader.
- Operator with appropriate cancel/terminate permissions.
- Database owner.
- Superuser/break-glass account.

Do not use superuser for a read-only dashboard if unnecessary.

### 23.6. Query Text Is Sensitive Data

Queries can contain identifiers, schema/table names, or literals. Restrict viewing access, apply masking, and set log retention according to policy.

---

## 24. Canceling Queries and Terminating Sessions

These are two distinct actions. Always verify the exact PID and owner before executing.

### 24.1. Cancel Query

~~~sql
SELECT pg_catalog.pg_cancel_backend(12345);
~~~

This function sends a cancel signal to the backend's currently running query. The session remains open.

### 24.2. Terminate Session

~~~sql
SELECT pg_catalog.pg_terminate_backend(12345);
~~~

This function sends a terminate signal to the backend. The session is closed; any open transaction rolls back as the backend exits.

### 24.3. Comparison

| Action | Result | When to Consider |
| --- | --- | --- |
| pg_cancel_backend | Cancels current query, keeps session | Query is running too long or statement needs to be stopped |
| pg_terminate_backend | Ends backend/session | Session is causing issues and connection must be closed |

### 24.4. Canceling Inside an Explicit Transaction

If a query is canceled inside an explicit transaction, the transaction may transition to the aborted state and the client must issue ROLLBACK. The session remains open.

### 24.5. Termination Can Trigger a Large Rollback

Terminating a large write transaction may require rolling back changes, generating I/O and keeping the session/locks around during rollback. Termination does not always free resources instantaneously.

### 24.6. Permissions

Typically requires being the backend owner, a member of pg_signal_backend, or superuser per PostgreSQL rules. You cannot signal a superuser-owned backend using pg_signal_backend alone.

### 24.7. Verification Procedure Before Termination

1. Capture a pg_stat_activity snapshot.
2. Record PID and backend_start.
3. Identify database, user, application_name, and client_addr.
4. Check query, transaction age, state, and wait event.
5. Find sessions blocked by this blocker.
6. Contact the owner/on-call per runbook.
7. Choose cancel or terminate.
8. Verify the outcome and side effects.

### 24.8. Do Not Terminate Using a Stale PID

PIDs can be reused after a backend exits. Re-run the session verification query immediately before signaling.

---

## 25. Timeouts Related to Sessions and Transactions

### 25.1. statement_timeout

Limits total statement duration. Useful to prevent runaway queries, but must be tuned to the workload.

### 25.2. lock_timeout

Limits how long to wait for a lock. Can be used to prevent requests from being blocked too long.

### 25.3. idle_in_transaction_session_timeout

Automatically terminates sessions remaining idle in transaction longer than the configured duration. Helps curb abandoned transactions, though setting it too low can affect legitimate applications.

### 25.4. idle_session_timeout

Can close sessions that remain idle too long on supported versions. Check pooler/client behavior to avoid unintended connection churn.

### 25.5. transaction_timeout

Some newer PostgreSQL versions support limiting total transaction duration. Check version and semantics before using.

### 25.6. Viewing Current Settings

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_catalog.pg_settings
WHERE name IN (
    'statement_timeout',
    'lock_timeout',
    'idle_in_transaction_session_timeout',
    'idle_session_timeout',
    'transaction_timeout',
    'deadlock_timeout'
)
ORDER BY name;
~~~

Columns or settings may not exist on older versions. Monitoring queries must be server-compatible.

### 25.7. Timeouts Do Not Replace Transaction Management

Timeouts help bound durations, but applications must still consistently COMMIT/ROLLBACK, close cursors, and return connections to the pool.

---

## 26. Impact of Sessions on Vacuum and Bloat

### 26.1. MVCC Retains Multiple Row Versions

PostgreSQL uses MVCC. UPDATE/DELETE create new/old row versions; VACUUM only reclaims versions no longer needed by any active snapshot.

### 26.2. Long Transactions Hold Snapshots

A long transaction can hold an old xmin, preventing VACUUM from removing dead tuples that the snapshot might still need.

### 26.3. Idle in Transaction Is an Important Signal

An idle in transaction session can hold a snapshot without running any query. This is why transaction age must be monitored, not just query duration.

### 26.4. Replication Slots and Standby Feedback

Replication slots or hot_standby_feedback can retain xmin/WAL. Investigating vacuum lag requires checking pg_stat_activity, pg_replication_slots, and standby state together.

### 26.5. Monitoring Database XID Age

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_catalog.pg_database
ORDER BY xid_age DESC;
~~~

This is a critical metric for managing transaction ID wraparound. Alert thresholds must reflect version, autovacuum policy, and cluster scale.

### 26.6. Do Not Look Only at Dead Tuples

n_dead_tup is an estimate. Combine XID age, last_autovacuum, vacuum progress, long transactions, replication horizon, and table growth.

---

## 27. Background Tasks Do Not Always Have a Client Session

### 27.1. PostgreSQL Internal Workers

These may appear in pg_stat_activity under their own backend_type. They do not necessarily have a user/application_name like client sessions.

### 27.2. Extension Background Tasks

Extensions may run background workers with custom names. Extension documentation is the source for understanding their lifecycle and intervention methods.

### 27.3. External Schedulers

Cron/systemd/Kubernetes/Airflow may open a database connection only while running. When the job is not running, no corresponding session exists.

### 27.4. OS Processes

Some tasks such as file copying, archive uploading, or backup agents run outside PostgreSQL. Check the OS process list, service manager, and logs.

### 27.5. Job History

pg_stat_activity is only a point-in-time snapshot. To see whether a job succeeded or failed, check scheduler history, application logs, or extension job catalogs.

---

## 28. Runbook: Investigating a Slow Query

### Step 1: Define Scope

Ask which query, which database, which application, when it started, and whether users are affected.

### Step 2: List Active Sessions

Use pg_stat_activity to inspect query age, wait events, user, application, and client.

### Step 3: Distinguish Execution from Waiting

If active with no wait event, inspect CPU/query plan. If wait event has a value, drill down by Lock, IO, Client, LWLock, or IPC.

### Step 4: Check Blockers

Use pg_blocking_pids and pg_locks. Identify the root blocker and the blocker's transaction age.

### Step 5: Check Query History

Use pg_stat_statements to inspect calls, total/mean execution time, rows, and buffer/temp activity.

### Step 6: Check Resources

CPU, memory, storage latency, queue depth, network, connection pool waits, and disk capacity.

### Step 7: Choose an Action

Adjust the query/index, resolve the blocker with its owner, throttle the workload, or cancel the statement. Do not terminate before understanding the transaction and its impact.

### Step 8: Verify

Monitor latency, throughput, waiters, error rate, and query progress after the change.

---

## 29. Runbook: Long-Open Transactions and Idle in Transaction

### Step 1: List Transaction Ages

Find old xact_start values, state, application_name, user, and backend_xmin.

### Step 2: Classify

- Long-running active query.
- Active query waiting on lock/I/O.
- Idle in transaction.
- Idle in transaction (aborted).
- Prepared transaction.

### Step 3: Identify the Owner

Use application_name, client_addr, user, and application logs to locate the service/job owning the connection.

### Step 4: Check Lock Impact

Find blocked sessions and locks held by the transaction.

### Step 5: Check Vacuum Impact

Correlate backend_xmin, n_dead_tup, XID age, vacuum progress, and replication horizon.

### Step 6: Contact the Owner per Policy

Prefer letting the application COMMIT/ROLLBACK properly. If intervention is necessary, evaluate cancel/terminate and rollback cost.

### Step 7: Monitor After Remediation

Confirm the session ended, blockers cleared, vacuum resumed, and the connection pool stabilized.

---

## 30. Runbook: Long-Running Background Tasks

### Step 1: Identify Backend Type

Use pg_stat_activity to distinguish autovacuum, checkpointer, background writer, replication, and client backends.

### Step 2: Find the Corresponding Progress View

- VACUUM: pg_stat_progress_vacuum.
- CREATE INDEX: pg_stat_progress_create_index.
- COPY: pg_stat_progress_copy.
- Base backup: pg_stat_progress_basebackup.

### Step 3: Check Waits and Resources

Inspect wait_event, CPU, I/O, disk, locks, and transaction blockers.

### Step 4: Check Logs

Read PostgreSQL logs or tool/scheduler logs to identify phases, retries, and failures.

### Step 5: Determine Expected Duration

Compare against table size, workload, maintenance window, and baseline. Do not assume it is stuck merely due to long duration.

### Step 6: Intervene via the Task Owner

Do not kill autovacuum, checkpoint, replication, or backup workers just to make a process disappear from a dashboard. Use the management mechanism appropriate to that task.

---

## 31. Monitoring Dashboard for Sessions and Transactions

An administrative dashboard should include the following panels.

### 31.1. Session Overview

- Total sessions.
- Active/idle/idle in transaction.
- Sessions by database/user/application.
- Backend types.
- Connection usage versus capacity.

### 31.2. Long-Running Work

- Longest active query age.
- Longest transaction age.
- Longest idle-in-transaction age.
- Active queries by wait_event_type.
- Sessions holding old backend_xmin.

### 31.3. Locks

- Number of blocked sessions.
- Root blocker PIDs.
- Lock wait age.
- Deadlocks/s.
- Lock timeout errors.

### 31.4. Background Tasks

- Autovacuum workers and progress.
- CREATE INDEX/COPY/base backup progress.
- Checkpoint/WAL activity.
- Replication sender/receiver state.
- Logical replication workers.
- Scheduled job state from the scheduler.

### 31.5. Pooling

- Application pool active/idle/waiters.
- Acquisition latency.
- Server connections.
- Queue timeouts.
- Connection creation/recycle rate.

### 31.6. Alerts with Owner and Runbook

Each alert should state database/cluster, application_name, PID/backend_start, age, wait event, blocker if any, user impact, and next inspection step. Avoid placing raw queries or user identifiers into unbounded labels.

---

## 32. Version Compatibility and Schema Discovery

PostgreSQL statistics views change across major versions. Do not assume a query written for one server will run on every server.

### 32.1. Identify the Version

~~~sql
SELECT version();
SHOW server_version;
SHOW server_version_num;
~~~

### 32.2. Discover pg_stat_activity Columns

~~~sql
SELECT
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'pg_catalog'
  AND table_name = 'pg_stat_activity'
ORDER BY ordinal_position;
~~~

### 32.3. Discover Progress Views

~~~sql
SELECT
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'pg_catalog'
  AND table_name LIKE 'pg_stat_progress_%'
ORDER BY table_name, ordinal_position;
~~~

### 32.4. Columns May Differ

backend_type, leader_pid, query_id, and progress fields depend on version. Some views do not exist on older major versions.

### 32.5. Exporters Should Be Version-Aware

Monitoring collectors need to check the server version or use compatible SQL queries. One failing query can cause a collector to drop an entire group of metrics.

### 32.6. Do Not Use SELECT * as a Long-Term Contract

SELECT * is convenient for lab exploration, but stable dashboards/runbooks should select explicit columns with version-based fallbacks.

---

## 33. Lab 1: Viewing Sessions and States

Use a lab database or development environment.

### 33.1. Open Two Connections

Open two psql terminals or two sessions from an SQL client.

### 33.2. Session A Runs a Query

~~~sql
SELECT pg_sleep(45);
~~~

### 33.3. Session B Inspects Activity

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    query_start,
    left(query, 120) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE state <> 'idle'
ORDER BY query_start;
~~~

### 33.4. Observe the State

Session A has state active while pg_sleep runs. The wait event may indicate it is waiting on a timer.

### 33.5. Finish the Query

Wait for the query to finish or cancel it from the client itself. There is no need to terminate the session to stop a routine lab query.

### 33.6. Conclusion

An active query does not necessarily consume CPU; wait events help explain why.

---

## 34. Lab 2: Observing idle in transaction

### 34.1. Create a Lab Table

~~~sql
CREATE TABLE IF NOT EXISTS public.session_lab (
    id INTEGER PRIMARY KEY,
    value INTEGER NOT NULL
);

INSERT INTO public.session_lab(id, value)
VALUES (1, 0)
ON CONFLICT (id) DO NOTHING;
~~~

### 34.2. Session A

~~~sql
BEGIN;
UPDATE public.session_lab
SET value = value + 1
WHERE id = 1;
-- Not yet committed/rolled back.
~~~

### 34.3. Session B Inspects

~~~sql
SELECT
    pid,
    state,
    clock_timestamp() - xact_start AS transaction_age,
    clock_timestamp() - state_change AS state_age,
    application_name,
    left(query, 120) AS last_query
FROM pg_catalog.pg_stat_activity
WHERE state LIKE 'idle in transaction%';
~~~

### 34.4. Session B Attempts to Update the Same Row

~~~sql
UPDATE public.session_lab
SET value = value + 1
WHERE id = 1;
~~~

Session B may wait on the row lock held by Session A.

### 34.5. Session A Rolls Back or Commits

Observe Session B proceed after the blocker finishes.

### 34.6. Conclusion

A transaction can hold a lock even when the session is not executing a query at the moment of observation.

---

## 35. Lab 3: Finding Blocked Sessions and Blockers

### 35.1. Create a Blocker/Waiter

Use two sessions and one row in the lab table. Session A runs BEGIN and UPDATE; Session B runs UPDATE on the same row.

### 35.2. Query the Blocker Graph

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocker.pid AS blocker_pid,
    blocked.wait_event_type,
    blocked.wait_event,
    blocked.application_name AS blocked_app,
    blocker.application_name AS blocker_app,
    clock_timestamp() - blocker.xact_start AS blocker_xact_age
FROM pg_catalog.pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(
    pg_catalog.pg_blocking_pids(blocked.pid)
) AS b(pid)
JOIN pg_catalog.pg_stat_activity AS blocker
    ON blocker.pid = b.pid
WHERE blocked.wait_event_type = 'Lock';
~~~

### 35.3. Inspect pg_locks

~~~sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    relation
FROM pg_catalog.pg_locks
WHERE pid IN (SELECT pid FROM pg_catalog.pg_stat_activity)
ORDER BY pid, granted;
~~~

### 35.4. Release the Blocker

COMMIT or ROLLBACK Session A and observe the waiter proceed.

### 35.5. Conclusion

Identify the root blocker before handling large numbers of waiters.

---

## 36. Lab 4: Monitoring Autovacuum and Progress

### 36.1. Create a Churn Table

~~~sql
CREATE TABLE IF NOT EXISTS public.vacuum_lab (
    id BIGINT PRIMARY KEY,
    payload TEXT NOT NULL
);

INSERT INTO public.vacuum_lab(id, payload)
SELECT g, repeat('x', 300)
FROM generate_series(1, 100000) AS g;
~~~

### 36.2. Generate Dead Tuples

~~~sql
UPDATE public.vacuum_lab
SET payload = repeat('y', 300)
WHERE id % 2 = 0;

DELETE FROM public.vacuum_lab
WHERE id % 5 = 0;
~~~

### 36.3. Run VACUUM in the Lab

~~~sql
VACUUM (ANALYZE) public.vacuum_lab;
~~~

### 36.4. Observe Progress

In another session, query pg_stat_progress_vacuum and pg_stat_activity. The task may finish quickly; increase the lab dataset size if you need longer observation.

### 36.5. Observe Table Stats

~~~sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_catalog.pg_stat_user_tables
WHERE relname = 'vacuum_lab';
~~~

### 36.6. Conclusion

Progress views describe currently running work; table stats help observe results over time.

---

## 37. Lab 5: Distinguishing Sessions from Prepared Transactions

The lab requires an appropriate max_prepared_transactions setting and a test environment. Do not enable two-phase commit in production just for practice.

### 37.1. Start a Transaction

~~~sql
BEGIN;
UPDATE public.session_lab
SET value = value + 1
WHERE id = 1;
PREPARE TRANSACTION 'session_lab_tx_1';
~~~

### 37.2. Check pg_stat_activity

The session that executed PREPARE TRANSACTION may exit its transaction session context, yet the prepared transaction still exists.

### 37.3. Check pg_prepared_xacts

~~~sql
SELECT *
FROM pg_catalog.pg_prepared_xacts
WHERE gid = 'session_lab_tx_1';
~~~

### 37.4. Complete the Prepared Transaction

In the lab, choose the appropriate coordinator outcome and run:

~~~sql
COMMIT PREPARED 'session_lab_tx_1';
~~~

Or ROLLBACK PREPARED if the scenario requires aborting.

### 37.5. Conclusion

Not every remaining transaction has a PID in pg_stat_activity. Prepared transactions require a separate catalog and a clear owner/coordinator.

---

## 38. Practice Exercises

### Exercise 1 — Concepts

Distinguish session, backend process, statement, and transaction using an example.

### Exercise 2 — pg_stat_activity

Write a query listing PID, user, database, application_name, client address, state, and wait event.

### Exercise 3 — Session State

Explain active, idle, idle in transaction, and idle in transaction (aborted).

### Exercise 4 — Query Age

Find active queries running for more than 60 seconds. Explain why query_start does not represent transaction age.

### Exercise 5 — Transaction Age

Find transactions open for more than 10 minutes, including idle sessions.

### Exercise 6 — Session Age

Write a query to find the longest-lived sessions and explain why connection age does not by itself prove a connection leak.

### Exercise 7 — Application Name

Design an application_name convention for API, ETL, migration, and reporting jobs.

### Exercise 8 — Wait Events

An active session has wait_event_type='Lock'. Explain the state and write steps to investigate the blocker.

### Exercise 9 — Blocker Graph

Write a query using pg_blocking_pids to find blocked PIDs and blocking PIDs.

### Exercise 10 — pg_locks

Explain granted, locktype, mode, and relation. Why does not every lock have a relation?

### Exercise 11 — Idle Blocker

A blocker is idle in transaction. Why can it still hold locks?

### Exercise 12 — Deadlock

Distinguish a lock wait from a deadlock. State the roles of deadlock_timeout and the deadlocks counter.

### Exercise 13 — Long Read Transaction

A long-running SELECT transaction prevents vacuum from reclaiming dead tuples. Explain MVCC snapshots and backend_xmin.

### Exercise 14 — Prepared Transaction

Why can a prepared transaction exist without a session PID in pg_stat_activity?

### Exercise 15 — Cancel

Explain pg_cancel_backend and the transaction state after a statement is canceled inside an explicit transaction.

### Exercise 16 — Terminate

Explain pg_terminate_backend and rollback impact. List the information to verify before terminating.

### Exercise 17 — Permissions

Design a monitoring role using pg_monitor or pg_read_all_stats with least privilege.

### Exercise 18 — Backend Types

Distinguish client backend, autovacuum worker, checkpointer, WAL writer, WAL sender, and parallel worker.

### Exercise 19 — Autovacuum

Write a query to find autovacuum workers and the progress of a running vacuum.

### Exercise 20 — Checkpoint

Find the checkpoint/background writer processes and list the statistics to check to understand write pressure.

### Exercise 21 — Replication

Inspect WAL senders on the primary and the WAL receiver on the standby. Why is connection state insufficient to conclude a replica is healthy?

### Exercise 22 — Logical Replication

List the workers and statistics views to inspect when a subscription is not applying changes.

### Exercise 23 — Progress Views

Match the corresponding views for VACUUM, CREATE INDEX, COPY, and base backup.

### Exercise 24 — Scheduled Jobs

Distinguish a pg_cron session from a Kubernetes CronJob waiting for its schedule. Why does pg_stat_activity not show every scheduled task?

### Exercise 25 — Connection Pool

Pool waiters are rising while database sessions are mostly idle. Propose metric sources to check.

### Exercise 26 — Connection Capacity

Compare the current backend count with max_connections. Why should max_connections not be increased immediately upon hitting the threshold?

### Exercise 27 — Timeouts

Distinguish statement_timeout, lock_timeout, and idle_in_transaction_session_timeout.

### Exercise 28 — Stats Snapshot

Explain why now() may not advance inside a long-running monitoring transaction and when to use clock_timestamp().

### Exercise 29 — Version Compatibility

Write queries to discover the columns of pg_stat_activity and progress views across different major versions.

### Exercise 30 — Stuck Background Task

A CREATE INDEX has been running for 40 minutes. Design a procedure to inspect progress, locks, wait events, I/O, and expected duration.

### Exercise 31 — Vacuum Horizon

A long transaction and a replication slot coexist. List the checks to perform before concluding the cause of vacuum lag.

### Exercise 32 — Root Blocker

One blocker is blocking 80 sessions. Build a procedure to find the owner, evaluate the transaction, and choose cancel/terminate.

### Exercise 33 — PID Reuse

Why must backend_start be checked immediately before sending a signal to a PID saved from an incident snapshot?

### Exercise 34 — Query Visibility

A monitoring user sees their own queries, but query text for other users is NULL. Explain which privileges to review.

### Exercise 35 — Transaction Rollback

A transaction that wrote millions of rows is terminated. What impacts on rollback, I/O, and lock duration should be expected?

### Exercise 36 — Autovacuum Safety

Why can terminating an autovacuum worker worsen bloat/XID risk?

### Exercise 37 — Dashboard

Design a dashboard covering session states, long transactions, wait events, blockers, prepared transactions, and background progress.

### Exercise 38 — Incident Runbook

An API is timing out, database CPU is low, 60 sessions are waiting on locks, and an idle-in-transaction session holds the blocker. Write the sequence of investigation and action.

### Exercise 39 — Two-Phase Commit

A prepared transaction has existed for several hours. List the information to gather from the coordinator before running COMMIT PREPARED or ROLLBACK PREPARED.

### Exercise 40 — End-to-End Administration

A cluster has a primary, two standbys, PgBouncer, pg_cron, and autovacuum. After a deploy, connection pool waits increase, a transaction has been idle for 25 minutes, 30 queries are waiting on locks, autovacuum is slow, and replication replay lag is rising. Design the sequence for reading views, identifying the root cause, delegating actions, handling the session, and verifying recovery.

---

## 39. Checklist for Inspecting Sessions, Transactions, and Background Tasks

| Item | What to Verify |
| --- | --- |
| PostgreSQL version | Major version and available columns |
| Session identity | PID, backend_start, user, database |
| Application identity | application_name, client_addr |
| Backend type | Client or internal worker |
| Session state | active/idle/idle in transaction/aborted |
| Query age | query_start and state |
| Transaction age | xact_start |
| Session age | backend_start |
| State age | state_change |
| Query visibility | Appropriate monitoring privileges |
| Wait event | wait_event_type and wait_event |
| Active CPU vs wait | Do not just count active state |
| Blocked sessions | pg_blocking_pids |
| Root blocker | Blocking PID and transaction age |
| Lock details | pg_locks, mode, granted |
| Deadlocks | pg_stat_database delta and logs |
| Prepared transactions | pg_prepared_xacts |
| Old snapshots | backend_xmin/xmin horizon |
| Vacuum impact | dead tuples, XID age, vacuum progress |
| Autovacuum | Launcher/worker and progress |
| Checkpointer | Process and checkpoint stats |
| WAL writer | WAL statistics |
| Replication | Sender/receiver, LSN, and sync state |
| Logical replication | Subscription workers/stats |
| Progress tasks | Vacuum/index/copy/basebackup |
| Scheduled jobs | pg_cron or scheduler history |
| External jobs | OS/Kubernetes/orchestrator logs |
| Connection pool | Active/idle/waiters/acquisition latency |
| Connection capacity | Current backends and max_connections |
| Timeout policy | statement/lock/idle transaction |
| Cancel/terminate | Owner, permission, impact, and rollback |
| PID safety | Recheck PID/backend_start before signaling |
| Post-action verification | Blockers, queries, pool, and application health |
| Audit trail | Incident time, action, operator, and result |

## Conclusion

Inspecting sessions, transactions, and background tasks in PostgreSQL requires combining pg_stat_activity with locks, prepared transactions, progress views, and specialized statistics. An active session may be waiting; an idle session may hold a transaction and a snapshot; a long-running background worker may be doing necessary work. Reading timestamps, wait events, and backend types accurately helps distinguish normal conditions from issues requiring intervention.

Key principles to remember:

1. **Session does not mean transaction.** A session can keep a transaction open without running a query.
2. **Query age differs from transaction age.** Use query_start to inspect statements and xact_start to inspect transactions.
3. **Active does not mean using CPU.** Always read wait_event_type and wait_event.
4. **Idle in transaction can have major impact.** It can hold locks, snapshots, and block vacuum.
5. **pg_blocking_pids helps find blockers.** Identify the root blocker before handling multiple waiters.
6. **pg_locks shows lock state.** Read granted, mode, locktype, and relation in proper context.
7. **Prepared transactions have their own catalog.** They can persist after the original session disappears.
8. **Background workers have dedicated duties.** Autovacuum, checkpointer, WAL, and replication are not regular client sessions.
9. **Progress views distinguish slow from stuck.** Monitor phases and progress instead of duration alone.
10. **Scheduled jobs may live outside PostgreSQL.** Use scheduler logs and application_name to correlate them.
11. **Monitoring requires proper privileges.** Use pg_monitor/pg_read_all_stats with least privilege and protect query text.
12. **Cancel differs from terminate.** Cancel stops the query; terminate closes the session and may cause a rollback.
13. **Verify PID immediately before signaling.** PIDs can be reused.
14. **Do not stop background tasks arbitrarily.** Especially autovacuum, checkpoint, backup, and replication must be handled per runbook.
15. **Verify after intervention.** Check blockers, transaction state, pool, vacuum, replication, and application health.

A sound administrative workflow starts with a snapshot containing full identifiers and timestamps, determines what the session is doing or waiting on, identifies related transactions/locks/background tasks, and only then selects the appropriate action. After every change, confirm that blockers are cleared, transactions conclude properly, and services return to a healthy state.
