# Extended background processes (background workers), autovacuum, and replication processes

PostgreSQL is not merely a single process accepting SQL and returning results. When an instance runs, the operating system typically sees **multiple processes** cooperating with one another: a main process managing server lifecycle, backends serving application connections, processes dedicated to WAL and checkpoints, **autovacuum** reclaiming old row versions, and processes sending/receiving WAL or applying changes for data replication.

Certain features also use the **background worker** mechanism (*extended background processes*) to run work inside the server without requiring an ordinary user connection. Understanding these process types helps answer practical questions: why a table keeps bloating despite deleting many rows, why a replica lags behind the primary, why increasing parallel queries starves workers, and why an issue in a background component can affect PostgreSQL operations.

This lesson focuses on three groups within PostgreSQL's architecture:

1. **Background workers and PostgreSQL background processes:** how they are spawned, consume resources, and coordinate with the server.
2. **Autovacuum:** launcher and workers automatically cleaning MVCC data, updating statistics, and protecting transaction IDs.
3. **Replication processes:** WAL sender/receiver in *physical replication*; logical replication launcher, apply worker, and table synchronization worker in *logical replication*.

Observation examples use SQL in `psql`, notably `pg_stat_activity`, `pg_stat_progress_vacuum`, `pg_stat_replication`, `pg_stat_wal_receiver`, and `pg_stat_subscription`. Process names and statistics columns can vary across versions, so adapt these queries to the PostgreSQL version you run.

> **Practice scope:** The `SELECT` statements in this lesson are primarily read-only observations and can be tested on a PostgreSQL instance where you have privileges. Changes to autovacuum, worker limits, publications/subscriptions, or replication must be tested in a lab or deployed under change approval. Never disable autovacuum or drop replication slots arbitrarily on production.

## 1. Big picture: PostgreSQL is a multi-process architecture

On common platforms, PostgreSQL uses a **multi-process model**. The main process is traditionally called *postmaster* (program name `postgres`), coordinating startup, managing child processes, and handling server lifecycle.

When a client connects, PostgreSQL normally spawns a **backend process** for that connection. Alongside backends, there are instance-wide auxiliary processes and on-demand processes such as parallel workers or logical replication workers.

Conceptual diagram:

```text
                 Client / Java / psql
                          │
                          ▼
               PostgreSQL main process
                    (postmaster)
                          │
            ┌─────────────┼──────────────────┐
            │             │                  │
            ▼             ▼                  ▼
      Client backends   Auxiliary       Background workers
      - SQL queries     processes       - Extension workers
      - Transactions    - Checkpointer  - Parallel workers
                        - WAL writer    - Logical apply/sync
                        - BG writer
                        - Autovacuum
                          launcher/worker
            │             │                  │
            └─────────────┼──────────────────┘
                          │
                          ▼
                Shared memory + WAL
                          │
          ┌───────────────┴─────────────────┐
          ▼                                 ▼
     WAL sender                        WAL receiver
     (primary / sender)                (standby)
          │                                 │
          └────────── WAL stream ───────────┘
```

This diagram shows **functional groupings**, not an exact process parent–child tree or a complete map of every data flow. For example, on a standby, the WAL receiver receives WAL while the *startup/recovery* process performs replay; in logical replication, the apply worker has a distinct role. Depending on configuration, certain processes may **not exist** when the corresponding feature is disabled.

### Process groups to distinguish

| Group | Primary role | Usually spawned when? |
|---|---|---|
| **Main server/postmaster** | Starts and monitors the instance, accepts new connections, coordinates processes. | When PostgreSQL server starts. |
| **Client backend** | Executes SQL, maintains session and transaction state for a connection. | When a client connects successfully. |
| **Auxiliary processes** | System tasks like checkpointing, WAL writing, background writing; depends on version and config. | Across the server lifecycle. |
| **Autovacuum launcher and workers** | Schedules and runs automatic vacuum/analyze on tables needing maintenance. | When autovacuum is enabled and eligible work exists. |
| **Generic/extension background workers** | Runs core/extension tasks that are not direct client SQL requests. | When an extension or internal mechanism registers/requests a worker. |
| **WAL sender** | Ships change streams for streaming replication or logical decoding. | When a corresponding replication connection is active. |
| **WAL receiver** | Receives WAL from upstream on a physical standby. | When a standby uses streaming replication. |
| **Logical replication workers** | Reads and applies changes for subscriptions, plus initial table sync. | When a subscriber has active subscriptions. |

**Important:** Do not call every background process a "background worker" in the sense of the extension API. PostgreSQL has several **core background/auxiliary processes** with fixed roles; the *background worker framework* is the mechanism allowing features and extensions to register additional server-managed processes.

## 2. Why does PostgreSQL use multiple processes instead of one single task?

Each group performs a distinct kind of work with different characteristics. Query backends need low-latency responses for applications; the checkpointer coordinates dirty-page flushing; autovacuum works periodically in the background; replication continuously ships, receives, and applies changes.

Separating into processes offers several advantages:

- **Process-level isolation:** a client connection backend is not sharing a single execution thread directly with every other backend.
- **Concurrency:** client queries, WAL writes, vacuuming, and replication can progress concurrently within resource and synchronization limits.
- **Clear observability units:** the OS and statistics views expose PID, backend type, state, duration, and wait events per process.
- **Controlled privileges and lifecycles:** internal processes are spawned and managed by the server rather than created arbitrarily by database users.

However, separate processes **do not mean zero interference**. They share shared memory, buffer caches, WAL, CPU, disk, network, and lock resources. An autovacuum running on a huge table can consume heavy I/O; a slow replication worker can pin WAL via a replication slot; parallel workers can contend with logical replication workers for worker slots.

Thus, when observing PostgreSQL, inspect both **process types** and **the resources they contend over**.

## 3. Identifying processes with pg_stat_activity

`pg_stat_activity` reports information about backend processes tracked by PostgreSQL. The `backend_type` column identifies each row's role.

Example:

```sql
SELECT
    pid,
    backend_type,
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    backend_start
FROM pg_stat_activity
ORDER BY backend_type, pid;
```

Depending on version and state, you may see types such as:

```text
client backend
autovacuum launcher
autovacuum worker
background writer
checkpointer
walwriter
walsender
walreceiver
logical replication launcher
logical replication worker
parallel worker
background worker
```

The list above is **illustrative only**, not a guarantee every server has every row or identical display names. For example, a primary with no connected standby has no WAL sender; a server not using logical replication has no apply worker. Furthermore, visibility into query text and state of processes belonging to other users depends on monitoring privileges.

### Counting processes by type

```sql
SELECT
    backend_type,
    COUNT(*) AS process_count
FROM pg_stat_activity
GROUP BY backend_type
ORDER BY process_count DESC, backend_type;
```

This query gives a point-in-time snapshot, useful for checking active client backends, parallel workers, or autovacuum workers. **Short-lived processes can exit before you observe them**; a single snapshot does not represent activity across the whole day.

### Identifying waiting processes

```sql
SELECT
    pid,
    backend_type,
    state,
    wait_event_type,
    wait_event,
    now() - backend_start AS process_age
FROM pg_stat_activity
WHERE wait_event_type IS NOT NULL
ORDER BY backend_type, pid;
```

`wait_event_type`/`wait_event` indicate what kind of event a process is waiting on, such as locks, I/O, or internal activity. However, **not every process showing a wait event has a problem**: a background process may simply be sleeping waiting for new work by design. Understand the process type and correlate metrics before intervening.

## 4. Background worker framework: extending background processes

PostgreSQL provides a framework for extensions or core components to register **background workers**. They run inside the PostgreSQL server lifecycle, are managed by the server, and can perform scheduled or signal-driven work rather than waiting on direct client SQL requests.

A background worker can:

1. Start at server boot or be registered dynamically at an appropriate time.
2. Run a work/wait loop responding to signals or timers.
3. Communicate with the server via shared memory, latches, or PostgreSQL-supported primitives.
4. Where API rules permit, connect to a database and run queries via the **Server Programming Interface (SPI)**.
5. Terminate upon completing its work, receiving a shutdown signal, or when stopped by the server.

These capabilities belong to **server-side C APIs**, generally requiring C code and deep understanding of PostgreSQL's process model. An extension running a background worker operates with far greater trust and privileges than an ordinary JDBC application.

### Practical examples

- Job-scheduling extensions running periodic tasks inside the database server.
- Background metric collection or metadata synchronization tasks.
- Internal workers supporting **parallel queries**.
- Workers powering **logical replication** on subscribers.

Not every scheduled task is a PostgreSQL background worker. For instance, a Java scheduler in a separate service calling `psql` or JDBC is an **application-side process**, not a PostgreSQL background worker.

### Static vs. dynamic registration

Some extensions require `shared_preload_libraries` so they load at PostgreSQL startup and register workers early. Other components can register workers dynamically when API conditions and limits allow.

Adding an extension to `shared_preload_libraries` is more than editing one line in a config file:

- The server must locate a shared library compiled for that exact PostgreSQL major version.
- The library can execute initialization code during startup, so misconfiguration can prevent the server from starting.
- Changing `shared_preload_libraries` usually requires a **restart**, not merely a reload.
- Extensions must be vetted for reliability, version compatibility, and rollback plans prior to rollout.

This is why custom background workers fall under **system administration and trusted server code**, not an ad-hoc feature for SQL users to spawn arbitrary processes.

## 5. Resource limits for background workers

Several parameters govern concurrent worker capacity:

| Parameter | Typical meaning | Key points to remember |
|---|---|---|
| `max_worker_processes` | Total background worker processes PostgreSQL supports in the configured pool. | Caps capacity across worker types sharing this pool; requires restart to change. |
| `max_parallel_workers` | Maximum parallel query workers usable concurrently across the instance. | Still bounded by other worker limits and system resources. |
| `max_parallel_workers_per_gather` | Maximum parallel workers a single Gather/Gather Merge node can request. | Does not guarantee a query always gets that many workers. |
| `max_logical_replication_workers` | Limit on logical replication workers on a subscriber. | These workers also draw from `max_worker_processes`. |
| `max_sync_workers_per_subscription` | Maximum workers for initial table sync per subscription. | Not to be confused with the regular change-applying worker. |
| `autovacuum_max_workers` | Limit on concurrently active autovacuum workers. | Dedicated autovacuum throttle; do not conflate directly with parallel-query worker limits. |
| `max_wal_senders` | Maximum WAL sender processes for replication/backup connections. | Separate limit for sender processes, not another name for `max_worker_processes`. |

Example configuration check:

```sql
SELECT
    name,
    setting,
    unit,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'max_worker_processes',
    'max_parallel_workers',
    'max_parallel_workers_per_gather',
    'max_logical_replication_workers',
    'max_sync_workers_per_subscription',
    'autovacuum_max_workers',
    'max_wal_senders'
)
ORDER BY name;
```

`context` indicates when a parameter can be changed; several require a server restart to take effect. Never assume every setting can be changed with `SET` inside an SQL session.

**Trade-off example:** If logical replication and a background extension need workers while parallel queries also request workers, the shared pool can become a bottleneck. When workers are exhausted, tasks are delayed or queries run with fewer parallel workers than planned. Raising `max_worker_processes` may require a restart and increases resource demand; never raise it before confirming the true bottleneck.

## 6. Autovacuum exists because PostgreSQL uses MVCC

PostgreSQL uses **Multi-Version Concurrency Control (MVCC)** so transactions can read and write concurrently under isolation rules. When a row is updated via `UPDATE`, PostgreSQL normally creates a **new row version**; on `DELETE`, old versions are not necessarily erased from data pages immediately because other transactions may still need to see them.

Example:

```sql
CREATE TABLE demo_inventory (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    quantity INTEGER NOT NULL
);

INSERT INTO demo_inventory(sku, quantity)
VALUES ('SKU-001', 10);

UPDATE demo_inventory
SET quantity = 9
WHERE sku = 'SKU-001';

DELETE FROM demo_inventory
WHERE sku = 'SKU-001';
```

After these changes, PostgreSQL can leave behind tuple versions **no longer needed by any transaction** in heap pages. These versions are commonly called **dead tuples** once eligible for reclamation under MVCC rules.

Routine `VACUUM` can:

- Identify and reclaim space from obsolete tuple versions.
- Maintain index and visibility map metadata for efficient access.
- Perform **transaction ID freezing** to prevent transaction ID wraparound.
- Update related storage statistics.

`ANALYZE` serves a different purpose: collecting **data distribution statistics** so the query optimizer picks better plans. Autovacuum runs both vacuum and autoanalyze tasks automatically, yet **VACUUM does not completely replace ANALYZE** for all statistical needs.

### VACUUM does not mean returning all disk space to the OS

In most cases, routine `VACUUM` marks space inside the table as **reusable for new data**; physical file size does not necessarily shrink immediately. It can occasionally truncate empty pages at the very end of a file when conditions permit, but there is no guarantee that "deleting 1 GB of data frees 1 GB of disk space."

`VACUUM FULL` rewrites the table to reclaim space aggressively, but requires an **ACCESS EXCLUSIVE lock** and extra disk space. It is not something autovacuum routinely runs on its own.

## 7. Autovacuum launcher and autovacuum workers

PostgreSQL separates two clear roles:

| Component | Role |
|---|---|
| **Autovacuum launcher** | Wakes up on a schedule, inspects databases, and spawns workers where work is needed. |
| **Autovacuum worker** | Connects to a database, picks relations needing maintenance, and executes automatic vacuum or analyze. |

Diagram:

```text
       PostgreSQL server
              │
              ▼
     autovacuum launcher
              │
    periodically checks demand
              │
              ▼
    Spawns autovacuum workers
              │
        ┌─────┴────────┐
        ▼              ▼
    Database A      Database B
    ├─ table X      └─ table Z
    └─ table Y
         │
         ▼
  VACUUM / ANALYZE when eligible
         │
         ▼
  Reusable space + statistics
  + XID age wraparound protection
```

`autovacuum_naptime` influences how often the launcher checks databases, yet **never interpret it as a guarantee that "every table is vacuumed every N seconds."** Actual frequency depends on thresholds, worker count, number of databases, I/O load, transaction age, and task duration.

### When is autovacuum triggered?

For ordinary tables, vacuum triggering relates to dead tuple count and table size; a basic model is:

\[
\text{Vacuum threshold} \approx
\text{autovacuum\_vacuum\_threshold}
+
\text{autovacuum\_vacuum\_scale\_factor}
\times
\text{estimated row count}
\]

Suppose the base threshold is **50**, the scale factor is **0.2**, and the table has roughly **1,000,000 rows**; the simple model gives about **200,050** dead tuples. This formula only explains the parameter semantics—**it is not the sole condition autovacuum evaluates**.

PostgreSQL also evaluates other triggers such as insert counts, analyze thresholds, and crucially **XID freezing** to prevent wraparound. Exact triggers and additional parameters depend on version.

### Why must transaction IDs be frozen?

PostgreSQL uses transaction IDs from a finite numeric space. If tuple versions retain very old XIDs without maintenance, the system faces **transaction ID wraparound**, corrupting transaction ordering semantics.

Autovacuum plays a vital role in **freezing old transaction metadata** before wraparound risk becomes critical. Therefore:

- Never disable autovacuum globally just to reduce I/O.
- Certain anti-wraparound vacuum operations may still be forced by PostgreSQL **even when autovacuum is disabled at the table level**.
- Long-running transactions and replication slots holding back old XIDs can obstruct dead tuple cleanup.
- Approaching wraparound can trigger strict protective stops affecting system write availability.

**Autovacuum is a core component ensuring long-term data integrity**, not merely a background garbage collector saving disk space.

## 8. Key autovacuum parameters to know

Common settings:

| Parameter | Effect |
|---|---|
| `autovacuum` | Enables/disables routine autovacuum per server rules. |
| `autovacuum_max_workers` | Caps concurrently active autovacuum workers. |
| `autovacuum_naptime` | Base sleep/scheduling interval for the launcher between database checks. |
| `autovacuum_vacuum_threshold` | Base dead-tuple threshold component for triggering vacuum. |
| `autovacuum_vacuum_scale_factor` | Table-size multiplier component for triggering vacuum. |
| `autovacuum_analyze_threshold` | Base modified-tuple threshold for triggering autoanalyze. |
| `autovacuum_analyze_scale_factor` | Table-size multiplier for triggering autoanalyze. |
| `autovacuum_vacuum_cost_delay` | Throttling pause to reduce resource pressure. |
| `autovacuum_vacuum_cost_limit` | Cost budget in vacuum throttling mechanics. |
| `autovacuum_work_mem` | Memory limit usable by autovacuum work, per parameter rules. |

Inspect active settings:

```sql
SELECT
    name,
    setting,
    unit,
    context,
    pending_restart
FROM pg_settings
WHERE name LIKE 'autovacuum%'
ORDER BY name;
```

**Never copy values from a lesson straight into production.** Appropriate intervals between vacuums depend on `UPDATE`/`DELETE` churn, table size, HOT updates, indexes, storage speed, application load, and worker limits.

### Per-table tuning

A heavily updated table may need autovacuum sooner than the rest of the database. PostgreSQL supports setting select parameters in **table storage parameters**, for example:

```sql
-- Illustrative only on a lab table.
ALTER TABLE demo_inventory SET (
    autovacuum_vacuum_threshold = 1000,
    autovacuum_vacuum_scale_factor = 0.02
);
```

This alters the trigger conditions for the chosen table only, not every table in the database. However, **lowering thresholds does not magically add CPU or I/O**. If autovacuum workers are already saturated or blocked by long transactions, diagnose the root cause first.

To revert to server-inherited defaults:

```sql
ALTER TABLE demo_inventory RESET (
    autovacuum_vacuum_threshold,
    autovacuum_vacuum_scale_factor
);
```

Note that this is DDL requiring table ownership and taking corresponding locks; apply changes through planned rollouts rather than ad-hoc edits.

## 9. Observing what autovacuum is doing

### 9.1. Inspecting autovacuum workers via pg_stat_activity

```sql
SELECT
    pid,
    backend_type,
    datname,
    state,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE backend_type IN ('autovacuum launcher', 'autovacuum worker')
ORDER BY backend_type, pid;
```

If you see a worker processing a large table, do not assume it is a bug. It may be performing essential maintenance to prevent bloat or wraparound.

### 9.2. Tracking VACUUM progress

`pg_stat_progress_vacuum` exposes details about **currently running VACUUMs**, including autovacuum workers where applicable:

```sql
SELECT
    p.pid,
    p.datname,
    p.relid::regclass AS relation_name,
    p.phase,
    p.heap_blks_total,
    p.heap_blks_scanned,
    p.heap_blks_vacuumed,
    a.backend_type
FROM pg_stat_progress_vacuum AS p
LEFT JOIN pg_stat_activity AS a ON a.pid = p.pid
ORDER BY p.datname, p.pid;
```

`heap_blks_*` are measured in **blocks/pages**, not rows. The `scanned/total` ratio tracks one phase, not always overall VACUUM completion percentage, because VACUUM passes through multiple phases (heap scan, index vacuuming, cleanup, etc.).

If the query returns zero rows, no VACUUM is currently active in the view at that instant; **it does not prove autovacuum is disabled**.

### 9.3. Viewing recent history and estimated dead tuples

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    autovacuum_count,
    last_autoanalyze,
    autoanalyze_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
```

`n_live_tup` and `n_dead_tup` are **statistical estimates**, not exact instantaneous row counts. `last_autovacuum` and counters also depend on when statistics were last reset; tables that have not yet met trigger criteria may show null.

### 9.4. Detecting long-running transactions

```sql
SELECT
    pid,
    usename,
    datname,
    state,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start
LIMIT 20;
```

A transaction open too long pins an old snapshot and prevents vacuum from reclaiming dead versions visible to that transaction. When seeing persistent `idle in transaction` sessions, investigate application code, connection pooling, and commit/rollback boundaries.

**Never automatically run `pg_terminate_backend(...)` on every long session.** Killing a connection executing business work can force rollbacks, user-facing errors, or inconsistent external state.

## 10. Autovacuum, manual VACUUM, and resource contention

Occasionally an administrator runs `VACUUM` or `ANALYZE` manually in an authorized environment:

```sql
VACUUM (ANALYZE) demo_inventory;
```

Routine vacuum does not take an exclusive lock like `VACUUM FULL` blocking all reads/writes, yet it still consumes CPU/I/O and can contend with DDL or maintenance tasks. It is not a zero-impact operation on busy workloads.

Practical notes:

- Routine `VACUUM` cannot run inside an explicit **transaction block**.
- `ANALYZE` refreshes optimizer statistics, often useful after large bulk loads or distribution shifts.
- `VACUUM FULL` rewrites the table, requires heavy locks, causes disruption, and is not the default fix for bloat.
- If dead tuples keep growing despite autovacuum running, check **long transactions, replication slots, thresholds, worker counts, I/O, and write churn**.
- If worried about autovacuum load, measure and throttle properly rather than disabling it; disabling can worsen bloat and XID risks.

### "Slow" autovacuum may be a symptom, not the disease

Suppose an application updates the same table continuously at very high speed so autovacuum runs nonstop. You may need to:

1. Review `UPDATE` patterns and indexes: is every update creating new versions and churning multiple indexes?
2. Check for long-held snapshots preventing dead tuple reclamation.
3. Inspect I/O throughput, buffer cache, and contention.
4. Review vacuum thresholds and worker capacity.
5. Revisit data modeling or batch schedules rather than merely raising worker counts.

Stronger settings can help in certain cases, yet **never substitute for understanding what generates dead tuples**.

## 11. Role of WAL in PostgreSQL replication

The **Write-Ahead Log (WAL)** records change metadata required for durability and crash recovery in PostgreSQL. Before modified data pages are durably written to storage, corresponding WAL must be written per engine rules.

WAL also serves as the foundation for **replication**. However, distinguish its two main forms:

| Characteristic | Physical replication | Logical replication |
|---|---|---|
| Data shipped | Physical-level WAL to reproduce cluster state. | Logical change stream decoded from WAL per publication/subscription. |
| Scope | Typically the **entire physical PostgreSQL cluster**. | By **publication**, usually specifying selected tables and operations. |
| Receiving processes | Standby runs **WAL receiver**; recovery processes replay WAL. | Subscriber runs **logical replication apply worker** and possibly table sync workers. |
| Common goals | Standby for HA, disaster recovery, read scaling on hot standby. | Table sync between systems, partial/cross-version migrations, integrations. |
| Version/schema rules | Physical standbys have strict binary compatibility constraints; not an arbitrary upgrade tool. | Logical replication requires compatible tables/types/keys/schemas; does not replicate all DDL by default. |

Never treat a physical replica and a logical subscriber as the same thing. Although both can use WAL senders on the publisher/upstream, **how changes are received and applied differs fundamentally**.

## 12. Physical streaming replication: WAL sender and WAL receiver

In physical streaming replication, a PostgreSQL primary generates WAL and ships it to standbys over a replication connection.

```text
 PRIMARY                                        STANDBY
─────────                                     ───────────
Client writes SQL
     │
     ▼
Data changes + WAL
     │
     ▼
WAL sender  ────────── ships WAL ──────────►  WAL receiver
                                                   │
                                                   ▼
                                               Writes WAL
                                                   │
                                                   ▼
                                          Startup/recovery process
                                                   │
                                                   ▼
                                         Replays changes to data
```

### WAL sender

On the primary (or an upstream standby in cascading replication), a **WAL sender** serves a replication connection and streams WAL data downstream. Multiple standbys mean multiple WAL senders.

Related parameters:

- `wal_level`: level of detail written to WAL; must match replication needs.
- `max_wal_senders`: cap on concurrent WAL sender processes.
- `max_replication_slots`: number of replication slots available.
- `wal_keep_size`: safety retention of WAL aiding standbys in some scenarios; does not replace backups/PITR.
- `archive_mode` and `archive_command`: govern WAL archiving for PITR and recovery strategies.

These settings have version-specific details and config contexts; several require a restart.

### WAL receiver

On a physical standby, the **WAL receiver** connects upstream, receives WAL, and writes it according to standby storage rules. The startup/recovery process **replays WAL** so standby data tracks the source.

Distinguish:

- **WAL received** does not mean **replayed** up to the same LSN.
- **WAL replayed** does not automatically mean an application has permissions or read access depending on standby config.
- A standby may temporarily lack a WAL receiver if streaming is disconnected, yet still replay already-fetched WAL or pull segments from an archive depending on setup.

Therefore, monitoring WAL receivers requires combining **receive progress, replay progress, and connection state**.

## 13. Monitoring physical replication on the primary

On a server with active WAL senders serving replication, `pg_stat_replication` reports sender connection details:

```sql
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
FROM pg_stat_replication
ORDER BY application_name, pid;
```

General interpretation:

| Field | Interpretation |
|---|---|
| `pid` | PID of the WAL sender on the observed server. |
| `application_name` | Application name of the replication connection, commonly used to identify the standby. |
| `client_addr` | Replication client IP address when available. |
| `state` | WAL sender state, such as `streaming` or another phase. |
| `sync_state` | Standby sync state per synchronous replication policy. |
| `sent_lsn` | Last WAL position sent. |
| `write_lsn` | Last WAL position reported written downstream. |
| `flush_lsn` | Last WAL position reported flushed downstream. |
| `replay_lsn` | Last WAL position reported replayed downstream. |

LSN values represent **positions in the WAL stream**, not row counts or transaction counts. Distance between LSNs can be converted to bytes using `pg_wal_lsn_diff`, though bytes alone do not automatically convert into seconds of lag.

Example:

```sql
SELECT
    application_name,
    state,
    pg_wal_lsn_diff(sent_lsn, replay_lsn)
        AS sent_minus_replayed_bytes
FROM pg_stat_replication
WHERE sent_lsn IS NOT NULL
  AND replay_lsn IS NOT NULL;
```

This compares **sent position** against **reported replay position** to spot backlog at a point in time. Evaluating RPO requires knowing sync policy, commit behavior, and **actual WAL durability**; a single byte delta is insufficient to predict data loss on failover.

**Caution:** `pg_stat_replication` lives on the **WAL-sending upstream**; never query it on a standby and treat an empty result as proof the standby is not receiving data.

## 14. Monitoring WAL receiver on a standby

To check whether the current instance is in recovery/standby mode:

```sql
SELECT pg_is_in_recovery() AS is_standby;
```

`true` indicates recovery mode, typical on physical standbys. Then inspect the WAL receiver:

```sql
SELECT
    pid,
    status,
    receive_start_lsn,
    latest_end_lsn,
    last_msg_send_time,
    last_msg_receipt_time,
    sender_host,
    sender_port
FROM pg_stat_wal_receiver;
```

Columns and stats may vary across PostgreSQL versions; check the view definition on your target server if a column differs.

Functions to check WAL progress on a standby:

```sql
SELECT
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn()  AS replayed_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit_time;
```

And the byte gap between received and replayed WAL:

```sql
SELECT
    pg_wal_lsn_diff(
        pg_last_wal_receive_lsn(),
        pg_last_wal_replay_lsn()
    ) AS received_not_yet_replayed_bytes;
```

**Do not treat `now() - pg_last_xact_replay_timestamp()` as absolute lag in every situation.** If the primary has no recent write transactions, the last replayed commit timestamp grows old even while the standby is completely caught up. Combine LSN positions with knowledge of primary write activity.

### Distinguishing types of delay

```text
Primary generates WAL
       │
       ▼
WAL sender ships           → may lag due to network, sender, or source load
       │
       ▼
WAL receiver writes        → may lag due to network or standby I/O
       │
       ▼
Standby flushes WAL        → may lag due to storage speed
       │
       ▼
Standby replays WAL        → may lag due to replay speed, query conflicts,
                             I/O, or competing tasks
```

A standby showing `status='streaming'` **can still lag**, because connection state does not replace measuring receive and replay progress.

## 15. Logical replication: publisher, subscriber, and background workers

Physical replication reproduces physical changes cluster-wide. In **logical replication**, PostgreSQL decodes WAL into table-level changes and applies them on another PostgreSQL instance.

Terminology:

- **Publisher:** server publishing changes from one or more tables via a **publication**.
- **Subscriber:** server holding a **subscription**, receiving and applying published changes.
- **WAL sender/logical decoding:** on the publisher, streams logical changes matching the subscription.
- **Logical replication launcher:** on the subscriber, manages and spawns workers needed for subscriptions.
- **Apply worker:** on the subscriber, reads the stream and applies changes to target tables.
- **Table synchronization worker:** copies initial table data when a subscription requires initial synchronization.

Diagram:

```text
     PUBLISHER                               SUBSCRIBER
 ┌──────────────────┐                   ┌────────────────────────┐
 │ Source table     │                   │ Compatible target table│
 │ INSERT/UPDATE/...│                   │                        │
 └─────────┬────────┘                   └────────────▲───────────┘
           │                                         │
           ▼                                         │
     WAL + decoding                                  │
           │                                         │
           ▼                                         │
     WAL sender  ───────── logical stream ────► Apply worker
                                                     ▲
                                                     │
                                      Logical replication launcher
                                                     │
                                                     ▼
                                        Table sync worker (if initial
                                        data synchronization needed)
```

Logical replication supports flexible data synchronization, yet **does not replicate every database object by default**. DDL/schema changes are not applied automatically as in physical WAL replay; target schemas must be managed compatibly. Certain object types, sequences, or special operations have specific rules depending on version and design.

### Illustrative publication/subscription setup (conceptual only)

On a publisher with an eligible business table:

```sql
CREATE PUBLICATION sales_pub
FOR TABLE public.orders;
```

On a subscriber with a compatible target schema/table and replication role:

```sql
-- Syntax example; DO NOT run with placeholder host/account names.
CREATE SUBSCRIPTION sales_sub
CONNECTION 'host=publisher.example.internal port=5432 dbname=sales user=repl_user'
PUBLICATION sales_pub;
```

Creating a subscription can **connect to the publisher, create a replication slot**, and start synchronization; it does not merely store a passive config line. Prepare privileges, networking, security, replica identity, table schemas, and WAL disk headroom beforehand.

**Never embed plaintext passwords in migrations, shell history, or documentation.** Manage credentials through secure platform secret/authentication mechanisms.

## 16. Monitoring logical replication workers

On the **subscriber**, start with `pg_stat_subscription`:

```sql
SELECT
    subname,
    pid,
    relid,
    received_lsn,
    latest_end_lsn,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_time
FROM pg_stat_subscription
ORDER BY subname, pid;
```

Meaning:

- `subname`: subscription name.
- `pid`: worker PID described by the row if running; null when inactive.
- `relid`: distinguishes table sync workers per version/mechanism.
- `received_lsn`, `latest_end_lsn`, and timestamps: indicators of receive/apply progress, not guarantees that external non-PostgreSQL workflows are synchronized.

To inspect related processes:

```sql
SELECT
    pid,
    backend_type,
    application_name,
    state,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE backend_type LIKE '%logical replication%'
   OR backend_type = 'walsender'
ORDER BY backend_type, pid;
```

On the publisher, `pg_stat_replication` also displays WAL senders for logical replication connections. On the subscriber, apply/sync workers are bounded by `max_logical_replication_workers`, `max_sync_workers_per_subscription`, and overall `max_worker_processes`.

### When no apply worker appears

A subscription may be inactive or lacking a running worker because:

1. The subscription was disabled administratively.
2. The subscriber cannot connect to the publisher due to networking, authentication, privileges, or configuration.
3. Background worker slots are exhausted.
4. The apply worker stopped due to a schema mismatch, data type error, unique constraint violation, or similar failure.
5. Initial table synchronization or change application hit an error.

Read the **subscriber** logs first to spot apply errors, while checking WAL senders and slots on the publisher. Never conclude the subscriber lacks worker slots solely because one SQL snapshot showed no PID.

## 17. Replication slots: why slow workers can fill the disk

A **replication slot** persists state so PostgreSQL knows how much WAL or version data a consumer still requires. Slots prevent premature WAL deletion when consumers lag or disconnect briefly, yet also carry the risk of **retaining WAL indefinitely**.

On the server owning the slot:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

| Column | Basic meaning |
|---|---|
| `slot_name` | Slot name. |
| `slot_type` | `physical` or `logical`. |
| `active` | Whether a consumer is currently using the slot per PostgreSQL. |
| `restart_lsn` | Oldest WAL position the slot may still require retained. |
| `confirmed_flush_lsn` | Position confirmed processed per logical slot semantics; generally unused for physical slots. |

You can use `pg_wal_lsn_diff` to estimate WAL distance in bytes from current WAL to the retained boundary:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)
        AS wal_distance_bytes
FROM pg_replication_slots
WHERE restart_lsn IS NOT NULL;
```

The query above uses `pg_current_wal_lsn()` on a **primary**; do not apply it blindly on a standby in recovery. LSN distance measures **WAL stream distance**, not necessarily the exact filesystem space pinned exclusively by that slot due to segment boundaries, checkpoints, retention settings, and other consumers.

### Why never drop an inactive slot blindly?

`active = false` only means no consumer is connected to the slot at that moment. A subscriber might simply be down for maintenance. Dropping the slot can prevent the downstream consumer from **catching up from the existing stream**, forcing a full resync/rebuild.

Safe workflow:

1. Identify **who owns the slot** and which consumer relies on it.
2. Check subscription/standby status and maintenance windows.
3. Measure retained WAL, growth rate, remaining disk space, and alert thresholds.
4. Investigate why the consumer is slow or disconnected.
5. Modify or drop slots only per approved runbooks with a plan to rebuild the consumer if needed.

Settings like `max_slot_wal_keep_size` can cap how much WAL a slot retains per version/conditions, yet if exceeded and needed WAL is removed, the consumer may have to be reinitialized. Never assume such limits are completely free of side effects.

## 18. How are autovacuum and replication connected?

At first glance, autovacuum cleans dead tuples while replication ships WAL. In practice, they interact closely.

### 18.1. Autovacuum generates WAL and consumes I/O

Vacuuming generates WAL for necessary page and metadata modifications while consuming CPU and I/O. On a primary, WAL generated by vacuuming also affects shipping and replay load on standbys. Under heavy load, replication workers and autovacuum compete for storage resources.

**Never conclude "vacuum is always the cause of replication lag"** just because both happen concurrently. Measure WAL throughput, I/O, LSN progress, and wait events.

### 18.2. Replication slots can pin XID horizons

Certain replication slots—especially logical slots—can maintain `xmin` or `catalog_xmin` to protect tuple/catalog versions still needed by logical decoding. If a consumer stalls, holding an old snapshot or XID horizon can prevent reclaiming dead tuples, contributing to **table and catalog bloat**.

Inspect relevant columns depending on version:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    catalog_xmin
FROM pg_replication_slots
ORDER BY slot_name;
```

A null value does not automatically mean the slot has zero retention impact; check `restart_lsn` and configuration as well.

### 18.3. Long transactions hurt both vacuum and applications

A long-running read transaction holding an old snapshot can block vacuum from reclaiming tuples. On a hot standby, long queries can also conflict with replaying certain WAL records depending on conflict-handling and feedback settings.

For example, enabling `hot_standby_feedback` on a standby to reduce query cancellations can force the primary to retain older row versions longer, increasing bloat. This is a **trade-off between standby query continuity and primary space reclamation**, with no single universal setting for every workload.

## 19. Seeing background processes together through real scenarios

### Scenario A — PostgreSQL uses high CPU despite no large SQL requests

`pg_stat_activity` shows several active `autovacuum worker` processes. A table has a high `n_dead_tup` and a recent `last_autovacuum`.

**Approach:** check `pg_stat_progress_vacuum`, long transactions, update/delete churn, I/O, and worker thresholds. Never kill every autovacuum worker just because CPU rose; first determine whether this is essential maintenance or a workload shift.

### Scenario B — Streaming replica is connected, yet reads lag behind the primary

`pg_stat_replication.state` shows `streaming`, while `replay_lsn` trails far behind `sent_lsn`.

**Approach:** check WAL receiver status, receive-vs-replay lag, standby I/O, long standby queries, and replay conflicts. A live streaming connection does not guarantee data has replayed promptly.

### Scenario C — Logical subscription stalls after a schema change

A table or column type changed on the publisher without matching updates on the subscriber. The apply worker errors out and the subscription stops advancing.

**Approach:** inspect subscriber logs and `pg_stat_subscription`, compare source/target schemas, and never drop the slot just to "reset lag." Resolve the apply error or execute a planned resynchronization.

### Scenario D — pg_wal disk fills up when a consumer disconnects

A logical slot sits at `active=false` with `restart_lsn` far behind current WAL; WAL disk usage climbs rapidly.

**Approach:** identify the consumer, verify whether the slot is still needed, restore consumption, or reinitialize per policy. Never drop the slot before understanding downstream data-loss consequences.

### Scenario E — Parallel queries slow down while logical replication also backs up

An extension background worker and logical replication workers occupy the worker pool; SQL queries fail to receive expected parallelism.

**Approach:** inspect `max_worker_processes`, `max_parallel_workers`, `max_logical_replication_workers`, active processes, and host CPU/RAM/I/O. Never raise every limit simultaneously without verifying host resource headroom.

## 20. Operator monitoring workflow

A basic observation runbook can follow this order:

```text
1. Are the server and expected processes running?
          │
          ▼
   pg_stat_activity.backend_type
          │
          ▼
2. Is autovacuum keeping up with data churn?
          │
          ▼
   pg_stat_user_tables + pg_stat_progress_vacuum
          │
          ▼
3. Are WAL sender/receiver active and keeping up?
          │
          ▼
   pg_stat_replication (sender)
   pg_stat_wal_receiver (standby)
   pg_last_wal_receive/replay_lsn (standby)
          │
          ▼
4. Are logical apply workers and slots stalled?
          │
          ▼
   pg_stat_subscription + pg_replication_slots
          │
          ▼
5. Identify root cause:
   - long transactions / locks
   - schema conflicts
   - worker limits
   - CPU, I/O, network
   - WAL retention and disk space
          │
          ▼
6. Change per runbook, re-measure, and record evidence
```

### Monitoring principles to remember

- **A single snapshot is not a trend.** Collect metrics over time to see whether workers, dead tuples, WAL lag, and disk usage are rising or falling.
- **Statistics views have lag and privilege limits.** Some fields are estimates or nullable. Distinguish "no data/no privilege" from "zero activity."
- **Do not equate a live connection with synchronized data.** For replication, measure receive, flush, and replay in context.
- **Do not equate a present worker with a fault.** Long-running autovacuum may be vital; an idle replication sender may simply reflect zero new WAL.
- **Never change multiple settings at once.** Measure before/after, define rollback steps, and persist config changes if needed across restarts.
- **Never run destructive actions to troubleshoot blindly.** Dropping slots, killing processes, disabling autovacuum, or restarting in HA setups all require clear impact analysis.

## 21. Practice exercises

### Exercise 1 — Classify processes

Given a list of `backend_type` values: `client backend`, `autovacuum launcher`, `autovacuum worker`, `walsender`, `walreceiver`, `logical replication worker`, `parallel worker`, and `checkpointer`.

Group them into user query serving, data maintenance, replication, and other core server work. Explain why all of them should not be labeled "extension background workers."

### Exercise 2 — Observe with SQL

Write a query on `pg_stat_activity` returning `pid`, `backend_type`, `state`, and `wait_event` for background processes. Write a second query counting processes by `backend_type`. Explain why seeing zero `autovacuum worker` rows in one query does not prove autovacuum is disabled.

### Exercise 3 — Calculate an autovacuum threshold

Suppose a table has 2,000,000 rows, `autovacuum_vacuum_threshold=100`, and `autovacuum_vacuum_scale_factor=0.05`. Using the simple dead-tuple formula, what is the threshold?

*Hint:* `100 + 0.05 × 2,000,000 = 100,100` dead tuples. Name at least two other situations that trigger or influence autovacuum work.

### Exercise 4 — Autovacuum fails to reclaim dead tuples

`n_dead_tup` keeps climbing, autovacuum has run, yet table size continues bloating. Meanwhile, several long `idle in transaction` sessions and a lagging logical replication slot exist.

Describe how to check transaction age, `pg_replication_slots.xmin`/`catalog_xmin`, vacuum metrics, and why simply increasing `autovacuum_max_workers` may fail to fix the root cause.

### Exercise 5 — Diagnose replication lag

On the primary, `sent_lsn` advances steadily; on the standby, `pg_last_wal_receive_lsn()` stays close to sent LSN, while `pg_last_wal_replay_lsn()` lags significantly behind.

Following the sender → receiver → replay pipeline, which stage should you investigate first? Give examples of causes involving standby I/O, replay, and long standby queries.

### Exercise 6 — Logical replication missing apply worker

A subscription was created, yet `pg_stat_subscription` shows no active apply worker. Outline a diagnostic checklist from subscription status, privileges/connectivity, subscriber logs, and worker limits through publisher slots. Why should you not drop the slot immediately?

### Exercise 7 — Background worker limits

A system uses an extension background worker, logical replication, and parallel queries. Explain the differences among `max_worker_processes`, `max_logical_replication_workers`, and `max_parallel_workers`. List metrics to check before raising limits.

### Exercise 8 — Design a minimal dashboard

Design a PostgreSQL monitoring dashboard covering:

- Process counts by `backend_type`.
- Estimated dead tuples and `last_autovacuum`/`last_autoanalyze` on hot tables.
- `pg_stat_progress_vacuum` progress when active.
- WAL sent/received/replayed LSNs and lag.
- Logical subscription health and replication slots retaining WAL.
- Filesystem/WAL disk usage, CPU, I/O, and long-running transactions.

Explain how multi-point time-series data distinguishes healthy baselines from incidents.

## Conclusion

PostgreSQL's architecture comprises **multiple cooperating processes with distinct roles**. Backends serve client SQL; core auxiliary processes handle storage, WAL, and checkpoints; the **background worker** framework lets core and extensions run server-managed background tasks. **Autovacuum launcher and workers** perform vital maintenance in an MVCC engine: reclaiming reusable dead tuple space, refreshing statistics, and preventing XID wraparound.

In replication, the **WAL sender** on the source and the **WAL receiver plus recovery process** on the standby power physical streaming. In **logical replication**, the publisher streams decoded changes while the subscriber uses the **logical replication launcher, apply worker, and table synchronization workers** to synchronize data per publication/subscription.

To operate safely, combine observations across **`pg_stat_activity`, `pg_stat_user_tables`, `pg_stat_progress_vacuum`, `pg_stat_replication`, `pg_stat_wal_receiver`, `pg_stat_subscription`, and `pg_replication_slots`**. Never judge a process solely by its name or one point-in-time snapshot: understand the mechanism, measure progress and resource contention, and only then tune worker limits, autovacuum, or replication under controlled procedures.
