# Coordinator Process, Connection-Serving Processes, and Background Processes in PostgreSQL

When an application opens a connection to PostgreSQL and runs `SELECT`, who receives that connection? Who parses the SQL, reads data pages, holds locks, and returns the results? When there are no user queries running, why does PostgreSQL still have active processes? Understanding the three groups—the **coordinator process**, **connection-serving processes**, and **background processes**—is essential for explaining PostgreSQL's structure, connection limits, disk write behavior, data maintenance, and troubleshooting.

In PostgreSQL's traditional model, the server operates using a **multi-process architecture**. One main process accepts connections and manages child process lifecycles. Each normal client connection is served by a dedicated **backend process**. Alongside them are background processes specialized for checkpoints, WAL writing, vacuuming, replication, and other tasks. These processes share access to **shared memory** regions and coordinate via internal synchronization mechanisms.

This lesson focuses on modern PostgreSQL, particularly versions 15–17, and architectural concepts that remain widely applicable. Process lists, display names, and some statistics mechanisms may vary by version or configuration; use the observation queries below to inspect the actual state on your server.

## 1. The Big Picture: What Components Make Up a PostgreSQL Server?

A PostgreSQL instance can be illustrated by the following diagram:

~~~mermaid
flowchart TD
    C1["Java / JDBC Application"] -->|TCP or Unix socket| PM["Main postgres process<br/>postmaster / supervisor"]
    C2["psql"] -->|TCP or Unix socket| PM

    PM --> B1["Client backend A<br/>serving JDBC"]
    PM --> B2["Client backend B<br/>serving psql"]
    PM --> BG["Background processes"]

    B1 <--> SH["Shared memory<br/>shared_buffers, lock tables, WAL buffers..."]
    B2 <--> SH
    BG <--> SH

    BG --> CK["Checkpointer"]
    BG --> BW["Background writer"]
    BG --> WW["WAL writer"]
    BG --> AV["Autovacuum launcher / workers"]
    BG --> RP["Replication / archive / other workers"]

    SH --> D["Data files and WAL files<br/>in storage"]
~~~

This diagram illustrates **roles and coordination paths**, not the exact function-call sequence of every SQL statement. For instance, a backend can directly perform necessary reads and writes; not every file operation must pass through the checkpointer or background writer.

Three groups must be distinguished immediately:

| Group | Primary role | Observed examples |
| --- | --- | --- |
| **Coordinator process** | Initializes the service, accepts connections, spawns and monitors child processes, and handles server lifecycle events | Main `postgres` process, historically called the *postmaster* |
| **Connection-serving process** | Handles a client session's requests: validates session context, parses/plans/executes SQL, manages transactions, and sends results | A `client backend` for `psql` or an application |
| **Background process** | Performs internal work, maintenance, disk writes, recovery, replication, or tasks not tied directly to a single client session | `checkpointer`, `background writer`, `walwriter`, `autovacuum worker`, `walsender`, `walreceiver` |

Important point: **a backend is also a PostgreSQL server process**, not a separate program created by JDBC on the application machine. Backends run on the server side and serve specific connections. Background processes can stay active even when no application is sending queries.

## 2. PostgreSQL Uses Processes, Not One Thread per Connection

On many operating systems, PostgreSQL processes appear in the OS process list under the name `postgres`. Seeing many `postgres` lines does not necessarily mean multiple independent servers. They are usually child processes of the **same instance** performing different functions.

Example conceptual process tree on a Unix-like system:

~~~text
postgres (main server / postmaster)
├── postgres: checkpointer
├── postgres: background writer
├── postgres: walwriter
├── postgres: autovacuum launcher
├── postgres: logical replication launcher
├── postgres: appdb app_user 10.0.0.21 idle
├── postgres: appdb app_user 10.0.0.22 SELECT
└── postgres: appdb reporting_user 10.0.0.30 idle
~~~

This list is **illustrative**, not guaranteed output from every PostgreSQL version. Some processes may be absent if the corresponding feature is disabled; others appear only when there is work to do. Process display names vary by operating system and monitoring tool.

On Unix-like systems, PostgreSQL typically uses platform-appropriate child-process creation such as `fork`. On Windows, child-process creation differs at the OS level, yet architecturally you still observe multiple **processes** with distinct roles. Therefore, do not describe PostgreSQL's architecture merely by saying "the server creates threads like some other DBMSs."

### 2.1. One connection usually pairs with one backend

When an application opens a normal connection:

1. The client connects to PostgreSQL's address/port.
2. The main process accepts the request and arranges a child process to serve the session.
3. The backend performs the required protocol steps and authentication, initializing session state.
4. The backend receives SQL statements and executes them within that same session.
5. The backend returns results to the client.
6. When the connection closes, the corresponding session backend exits.

A `SELECT` followed by an `UPDATE` sent **over the same connection** normally uses **the same backend**; PostgreSQL does not spawn a new process for every SQL statement. Conversely, two concurrent connections from the same application normally have two distinct client backends.

Diagram:

~~~text
Java Application                    PostgreSQL server
---------------------------------------------------------------
Connection A ---------------------> Backend PID 12001
    SELECT ...                           |
    BEGIN                                | same session
    UPDATE ...                           |
    COMMIT                               |

Connection B ---------------------> Backend PID 12002
    SELECT ...                       other session
~~~

The PIDs are example numbers only. In environments with a **connection proxy/pooler** in between, each application connection does not necessarily map one-to-one to a server connection at all times; pooling is explained in section 11.

### 2.2. A backend does not own a copy of the entire database

Even though backends are separate processes, they do not load private copies of all tables into memory. Backends share instance-wide resources such as:

- **Shared buffers:** the shared page cache for table and index pages in use.
- **WAL buffers:** memory supporting creation of write-ahead log records.
- **Lock and transaction state:** enabling processes to coordinate concurrent access.
- **Internal coordination, statistics, and synchronization structures**.

Each backend also has **private memory** for session state, query plan trees, execution operators, and other local structures. These two memory categories are distinct, so connection limits are directly tied to RAM management.

## 3. The Main Process: Postmaster Coordinating the Server Lifecycle

In PostgreSQL documentation and history, the main process is commonly called the **postmaster**. On most systems, the executable is named `postgres`, and server functions are started via `pg_ctl`, a service manager, or managed database infrastructure.

High-level responsibilities of the main process:

1. Initialize and manage the instance lifecycle.
2. Set up shared resource mechanisms and structures required by the server.
3. Listen for client connections over TCP or Unix-domain sockets according to configuration.
4. Spawn/start connection-serving processes and required background processes.
5. Monitor child processes, handle stop/reload signals, and coordinate shutdown.
6. Participate in handling abnormal server events, such as a backend crashing in a way that could jeopardize shared memory consistency.

### 3.1. The main process does not execute every SELECT itself

A common misconception is that "the postmaster receives SQL statements and runs them itself." In normal execution, the session's backend parses, plans, executes, and returns results. The main process primarily acts as a **supervisor/coordinator**, not as the executor of every application query.

This explains why with 100 connections to one PostgreSQL instance, an administrator sees many backends yet still only **one main process** for that instance.

### 3.2. When a backend encounters an error

Not every SQL error kills a backend. For example, a `UNIQUE` constraint violation normally just returns an error to the session; PostgreSQL places any open transaction into an aborted state requiring `ROLLBACK`, while the connection and backend remain alive.

By contrast, if a backend crashes severely and PostgreSQL suspects shared memory state may no longer be safe, the coordinator process may signal other backends to exit, reinitialize internal structures, and perform recovery before allowing normal connections again. That is far more serious than a routine SQL syntax error.

Do not confuse "a statement returned an error" with "a PostgreSQL process crashed."

### 3.3. Start, reload, and restart are different

| Action | Meaning | Notes |
| --- | --- | --- |
| **Reload configuration** | Tells PostgreSQL to reload parameters supporting reload and corresponding config info | Not every parameter takes effect on reload |
| **Restart** | Stops and starts the server again per administrative procedure | Interrupts active sessions and transactions |
| **Controlled shutdown** | Stops the service using an appropriate shutdown mode | Impact on open connections depends on shutdown mode |
| **Crash recovery** | Reads storage/WAL state to recover after an abnormal termination | Not equivalent to simply reloading config files |

An administrative SQL statement to request a configuration reload, when run by an appropriately privileged role:

~~~sql
SELECT pg_reload_conf();
~~~

This function returns whether the reload signal was sent successfully; **it does not prove that every setting is valid or has taken effect**. Some parameters require a restart. Check `pg_settings` metadata and server logs to verify accurately.

## 4. Backend Process: Where the SQL Session Is Served

A client backend handles the core stages of the query lifecycle:

~~~mermaid
flowchart TD
    A["Client sends SQL"] --> B["Backend receives message"]
    B --> C["Parse / analyze / rewrite"]
    C --> D["Planner chooses plan"]
    D --> E["Executor executes"]
    E --> F["Access shared buffers, indexes, heap, and locks"]
    F --> G["Read/write data; WAL if needed"]
    G --> H["Return rows, command tag, or error"]
    H --> I["Backend waits for next command in same session"]
~~~

These components form a simplified model; prepared statements can perform certain steps at different times, and utility or administrative commands do not necessarily follow the exact same flow as `SELECT`.

### 4.1. Backends maintain session state

A PostgreSQL connection can hold:

- Current transaction state and isolation level.
- Session settings such as `search_path` or `statement_timeout`.
- Prepared statements and other session-bound objects.
- Temporary tables, if created by the session.
- Cursor states and transaction-level or session-level advisory locks when used.

Example on one connection:

~~~sql
SET application_name = 'lesson_55_psql';
SET search_path = public;

SELECT
    pg_backend_pid() AS my_backend_pid,
    current_database() AS my_database,
    current_user AS my_role,
    current_setting('application_name') AS app_name;
~~~

`pg_backend_pid()` returns the PID of the backend currently serving this connection. Running two separate `psql` sessions typically yields two different PIDs.

### 4.2. One transaction can contain multiple statements

~~~sql
BEGIN;

SELECT txid_current() AS current_xid;

-- Subsequent read/write statements on the same connection
-- participate in the current transaction until COMMIT or ROLLBACK.

ROLLBACK;
~~~

`txid_current()` can assign/consume a transaction ID and is unnecessary for ordinary read operations; use it only in labs when observing transaction semantics. Newer PostgreSQL versions also provide transaction ID functions using newer data types; do not rely on transaction ID values to identify a backend or session.

Distinguish clearly:

- **Connection/session:** spans from client login until disconnection, and can contain many transactions.
- **Transaction:** started by `BEGIN` or implicitly via autocommit, ended by `COMMIT`/`ROLLBACK`.
- **Statement:** an individual SQL command inside a transaction.
- **Backend process:** the process serving a connection, capable of executing many statements and transactions across the session lifetime.

An HTTP request might borrow a connection from a pool to run multiple SQL statements; afterward, the connection may be returned to the pool **without closing**, so the server backend stays alive in the `idle` state.

### 4.3. Why can a waiting backend still consume resources?

In `pg_stat_activity`, a backend can report states such as:

| `state` | Interpretation |
| --- | --- |
| `active` | The backend is executing a query |
| `idle` | Not executing a query right now; waiting for the next command |
| `idle in transaction` | A transaction remains open, but no SQL statement is currently running |
| `idle in transaction (aborted)` | An open transaction hit an error and must end with rollback |
| `fastpath function call` or other states | Depends on active functionality/version |

**`idle` does not mean the connection consumes zero resources**: the backend still holds memory and a connection slot. **`idle in transaction` is more concerning** because the session may hold locks, retain a snapshot, or prevent cleanup of old row versions needed for MVCC. Applications should therefore avoid opening a transaction and then making external HTTP calls or waiting indefinitely for user input.

## 5. Shared Memory and Inter-Process Coordination

A multi-process architecture requires a way to exchange state. PostgreSQL uses **shared memory** and appropriate synchronization primitives so backends and background processes operate on shared structures.

~~~text
                  Shared memory of one instance
  +----------------------------------------------------+
  | shared_buffers: page cache for heap and indexes    |
  | WAL buffers: WAL records prior to being written    |
  | lock structures: access synchronization info       |
  | transaction status / other internal state          |
  +----------------------------------------------------+
       ^                 ^                   ^
       |                 |                   |
   Backend A         Backend B         Background process
  (private RAM)     (private RAM)        (private RAM)
~~~

### 5.1. Shared buffers

`shared_buffers` configures the size of PostgreSQL's shared page buffer cache. A backend may need to read a table page from storage; if the page is already cached, it can use that buffered copy. If modified, the cached page becomes a **dirty buffer** until written out to data files.

~~~sql
SHOW shared_buffers;
~~~

Do not confuse `shared_buffers` with total RAM used by PostgreSQL. The system also uses **private backend memory**, operating system page cache, memory for parallel workers, maintenance operations, and other components.

### 5.2. Private backend memory

A query with `ORDER BY` or `GROUP BY` can allocate memory for sorting or hashing. The `work_mem` parameter sets a threshold per **sort/hash operation**, not a fixed RAM cap for the entire server or even a single connection.

~~~sql
SHOW work_mem;
SHOW maintenance_work_mem;
~~~

A complex query can contain multiple memory-consuming operators, and many backends can run concurrently. If each backend runs multiple sorts/hashes, total RAM consumption can far exceed a single `work_mem` value. In supported versions, `hash_mem_multiplier` also affects memory limits for hash operations.

That is why you cannot pick `max_connections = 1000` and `work_mem = 100MB` and assume only a few hundred MB of RAM are needed. You must evaluate **process count, operator count, and realistic concurrency together**.

### 5.3. Locks and MVCC

Backends coordinate through locking and **MVCC**. MVCC allows readers to inspect consistent data versions without necessarily blocking all writers. However, concurrent write transactions can still contend for row locks or other locks.

Consequently:

- Two backends can run `SELECT` concurrently without blocking each other in typical workloads.
- Two backends updating the same row may wait on one another.
- DDL statements may require stronger locks that affect other sessions.
- Long-open transactions can hold back snapshot horizons and prevent VACUUM from reclaiming old row versions.

When troubleshooting, distinguish **a backend running slowly due to CPU/I/O** from **a backend waiting on locks or waiting on the client**. Each requires a different remedy.

## 6. Background Writing Processes: Background Writer, Checkpointer, and WAL Writer

These three processes are easily confused because all involve "writing," yet their responsibilities differ.

| Process | Typical responsibility | Common misconception to avoid |
| --- | --- | --- |
| **Background writer (bgwriter)** | Proactively writes out some dirty buffers to keep clean buffers available for reuse and reduce sudden write pressure when a backend needs a page | Not the only process that writes data pages |
| **Checkpointer** | Coordinates checkpoints and writing/syncing required pages at recovery milestones | Not a full rewrite of the entire database from scratch |
| **WAL writer (walwriter)** | Writes data from WAL buffers to WAL files in the background | Does not mean every `COMMIT` waits solely on WAL writer |

### 6.1. WAL and its relationship to durability

**WAL (*Write-Ahead Log*)** enables PostgreSQL to recover changes after a crash. The write-ahead principle requires corresponding WAL records to be durably written according to durability rules **before** modified data pages are allowed to be written to storage in ways that might require recovery.

Simplified flow:

~~~text
Client: UPDATE ...
    |
    v
Backend modifies page in shared_buffers
    |
    +--> generates WAL records into WAL buffers
    |
    +--> COMMIT per durability policy
              |
              v
      WAL written/flushed as required

Later:
    bgwriter / checkpointer / backend
        writes dirty data pages to data files
~~~

Exact ordering and flush mechanics depend on settings such as `synchronous_commit` and how PostgreSQL coordinates backends and the WAL writer. Under normal durability defaults, a successful `COMMIT` **does not require** all modified table data pages to be written immediately to table files; WAL enables recovery in a crash.

Do not conclude "after COMMIT, data only lives in RAM until the next checkpoint." Under standard durability settings, PostgreSQL enforces required WAL guarantees; table pages can be flushed later.

### 6.2. Background writer: smoothing spikes when backends need free buffers

The buffer pool has finite size; some buffers hold modified pages. If a backend needs to evict and reuse an older buffer that is still dirty, it may have to write and wait as needed. The background writer writes out a portion of dirty buffers ahead of time so clean buffers are more readily available.

However, under heavy write volume, backends can still write pages directly when necessary. Bgwriter is not a "single write queue" that every SQL operation waits behind.

Inspect related settings:

~~~sql
SHOW bgwriter_delay;
SHOW bgwriter_lru_maxpages;
~~~

These parameters partially control background writer behavior; do not tune them based on a single high-I/O observation. Consider overall workload, checkpointing, and storage hardware.

### 6.3. Checkpointer and checkpoints

Checkpoints bound the amount of WAL that must be replayed during recovery and serve as key milestones for durable storage management. The checkpointer coordinates writing and syncing required data pages for checkpoints.

Common parameters:

~~~sql
SHOW checkpoint_timeout;
SHOW max_wal_size;
SHOW checkpoint_completion_target;
~~~

`max_wal_size` is a target/soft threshold related to checkpoint and WAL sizing policies, **not an absolute hard ceiling that can never be exceeded** under all circumstances. Checkpoint timing also depends on other operational conditions.

Lowering `checkpoint_timeout` does not automatically make the server safer: overly frequent checkpoints can increase I/O and WAL volume due to full-page writes, while overly sparse checkpoints trade off longer recovery time and higher WAL storage usage. Tune based on measurements and RTO goals.

### 6.4. WAL writer and commit behavior

The WAL writer performs background work on WAL buffers. Under high-transaction workloads, it helps reduce the need for every backend to perform frequent tiny writes. However, when a transaction needs commit durability guarantees, **the backend itself can directly ensure the required WAL flush** rather than always waiting for a separate WAL writer cycle.

This explains an apparent paradox: "If the server has a WAL writer, why can a `COMMIT` still be slow?" Because commit latency also depends on storage flush speed, WAL synchronization, I/O contention, synchronous replication, and durability settings.

## 7. Autovacuum: Background Process Keeping MVCC and Statistics Healthy

PostgreSQL uses MVCC to keep row versions over time. When `UPDATE` creates a new version or `DELETE` marks an old version obsolete, old versions cannot be removed immediately if other transactions might still need to see them.

**Autovacuum** automates the necessary maintenance. High-level architecture:

~~~mermaid
flowchart TD
    L["Autovacuum launcher"] --> W1["Autovacuum worker 1"]
    L --> W2["Autovacuum worker 2"]
    W1 --> T1["VACUUM / ANALYZE table A"]
    W2 --> T2["VACUUM / ANALYZE table B"]
    T1 --> S["Reclaim reusable space,<br/>maintain MVCC metadata"]
    T2 --> S
~~~

- **Autovacuum launcher** monitors tables and schedules when workers should run.
- **Autovacuum workers** perform concrete work on eligible tables: vacuuming and/or analyzing.
- **VACUUM** removes obsolete row versions and handles related maintenance, including preventing transaction ID wraparound risks.
- **ANALYZE** updates data distribution statistics for the query planner.

Autovacuum is not an SQL command sent by an application, so learners may see these processes active even when zero HTTP requests are hitting the server.

### 7.1. Observing autovacuum

~~~sql
SHOW autovacuum;
SHOW autovacuum_max_workers;

SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
~~~

`n_live_tup` and `n_dead_tup` are **statistical estimates**, not exact counts. `last_autovacuum`/`last_autoanalyze` reflect timestamps recorded in the statistics system. In a database with only a handful of rows, you might not see workers trigger while watching.

### 7.2. Why should you not disable autovacuum?

Disabling autovacuum to reduce I/O causes tables to bloat with dead row versions, leaves planner statistics stale, and raises transaction ID wraparound risk. In serious operations, the proper approach is **monitoring and tuning maintenance thresholds for the workload**, not turning off the mechanism just because it shows up in the process list.

`VACUUM FULL` differs from regular `VACUUM`: it rewrites the entire table to reclaim physical disk space, requires strong locks, and is not part of routine continuous background vacuuming. Do not use `VACUUM FULL` as a default routine fix on large tables.

## 8. Other Background Processes: WAL Archive, Recovery, and Replication

PostgreSQL's active process list varies by instance role. A standalone primary has fewer replication components than a primary serving multiple standbys or an instance subscribed to logical replication.

### 8.1. WAL archiver

When WAL archiving is enabled and configured, the **archiver** copies completed WAL segments to long-term archive storage. This is essential for **point-in-time recovery (PITR)** alongside appropriate base backups.

~~~sql
SHOW archive_mode;
SHOW archive_command;

SELECT
    archived_count,
    failed_count,
    last_archived_wal,
    last_archived_time,
    last_failed_wal,
    last_failed_time
FROM pg_stat_archiver;
~~~

Do not treat the mere presence of an archiver process as proof of **a complete backup**. Archiving must succeed reliably, the WAL chain must be unbroken, base backups must be valid, and restore procedures must be tested.

Note: `archive_command` can contain operational paths and configuration details; avoid exposing sensitive information from it in public logs or documentation.

### 8.2. Startup process and WAL recovery

When PostgreSQL starts after an unclean shutdown or runs as a **standby/recovery** instance, recovery tasks replay WAL to bring data to a consistent state.

The **startup process** plays a central role in applying WAL during recovery. On a standby, continuous WAL replay keeps the replica caught up with the primary. Exact process names and states depend on startup phase and version.

~~~sql
SELECT pg_is_in_recovery() AS is_standby_or_recovering;
~~~

If `pg_is_in_recovery() = TRUE`, the server is in recovery mode, typically a standby replaying WAL. If `FALSE`, the server is not in recovery mode at query time. However, this single check **is not sufficient to determine the full topology or which node holds application write authority**; also inspect configuration and failover orchestration.

### 8.3. WAL sender and WAL receiver

In **physical streaming replication**, the primary runs **WAL sender processes (walsender)** to stream WAL data to standbys. On the standby side, a **WAL receiver (walreceiver)** receives the WAL stream, and the startup/recovery process applies WAL as it arrives.

~~~mermaid
flowchart LR
    A["Primary PostgreSQL"] --> WS["WAL sender"]
    WS -->|"Streaming WAL"| WR["WAL receiver on standby"]
    WR --> RL["Local WAL"]
    RL --> ST["Startup / recovery"]
    ST --> SD["Standby data files"]
~~~

Observing on the primary:

~~~sql
SELECT
    pid,
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

Observing on the standby:

~~~sql
SELECT
    pid,
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_wal_receiver;
~~~

On a server without replication, these queries may return **zero rows**; that does not indicate PostgreSQL is broken. Depending on version, columns in `pg_stat_wal_receiver` may vary slightly; run `\d+ pg_stat_wal_receiver` in `psql` on the target server to verify exact columns before building dashboards.

### 8.4. Logical replication launcher and apply workers

Logical replication replicates changes at a logical level, unlike a standby replaying the physical WAL stream of the entire instance. An instance using a **subscription** can run a **logical replication launcher** and **apply workers** to receive and apply decoded changes from the publisher.

Not every instance running a logical replication launcher has an active subscription, and not every replication connection is a regular client backend. Logical replication processes must be factored into background worker budgets and connection limits per configuration.

### 8.5. Background workers created by extensions

PostgreSQL allows certain extensions or system features to register **background workers**. Depending on installed extensions, you may see processes handling scheduling, maintenance, or other internal tasks.

Do not see an unfamiliar process name and immediately assume malware or a PostgreSQL bug; first verify installed extensions, configuration files, role/ownership, and feature documentation. Conversely, do not allow arbitrary extensions to run background code in production without security review.

## 9. Parallel Workers: Processes Assisting a Large Query

Not every extra spawned process is an application connection or a maintenance daemon. With **parallel query**, PostgreSQL can launch **parallel workers** to help execute part of a query plan.

Example:

~~~text
Client Connection
      |
      v
Leader backend PID 22001
      |
      +--> Parallel worker PID 22011
      +--> Parallel worker PID 22012
      |
      +--> Gather / Gather Merge
      |
      v
Results returned over the same client connection
~~~

In this model, the client still holds **one connection**, yet the server may use one or more additional workers during execution. Thus "one backend per connection" does not mean every query can only use a single process to compute results.

A parallel plan may include a `Gather` or `Gather Merge` node along with planned/launched worker counts:

~~~sql
EXPLAIN
SELECT COUNT(*)
FROM large_events;
~~~

This example assumes a `large_events` table already exists with sufficient data; it is **not** runnable on a brand-new empty database. PostgreSQL does not guarantee every `COUNT(*)` query runs in parallel. The planner weighs cost, query conditions, table size, `max_parallel_workers_per_gather`, worker budgets, and other constraints.

Common configuration variables:

~~~sql
SHOW max_parallel_workers_per_gather;
SHOW max_parallel_workers;
SHOW max_worker_processes;
~~~

These settings are not "threads per connection." Workers are allocated based on the query plan and runtime availability; a planned parallel query may receive fewer workers if the server is busy or hits resource limits.

### 9.1. Why isn't a parallel query always faster?

Launching and coordinating workers has overhead, requires transferring tuples back to the leader, and can introduce CPU/I/O contention. On small tables, a single process scanning data can finish faster than spinning up a worker group. When many concurrent queries request multiple workers, total server load can exceed CPU/storage capacity.

Inspect `EXPLAIN (ANALYZE, BUFFERS)` in a staging/test environment with representative data to measure real impact; note that `EXPLAIN ANALYZE` **actually executes** the query and can consume significant resources.

## 10. Observing Processes with pg_stat_activity

`pg_stat_activity` is one of the most useful system views for inspecting active PostgreSQL processes. It can include client backends as well as various background/auxiliary processes, with columns such as `pid`, `backend_type`, `state`, and `wait_event`.

### 10.1. Listing current backend types

~~~sql
SELECT
    backend_type,
    COUNT(*) AS process_count
FROM pg_stat_activity
GROUP BY backend_type
ORDER BY backend_type;
~~~

Illustrative output:

~~~text
backend_type                 process_count
------------------------------------------------
autovacuum launcher          1
background writer            1
checkpointer                 1
client backend               4
logical replication launcher 1
walwriter                    1
~~~

**Do not treat this exact list as mandatory.** Different versions and configurations produce different lists, and not every OS process appears in the view identically to application backends. The main `postmaster` process is not listed as a `client backend` row.

### 10.2. Viewing client sessions, queries, and wait states

~~~sql
SELECT
    pid,
    backend_type,
    datname,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    now() - backend_start AS backend_age,
    now() - xact_start AS transaction_age,
    LEFT(query, 100) AS query_preview
FROM pg_stat_activity
WHERE backend_type = 'client backend'
ORDER BY backend_start;
~~~

Columns:

| Column | Meaning |
| --- | --- |
| `pid` | OS PID of the backend process |
| `backend_type` | Process type, e.g. `client backend` |
| `datname` / `usename` | Associated database and role |
| `application_name` | Label set by client/configuration for observability |
| `client_addr` | Client IP address if applicable; may be `NULL` for Unix sockets |
| `state` | Execution/wait state of the client backend |
| `wait_event_type` / `wait_event` | Category and specific event the backend is waiting on |
| `backend_start` | Timestamp when the backend started |
| `xact_start` | Timestamp when the current transaction started; may be `NULL` |
| `query` | Current SQL statement or most recent statement depending on state |

When no transaction is open, `now() - xact_start` evaluates to `NULL`. An `idle` backend can still display its **last executed query** in `query`; do not assume it is still running that query.

Access privileges can restrict details of other sessions. Some fields may be masked unless the role holds appropriate monitoring privileges; roles like `pg_read_all_stats` should be granted intentionally by administrators rather than handed out broadly just for demos.

### 10.3. Query to detect idle in transaction

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE state LIKE 'idle in transaction%'
ORDER BY xact_start NULLS LAST;
~~~

If a session holds an open transaction idle for hours, inspect application logic, timeouts, locks, and MVCC impact. **Do not blindly auto-terminate every idle in transaction session in production**: canceling/closing connections can roll back legitimate work and disrupt users.

### 10.4. Distinguishing a backend waiting on a lock from waiting on a client

A backend with `wait_event_type = 'Lock'` may be waiting on a PostgreSQL lock:

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    LEFT(a.query, 120) AS query_preview
FROM pg_stat_activity AS a
WHERE a.wait_event_type = 'Lock'
ORDER BY a.pid;
~~~

`pg_blocking_pids(pid)` helps identify processes blocking the target PID, subject to permission and locking context. A backend waiting for the client to send the next command shows a different wait category, typically `Client`; that does not mean the database is locked up.

### 10.5. Inspecting your own session's PID

~~~sql
SELECT
    pg_backend_pid() AS current_pid,
    pg_postmaster_start_time() AS server_started_at,
    current_database() AS current_database,
    current_setting('application_name') AS application_name;
~~~

`pg_postmaster_start_time()` reports when the current main server started; it is **not** the coordinator's PID. `pg_backend_pid()` is the PID of the connection executing this SQL statement.

## 11. Connection Pools and PgBouncer: A Process Perspective

Because PostgreSQL uses a backend process per connection, an application serving thousands of concurrent clients should generally not open thousands of direct **physical connections** to PostgreSQL. Opening connections incurs process creation, session initialization, and memory allocation; too many connections also create CPU, cache, and administrative contention.

Example:

~~~text
30 application instances
  x 20 connections per pool
  = up to 600 potential backend connections
    if all pools fill completely and connect directly to PostgreSQL
~~~

The 600 figure is a **potential** upper bound from configuration, not a guarantee of 600 backends actively running SQL simultaneously. Some connections may sit idle; actual open counts depend on pool behavior.

### 11.1. Application-side connection pools

Java systems typically use a `DataSource` and a pool such as HikariCP. The pool keeps connections reusable across HTTP requests. A connection returned to the pool can stay open inside PostgreSQL:

~~~mermaid
flowchart LR
    R1["HTTP request 1"] --> POOL["Application connection pool"]
    R2["HTTP request 2"] --> POOL
    R3["HTTP request 3"] --> POOL
    POOL --> A["PostgreSQL backend A"]
    POOL --> B["PostgreSQL backend B"]
~~~

When sizing a pool, consider all of the following:

- PostgreSQL's `max_connections` and reserved slots for administrative/special connections.
- Total number of application instances, not just a single instance's configuration.
- RAM cost per backend and concurrently running queries.
- Transaction duration, query timeouts, and connection acquisition timeouts.
- Actual server capacity, avoiding simply increasing pool size when queries are slow.

~~~sql
SHOW max_connections;
SHOW superuser_reserved_connections;
~~~

Newer versions may include additional reserved-connection parameters; check documentation for your version. Certain background and replication workers are governed by separate limits, so **do not sum all OS processes and compare them one-to-one against `max_connections`**.

### 11.2. PgBouncer and session semantic limits

`PgBouncer` is an external connection pooler for PostgreSQL. It can accept many client connections while multiplexing them onto a smaller set of server connections. Under **transaction pooling**, a client can be assigned to a different PostgreSQL backend on its next transaction.

~~~text
Client X --transaction 1--> PgBouncer --> Backend 10
Client X --transaction 2--> PgBouncer --> Backend 12
~~~

This works well for applications with many short-lived transactions, but **you cannot assume session state persists across transactions**. Features such as temporary tables spanning transactions, session-level advisory locks, session settings, server-side prepared statements, and certain cursors may require special handling or depend on PgBouncer/driver support.

If an application requires a fixed backend for the entire session, **session pooling** aligns better with keeping one server connection per client session, though its backend sharing efficiency and resource usage differ from transaction pooling.

Do not add PgBouncer assuming every performance problem disappears. A pooler reduces connection-management overhead in suitable workloads; **it does not make a heavy query lighter**, nor does it replace indexing, vacuuming, or SQL tuning.

## 12. Hands-On Practice: Observing Two Sessions and Background Processes

This section uses only safe read/practice queries on a **dedicated lab database**. You need PostgreSQL access and `psql` or an equivalent SQL client.

### Lab Exercise 1 — Two connections, two PIDs

**Session A**, connect via `psql`:

~~~sql
SET application_name = 'lesson55_A';

SELECT
    pg_backend_pid() AS pid_a,
    current_database() AS db_a,
    current_user AS user_a;
~~~

**Session B**, open a second connection:

~~~sql
SET application_name = 'lesson55_B';

SELECT
    pg_backend_pid() AS pid_b,
    current_database() AS db_b,
    current_user AS user_b;
~~~

Then in either session:

~~~sql
SELECT
    pid,
    application_name,
    backend_type,
    state
FROM pg_stat_activity
WHERE application_name IN ('lesson55_A', 'lesson55_B')
ORDER BY application_name;
~~~

Expect **two distinct PIDs** and `backend_type = 'client backend'`. If an SQL GUI automatically closes and reconnects on every statement, the PID may change between queries; distinguish tool behavior from PostgreSQL behavior.

### Lab Exercise 2 — Watching an active backend

In **Session A**:

~~~sql
SELECT pg_sleep(15);
~~~

While that command is executing, in **Session B**:

~~~sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE application_name = 'lesson55_A';
~~~

On many PostgreSQL versions, you will see `state = 'active'` alongside a wait event indicating it is sleeping in `pg_sleep`. **Active** means the statement is still in flight, not necessarily burning CPU at every instant.

If the query finishes before you observe it, repeat in the lab with a suitable duration. Do not run a long sleep in production just to construct an example.

### Lab Exercise 3 — Observing idle in transaction

In **Session A**:

~~~sql
BEGIN;

SELECT 1 AS still_in_transaction;

-- Leave the session at the prompt without COMMIT/ROLLBACK.
~~~

In **Session B**:

~~~sql
SELECT
    pid,
    application_name,
    state,
    now() - xact_start AS transaction_age
FROM pg_stat_activity
WHERE application_name = 'lesson55_A';
~~~

Expect to see `idle in transaction` once `SELECT 1` finishes while the transaction remains open. Return to Session A and clean up:

~~~sql
ROLLBACK;
~~~

If you check again, Session A typically returns to `idle`. With clients that use automatic transaction modes or different pooling behavior, displayed states must be interpreted according to the client tool's behavior.

### Lab Exercise 4 — Observing background process types

~~~sql
SELECT backend_type, COUNT(*) AS cnt
FROM pg_stat_activity
GROUP BY backend_type
ORDER BY cnt DESC, backend_type;
~~~

Identify types that may appear such as `checkpointer`, `background writer`, `walwriter`, and `autovacuum launcher`. If `autovacuum worker` or `parallel worker` does not appear, that can be completely normal: those workers are usually spawned only when matching work exists.

### Lab Exercise 5 — Observing replication workload if configured

If your lab server has physical replication configured:

~~~sql
-- Run on primary:
SELECT
    application_name,
    state,
    sync_state
FROM pg_stat_replication;
~~~

On a standalone instance, this query typically returns 0 rows. You do not need to set up a replica solely to learn basic architecture; this exercise is for environments where a test topology already exists.

## 13. Symptom-Based Diagnosis: Which Process Matters?

| Symptom | Process or view to check | Investigative questions |
| --- | --- | --- |
| Application cannot acquire a connection | Client backends, `pg_stat_activity`, pool, `max_connections` | Too many idle or active sessions? Is the pool leaking connections? |
| Query suddenly becomes slow | Active backend, `EXPLAIN`, wait events | Waiting on CPU, I/O, locks, or running a poor plan? |
| Many `idle in transaction` sessions | Client backends and `xact_start` | Is code opening transactions and failing to commit/rollback promptly? |
| Table bloat grows rapidly | Autovacuum workers, `pg_stat_user_tables` | Heavy UPDATE/DELETE, long transactions, or vacuum falling behind? |
| Disk writes cause large I/O spikes | Checkpointer, bgwriter, backend writes, storage metrics | Checkpoints too frequent, rising workload, or slow storage? |
| High commit latency | WAL writer, WAL flush, synchronous replication, storage | Slow WAL flush, standby network delay, or contention? |
| WAL archiving stops updating | Archiver, `pg_stat_archiver`, logs | Failing archive command, missing permissions, or full disk? |
| Replica lags behind | WAL sender/receiver, recovery process, replication views | Slow network, WAL receiver, replay lag, or resource bottleneck? |
| Single query uses CPU across many cores | Leader backend and parallel workers | Is the parallel plan actually helping? |
| PostgreSQL restarts after a failure | Main process, startup/recovery logs | Backend crash, memory/storage fault, or OS intervention? |

Diagnostic rule: **never look only at process count**. Combine process type, state, wait events, open transaction count, I/O, and logs to understand the real situation.

### 13.1. Many postgres processes do not automatically indicate a leak

A server with 200 client connections plus background processes can show over 200 `postgres` OS processes. If `max_connections` and pools were sized for that workload, that alone proves nothing is wrong. Conversely, 20 connections holding locks inside hours-long transactions can cause a severe outage.

### 13.2. Do not arbitrarily kill PostgreSQL processes at the OS level

When a backend runs a heavy query, administrators should consider PostgreSQL's built-in functions instead of sending forceful OS signals. For example:

~~~sql
-- Illustrative only; do not run before verifying PID and privileges:
SELECT pg_cancel_backend(<pid>);
~~~

In the snippet above, `<pid>` is a placeholder and **not valid SQL** until replaced with a verified numeric PID. `pg_cancel_backend` requests cancellation of the backend's **current query**; `pg_terminate_backend` is stronger and terminates the **session**, which can roll back that session's transaction. Calling these functions requires proper privileges and impacts real users.

**Never send `kill -9` / TerminateProcess indiscriminately to PostgreSQL processes in production.** Killing a single process abnormally can trigger protective restarts and recovery procedures that are far more disruptive than controlled query cancellation.

## 14. Common Architectural Misconceptions

| Misconception | Reality |
| --- | --- |
| "A PostgreSQL instance has only one process" | It has a main process, client backends, and background/auxiliary processes |
| "Each SQL statement spawns a new process" | One backend typically serves many statements on the same connection |
| "A connection is always a process on the application host" | The backend process runs on the **server**; the client holds a protocol connection |
| "Adding 500 connections boosts performance" | More backends add overhead and contention; choose an appropriate pool size |
| "Each backend has its own copy of shared_buffers" | `shared_buffers` is shared memory across the instance |
| "Having a WAL writer means backends never write WAL" | Backends can write/flush WAL themselves when needed to guarantee commit |
| "Checkpoints are when transactions finally commit" | Commits rely on durability/WAL rules; checkpoints are write and recovery milestones |
| "Bgwriter is the only process writing data pages" | Checkpointer and backends can also write data pages |
| "Autovacuum running means the database has an error" | It is normal maintenance required for MVCC and statistics |
| "Disabling autovacuum to lighten server load is always safe" | It can cause bloat and transaction ID wraparound risk |
| "A replica needs a regular client backend per transaction" | Streaming replication uses dedicated WAL sender/receiver and recovery processes |
| "Parallel workers are extra connections from the application" | They assist query execution server-side, not independent client sessions |
| "`active` means using 100% CPU" | An active backend may be waiting on locks, I/O, or timers |
| "`idle` means consuming zero resources" | Idle connections still retain a backend process and session resources |
| "`idle in transaction` is harmless like idle" | It can hold locks/snapshots and interfere with VACUUM |
| "Viewing `pg_stat_activity` shows every detail of every process" | Visibility depends on privileges, process type, and PostgreSQL version |

## 15. Applied Exercises

### Exercise 1 — Calculating potential client backends

An application runs 4 instances. Each instance configures a direct PostgreSQL pool with a maximum of 15 connections. Calculate the number of client backends from this application when **all pools are completely full**, excluding admin connections and background components.

**Suggested answer:** 4 × 15 = **60 potential client backends**. This is not the guaranteed number of queries executing in parallel, nor is it the total number of PostgreSQL OS processes.

### Exercise 2 — Distinguishing write milestones

An `UPDATE` committed successfully, yet the table's data page is still dirty in `shared_buffers`. Does that mean the transaction is not durable?

**Hint:** do not draw that conclusion. Under normal durability settings, WAL is written/flushed per commit rules before data file pages must be flushed. Data pages can be written out later by checkpointer/bgwriter/backends; crash recovery replays WAL when needed.

### Exercise 3 — Why are there 10 `postgres` lines when only 2 psql sessions are open?

Identify the main process, two client backends, and processes such as checkpointer, bgwriter, walwriter, and autovacuum launcher from OS output or `pg_stat_activity`.

**Hint:** many processes do not mean many user connections. Several background processes run independently, and displayed names depend on version.

### Exercise 4 — Why do many `idle in transaction` sessions increase table bloat?

Suppose transaction A opens a snapshot and sits idle for a very long time while transactions B repeatedly update rows. Explain MVCC and why VACUUM may be unable to reclaim old row versions that transaction A might still need to see.

**Hint:** distinguish `idle` (no open transaction) from `idle in transaction` (transaction held open); inspect `xact_start` and application logic.

### Exercise 5 — Checking the current backend

Open two independent `psql` connections and run:

~~~sql
SELECT pg_backend_pid(), current_database(), current_user;
~~~

Compare PIDs. In one session, run `SELECT pg_sleep(10);`; in the other, query `pg_stat_activity`. Explain why `state` can be `active` while `wait_event` shows the backend is waiting.

### Exercise 6 — Choosing which process to investigate by scenario

| Scenario | Process group to inspect first |
| --- | --- |
| WAL archiving is failing | Archiver and `pg_stat_archiver` |
| Standby suffers replay lag | WAL receiver, startup/recovery, and replication metrics |
| Large `COUNT(*)` query uses `Gather` | Leader backend and parallel workers |
| Frequent deadlocks | Client backends, locks, and transaction boundaries |
| Queries wait on the connection pool | Client backends, pool, and connection limits |
| Table dead tuples stay high for a long time | Autovacuum and long-running transactions |

### Exercise 7 — Designing a connection pool

A server has resources for a relatively modest number of productively executing concurrent queries, yet the application receives thousands of short requests. Explain:

1. Why opening thousands of direct PostgreSQL connections can be harmful.
2. Which costs an application-side connection pool reduces.
3. How PgBouncer transaction pooling differs from session pooling in preserving session state.
4. Why prepared statements, temporary tables, and session settings must be reviewed before changing pooling mode.

### Exercise 8 — Reading a status table

Suppose `pg_stat_activity` reports:

~~~text
PID    backend_type     state                  wait_event_type
3010   client backend   active                 Lock
3011   client backend   idle in transaction    Client
3012   client backend   idle                   Client
3013   background writer (null)                (null)
~~~

Answer the following:

- What might PID 3010 be waiting for?
- Why is PID 3011 more concerning than an ordinary idle connection?
- Can you call `pg_cancel_backend(3013)` as if the background writer were a user query?
- Is this table alone enough evidence to terminate PID 3011?

**Hint:** identify lock causes, transaction age, application source, and impact/privileges before intervening. The background writer is not a user SQL session. Never arbitrarily cancel background processes.

## 16. Summary

In PostgreSQL, the **main process / postmaster** coordinates startup, incoming connections, and server lifecycle. **Client backends** serve individual connections, execute statements and transactions, use private memory, and coordinate via shared memory. **Background processes** handle longer-lived, independent duties: the background writer eases buffer pressure, the checkpointer manages checkpoints, the WAL writer assists log writes, autovacuum maintains MVCC health and statistics, and replication/recovery processes handle replication and recovery.

These components collaborate rather than operating in total isolation. When executing SQL, a backend can read from shared buffers and wait on locks; at `COMMIT`, WAL and durability settings enforce required guarantees; afterward, background writers continue flushing pages. For large queries, PostgreSQL can recruit parallel workers; for high-concurrency applications, connection pools keep backend counts controlled.

Understanding **who accepts connections, who runs queries, and who maintains the system** helps developers avoid costly mistakes such as raising connection limits endlessly, disabling autovacuum, or killing the wrong process. It also forms the foundation for using `pg_stat_activity`, `EXPLAIN`, and system views to observe, explain, and operate PostgreSQL reliably.
