# How autocommit Affects Observed Isolation Level

In MySQL, `autocommit` and transaction isolation level are two distinct settings that work together to determine how an application observes data.

- `autocommit` determines transaction boundaries: whether each statement commits on its own or multiple statements belong to the same transaction.
- The isolation level determines how a transaction sees changes made by other transactions, as well as the locking level needed to protect read/write operations.

With InnoDB, the default isolation level is typically `REPEATABLE READ`. However, if `autocommit=1`, each standalone SELECT statement is its own separate transaction. Therefore, two consecutive SELECT statements can see two different snapshots even though the isolation level remains REPEATABLE READ. Only when multiple SELECT statements are placed inside the same transaction does REPEATABLE READ keep the same read view for consistent reads within that transaction.

This lesson falls within the scope of `DATABASE_MYSQL`: understanding MVCC, transactions, and isolation levels; controlling commit boundaries; predicting the data each query observes; designing safe multi-step operations; and managing connection state in applications.

## 1. Two Different Settings: autocommit and Isolation Level

### 1.1. Autocommit Determines When a Transaction Ends

MySQL has the `autocommit` system variable:

~~~sql
SELECT @@session.autocommit;
~~~

Common values:

| Value | Meaning |
|---:|---|
| 1 | Autocommit enabled. Each statement runs as its own separate transaction unless an explicit transaction is already open. |
| 0 | Autocommit disabled. The session maintains a transaction for subsequent statements until COMMIT or ROLLBACK. |

With `autocommit=1`, a data-modification statement on InnoDB commits automatically on success if not inside an explicit transaction:

~~~sql
UPDATE account
SET balance = balance + 100
WHERE account_id = 1;
~~~

After the statement, the change is already committed. A subsequent statement does not belong to the same transaction.

With `autocommit=0`, changes are not committed automatically:

~~~sql
SET autocommit = 0;

UPDATE account
SET balance = balance + 100
WHERE account_id = 1;

-- The change still belongs to the current transaction.
COMMIT;
~~~

If ROLLBACK is run instead of COMMIT before the transaction ends, the InnoDB change will be undone.

### 1.2. Isolation Level Determines How Data Is Read

InnoDB supports four standard isolation levels:

| Isolation level | Key Characteristics |
|---|---|
| READ UNCOMMITTED | Can read uncommitted changes from other transactions (dirty read). |
| READ COMMITTED | Each consistent read takes a fresh snapshot at the start of the SELECT statement; can see new commits between two reads in the same transaction. |
| REPEATABLE READ | Consistent reads in the same transaction share the read view created at the first consistent read, unless a separate snapshot is requested. |
| SERIALIZABLE | The strictest level; for multi-statement transactions, ordinary SELECTs are converted to locking reads under conditions defined by InnoDB. |

Check the isolation level:

~~~sql
SELECT
    @@session.transaction_isolation AS session_isolation,
    @@global.transaction_isolation AS global_default;
~~~

The isolation level does not itself decide when a transaction ends. Autocommit does not itself change the isolation level. The two variables answer two separate questions:

- Autocommit: which statements belong to the same transaction?
- Isolation: which data version do read statements within the transaction see?

## 2. Why Does autocommit Affect the Observed Isolation Level?

InnoDB's MVCC allows consistent reads to read the data version matching a read view (snapshot) without having to lock the rows being read in the manner of a typical locking read.

With `REPEATABLE READ`:

- Within a transaction, the first consistent read creates a read view.
- Subsequent consistent reads in the same transaction continue using that read view.
- Commits by other transactions after the read view is created do not change the results of subsequent consistent reads in the current transaction.

When `autocommit=1`, a standalone SELECT statement typically ends its transaction right after execution. The next SELECT starts a new transaction and creates a new read view. Therefore, each SELECT statement can see new commits from other transactions.

When `autocommit=0` or using `START TRANSACTION`, multiple SELECT statements can belong to the same transaction. Under REPEATABLE READ, they can see the same snapshot, even if other transactions have committed new data.

This is why two sessions can observe different results even while both use REPEATABLE READ: their transaction boundaries differ.

## 3. Autocommit Enabled: Each Standalone SELECT Can See a New Snapshot

Suppose we have an accounts table:

~~~sql
CREATE TABLE account_mvcc_demo (
    account_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO account_mvcc_demo (account_id, balance)
VALUES (1, 1000.00);
~~~

Session A configures:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SET autocommit = 1;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

The first result is 1000.00. Because autocommit is enabled and there is no explicit transaction, the SELECT statement ends its read transaction.

Meanwhile, Session B updates and commits:

~~~sql
START TRANSACTION;

UPDATE account_mvcc_demo
SET balance = balance + 200
WHERE account_id = 1;

COMMIT;
~~~

Session A reruns the same SELECT statement:

~~~sql
SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

The result this time is 1200.00.

This does not violate REPEATABLE READ. The two SELECTs reside in two independent transactions, each with its own read view. REPEATABLE READ guarantees the repeatability of consistent reads within the same transaction; it does not preserve snapshots across finished transactions.

### 3.1. Implications for Multi-Query Reports

Suppose a report screen runs two statements:

~~~sql
SELECT SUM(balance)
FROM account_mvcc_demo;

SELECT COUNT(*)
FROM account_mvcc_demo;
~~~

If autocommit=1, each statement is a separate transaction. Another transaction can commit between the two statements. In that case, total balance and account count are computed from two different snapshots.

If the report needs metrics consistent at the same logical point in time, group them into a REPEATABLE READ transaction or use a single appropriate aggregate SELECT statement.

## 4. Autocommit Enabled with an Explicit Transaction

Having autocommit enabled does not mean you cannot create a multi-statement transaction. `START TRANSACTION` opens an explicit transaction; subsequent statements belong to that transaction until COMMIT or ROLLBACK.

Session A:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SET autocommit = 1;

START TRANSACTION;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Suppose the result is 1000.00 and the first consistent read has created a read view.

Session B updates and commits:

~~~sql
START TRANSACTION;

UPDATE account_mvcc_demo
SET balance = balance + 200
WHERE account_id = 1;

COMMIT;
~~~

Session A reads again inside the open transaction:

~~~sql
SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

The result is still 1000.00 because the consistent read continues using transaction A's read view.

Then A commits:

~~~sql
COMMIT;
~~~

A's next SELECT is a new transaction, since autocommit is still enabled. It can see 1200.00.

Key point: `autocommit=1` only means standalone statements commit automatically. Once an explicit transaction is opened, statements inside it are still grouped into one transaction.

## 5. Autocommit Disabled: Multiple Statements Share a Transaction

With `autocommit=0`, the session maintains a transaction for subsequent statements until COMMIT or ROLLBACK. When the transaction ends, the session remains with autocommit disabled and the next transaction begins when a statement requiring a transaction runs.

Session A:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SET autocommit = 0;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Suppose the result is 1000.00. This is the first consistent read in the transaction and creates the read view.

Session B updates balance to 1200.00 and COMMITs.

Session A reads again:

~~~sql
SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

The result is still 1000.00 because transaction A has not ended and still uses the old snapshot.

End transaction A:

~~~sql
COMMIT;
~~~

A's next SELECT statement belongs to a new transaction:

~~~sql
SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

The result can be 1200.00 because the new transaction creates a new read view.

### 5.1. Autocommit=0 Does Not Mean a Snapshot Is Taken Immediately at SET

A common misconception is that simply running:

~~~sql
SET autocommit = 0;
~~~

captures a snapshot immediately at that moment. With REPEATABLE READ, an ordinary consistent read's read view is created when the transaction performs its first consistent read, not necessarily right when changing the autocommit variable.

If you need to create a consistent snapshot immediately upon starting a transaction, MySQL/InnoDB supports:

~~~sql
START TRANSACTION WITH CONSISTENT SNAPSHOT;
~~~

This option is meaningful with InnoDB at REPEATABLE READ; at other isolation levels, MySQL may ignore the option and emit a warning. Check warnings and the documentation for your running version.

## 6. Comparing REPEATABLE READ and READ COMMITTED in the Same Transaction

To see how important the isolation level is, keep the multi-statement transaction the same and change only the isolation level.

### 6.1. REPEATABLE READ

Session A:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Session B updates and commits the balance.

Session A SELECTs again in the same transaction. With an ordinary consistent read, A still sees the value in the snapshot created on the first read.

### 6.2. READ COMMITTED

Session A:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Session B updates and commits the balance.

Session A SELECTs again:

~~~sql
SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Under READ COMMITTED, each consistent read takes a fresh snapshot at the start of the SELECT statement. Therefore, the second read can see the value B just committed, even though transaction A is still open.

### 6.3. Observation Comparison Table

Suppose initially balance=1000; B commits balance=1200 between A's two reads:

| A's Configuration | Transaction A | Read 1 | Read 2 |
|---|---|---:|---:|
| autocommit=1, REPEATABLE READ | Two separate transactions | 1000 | 1200 |
| autocommit=1, READ COMMITTED | Two separate transactions | 1000 | 1200 |
| autocommit=0, REPEATABLE READ | One transaction | 1000 | 1000 |
| START TRANSACTION, REPEATABLE READ | One transaction | 1000 | 1000 |
| autocommit=0, READ COMMITTED | One transaction | 1000 | 1200 |

This table assumes both reads are ordinary consistent reads, B committed before the second read, and no other changes occurred.

With autocommit=1, the difference between REPEATABLE READ and READ COMMITTED usually does not show across two standalone SELECTs, because each SELECT is already in its own transaction. The clearest difference appears when multiple SELECTs are inside the same transaction.

## 7. The Four Isolation Levels and the Role of autocommit

### 7.1. READ UNCOMMITTED

At this level, consistent reads can read uncommitted changes from other transactions. This is a dirty read.

Autocommit does not eliminate dirty reads. If a SELECT runs with READ UNCOMMITTED while another transaction is updating without having committed, it can observe the uncommitted value. When the other transaction ROLLBACKs, the observed value no longer exists.

Do not use READ UNCOMMITTED for balances, inventory, payments, or data requiring high reliability solely to reduce lock waits.

### 7.2. READ COMMITTED

Each consistent read takes a fresh snapshot at the start of the statement. In a multi-statement transaction, a later read can see new commits from other transactions.

Autocommit=1 also creates a new snapshot for each SELECT, but that is because each statement belongs to a separate transaction. With READ COMMITTED, a fresh snapshot is taken for each consistent read even when multiple SELECTs are in one transaction.

### 7.3. REPEATABLE READ

This is InnoDB's common default level. Consistent reads in the same transaction share the same read view, creating stable repeatable read behavior.

When autocommit=1 and each SELECT is a separate transaction, repeatability does not span across two standalone SELECTs. Use START TRANSACTION or autocommit=0 when the same snapshot is needed across multiple read statements.

### 7.4. SERIALIZABLE

SERIALIZABLE applies stricter rules and can increase locking/waiting.

In InnoDB, when a multi-statement transaction is open (autocommit disabled or START TRANSACTION executed), an ordinary SELECT under SERIALIZABLE is treated as a shared-lock locking read according to engine rules. When autocommit=1, a standalone SELECT is a single-statement transaction and can be handled as a consistent read.

Do not choose SERIALIZABLE just to "be safer" without evaluating lock contention. It can reduce concurrency and increase deadlocks or lock waits.

## 8. Consistent Read and Locking Read Are Not the Same

The effect of autocommit is also reflected in lock lifetime.

### 8.1. Ordinary Consistent Read

~~~sql
SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

With InnoDB at READ COMMITTED or REPEATABLE READ, this is typically a consistent nonlocking read. It reads the version matching the read view and does not place row locks solely for reading.

### 8.2. Locking Read with FOR UPDATE

~~~sql
START TRANSACTION;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1
FOR UPDATE;

-- Perform checks and updates based on the locked row.

COMMIT;
~~~

FOR UPDATE is a locking read. InnoDB acquires the locks needed to protect the read row until the transaction ends.

If you run a SELECT FOR UPDATE with autocommit=1 without opening an explicit transaction, there is no long-lived transaction to hold the lock for a subsequent statement. To have locks protect a read-then-write sequence, use START TRANSACTION or autocommit=0.

### 8.3. FOR SHARE

~~~sql
START TRANSACTION;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1
FOR SHARE;

COMMIT;
~~~

FOR SHARE acquires a shared lock per InnoDB rules. Other transactions can still perform compatible reads, but write operations needing conflicting locks may have to wait.

Use a locking read when business logic needs to check data and hold a lock before executing the next operation. Do not replace every SELECT with FOR UPDATE because doing so creates unnecessary contention.

### 8.4. Locking Reads Are Current Reads

Locking reads and UPDATE/DELETE operations are current reads, distinct from ordinary consistent snapshot reads. They read the current version per InnoDB's locking rules rather than merely reading an old read view.

Therefore, in a REPEATABLE READ transaction, a plain SELECT can see an old snapshot while SELECT ... FOR UPDATE can see the current state and lock the row. Do not mix the two read modes without understanding the difference.

## 9. Impact of autocommit on Multi-Step Operations

### 9.1. Money Transfers Need Explicit Transactions

Example transferring 100 from account 1 to account 2:

~~~sql
UPDATE account_mvcc_demo
SET balance = balance - 100
WHERE account_id = 1;

UPDATE account_mvcc_demo
SET balance = balance + 100
WHERE account_id = 2;
~~~

If autocommit=1 and the two UPDATEs are separate statements, the first UPDATE can commit before the second UPDATE runs. If the second statement fails, the amount deducted from account 1 remains saved.

Safe approach:

~~~sql
START TRANSACTION;

UPDATE account_mvcc_demo
SET balance = balance - 100
WHERE account_id = 1;

UPDATE account_mvcc_demo
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

If a step fails, the application ROLLBACKs so both changes are undone together. You must check affected row counts and enforce non-negative balance rules per business requirements.

### 9.2. Autocommit=0 Can Keep Transactions Open Too Long

Disabling autocommit does not automatically make an application safer. If you forget COMMIT or ROLLBACK:
- The transaction can hold row locks for a long time.
- Consistent read views can retain needed undo versions, slowing purge.
- The connection sits idle while the transaction remains open.
- Other transactions can be blocked or deadlock risk can increase.
- Metadata locks from statements that accessed tables can persist longer than desired.

Therefore, for web applications, it is usually better to keep default autocommit and open explicit transactions scoped to the business unit. Disabling autocommit at the session level is only suitable when the application actively manages transactions and always guarantees transaction termination.

### 9.3. One Long SELECT vs. Multiple Short SELECTs

A single SELECT statement with autocommit=1 has one read view for the entire statement. If data is updated while the SELECT is running, the consistent read still uses that statement's snapshot.

Conversely, multiple standalone SELECTs with autocommit=1 create multiple transactions and multiple read views. Aggregated results across multiple statements may not represent the same point in time.

## 10. Configuring Isolation Level at the Right Scope

MySQL supports setting isolation levels at different scopes.

### 10.1. Checking Current State

~~~sql
SELECT
    @@session.autocommit,
    @@session.transaction_isolation,
    @@global.transaction_isolation;
~~~

- SESSION is the configuration of the current connection.
- GLOBAL is the default applied to new connections; it does not automatically alter already open session configurations.

### 10.2. Setting Isolation Level for a Session

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
~~~

This setting applies to subsequent transactions in the session. It does not change the isolation level of an already running transaction.

### 10.3. Setting Isolation Level for the Next Transaction

~~~sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

START TRANSACTION;

-- Statements in this transaction use READ COMMITTED.

COMMIT;
~~~

Without SESSION/GLOBAL, SET TRANSACTION applies to the next transaction of the session. After that transaction, the session returns to its current default isolation level.

### 10.4. Setting the Server-Wide Default

~~~sql
SET GLOBAL TRANSACTION ISOLATION LEVEL READ COMMITTED;
~~~

GLOBAL configuration affects new sessions; existing sessions retain their session values. This operation requires appropriate administrative privileges and does not necessarily persist across restarts unless a persistent configuration mechanism is used.

Do not change GLOBAL just to test a query. In application environments, prefer configuring at the session or transaction scope to avoid affecting other connections.

## 11. SET autocommit and Transaction Boundaries

### 11.1. Switching from 1 to 0

~~~sql
SET autocommit = 0;
~~~

This statement disables automatic commits for subsequent statements in the session. It is not a way to open a nested sub-transaction and does not immediately create a consistent read snapshot.

### 11.2. Switching from 0 to 1

~~~sql
SET autocommit = 1;
~~~

If a transaction is active, switching autocommit from 0 to 1 commits that transaction. This is a data-impacting operation, not merely a configuration change.

Before re-enabling autocommit, explicitly decide whether the open transaction should COMMIT or ROLLBACK. Do not let a configuration statement accidentally commit unconfirmed data.

### 11.3. START TRANSACTION When autocommit=0

MySQL does not support nested transactions. Calling START TRANSACTION while another transaction is active ends the current transaction before starting a new one. Use SAVEPOINT to create rollback points within the same transaction, not nested START TRANSACTION calls.

### 11.4. DDL and Implicit Commit

Many DDL statements such as ALTER TABLE, CREATE TABLE, DROP TABLE, and TRUNCATE TABLE cause an implicit commit. If autocommit=0, DDL can still end an active transaction. Do not rely on ROLLBACK to undo DDL that has already succeeded.

## 12. Autocommit in JDBC and Connection Pools

JDBC typically creates a Connection with autocommit enabled per the driver's default configuration. Applications can check:

~~~java
boolean autoCommit = connection.getAutoCommit();
int isolation = connection.getTransactionIsolation();
~~~

To execute a multi-statement transaction:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setTransactionIsolation(
        Connection.TRANSACTION_REPEATABLE_READ
    );
    connection.setAutoCommit(false);

    try {
        // SQL statements within the same transaction.
        debitAccount(connection, fromAccountId, amount);
        creditAccount(connection, toAccountId, amount);

        connection.commit();
    } catch (SQLException ex) {
        connection.rollback();
        throw ex;
    }
}
~~~

This example only illustrates the structure. In production code, you must:
- Check updated row counts and business conditions.
- Roll back when any step fails.
- Ensure exceptions during rollback do not suppress the original error.
- Not hold connections longer than the required transaction scope.

### 12.1. Restoring Connection State

Connection pools reuse physical connections. If one request alters autocommit or isolation level without restoring it, a subsequent request may receive a connection with an unexpected state, depending on how the pool resets connections.

Explicit management pattern:

~~~java
try (Connection connection = dataSource.getConnection()) {
    boolean originalAutoCommit = connection.getAutoCommit();
    int originalIsolation = connection.getTransactionIsolation();

    try {
        connection.setTransactionIsolation(
            Connection.TRANSACTION_REPEATABLE_READ
        );
        connection.setAutoCommit(false);

        // Perform operations belonging to one transaction.
        performBusinessOperation(connection);

        connection.commit();
    } catch (Exception ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    } finally {
        // Only restore after the transaction has committed/rolled back.
        connection.setAutoCommit(originalAutoCommit);
        connection.setTransactionIsolation(originalIsolation);
    }
}
~~~

If `originalAutoCommit=true`, calling setAutoCommit(true) while a transaction is still open can commit the transaction. Therefore, always commit or roll back before restoring autocommit. In systems using pools, verify whether the pool resets state automatically and follow a consistent convention.

### 12.2. Setting Isolation Before Starting a Transaction

JDBC:

~~~java
connection.setTransactionIsolation(
    Connection.TRANSACTION_READ_COMMITTED
);
connection.setAutoCommit(false);
~~~

Setting isolation before the transaction starts avoids changing configuration mid-transaction. Do not change the isolation level in the middle of a read/write flow assuming the current snapshot is recreated.

## 13. Commonly Misinterpreted Observation Scenarios

### 13.1. REPEATABLE READ Yet Two SELECTs Still Differ

Cause: the two SELECTs belong to two different transactions because autocommit=1.

How to handle: use START TRANSACTION if you need the same read view across multiple read statements.

### 13.2. READ COMMITTED Yet the Transaction Remains Open

READ COMMITTED does not automatically commit the transaction after each SELECT. With autocommit=0 or an explicit transaction, the transaction remains open until COMMIT/ROLLBACK; only the read view is refreshed for each consistent read.

### 13.3. REPEATABLE READ Yet SELECT FOR UPDATE Sees a Different Value

An ordinary SELECT can be a consistent read using an older snapshot; SELECT FOR UPDATE is a locking/current read. The two read modes have different semantics.

### 13.4. Autocommit=0 Yet Reads Do Not See New Commits

If the transaction has already created a read view under REPEATABLE READ, subsequent consistent reads continue using that snapshot. COMMIT or ROLLBACK to end the transaction, then read again in a new transaction.

### 13.5. Autocommit=1 Yet Two UPDATEs Are Not Atomic

Each UPDATE is a separate transaction. Use START TRANSACTION to group both changes into a single atomic unit.

## 14. Decision Table by Need

| Need | Appropriate Configuration/Design |
|---|---|
| Each statement is independent, no multi-step transaction needed | autocommit=1 |
| Multiple SELECTs need the same snapshot | START TRANSACTION + REPEATABLE READ |
| Each SELECT in a transaction needs to see new commits | READ COMMITTED |
| Money transfer or multi-table update must succeed together | START TRANSACTION, COMMIT/ROLLBACK |
| Read a row then update based on the value just read | Transaction + appropriate SELECT ... FOR UPDATE |
| Protect data from dirty reads | Do not use READ UNCOMMITTED |
| Need a different isolation level for just one transaction | SET TRANSACTION before the transaction |
| Application uses a connection pool | Manage and reset autocommit/isolation explicitly |

There is no single best configuration for every application. Choose isolation levels and transaction boundaries based on consistency requirements, concurrency level, transaction duration, and locking overhead.

## 15. Observing Open Transaction State

When autocommit=0, a session can hold a transaction open for a long time without the application realizing it. You can inspect InnoDB transactions:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_mysql_thread_id,
    trx_isolation_level,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Find connections by thread ID:

~~~sql
SHOW PROCESSLIST;
~~~

Signs to watch for:
- Transactions with very old start times.
- Idle transactions that have not committed.
- Queries holding locks or waiting on locks.
- An old read view persisting for a long time, hindering undo history purge.

Not every long transaction is wrong; a report needing a consistent snapshot may run for a while. However, bound its duration, row count, and resources so it does not impact the system.

## 16. Diagnostic Workflow When Read Results Differ from Expectations

When two SELECT statements return different results, check in order:

1. Did both SELECTs run on the same connection?
2. Is `@@session.autocommit` 0 or 1?
3. Is an explicit transaction open?
4. What is the session's isolation level?
5. Are the two SELECTs ordinary consistent reads or locking reads?
6. At what time did the other transaction COMMIT?
7. On which consistent read was the read view created?
8. Did any DDL or implicit-commit statement run in between?
9. Was the isolation level changed for the next transaction or session?
10. Did the connection pool return a connection with leftover session state?

Quick inspection queries:

~~~sql
SELECT
    CONNECTION_ID() AS connection_id,
    @@session.autocommit AS autocommit,
    @@session.transaction_isolation AS isolation_level,
    @@session.in_transaction AS in_transaction;
~~~

`@@session.in_transaction` indicates whether the session is currently inside a transaction on MySQL versions that support this variable. If your target version does not support it, check state via administrative tools and `information_schema.innodb_trx`.

## 17. Two-Session Practice Exercises

The following exercises use the `account_mvcc_demo` table from section 3. Run in a test environment and reset the balance after each exercise so results are easy to compare.

### Exercise 1: Autocommit=1 and REPEATABLE READ

Session A:
~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SET autocommit = 1;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Session B:
~~~sql
UPDATE account_mvcc_demo
SET balance = balance + 100
WHERE account_id = 1;
~~~

Session A runs SELECT again. Note why the second read sees the change.

### Exercise 2: Autocommit=1 with an Explicit Transaction

Session A:
~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SET autocommit = 1;
START TRANSACTION;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Session B updates and commits. Session A reads again before COMMIT. Compare the result with Exercise 1. Then COMMIT and SELECT again.

### Exercise 3: Autocommit=0

Session A:
~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SET autocommit = 0;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Session B updates and commits. Session A reads again, then COMMITs and reads once more. Identify when the snapshot changed.

### Exercise 4: READ COMMITTED

Session A:
~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;
~~~

Session B updates and commits. Session A reads again inside the same transaction. Explain why the second read can see the new value.

### Exercise 5: Consistent Read vs. Locking Read

Session A:
~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1;

SELECT balance
FROM account_mvcc_demo
WHERE account_id = 1
FOR UPDATE;
~~~

While A keeps its transaction open, Session B tries to UPDATE the same row. Observe the read values and lock wait time. After the exercise, COMMIT or ROLLBACK both sessions.

### Exercise 6: Switching autocommit from 0 to 1

Session A:
~~~sql
SET autocommit = 0;

UPDATE account_mvcc_demo
SET balance = balance + 50
WHERE account_id = 1;

SET autocommit = 1;
~~~

Session B reads balance. Confirm the change was committed when autocommit switched from 0 to 1.

### Exercise 7: Multi-SELECT Reports

Have transaction B update two groups of data and commit between Session A's two SELECTs. Compare:
- Two separate SELECTs with autocommit=1.
- Two SELECTs inside one REPEATABLE READ transaction.
- Two SELECTs inside one READ COMMITTED transaction.

Record which option is needed when a report must be consistent at a single snapshot.

## 18. Pre-Deployment Checklist

- [ ] Distinguished autocommit from transaction isolation level.
- [ ] Understood that autocommit=1 causes each standalone statement to commit automatically.
- [ ] Understood that START TRANSACTION still creates a multi-statement transaction when autocommit=1.
- [ ] Understood that autocommit=0 keeps a transaction open until COMMIT/ROLLBACK.
- [ ] Understood that a REPEATABLE READ snapshot is created at the first consistent read.
- [ ] Distinguished REPEATABLE READ from READ COMMITTED within the same transaction.
- [ ] Distinguished consistent reads from locking/current reads.
- [ ] Understood that FOR UPDATE/FOR SHARE need an appropriate transaction to hold locks across multiple statements.
- [ ] Avoided using SERIALIZABLE without evaluating lock contention.
- [ ] Knew how to set isolation level at SESSION scope or for the next transaction.
- [ ] Understood that switching autocommit from 0 to 1 can commit an open transaction.
- [ ] Avoided long transactions when autocommit=0.
- [ ] Used explicit transactions for multi-step operations requiring atomicity.
- [ ] Managed connection state in JDBC and connection pools.
- [ ] Tested with two sessions on InnoDB and the exact MySQL version.
- [ ] Monitored open transactions and long-lived read views during operational diagnostics.

## 19. Conclusion

Autocommit and isolation level govern two different aspects of transactions. Autocommit defines transaction boundaries; isolation level defines how transactions see data and coordinate locks. Therefore, REPEATABLE READ does not guarantee two standalone SELECTs always see the same data when autocommit=1: each SELECT is a new transaction with its own read view.

If you need multiple read statements to share a snapshot, use an explicit transaction or autocommit=0 with clear COMMIT/ROLLBACK management. If using READ COMMITTED, each consistent read can see new commits even within an open transaction. When you need to read and then write based on the same row, consider a locking read inside a transaction. Finally, manage connection pools carefully because autocommit and isolation are per-session states; an unreset connection can cause subsequent requests to observe unexpected data.

## Official References

- [MySQL 8.4 Reference Manual – InnoDB Autocommit, Commit, and Rollback](https://dev.mysql.com/doc/refman/8.4/en/innodb-autocommit-commit-rollback.html)
- [MySQL 8.4 Reference Manual – SET TRANSACTION Statement](https://dev.mysql.com/doc/refman/8.4/en/set-transaction.html)
- [MySQL 8.4 Reference Manual – InnoDB Transaction Isolation Levels](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html)
- [MySQL 8.4 Reference Manual – Consistent Nonlocking Reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-consistent-read.html)
- [MySQL 8.4 Reference Manual – Locking Reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking-reads.html)
- [MySQL 8.4 Reference Manual – InnoDB Multi-Versioning](https://dev.mysql.com/doc/refman/8.4/en/innodb-multi-versioning.html)
- [MySQL 8.4 Reference Manual – InnoDB Transaction Model](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-model.html)
- [MySQL 8.4 Reference Manual – System Variable autocommit](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html#sysvar_autocommit)
- [MySQL 8.4 Reference Manual – Transaction Isolation System Variables](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html#sysvar_transaction_isolation)
