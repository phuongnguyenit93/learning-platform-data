# Analyzing Locks, Metadata Locks, and Blocking Sessions

When an SQL statement hangs, the cause may be another transaction holding locks on data rows, a DDL operation waiting on a metadata lock, or multiple sessions forming a blocking chain. To resolve it properly, you must identify the **waiting session**, the **lock-holding session**, the locked object, and which transaction needs to finish.

In MySQL, InnoDB row locks and metadata locks (MDL) are two distinct mechanisms. Row locks protect data during locking reads or writes; MDL protects the metadata of objects such as tables and schemas while statements access or alter object structure. Both can force queries to wait, yet they require different observation tools and remediation steps.

## 1. Distinguishing Lock Types and Wait Scenarios

| Mechanism | What It Protects | Common Examples | Where to Observe |
|---|---|---|---|
| InnoDB record/gap/next-key locks | Index records and gaps between them | `UPDATE`, `DELETE`, `SELECT ... FOR UPDATE` | `performance_schema.data_locks`, `data_lock_waits`, `sys.innodb_lock_waits` |
| InnoDB intention/table locks | Signals row-level locking intent and interacts with table locks | Transactions taking row locks, `LOCK TABLES` | `performance_schema.data_locks`, `SHOW ENGINE INNODB STATUS` |
| Metadata locks (MDL) | Metadata of schemas, tables, views, routines, and related objects | Open transaction reading a table, `ALTER TABLE`, `DROP TABLE` | `performance_schema.metadata_locks`, `sys.schema_table_lock_waits` |
| Deadlock | Cyclic lock-wait dependency between transactions | A holds row 1 waiting for row 2; B holds row 2 waiting for row 1 | `SHOW ENGINE INNODB STATUS`, error log if deadlock logging enabled |

A `Sleep` session can still hold a transaction and locks. The `Sleep` state only means the connection is not currently executing a statement; it does not prove the transaction has committed or rolled back.

## 2. Understanding InnoDB Row Locks

InnoDB locks index entries to protect locking reads and writes. Depending on query predicates, isolation level, and access path, locks can include:

- **Record lock:** locks a specific index entry.
- **Gap lock:** locks the gap between index entries to prevent other transactions from inserting into that gap when required.
- **Next-key lock:** combines a record lock with the gap lock immediately preceding the index entry.
- **Insert intention lock:** signals a transaction's intent to insert into a gap; inserts at different positions in the same gap generally do not conflict with one another.
- **Intention lock:** table-level lock such as `IS` or `IX`, indicating the transaction's intent to acquire shared or exclusive row-level locks.

Example of two transactions updating the same row:

```sql
-- Session A
START TRANSACTION;
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 9001;
-- Not committed yet
```

```sql
-- Session B
UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 9001;
-- May wait on the lock held by A
```

Only when Session A commits or rolls back can Session B proceed. In InnoDB, locks are normally held until the transaction ends, not merely until the `UPDATE` statement returns.

### Why Indexes Affect Lock Scope

InnoDB locks the index records traversed during query execution. A query with a suitable index and selective predicate locks fewer entries. A query scanning wide ranges or lacking an index may touch and lock far more entries than expected, increasing contention.

For example, if `product_id` is the primary key, an equality predicate on `product_id` targets a single record. If the predicate uses an unindexed column, the engine may scan many rows; the actual lock scope depends on the access path and isolation level. Use `EXPLAIN` alongside lock data to understand which index the query traversed.

Do not assume every `SELECT` acquires row locks. Standard InnoDB consistent reads use MVCC and do not lock read rows the way `SELECT ... FOR UPDATE` does. Only locking reads such as `FOR UPDATE` or `FOR SHARE`, along with write statements, acquire corresponding locks.

## 3. What Is a Metadata Lock (MDL)?

MySQL uses metadata locks to protect object definitions and metadata while sessions are using those objects. MDL prevents structural changes from occurring concurrently in a way that would expose inconsistent metadata to other queries.

Table-accessing statements such as `SELECT`, `INSERT`, `UPDATE`, and `DELETE` acquire appropriate MDL locks. DDL statements such as `ALTER TABLE`, `DROP TABLE`, and `RENAME TABLE` typically require an exclusive MDL or corresponding lock level during metadata changes.

Key point: a transaction can hold MDL until the transaction ends. Thus, a session that ran a `SELECT` inside a long-open transaction can force `ALTER TABLE` to wait, even after the `SELECT` finished and the session is now `Sleep`.

### Simulating DDL Blocked by a Reading Transaction

```sql
-- Session A
START TRANSACTION;
SELECT * FROM orders WHERE order_id = 7001;
-- Keep transaction open without COMMIT/ROLLBACK
```

```sql
-- Session B
ALTER TABLE orders ADD COLUMN source VARCHAR(30);
-- Waiting for metadata lock from Session A
```

Session A may hold no row locks after a normal consistent read, yet it still holds an MDL on the `orders` table. Session B needs a conflicting metadata lock to alter the table and must wait.

When an exclusive MDL request is waiting, new queries against the same object may also queue behind it depending on lock priority rules. One long-running read transaction can trigger a pileup: DDL waits on the old transaction, and subsequent new queries queue behind the DDL.

### Common MDL States

In `performance_schema.metadata_locks`, `LOCK_STATUS` typically shows:

- `GRANTED`: lock has been granted.
- `PENDING`: lock is waiting to be granted.

`LOCK_TYPE` indicates the request type such as `SHARED_READ`, `SHARED_WRITE`, `SHARED_UPGRADABLE`, or `EXCLUSIVE`. `LOCK_DURATION` indicates how long the lock is held, typically `STATEMENT`, `TRANSACTION`, or `EXPLICIT`.

## 4. Quickly Viewing Open InnoDB Transactions

`information_schema.innodb_trx` provides information on current InnoDB transactions. Start with:

```sql
SELECT trx_id,
       trx_state,
       trx_started,
       TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
       trx_mysql_thread_id AS connection_id,
       trx_query,
       trx_tables_locked,
       trx_rows_locked,
       trx_rows_modified,
       trx_isolation_level
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Useful fields:

- `trx_started`: when the transaction began; old transactions usually deserve close inspection.
- `trx_state`: state such as `RUNNING` or `LOCK WAIT`.
- `trx_mysql_thread_id`: connection ID used with `SHOW PROCESSLIST` or `KILL`.
- `trx_query`: current SQL if the transaction is actively running a statement; may be `NULL` if the connection is idle.
- `trx_rows_locked` and `trx_rows_modified`: counts of locked and modified rows reported for the transaction.

To join with user, host, and connection state:

```sql
SELECT t.PROCESSLIST_ID AS connection_id,
       t.PROCESSLIST_USER AS user_name,
       t.PROCESSLIST_HOST AS client_host,
       t.PROCESSLIST_DB AS current_db,
       t.PROCESSLIST_COMMAND AS command_name,
       t.PROCESSLIST_TIME AS command_seconds,
       t.PROCESSLIST_STATE AS process_state,
       trx.trx_id,
       trx.trx_state,
       trx.trx_started,
       trx.trx_query
FROM information_schema.innodb_trx AS trx
LEFT JOIN performance_schema.threads AS t
       ON t.PROCESSLIST_ID = trx.trx_mysql_thread_id
ORDER BY trx.trx_started;
```

If `PROCESSLIST_COMMAND` is `Sleep` while the transaction still appears in `innodb_trx`, the connection is idle with an open transaction. This is a critical clue when investigating blockers.

## 5. Analyzing InnoDB Lock Waits with the sys Schema

On MySQL 8.0, a convenient starting point is `sys.innodb_lock_waits`. This view combines lock-wait, transaction, and connection details to show who is waiting on whom:

```sql
SELECT wait_started,
       wait_age,
       waiting_pid,
       waiting_query,
       locked_table,
       locked_index,
       waiting_trx_rows_locked,
       blocking_pid,
       blocking_query,
       blocking_trx_age,
       blocking_trx_rows_locked,
       sql_kill_blocking_query,
       sql_kill_blocking_connection
FROM sys.innodb_lock_waits
ORDER BY wait_age_secs DESC;
```

Meaning:

- `waiting_pid`: waiting connection ID.
- `waiting_query`: statement waiting on the lock.
- `locked_table` and `locked_index`: table and index involved in the lock wait.
- `blocking_pid`: connection ID holding the blocking lock.
- `blocking_query`: blocker's current statement if any; may be `NULL` if the blocker is idle.
- `blocking_trx_age`: age of the blocking transaction.
- `sql_kill_blocking_query` and `sql_kill_blocking_connection`: suggested statements to terminate the blocking query or connection; these are suggestions only and should never be executed blindly.

One blocker can block multiple waiters. Group by `blocking_pid` to identify high-impact blockers:

```sql
SELECT blocking_pid,
       COUNT(*) AS waiting_sessions,
       MAX(wait_age_secs) AS longest_wait_seconds,
       MAX(blocking_trx_age) AS blocking_trx_age
FROM sys.innodb_lock_waits
GROUP BY blocking_pid
ORDER BY waiting_sessions DESC, longest_wait_seconds DESC;
```

`sys.innodb_lock_waits` depends on Performance Schema and underlying system tables. If the view returns no rows, do not assume there are no locks; verify version, privileges, and instrumentation first.

## 6. Inspecting Lock Details with Performance Schema

In MySQL 8.0, `performance_schema.data_locks` lists existing InnoDB locks and `performance_schema.data_lock_waits` describes relationships between requesting and blocking locks.

Check locks on a specific table:

```sql
SELECT ENGINE,
       ENGINE_TRANSACTION_ID,
       THREAD_ID,
       OBJECT_SCHEMA,
       OBJECT_NAME,
       INDEX_NAME,
       LOCK_TYPE,
       LOCK_MODE,
       LOCK_STATUS,
       LOCK_DATA
FROM performance_schema.data_locks
WHERE OBJECT_SCHEMA = DATABASE()
  AND OBJECT_NAME = 'orders'
ORDER BY ENGINE_TRANSACTION_ID, INDEX_NAME;
```

`LOCK_MODE` can show modes such as `S`, `X`, `IS`, `IX`, `GAP`, `REC_NOT_GAP`, or combinations depending on lock type. `LOCK_DATA` may contain the locked record's key values; it is not always populated.

The following query joins waiting locks with blocking locks and their corresponding threads:

```sql
SELECT w.REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx_id,
       wt.PROCESSLIST_ID AS waiting_connection_id,
       r.OBJECT_SCHEMA,
       r.OBJECT_NAME,
       r.INDEX_NAME,
       r.LOCK_MODE AS requested_lock_mode,
       r.LOCK_DATA AS requested_lock_data,
       w.BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx_id,
       bt.PROCESSLIST_ID AS blocking_connection_id,
       b.LOCK_MODE AS blocking_lock_mode,
       b.LOCK_DATA AS blocking_lock_data
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS r
  ON r.ENGINE = w.ENGINE
 AND r.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS b
  ON b.ENGINE = w.ENGINE
 AND b.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID
LEFT JOIN performance_schema.threads AS wt
  ON wt.THREAD_ID = w.REQUESTING_THREAD_ID
LEFT JOIN performance_schema.threads AS bt
  ON bt.THREAD_ID = w.BLOCKING_THREAD_ID;
```

`data_lock_waits` represents relationships between locks, not a list of every existing lock. Use `data_locks` to inspect granted or waiting locks; use `data_lock_waits` to identify waiter/blocker pairs.

## 7. Analyzing Metadata Lock Waits

MDL is observed in `performance_schema.metadata_locks`. The following query lists pending requests alongside granted locks on the same objects:

```sql
SELECT ml.OBJECT_TYPE,
       ml.OBJECT_SCHEMA,
       ml.OBJECT_NAME,
       ml.LOCK_TYPE,
       ml.LOCK_DURATION,
       ml.LOCK_STATUS,
       th.PROCESSLIST_ID AS connection_id,
       th.PROCESSLIST_USER AS user_name,
       th.PROCESSLIST_HOST AS client_host,
       th.PROCESSLIST_COMMAND AS command_name,
       th.PROCESSLIST_TIME AS command_seconds,
       esc.SQL_TEXT AS current_sql
FROM performance_schema.metadata_locks AS ml
LEFT JOIN performance_schema.threads AS th
       ON th.THREAD_ID = ml.OWNER_THREAD_ID
LEFT JOIN performance_schema.events_statements_current AS esc
       ON esc.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.LOCK_STATUS IN ('PENDING', 'GRANTED')
  AND ml.OBJECT_SCHEMA = DATABASE()
ORDER BY ml.OBJECT_NAME, ml.LOCK_STATUS, th.PROCESSLIST_ID;
```

This query helps inspect locks on the same object, though it does not automatically evaluate every compatibility/conflict rule among MDL types. To view waiting and blocking session pairs more readably, use `sys.schema_table_lock_waits`:

```sql
SELECT object_schema,
       object_name,
       waiting_pid,
       waiting_account,
       waiting_lock_type,
       waiting_query,
       waiting_query_secs,
       blocking_pid,
       blocking_account,
       blocking_lock_type,
       bsql.SQL_TEXT AS blocking_current_sql,
       sql_kill_blocking_query,
       sql_kill_blocking_connection
FROM sys.schema_table_lock_waits AS waits
LEFT JOIN performance_schema.threads AS bt
       ON bt.THREAD_ID = waits.blocking_thread_id
LEFT JOIN performance_schema.events_statements_current AS bsql
       ON bsql.THREAD_ID = bt.THREAD_ID
ORDER BY waiting_query_secs DESC;
```

This view focuses on metadata lock waits on table objects. It provides thread ID, connection ID, and lock details for waiter/blocker; the blocker's current SQL is pulled from `events_statements_current`. `blocking_current_sql` may be `NULL` if the blocking session is no longer running SQL while its transaction stays open. In that case, join `blocking_pid` with `innodb_trx` and `threads` to check when the transaction started, which user owns the connection, and its current state.

### Checking MDL Instrumentation

If `metadata_locks` does not provide expected data, check the instrument:

```sql
SELECT NAME, ENABLED, TIMED
FROM performance_schema.setup_instruments
WHERE NAME = 'wait/lock/metadata/sql/mdl';
```

If the instrument is disabled and you have administrative privileges, enable it to resume collection:

```sql
UPDATE performance_schema.setup_instruments
SET ENABLED = 'YES', TIMED = 'YES'
WHERE NAME = 'wait/lock/metadata/sql/mdl';
```

Enable only when needed and in line with operational policy. Changing instrumentation can affect overhead and observability scope; do not update all of `setup_instruments` indiscriminately. After the investigation, restore its prior state if policy requires.

## 8. Matching the Blocker to Its Statement and Transaction

The currently displayed SQL is not always the statement that acquired the lock. A transaction may run several statements: the first acquired an MDL or row lock, subsequent ones finished, and the connection returned to `Sleep` while the transaction remained uncommitted.

When `blocking_query` is `NULL`, check:

1. `information_schema.innodb_trx` for open transactions, transaction age, and locked row counts.
2. `performance_schema.threads` for connection ID, user, host, command, and state.
3. `performance_schema.events_statements_current` for the running statement; if empty, check `events_statements_history` or `events_statements_history_long` if consumers are enabled and entries remain in history.
4. Application logs to trace which request started the transaction and why it has not committed or rolled back.

Example: viewing recent statements for threads holding open transactions:

```sql
SELECT th.PROCESSLIST_ID AS connection_id,
       th.PROCESSLIST_USER AS user_name,
       th.PROCESSLIST_HOST AS client_host,
       th.PROCESSLIST_COMMAND AS command_name,
       th.PROCESSLIST_TIME AS command_seconds,
       esh.EVENT_ID,
       esh.SQL_TEXT,
       esh.TIMER_WAIT
FROM performance_schema.threads AS th
JOIN information_schema.innodb_trx AS trx
  ON trx.trx_mysql_thread_id = th.PROCESSLIST_ID
LEFT JOIN performance_schema.events_statements_history AS esh
  ON esh.THREAD_ID = th.THREAD_ID
WHERE th.TYPE = 'FOREGROUND'
ORDER BY th.PROCESSLIST_ID, esh.EVENT_ID DESC;
```

History retains only recent statements in a bounded buffer and may be disabled. Missing history rows do not mean the connection ran no prior SQL. Cross-check application logs and transaction age.

## 9. Distinguishing Lock Waits from Deadlocks

A **lock wait** occurs when one transaction waits for a lock held by another. Once the blocker finishes, the waiter can proceed. If the wait exceeds the configured timeout, the statement fails with a lock wait timeout error (typically error `1205`).

A **deadlock** is a dependency cycle: transaction A waits on a resource held by B, while B waits on a resource held by A (or a longer cycle forms). InnoDB detects the deadlock and rolls back a chosen victim transaction to break the cycle; the application receives a deadlock error (typically `1213`) and should retry the entire transaction under a bounded retry policy.

View the latest deadlock:

```sql
SHOW ENGINE INNODB STATUS;
```

Look for the `LATEST DETECTED DEADLOCK` section in the output. If you need to log all deadlocks to the error log for investigation, administrators can consider `innodb_print_all_deadlocks`, after assessing log volume and operational procedures beforehand.

A lock wait timeout is not a deadlock. In InnoDB, by default when a lock wait timeout occurs, only the waiting statement is rolled back; the full transaction rolls back only if `innodb_rollback_on_timeout` is enabled or the application explicitly rolls back. Applications should handle errors consistently—typically rolling back the transaction and retrying the entire unit of work when safe.

## 10. Safe Procedure for Handling Blocking Sessions

When alerted about lock-waiting queries, proceed in order:

1. **Identify the wait type:** row lock, MDL, table lock, or deadlock. Use `sys.innodb_lock_waits`, `sys.schema_table_lock_waits`, and `SHOW ENGINE INNODB STATUS` as appropriate.
2. **Locate waiter and blocker:** record connection ID, transaction ID, table, index, lock mode, and wait duration.
3. **Find the root blocker:** if the blocker is itself waiting on another session, follow the chain to the root lock-holding transaction.
4. **Assess impact:** number of waiters, transaction age, modified row count, user/host, SQL statement, and business flow involved.
5. **Prefer application-level resolution:** if the connection owner can safely commit or roll back, have the application finish the transaction cleanly.
6. **Intervene administratively only after understanding impact:** verify connection ID and owner before using `KILL`; notify affected teams per runbook.
7. **Verify afterward:** confirm waiters progress or error cleanly, lock waits disappear, and no new blocking chain forms.

### `KILL QUERY` vs. `KILL CONNECTION`

```sql
KILL QUERY 12345;
KILL CONNECTION 12345;
```

- `KILL QUERY` stops the connection's current statement while keeping the connection open. If inside an open transaction, the transaction can remain open and continue holding locks.
- `KILL CONNECTION` terminates the connection. Any open transaction on that connection is rolled back; rollback may take time if the transaction modified substantial data. Locks are released once rollback completes.

Never execute `KILL` based on a stale connection ID from a dashboard. The ID may have disconnected and been reused by the server; re-verify user, host, duration, and transaction immediately before intervening. For MDL held by an idle transaction, `KILL QUERY` usually fails to resolve the block because no statement is actively running to stop.

## 11. Reducing Lock Contention and Blocking Risk

- Keep transactions short; avoid waiting on user input or calling external services while a transaction remains open.
- Access tables and rows in a consistent order across transactions to reduce deadlock risk.
- Create suitable indexes for `WHERE` predicates and joins to minimize the number of index records scanned and locked.
- Batch large data modifications into smaller chunks; commit at safe business boundaries.
- Handle deadlock and timeout errors with bounded retries, backoff, and idempotent operations where required.
- Do not leave DDL waiting indefinitely without monitoring. Check for long transactions before running `ALTER TABLE`, `DROP TABLE`, or `RENAME TABLE`.
- Set appropriate application and operational timeouts, without treating shorter timeouts as a fix for long-lock-holding transactions.
- Monitor transaction age, waiter counts, maximum wait times, and frequently contended tables/indexes.

## 12. Observability Tool Selection Guide

| Question | Recommended Tool | Purpose |
|---|---|---|
| Which InnoDB transactions have been open long? | `information_schema.innodb_trx` | Transaction age, state, connection ID, and locked rows |
| Which connections are waiting on row locks and who blocks them? | `sys.innodb_lock_waits` | Waiter/blocker pairs, table, index, and wait age |
| Need detailed lock modes and lock data? | `performance_schema.data_locks`, `data_lock_waits` | Analyze granted locks and wait relationships |
| Which DDL is waiting on a metadata lock? | `sys.schema_table_lock_waits` | Match waiting sessions to MDL-holding sessions |
| Need granted/pending MDL statuses? | `performance_schema.metadata_locks` | Inspect object, lock type, duration, and owner thread |
| Need to investigate the latest deadlock? | `SHOW ENGINE INNODB STATUS` | Read transactions, index records, and deadlock cycle |
| What is a connection currently doing? | `SHOW FULL PROCESSLIST`, `performance_schema.threads` | User, host, command, state, and current statement |

## 13. Self-Check

1. How do InnoDB row locks and metadata locks differ in what they protect?
2. Why can a `Sleep` connection still block another transaction or DDL?
3. Can an ordinary read transaction hold an MDL even without holding any row locks?
4. Through which columns does `sys.innodb_lock_waits` identify waiters and blockers?
5. When should you use `performance_schema.data_locks` and `data_lock_waits`?
6. Why does `metadata_locks` list locks without directly describing full compatibility rules among them?
7. How does `KILL QUERY` differ from `KILL CONNECTION` when the blocker is inside an open transaction?
8. How do deadlocks differ from lock wait timeouts, and how should applications handle them?
