# pg_stat_activity, Session States, and Running Queries in PostgreSQL

When PostgreSQL becomes slow, connection counts spike unusually, or a statement hangs, the first questions an operator usually asks are: **which sessions are currently connected, what is each session doing, and which sessions are waiting on resources?** The system view `pg_stat_activity` is the primary starting point for answering those questions.

`pg_stat_activity` provides one row per server process, including client sessions and many PostgreSQL background processes. This view shows the database, user, application, session state, current or most recent query, query/transaction start timestamps, and wait event if the process is waiting.

This view is a point-in-time snapshot of current activity. It helps observe present status, find long-running queries, detect forgotten transactions, identify lock waits, and locate applications opening too many connections. It is not a complete historical store of every statement ever executed; historical analysis requires combining logging, `pg_stat_statements`, or other observability systems.

This lesson explains how to read `pg_stat_activity`, understand session states and wait events, measure query/transaction durations, find blockers, handle sessions safely, and build monitoring queries usable in production operations.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain `pg_stat_activity` and how this view relates to PostgreSQL server processes.
2. Distinguish client backends from background workers.
3. Read the columns identifying database, user, client, application, and process.
4. Distinguish `active`, `idle`, `idle in transaction`, and `idle in transaction (aborted)`.
5. Understand `state`, `wait_event_type`, and `wait_event`.
6. Measure query age, transaction age, and how long a session has been in its current state.
7. Find long-running active statements and sessions waiting on locks.
8. Use `pg_blocking_pids` to locate blockers.
9. Distinguish an actively running query from the most recent query of an idle session.
10. Understand permission limits on viewing another user's activity.
11. Use `pg_cancel_backend` and `pg_terminate_backend` in the right situations.
12. Combine `pg_stat_activity` with `pg_locks`, `pg_stat_ssl`, `pg_stat_progress_*`, and `pg_stat_statements`.
13. Build dashboards, alerts, and troubleshooting procedures.
14. Avoid common mistakes when interpreting monitoring data.

## 2. What Is pg_stat_activity?

`pg_stat_activity` is a statistics/activity view in the `pg_catalog` system schema. Each row represents one PostgreSQL server process at the moment of observation.

~~~text
PostgreSQL server
    |
    +-- Client backend (application session)
    |
    +-- Client backend (psql session)
    |
    +-- Autovacuum worker
    |
    +-- WAL sender
    |
    +-- Background writer / checkpointer
    |
    +-- Parallel worker
    |
    +-- Other background processes
             |
             v
       pg_stat_activity
             |
             v
       Session, query, state, wait event
~~~

### 2.1. One row is not necessarily one end user

A row can represent:
- A connection from an application server.
- A connection from a connection pool.
- A `psql` or administrative tool session.
- An autovacuum worker.
- A WAL sender/receiver.
- A background worker or parallel query worker.

Therefore, do not count every row as an end user. Filter by `backend_type` or attributes appropriate for your version.

### 2.2. A view of current activity

`pg_stat_activity` shows the state PostgreSQL currently records for each process. It does not retain a separate record for every past statement.

If a session is `active`, the `query` column shows the currently executing statement. If a session is `idle`, `query` usually shows the most recent statement that session executed. Never read an idle session's `query` as though that statement were still running.

### 2.3. Inspecting the view

~~~sql
SELECT *
FROM pg_stat_activity
LIMIT 5;
~~~

In production environments, avoid blindly relying on `SELECT *` in dashboards or automation because view schemas can change across PostgreSQL major versions. Explicitly select the columns you need.

## 3. Key Columns

Commonly used columns:

| Column | Meaning |
| --- | --- |
| pid | Process ID of the server process |
| datid | OID of the database |
| datname | Name of the database |
| usesysid | OID of the user |
| usename | Name of the user |
| application_name | Client/application name supplied by the client |
| client_addr | Client IP address; NULL for some local/background processes |
| client_hostname | Client hostname if resolved |
| client_port | Client-side TCP port |
| backend_start | Timestamp when the process/session started |
| xact_start | Timestamp when the current transaction started |
| query_start | Timestamp when the current query started if active; otherwise when the most recent query started |
| state_change | Timestamp of the most recent state change |
| state | Session state |
| wait_event_type | Category of the wait event |
| wait_event | Specific wait event name |
| backend_type | Server process type, if provided by the version |
| backend_xid | Transaction ID of the current transaction, if any |
| backend_xmin | Oldest xmin held by the backend's snapshot, if any |
| query_id | Query identifier if query ID computation is enabled and available |
| query | Current or most recent statement, depending on state |
| leader_pid | PID of the parallel group leader if the process is a parallel worker |

### 3.1. PID

`pid` identifies the process across system views and is passed to cancel/terminate functions. A PID can change after reconnecting; never store a PID as a long-lived identifier for an application session.

### 3.2. Database and user

`datname` and `usename` indicate which database the session is working in and under which role. These fields may be NULL for background processes not tied to a regular database or user.

### 3.3. Application name

`application_name` helps distinguish services or components. Set clear names in the connection string or session:

~~~sql
SET application_name = 'orders-api';
~~~

Use names such as `orders-api`, `billing-worker`, `reporting-job`, or `migration-runner`. Consistent naming makes it easy to trace where connections and queries originate.

### 3.4. Client address

`client_addr` can be NULL for Unix-domain sockets, background processes, or connections without a standard IP address. Do not automatically treat NULL as an error.

### 3.5. Timestamps

`backend_start` measures session age. `xact_start` measures transaction age. `query_start` records when the current or most recent query started depending on `state`. These three timestamps answer different questions.

### 3.6. Query text

`query` can be truncated according to `track_activity_query_size`. It can also contain sensitive literal values. Restrict access to activity views and consider masking at the application or logging layer.

## 4. Basic Queries to Inspect Sessions

A useful query for inspecting client sessions:

~~~sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    backend_start,
    state_change,
    left(query, 500) AS query
FROM pg_stat_activity
WHERE backend_type = 'client backend'
ORDER BY backend_start;
~~~

`backend_type` is present in modern PostgreSQL versions; if you must support older versions, check the schema and adjust the filter.

### 4.1. Excluding the session running the monitoring query

Every time you query `pg_stat_activity`, your own administrative session also appears:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    query
FROM pg_stat_activity
WHERE pid <> pg_backend_pid();
~~~

`pg_backend_pid()` returns the PID of the current session.

### 4.2. Viewing sessions by database

~~~sql
SELECT
    datname,
    count(*) AS session_count
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname
ORDER BY session_count DESC;
~~~

### 4.3. Viewing sessions by user and application

~~~sql
SELECT
    usename,
    application_name,
    count(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY usename, application_name
ORDER BY sessions DESC;
~~~

Use this query to identify applications opening too many connections or omitting `application_name`.

## 5. Understanding Session State

The `state` column describes what a backend is doing at the session/query level.

| State | Meaning |
| --- | --- |
| active | Backend is currently executing a query |
| idle | Backend is waiting for the client to send the next query |
| idle in transaction | Backend is inside a transaction but not currently executing a query |
| idle in transaction (aborted) | Transaction has errored and is waiting for ROLLBACK/end of transaction |
| fastpath function call | Backend is executing a fast-path function call |
| disabled | Activity tracking is disabled for this backend |

Verify exact names and states against the documentation for the major version in use.

### 5.1. active

The session is executing a query. However, `active` does not mean the query is continuously burning CPU. It may be waiting on a lock, I/O, client, or another event.

To understand an active session, read `state` alongside `wait_event_type` and `wait_event`.

### 5.2. idle

The session has finished its most recent query and is waiting for the client to send a new command. With connection pools, having some idle sessions is normal.

Idle sessions still occupy connection slots and some process resources. Too many idle sessions may indicate oversized pools or an application opening unbounded connections.

### 5.3. idle in transaction

The session ran `BEGIN` or a transaction-starting statement, is not currently running a query, and has not ended the transaction. This state deserves attention because the transaction can hold locks and snapshots and prevent vacuum from removing old tuple versions.

A forgotten open transaction can cause:
- Rising table/index bloat.
- Autovacuum being unable to clean up old dead tuples.
- Other transactions getting blocked.
- `xmin` being pinned for a long time.
- Increased transaction ID pressure in severe, prolonged cases.

### 5.4. idle in transaction (aborted)

A statement inside the transaction raised an error. The transaction is in an aborted state and cannot execute normal statements until `ROLLBACK` or transaction end. The application must handle errors and close transactions properly.

### 5.5. idle is not an error

A pool keeping a few idle connections warm can be intentional by design. Compare against pool configuration, `max_connections`, workload, and connection wait time before drawing conclusions.

## 6. State and Wait Event Are Different Concepts

`state` answers whether the backend is executing a query. `wait_event_type` and `wait_event` show what kind of event the backend is waiting on.

Examples:
- `state=active`, `wait_event=NULL`: the query is active and did not report a wait event at sampling time.
- `state=active`, `wait_event_type=Lock`: the query is active but waiting for a lock.
- `state=idle`, `wait_event_type=Client`: the backend is likely waiting for the client to send the next data/command.
- `state=idle in transaction`: a transaction is open while the session is not running a statement; it may still hold locks/snapshots.

### 6.1. Wait event categories

Depending on version, `wait_event_type` can include categories such as:

| Category | General Meaning |
| --- | --- |
| Lock | Waiting for a heavyweight lock |
| LWLock | Waiting for an internal lightweight lock |
| BufferPin | Waiting for a buffer pin |
| IO | Waiting for I/O |
| Client | Waiting for client/network activity |
| Activity | Waiting for an internal activity or background process |
| IPC | Waiting for inter-process communication |
| Timeout | Waiting for a timeout |
| Extension | Waiting for an extension-defined event |

Exact lists and `wait_event` names vary by version. Check catalog documentation or look up the specific wait event in the PostgreSQL documentation.

### 6.2. An active query that is waiting

A query with `state=active` and `wait_event_type=Lock` is still classified as `active` because the statement has not completed. It is not necessarily consuming CPU.

### 6.3. Wait event NULL

NULL does not guarantee the query is fast or problem-free. It only means the backend did not report a wait event at the instant of observation.

### 6.4. ClientRead

An idle session waiting for the client to send a query typically shows a `Client` wait event such as `ClientRead`. This is usually the normal state of an idle connection awaiting commands.

## 7. Viewing Running Queries

Use the following query to list active queries:

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
    left(query, 1000) AS query
FROM pg_stat_activity
WHERE state = 'active'
  AND pid <> pg_backend_pid()
ORDER BY query_start;
~~~

### 7.1. query_age

Measures elapsed time since `query_start`. Interpret it as current query execution duration only when `state=active`.

### 7.2. transaction_age

Measures elapsed time since `xact_start`. A query that started just a few milliseconds ago can sit inside a transaction that has been open for hours.

### 7.3. Most recent query of an idle session

If `state` is not `active`, `query` is usually the most recent statement. Do not compute `clock_timestamp() - query_start` and call it query execution duration for an idle session.

### 7.4. Filtering queries longer than a threshold

Example to find queries active for more than 30 seconds:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    clock_timestamp() - query_start AS duration,
    wait_event_type,
    wait_event,
    left(query, 1000) AS query
FROM pg_stat_activity
WHERE state = 'active'
  AND query_start < clock_timestamp() - interval '30 seconds'
  AND pid <> pg_backend_pid()
ORDER BY query_start;
~~~

30 seconds is just an example threshold. Choose according to workload and SLA; a 5-minute analytical query may be normal whereas a 5-second OLTP query may warrant investigation.

## 8. Distinguishing Query Age, Transaction Age, and Session Age

These measures are frequently confused.

| Metric | Formula | Question Answered |
| --- | --- | --- |
| Session age | now - backend_start | How long has the connection/process existed? |
| Transaction age | now - xact_start | How long has the current transaction been open? |
| Query age | now - query_start when active | How long has the current statement been running? |
| State age | now - state_change | How long has the backend been in its current state? |

Example:
- Backend has existed for 3 hours.
- Transaction has been open for 45 minutes.
- Current query has been running for 2 seconds.
- Session switched to `active` 2 seconds ago.

You cannot conclude the transaction has only been open for 2 seconds based on `query_start`.

### 8.1. Complete query

~~~sql
SELECT
    pid,
    state,
    clock_timestamp() - backend_start AS session_age,
    clock_timestamp() - xact_start AS transaction_age,
    CASE
        WHEN state = 'active'
        THEN clock_timestamp() - query_start
    END AS active_query_age,
    clock_timestamp() - state_change AS state_age,
    application_name,
    left(query, 500) AS query
FROM pg_stat_activity
WHERE backend_type = 'client backend'
ORDER BY xact_start NULLS LAST, backend_start;
~~~

### 8.2. NULL xact_start

If a session is not currently in a transaction, `xact_start` may be NULL. Do not convert NULL to 0 without preserving clear semantics.

### 8.3. state_change

`state_change` indicates when `state` last changed. A session that has been `idle` for a long time does not mean its last query ran for a long time.

## 9. Finding idle-in-transaction Sessions

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    clock_timestamp() - xact_start AS transaction_age,
    clock_timestamp() - state_change AS idle_duration,
    wait_event_type,
    wait_event,
    left(query, 1000) AS last_query
FROM pg_stat_activity
WHERE state IN ('idle in transaction', 'idle in transaction (aborted)')
ORDER BY xact_start;
~~~

### 9.1. Why care?

Long-open transactions can hold row/table locks and old snapshots. This prevents vacuum from reclaiming dead tuples that those transactions could still see.

### 9.2. Last query is not a currently running query

In `idle in transaction`, `query` is usually the most recent statement. Read `state` to confirm the backend is no longer executing that statement.

### 9.3. Finding the oldest transactions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    datname,
    state,
    xact_start,
    clock_timestamp() - xact_start AS transaction_age,
    left(query, 500) AS last_or_current_query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start
LIMIT 20;
~~~

### 9.4. Application-side causes

- Opening a transaction before calling an external API.
- Forgetting `COMMIT`/`ROLLBACK` in an exception path.
- Returning a connection to the pool while a transaction is still open.
- An interactive client holding a transaction open while a user thinks.
- A batch job processing items piecemeal without closing the transaction.
- Code calling `BEGIN` without a `finally`/cleanup block.

### 9.5. Configuring timeouts

Consider:
- `idle_in_transaction_session_timeout`: terminates sessions idle in a transaction for too long.
- `idle_session_timeout`: limits idle sessions, taking connection pools into account.
- `statement_timeout`: limits statement execution duration.
- `lock_timeout`: limits how long a statement waits for a lock.

Set timeouts per role, database, or application and workload. Do not apply a single global value to every session without testing.

## 10. Finding Queries Waiting on Locks

~~~sql
SELECT
    pid,
    usename,
    application_name,
    datname,
    clock_timestamp() - query_start AS query_age,
    wait_event_type,
    wait_event,
    left(query, 1000) AS query
FROM pg_stat_activity
WHERE state = 'active'
  AND wait_event_type = 'Lock'
ORDER BY query_start;
~~~

### 10.1. Lock wait alone does not identify the blocker

`pg_stat_activity` tells you which session is waiting on a lock. To find the blocking backend, call `pg_blocking_pids(pid)` and match the PID back against `pg_stat_activity`.

### 10.2. Do not look only at query age

A query with high `query_age` might be running CPU-intensive work, waiting on I/O, or waiting on a lock. Combine wait events with execution plans and metrics to find the cause.

### 10.3. Blocked queries can pile up across many sessions

A single lock-holding transaction can block one query, which in turn holds resources causing many other sessions to queue behind it. Find the root blocker instead of canceling all blocked queries.

## 11. Finding Blocking Sessions with pg_blocking_pids

`pg_blocking_pids(pid)` returns the PIDs of sessions currently blocking the given backend.

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.usename AS blocked_user,
    blocked.application_name AS blocked_app,
    clock_timestamp() - blocked.query_start AS blocked_query_age,
    blocked.wait_event,
    left(blocked.query, 500) AS blocked_query,
    blocker.pid AS blocker_pid,
    blocker.usename AS blocker_user,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    clock_timestamp() - blocker.xact_start AS blocker_xact_age,
    left(blocker.query, 500) AS blocker_last_or_current_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS p(blocker_pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = p.blocker_pid
WHERE blocked.wait_event_type = 'Lock'
ORDER BY blocked.query_start;
~~~

### 11.1. Reading the output

- `blocked_pid`: the waiting process.
- `blocker_pid`: the process holding the lock or ahead in the lock wait queue.
- `blocker_state`: the blocker can be `active` or `idle in transaction`.
- `blocker_xact_age`: how long the blocker's transaction has been open.
- `blocker_last_or_current_query`: current query if active, or most recent query if idle.

### 11.2. Blocker idle in transaction

This is an important pattern. The session is not running any query right now, yet it still holds transactions and locks. The displayed query is likely the last statement executed before becoming `idle in transaction`.

### 11.3. Multiple blockers

A backend can have multiple blocking PIDs. The query above produces one row per blocked/blocker pair. Review the full group before deciding to cancel or terminate.

### 11.4. Blocking tree

For complex incidents, build the `blocked_pid -> blocker_pid` graph and locate the node blocking the most sessions. Do not sort only by query age; the root blocker might be in an `idle` state.

## 12. Combining pg_stat_activity with pg_locks

`pg_locks` displays locks currently held or requested by processes.

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 500) AS query
FROM pg_locks AS l
JOIN pg_stat_activity AS a
  ON a.pid = l.pid
ORDER BY l.granted, a.pid;
~~~

### 12.1. granted

- `true`: the lock has been granted.
- `false`: the backend is waiting for the lock.

### 12.2. relation

`relation` may be NULL for locks not tied directly to a specific relation. Casting to `regclass` displays table names when a valid OID is present.

### 12.3. Lock modes

Lock modes such as `AccessShareLock`, `RowShareLock`, `RowExclusiveLock`, `ShareLock`, and `AccessExclusiveLock` have distinct semantics. Do not guess from the lock name alone; check the lock conflict matrix and the operation being performed.

### 12.4. pg_locks does not replace pg_blocking_pids

`pg_locks` details lock objects and modes; `pg_blocking_pids` is generally the most convenient way to identify which sessions are blocking a PID. Use both together when deep analysis is needed.

## 13. Viewing Sessions by Application and Client

### 13.1. Connections by application

~~~sql
SELECT
    COALESCE(application_name, '(unset)') AS application,
    state,
    count(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY COALESCE(application_name, '(unset)'), state
ORDER BY application, state;
~~~

### 13.2. Connections by client address

~~~sql
SELECT
    client_addr,
    application_name,
    usename,
    count(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY client_addr, application_name, usename
ORDER BY sessions DESC;
~~~

### 13.3. Sessions by database and state

~~~sql
SELECT
    datname,
    state,
    count(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname, state
ORDER BY datname, state;
~~~

### 13.4. Missing application_name

If many sessions have `application_name` NULL or empty, configure names for each service. This greatly improves attribution during investigations.

### 13.5. Connection pools

Pools may keep connections idle for reuse. Monitor connections from each application instance, pool max size, active/idle pool clients, and queue waits. PostgreSQL only sees server-side connections and does not necessarily know how many requests are waiting inside the pooler.

## 14. Viewing Backend Types

On versions that include the `backend_type` column:

~~~sql
SELECT
    backend_type,
    state,
    count(*) AS processes
FROM pg_stat_activity
GROUP BY backend_type, state
ORDER BY backend_type, state;
~~~

Process types can include:
- client backend.
- autovacuum worker.
- background writer.
- checkpointer.
- WAL sender.
- WAL receiver.
- logical replication worker.
- parallel worker.
- other background workers.

The exact list depends on version and extensions. Background processes are not client sessions; `query` text may differ or be NULL.

## 15. Viewing Sessions Using SSL

`pg_stat_activity` does not contain full TLS details. Join with `pg_stat_ssl`:

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.client_addr,
    s.ssl,
    s.version,
    s.cipher,
    s.bits
FROM pg_stat_activity AS a
LEFT JOIN pg_stat_ssl AS s
  ON s.pid = a.pid
WHERE a.backend_type = 'client backend'
ORDER BY a.pid;
~~~

### 15.1. SSL false

A non-SSL connection may still be valid if policy allows it, such as Unix sockets or controlled internal networks. Evaluate against security policy rather than just checking a boolean.

### 15.2. TLS configuration

Combine `pg_stat_ssl` with `ssl=on`, `pg_hba.conf`, and application connection settings. Verify client certificate requirements if using mutual TLS.

## 16. Query ID and Linking to Query Statistics

Some PostgreSQL versions expose `query_id` in `pg_stat_activity` when query identifier computation is enabled and the query can be identified.

~~~sql
SELECT
    pid,
    query_id,
    state,
    clock_timestamp() - query_start AS query_age,
    left(query, 1000) AS query
FROM pg_stat_activity
WHERE state = 'active'
ORDER BY query_start;
~~~

### 16.1. query_id can be NULL

Query ID may be NULL if the feature is disabled, the query has no identifier, or the version/configuration does not compute it.

### 16.2. compute_query_id

The `compute_query_id` setting controls query identifier calculation in supported versions. Check `SHOW compute_query_id` and your major version's documentation.

### 16.3. pg_stat_statements

`pg_stat_statements` aggregates statistics by query identity, such as call counts and cumulative execution time. It provides a historical workload view, whereas `pg_stat_activity` focuses on existing sessions and current state.

### 16.4. Query ID is not a permanent global identifier

Do not treat `query_id` as a permanent unique ID across versions, databases, or environments without checking semantics. Combine database, user, version, and query fingerprint when correlating.

## 17. pg_stat_activity and Query History

`pg_stat_activity` is not a query log.

| Tool | Purpose |
| --- | --- |
| pg_stat_activity | Existing sessions and current/most recent query |
| pg_stat_statements | Aggregated statistics by query |
| PostgreSQL logs | Event/statement history per logging configuration |
| auto_explain | Logs execution plans for queries meeting configured criteria |
| pg_stat_progress_* | Progress of certain running operations |

### 17.1. Enable logging purposefully

Settings such as `log_min_duration_statement`, `log_line_prefix`, `log_lock_waits`, and `log_temp_files` aid investigations. Choose thresholds and retention to avoid excessive log volume.

### 17.2. log_line_prefix

Include PID, user, database, `application_name`, and client address in the log prefix to correlate log lines with sessions.

### 17.3. Query text can be sensitive

Query literals can contain emails, tokens, or business data. Consider parameterization, access control, log retention, and masking.

### 17.4. Avoid aggressive polling

Querying `pg_stat_activity` too frequently from multiple monitors adds overhead and noise. Choose sensible sampling intervals and avoid dashboards opening hundreds of panels simultaneously.

## 18. Permissions and Visibility

Not every user can see full details of every session.

### 18.1. Regular users

A regular user can view full details for their own sessions. For sessions owned by other users, sensitive fields such as query text and query identifiers may be hidden or NULL.

### 18.2. pg_read_all_stats

The predefined `pg_read_all_stats` role grants broader visibility into statistics and activity details. Granting this role permits reading queries and activity across users; evaluate it under least privilege.

~~~sql
GRANT pg_read_all_stats TO monitoring_reader;
~~~

### 18.3. pg_monitor

`pg_monitor` is a convenience role granting broader monitoring privileges, including predefined monitoring roles like `pg_read_all_stats` and access to many settings/statistics. Read the documentation for your version and grant it only to necessary monitoring principals.

### 18.4. Do not grant superuser to dashboards

Dashboards rarely need superuser. Use a dedicated role with appropriate `SELECT`/monitoring privileges.

### 18.5. Signal privileges

Canceling or terminating another user's backend requires appropriate signal privileges, typically superuser or a role with `pg_signal_backend`; superuser-owned backends carry additional protections. Verify policy and version behavior before granting.

## 19. Canceling a Query with pg_cancel_backend

`pg_cancel_backend(pid)` sends a cancel signal to the backend's current query.

~~~sql
SELECT pg_cancel_backend(12345);
~~~

The boolean result indicates the signal was sent successfully, not a guarantee that the query has already ended or that the transaction behaved as desired.

### 19.1. When to use it?

- A query has been running too long and is confirmed unnecessary to continue.
- A query is causing abnormal load.
- A blocked statement needs to be stopped.
- Resources need to be freed while keeping the session connected.

### 19.2. Transaction behavior

If a query fails due to cancellation inside a transaction, the transaction enters an aborted state and requires `ROLLBACK`. The application must handle the error and end the transaction.

### 19.3. Do not cancel solely because query age is high

A long query might be a legitimate report. Verify owner, application, business impact, wait events, and execution plan before canceling.

## 20. Terminating a Session with pg_terminate_backend

`pg_terminate_backend(pid)` requests the server to terminate the session/process.

~~~sql
SELECT pg_terminate_backend(12345);
~~~

### 20.1. Impact

- The session is disconnected.
- Any open transaction is rolled back when the backend exits.
- The client must reconnect to continue.
- The application may receive a connection error and retry.

### 20.2. When to use it?

Use only with clear justification—for example, an `idle in transaction` session holding locks for a long time when the owner cannot intervene, or a session causing an active incident that must be terminated after evaluation.

### 20.3. Why is it risky?

Termination can fail application requests, roll back large transactions, and trigger a retry storm. Terminating a blocker can wake up many queued queries at once, creating a new load spike.

### 20.4. Verify the PID before acting

A PID can exit and be reused. Capture PID, user, database, `application_name`, `client_addr`, `state`, `xact_start`, and `query` immediately before signaling.

### 20.5. Never terminate system processes arbitrarily

Do not kill autovacuum, WAL sender/receiver, checkpointer, or background workers merely because they appear in the view. Identify the backend type and operational role first.

## 21. Runbook for Handling Long-Running Queries

1. List active sessions.
2. Identify database, user, `application_name`, and client.
3. Measure query age and transaction age.
4. Read `wait_event_type` and `wait_event`.
5. If `Lock`, find blockers using `pg_blocking_pids`.
6. If `IO` or CPU, inspect relevant metrics and execution plans.
7. Confirm whether the query is a legitimate workload.
8. Contact the owner or application team per the incident process.
9. Try canceling the query first if approved and appropriate.
10. Terminate the session only when canceling is insufficient or an `idle-in-transaction` session is causing harm.
11. Monitor the aftermath: transaction rollback, lock release, retries, and application errors.
12. Record the incident timeline and root cause.

## 22. Runbook for Handling Lock Contention

### Step 1: Find blocked sessions

Filter for `state = 'active'` and `wait_event_type = 'Lock'`.

### Step 2: Find blockers

Use `pg_blocking_pids` and join back to `pg_stat_activity`.

### Step 3: Identify the root blocker

Inspect the blocker's `state`, `xact_start`, `application_name`, `query`, and locks. An `idle in transaction` blocker often deserves immediate attention.

### Step 4: Understand the transaction

Determine whether the lock-holding transaction can safely commit or roll back. Never issue `COMMIT` on behalf of an application.

### Step 5: Release in a controlled manner

Ask the application owner to end the transaction, or cancel/terminate according to authorization and incident policy.

### Step 6: Monitor the queue

After the blocker exits, watch blocked sessions, latency, and retry behavior. Releasing locks can trigger many queries running concurrently.

## 23. Runbook for Handling idle-in-transaction

1. Locate `idle in transaction` sessions.
2. Sort by transaction age.
3. Identify `application_name`, user, client, and last query.
4. Check which sessions are blocked by it.
5. Check application logs or request IDs if available.
6. Contact the owner to commit or roll back according to business logic.
7. If necessary, cancel/terminate per procedure.
8. Check autovacuum and bloat impact.
9. Configure `idle_in_transaction_session_timeout` if appropriate.
10. Fix application code paths so every transaction closes in both success and error paths.

## 24. Monitoring Connection Capacity

### 24.1. Connections by state

~~~sql
SELECT
    state,
    count(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY state
ORDER BY sessions DESC;
~~~

### 24.2. Total connections by database

~~~sql
SELECT
    datname,
    count(*) AS sessions,
    count(*) FILTER (WHERE state = 'active') AS active_sessions,
    count(*) FILTER (WHERE state = 'idle') AS idle_sessions,
    count(*) FILTER (
        WHERE state LIKE 'idle in transaction%'
    ) AS idle_in_transaction_sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname
ORDER BY sessions DESC;
~~~

### 24.3. Comparing against max_connections

~~~sql
SHOW max_connections;

SELECT count(*) AS client_backends
FROM pg_stat_activity
WHERE backend_type = 'client backend';
~~~

`max_connections` is a configured ceiling for concurrent connections, not a target to consume fully. Reserved slots/connections and other backend types can affect the comparison; verify version and settings.

### 24.4. Pool sizing

Total connections across all application instances, workers, schedulers, and admin tools must stay within budget. A pool with `max_size = 20` across 30 instances can open up to 600 connections if every pool expands to maximum.

### 24.5. Connection churn

Monitor `backend_start` and connection creation rates. Excessive connects/disconnects add authentication, process startup, and TLS handshake overhead.

## 25. Monitoring Operation Progress

`pg_stat_activity` shows query and state, while progress views provide details for specific operations.

Example:

~~~sql
SELECT *
FROM pg_stat_progress_vacuum;
~~~

Other views, depending on version and operation, track `CREATE INDEX`, `ANALYZE`, `COPY`, `CLUSTER`, `BASEBACKUP`, and other tasks.

### 25.1. Why combine them?

An active query may show only that a `VACUUM` command is running. `pg_stat_progress_vacuum` can show the current phase, heap blocks scanned/vacuumed, and index vacuum progress.

### 25.2. Not every query has a progress view

A regular `SELECT` has no general progress view. Rely on query age, wait events, `EXPLAIN`/metrics, and logs.

### 25.3. Version differences

View names and columns depend on major version. Check `pg_catalog` and documentation for your running server.

## 26. Monitoring Vacuum and Transaction Horizons

`pg_stat_activity` helps detect old transactions and snapshots that may hinder vacuum.

### 26.1. backend_xmin

`backend_xmin` shows the `xmin` currently held by a backend, if any. An old snapshot can prevent vacuum from removing tuple versions still visible to that snapshot.

### 26.2. Transaction age

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    clock_timestamp() - xact_start AS xact_age,
    backend_xmin,
    left(query, 500) AS query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

### 26.3. Replication slots

Logical and physical slots can also retain WAL or catalog history; they do not show up as ordinary client transactions. Combine `pg_replication_slots` with vacuum monitoring.

### 26.4. XID wraparound

Long-lived transactions and persistently blocked vacuuming can drive up transaction ID age. Monitor database age/freeze metrics separately; do not watch `xact_start` alone.

## 27. Combining with pg_stat_database

`pg_stat_database` provides database-level statistics such as commits, rollbacks, blocks read/hit, tuples returned/fetched/inserted/updated/deleted, and conflicts.

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
    tup_deleted
FROM pg_stat_database
ORDER BY datname;
~~~

These are cumulative counters since the last statistics reset or server startup depending on the field. Convert counters to rates by taking deltas across two scrapes; never treat raw cumulative values as current rates.

## 28. Combining with pg_stat_statements

`pg_stat_statements` aggregates execution statistics for normalized queries when the extension is installed and configured.

Example:

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    left(query, 500) AS query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Column names can differ across versions. Check the extension version and view definition before using in automation.

### 28.1. Two perspectives

- `pg_stat_activity`: which queries are running right now, and which sessions are waiting.
- `pg_stat_statements`: which query patterns consumed the most cumulative time over a statistical period.

### 28.2. Do not confuse total time with current duration

`total_exec_time` is cumulative time across all calls for that query entry, not the runtime of any currently active session.

## 29. Combining with Application Observability

Database PIDs and query text are much more actionable when correlated with:
- `application_name`.
- Request ID or trace ID.
- Job ID.
- Service instance/hostname.
- User/tenant context per policy.
- Application logs.
- Distributed tracing.

Do not embed sensitive data into `application_name` or query comments. Use bounded, controlled identifiers.

## 30. Recommended Monitoring Dashboard

An operational dashboard can include these panels:

| Panel | Source | Question |
| --- | --- | --- |
| Connections by state | pg_stat_activity | How many active/idle/idle-in-transaction sessions exist? |
| Connections by app | pg_stat_activity | Which service is opening too many connections? |
| Long active queries | pg_stat_activity | Which queries exceed duration thresholds? |
| Old transactions | pg_stat_activity | Which transactions have been open too long? |
| Lock waiters/blockers | pg_stat_activity + pg_blocking_pids | Who is blocking whom? |
| Wait events | pg_stat_activity | What are backends waiting on? |
| Query workload | pg_stat_statements | Which query patterns consume the most time? |
| Database rates | pg_stat_database | What are commit/read/write trends? |
| Operation progress | pg_stat_progress_* | Which phase are vacuum/index/copy jobs in? |
| SSL connections | pg_stat_ssl | Are connections using TLS per policy? |

### 30.1. Sampling interval

Choose intervals based on incident response needs and monitoring overhead. There is no need to scrape every `query` text column every second on a huge cluster without justification.

### 30.2. Alert thresholds

Set thresholds against baselines:
- `idle-in-transaction` count exceeding threshold.
- Transaction age exceeding SLA.
- Rising lock wait durations.
- Active query age exceeding workload threshold.
- Connection usage approaching capacity.
- Unusual wait events.
- Rising query cancellation/error rates.

### 30.3. Alert context

Alerts should include PID, database, user, `application_name`, client address, state, wait event, transaction age, and a protected query sample. Never post raw sensitive query literals to public channels.

## 31. Limitations and Pitfalls When Reading pg_stat_activity

### 31.1. Query text can be truncated

`track_activity_query_size` bounds the stored query text length. Long queries can be cut off; do not assume the displayed snippet is the entire statement.

### 31.2. Query text may be the previous statement

For non-active sessions, `query` is typically the most recent statement. Read it together with `state` and `query_start`.

### 31.3. Sampling is instantaneous

A short query can start and finish between two scrapes. When history is needed, use logs, tracing, or `pg_stat_statements`.

### 31.4. Wait events can change continuously

A backend can switch from `Lock` to `IO` or no wait within fractions of a second. A single snapshot does not describe the entire query lifetime.

### 31.5. Permissions hide data

Queries from other users may appear hidden if the monitoring role lacks privileges. NULL does not always mean no query exists.

### 31.6. View columns evolve

New columns may be added across major versions. Automation should check compatibility or pin schemas by version.

### 31.7. Not every backend is an application connection

Filter `backend_type` or recognize background processes before counting client sessions.

## 32. Configuring Activity Tracking

### 32.1. track_activities

This setting controls collection of command/activity details for sessions. If disabled, `state` can appear as `disabled` and query details will be unavailable as expected.

~~~sql
SHOW track_activities;
~~~

### 32.2. track_activity_query_size

Limits the size of collected query text. Larger values increase memory overhead; balance investigative needs against statement sizes.

~~~sql
SHOW track_activity_query_size;
~~~

### 32.3. compute_query_id

If `query_id` is needed, check `compute_query_id` and your version. Some integrations or `pg_stat_statements` setups may require additional configuration.

### 32.4. Logging settings

~~~sql
SHOW log_min_duration_statement;
SHOW log_lock_waits;
SHOW log_line_prefix;
~~~

Select logging policies to retain adequate evidence without flooding logs or exposing sensitive data.

## 33. Safety When Acting on Sessions

Before canceling or terminating:
1. Verify PID and session identity.
2. Confirm database/user/application.
3. Check state and wait event.
4. Check query age and transaction age.
5. Identify blockers and dependents.
6. Assess rollback and retry impact.
7. Notify the owner per incident policy.
8. Prefer canceling first if only stopping a query is needed.
9. Terminate only with clear justification.
10. Monitor the aftermath and record an audit trail.

### 33.1. Do not run scripts that blindly kill all long queries

Query age alone is not enough. A valid long report, `VACUUM`, or migration may legitimately run for a long time.

### 33.2. Do not terminate blindly by application_name

An application can have critical requests, background jobs, and lock-holding sessions at the same time. Target specific PIDs and verify first.

### 33.3. You cannot run COMMIT/ROLLBACK from another session

PostgreSQL does not allow an admin session to commit another client session's transaction via an ordinary SQL command. Ask the owner to handle it or terminate according to policy.

## 34. Troubleshooting: Database Reports Too Many Connections

1. Count client backends by database/user/application.
2. Compare against `max_connections` and reserved connection capacity.
3. Determine whether pools are opening too many connections.
4. Inspect idle sessions and connection churn.
5. Check for connection leaks or retry storms.
6. Consider a pooler such as PgBouncer if the architecture fits.
7. Adjust pool sizes and timeouts.
8. Terminate sessions only after clear identification and approval.

Raising `max_connections` is not a default solution; each backend consumes resources and can worsen memory and scheduler contention.

## 35. Troubleshooting: Query Is Slow Without Lock Waits

If `state=active` and `wait_event_type` is not `Lock`:
- Check other wait events such as `IO`, `LWLock`, or `Client`.
- Inspect CPU saturation and storage latency.
- Run `EXPLAIN (ANALYZE, BUFFERS)` in an appropriate environment; `ANALYZE` executes the query, so proceed carefully.
- Compare the query against `pg_stat_statements`.
- Check for plan regressions, stale statistics, and missing/changed indexes.
- Check network/client consumption if the server is waiting to send results.
- Check parallel workers and resource contention.

Do not conclude a query is burning CPU solely because `wait_event` is NULL.

## 36. Troubleshooting: Rising idle-in-transaction Count

Common causes:
- Application forgot to commit or roll back.
- Transaction left open while waiting on network/external APIs.
- Pooler returned a connection with an unclosed transaction.
- Interactive user left a transaction open.
- Exception handler failed to roll back.

Remediation path:
- Identify the owner via `application_name` and client address.
- Inspect transaction age and blocker relationships.
- Fix the application's transaction lifecycle.
- Consider `idle_in_transaction_session_timeout`.
- Monitor vacuum/bloat and oldest transaction horizons.

## 37. Troubleshooting: Sudden Spike in Lock Waits

1. Identify blocked sessions.
2. Locate blockers using `pg_blocking_pids`.
3. Group by application, database, and relation.
4. Inspect blockers' transaction age.
5. Check for DDL, bulk updates, migrations, or long transactions.
6. Cancel or terminate in a controlled manner.
7. Watch for retry storms once the lock clears.
8. Review `lock_timeout` and transaction design.

## 38. Troubleshooting: Dashboard Shows NULL Queries

Possible reasons:
- Monitoring user lacks permission to view other sessions' queries.
- Backend has no standard query text.
- `track_activities` is disabled.
- Query text is not populated for that backend type.
- The query finished and activity state changed between observations.
- Version/view semantics differ.

Check monitoring privileges, `SHOW track_activities`, and `backend_type`. Do not assume NULL queries automatically indicate a database error.

## 39. PostgreSQL Practice Exercises

Run these in a lab or staging environment. Any cancel/terminate operations should target test sessions you created yourself.

1. **Explore:** query `pg_stat_activity` and identify the current session's PID.
2. **Identify:** list `datname`, `usename`, `application_name`, and `client_addr`.
3. **Client backends:** filter `backend_type = 'client backend'`.
4. **Background:** list the distinct `backend_type` values.
5. **State:** count sessions grouped by `state`.
6. **Active:** run a sufficiently long query in the lab and observe `state=active`.
7. **Idle:** open `psql` without running a query and observe `state=idle`.
8. **Transaction:** run `BEGIN` and wait, observing `idle in transaction`.
9. **Aborted:** trigger an error inside a transaction and observe `idle in transaction (aborted)`.
10. **Query text:** compare the `query` column of active and idle sessions.
11. **Query age:** compute query age for active statements.
12. **Transaction age:** compute transaction age from `xact_start`.
13. **Session age:** compute connection age from `backend_start`.
14. **State age:** compute time in current state from `state_change`.
15. **Application name:** run `SET application_name` and filter sessions by name.
16. **Database counts:** group connections by database.
17. **User counts:** group connections by user.
18. **Client counts:** group sessions by `client_addr`.
19. **Long query:** find queries active longer than a threshold.
20. **Idle transaction:** find `idle-in-transaction` sessions older than 1 minute.
21. **Old transaction:** sort sessions by `xact_start`.
22. **Wait event:** create a lock wait across two sessions and observe `wait_event_type`.
23. **Lock blocker:** use `pg_blocking_pids` to locate the blocker.
24. **Blocking tree:** create multiple blocked sessions and map the PID relationships.
25. **pg_locks:** join `pg_locks` with `pg_stat_activity`.
26. **Lock mode:** observe the lock modes acquired by `SELECT`, `UPDATE`, and DDL.
27. **Cancel:** call `pg_cancel_backend` on a long lab query.
28. **Terminate:** call `pg_terminate_backend` on a lab session and observe client reconnection.
29. **Rollback:** verify the transaction rolls back when its backend is terminated.
30. **Permissions:** inspect activity using a regular role vs. a role with `pg_read_all_stats`.
31. **Monitoring role:** grant `pg_monitor` to a lab role and check visibility.
32. **Signal role:** study `pg_signal_backend` and process signaling permissions.
33. **SSL:** join `pg_stat_activity` with `pg_stat_ssl`.
34. **Query ID:** inspect `query_id` and `compute_query_id` if supported by your version.
35. **pg_stat_statements:** compare currently running queries with cumulative statistics.
36. **Progress:** run `VACUUM` or `CREATE INDEX` in the lab and observe the corresponding progress view.
37. **Connection pool:** simulate multiple application connections and count sessions by `application_name`.
38. **Pool sizing:** calculate total connection budget across multiple application instances.
39. **Churn:** repeatedly open/close connections and observe `backend_start`.
40. **Timeout:** configure `statement_timeout` and observe query cancellation.
41. **Lock timeout:** configure `lock_timeout` and trigger a lock conflict.
42. **Idle transaction timeout:** configure `idle_in_transaction_session_timeout` in the lab.
43. **Idle session timeout:** test `idle_session_timeout` and its impact on pools.
44. **track_activities:** inspect the setting and understand the `disabled` state.
45. **Query size:** inspect `track_activity_query_size` and query text truncation.
46. **Log prefix:** configure `log_line_prefix` with PID, user, database, and application.
47. **Slow query logs:** test `log_min_duration_statement` in the lab.
48. **Lock logs:** enable `log_lock_waits` and trigger a lock wait.
49. **Wait sampling:** capture multiple snapshots to observe changing wait events.
50. **ClientRead:** observe an idle session waiting for the client.
51. **IO wait:** generate an I/O workload and identify version-appropriate wait events.
52. **LWLock:** read documentation on an observed `LWLock` wait event.
53. **Parallel query:** run a parallel query and locate `leader_pid` and parallel workers.
54. **Autovacuum:** observe an autovacuum worker in `pg_stat_activity`.
55. **WAL sender:** set up a physical replication lab and identify the WAL sender.
56. **Logical worker:** create a logical subscription and identify apply/sync workers.
57. **backend_xmin:** find sessions holding an old `xmin`.
58. **Vacuum horizon:** simulate an old transaction snapshot and observe its impact on vacuum in the lab.
59. **Database stats:** correlate insights with `pg_stat_database`.
60. **Query rate:** take two counter snapshots and compute delta/rate.
61. **NULL query:** verify visibility when `pg_read_all_stats` is missing.
62. **Sensitive query:** run a test query with literals and evaluate access controls on query text.
63. **Dashboard:** build a connections-by-state panel.
64. **Dashboard:** build a connections-by-application panel.
65. **Dashboard:** build a long-running queries panel.
66. **Dashboard:** build an idle-in-transaction age panel.
67. **Dashboard:** build a lock waiters and blockers panel.
68. **Alert:** create an alert when `idle-in-transaction` exceeds threshold.
69. **Alert:** create an alert when connection usage approaches capacity.
70. **Alert:** create an alert when lock wait duration climbs.
71. **Troubleshooting:** investigate `too many connections` in the lab.
72. **Troubleshooting:** investigate a long active query with no `Lock` wait.
73. **Troubleshooting:** investigate an `idle in transaction` blocker.
74. **Troubleshooting:** investigate NULL query text.
75. **Incident:** write a runbook for canceling a heavy-load query.
76. **Incident:** write a runbook for terminating a lock-holding session.
77. **Security:** design a non-superuser monitoring role.
78. **Observability:** correlate PID/`application_name` with application request logs.
79. **History:** design logging and `pg_stat_statements` to provide the history `pg_stat_activity` does not retain.
80. **Capstone design:** build a PostgreSQL dashboard and runbook covering session states, long queries, lock blockers, transaction age, connection capacity, permissions, cancel/terminate safety, and incident evidence.

## 40. Operations Checklist

### Observing sessions

- [ ] Filter client backends vs. background processes properly.
- [ ] Identify database, user, `application_name`, and client.
- [ ] Read `state` alongside `wait_event_type` and `wait_event`.
- [ ] Compute query age only for active sessions.
- [ ] Distinguish query age, transaction age, and session age.
- [ ] Recognize that query text may be the most recent statement.

### Investigating slowness and locks

- [ ] Find active queries exceeding thresholds.
- [ ] Find `idle-in-transaction` sessions.
- [ ] Use `pg_blocking_pids` to locate blockers.
- [ ] Cross-check `pg_locks` when needed.
- [ ] Combine metrics, progress views, and logs.
- [ ] Identify owner/application before intervening.

### Intervention

- [ ] Verify PID and session identity.
- [ ] Prefer canceling the query when only stopping a statement is required.
- [ ] Terminate only after evaluating rollback and retry impact.
- [ ] Never kill background processes arbitrarily.
- [ ] Monitor aftermath after signaling.

### Monitoring and security

- [ ] `application_name` is set consistently.
- [ ] Monitoring role follows least privilege.
- [ ] Query text and logs are protected.
- [ ] Connection capacity is evaluated against pool budgets.
- [ ] Slot, vacuum, and transaction horizons are monitored alongside activity.
- [ ] Sampling intervals do not create excessive overhead.
- [ ] Dashboards and automation match the PostgreSQL version.

## 41. Summary

`pg_stat_activity` is an essential window into live PostgreSQL server processes and sessions. It reveals who is connected, what type of backend each process is, whether a session is active or idle, what the current or most recent query is, and what event a process is waiting on.

Key principles:

- **One row represents one server process**, not necessarily one end user.
- **`state` and `wait_event` complement each other.** Active does not mean burning CPU; a query may be waiting on a lock or I/O.
- **Query text on an idle session is usually the most recent statement.** Interpret `query_start` as execution duration only when `state=active`.
- **Transaction age differs from query age and session age.** Prolonged `idle-in-transaction` sessions can hold locks/snapshots and hinder vacuum.
- **`pg_blocking_pids` helps locate blockers.** Combine `pg_locks` and `pg_stat_activity` to understand lock contention.
- **`pg_cancel_backend` stops a query; `pg_terminate_backend` ends a session.** Both require verifying PID, owner, and impact before execution.
- **`pg_stat_activity` shows current state, not full history.** Use logs, `pg_stat_statements`, and tracing for historical analysis.
- **Monitoring privileges govern visibility.** Grant `pg_read_all_stats`/`pg_monitor` intentionally and protect query text.
- **Combine activity with progress views, database stats, and application telemetry** to find root causes instead of relying on a single snapshot.

When paired with consistent `application_name` tagging, wait events, lock diagnostics, and proper logging, `pg_stat_activity` enables DBAs to spot abnormal sessions early, pinpoint bottlenecks, and resolve incidents safely without unintended workload disruption.
