# LOCK Clause, Metadata Locks, and DDL Wait Times

In the `DATABASE_MYSQL` module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, privilege management, backups, and handling relational database operational issues. This lesson focuses on changing schemas safely while the system still receives traffic: choosing the appropriate lock level for DDL, understanding metadata locks (MDL), finding blocking sessions, and controlling wait times.

An `ALTER TABLE` statement can be designed to allow the application to continue reading and writing during most of its execution time. However, that does not mean DDL requires no locks. MySQL still needs metadata locks to protect the table definition and typically requires stronger lock rights during certain phases, especially at the start or completion of the change. A long-lived open transaction can hold an MDL and force DDL to wait; a waiting DDL can also cause subsequent queries to queue behind it. Therefore, schema deployments must check the DDL algorithm, lock level, wait timeout, and currently running transactions.

## 1. Two lock concepts to distinguish

When investigating a waiting DDL statement, distinguish metadata locks from InnoDB data locks.

| Lock type | What does it protect? | Example wait scenario | Primary inspection tools |
|---|---|---|---|
| Metadata lock (MDL) | Metadata of databases, tables, views, routines, and related schema objects. | `ALTER TABLE` waits for another transaction to finish because that transaction is using the table. | `performance_schema.metadata_locks`, `sys.schema_table_lock_waits`, process list. |
| InnoDB record/gap/next-key lock | Records and index key ranges to coordinate concurrent transactions. | `UPDATE` or `SELECT ... FOR UPDATE` waits for another transaction to release row locks. | `performance_schema.data_locks`, `performance_schema.data_lock_waits`, `SHOW ENGINE INNODB STATUS`. |

MDL is not a row lock. Increasing `innodb_lock_wait_timeout` does not solve DDL waiting on a metadata lock. Conversely, `lock_wait_timeout` controls metadata lock wait duration, not InnoDB row lock wait timeouts.

## 2. The LOCK clause in ALTER TABLE

For many `ALTER TABLE` operations, MySQL lets you specify the concurrency level using `LOCK`. This option requests a specific locking level during DDL execution. Support depends on storage engine, exact operation, MySQL version, and table structure.

| Value | Meaning for concurrent access | How to interpret when planning |
|---|---|---|
| `LOCK=DEFAULT` | Lets MySQL pick the default lock level for the selected operation and algorithm. | Flexible, but check documentation and behavior for your running version. |
| `LOCK=NONE` | Permits concurrent reads and writes during operation phases supporting this lock level. | Typically suited for online changes, yet may still need brief MDLs at start/end. |
| `LOCK=SHARED` | Permits concurrent reads; blocks concurrent writes while the lock applies. | Useful when pausing writes is acceptable while reads must continue. |
| `LOCK=EXCLUSIVE` | Blocks both concurrent reads and writes on the altered object. | Disruptive; requires a maintenance window and runtime evaluation. |

Example adding a secondary index to an InnoDB table:

```sql
ALTER TABLE orders
    ADD INDEX idx_orders_created_at (created_at),
    ALGORITHM=INPLACE,
    LOCK=NONE;
```

This statement requires MySQL to use the `INPLACE` algorithm and `NONE` lock level. If the operation, engine, or table structure does not support that combination, MySQL returns an error rather than silently escalating to a more disruptive lock level. This is useful for failing fast when online execution is mandatory.

Never deduce that `LOCK=NONE` means zero locking across the entire DDL lifecycle. MySQL still needs MDL to read and modify metadata. During metadata transition phases, DDL may wait for or acquire a strong MDL briefly. If an older transaction holds a compatible MDL, the statement still must wait for that transaction to finish.

### ALGORITHM and LOCK answer two different questions

`ALGORITHM` decides how MySQL performs the structural change; `LOCK` governs the concurrent access level the operation is allowed to use.

| ALGORITHM | Characteristics | What to keep in mind |
|---|---|---|
| `INSTANT` | Modifies metadata without rebuilding all table data for supported operations. | Applies only to specific operations and version/engine conditions. Can fail if the table hit its row version limit or fails eligibility. |
| `INPLACE` | Executes changes via internal engine mechanisms, avoiding the general table-copy method. | Does not always mean no rebuild; some `INPLACE` operations still rebuild data and use heavy I/O. |
| `COPY` | Builds a new table structure and copies data across. | Can take significant time, disk space, and restrict writes during copying. |
| `DEFAULT` | Lets MySQL choose the appropriate algorithm. | Outcome may vary by version, engine, and change type. |

Example adding a nullable column at the end of a table using `INSTANT` on a supported version/engine:

```sql
ALTER TABLE orders
    ADD COLUMN source_tag VARCHAR(30) NULL,
    ALGORITHM=INSTANT;
```

This example is valid only when adding the column meets the `INSTANT` requirements of the MySQL version in use. Not all data type changes, column positions, keys, default expressions, or partition changes can run with `INSTANT`. Check version-specific documentation and test on a clone matching production structure.

If the application requires zero write blocking, specify `LOCK=NONE` on supported operations and verify on staging. Do not automatically remove `LOCK=NONE` upon error, as doing so can cause the same command to run with a stricter lock than intended.

## 3. How long are metadata locks held?

MySQL uses MDL to prevent schema object definitions from changing while a statement or transaction still depends on that metadata. On InnoDB tables, statements accessing a table acquire corresponding metadata locks. Inside an explicit transaction, MDL can be held until the transaction ends, even after a `SELECT` statement has finished executing.

Example:

```sql
START TRANSACTION;

SELECT order_id, status
FROM orders
WHERE order_id = 1001;

-- Application leaves the transaction open without COMMIT or ROLLBACK.
```

While this session keeps the transaction open, the MDL on `orders` remains held. Another session running `ALTER TABLE orders ...` needs an MDL compatible with the DDL operation; if it cannot acquire the lock, the DDL waits.

This commonly happens in scenarios such as:

- Application starts a transaction but encounters an error before `COMMIT` or `ROLLBACK`.
- Connection pool returns a connection to the pool while a transaction is still open.
- A transaction reads multiple tables and waits on an external call, holding MDL longer than expected.
- A long-running query accesses the table that DDL needs to alter.
- A session uses `LOCK TABLES` or administrative operations holding object locks.

With autocommit enabled and standalone statements, MDL is generally released when the statement finishes. However, when a statement runs inside an explicit transaction, the transaction must finish to release locks. A session in `Sleep` state can still hold an open transaction and MDL; never filter the process list solely by actively running queries.

## 4. Waiting DDL can create a query queue

Suppose transaction A accessed `orders` and has not finished yet. DDL B requests a strong MDL to alter the table and therefore waits. While B is waiting, a new query C may queue behind B depending on lock types and MDL priority policy. A DDL command that appears to be waiting on just one transaction can thus spike latency or cause many new queries to stall behind it.

```mermaid
sequenceDiagram
    participant A as Transaction A
    participant B as ALTER TABLE B
    participant C as Query C
    A->>A: SELECT orders; keep transaction open
    B->>B: Request strong metadata lock
    Note over B: Wait for A to release MDL
    C->>C: Request MDL to access orders
    Note over B,C: C may have to queue behind the waiting DDL request
    A->>A: COMMIT or ROLLBACK
    A-->>B: Release MDL
    B->>B: Execute DDL and complete metadata transition
    B-->>C: Release MDL
    C->>C: Resume query
```

This is why you should never let DDL wait indefinitely during peak hours. When DDL is found blocked, identify the blocker, estimate how many sessions are queued, and decide whether to keep waiting or cancel the DDL. If DDL has been waiting a long time, watching only the DDL session while ignoring queued queries behind it can severely underestimate application impact.

## 5. Finding sessions holding or waiting on metadata locks

### Inspecting the process list

```sql
SHOW FULL PROCESSLIST;
```

Look for sessions with states like `Waiting for table metadata lock`. Note the connection ID, user, host, runtime, statement, and database. A `Sleep` session can still be the blocker if its transaction has not ended.

### Using sys.schema_table_lock_waits

If the `sys` schema is available and the account has read privileges, `sys.schema_table_lock_waits` shows the relationship between waiting and blocking sessions:

```sql
SELECT
    object_schema,
    object_name,
    waiting_pid,
    waiting_query,
    waiting_query_secs,
    blocking_pid,
    blocking_query,
    blocking_lock_duration
FROM sys.schema_table_lock_waits
ORDER BY waiting_query_secs DESC;
```

`waiting_pid` is the waiting connection; `blocking_pid` is the connection holding the lock preventing the request from being granted. `blocking_query` may be empty if the blocking session is idle inside a transaction. In that case, also inspect active transactions and the process list.

### Inspecting Performance Schema directly

You can read granted or pending locks from `performance_schema.metadata_locks`:

```sql
SELECT
    ml.OBJECT_TYPE,
    ml.OBJECT_SCHEMA,
    ml.OBJECT_NAME,
    ml.LOCK_TYPE,
    ml.LOCK_DURATION,
    ml.LOCK_STATUS,
    th.PROCESSLIST_ID,
    th.PROCESSLIST_USER,
    th.PROCESSLIST_HOST,
    th.PROCESSLIST_TIME,
    th.PROCESSLIST_STATE,
    th.PROCESSLIST_INFO
FROM performance_schema.metadata_locks AS ml
LEFT JOIN performance_schema.threads AS th
    ON th.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.OBJECT_SCHEMA = 'shop'
  AND ml.OBJECT_NAME = 'orders'
ORDER BY ml.LOCK_STATUS, th.PROCESSLIST_TIME DESC;
```

`LOCK_STATUS` typically shows `GRANTED` or `PENDING`. `PENDING` rows indicate waiting requests; `GRANTED` rows on the same object provide leads for identifying sessions holding locks. Combine with `sys.schema_table_lock_waits` or analyze lock types to pinpoint the exact blocker. Performance Schema must be enabled and the account needs privileges to read the relevant tables.

### Finding long-running open InnoDB transactions

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS age_seconds,
    trx_mysql_thread_id AS connection_id,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Results show InnoDB transactions and their corresponding connection IDs. `trx_query` may be `NULL` when a session is idle while its transaction remains open. Cross-reference `connection_id` with the process list and MDL wait views to identify the session needing attention.

## 6. Controlling DDL wait times

`lock_wait_timeout` configures the maximum wait duration for metadata locks in seconds. MySQL's default is very large (31,536,000 seconds, or one year), so DDL can wait indefinitely if an appropriate timeout is not set.

Before executing DDL, set a short session timeout:

```sql
SET SESSION lock_wait_timeout = 15;

ALTER TABLE orders
    ADD INDEX idx_orders_customer_id (customer_id),
    ALGORITHM=INPLACE,
    LOCK=NONE;
```

If it cannot acquire the metadata lock within 15 seconds, the statement fails with a timeout and can be retried after resolving the blocker. This caps how long a migration sits in the lock queue. Choose the value based on your deployment window and application tolerance.

Clearly distinguish the two variables:

| Variable | Controls | When to check? |
|---|---|---|
| `lock_wait_timeout` | Metadata lock wait time. | `ALTER TABLE`, `CREATE TABLE`, `RENAME TABLE`, operations needing MDL. |
| `innodb_lock_wait_timeout` | InnoDB record/table lock wait time inside transactions. | `UPDATE`, `DELETE`, `SELECT ... FOR UPDATE` blocked by another transaction. |

Lowering `lock_wait_timeout` does not make DDL run faster; it simply causes DDL to give up waiting after the deadline. If the cause is a long-open transaction, resolve the transaction or reschedule the DDL. Also remember that DDL can wait on MDL at either the start or completion of the operation even after most online work has finished.

## 7. Safely handling blockers

Once you identify the session holding an MDL, do not kill it immediately without understanding the transaction and business impact.

1. **Identify the owner.** Correlate connection ID with user, host, application, and service. Check when the transaction started, which tables it touched, and whether a statement is actively running.
2. **Assess normal completion.** If the application can finish shortly, let the session run `COMMIT` or `ROLLBACK` per business flow.
3. **If intervention is required, choose the right scope.** `KILL QUERY <id>` cancels only the current statement; if the session still holds an open transaction, MDL may remain held. `KILL CONNECTION <id>` closes the session and forces MySQL to roll back the open transaction; rollback can take significant time for large transactions.
4. **Verify after action.** Confirm the blocker released the lock, whether DDL resumed or timed out, and whether waiting queries drained.
5. **Address root cause.** Fix transaction scopes, connection pools, application timeouts, or migration workflows so the issue does not recur.

Never kill a session based solely on `Sleep` duration. A session may hold a legitimate transaction the application expects to complete. Also do not assume `KILL QUERY` releases all MDLs; if the transaction stays open, the session can still hold locks until commit, rollback, or connection closure.

## 8. Safe DDL deployment workflow

Before running migrations in production:

1. **Verify the change.** Identify the exact table, index, column, constraints, and application dependencies. Verify MySQL version and storage engine.
2. **Choose ALGORITHM and LOCK.** Prefer `INSTANT` when genuinely supported; consider `INPLACE, LOCK=NONE` for eligible online operations. Never assume algorithm names reflect total I/O or rebuild time.
3. **Test on staging.** Use a data copy matching production size and workload. Measure duration, I/O, temporary space, write impact, and final MDL acquisition time.
4. **Check long transactions.** Inspect process list, `innodb_trx`, and MDL waits before starting. Handle anomalous transactions with their owners.
5. **Set timeout.** Set `lock_wait_timeout` according to the deployment's wait budget. If it times out, stop and investigate; do not blindly retry repeatedly and worsen lock queues.
6. **Monitor during execution.** Watch DDL state, wait time, resources, waiting connections, and application errors.
7. **Verify post-DDL.** Inspect structure with `SHOW CREATE TABLE`, indexes with `SHOW INDEX`, check queries and error logs, and confirm the application behaves normally.

For major changes, consider the expand-contract strategy: add new structures first, deploy code compatible with both old and new structures, backfill in batches, switch reads/writes, and drop legacy structures in a separate deployment. This breaks changes into small steps, improving risk control and rollback ease.

### Online DDL still has resource limits

Even when `LOCK=NONE` is supported, DDL generates I/O load, consumes temporary space, increases redo/undo activity, or creates an online alter log to record concurrent modifications. In InnoDB, `innodb_online_alter_log_max_size` caps the size of the online alter log. If concurrent writes during DDL exceed that limit, the operation fails. Therefore, monitor write rate, disk space, rebuild duration, and storage capacity.

## 9. Common incidents and how to handle them

| Symptom | Common cause | Resolution |
|---|---|---|
| `ALTER TABLE` stuck in `Waiting for table metadata lock` | Another transaction or statement holds an incompatible MDL. | Find blocker via `sys.schema_table_lock_waits`, `metadata_locks`, and process list; resolve transaction. |
| DDL runs long while waiting query count spikes | DDL is waiting on MDL and new requests queue behind it. | Enforce timeout, evaluate queue impact, cancel DDL if needed, and reschedule for an appropriate window. |
| `LOCK=NONE` rejected | Operation, engine, or version does not support that lock level. | Check online DDL capability; pick an alternative migration method or an approved maintenance window. |
| `ALGORITHM=INSTANT` fails | Change unsupported or table fails version/eligibility conditions. | Check version docs; test `INPLACE`/`COPY` in staging and evaluate rebuild impact. |
| DDL still waits after `KILL QUERY` | Blocker session still has an open transaction holding MDL. | Verify transaction; request `COMMIT`/`ROLLBACK` or terminate connection per runbook. |
| DDL fails because online alter log exceeded limit | Concurrent write volume during DDL too high or operation ran too long. | Reduce write pressure, split migration, evaluate capacity before tuning limit, and retry. |
| Increasing `innodb_lock_wait_timeout` still leaves DDL waiting | Waiting on metadata lock, not InnoDB row lock. | Check and tune `lock_wait_timeout`, resolve MDL blocker. |

## 10. Practice exercise

In a test MySQL environment, create an orders table and two separate connection sessions. The goal is to observe MDL and how DDL waits.

**Prepare the table:**

```sql
CREATE DATABASE IF NOT EXISTS shop;
USE shop;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE=InnoDB;
```

**Session A — keep a transaction open:**

```sql
USE shop;
START TRANSACTION;
SELECT * FROM orders WHERE order_id = 1;
-- Pause here without COMMIT or ROLLBACK.
```

**Session B — request DDL with a short timeout:**

```sql
SET SESSION lock_wait_timeout = 15;

ALTER TABLE shop.orders
    ADD INDEX idx_orders_created_at (created_at),
    ALGORITHM=INPLACE,
    LOCK=NONE;
```

While Session B is waiting, open Session C and inspect:

```sql
SELECT * FROM sys.schema_table_lock_waits;
SHOW FULL PROCESSLIST;
```

Record the waiting connection ID, blocking connection ID, wait duration, and session state. Next, in Session A run `COMMIT` or `ROLLBACK`, and observe whether the DDL proceeds or already timed out. Repeat the exercise with a short transaction and compare how long the DDL had to wait.

Finally, try changing lock levels on an operation supported by your MySQL version and observe the difference. Never run exercises that hold long transactions, interrupt sessions, or kill connections in production.

After this exercise, learners should be able to explain why `LOCK=NONE` can still wait on MDL, why a `Sleep` session can block DDL, how `lock_wait_timeout` differs from `innodb_lock_wait_timeout`, and how to pinpoint the exact blocker before deciding whether to abort a migration or terminate a connection. This is the foundation for evolving MySQL schemas while controlling downtime and application impact.
