# Lock wait timeouts and rollback scope by configuration

When a transaction needs to lock a row currently held by another transaction, InnoDB must wait. If the wait exceeds the threshold, MySQL returns a lock wait timeout error. By default, this error does not mean the entire transaction has been aborted: under the default configuration, InnoDB rolls back only the timed-out statement, while earlier changes in the same transaction may still remain pending commit.

In the DATABASE_MYSQL module, understanding rollback scope accurately is critical for handling errors without accidentally committing partial work. This lesson focuses on two InnoDB settings, the difference between row locks and metadata locks, how to reproduce a timeout with two sessions, and a safe rollback and retry workflow.

## 1. When does a lock wait timeout occur?

InnoDB uses locks to protect data being read or modified by transactions. If transaction B requests a lock incompatible with a lock held by transaction A, B must wait for A to release the lock via COMMIT or ROLLBACK.

Example:

- Session A opens a transaction and updates the account with `account_id = 1`.
- Session A has not committed yet, so it still holds the lock on that row.
- Session B also updates `account_id = 1`.
- Session B must wait for Session A.
- If the wait exceeds the limit, Session B receives a lock wait timeout error.

Lock wait timeout is commonly reported as MySQL error 1205 (`ER_LOCK_WAIT_TIMEOUT`), with the message “Lock wait timeout exceeded; try restarting transaction”. This error stems from waiting too long for a lock, distinct from a deadlock.

Error code 1205 can also appear when an operation waiting on a metadata lock exceeds `lock_wait_timeout`. Therefore, identify which lock type is waiting via Performance Schema and statement context; looking solely at the error code or message is insufficient to conclude it is an InnoDB row lock.

Not every waiting statement is waiting on an InnoDB row lock. MySQL also has metadata locks (MDL)—for instance, DDL must wait for other transactions to finish before altering a table's structure. Identify the lock type before adjusting timeouts.

## 2. Two settings to distinguish

| System variable | Scope of effect | Meaning |
|---|---|---|
| `innodb_lock_wait_timeout` | InnoDB row locks | Number of seconds a transaction waits for an InnoDB row lock before timing out |
| `innodb_rollback_on_timeout` | InnoDB transactions | Determines whether a timeout rolls back only the current statement or the entire transaction |
| `lock_wait_timeout` | Metadata locks | Wait timeout for metadata locks, e.g., when DDL needs a table's metadata lock |

These three variables do not substitute for one another. Increasing `innodb_lock_wait_timeout` will not help a DDL statement waiting on a metadata lock; changing `innodb_rollback_on_timeout` does not govern wait duration.

## 3. innodb_lock_wait_timeout: limiting row lock wait duration

The `innodb_lock_wait_timeout` variable controls how long InnoDB waits for a row lock. MySQL's default value is 50 seconds unless configured otherwise. This variable can be changed dynamically at the GLOBAL or SESSION level.

Check configuration:

~~~sql
SELECT
    @@GLOBAL.innodb_lock_wait_timeout AS global_timeout,
    @@SESSION.innodb_lock_wait_timeout AS session_timeout;
~~~

Set a 5-second timeout for the current session:

~~~sql
SET SESSION innodb_lock_wait_timeout = 5;
~~~

Set a 10-second default for new sessions:

~~~sql
SET GLOBAL innodb_lock_wait_timeout = 10;
~~~

Changing GLOBAL does not overwrite SESSION values already active on existing connections. With connection pools, set or reset the SESSION variable per connection according to application policy.

A short timeout fails requests quickly under contention, though it can fail legitimate transactions if the system routinely holds locks for a while. A longer timeout reduces errors under normal load, yet lets requests hang longer and masks transactions holding locks too long. Tune this value based on target latency, transaction duration, and observed metrics.

Never treat increasing the timeout as a root-cause fix. Locate the transaction holding the lock, determine why it has not finished, and narrow lock scope/duration.

## 4. innodb_rollback_on_timeout: deciding rollback scope

This is the most critical setting in this lesson. Under the default configuration:

~~~ini
innodb_rollback_on_timeout = OFF
~~~

When an InnoDB row lock wait timeout occurs, InnoDB rolls back only the statement that timed out. In InnoDB tables, changes from the failing statement itself are undone as a single unit; earlier statements in the same transaction are not automatically rolled back. The transaction can remain open and keep holding locks acquired earlier.

If autocommit is enabled and the statement runs standalone outside an explicit transaction, that statement is usually the entire transaction; therefore, rolling back the statement means the single-statement transaction is not committed. The sharpest difference arises when an application uses `START TRANSACTION` or disables autocommit and runs multiple statements before the error.

When enabled:

~~~ini
innodb_rollback_on_timeout = ON
~~~

InnoDB rolls back the entire transaction when a lock wait timeout occurs. All uncommitted changes in that transaction are discarded.

This difference directly affects application logic:

| Configuration | When a statement hits lock wait timeout | State of earlier statements |
|---|---|---|
| OFF (default) | Only the current statement is rolled back | Still inside the transaction; can be committed if the application proceeds to call COMMIT |
| ON | The entire transaction is rolled back | Earlier uncommitted changes are also discarded |

`innodb_rollback_on_timeout` is a GLOBAL configuration variable and cannot be changed dynamically per session. It must be set in the MySQL option file or server startup arguments, followed by a MySQL restart to take effect.

With `autocommit = 1`, each standalone statement normally runs as its own transaction. When that statement times out and rolls back, there are no earlier statements in the same transaction to retain. In an explicit transaction, by contrast, statements prior to the timeout remain active in the transaction when this variable is OFF.

Example in the config file:

~~~ini
[mysqld]
innodb_rollback_on_timeout = ON
~~~

You cannot run `SET SESSION innodb_rollback_on_timeout = ON` to alter behavior for a single connection. Check documentation for your exact server version and operational procedures before changing this setting in production.

## 5. Two-session example: default rolls back only the statement

Create the test table:

~~~sql
CREATE TABLE accounts (
    account_id INT NOT NULL,
    balance DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (account_id)
) ENGINE=InnoDB;

INSERT INTO accounts (account_id, balance)
VALUES (1, 1000.00), (2, 2000.00);
~~~

Open two independent MySQL connections.

**Session A — holds the lock on the first row**

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 1;

-- Temporarily do not COMMIT or ROLLBACK yet.
~~~

Session A holds the lock on `account_id = 1` until the transaction ends.

**Session B — executes one statement first, then waits on a lock**

~~~sql
SET SESSION innodb_lock_wait_timeout = 5;

START TRANSACTION;

UPDATE accounts
SET balance = balance - 50.00
WHERE account_id = 2;

-- This statement must wait for Session A and will time out after about 5 seconds.
UPDATE accounts
SET balance = balance + 50.00
WHERE account_id = 1;
~~~

When the last UPDATE receives error 1205 while `innodb_rollback_on_timeout` is OFF:

1. The UPDATE on `account_id = 1` is rolled back.
2. The earlier UPDATE on `account_id = 2` remains inside transaction B.
3. Transaction B has not ended automatically.
4. If the application calls COMMIT right after the error, the 50-unit deduction on `account_id = 2` can still be committed.

Therefore, in business applications, the safe practice is usually to ROLLBACK the entire transaction after a timeout error, unless logic is explicitly designed to continue from the remaining state.

**Session B — end the transaction**

~~~sql
ROLLBACK;
~~~

Then Session A can release its lock:

~~~sql
COMMIT;
~~~

This example shows that a statement error does not automatically mean all earlier changes in the transaction were discarded.

## 6. Repeating the example with innodb_rollback_on_timeout = ON

If the server is started with:

~~~ini
[mysqld]
innodb_rollback_on_timeout = ON
~~~

Re-run the two-session experiment. Session B executes UPDATE on `account_id = 2` first, then UPDATE on `account_id = 1` and waits until timeout.

When the timeout occurs:

- The waiting statement is aborted.
- All of transaction B is rolled back.
- The earlier change on `account_id = 2` is also discarded.
- Session B no longer holds locks from the rolled-back transaction.

You cannot toggle this variable with `SET` inside a session for direct comparison; you must change the server configuration and restart per administrative procedures. During testing, confirm the active value after server startup:

~~~sql
SELECT @@GLOBAL.innodb_rollback_on_timeout;
~~~

Never test configuration changes on production merely for observation. Use a test environment with recoverable data.

## 7. How does a lock wait timeout differ from a deadlock?

Both errors involve locking, but their handling differs:

| Aspect | Lock wait timeout | Deadlock |
|---|---|---|
| Nature | One transaction waits for a lock longer than configured timeout | Transactions form a wait cycle; none can proceed on its own |
| Detection | Wait timer expires | InnoDB detects a lock cycle when deadlock detection is active |
| Common error code | 1205 | 1213 (`ER_LOCK_DEADLOCK`) |
| InnoDB rollback scope | Depends on `innodb_rollback_on_timeout` | Entire chosen victim transaction is rolled back |
| Application handling | Usually roll back the entire transaction then consider retry | Retry the entire rolled-back transaction |

`innodb_rollback_on_timeout` does not change deadlock rollback rules. When InnoDB detects a deadlock, it chooses one transaction as the victim and rolls back that entire transaction to break the wait cycle. The application must retry the entire transaction using the same idempotency key.

If the deadlock detector is disabled or does not detect a cycle, timeouts may become the fallback mechanism to break waiting; do not design transactions around that assumption.

## 8. lock_wait_timeout: metadata locks have their own timeout

Metadata locks protect the metadata of database objects such as tables, schemas, or routines. For example, a transaction using the `customers` table can hold a metadata lock until the transaction finishes; an `ALTER TABLE` on the same table must wait.

The `lock_wait_timeout` variable controls the metadata lock wait timeout. It is distinct from `innodb_lock_wait_timeout`:

~~~sql
SELECT
    @@GLOBAL.lock_wait_timeout AS global_mdl_timeout,
    @@SESSION.lock_wait_timeout AS session_mdl_timeout;

-- Limit MDL wait time for the current session.
SET SESSION lock_wait_timeout = 60;
~~~

The default `lock_wait_timeout` in MySQL is very long (31,536,000 seconds). For a DDL session where wait time should be bounded, set an appropriate SESSION timeout before running the statement. This change does not alter InnoDB's row lock timeout.

A typical symptom:

- One session opens a transaction, runs SELECT or UPDATE on a table, and leaves the transaction open.
- Another session runs ALTER TABLE on the same table.
- ALTER TABLE waits on a metadata lock even if there is no row lock conflict.
- Upon exceeding `lock_wait_timeout`, the DDL statement reports a timeout.

To diagnose MDL, inspect `performance_schema.metadata_locks` and the process list. Do not increase `innodb_lock_wait_timeout` to address this kind of wait.

## 9. Why can a transaction hold locks for a long time?

A lock wait timeout is often a symptom of a transaction holding locks too long or transactions contending over the same data region. Common causes:

- The application opens a transaction and makes HTTP calls, reads files, or waits for user input before committing.
- A transaction updates multiple rows, but workers process rows in inconsistent orders.
- An UPDATE/DELETE scans too many rows due to lacking a suitable index.
- A range query acquires next-key locks or gap locks depending on isolation level and access path.
- Large batches hold locks for an extended duration.
- Connections are abandoned in a connection pool while transactions remain open.
- DDL must wait for old transactions to release metadata locks.

A transaction should perform off-database work before opening the transaction whenever possible. After `START TRANSACTION`, execute only the SQL statements belonging to that atomic unit; commit or roll back promptly.

Indexes affect more than read speed. For UPDATE/DELETE, appropriate indexes help InnoDB locate target rows faster and reduce the number of records needing locks. However, new indexes also carry write overhead and do not guarantee all range locks disappear.

## 10. Diagnosing waiting row locks

When encountering the error, determine:

1. Which transaction is waiting?
2. Which transaction holds the lock?
3. Which table, index, and rows are involved?
4. When did the lock-holding transaction start?
5. Which SQL statement acquired the lock and why has the transaction not ended?

In MySQL 8.0, Performance Schema provides `data_locks` and `data_lock_waits`. You can use the convenience view in the `sys` schema:

~~~sql
SELECT *
FROM sys.innodb_lock_waits;
~~~

This view can display the waiting session, blocking session, wait duration, table/index, and related SQL. Read privileges on Performance Schema/`sys` are required, and the view may vary or be absent in certain distributions.

Querying Performance Schema directly:

~~~sql
SELECT
    w.REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx_id,
    wt.PROCESSLIST_ID AS waiting_connection_id,
    w.BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx_id,
    bt.PROCESSLIST_ID AS blocking_connection_id,
    dl.OBJECT_SCHEMA,
    dl.OBJECT_NAME,
    dl.INDEX_NAME,
    dl.LOCK_TYPE,
    dl.LOCK_MODE,
    dl.LOCK_DATA
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS dl
  ON dl.ENGINE = w.ENGINE
 AND dl.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
LEFT JOIN performance_schema.threads AS wt
  ON wt.THREAD_ID = w.REQUESTING_THREAD_ID
LEFT JOIN performance_schema.threads AS bt
  ON bt.THREAD_ID = w.BLOCKING_THREAD_ID;
~~~

Further inspect active transactions and running statements:

~~~sql
SHOW FULL PROCESSLIST;
SHOW ENGINE INNODB STATUS;
~~~

`SHOW ENGINE INNODB STATUS` provides InnoDB status and latest deadlock details; it does not replace current wait-tracking tables. Do not focus solely on the waiting query while ignoring the blocking transaction: the blocker may be in the `Sleep` state while still holding an uncommitted transaction.

## 11. Diagnosing metadata locks

If you suspect DDL is waiting on a metadata lock, inspect Performance Schema:

~~~sql
SELECT
    OBJECT_TYPE,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    LOCK_TYPE,
    LOCK_DURATION,
    LOCK_STATUS,
    OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE LOCK_STATUS = 'PENDING'
   OR OBJECT_NAME = 'customers';
~~~

You can join `OWNER_THREAD_ID` with `performance_schema.threads` to find the connection ID and process list. Views in the `sys` schema such as `schema_table_lock_waits` also provide more readable blocker/waiter queries.

When DDL is blocked:

- Find the transaction holding the metadata lock on the object.
- Determine whether that session still needs the transaction.
- Have the application end the transaction properly or follow operational procedures.
- Kill a connection only after assessing rollback impact and receiving operational authorization.
- Set a reasonable `lock_wait_timeout` for the DDL session so it does not wait indefinitely.

Never automatically kill a blocking session just because it blocks DDL. Rolling back a long transaction can generate heavy load and impact business operations.

## 12. How applications should handle error 1205

When a statement inside a transaction receives a lock wait timeout, the application should:

1. Log the error code, batch/request ID, connection ID, statement or operation, wait duration, and transaction context.
2. If the connection is still active, ROLLBACK the entire transaction to restore the session to a clean state.
3. Never return a connection to the pool without ensuring the transaction has ended.
4. Wait with backoff and jitter outside any transaction.
5. If business rules allow, retry the entire transaction from the start using the same idempotency key.
6. Cap retry attempts; if failures persist, return a handleable error and emit alerts.

Pseudocode example:

~~~text
for attempt in 1..MAX_ATTEMPTS:
    begin transaction
    try:
        execute all business statements
        commit
        return success
    catch lock_wait_timeout or deadlock:
        rollback transaction
        if attempt == MAX_ATTEMPTS:
            raise retryable database error
        sleep(exponential_backoff_with_jitter(attempt))
~~~

This is pseudocode, not SQL syntax. Retry logic should live at the transaction-management layer to ensure every statement in the business unit is re-executed together.

When `innodb_rollback_on_timeout` is OFF, explicit rollback is especially critical because the transaction may still retain changes from statements before the timed-out statement. Even when the variable is ON, manage transaction state explicitly and never assume the application can proceed with the next statement.

## 13. What NOT to do on timeout

| Wrong approach | Why it is dangerous | Proper approach |
|---|---|---|
| Catching error 1205 and immediately calling COMMIT | Can commit earlier statements when config rolls back only the statement | ROLLBACK the entire transaction then retry in a controlled manner |
| Immediately raising timeout to a huge value | Makes requests hang longer and hides lock-holding transactions | Find the blocker, transaction duration, and access path |
| Retrying only the failed statement | Earlier statements may remain in the transaction; business atomicity may break | Retry the entire transaction after rollback |
| Killing the blocker without investigating | Can abort valid transactions or trigger massive rollbacks | Verify owner, transaction age, and impact before intervening |
| Confusing MDL with row locks | Tunes the wrong timeout variable and leaves root cause unsolved | Check `data_lock_waits` and `metadata_locks` |
| Returning the errored connection to the pool | Connection may still hold an open transaction and locks | Roll back/reset connection before returning to pool |
| Infinite retries without backoff | Creates retry storms and increases contention | Cap attempts, apply backoff and jitter |

## 14. Reducing the likelihood of lock wait timeouts

- Keep transactions short; do not call external services or wait for input while holding locks.
- Update rows in a consistent order across transactions, such as always ascending by `account_id`.
- Create appropriate indexes for WHERE and JOIN predicates of UPDATE/DELETE statements.
- Split large batches into reasonably sized chunks, committing each idempotent unit.
- Avoid read-then-write when a conditional UPDATE or explicit row lock can be used.
- Use `SELECT ... FOR UPDATE` when needing to read and update a row in the same transaction, locking only needed rows and finishing quickly.
- Never leave transactions open after finishing data work simply because the application has not closed the connection.
- Monitor long transactions, lock waits, deadlocks, and error rates over time.

Example locking a row before checking balance:

~~~sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;

-- Application checks the balance and performs the needed update.
UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 1
  AND balance >= 100.00;

COMMIT;
~~~

`SELECT ... FOR UPDATE` acquires the appropriate exclusive lock on the read row within the transaction. Check the UPDATE's affected row count; if the balance is insufficient or the account is missing, roll back according to business rules. Never hold locks while the application performs network calls or unrelated tasks.

## 15. Inspecting configuration and transaction state

Before investigating, record the values of relevant variables:

~~~sql
SELECT
    @@GLOBAL.innodb_lock_wait_timeout,
    @@SESSION.innodb_lock_wait_timeout,
    @@GLOBAL.innodb_rollback_on_timeout,
    @@GLOBAL.lock_wait_timeout,
    @@SESSION.autocommit,
    @@SESSION.transaction_isolation;
~~~

`transaction_isolation` may appear differently depending on MySQL version; on older versions, the corresponding variable may be named `tx_isolation`. If querying a variable that does not exist, check your server version and use the supported name.

When hitting a timeout inside an explicit transaction, never infer that the transaction ended solely from the error message. Under default settings, check state and explicitly ROLLBACK. In applications, always provide a transaction cleanup path when a statement fails.

## 16. Operational checklist

1. Determine whether the timeout belongs to an InnoDB row lock or a metadata lock.
2. Record `innodb_lock_wait_timeout` and `innodb_rollback_on_timeout`.
3. Check `lock_wait_timeout` if DDL or metadata operations are waiting.
4. Identify the waiting transaction and the blocking transaction.
5. Check when the blocking transaction started, which rows it modified, and why it has not finished.
6. Distinguish error 1205 from deadlock 1213.
7. After a timeout, roll back the entire transaction at the application layer if business logic requires atomicity.
8. Retry only after rollback, with backoff, jitter, and an attempt cap.
9. Ensure retries are idempotent and do not repeat external side effects outside the database.
10. Tune timeouts based on metrics rather than using long timeouts to mask design flaws.
11. If changing `innodb_rollback_on_timeout`, assess server-wide impact and plan the restart.
12. After changes, verify the live configuration and monitor timeout/deadlock rates.

## 17. Practice exercises

1. Create the `accounts` table and test the two-session example; verify Session B receives error 1205.
2. With `innodb_rollback_on_timeout` at its default OFF, update an unlocked row first and then wait for a row held by Session A; observe that the first change remains in the transaction.
3. After the timeout, run ROLLBACK in Session B and confirm the earlier change is not committed.
4. In a test environment, enable `innodb_rollback_on_timeout` in the server config, restart, and re-run; confirm all of transaction B is rolled back.
5. Test `SET SESSION innodb_lock_wait_timeout` with different values; observe wait duration and impact on requests.
6. Create a transaction holding a metadata lock, run ALTER TABLE in another session, and observe `lock_wait_timeout`.
7. Use `sys.innodb_lock_waits` or `performance_schema.data_lock_waits` to identify the row lock blocker.
8. Use `performance_schema.metadata_locks` to identify sessions holding or waiting for MDL.
9. Create two transactions updating two rows in opposite order to observe a deadlock; distinguish error 1213 from 1205.
10. Write application-layer error-handling logic: roll back the full transaction, apply backoff, and retry with the same idempotency key.

You complete this lesson when you can explain why the default timeout rolls back only the statement, describe how `innodb_rollback_on_timeout` changes rollback scope, distinguish row locks from metadata locks and deadlocks, and build a rollback/retry flow that never accidentally commits incomplete changes.
