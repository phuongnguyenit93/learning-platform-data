# Metadata locks, uncommitted transactions, and hanging DDL

A DBA runs `ALTER TABLE orders` to add a new column, yet the statement hangs waiting on a metadata lock. Inspecting the process list shows no large UPDATE running. The culprit may be a transaction that ran a SELECT on `orders`, finished the SELECT long ago, and never executed COMMIT or ROLLBACK. That connection may show up in the `Sleep` state while still holding a metadata lock (MDL) on the table.

Metadata locks protect the metadata of database objects—such as table names, column definitions, and table structures—while statements use those objects. MySQL uses MDL to prevent DDL from altering table structure while another transaction is still using the table. Therefore, an uncommitted transaction can block DDL even when no SQL statement is actively running on that connection.

This lesson explains the MDL lifecycle, its relationship with long transactions, how to identify blockers and waiters, cascading queue effects when DDL waits, and safe handling procedures in production.

## 1. What is a metadata lock?

A metadata lock (MDL) is a lock at the metadata layer of MySQL Server. It protects objects such as databases, tables, schema objects, and certain other objects from incompatible structural changes while in use.

Examples:

- `SELECT` needs a metadata lock so the table definition cannot change while the statement uses the table.
- `INSERT`, `UPDATE`, and `DELETE` need appropriate metadata locks when accessing a table.
- `ALTER TABLE`, `DROP TABLE`, and `RENAME TABLE` require stronger metadata lock privileges to modify table structure or names.
- A transaction can hold metadata locks on accessed tables until the transaction finishes.

MDL differs from InnoDB row locks:

| Mechanism | What does it protect? | Example scenario |
|---|---|---|
| Metadata lock (MDL) | Object metadata/definition | ALTER TABLE waits for a transaction using the table |
| Record lock (S/X) | Record/index record | Concurrent UPDATE on the same row must wait |
| Gap/next-key lock | Index intervals and associated records | Prevents phantom inserts during locking range scans |
| Table intention lock (IS/IX) | Signals intent to lock records inside a table | Coordinates row locks with table-level locks |
| Internal latch/mutex | Server/engine internal memory structures | Short-duration synchronization of internal operations |

A single statement can involve multiple mechanisms simultaneously. For example, an UPDATE can acquire an MDL on the table and an X lock on a record. If ALTER TABLE is waiting on an MDL, increasing `innodb_lock_wait_timeout` does not address the root cause because these are two completely different lock types.

## 2. Why can a regular SELECT also block DDL?

A regular SELECT in InnoDB is usually a consistent nonlocking read: it acquires no S record locks on individual rows. However, the SELECT still needs a metadata lock to ensure the table definition remains stable during use.

When running in autocommit mode, the statement's transaction usually ends as soon as the SELECT finishes, releasing transaction-scoped MDL. But if the SELECT runs inside an explicit transaction, the MDL on the accessed table can be held until COMMIT or ROLLBACK.

Session A example:

    START TRANSACTION;

    SELECT id, status
    FROM orders
    WHERE id = 1001;

    -- The SELECT statement has finished.
    -- Transaction is still open, not yet COMMIT/ROLLBACK.

Session B:

    ALTER TABLE orders
    ADD COLUMN source VARCHAR(30);

Session B may have to wait for MDL because Session A still holds a metadata lock on `orders`. No row lock needs to be blocking DDL; simply leaving transaction A open is enough to retain the MDL.

This is a common cause of the "DDL is hanging yet no long-running query is visible" situation.

## 3. Uncommitted transactions and the Sleep state

A connection may not be executing any SQL statement while still having an open transaction. In `SHOW PROCESSLIST`, that connection can display `Command = Sleep`.

Application example:

1. Borrow a connection from the pool.
2. Send `START TRANSACTION`.
3. Read from the `orders` table.
4. Process data in the application tier.
5. Hit a logic bug or forget to call COMMIT/ROLLBACK.
6. Return the connection to the pool or leave it idle.

If the connection has not actually closed the transaction, the MDL can persist. Seeing `PROCESSLIST_INFO` as NULL or `Command` as Sleep does not prove the connection has released its locks.

### 3.1. Signs of an idle transaction

- `SHOW FULL PROCESSLIST` shows a connection in the Sleep state for a long time.
- `information_schema.innodb_trx` shows a transaction with an old `trx_started` timestamp.
- `trx_query` may be NULL because no statement is currently executing.
- `trx_mysql_thread_id` maps to the connection ID in the process list.
- `performance_schema.metadata_locks` shows a GRANTED lock owned by that thread.

Not every Sleep connection holds a transaction. Cross-reference `innodb_trx` and metadata locks rather than looking solely at Sleep duration.

## 4. Common metadata lock modes

MDL has multiple lock modes representing levels of object access. Common modes encountered when investigating tables include:

| Mode | General meaning |
|---|---|
| `SHARED_READ` | Shared metadata read access when reading a table, common with SELECT |
| `SHARED_WRITE` | Access to use a table for write operations such as DML |
| `SHARED_UPGRADABLE` | Initial lock for some DDL operations that need to upgrade at a later stage |
| `SHARED_NO_WRITE` | Shared mode restricting concurrent writes during certain operations |
| `SHARED_NO_READ_WRITE` | Shared mode restricting both concurrent reads and writes during certain operations |
| `EXCLUSIVE` | Exclusive metadata access, typically required for structural changes |

Mode names are diagnostic information; do not deduce full compatibility solely from names. Compatibility depends on object type, lock mode, and statement phase. In practice, what you need to find is:

- Which locks are `GRANTED` and which transaction/session holds them?
- Which locks are `PENDING` and waiting?
- Which shared object are both locks targeting?
- Which statements and transactions created the wait relationship?

`performance_schema.metadata_locks` provides lock status; `sys.schema_table_lock_waits` presents waiter/blocker relationships in a more readable form.

## 5. Why does DDL need a strong metadata lock?

DDL such as `ALTER TABLE`, `DROP TABLE`, or `RENAME TABLE` modifies metadata currently used by other statements. MySQL must ensure no other transaction continues using the old definition in a way that causes errors or inconsistency.

Example:

    ALTER TABLE orders
    ADD COLUMN source VARCHAR(30);

Before modifying the table definition, the server must acquire a metadata lock compatible with existing locks. If a transaction holds an incompatible MDL, the DDL must wait.

Statements that commonly require a strong MDL:

- `ALTER TABLE`
- `DROP TABLE`
- `RENAME TABLE`
- `TRUNCATE TABLE`
- Certain index creation/deletion or constraint modification operations

Exact lock strength and acquisition timing depend on the DDL type, object, and execution algorithm.

## 6. Online DDL does not mean no MDL is needed

InnoDB supports multiple DDL algorithms:

- `ALGORITHM=INSTANT`: instantaneous metadata change for supported operations.
- `ALGORITHM=INPLACE`: performs changes in place as supported by the operation; may still rebuild or scan data depending on the case.
- `ALGORITHM=COPY`: builds a structural/data copy and swaps it.

Some operations also support `LOCK=NONE`, permitting concurrent DML during the main phase of the DDL. However:

- Not every change supports INSTANT, INPLACE, or LOCK=NONE.
- Online DDL still needs metadata locks at specific stages, especially when starting or finalizing the metadata swap.
- DDL can wait for old transactions to finish before acquiring the required MDL.
- Once started, a DDL operation can still take time to build indexes or process data.

Example requesting an explicit algorithm:

    ALTER TABLE orders
    ADD COLUMN source VARCHAR(30),
    ALGORITHM=INSTANT;

If the operation does not support INSTANT on the current version/schema, the statement can error instead of silently falling back to another algorithm. Specifying the algorithm helps avoid unexpected high-cost fallbacks.

Example with an operation supporting online DML:

    ALTER TABLE orders
    ADD INDEX idx_orders_created_at (created_at),
    ALGORITHM=INPLACE,
    LOCK=NONE;

Use this syntax only when the specific operation and MySQL version support it. `LOCK=NONE` does not eliminate MDL; it describes the level of concurrent DML allowed during supported phases.

## 7. A waiting DDL can create a query queue

A dangerous operational scenario:

1. Transaction A holds an MDL on `orders` because it has not ended.
2. DDL B requests an `EXCLUSIVE` MDL on `orders` and enters PENDING.
3. New statements from C, D, and E continue accessing `orders`.
4. Subsequent requests may queue behind the waiting DDL request, depending on lock order and priority.
5. Connections and threads pile up, raising latency or making the whole application appear frozen.

Therefore, even an ALTER TABLE that has not started executing yet can disrupt traffic. Never look at a waiting DDL and assume the impact is isolated to a single session.

When detecting a long-waiting DDL, locate the blocker early. If the DDL cannot run in the current window, consider canceling the waiting DDL statement to stop the queue from growing, then reschedule once the blocking transaction is resolved.

## 8. Observing metadata locks with Performance Schema

MySQL provides the `performance_schema.metadata_locks` table to observe held or requested MDLs.

### 8.1. Viewing metadata locks for a table

Example inspecting the `orders` table in the current database:

    SELECT
        ml.OBJECT_TYPE,
        ml.OBJECT_SCHEMA,
        ml.OBJECT_NAME,
        ml.COLUMN_NAME,
        ml.LOCK_TYPE,
        ml.LOCK_DURATION,
        ml.LOCK_STATUS,
        ml.OWNER_THREAD_ID,
        t.PROCESSLIST_ID AS connection_id,
        t.PROCESSLIST_USER,
        t.PROCESSLIST_HOST,
        t.PROCESSLIST_COMMAND,
        t.PROCESSLIST_TIME,
        t.PROCESSLIST_STATE,
        t.PROCESSLIST_INFO
    FROM performance_schema.metadata_locks AS ml
    LEFT JOIN performance_schema.threads AS t
        ON t.THREAD_ID = ml.OWNER_THREAD_ID
    WHERE ml.OBJECT_SCHEMA = DATABASE()
      AND ml.OBJECT_NAME = 'orders'
    ORDER BY
        ml.LOCK_STATUS,
        t.PROCESSLIST_TIME DESC;

Key columns:

| Column | How to read it |
|---|---|
| `OBJECT_TYPE` | Type of locked object |
| `OBJECT_SCHEMA`, `OBJECT_NAME` | Database and object |
| `LOCK_TYPE` | Metadata lock mode |
| `LOCK_DURATION` | Lock lifetime, e.g., TRANSACTION, STATEMENT, or EXPLICIT |
| `LOCK_STATUS` | `GRANTED` means acquired; `PENDING` means waiting |
| `OWNER_THREAD_ID` | Thread owning the lock request |
| `PROCESSLIST_ID` | Connection ID for matching against the process list |
| `PROCESSLIST_INFO` | Current statement if the connection is running one |

A GRANTED lock may belong to an idle transaction; `PROCESSLIST_INFO` can then be NULL. A PENDING lock usually helps identify the waiting DDL statement.

### 8.2. Finding all waiting metadata locks

    SELECT
        OBJECT_TYPE,
        OBJECT_SCHEMA,
        OBJECT_NAME,
        LOCK_TYPE,
        LOCK_DURATION,
        OWNER_THREAD_ID
    FROM performance_schema.metadata_locks
    WHERE LOCK_STATUS = 'PENDING';

If no PENDING rows appear at query time, the DDL may have received the lock, finished, or the wait just cleared. This is a point-in-time state snapshot, not a lock history.

### 8.3. Using sys.schema_table_lock_waits

MySQL includes a view in the `sys` schema that joins waiter and blocker information:

    SELECT *
    FROM sys.schema_table_lock_waits
    WHERE object_schema = DATABASE()
      AND object_name = 'orders';

This view typically provides connection IDs, accounts, waiting statements, blocking statements/connections, and SQL columns suggesting kill commands. Exact columns depend on the `sys` schema version.

This is often a quick starting point when investigating hanging DDL. Always verify the blocker and business impact before running any KILL command.

## 9. Combining metadata_locks with process list and InnoDB transactions

### 9.1. Viewing active connections

    SHOW FULL PROCESSLIST;

Pay attention to:

- `Id`: connection ID.
- `User`, `Host`: identity and connection origin.
- `db`: default database.
- `Command`: Query, Sleep, or another state.
- `Time`: duration in the current command state.
- `State`: waiting or execution state.
- `Info`: current SQL statement, if any.

`SHOW FULL PROCESSLIST` does not by itself show which transactions hold MDLs. Combine it with `metadata_locks` and `innodb_trx`.

### 9.2. Finding the oldest InnoDB transactions

    SELECT
        trx_id,
        trx_state,
        trx_started,
        TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
        trx_mysql_thread_id AS connection_id,
        trx_query,
        trx_tables_locked,
        trx_rows_locked,
        trx_rows_modified
    FROM information_schema.innodb_trx
    ORDER BY trx_started;

Warning signs to watch for:

- A transaction that started a long time ago.
- `trx_query` is NULL yet the transaction still exists.
- `trx_mysql_thread_id` maps to a connection in the Sleep state.
- Unusually high locked row or table counts.

Not every MDL blocker necessarily appears as an active InnoDB transaction in `innodb_trx`; MDL also relates to other statements and objects. Therefore, `metadata_locks` remains the direct source of truth for observing MDL.

### 9.3. Mapping threads to connections

`OWNER_THREAD_ID` in Performance Schema is not the connection ID. Use `performance_schema.threads` to map it:

    SELECT
        THREAD_ID,
        PROCESSLIST_ID,
        PROCESSLIST_USER,
        PROCESSLIST_HOST,
        PROCESSLIST_COMMAND,
        PROCESSLIST_TIME,
        PROCESSLIST_STATE,
        PROCESSLIST_INFO
    FROM performance_schema.threads
    WHERE PROCESSLIST_ID IS NOT NULL;

When needing to kill a connection, use the appropriate `PROCESSLIST_ID`/connection ID—never confuse it with `THREAD_ID` or `ENGINE_TRANSACTION_ID`.

## 10. Workflow for diagnosing hanging DDL

Suppose an `ALTER TABLE orders` statement fails to complete:

**Step 1 — Confirm the DDL is waiting.**

    SHOW FULL PROCESSLIST;

Look for a connection whose `State` relates to metadata locks or an ALTER statement running for a long time.

**Step 2 — Identify the PENDING object and lock.**

    SELECT *
    FROM performance_schema.metadata_locks
    WHERE LOCK_STATUS = 'PENDING';

Verify the exact schema/table, mode, and owner thread of the waiting lock.

**Step 3 — Find GRANTED locks on the same object.**

Filter `metadata_locks` by the same `OBJECT_TYPE`, `OBJECT_SCHEMA`, and `OBJECT_NAME`, then locate GRANTED locks and their owning threads. Use mode compatibility rules to pinpoint locks that can block the DDL request.

**Step 4 — Map the blocker to a connection.**

Join `OWNER_THREAD_ID` with `performance_schema.threads`; retrieve `PROCESSLIST_ID`, user, host, command, and time.

**Step 5 — Inspect the transaction.**

Cross-reference the connection ID with `information_schema.innodb_trx`. If the transaction started long ago, its current query is NULL, and the process list shows Sleep, it is likely an idle transaction holding MDL.

**Step 6 — Verify ownership.**

Check with the application/job using that connection or inspect logs/request traces to see what the transaction is doing. Never guess solely from user/host because a single pool can serve many request types.

**Step 7 — Choose how to release it.**

Prefer letting the application COMMIT/ROLLBACK cleanly. If the transaction was abandoned and must be cleared urgently, assess impact before terminating the connection.

**Step 8 — Handle the waiting DDL and inspect the queue.**

If the DDL should not proceed right now, cancel the waiting statement using the exact connection ID after verification. Then confirm queued requests clear and reschedule the DDL.

## 11. How do KILL QUERY and KILL CONNECTION differ?

MySQL provides two common commands:

    KILL QUERY 12345;

    KILL CONNECTION 12345;

- `KILL QUERY` stops the connection's currently executing statement while keeping the connection alive.
- `KILL CONNECTION` terminates the connection; any open transaction on that connection is rolled back as the server closes the session.

Important point for idle transactions:

- If a connection is in Sleep with no running statement, `KILL QUERY` does not resolve an open transaction holding an MDL.
- To release transaction-scoped MDL on an abandoned session, the transaction must COMMIT/ROLLBACK or the connection must terminate.
- `KILL CONNECTION` can trigger a massive rollback, lose uncommitted work, and cause connection errors in the application.

Never run a KILL command simply because a connection has a long Sleep time. Verify connection ID, transaction age, locked objects, owner, and business impact first.

If the waiting DDL itself is causing the query queue to pile up and cannot run yet, `KILL QUERY` on the DDL's connection can cancel the waiting request while keeping the connection alive. Afterward, resolve the blocker and reschedule the DDL.

## 12. DDL implicit commit and transaction boundaries

Many DDL statements such as `ALTER TABLE`, `CREATE TABLE`, and `DROP TABLE` cause an implicit commit. This means an open transaction in the session running the DDL can be committed before the DDL executes; you cannot wrap ALTER TABLE inside a transaction and expect a subsequent ROLLBACK to undo the structural change.

Example:

    START TRANSACTION;

    UPDATE orders
    SET status = 'ARCHIVED'
    WHERE id = 1001;

    ALTER TABLE orders
    ADD COLUMN source VARCHAR(30);

    ROLLBACK;

Do not assume the final ROLLBACK will undo both the UPDATE and the ALTER. DDL causes an implicit commit per MySQL's rules; separate data changes and schema changes into deployment steps with clear boundaries.

MySQL 8.0 supports atomic DDL for many supported operations: metadata and data changes from a single DDL can recover atomically on a server crash. Atomic DDL does not mean DDL participates in user transactions or can be rolled back via a ROLLBACK statement.

## 13. Timeouts related to metadata locks

MySQL provides the `lock_wait_timeout` variable to bound metadata lock wait time. Check it with:

    SELECT
        @@SESSION.lock_wait_timeout,
        @@GLOBAL.lock_wait_timeout;

Set a specific limit for a DDL-running session:

    SET SESSION lock_wait_timeout = 30;

If the MDL cannot be acquired within the configured duration, the statement can return a timeout error instead of waiting indefinitely or for too long. Choose a specific value based on your deployment window and system wait tolerance.

Distinguish from:

    SELECT @@SESSION.innodb_lock_wait_timeout;

`innodb_lock_wait_timeout` governs InnoDB row lock wait duration; `lock_wait_timeout` governs metadata lock waits. Changing the wrong variable will not address the actual wait source.

A timeout only limits how long the requesting session waits. It does not automatically terminate blocking transactions or fix why blockers retain MDLs.

## 14. Preventing long transactions from holding MDL

### 14.1. Always terminate transactions

Every application flow must ensure COMMIT or ROLLBACK across all success and error branches. With JDBC, use explicit transaction boundaries and `try/finally` so connections are never returned to the pool while a transaction remains open.

Logic example:

    connection.setAutoCommit(false);
    try {
        // Execute SQL statements requiring the transaction.
        connection.commit();
    } catch (Exception ex) {
        connection.rollback();
        throw ex;
    } finally {
        // Return the connection to the pool only after the transaction has been cleaned up.
    }

This is illustrative pseudocode. In production code, also handle rollback errors and restore connection state per pool/driver contracts.

### 14.2. Never hold transactions open during external waits

Avoid:

1. Opening a transaction.
2. Running SELECT on a table.
3. Calling an HTTP service or waiting for user input.
4. Processing a large file.
5. Committing several minutes later.

Off-database steps extend MDL retention and can also hold row locks, undo history, or connection pool slots. Gather necessary data, end the transaction promptly, and perform external work afterward if business rules allow.

### 14.3. Monitoring idle-in-transaction sessions

Set alerts for transactions exceeding maximum age for each workload. Track:

- Transaction age.
- Connections in Sleep that still hold active transactions.
- Number of locked tables/rows.
- Long-lived GRANTED metadata locks.
- PENDING DDL locks.
- Connection pools returning connections without resetting transactions.

Do not set a single uniform threshold for all workloads; a long reporting transaction may be legitimate, though it should be scheduled so it does not block critical DDL or OLTP.

## 15. Planning safe DDL execution

Before running a migration:

1. Identify the table, change type, and supported DDL algorithm.
2. Check for long-running transactions and existing metadata locks.
3. Pick a low-traffic window or deploy using a suitable online strategy.
4. Set a sensible `lock_wait_timeout` for the migration session.
5. Monitor the process list, metadata locks, and replication while running.
6. If DDL waits too long, find the blocker rather than repeatedly opening more sessions running the same ALTER.
7. If cancellation is required, verify DDL and schema state before retrying.
8. Upon completion, verify the schema and test the application.

Avoid launching multiple identical ALTER TABLE statements concurrently on the same table. Multiple waiting MDL requests complicate queuing and add extra load.

## 16. Common misconceptions

| Misconception | Reality |
|---|---|
| Regular SELECT does not lock so it cannot block DDL | SELECT still acquires MDL; an explicit transaction can retain locks after the statement finishes |
| A Sleep connection holds no locks | An idle transaction can hold MDL and row locks |
| Hanging DDL is definitely caused by InnoDB row locks | DDL may be waiting on a metadata lock, which is a different mechanism |
| Online DDL needs no locks | Online/INSTANT DDL still requires MDL at certain phases |
| LOCK=NONE means zero locks exist | It describes supported concurrent DML, not elimination of MDL |
| Raising innodb_lock_wait_timeout fixes DDL waits | Metadata lock waits use `lock_wait_timeout` |
| KILL QUERY always frees a transaction | It stops only the active statement; an idle transaction can remain open |
| ROLLBACK undoes ALTER TABLE | DDL normally causes an implicit commit and is outside user transaction rollback |
| PROCESSLIST_INFO = NULL means the connection holds nothing | A Sleep connection may still own a transaction and MDL |
| Atomic DDL means DDL is transactional for applications | Atomic DDL ensures crash recovery for DDL, not user-driven rollback |

## 17. Checklist for investigating metadata locks and hanging DDL

- On which object and schema is the DDL waiting?
- Are there PENDING locks in `performance_schema.metadata_locks`?
- Which thread owns the PENDING lock, and what is its corresponding connection ID?
- Which GRANTED locks on the same object are incompatible with the waiting request?
- Is the blocker a Sleep connection that still holds a transaction in `innodb_trx`?
- When did the transaction start, which tables has it accessed, and which application/job owns it?
- Is another waiting DDL already causing new requests to queue up?
- Can the application safely COMMIT/ROLLBACK?
- If a KILL is needed, are the differences between KILL QUERY and KILL CONNECTION clear?
- Does the DDL support the chosen ALGORITHM/LOCK on the current MySQL version?
- Is `lock_wait_timeout` configured appropriately for the migration session?
- After clearing the blocker, has the queue drained and has the DDL completed?

## Conclusion

Metadata locks protect object definitions while MySQL uses or modifies tables. A regular SELECT needs no S record locks yet still acquires MDL; if it executes inside an open transaction, MDL can persist after the SELECT finishes and block ALTER TABLE. Consequently, a Sleep connection can still be a blocker. Look for PENDING/GRANTED locks in `performance_schema.metadata_locks`, and use `sys.schema_table_lock_waits`, the process list, and `innodb_trx` to map waiters and blockers. Distinguish `lock_wait_timeout` from `innodb_lock_wait_timeout`, remember that online DDL still requires MDL, and terminate connections only after evaluating rollback impact. Keeping transactions short, releasing connections properly, and planning DDL around lock state prevents hanging migrations and cascading query queues.
