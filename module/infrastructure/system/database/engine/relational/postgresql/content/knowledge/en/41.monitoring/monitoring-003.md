# Wait Events and Distinguishing Lock, I/O, and Client Waits in PostgreSQL

## 1. What Questions Do Wait Events Answer?

When a query runs slowly, the delay can come from many causes: another transaction holding a lock, PostgreSQL waiting on storage to read or write data, a backend waiting for the client to send a command or read results, or another process coordinating internally. Looking at query duration alone is not enough to identify the cause.

PostgreSQL exposes **wait events** to indicate where a backend or process is waiting. Two key fields in `pg_stat_activity` are:

- `wait_event_type`: the wait category, such as `Lock`, `IO`, `Client`, `LWLock`.
- `wait_event`: the specific wait point, such as `transactionid`, `DataFileRead`, `ClientRead`.

Combining wait events with `state`, query/transaction duration, blocker information, I/O statistics, and OS metrics helps distinguish three common categories:

1. **Lock waits:** a query cannot proceed because it needs a lock currently held by another backend.
2. **I/O waits:** a backend is waiting for data or WAL read/write/flush/extend operations.
3. **Client waits:** PostgreSQL is waiting for data from the client or trying to send data back to the client.

A single wait event is only a point-in-time snapshot of state at sampling time. On its own, it does not prove a query has failed, the database is congested, or a backend must be killed. Always observe repeatedly and consider context.

### 1.1. Learning Objectives

After this lesson, you will be able to:

1. Read `state`, `wait_event_type`, and `wait_event` in `pg_stat_activity`.
2. Distinguish heavyweight locks from `LWLock` and `BufferPin`.
3. Find blockers using `pg_blocking_pids()` and `pg_locks`.
4. Identify I/O waits and analyze read/write/flush pressure.
5. Distinguish `ClientRead` from `ClientWrite`.
6. Recognize normal idle sessions versus hazardous `idle in transaction` sessions.
7. Sample wait events to detect patterns instead of drawing conclusions from a single query.
8. Design dashboards, alerts, and runbooks for lock, I/O, and client waits.
9. Determine when to investigate query plans, storage, network, or the application.
10. Practice troubleshooting in a PostgreSQL lab.

### 1.2. Key Principles to Remember

- `wait_event_type` is the category; `wait_event` is the specific wait point name.
- `state='active'` does not mean the backend is continuously burning CPU; it may be waiting.
- `state='idle'` paired with `ClientRead` usually means a connection awaiting the next command, not an error.
- `ClientWrite` usually means the server is waiting to send data to the client; a slow client or network/large output may be the cause.
- `Lock` typically refers to locks managed by the lock manager; `LWLock` is a separate internal synchronization mechanism.
- `IO` indicates the backend is waiting on an I/O operation, but does not by itself prove the storage device is the sole bottleneck.
- A transient wait event can be completely normal.
- `pg_stat_activity` shows only current state; historical wait analysis requires separate sampling/monitoring.
- Never kill a backend based solely on a single wait event.
- Always check blockers, transaction age, query, application, storage/network metrics, and business impact.

---

## 2. Reading pg_stat_activity

### 2.1. Important fields

`pg_stat_activity` contains one row per server process, including client backends and various background workers.

| Field | Meaning |
|---|---|
| `pid` | Process ID |
| `datname` | Database |
| `usename` | User |
| `application_name` | Application/connection name |
| `client_addr` | Client address |
| `backend_type` | Backend/process type on supported versions |
| `state` | Query/session state |
| `wait_event_type` | Wait event category |
| `wait_event` | Specific wait point |
| `query_start` | Timestamp when the current query started |
| `xact_start` | Timestamp when the current transaction started |
| `state_change` | Most recent state change timestamp |
| `query` | Current or most recent query depending on state |

Some columns exist only in specific major versions. Check the view schema on your actual server before using queries in automation.

### 2.2. state

Common states:

- `active`: backend is currently executing a query.
- `idle`: backend is waiting for a new command from the client.
- `idle in transaction`: backend is inside a transaction but not currently running a query.
- `idle in transaction (aborted)`: the transaction errored and is waiting for the client to roll back or close the transaction.
- `fastpath function call`: backend is executing a fast-path function call on versions that report this state.

`idle in transaction` can hold locks, snapshots, and transaction IDs longer than necessary. It can prevent vacuum from cleaning up dead tuples, hold relation locks, and cause bloat even with no active query.

### 2.3. Basic query to inspect waits

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
    clock_timestamp() - query_start AS query_age,
    clock_timestamp() - xact_start AS transaction_age,
    query
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
ORDER BY query_start NULLS LAST;
~~~

`query_age` is directly meaningful for a running query only when `state='active'`. For idle sessions, `query` may be the last statement executed and `query_start` does not represent a currently executing query.

### 2.4. Viewing only active backends that are waiting

~~~sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS query_age,
    query
FROM pg_stat_activity
WHERE state = 'active'
  AND wait_event IS NOT NULL
ORDER BY query_start;
~~~

This query is helpful for listing currently waiting sessions, though it omits `idle-in-transaction` sessions that might be holding locks and blocking other queries.

### 2.5. Understanding active yet waiting

When `state='active'` and `wait_event IS NOT NULL`, the query is considered active, yet the process is currently paused at a wait point. For example:
- Active + Lock: query is waiting on a lock.
- Active + IO: query is waiting on I/O.
- Active + LWLock: query is waiting on an internal lightweight lock.

If `state='active'` and `wait_event IS NULL`, the backend was not at an instrumented wait point at sampling time. It may be running on CPU, runnable, or executing uninstrumented code. Check CPU, query plan, and OS scheduler metrics to distinguish.

### 2.6. Permissions and visibility

To inspect full details of other sessions, a role needs appropriate privileges, typically superuser or a role such as `pg_read_all_stats` depending on version. Without sufficient privileges, query/activity details for other backends may be hidden.

Do not grant superuser just so dashboards can read stats; use a dedicated monitoring role with least privilege.

### 2.7. Query text and sensitive data

`query` can contain literal values, emails, identifiers, or sensitive data. Do not expose raw query text on dashboards or tickets with broad audiences. Redact text, restrict access, use query IDs from `pg_stat_statements`, or store sanitized samples.

---

## 3. Wait Event Taxonomy

### 3.1. wait_event_type categories

Common categories in PostgreSQL include:

| Wait event type | General Meaning | Examples |
|---|---|---|
| `Activity` | Background process waiting on main loop activity | `WalWriterMain`, `AutoVacuumMain` |
| `BufferPin` | Waiting for a buffer pin to be released | `BufferPin` |
| `Client` | Waiting for communication on a client socket | `ClientRead`, `ClientWrite` |
| `Extension` | Extension-defined wait point | Depends on extension |
| `IO` | Waiting on an I/O operation | `DataFileRead`, `WALWrite` |
| `IPC` | Waiting on inter-process communication/coordination | Version-dependent events |
| `Lock` | Waiting on a heavyweight lock | `relation`, `transactionid` |
| `LWLock` | Waiting on an internal lightweight lock | `BufferContent`, `WALWrite` |
| `Timeout` | Waiting on a timeout/delay | `PgSleep`, `VacuumDelay` |

Event lists and exact names vary across major versions. Always check PostgreSQL documentation for your exact release.

### 3.2. A wait event is not an error code

A process waiting on I/O, a lock, or a client socket can be normal behavior. A wait event describes what the backend is waiting on, not that an SLA has been violated or an error occurred.

You also need:
- Wait duration and repeated samples.
- Query and transaction age.
- Number of affected sessions.
- Query rate/throughput.
- Resource saturation.
- User-visible latency.
- Blocking chain or storage/network evidence.

### 3.3. A process has one wait event at a time

A backend can rapidly transition between CPU work, lock waits, I/O waits, and client waits. A single sampling query can miss significant waits. Periodic sampling reveals patterns, provided the interval balances visibility against telemetry overhead.

### 3.4. Wait events and query duration

A query running for 10 minutes did not necessarily spend all 10 minutes in the same wait event. It might have:
- Waited 8 minutes on a lock, then spent 2 minutes reading data.
- Read many pages with scattered I/O waits.
- Produced a large result set and waited for the client to receive it.
- Run CPU-bound with `wait_event` NULL for most of its runtime.

Therefore, never infer total wait time from a single current wait event.

### 3.5. Wait groups to distinguish

This lesson focuses on three operational groups:

1. `Lock`: usually requires finding blockers and lock conflicts.
2. `IO`: requires analyzing query plans, buffers/cache, storage, and WAL.
3. `Client`: requires checking the application, sockets, network, and transaction/session lifecycle.

`LWLock` and `BufferPin` are also important because they can look like a “lock wait” while having different root causes and remedies than heavyweight locks.

---

## 4. Lock Waits

### 4.1. What is a heavyweight lock?

PostgreSQL uses the lock manager to coordinate concurrent access to resources such as tables, rows/tuples, transactions, objects, and advisory locks. When a backend requests a mode that conflicts with a lock held by another backend, it must wait.

Examples:
- A transaction holds an `ACCESS EXCLUSIVE` lock from `ALTER TABLE`.
- A `SELECT` query needs an `ACCESS SHARE` lock and must wait.
- An `UPDATE` waits on a row lock because another transaction is modifying the same row.
- A transaction waits on the transaction ID of an uncommitted/unrolled-back transaction.

### 4.2. Identifying Lock waits

In `pg_stat_activity`:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS query_age,
    clock_timestamp() - xact_start AS xact_age,
    query
FROM pg_stat_activity
WHERE wait_event_type = 'Lock'
ORDER BY query_start;
~~~

When you see `wait_event_type='Lock'`, locate direct blockers with `pg_blocking_pids()`. Do not draw conclusions from the event name alone; inspect lock type, mode, and the lock-holding query.

### 4.3. pg_blocking_pids()

`pg_blocking_pids(pid)` returns the PIDs of processes currently blocking the specified backend. This is usually the easiest way to find blockers because PostgreSQL computes the lock conflict directly.

~~~sql
SELECT
    pid,
    pg_blocking_pids(pid) AS blocking_pids,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE cardinality(pg_blocking_pids(pid)) > 0;
~~~

Results may contain multiple blockers. A blocker PID can be a parallel worker or another process depending on version behavior; inspect full process details.

### 4.4. Displaying waiter and blocker on the same row

~~~sql
SELECT
    waiter.pid AS waiter_pid,
    waiter.usename AS waiter_user,
    waiter.application_name AS waiter_app,
    waiter.state AS waiter_state,
    waiter.wait_event,
    clock_timestamp() - waiter.query_start AS waiter_query_age,
    waiter.query AS waiter_query,
    blocker.pid AS blocker_pid,
    blocker.usename AS blocker_user,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    clock_timestamp() - blocker.xact_start AS blocker_xact_age,
    blocker.query AS blocker_query
FROM pg_stat_activity AS waiter
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(waiter.pid)) AS blocked(blocker_pid)
JOIN pg_stat_activity AS blocker
    ON blocker.pid = blocked.blocker_pid
ORDER BY waiter.query_start;
~~~

This is a direct diagnostic query. If the blocker is `idle in transaction`, inspect its transaction age and application owner. The blocker's `query` text may be its last statement, not necessarily the statement that originally acquired the lock.

### 4.5. Viewing ungranted locks

~~~sql
SELECT
    l.pid,
    a.usename,
    a.application_name,
    a.state,
    l.locktype,
    l.mode,
    l.relation::regclass AS relation_name,
    l.page,
    l.tuple,
    l.transactionid,
    l.virtualxid,
    l.granted,
    a.query
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
WHERE NOT l.granted
ORDER BY l.pid;
~~~

`granted=false` indicates a waiting lock request. This query shows waiters, not the full conflict chain. Use `pg_blocking_pids()` to identify blockers, then inspect the blockers' locks.

### 4.6. Lock modes and conflicts

PostgreSQL has multiple lock modes; two modes conflict only when defined by the lock conflict matrix. For example:
- `ACCESS SHARE` is compatible with most modes, but conflicts with `ACCESS EXCLUSIVE`.
- `ROW EXCLUSIVE` is typically acquired by `INSERT`/`UPDATE`/`DELETE`.
- `SHARE`/`SHARE ROW EXCLUSIVE`/`EXCLUSIVE`/`ACCESS EXCLUSIVE` have differing conflict levels.

Do not guess lock conflicts from mode names alone. Consult the lock conflict matrix in the PostgreSQL documentation.

### 4.7. Relation locks and row locks

`pg_locks` shows relation locks or transaction ID locks. Row-level locks are normally stored in tuple headers and show up as transaction ID waits; you will not always see a simple row lock as a straightforward row in `pg_locks`.

Consequently, a waiter with `wait_event='transactionid'` may be waiting for the transaction holding a row lock to finish.

### 4.8. Lock queues and blocker chains

One blocker can stall multiple waiters; one waiter can in turn block other requests queued behind it. Building a lock tree helps isolate the root blocker. Prioritize resolving the transaction at the head of the chain rather than killing individual waiters.

### 4.9. Idle in transaction is a common blocker

An `idle in transaction` session can retain locks long after its statement finishes. An application may:
- Open a transaction and then wait for user input.
- Fail to commit/roll back on an exception.
- Hold a connection in a pool for too long.
- Forget to close a transaction across multi-step processing.

Monitor `xact_start`, `state_change`, and `application_name`. `idle_in_transaction_session_timeout` can help cap forgotten sessions, though application and version impact must be evaluated.

### 4.10. Advisory locks

Advisory locks are managed by the application and do not automatically protect table rows like constraints. They can produce the `advisory` wait event. Locate code paths calling `pg_advisory_lock`/`pg_try_advisory_lock` and review key conventions across services.

### 4.11. How to handle Lock waits

1. Identify waiters and wait durations.
2. Locate blockers using `pg_blocking_pids`.
3. Identify the lock-holding transaction/query and its owner.
4. Check transaction age, state, application, and business operation.
5. Inspect lock mode and resource to understand the conflict.
6. Prefer letting the transaction complete if feasible.
7. If canceling/terminating is required, evaluate rollback cost and unknown outcomes on the application side.
8. Watch the queue drain and queries resume.

Do not terminate a blocker solely because it is blocking others. It may be executing a valid transaction or critical migration; decisions must follow incident policy.

---

## 5. Distinguishing Lock, LWLock, and BufferPin

### 5.1. Lock

`wait_event_type='Lock'` represents heavyweight lock manager waits. You can use `pg_blocking_pids` to locate the backend holding the conflicting lock.

### 5.2. LWLock

Lightweight locks protect internal shared-memory structures. They are not equivalent to SQL table/row locks and cannot be resolved by blindly killing a “blocker query.”

Illustrative wait names:
- `BufferContent`: waiting for access to a shared buffer's contents.
- `BufferMapping`: synchronizing buffer mapping structures.
- `WALInsert`/`WALWrite`: synchronizing WAL write paths.
- `LockManager`: internal synchronization of the lock manager.
- `ProcArray`: synchronizing process/transaction state structures.

Exact names and wait groupings vary by version.

### 5.3. Investigating LWLock

If `LWLock` waits increase:
- Inspect the specific wait event.
- Check how many backends are affected.
- Check workload concurrency.
- Check buffer/WAL/transaction churn.
- Check your PostgreSQL version and known issues.
- Inspect CPU, memory, storage, and logs.
- Use profiling or specialized tools if internal contention requires deeper analysis.

`pg_blocking_pids()` is not a general tool for finding blockers for all `LWLock` waits.

### 5.4. BufferPin

`wait_event_type='BufferPin'` means a backend is waiting for a buffer pin to be released. A pin prevents a buffer from being evicted during an operation; it is not like a heavyweight lock.

Causes can involve long-running queries/scans holding buffer pins, cursors, or specific buffer access paths. Inspect active queries, transaction age, workload, and event context. Do not apply heavyweight lock-mode diagnosis to `BufferPin`.

### 5.5. Why the distinction matters

- Heavyweight `Lock`: locate blocker, transaction, and lock conflict.
- `LWLock`: investigate internal contention/concurrency; typically requires metrics/profiling.
- `BufferPin`: locate backends holding pins too long and inspect buffer access paths.

Lumping all of them together as “database locks” leads to the wrong actions and can worsen an incident.

---

## 6. I/O Waits

### 6.1. What is an IO wait?

`wait_event_type='IO'` indicates a backend is waiting on a PostgreSQL-instrumented I/O operation. Depending on the event, this may be:
- Reading a page from a data file.
- Writing or extending a data file.
- Flushing/syncing a data file.
- Reading, writing, or syncing WAL.
- I/O on SLRU or temporary files.
- Other internal control files.

Event names vary across major versions. Common examples include `DataFileRead`, `DataFileWrite`, `DataFileExtend`, `DataFileSync`, `WALRead`, `WALWrite`, and `WALSync`.

### 6.2. Identifying I/O waits

~~~sql
SELECT
    pid,
    datname,
    application_name,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS query_age,
    query
FROM pg_stat_activity
WHERE wait_event_type = 'IO'
ORDER BY query_start;
~~~

A query showing many `DataFileRead` waits may be reading pages absent from `shared_buffers`, though you must examine the plan, cache behavior, and storage latency before concluding.

### 6.3. A read wait does not necessarily mean a failing disk

`DataFileRead` can be normal whenever a query needs pages not in `shared_buffers`. It becomes a problem when:
- Wait duration/volume increases abnormally.
- Storage latency is high.
- Cache hit drops for the same workload.
- A query plan reads far too many pages.
- Many sessions are affected simultaneously.
- Throughput drops and request latency climbs.

Inspect query plans, indexes, selectivity, table bloat, cache sizing, and OS/storage metrics.

### 6.4. Write/extend/sync waits

- `DataFileWrite`: backend waiting to write a data file.
- `DataFileExtend`: waiting to extend a relation file.
- `DataFileSync`: waiting to sync/flush a data file on the I/O path.
- `WALWrite`/`WALSync`: waiting on WAL write/sync operations depending on version events.

WAL I/O and data-file I/O behave differently. A slow `COMMIT` may be impacted by WAL flush latency; checkpoints can create write pressure on data files.

### 6.5. I/O waits and checkpoints

Checkpoints flush dirty buffers to data files. If checkpoint writeback creates heavy pressure, foreground backends may compete for storage bandwidth. Monitor:
- Checkpoint frequency and duration.
- Checkpoint write/sync time.
- WAL volume and checkpoint spikes.
- Storage throughput, latency, and queue depth.
- Background writer and checkpointer activity.

Checkpoint statistics columns change across versions; inspect `pg_stat_checkpointer` or `pg_stat_bgwriter` according to your major version.

### 6.6. I/O waits and temporary files

Sort/hash operations can spill to temporary files when memory is insufficient or queries process large datasets. Temporary file I/O can slow queries down even when data-table reads are modest.

Check:
- `EXPLAIN (ANALYZE, BUFFERS)`.
- Temp blocks read/written in query stats.
- `work_mem` and concurrent operation count.
- Join/sort plans.
- Query cardinality estimates.

Do not raise `work_mem` server-wide casually; it can be allocated by many sort/hash nodes across many sessions simultaneously.

### 6.7. pg_stat_io starting in PostgreSQL 16

PostgreSQL 16 introduced `pg_stat_io` to observe aggregated I/O by backend type, object, and context. Views and columns may expand in later major releases.

~~~sql
SELECT *
FROM pg_stat_io
ORDER BY backend_type, object, context;
~~~

Use this view to analyze patterns such as reads, writes, extends, hits, evictions, and timing if those columns exist in your version. These are grouped aggregates, not one row per query or PID.

### 6.8. pg_stat_database and track_io_timing

~~~sql
SELECT
    datname,
    blks_read,
    blks_hit,
    round(
        100.0 * blks_hit / NULLIF(blks_hit + blks_read, 0),
        2
    ) AS shared_buffer_hit_pct,
    blk_read_time,
    blk_write_time
FROM pg_stat_database
WHERE datname = current_database();
~~~

`blk_read_time` and `blk_write_time` record meaningful timing only when `track_io_timing` is enabled. This setting can introduce overhead depending on platform and workload; measure on a representative environment before enabling widely.

A high cache hit ratio does not guarantee fast queries. A query can perform millions of buffer hits and still burn CPU; a low cache hit ratio during a sequential-scan workload can be entirely normal.

### 6.9. pg_stat_statements

When `pg_stat_statements` is installed and configured, you can find queries generating heavy reads or temp writes:

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_read,
    shared_blks_hit,
    temp_blks_read,
    temp_blks_written,
    query
FROM pg_stat_statements
ORDER BY shared_blks_read DESC
LIMIT 20;
~~~

Columns vary across server and extension versions. These are aggregate query statistics, not wait-event history. Use `queryid` and plans to pinpoint the I/O-heavy workload.

### 6.10. EXPLAIN for investigating I/O

~~~sql
EXPLAIN (ANALYZE, BUFFERS, WAL)
SELECT *
FROM app.orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 100;
~~~

`ANALYZE` executes the query. Use it only on safe `SELECT` queries or test environments; DML/DDL will modify data. `BUFFERS` shows buffer activity; `WAL` displays WAL generated on supported versions. With `track_io_timing` enabled, the plan can also show I/O timings.

### 6.11. Correlate with OS/storage

PostgreSQL wait events do not replace storage-layer metrics. Check:
- Device latency and queue depth.
- IOPS and throughput limits.
- Cloud volume burst credits and throttling.
- Filesystem saturation and free space.
- Network storage latency.
- CPU steal and host contention.
- Memory pressure and OS page cache.
- Disk errors and kernel logs.

A query with `DataFileRead` waits can stem from a query plan reading too many pages or from slow storage; gather evidence from both database and OS.

### 6.12. When are IO waits normal?

- Initial cache warm-up.
- Bulk loads and index builds.
- Backups and restores.
- Intentional sequential scans.
- Checkpoints or vacuum runs.
- Sudden workload spikes.

Compare against baselines for the same hour/day and workload. Alert on duration and impact rather than every occurrence.

---

## 7. Client Waits

### 7.1. What is a Client wait?

`wait_event_type='Client'` indicates a backend is waiting on client socket activity. Two common events are:

- `ClientRead`: PostgreSQL is waiting for the client to send the next data/command.
- `ClientWrite`: PostgreSQL is waiting to send data back to the client.

This category is easy to misread because a client wait is often the normal state of an idle connection.

### 7.2. ClientRead when state=idle

A connection pool keeping connections open for reuse typically exhibits:
- `state='idle'`.
- `wait_event_type='Client'`.
- `wait_event='ClientRead'`.

The backend is simply awaiting the next command. This is not a database bottleneck; it is an idle connection.

### 7.3. ClientRead when idle in transaction

If a session shows:
- `state='idle in transaction'`.
- `wait_event='ClientRead'`.
- Very old `xact_start`.

PostgreSQL is waiting for the client to continue the transaction, yet the transaction remains open. It can hold locks and snapshots, prevent vacuum from cleaning dead tuples, retain relation locks, and cause bloat even without an active query.

This is an application lifecycle issue even though the wait event is `Client`. Inspect transaction age, owner, `application_name`, and code paths.

### 7.4. ClientWrite

`ClientWrite` means the server is attempting to send data, but the socket or client has not drained enough for the server to proceed. Possible causes:
- Slow row processing in the client.
- Application not reading the full result set.
- Network latency, packet loss, or congestion.
- Oversized result sets.
- Client process paused, in GC, or CPU-starved.
- Congested proxy, load balancer, or socket buffer.

Do not assume this is PostgreSQL storage I/O. The server may have finished reading data and be encountering backpressure on the return path.

### 7.5. Queries returning too many rows

A query lacking `LIMIT` or pagination can return millions of rows. PostgreSQL sends the results; if the client reads slowly, the backend can wait on `ClientWrite`. Typical fixes include:
- Limiting the result set.
- Using pagination or keyset pagination.
- Implementing proper streaming or batching.
- Avoiding loading entire datasets into memory.
- Reviewing the query plan and payload size.

### 7.6. ClientRead does not mean the application is broken

Healthy connection pools maintain many idle sessions. A high `ClientRead` count is not proof the database is hung. Distinguish:
- Idle outside a transaction: usually normal.
- `idle in transaction`: creates operational risk.
- Active query with `ClientWrite`: inspect output size and network.
- Connection count exceeding pool budget: inspect pool sizing and app lifecycle.

### 7.7. Client waits and connection pools

Monitor:
- Active/idle/idle-in-transaction counts.
- Pool max size and application-side wait queues.
- Connection churn.
- Client connection age.
- Transaction age.
- `ClientWrite` durations.
- Application CPU, GC, and network.

PostgreSQL cannot see full request states inside the connection pool. Correlate database PID/`application_name` with application trace/request IDs when available.

### 7.8. Inspecting client waits

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
    clock_timestamp() - state_change AS time_in_state,
    clock_timestamp() - xact_start AS transaction_age,
    query
FROM pg_stat_activity
WHERE wait_event_type = 'Client'
ORDER BY state_change;
~~~

Always pay close attention to `state` when interpreting `ClientRead` and `ClientWrite`.

### 7.9. When clients fail to read results

If many sessions are `active` + `ClientWrite`:
1. Check query/result size.
2. Check client CPU, memory, and GC.
3. Check network throughput and retransmits.
4. Check proxy/pool behavior.
5. Check whether the application consumes rows sequentially or abandons reads mid-stream.
6. Reduce result size or improve client consumption.
7. Verify connections/queries are closed and canceled properly.

### 7.10. When clients hold transactions open

If `idle-in-transaction`:
1. Identify app, user, PID, and transaction age.
2. Inspect the last query and `xact_start`.
3. Check blocker chains and vacuum impact.
4. Inspect application logs/traces.
5. Fix code to guarantee commit/rollback on every branch.
6. Enforce transaction timeouts per policy.
7. Terminate sessions only after confirming owner and impact.

---

## 8. Quick Comparison: Lock, I/O, and Client Waits

| Symptom | Lock Wait | I/O Wait | Client Wait |
|---|---|---|---|
| wait_event_type | Lock | IO | Client |
| Example events | transactionid, relation | DataFileRead, WALSync | ClientRead, ClientWrite |
| Typical cause | Another transaction holds a lock | Backend waiting on read/write/flush | Client not sending or reading data |
| First tool | pg_blocking_pids(), pg_locks | pg_stat_io, plan, OS metrics | state, app/network metrics |
| Signal to look for | Blocker and lock age | Latency/throughput/plan | Idle transaction or slow consumer |
| Common action | Controlled finish/resolution of blocker | Optimize query or fix storage | Fix client/pool/network/result handling |

### 8.1. Interpretation examples

**Example A:** `UPDATE` query in `active` state, wait event `Lock/transactionid`, `pg_blocking_pids` returns PID 1200. Investigate PID 1200's transaction first.

**Example B:** `SELECT` query in `active` state, wait event `IO/DataFileRead`, no blockers. Check query plan, buffers, storage latency, and cache.

**Example C:** `idle` session, `Client/ClientRead`, no open transaction. This is typically a normal pooled connection.

**Example D:** `idle in transaction` session, `Client/ClientRead`, transaction age 25 minutes. Investigate the application holding the transaction; it may be blocking others even though no query is active.

**Example E:** `active` query, `Client/ClientWrite`, and high app CPU. Inspect client consumption and network before scaling database resources.

### 8.2. Wait events vs. CPU-bound queries

An `active` query with `wait_event` NULL may be CPU-bound. Check:
- Per-process and host CPU usage.
- `EXPLAIN ANALYZE`.
- Sorts, hashes, and aggregations.
- Function CPU cost.
- Parallel workers.
- Cardinality estimates and plan choices.
- OS scheduler and load.

Do not hunt for blockers when there are no `Lock` waits or lock-conflict evidence.

---

## 9. Sampling Wait Events and Historical Analysis

### 9.1. pg_stat_activity is a current snapshot

Each query against `pg_stat_activity` returns only state at the moment of observation. If a query waits 200 ms on a lock between 10-second polling intervals, dashboards may never catch that wait.

Not seeing a wait once does not prove no waits occur. Seeing a wait once does not tell you how long it has been waiting beforehand.

### 9.2. Periodic sampling

A monitoring agent or external job can periodically sample:
- UTC timestamp.
- PID and backend type.
- Database, user, application, and client.
- State and `wait_event_type`/`wait_event`.
- Query ID if available.
- Query and transaction age.
- Blocking PID list.
- Relevant LSN or I/O metrics when needed.

There is no need to store raw query text for every sample. Prefer query ID, application name, wait category, and durations; protect sensitive data.

### 9.3. Sampling intervals

Choose intervals according to goals:
- 1–5 seconds: captures short waits and supports incident troubleshooting, at higher telemetry volume.
- 10–30 seconds: everyday operational dashboards.
- 1 minute or more: long-term trends, though short waits may be missed.

These are only guidelines. Measure overhead and retention costs. You can increase sampling frequency during active alerts and lower it during normal operation.

### 9.4. Counting samples by wait group

Once samples are stored in an external monitoring table or metrics store, you can aggregate:
- Counts by `wait_event_type`/`wait_event`.
- Distinct PIDs and query IDs.
- Consecutive samples where a backend remains in the same wait.
- Share of samples in `Lock`/`IO`/`Client`.
- Wait groups by application and database.
- Correlation with latency and throughput.

Sample counts do not equal total wait milliseconds if intervals vary or waits shift between samples. Never multiply sample counts by an interval to claim exact wait time when samples drop or jitter exists.

### 9.5. pg_wait_sampling and external tools

Third-party extensions such as `pg_wait_sampling` collect wait-event history on supported setups. Extensions must be installed, configured, and verified for major-version compatibility; they are not included by default in every PostgreSQL installation.

Monitoring vendors can also gather wait profiles. Verify retention, sampling frequency, privacy, and overhead before enabling.

### 9.6. Combining with pg_stat_statements

`pg_stat_statements` stores aggregate execution statistics by query. It excels at finding queries consuming heavy total time or blocks, though it does not record a full wait-event timeline per execution.

Use both sources together:
- Wait sampling: what backends are waiting on.
- `pg_stat_statements`: which queries drive high workload/time/blocks.
- `EXPLAIN`: which plan produces that workload.
- OS metrics: which resource layer is saturating.

### 9.7. Correlating with application traces

Assign structured `application_name` values, such as service/env/role. If the application carries request IDs or trace IDs, log the mapping between requests and PID/query ID in application telemetry. PostgreSQL itself does not track the connection pool's request lifecycle.

### 9.8. Query age is not wait duration

`clock_timestamp() - query_start` is total elapsed time since the query started, not how long the query has spent in its current wait event. `state_change` records when `state` last changed; it does not tell when the current wait event started if the wait event changed without a state change.

If precise wait durations are required, sample at higher frequency or use wait-history instrumentation.

---

## 10. Dashboards and Alerting

### 10.1. Wait-category dashboard

Include:
- Active backends by `wait_event_type`.
- Top N wait events.
- Active queries currently waiting.
- Lock waiters and blocker counts.
- Longest transaction and `idle-in-transaction` ages.
- I/O wait samples by event.
- `ClientRead`/`ClientWrite` samples.
- Query latency and throughput.
- CPU, storage latency, and network throughput.
- Application pool saturation.

### 10.2. Lock dashboard

Display:
- Waiter PID, app, and query age.
- Blocker PID, app, state, and transaction age.
- Lock event, resource, and mode.
- Number of blocked sessions.
- Root blocker and chain depth.
- Relation/table if applicable.
- Incident start time and owner.

### 10.3. I/O dashboard

Display:
- I/O wait samples by event.
- Read/write/sync timings.
- `pg_stat_io` counters by backend/object/context on PG16+.
- `pg_stat_database` blocks and timings.
- `pg_stat_statements` shared and temp blocks.
- Storage latency, IOPS, throughput, and queue depth.
- Checkpoint activity and WAL rate.

### 10.4. Client dashboard

Display:
- `ClientRead` sessions idle outside transactions.
- `idle-in-transaction` sessions and transaction ages.
- `ClientWrite` active sessions.
- Connection pool active, idle, and waiting counts.
- Result sizes and rows returned.
- Network latency and retransmits.
- Application CPU, GC, and consumer lag.

### 10.5. Sample Lock alerts

Alert when:
- A `Lock` waiter persists beyond threshold.
- A single blocker stalls many sessions.
- Transaction age breaches SLA.
- An `idle-in-transaction` session holds locks for too long.
- A DDL migration blocks production traffic.

Thresholds must reflect workload norms. A brief lock wait inside a normal transaction does not merit an alert.

### 10.6. Sample I/O alerts

Alert when multiple signals align:
- Unusual jump in I/O wait samples.
- Storage latency/queue exceeds baseline.
- Query latency/throughput degrades.
- IOPS or throughput quotas are hit.
- Checkpoint or WAL sync pressure rises.

Never alert merely because `DataFileRead` appears; read waits can be completely normal.

### 10.7. Sample Client alerts

Alert when:
- Active `ClientWrite` persists and affects multiple sessions.
- `idle-in-transaction` exceeds maximum allowed age.
- Connection pool wait queues grow.
- `ClientWrite` coincides with network retransmits or app CPU saturation.
- Connection counts surge abnormally.

`ClientRead` on an idle session outside a transaction should generally not trigger an alert.

### 10.8. Alerts must carry context

A good alert includes:
- Cluster/database.
- Wait category and event.
- PID, query ID, and application.
- Duration or consecutive sample count.
- Blocker details if applicable.
- Corresponding resource metrics.
- Runbook link and owner.
- Last known good baseline.
- Clear condition.

---

## 11. Runbook: Investigating Lock Waits

### 11.1. Determine scope

1. Query `pg_stat_activity`.
2. Filter for `active` + `Lock` waits.
3. Count waiters and affected applications.
4. Record query age and transaction age.
5. Identify blocked tables or operations.

### 11.2. Locate blockers

Use `pg_blocking_pids()` to find direct blockers. Inspect:
- PID, user, application, and client.
- State and `xact_start`.
- Last or current query.
- Held locks.
- Whether the blocker itself is waiting on another blocker.

If the blocker is also waiting, walk up the chain to the root blocker.

### 11.3. Classify the blocker

- Long-running transaction updating data.
- `idle in transaction`.
- DDL holding `ACCESS EXCLUSIVE`.
- Batch job or import.
- Application-managed advisory lock.
- Maintenance task.
- Orphaned session whose connection remains open.

### 11.4. Choose an action

Order of preference:
1. Contact the owner/application team if the blocker is a valid transaction.
2. Let the transaction finish if the remaining time is acceptable.
3. Stop or throttle the batch job per runbook.
4. Cancel the query if stopping the statement and rolling back safely suffices.
5. Terminate the session if releasing locks is urgent and rollback/unknown outcome impacts are assessed.

`pg_cancel_backend(pid)` requests query cancellation; `pg_terminate_backend(pid)` closes the session and rolls back any open transaction. Both require proper privileges and impact assessment. Never automate this solely off a single wait event.

### 11.5. Post-remediation verification

- Waiter queue drains.
- Blocked queries resume or clients receive clear errors.
- Blocker transaction ends.
- Application retries respect idempotency.
- No duplicate business actions occur.
- No lingering lock storm remains.
- Record root cause and owner.

---

## 12. Runbook: Investigating I/O Waits

### 12.1. Identify the event

Distinguish `DataFileRead`/`Write`/`Extend`/`Sync`, `WALRead`/`Write`/`Sync`, and temp/SLRU events according to version. Record session counts, sample durations, and query IDs.

### 12.2. Locate workload-driving queries

Use `pg_stat_statements` to rank by:
- `shared_blks_read`.
- `temp_blks_read`/`written`.
- `total`/`mean` execution time.
- Calls and rows.
- Query ID.

Select representative queries and inspect `EXPLAIN (ANALYZE, BUFFERS)`. Remember `ANALYZE` executes the query.

### 12.3. Inspect storage

Cross-check database findings with OS/cloud metrics:
- Latency and read/write IOPS.
- Throughput and queue depth.
- Burst credits and throttling.
- Volume saturation.
- Filesystem free space.
- Kernel/device errors.
- Network storage health.

### 12.4. Inspect checkpoints and WAL

If `WALSync`/`WALWrite` or data-file syncs climb:
- Check commit rate and `synchronous_commit`.
- Check checkpoint frequency and duration.
- Check WAL generation and archive pressure.
- Inspect storage `fsync` behavior.
- Check concurrent backup or maintenance jobs.

### 12.5. Inspect query plans

If `DataFileRead` is high:
- Are there unexpected sequential scans?
- Do indexes match predicates and sort order?
- Do row estimates differ sharply from actual rows?
- Is there table bloat or stale statistics?
- Is the query returning too many rows?
- Are join strategies or sort/hash spills occurring?

### 12.6. Remediate and verify

Depending on the cause:
- Optimize SQL, indexes, or statistics.
- Reduce temp spills.
- Adjust concurrency or `work_mem` carefully.
- Tune checkpoint pacing vs. storage capacity.
- Upgrade storage tier or IOPS/throughput quota.
- Reschedule backup or batch workloads.
- Monitor latency and throughput after changes.

Never increase `shared_buffers`/`work_mem` or alter storage settings based solely on an event name.

---

## 13. Runbook: Investigating Client Waits

### 13.1. Classify sessions

Filter `Client` waits and inspect `state`:
- `Idle` + `ClientRead`: pooled connection waiting for a command.
- `Idle in transaction` + `ClientRead`: application holding an open transaction.
- `Active` + `ClientWrite`: server sending results; client or network may be slow.

### 13.2. Idle in transaction

Inspect transaction age, last query, `application_name`, blocker list, and vacuum impact. Locate the code path failing to commit/roll back; prioritize fixing transaction lifecycles and timeout policies.

### 13.3. ClientWrite

Inspect rows/bytes returned, application consumer speed, network throughput/retransmits, proxies, and client CPU/GC. Shrink payloads, use pagination/streaming, and verify the application consumes and closes result sets properly.

### 13.4. Connection pools

Compare PostgreSQL backend counts with pool metrics:
- Pool max/active/idle counts.
- Wait queues and acquire timeouts.
- Connection leaks.
- Long transactions.
- Pool reset/session state behavior.
- Request durations.

Many idle connections can be normal; many `idle-in-transaction` sessions require action.

### 13.5. Verification

After remediation:
- `idle-in-transaction` count and age drop.
- `ClientWrite` waits decrease.
- Pool acquire latency improves.
- Connection churn does not spike.
- App logs show no leaked transactions or unclosed result cursors.
- No locks or snapshots remain held abnormally long.

---

## 14. Common Interpretation Pitfalls

### 14.1. “Having a wait event means the database is congested”

False. A wait event is a current state. You need duration, frequency, impact, and baseline context.

### 14.2. “ClientRead always means a broken client”

False. Idle connection pools normally sit in `ClientRead`. Investigate deeply only when sessions hold transactions or exhibit abnormal connection lifecycles.

### 14.3. “ClientWrite means a slow disk”

Not necessarily. `ClientWrite` involves the server-to-client socket; slow clients, network congestion, or large result sets are typical causes.

### 14.4. “Lock wait means terminate the blocker”

Not always true. The blocker may be a legitimate transaction, migration, or batch job. Terminating forces a rollback and can leave the application with unknown outcomes.

### 14.5. “IO wait proves the storage device is failing”

No. Queries might be scanning too many pages, missing cache, spilling to temp, or competing for bandwidth. Cross-check storage metrics and plans.

### 14.6. “LWLock is just like a row lock”

No. `LWLock` protects internal shared-memory structures; do not treat `pg_blocking_pids` as a general fix for it.

### 14.7. “Query age equals wait duration”

No. `query_start` measures total elapsed time since query start. The current wait event may have started very recently.

### 14.8. “No wait event means the query is fast”

No. The query may be CPU-bound, delayed by the OS scheduler, or running code with no instrumented wait point. Check CPU and plan.

### 14.9. “One sample is enough to conclude”

No. Waits shift rapidly. Repeated sampling and correlation with historical metrics reveal real patterns.

### 14.10. “pg_stat_activity stores history”

No. It is a live snapshot. Collecting wait history requires sampling or a dedicated extension.

---

## 15. PostgreSQL Reference Documentation

Prefer documentation matching your major version:

- [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity`, `pg_locks`, and wait events.
- [PostgreSQL — Wait Events](https://www.postgresql.org/docs/current/monitoring-stats.html#WAIT-EVENT-TABLE): wait event catalog and meanings.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): lock modes and conflict behavior.
- [PostgreSQL — System Catalogs: pg_locks](https://www.postgresql.org/docs/current/view-pg-locks.html): lock details.
- [PostgreSQL — pg_stat_io](https://www.postgresql.org/docs/current/monitoring-stats.html): I/O statistics, depending on major version.
- [PostgreSQL — pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html): query-level aggregate statistics.
- [PostgreSQL — Runtime Statistics Configuration](https://www.postgresql.org/docs/current/runtime-config-statistics.html): `track_io_timing` and runtime statistics.

`/current/` URLs may point to a newer major version. Verify wait event names, view columns, and extension support against your running release.

---

## 16. Lab: Reading Wait Events

### 16.1. Inspect backend states

~~~sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS query_age,
    clock_timestamp() - xact_start AS xact_age
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
ORDER BY query_start NULLS LAST;
~~~

Record:
- Active sessions.
- Idle sessions.
- `idle-in-transaction` sessions.
- Which wait categories appear.

### 16.2. Create a normal ClientRead

Open a `psql` session and leave it at the prompt awaiting commands. From another session, query `pg_stat_activity`. The session waiting for input will appear as `ClientRead`/`idle`. This is a healthy, normal connection.

### 16.3. Create an idle in transaction

In a lab session:

~~~sql
BEGIN;
SELECT now();
-- Keep the session open, without COMMIT or ROLLBACK.
~~~

From another session, inspect `state`, `ClientRead`, and `xact_start`. End the lab with:

~~~sql
ROLLBACK;
~~~

Never leave test transactions open long on shared environments.

### 16.4. Create a Lock wait

Session A:

~~~sql
CREATE TABLE IF NOT EXISTS wait_lab (
    id integer PRIMARY KEY,
    value text
);

INSERT INTO wait_lab VALUES (1, 'before')
ON CONFLICT (id) DO UPDATE SET value = EXCLUDED.value;

BEGIN;
UPDATE wait_lab SET value = 'session-a' WHERE id = 1;
-- Keep the transaction open.
~~~

Session B:

~~~sql
UPDATE wait_lab SET value = 'session-b' WHERE id = 1;
~~~

Session B will wait on session A's row lock/transaction. Inspect `pg_stat_activity`, `pg_blocking_pids`, and `pg_locks`. Afterward, `COMMIT` or `ROLLBACK` session A.

### 16.5. Generate an I/O workload

On a sufficiently large lab dataset, run an intentional sequential scan or sort. Observe wait events and `EXPLAIN (ANALYZE, BUFFERS)`. Behavior depends on cache, storage, and dataset size; you may not always see an `IO` wait if data is already cached in memory.

### 16.6. Observe pg_stat_io

On PostgreSQL 16+:

~~~sql
SELECT *
FROM pg_stat_io
ORDER BY backend_type, object, context;
~~~

Run before and after the workload and compare counters and timings. This view aggregates across dimensions and does not map individual rows directly to PIDs.

### 16.7. Test ClientWrite

Run a query returning many rows in the lab with a deliberately slow-reading client. Observe `ClientWrite` if socket backpressure develops. Never generate huge result sets or exhaust memory/network in production.

---

## 17. Practice Exercises

Perform these exercises in a PostgreSQL lab. Never kill sessions or induce I/O overload in production just to observe waits.

### Exercise 1 — Wait events

What does a wait event indicate? Is it an error code?

### Exercise 2 — Two key fields

Distinguish `wait_event_type` and `wait_event`.

### Exercise 3 — Active state

A backend shows `state=active`, `wait_event_type=Lock`. Is that backend continuously burning CPU?

### Exercise 4 — ClientRead

Is an `idle` + `ClientRead` session necessarily an error? Why or why not?

### Exercise 5 — ClientWrite

What does `ClientWrite` generally indicate? List three possible causes.

### Exercise 6 — Lock

An `UPDATE` query waits on `Lock/transactionid`. Which tool helps find the direct blocker?

### Exercise 7 — Blocker query

Write a query showing waiter PID, blocker PID, `application_name`, and blocker transaction age.

### Exercise 8 — pg_locks

What does `granted=false` mean? Why is querying `pg_locks` alone insufficient for tracing full blocker chains?

### Exercise 9 — Idle in transaction

Why can `idle in transaction` cause bloat or block DDL even when no query is active?

### Exercise 10 — LWLock

How does `LWLock` differ from a heavyweight `Lock`? Should `pg_blocking_pids` be used to locate blockers for all `LWLock` waits?

### Exercise 11 — BufferPin

What does a `BufferPin` wait describe? Why should it not be treated as a row lock?

### Exercise 12 — DataFileRead

Does `DataFileRead` prove storage hardware is failing? What should you check?

### Exercise 13 — WALSync

What does a `WALSync` wait suggest the backend is waiting on? List several possible causes.

### Exercise 14 — Temporary files

What type of I/O can sort/hash spills to temp files generate? Which metrics should you inspect?

### Exercise 15 — pg_stat_io

Which PostgreSQL major version introduced `pg_stat_io`? Along which dimensions does it break down statistics?

### Exercise 16 — track_io_timing

When do `blk_read_time`/`blk_write_time` contain useful timings? What must you consider before enabling it?

### Exercise 17 — Cache hit ratio

Why does a high cache hit ratio not guarantee fast queries?

### Exercise 18 — Query age

Does `query_start` age equal current wait duration? Explain.

### Exercise 19 — Sampling

Why is a single query of `pg_stat_activity` insufficient to establish a wait pattern?

### Exercise 20 — Historical waits

Does `pg_stat_activity` store wait history? What options exist to collect historical wait data?

### Exercise 21 — pg_stat_statements

How do `pg_stat_statements` and wait sampling complement each other?

### Exercise 22 — CPU-bound

A query is active with `wait_event` NULL. List investigation paths outside locks and I/O.

### Exercise 23 — Lock chains

A blocker is itself waiting on another backend. Which node in the chain must you locate to fix the root cause?

### Exercise 24 — Terminating blockers

Why should you avoid terminating a blocker solely because it is blocking many sessions?

### Exercise 25 — ClientRead inside a transaction

A session has been `idle in transaction` + `ClientRead` for 20 minutes. What information should you inspect?

### Exercise 26 — ClientWrite

A query returns millions of rows and the backend waits on `ClientWrite`. List application- and query-side fixes.

### Exercise 27 — Wait taxonomy

Distinguish `Lock`, `IO`, and `Client` using example events and the first diagnostic tool to reach for.

### Exercise 28 — Checkpoints

How can checkpoints impact I/O waits? Which metrics should you correlate?

### Exercise 29 — Alerting

Why should you not fire an alert solely whenever `wait_event_type='IO'` appears?

### Exercise 30 — Combined incident

A dashboard shows 50 `active/Lock` backends, 1 `idle in transaction` blocker open for 30 minutes, and 200 `idle/ClientRead` sessions. Classify the impact and prioritize remediation.

---

## 18. Solutions — Exercises 1 to 15

### Exercise 1 — Wait events

It indicates where a backend or process is waiting at sampling time. It is not an error code; a wait can be normal or signal a bottleneck depending on duration and impact.

### Exercise 2 — Two key fields

`wait_event_type` is the category such as `Lock`/`IO`/`Client`; `wait_event` is the specific name such as `transactionid`/`DataFileRead`/`ClientRead`.

### Exercise 3 — Active state

No. `active` means a query is in flight; when a wait event is set, the backend is currently blocked at that wait point rather than making continuous CPU progress.

### Exercise 4 — ClientRead

No. An idle connection in a pool normally sits in `ClientRead` waiting for the next command. It is concerning only if holding an open transaction, excessive connections, or an abnormal lifecycle.

### Exercise 5 — ClientWrite

The server is waiting to send data to the client. Possible causes include a slow-consuming client, network/proxy congestion, or an overly large result set.

### Exercise 6 — Lock

Call `pg_blocking_pids(waiter_pid)` to find direct blockers; then inspect `pg_stat_activity` and `pg_locks`.

### Exercise 7 — Blocker query

~~~sql
SELECT
    w.pid AS waiter_pid,
    w.application_name AS waiter_app,
    b.pid AS blocker_pid,
    b.application_name AS blocker_app,
    clock_timestamp() - b.xact_start AS blocker_xact_age
FROM pg_stat_activity AS w
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(w.pid)) AS p(blocker_pid)
JOIN pg_stat_activity AS b
    ON b.pid = p.blocker_pid;
~~~

### Exercise 8 — pg_locks

`granted=false` indicates a waiting lock request. `pg_locks` lists requested and held locks, but piecing together the conflict chain manually is cumbersome; `pg_blocking_pids` computes direct blockers conveniently.

### Exercise 9 — Idle in transaction

An open transaction can hold locks and old snapshots for a long time, preventing vacuum from cleaning up dead tuples and forcing DDL to wait for locks. Even with no active query, the transaction still exists.

### Exercise 10 — LWLock

`LWLock` is an internal synchronization primitive for shared-memory structures; heavyweight `Lock` coordinates database objects and transactions. `pg_blocking_pids` is primarily for heavyweight lock blockers, not a universal tool for all `LWLock` waits.

### Exercise 11 — BufferPin

The backend is waiting for a shared buffer pin to be released. A pin prevents buffer reuse during an operation; it is not a row-level lock.

### Exercise 12 — DataFileRead

No. It shows the backend is waiting to read a data file. Check query plans, buffer reads/hits, storage latency, IOPS/queues, cache, and workload.

### Exercise 13 — WALSync

The backend or process is waiting for WAL sync/flush per version event semantics. Possible causes include commit `fsync`, storage latency, checkpoint/WAL activity, or high concurrency.

### Exercise 14 — Temporary files

Sort/hash spills generate temp file reads and writes. Check `temp_blks_read`/`written` in `pg_stat_statements`, `EXPLAIN BUFFERS`, `work_mem`, and the query plan.

### Exercise 15 — pg_stat_io

`pg_stat_io` was added in PostgreSQL 16. It aggregates I/O by `backend_type`, `object`, and `context`; check exact columns for your major version.

### Exercise 16 — track_io_timing

`blk_read_time`/`blk_write_time` contain meaningful timing only when `track_io_timing` is enabled. Evaluate platform/workload overhead, configuration privileges, and baseline impact before enabling broadly.

### Exercise 17 — Cache hit ratio

A query can read millions of cached buffers and still burn heavy CPU in joins or sorts; hit ratio reflects neither absolute page counts, plan quality, nor overall storage latency.

### Exercise 18 — Query age

No. `query_start` age is total elapsed time since query start; a query can pass through multiple wait events or run CPU work between waits.

### Exercise 19 — Sampling

Wait events can shift rapidly and `pg_stat_activity` is only a snapshot. One sample can miss brief waits or fail to reflect duration and impact. Sample repeatedly and correlate metrics.

### Exercise 20 — Historical waits

`pg_stat_activity` does not retain history. Use a monitoring agent that samples periodically, an extension like `pg_wait_sampling` if compatible, or a monitoring platform with wait profiling.

### Exercise 21 — pg_stat_statements

`pg_stat_statements` gives aggregate query workload, time, and blocks; wait sampling shows what backends wait on over time. Combine them to link queries to resource bottlenecks.

### Exercise 22 — CPU-bound

Check per-process and host CPU utilization, `EXPLAIN ANALYZE`, cardinality estimates, sort/hash/aggregation costs, functions, parallel workers, and OS scheduler load.

### Exercise 23 — Lock chains

Trace back along the blocker chain to the root blocker—the backend holding the resource that prevents downstream waiters from progressing. Check the root blocker's transaction age and business owner.

### Exercise 24 — Terminating blockers

The blocker may be a valid transaction or an essential migration. Termination forces a rollback, adds I/O, and leaves the client with an unknown outcome; verify owner and impact first.

### Exercise 25 — ClientRead inside a transaction

Inspect PID/user/application/client, `xact_start`, `state_change`, last query, held locks, `pg_blocking_pids`, vacuum impact, application traces, and why code failed to commit or roll back.

### Exercise 26 — ClientWrite

Reduce result size, add `LIMIT`/pagination, use streaming/batching, trim payload columns, ensure the client consumes the entire result set, and check client CPU/GC and network/proxies.

### Exercise 27 — Wait taxonomy

- `Lock/transactionid`: query waiting on transaction/row conflict; inspect with `pg_blocking_pids` and `pg_locks`.
- `IO/DataFileRead` or `WALSync`: waiting on file I/O; inspect with `pg_stat_io`, query plans, and OS/storage metrics.
- `Client/ClientRead` or `ClientWrite`: waiting on sockets; inspect `state`, application, pool, and network.

### Exercise 28 — Checkpoints

Checkpoints flush dirty buffers to data files, potentially creating write/sync pressure and competing with foreground queries for storage. Correlate checkpoint frequency/duration, WAL volume, storage latency/queue depth, and I/O waits.

### Exercise 29 — Alerting

I/O waits can be normal during cache warm-up, scans, backups, or vacuum. Alerts should require sustained duration/frequency alongside degraded latency, throughput, or resource saturation relative to baseline.

### Exercise 30 — Combined incident

The 50 `active/Lock` backends are likely blocked behind a root blocker; prioritize investigating the 30-minute `idle-in-transaction` blocker, identify its owner, locks, and business impact, and resolve in a controlled manner. The 200 `idle/ClientRead` sessions outside transactions likely represent a normal pool; verify their state and pool budget rather than treating them as 200 errors. After clearing the blocker, verify waiters drain, check vacuum/transaction age, and monitor application retries.

---

## 19. Quick Decision Table

| Observation | Initial Interpretation | Next Step |
|---|---|---|
| active + Lock | Query waiting on a heavyweight lock | `pg_blocking_pids`, `pg_locks`, blocker transaction |
| active + IO | Backend waiting on an I/O operation | Check event, plan, `pg_stat_io`, and storage |
| idle + ClientRead | Connection awaiting a new command | Usually normal; verify pool budget |
| idle in transaction + ClientRead | Transaction open with no query sent | Check xact age, locks, app lifecycle |
| active + ClientWrite | Server waiting to send results | Check client consumption, network, result size |
| active + LWLock | Internal shared-memory contention | Check specific event, concurrency, profiling |
| active + BufferPin | Waiting for a buffer pin release | Find long-running scan/cursor holding pins |
| active + wait_event NULL | Not at a wait point at sample time | Check CPU, query plan, OS scheduler |
| Many WALSync waits | Possible commit/WAL flush pressure | Check storage fsync, commit rate, WAL/checkpoints |
| Rising DataFileRead | Increasing read I/O or cache misses | Check buffers, query plan, storage latency |

---

## 20. Wait Event Incident Report Template

~~~text
Incident ID:
Observed at (UTC):
Cluster/database:
PostgreSQL version:
Affected application/service:
Affected PIDs/query IDs:
Wait event type/event:
Number of affected backends:
Longest query age:
Oldest transaction age:
Blocker PID(s), if any:
Query plan / I/O evidence:
Storage/network/application evidence:
User-visible impact:
Mitigation:
Root cause:
Follow-up action owner:
Retest/verification:
~~~

### 20.1. Lock report template

~~~text
Waiter PID/app:
Blocker PID/app:
Lock type/mode/resource:
Blocker transaction age:
Blocker state/query:
Blocked sessions:
Action taken:
Rollback/unknown outcome:
Verification:
~~~

### 20.2. I/O report template

~~~text
Wait event(s):
Affected query IDs:
Read/write/sync pattern:
pg_stat_io / pg_stat_database evidence:
EXPLAIN BUFFERS evidence:
Storage latency/IOPS/queue:
Mitigation:
Verification:
~~~

### 20.3. Client report template

~~~text
Client wait event:
Session state:
Application/pool:
Transaction age:
Result size/rows:
Network/client CPU/GC:
Application root cause:
Mitigation:
Verification:
~~~

---

## 21. Summary

Wait events tell you where a PostgreSQL backend is waiting, yet they must be interpreted alongside session state, query/transaction age, and resource metrics to pinpoint the root cause.

Key points to remember:

1. `wait_event_type` is the wait category; `wait_event` is the specific wait point.
2. `pg_stat_activity` is a live snapshot, not a historical wait log.
3. An `active` session may be waiting; `wait_event IS NULL` does not by itself prove a query is fast.
4. `Lock` waits usually call for finding blockers with `pg_blocking_pids()` and inspecting `pg_locks`.
5. `LWLock` and `BufferPin` differ from heavyweight SQL locks; do not apply the same remediation.
6. `IO` waits must be cross-checked with query plans, buffer statistics, `pg_stat_io`, and OS/storage metrics.
7. `pg_stat_io` was introduced in PostgreSQL 16; views and columns vary across versions.
8. `track_io_timing` must be enabled for read/write timings in the corresponding statistics; weigh its overhead.
9. `ClientRead` on an idle session outside a transaction is normally healthy.
10. `ClientRead` on an `idle-in-transaction` session can hold locks and snapshots and block vacuum.
11. `ClientWrite` typically signals server backpressure while sending results; check the client, network, and payload size.
12. Query age is not wait duration.
13. Repeated sampling and correlation with app/OS metrics reveal true patterns.
14. Never terminate a blocker based solely on a wait event; verify owner, rollback impact, and business outcome.
15. Alerts require sustained duration, frequency, and impact—not firing on every appearance of a wait.
16. Wait diagnosis must conclude with post-remediation verification: queries proceed, queues drain, latency recovers, and no unintended side effects arise.

Investigation workflow: **capture a `pg_stat_activity` snapshot → classify `state` and `wait_event_type` → locate blockers or workload/resources driving waits → correlate with I/O, network, and application metrics → apply controlled remediation → re-sample and verify impact has cleared**.
