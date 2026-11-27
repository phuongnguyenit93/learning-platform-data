# Observing data_locks, data_lock_waits, and blocking sessions

In MySQL, a statement may have to wait because another transaction holds a lock on the same record or data range. When an incident occurs, you must answer three questions: which transaction is waiting, which transaction holds the blocking lock, and which object the two transactions are contending over.

For MySQL 8.0 using InnoDB, the two essential Performance Schema tables for investigation are **performance_schema.data_locks** and **performance_schema.data_lock_waits**. Combining them with **performance_schema.threads** and **information_schema.innodb_trx**, we can trace from a lock-wait relationship to the connection ID, user, statement, and transaction age.

This lesson belongs to the **Locking and Concurrency** chapter of the **DATABASE_MYSQL** module. Within the scope of mastering MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control, lock observation skills help explain why an UPDATE or DELETE hangs, why a short transaction can still be blocked for a long time, and what to check before intervening on a running session.

## 1. Distinguishing existing locks from lock-wait relationships

**data_locks** shows the locks currently tracked by the storage engine at query time. A row can represent either an already-granted lock or a waiting lock request. This table answers: which schema, table, and index the lock belongs to; whether it is a table-level or record-level lock; what the lock mode is; and which transaction/thread requested the lock.

**data_lock_waits** describes relationships between a waiting lock and the lock preventing it from being granted. Each row links a requested lock to a blocking lock. One transaction can be blocked by multiple locks or multiple other transactions, so results may include multiple rows for the same waiting transaction.

Remember the roles of the two tables as follows:

| Table | Main question | Key data to note |
|---|---|---|
| **performance_schema.data_locks** | Which locks currently exist? | Object, index, lock type, lock mode, status, transaction, and thread |
| **performance_schema.data_lock_waits** | Who is waiting on whom? | Requesting lock ID, blocking lock ID, transaction IDs, and thread IDs on both sides |

Both tables reflect current state. If a transaction commits or rolls back before the query runs, the wait relationship may have already disappeared. Therefore, when investigating an active incident, run these queries as soon as wait symptoms are reported.

## 2. Prerequisites and observation privileges

The queries in this lesson use MySQL 8.0's Performance Schema interface. Check the version and Performance Schema status first:

~~~sql
SELECT
    VERSION() AS mysql_version,
    @@performance_schema AS performance_schema_enabled;
~~~

If operating an older MySQL version, check documentation for your exact version before using these tables; lock diagnostic table names and interfaces have changed across MySQL releases. In MySQL 8.0, prefer **data_locks** and **data_lock_waits** over the legacy InnoDB lock tables in **INFORMATION_SCHEMA**.

A monitoring account needs read privileges on the relevant Performance Schema tables. To observe sessions belonging to other users completely, the account typically also needs the **PROCESS** privilege per server security policy. If a query does not return a session you know exists, check privileges before concluding no locks exist.

Never grant broad administrative privileges merely for investigative convenience. In production environments, use an approved monitoring account, restrict read privileges as needed, and avoid logging sensitive values from **LOCK_DATA** or SQL statements into public logs.

## 3. Reading locks in data_locks

The query below lists locks for a schema. Replace **shop** with the schema you want to inspect:

~~~sql
SELECT
    ENGINE,
    ENGINE_TRANSACTION_ID,
    THREAD_ID,
    EVENT_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    PARTITION_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks
WHERE OBJECT_SCHEMA = 'shop'
ORDER BY
    ENGINE_TRANSACTION_ID,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE;
~~~

Columns you normally need to read:

- **ENGINE**: the storage engine owning the lock; in this lab, we care about InnoDB.
- **ENGINE_TRANSACTION_ID**: the transaction ID provided by the engine. Use it to correlate with transaction IDs in the lock-wait table.
- **THREAD_ID**: Performance Schema's internal thread ID. This is not the connection ID used by applications to connect.
- **OBJECT_SCHEMA**, **OBJECT_NAME**, **INDEX_NAME**: the schema, table, and index associated with the lock.
- **LOCK_TYPE**: locked object type, commonly **TABLE** or **RECORD**.
- **LOCK_MODE**: lock mode. For example, at the table level you may see **IS** (intention shared) and **IX** (intention exclusive); at the record level you may see **S**, **X**, and variants relating to gaps or records.
- **LOCK_STATUS**: **GRANTED** means the lock has been granted; **WAITING** means the lock request has not yet been granted.
- **LOCK_DATA**: data associated with the lock, if the engine can supply it. The value can be **NULL** in certain cases, such as when page info is not available in the buffer pool.

Do not parse the **ENGINE_LOCK_ID** string by splitting internal components. It is an internal engine identifier; use the value as-is to join with **data_lock_waits**.

When reading **LOCK_MODE**, do not just see the letter **X** and conclude a statement is updating improperly. Table-level intention locks normally appear alongside record locks during normal InnoDB operation. Examine **LOCK_TYPE**, **INDEX_NAME**, status, and wait relationships together to understand the situation accurately.

## 4. Finding waiting transactions and blocking transactions

The following query joins each row in **data_lock_waits** with two corresponding rows in **data_locks**: one for the requested lock and one for the blocking lock. It also joins threads with **performance_schema.threads** to obtain server-level connection info.

~~~sql
SELECT
    w.ENGINE,
    w.REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx_id,
    wt.PROCESSLIST_ID AS waiting_connection_id,
    wt.PROCESSLIST_USER AS waiting_user,
    wt.PROCESSLIST_HOST AS waiting_host,
    wt.PROCESSLIST_COMMAND AS waiting_command,
    wt.PROCESSLIST_TIME AS waiting_command_seconds,
    wt.PROCESSLIST_STATE AS waiting_state,
    wt.PROCESSLIST_INFO AS waiting_sql,
    req.OBJECT_SCHEMA AS locked_schema,
    req.OBJECT_NAME AS locked_table,
    req.INDEX_NAME AS locked_index,
    req.LOCK_TYPE AS requested_lock_type,
    req.LOCK_MODE AS requested_lock_mode,
    req.LOCK_STATUS AS requested_lock_status,
    w.BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx_id,
    bt.PROCESSLIST_ID AS blocking_connection_id,
    bt.PROCESSLIST_USER AS blocking_user,
    bt.PROCESSLIST_HOST AS blocking_host,
    bt.PROCESSLIST_COMMAND AS blocking_command,
    bt.PROCESSLIST_TIME AS blocking_command_seconds,
    bt.PROCESSLIST_STATE AS blocking_state,
    bt.PROCESSLIST_INFO AS blocking_sql,
    blk.LOCK_MODE AS blocking_lock_mode,
    blk.LOCK_STATUS AS blocking_lock_status
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS req
    ON req.ENGINE = w.ENGINE
   AND req.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blk
    ON blk.ENGINE = w.ENGINE
   AND blk.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID
LEFT JOIN performance_schema.threads AS wt
    ON wt.THREAD_ID = w.REQUESTING_THREAD_ID
LEFT JOIN performance_schema.threads AS bt
    ON bt.THREAD_ID = w.BLOCKING_THREAD_ID
ORDER BY
    waiting_connection_id,
    blocking_connection_id;
~~~

How to read the output:

1. **waiting_connection_id** is the connection ID of the waiting session. This is the ID usable with session management commands after verifying the right target.
2. **blocking_connection_id** is the connection ID of the session holding the blocking lock.
3. **locked_schema**, **locked_table**, and **locked_index** show the contended object.
4. **requested_lock_mode** is the lock mode the waiting session needs; **blocking_lock_mode** is the mode of the lock blocking that request.
5. **waiting_sql** and **blocking_sql** are the current statements recorded by Performance Schema for the two threads, if any.

The join condition includes both **ENGINE** and **ENGINE_LOCK_ID**. Never join the two sides using only table name or transaction ID: one table can have many locks, and one transaction can hold many locks simultaneously.

**PROCESSLIST_ID** is the server-level connection ID; **THREAD_ID** is Performance Schema's internal thread ID. Never swap the two ID types when cross-referencing or running KILL commands.

## 5. Checking transaction age and session state

Information in **threads** shows which statement a session is currently running. However, the current SQL statement is not necessarily the statement that acquired the lock. A transaction can run an UPDATE, then transition to the **Sleep** state while still holding locks because it has not run COMMIT or ROLLBACK.

Use **information_schema.innodb_trx** to view transaction age, wait start time, and locked row count:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
    trx_wait_started,
    TIMESTAMPDIFF(SECOND, trx_wait_started, NOW()) AS lock_wait_seconds,
    trx_mysql_thread_id AS connection_id,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Points to distinguish:

- **trx_started** helps assess how long the transaction has been open. A long-open transaction can hold locks for a long time even when the session is not continuously running SQL.
- **trx_wait_started** shows when the transaction began waiting for a lock if it is currently waiting.
- **trx_rows_locked** and **trx_rows_modified** help gauge impact scope; these are point-in-time figures, not an exact guarantee of how many rows the application intends to modify.
- **trx_query** can be **NULL** if the session is idle between statements inside an open transaction.

You can filter the query by the connection IDs you just found:

~~~sql
SELECT
    t.PROCESSLIST_ID AS connection_id,
    t.PROCESSLIST_USER AS user_name,
    t.PROCESSLIST_HOST AS client_host,
    t.PROCESSLIST_DB AS current_schema,
    t.PROCESSLIST_COMMAND AS command_name,
    t.PROCESSLIST_TIME AS command_seconds,
    t.PROCESSLIST_STATE AS process_state,
    t.PROCESSLIST_INFO AS current_sql,
    it.trx_id,
    it.trx_state,
    it.trx_started,
    it.trx_rows_locked,
    it.trx_rows_modified,
    it.trx_query
FROM performance_schema.threads AS t
LEFT JOIN information_schema.innodb_trx AS it
    ON it.trx_mysql_thread_id = t.PROCESSLIST_ID
WHERE t.PROCESSLIST_ID IN (101, 102)
ORDER BY it.trx_started;
~~~

Replace **101** and **102** with connection IDs obtained from the wait-relationship query. This query also lets you see sessions without an active InnoDB transaction, in which case columns from **innodb_trx** will be **NULL**.

Never use **PROCESSLIST_TIME** alone to judge transaction age. This column describes how long the current process list state/command has lasted; **trx_started** is the timestamp to examine when evaluating how long a transaction has been open.

## 6. Hands-on practice: reproducing a blocking session

You can observe this directly using two separate MySQL connections. Practice in a test schema, never on business tables with live production data.

Create the test table and two rows:

~~~sql
CREATE TABLE IF NOT EXISTS lock_lab_accounts (
    id BIGINT NOT NULL PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL
) ENGINE = InnoDB;

INSERT IGNORE INTO lock_lab_accounts (id, balance)
VALUES (1, 1000.00), (2, 1000.00);
~~~

**Connection A — acquire the lock and keep the transaction open**

~~~sql
START TRANSACTION;

UPDATE lock_lab_accounts
SET balance = balance - 100.00
WHERE id = 1;

-- Keep the transaction open to observe; do not COMMIT or ROLLBACK yet.
~~~

The UPDATE acquires an exclusive lock on the record with **id = 1**. Because the transaction has not ended, the lock remains held.

**Connection B — request a lock on the same record**

~~~sql
START TRANSACTION;

UPDATE lock_lab_accounts
SET balance = balance + 50.00
WHERE id = 1;

-- This UPDATE will wait on the lock held by connection A.
~~~

**Connection C — observe**

Run the query from section 4. The output will show connection B as the requester and connection A as the blocker. The locked object is the record in **lock_lab_accounts** via its primary index. Run the query from section 5 to inspect transaction age and the state of both sessions.

If connection A is in the **Sleep** state and **blocking_sql** is **NULL**, that does not mean A released the lock. A may still hold an open transaction from its earlier UPDATE. Cross-reference **blocking_connection_id**, **innodb_trx**, and the wait graph rather than relying on the current SQL statement.

**Completing the lab**

On connection A, end the transaction:

~~~sql
COMMIT;
~~~

As soon as A commits, the lock is released and the waiting UPDATE on B proceeds. After B finishes, end transaction B:

~~~sql
COMMIT;
~~~

If you want to discard changes in the lab, use ROLLBACK on the respective connection instead of COMMIT. Never leave test transactions open when finished.

## 7. Investigation workflow for blocking in production

When an application reports slow queries or timeouts, follow this sequence to avoid targeting the wrong session:

1. **Capture current wait state.** Run the `data_lock_waits` query with both `data_locks` joins. Record the waiting transaction, blocking transaction, both connection IDs, and the contended object.
2. **Identify sessions and transactions.** Match connection IDs against `performance_schema.threads` and `information_schema.innodb_trx`. Check user, host, schema, current SQL, transaction start time, and locked row counts.
3. **Find the application-side cause.** Check whether the transaction is waiting on external work, calling another service, waiting for a user, or forgot to commit/roll back. A long-open transaction can hold locks even with no running SQL.
4. **Assess impact scope.** See how many sessions are waiting, which tables/indexes are contended, and how long the blocking transaction has existed. Check application logs to identify the corresponding business operation.
5. **Release via the transaction owner when possible.** If the application still controls the session, let it complete its work and commit or roll back per business logic. Then re-run the observation query to confirm the wait edge is gone.
6. **Intervene on a session only after verification.** If a session must be stopped, confirm the connection ID, owner, statement, and rollback impact with the responsible operations owner before acting.

You can use KILL QUERY or KILL CONNECTION when operational procedures permit:

~~~sql
-- Stop the currently running statement on connection 123.
KILL QUERY 123;

-- Close connection 123.
KILL CONNECTION 123;
~~~

The number **123** must be the verified **PROCESSLIST_ID**, not **THREAD_ID** or transaction ID. KILL QUERY stops the running statement while keeping the connection alive; if the transaction remains open, locks acquired by earlier statements may remain held. KILL CONNECTION closes the connection and forces any uncommitted InnoDB transaction to roll back. Rollback can take time; locks are released only once the appropriate rollback completes. Therefore, killing a session is not a harmless action and should never be done merely because a connection is in the Sleep state.

## 8. Common misinterpretations of output

**No rows in data_lock_waits.** This only indicates no lock-wait relationship was recorded at query time. The incident may have ended, the transaction may have just committed, or the query ran after a timeout. It does not prove the system never experienced contention.

**Blocking session has no current SQL.** A connection in the Sleep state can still hold locks if its transaction has not ended. Use transaction metadata and the wait graph to verify.

**Multiple rows for the same waiting session.** One transaction can be waiting on multiple blocking locks. Never assume there is only one blocker; read every lock pair in `data_lock_waits`.

**Seeing a table-level lock and assuming the entire table is exclusively locked.** Intention locks such as IX routinely coordinate with record locks. Read lock type, lock mode, index, and wait relationships together.

**No contention found in data_locks yet DDL is still waiting.** InnoDB data locks and metadata locks are two distinct mechanisms. When suspecting ALTER TABLE, DROP TABLE, or DDL is waiting, also check `performance_schema.metadata_locks` and related threads. `data_locks` is not a catch-all table for every wait type in MySQL.

**Relying on LOCK_DATA to identify every record.** `LOCK_DATA` may be absent or not represent all needed details. Use schema, table, index, lock mode, and transaction for analysis; avoid copying sensitive data values into unprotected reports.

## 9. Checklist for reading a lock incident

When receiving a blocking report, ensure you can answer the following questions:

- Which transaction is waiting, and what is its connection ID?
- Which transaction holds the blocking lock, and what is its connection ID?
- Which schema, table, index, and lock type are contended?
- What modes and statuses do the requested lock and blocking lock have?
- When did the blocking transaction start; is that session running SQL or in Sleep?
- How many transactions are waiting on the same blocker?
- Is it a metadata lock or another wait type instead of a data lock?
- Who owns the session, and which action (commit, roll back, or terminating the session) is authorized by procedure?

Once you can answer these questions, you can explain wait behavior using evidence from MySQL rather than guessing from a slow SQL statement. Lock investigation also feeds into subsequent tuning steps: reviewing update order across transactions, shortening transaction durations, checking indexes and filter predicates, and ensuring applications always end transactions across every execution path.
