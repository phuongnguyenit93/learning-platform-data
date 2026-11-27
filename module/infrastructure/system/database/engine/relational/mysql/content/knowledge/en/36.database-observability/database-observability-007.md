# Monitoring Waits, Stages, Transactions, and Tasks by Thread

When MySQL is slow, looking only at `SHOW PROCESSLIST` is often insufficient to know which resource a session is waiting on, which processing stage a statement is in, how long a transaction has held locks, or what background threads are doing. **Performance Schema** provides events at the thread, wait, stage, statement, and transaction levels; the **sys schema** consolidates much of that data into more readable views.

This lesson belongs to the **System Observability** section of MySQL. You will link connections to `THREAD_ID`, monitor active waits and stages, inspect event history, observe active transactions, find InnoDB lock-wait relationships, and use summary metrics to identify bottlenecks. The goal is to turn a vague symptom like "the database is slow" into concrete per-thread and per-event evidence.

## 1. Distinguishing Connections, Threads, and Events

MySQL has several related identifiers that cannot be used interchangeably:

| Concept | Meaning | Where to Observe |
| --- | --- | --- |
| Connection ID | Client connection ID, typically shown in `SHOW PROCESSLIST` and `CONNECTION_ID()`. | `performance_schema.threads.PROCESSLIST_ID`, `SHOW PROCESSLIST`. |
| `THREAD_ID` | Internal thread ID tracked by Performance Schema. | `performance_schema.threads.THREAD_ID`. |
| Event | An instrumented activity, such as a wait, stage, statement, or transaction. | `events_*_current`, `events_*_history`, and `events_*_summary_*` tables. |
| Transaction ID | Storage engine transaction identifier, if applicable. | `events_transactions_*`, `data_locks`, `information_schema.innodb_trx`. |

A foreground connection normally has a non-NULL `PROCESSLIST_ID` mapped to a `THREAD_ID`. InnoDB or replication background threads may have no connection ID. Therefore, do not filter all observations solely by `PROCESSLIST_ID` when investigating background activity.

Check the current connection:

```sql
SELECT CONNECTION_ID();
```

List threads and processlist information:

```sql
SELECT
    THREAD_ID,
    PROCESSLIST_ID AS connection_id,
    TYPE,
    NAME,
    PROCESSLIST_USER,
    PROCESSLIST_HOST,
    PROCESSLIST_DB,
    PROCESSLIST_COMMAND,
    PROCESSLIST_STATE,
    PROCESSLIST_TIME
FROM performance_schema.threads
ORDER BY TYPE, THREAD_ID;
```

`TYPE` generally distinguishes `FOREGROUND` from `BACKGROUND`. `PROCESSLIST_STATE` may be NULL when a thread has no corresponding processlist state. `PROCESSLIST_TIME` is the duration in the current processlist state, not total connection lifetime.

## 2. Performance Schema and Event Tables

Performance Schema is MySQL's internal instrumentation and telemetry mechanism. Key tables include:

| Group | Example Tables | Question Answered |
| --- | --- | --- |
| Thread | `threads` | Which thread belongs to which connection? Is it foreground or background? |
| Wait | `events_waits_current`, `events_waits_history`, `events_waits_history_long` | Which mutex, I/O, lock, or resource is the thread waiting on? |
| Stage | `events_stages_current`, `events_stages_history_long` | Which processing phase is the statement in? |
| Statement | `events_statements_current`, `events_statements_history_long` | Which SQL statement is running or just ran? |
| Transaction | `events_transactions_current`, `events_transactions_history_long` | Is a transaction active, committing, or rolling back? When did it start and how long has it lasted? |
| InnoDB Locks | `data_locks`, `data_lock_waits` | Which transaction holds locks and which is waiting? |
| Metadata Locks | `metadata_locks` | Which DDL or query is waiting on a metadata lock? |
| Summary | `events_*_summary_*` | Which event types consumed the most time in the statistics window? |

Performance Schema is usually enabled when MySQL starts. Check:

```sql
SHOW VARIABLES LIKE 'performance_schema';
```

If set to `OFF`, you cannot enable all of Performance Schema with a `SET` statement while the server is running; configure it at startup and schedule an appropriate restart.

## 3. Consumers and Instruments: Is Data Being Collected?

Performance Schema has two control layers:

- **Instruments** define which operations are measured, such as `wait/io/file/innodb/%`, `wait/lock/metadata/sql/mdl`, `stage/sql/%`, or `statement/sql/%`.
- **Consumers** determine which events are written into current/history tables or summary tables.

Inspect consumer configuration:

```sql
SELECT NAME, ENABLED
FROM performance_schema.setup_consumers
ORDER BY NAME;
```

Inspect instruments:

```sql
SELECT NAME, ENABLED, TIMED
FROM performance_schema.setup_instruments
WHERE NAME LIKE 'wait/lock/%'
   OR NAME LIKE 'wait/io/file/innodb/%'
   OR NAME LIKE 'stage/sql/%'
   OR NAME = 'transaction'
ORDER BY NAME;
```

If the relevant consumer or instrument is disabled, the corresponding event table may be empty or missing metrics. Before concluding "there are no waits," verify that instruments and consumers are enabled.

### Targeted Enablement in a Test Environment

Example enabling selected instruments for investigating locks, InnoDB I/O, and SQL stages:

```sql
UPDATE performance_schema.setup_instruments
SET ENABLED = 'YES', TIMED = 'YES'
WHERE NAME = 'wait/lock/metadata/sql/mdl'
   OR NAME = 'wait/io/file/innodb/%'
   OR NAME LIKE 'stage/sql/%';

UPDATE performance_schema.setup_consumers
SET ENABLED = 'YES'
WHERE NAME IN (
    'global_instrumentation',
    'thread_instrumentation',
    'events_waits_current',
    'events_waits_history',
    'events_waits_history_long',
    'events_stages_current',
    'events_stages_history_long',
    'events_statements_current',
    'events_statements_history_long',
    'events_transactions_current',
    'events_transactions_history_long'
);
```

Actual instrument names depend on version and build; query `setup_instruments` before updating. Do not arbitrarily enable all instruments in production. Instrumentation incurs CPU and memory overhead, especially when keeping long histories for high-frequency events.

Changes to `setup_instruments` and `setup_consumers` take effect at runtime but should not be assumed to persist across restarts. To persist them, configure Performance Schema according to your MySQL version's documentation and verify after restarting.

## 4. Monitoring Active Waits

Wait events show which resource or internal operation a thread is waiting on. Examples include file I/O, mutexes, conditions, table locks, or metadata locks. Active waits are recorded in `events_waits_current` if the corresponding instruments and consumers are enabled.

```sql
SELECT
    w.THREAD_ID,
    t.PROCESSLIST_ID AS connection_id,
    t.PROCESSLIST_USER,
    t.PROCESSLIST_HOST,
    w.EVENT_NAME,
    w.OPERATION,
    w.OBJECT_SCHEMA,
    w.OBJECT_NAME,
    w.INDEX_NAME,
    ROUND(w.TIMER_WAIT / 1000000000000, 6) AS wait_seconds
FROM performance_schema.events_waits_current AS w
LEFT JOIN performance_schema.threads AS t
  ON t.THREAD_ID = w.THREAD_ID
WHERE w.END_EVENT_ID IS NULL
ORDER BY w.TIMER_WAIT DESC;
```

Performance Schema timers are expressed in picoseconds; divide by (10^{12}) to convert to seconds. `TIMER_WAIT` may be NULL if the instrument does not measure time (`TIMED = NO`). Current wait events are a point-in-time snapshot when queried; a brief wait may finish before your observation query executes.

### Distinguishing Waits from Processlist States

`SHOW PROCESSLIST` shows the high-level state of a connection, such as `Sending data`, `Waiting for table metadata lock`, or `Sleep`. `events_waits_current` provides finer-grained instrumented events. A connection might not be inside a wait at snapshot time while still performing CPU work or transitioning between stages.

Do not interpret every wait as an error. Brief I/O or mutex waits are normal parts of operation. Compare duration, frequency, event type, and impact on workload latency.

## 5. Reading Wait History and Aggregating by Event Type

`events_waits_history` keeps the most recent events per thread; `events_waits_history_long` keeps a shared history with bounded capacity. Once the ring buffer is full, older events are overwritten.

View recent waits:

```sql
SELECT
    THREAD_ID,
    EVENT_ID,
    EVENT_NAME,
    OPERATION,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    ROUND(TIMER_WAIT / 1000000000000, 6) AS wait_seconds
FROM performance_schema.events_waits_history_long
ORDER BY TIMER_START DESC
LIMIT 100;
```

Aggregate by wait type:

```sql
SELECT
    EVENT_NAME,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_wait_seconds,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_wait_seconds,
    ROUND(MAX_TIMER_WAIT / 1000000000000, 6) AS max_wait_seconds
FROM performance_schema.events_waits_summary_global_by_event_name
WHERE COUNT_STAR > 0
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Summary tables accumulate since startup or the most recent statistics reset. To measure the effect of a change, take before/after snapshots and compute deltas; never compare cumulative totals from two servers with different uptimes.

### History Sizing

Check history limits:

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'performance_schema_events_waits_history_size',
    'performance_schema_events_waits_history_long_size'
);
```

History tables have fixed configured capacities and overwrite old data. History is not a long-term log archive. If you need multi-day trends, scrape periodically into an external observability system.

## 6. Tracking Stages: Which Phase Is the Statement In?

Stages are internal phases of statement execution. Examples may include opening tables, optimizing queries, executing, sorting, or sending results; exact names and granularity depend on version and instruments.

View active stages:

```sql
SELECT
    s.THREAD_ID,
    t.PROCESSLIST_ID AS connection_id,
    t.PROCESSLIST_USER,
    s.EVENT_NAME AS stage_name,
    ROUND(s.TIMER_WAIT / 1000000000000, 6) AS stage_seconds,
    s.WORK_COMPLETED,
    s.WORK_ESTIMATED
FROM performance_schema.events_stages_current AS s
LEFT JOIN performance_schema.threads AS t
  ON t.THREAD_ID = s.THREAD_ID
WHERE s.END_EVENT_ID IS NULL
ORDER BY s.TIMER_WAIT DESC;
```

`WORK_COMPLETED` and `WORK_ESTIMATED` are only meaningful for stage instruments that provide progress information; they may be NULL. Not every stage provides reliable completion ratios.

Stage history:

```sql
SELECT
    THREAD_ID,
    EVENT_ID,
    EVENT_NAME,
    ROUND(TIMER_WAIT / 1000000000000, 6) AS stage_seconds
FROM performance_schema.events_stages_history_long
ORDER BY TIMER_START DESC
LIMIT 100;
```

Aggregate stages by type:

```sql
SELECT
    EVENT_NAME,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_seconds,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_seconds
FROM performance_schema.events_stages_summary_global_by_event_name
WHERE COUNT_STAR > 0
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

If a statement spends most of its time in sort-related stages, inspect `ORDER BY`, indexes, and temporary tables. If time is spent in stages sending data, inspect result volume, client consumption rate, and networking. Stages guide investigation; combine `EXPLAIN ANALYZE` and wait metrics to determine root causes.

## 7. Tracking Statements per Thread

`events_statements_current` shows the currently executing statement on each thread. Join with `threads` to retrieve connection info and SQL text:

```sql
SELECT
    t.THREAD_ID,
    t.PROCESSLIST_ID AS connection_id,
    t.PROCESSLIST_USER,
    t.PROCESSLIST_HOST,
    t.PROCESSLIST_STATE,
    es.EVENT_NAME,
    ROUND(es.TIMER_WAIT / 1000000000000, 6) AS statement_seconds,
    es.ROWS_EXAMINED,
    es.ROWS_SENT,
    es.SQL_TEXT
FROM performance_schema.threads AS t
JOIN performance_schema.events_statements_current AS es
  ON es.THREAD_ID = t.THREAD_ID
WHERE t.TYPE = 'FOREGROUND'
  AND es.END_EVENT_ID IS NULL
ORDER BY es.TIMER_WAIT DESC;
```

SQL text may contain sensitive literals. Grant read access only to personnel who need it for investigation; when sharing outputs externally, redact personal data, tokens, emails, or business secrets.

To view recent statements for a specific thread, use `events_statements_history` or `events_statements_history_long`:

```sql
SELECT
    THREAD_ID,
    EVENT_ID,
    EVENT_NAME,
    ROUND(TIMER_WAIT / 1000000000000, 6) AS statement_seconds,
    ROWS_EXAMINED,
    ROWS_SENT,
    SQL_TEXT
FROM performance_schema.events_statements_history_long
WHERE THREAD_ID = 12345
ORDER BY EVENT_ID DESC
LIMIT 20;
```

Replace `12345` with the target `THREAD_ID`, not the connection ID. `EVENT_ID` is ordered within a thread; history_long may overwrite old entries and does not guarantee retaining every statement.

## 8. Monitoring Open Transactions

Long-running transactions can hold row locks, metadata locks, or old snapshots for extended periods, increasing lock waits and impeding purge. `events_transactions_current` shows active transactions for instrumented threads:

```sql
SELECT
    trx.THREAD_ID,
    t.PROCESSLIST_ID AS connection_id,
    t.PROCESSLIST_USER,
    t.PROCESSLIST_HOST,
    trx.EVENT_ID,
    trx.STATE,
    trx.TRX_ID,
    trx.ACCESS_MODE,
    trx.ISOLATION_LEVEL,
    trx.AUTOCOMMIT,
    ROUND(trx.TIMER_WAIT / 1000000000000, 3) AS transaction_seconds
FROM performance_schema.events_transactions_current AS trx
LEFT JOIN performance_schema.threads AS t
  ON t.THREAD_ID = trx.THREAD_ID
ORDER BY trx.TIMER_WAIT DESC;
```

Transaction events may not appear if transaction instrumentation or its consumer is disabled. `TIMER_WAIT` measures the duration of the transaction event recorded by Performance Schema; not every transaction will have full info if instrumentation was not enabled beforehand.

### Cross-Referencing InnoDB Transactions

`information_schema.innodb_trx` provides InnoDB-layer transaction details:

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id AS connection_id,
    trx_operation_state,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

This is a useful source for locating long-running transactions, transactions waiting on locks, or transactions modifying many rows. `trx_mysql_thread_id` corresponds to the client connection ID; join it with `performance_schema.threads.PROCESSLIST_ID` to obtain `THREAD_ID`.

```sql
SELECT
    t.THREAD_ID,
    t.PROCESSLIST_ID AS connection_id,
    t.PROCESSLIST_USER,
    t.PROCESSLIST_STATE,
    trx.trx_id,
    trx.trx_started,
    trx.trx_state,
    trx.trx_rows_locked,
    trx.trx_rows_modified,
    trx.trx_query
FROM information_schema.innodb_trx AS trx
LEFT JOIN performance_schema.threads AS t
  ON t.PROCESSLIST_ID = trx.trx_mysql_thread_id
ORDER BY trx.trx_started;
```

A long transaction is not necessarily a bug: it could be a legitimate batch job or maintenance task. Evaluate its purpose, duration, locked/modified row counts, and impact on other sessions before intervening.

## 9. Finding Waiting and Holding Row-Lock Transactions

MySQL 8.0 provides `performance_schema.data_locks` and `data_lock_waits` to observe InnoDB locks. This is the modern replacement for relying on the legacy `INFORMATION_SCHEMA.INNODB_LOCKS`/`INNODB_LOCK_WAITS` tables.

### Viewing Current Locks

```sql
SELECT
    ENGINE_TRANSACTION_ID,
    THREAD_ID,
    EVENT_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks
ORDER BY OBJECT_SCHEMA, OBJECT_NAME, THREAD_ID;
```

`LOCK_STATUS` typically shows whether a lock is `GRANTED` or `WAITING`. `LOCK_DATA` may contain locked key values or be NULL depending on lock type or record availability. Do not expose sensitive lock data to unauthorized destinations.

### Joining Waiters and Blockers

```sql
SELECT
    req.THREAD_ID AS waiting_thread_id,
    wt.PROCESSLIST_ID AS waiting_connection_id,
    wt.PROCESSLIST_USER AS waiting_user,
    req.ENGINE_TRANSACTION_ID AS waiting_trx_id,
    req.OBJECT_SCHEMA,
    req.OBJECT_NAME,
    req.INDEX_NAME,
    req.LOCK_TYPE,
    req.LOCK_MODE AS waiting_lock_mode,
    blk.THREAD_ID AS blocking_thread_id,
    bt.PROCESSLIST_ID AS blocking_connection_id,
    bt.PROCESSLIST_USER AS blocking_user,
    blk.ENGINE_TRANSACTION_ID AS blocking_trx_id,
    blk.LOCK_MODE AS blocking_lock_mode,
    req.LOCK_DATA
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS req
  ON req.ENGINE = w.ENGINE
 AND req.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blk
  ON blk.ENGINE = w.ENGINE
 AND blk.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID
LEFT JOIN performance_schema.threads AS wt
  ON wt.THREAD_ID = req.THREAD_ID
LEFT JOIN performance_schema.threads AS bt
  ON bt.THREAD_ID = blk.THREAD_ID;
```

The output identifies the waiting thread/connection, blocking thread/connection, table/index, and lock modes. A blocker may not be executing a statement at the moment of observation while still holding an open transaction and previously acquired locks.

### Using sys.innodb_lock_waits

If the sys schema is available, `sys.innodb_lock_waits` offers a more concise view:

```sql
SELECT
    wait_started,
    wait_age,
    waiting_pid,
    waiting_query,
    waiting_trx_id,
    blocking_pid,
    blocking_query,
    blocking_trx_id,
    locked_table,
    locked_index
FROM sys.innodb_lock_waits
ORDER BY wait_age_secs DESC;
```

This view aggregates information from Performance Schema and InnoDB. If the view is absent or the account lacks privileges, use the `data_lock_waits` query above.

## 10. Monitoring Metadata Locks

Metadata locks (MDL) protect table definitions and schema objects while queries or DDL operations use them. For example, a long-open transaction can hold a metadata lock on a table; an `ALTER TABLE` needing an exclusive lock must wait.

Inspect metadata locks:

```sql
SELECT
    ml.OBJECT_TYPE,
    ml.OBJECT_SCHEMA,
    ml.OBJECT_NAME,
    ml.LOCK_TYPE,
    ml.LOCK_DURATION,
    ml.LOCK_STATUS,
    ml.OWNER_THREAD_ID,
    t.PROCESSLIST_ID AS connection_id,
    t.PROCESSLIST_USER,
    t.PROCESSLIST_STATE
FROM performance_schema.metadata_locks AS ml
LEFT JOIN performance_schema.threads AS t
  ON t.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.LOCK_STATUS = 'PENDING'
   OR ml.LOCK_STATUS = 'GRANTED'
ORDER BY ml.OBJECT_SCHEMA, ml.OBJECT_NAME, ml.LOCK_STATUS;
```

Focus on `PENDING` rows to find waiting lock requests, then examine `GRANTED` rows on the same object. Not every granted lock blocks DDL; check lock types and compatibility rules.

When DDL waits on a metadata lock, do not rashly kill the waiting query. Find the transaction or session holding the lock for a long time, and check its owner and business impact. Terminating a blocking connection can trigger a transaction rollback and create heavy load.

## 11. Using sys Schema to Inspect Threads and Sessions Faster

The sys schema provides aggregated views over Performance Schema. A helpful view is `sys.processlist`:

```sql
SELECT
    thd_id,
    conn_id,
    user,
    db,
    command,
    state,
    time,
    statement_latency,
    lock_latency,
    rows_examined,
    rows_sent,
    tmp_tables,
    tmp_disk_tables,
    full_scan,
    current_statement,
    last_wait
FROM sys.processlist
ORDER BY statement_latency DESC;
```

This view presents connections/threads, statement latency, lock latency, row counts, and the most recent wait in a readable interface. Column names and views may differ across sys schema versions; verify with `DESCRIBE sys.processlist` if a query fails compatibility checks.

To locate sessions running slow statements, `sys.processlist` is often simpler than manually joining several tables. However, when analyzing specific events or background threads, querying Performance Schema directly remains necessary.

## 12. Two-Session Experiment: Observing a Row-Lock Wait

Create a lab table and one row of data:

```sql
CREATE TABLE observability_lock_lab (
    item_id INT PRIMARY KEY,
    quantity INT NOT NULL
) ENGINE = InnoDB;

INSERT INTO observability_lock_lab (item_id, quantity)
VALUES (1, 10);
```

Open three connections: session A, session B, and session C for observation.

**Session A — acquire a lock and keep the transaction open:**

```sql
START TRANSACTION;

UPDATE observability_lock_lab
SET quantity = quantity + 1
WHERE item_id = 1;

-- Not committed yet; the row lock remains held.
```

**Session B — request an update on the same row:**

```sql
START TRANSACTION;

UPDATE observability_lock_lab
SET quantity = quantity + 5
WHERE item_id = 1;
-- The statement will wait on the lock held by session A.
```

**Session C — observe the lock wait:**

```sql
SELECT
    req.THREAD_ID AS waiting_thread_id,
    wt.PROCESSLIST_ID AS waiting_connection_id,
    blk.THREAD_ID AS blocking_thread_id,
    bt.PROCESSLIST_ID AS blocking_connection_id,
    req.OBJECT_NAME,
    req.INDEX_NAME,
    req.LOCK_MODE AS waiting_mode,
    blk.LOCK_MODE AS blocking_mode,
    req.LOCK_DATA
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS req
  ON req.ENGINE = w.ENGINE
 AND req.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blk
  ON blk.ENGINE = w.ENGINE
 AND blk.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID
LEFT JOIN performance_schema.threads AS wt
  ON wt.THREAD_ID = req.THREAD_ID
LEFT JOIN performance_schema.threads AS bt
  ON bt.THREAD_ID = blk.THREAD_ID;
```

The result should show session B waiting and session A blocking on the row in `observability_lock_lab`. If no rows appear, verify that session B is actually waiting, the relevant consumers/instruments are active, and the query ran at the right moment.

Commit in **session A**:

```sql
COMMIT;
```

Session B will proceed once the lock is released. After the UPDATE in B completes:

```sql
COMMIT;
```

Verify the final data and close the transactions. In a lab environment, drop the table afterward:

```sql
DROP TABLE observability_lock_lab;
```

Never run long lock-holding experiments on production tables. If testing in a shared environment, use an isolated test table and limit wait timeouts.

## 13. Diagnosing Background Threads and Long Tasks

Not all activity is tied to a client connection. InnoDB uses background threads for purge, page cleaning, I/O, and internal tasks; replication uses threads to receive and apply events. These threads appear in `performance_schema.threads` with `TYPE = 'BACKGROUND'` and a NULL `PROCESSLIST_ID`.

List background threads:

```sql
SELECT
    THREAD_ID,
    NAME,
    TYPE,
    PROCESSLIST_STATE
FROM performance_schema.threads
WHERE TYPE = 'BACKGROUND'
ORDER BY NAME, THREAD_ID;
```

Join with active waits:

```sql
SELECT
    t.THREAD_ID,
    t.NAME,
    w.EVENT_NAME,
    w.OPERATION,
    w.OBJECT_NAME,
    ROUND(w.TIMER_WAIT / 1000000000000, 6) AS wait_seconds
FROM performance_schema.threads AS t
JOIN performance_schema.events_waits_current AS w
  ON w.THREAD_ID = t.THREAD_ID
WHERE t.TYPE = 'BACKGROUND'
  AND w.END_EVENT_ID IS NULL
ORDER BY w.TIMER_WAIT DESC;
```

A background thread waiting on an event does not necessarily indicate a problem; it may simply be idle waiting for work. Inspect the event name, frequency, duration, and related system metrics before concluding a thread is hung.

## 14. Limits, Overhead, and Access Privileges

Performance Schema is designed for relatively low-overhead observability, yet enabling too many instruments and keeping large histories still incurs CPU, memory, and query costs.

Principles:

1. Enable only the instruments needed for the current investigative question.
2. Enable history_long deliberately; tables have bounded capacity and overwrite older data.
3. Avoid polling full history scans continuously on heavily loaded servers; constrain time ranges, threads, and row limits.
4. Compute summary deltas rather than resetting statistics in production just to build charts.
5. Do not collect or share SQL text, lock data, or user information without proper authorization and purpose.
6. Re-verify instrumentation state after server restarts and version upgrades.

To view other users' sessions via the process list, an account may require the `PROCESS` privilege; read access to Performance Schema and the sys schema should also follow least privilege. Do not grant broad administrative privileges merely so a dashboard can read a few observability tables.

Some history sizes are controlled by startup configuration variables, for example:

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'performance_schema_events_waits_history_size',
    'performance_schema_events_waits_history_long_size',
    'performance_schema_events_stages_history_long_size',
    'performance_schema_events_statements_history_long_size',
    'performance_schema_events_transactions_history_long_size'
);
```

Increasing history sizes increases memory consumption. Base sizing on the required retention window and event rate rather than setting every limit to its maximum.

## 15. Workflow for Investigating a Slowness Incident

When receiving an alert about rising latency or application timeouts, follow this sequence:

1. **Determine scope:** is it one connection, one query digest, one schema, or the entire instance?
2. **List threads:** use `performance_schema.threads` or `sys.processlist` to check connections, users, states, and statements.
3. **Inspect statements:** read SQL text, duration, rows examined/sent, and execution plans if the query is still running or reproducible.
4. **Inspect waits:** check `events_waits_current` and history to see whether threads are waiting on I/O, mutexes, locks, or other resources.
5. **Inspect stages:** check `events_stages_current` to see which processing phase statements are in.
6. **Inspect transactions:** locate long transactions, locked/modified row counts, and retained snapshots.
7. **Inspect blockers:** use `data_lock_waits`, `data_locks`, `metadata_locks`, or `sys.innodb_lock_waits`.
8. **Cross-check summaries:** identify which wait/stage/statement types consumed the most time in the measurement window.
9. **Intervene safely:** optimize queries, adjust indexes, handle blocking transactions, or shed load per runbook.
10. **Re-measure:** compare latency, wait time, throughput, and lock waits after the change.

When considering terminating a query, distinguish `KILL QUERY connection_id` (stops the current statement) from `KILL CONNECTION connection_id` (closes the connection and may force a transaction rollback). Verify the exact connection, owner, and impact before acting; rolling back a large transaction can continue consuming resources for a noticeable time.

## 16. Self-Check Exercises

1. Distinguish `PROCESSLIST_ID` from `THREAD_ID`. Why is joining through `performance_schema.threads` necessary?
2. How do instruments and consumers differ?
3. What question does `events_waits_current` answer? Why does an empty table not prove there are no waits?
4. How do stages differ from waits? Does `WORK_COMPLETED` always have a value?
5. How do you inspect wait history and total time by event type?
6. Compare `events_transactions_current` with `information_schema.innodb_trx`.
7. How do you use `data_lock_waits` and `data_locks` to identify waiters and blockers?
8. How can a metadata lock cause DDL to wait when another transaction stays open for a long time?
9. Why can a background thread have a NULL `PROCESSLIST_ID`?
10. Design an investigation workflow from a latency alert down to threads, waits, stages, transactions, and blockers.

Effective observability connects **thread → statement → stage/wait → transaction → lock or resource → workload impact**. When identifiers and timestamps are accurately correlated, a DBA can distinguish CPU-heavy queries, I/O-bound queries, lock-holding transactions, and background threads performing legitimate work.
