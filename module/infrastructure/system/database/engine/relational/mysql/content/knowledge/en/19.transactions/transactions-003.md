# autocommit and Per-Connection Transaction Boundaries

MySQL runs with `autocommit = 1` by default. That means each standalone SQL statement is executed as its own transaction and committed when the statement succeeds. This is convenient for single operations, but if a business workflow consists of multiple statements that must succeed or fail together, the application must open an explicit transaction with `START TRANSACTION` (or the equivalent JDBC API), and end it with `COMMIT` or `ROLLBACK`.

`autocommit` and transaction states belong to each individual connection/session. Two connections to the same MySQL server can have different autocommit modes and be in different transactions. A `COMMIT` on connection A does not commit changes on connection B; nor does a single transaction automatically span multiple connections just because they belong to the same request or connection pool.

This lesson belongs to the `DATABASE_MYSQL` module, focusing on table design, data types, keys, SQL queries, indexes, transactions, concurrency control, reading execution plans, and relational database operations. The goal is to define accurate transaction boundaries in SQL and JDBC, avoid unintended commits, keep transactions short, and manage connection state safely when using a pool.

After this lesson, you will be able to:

- Explain `autocommit = 1` and `autocommit = 0` at the session level.
- Distinguish automatic per-statement transactions from multi-statement transactions.
- Use `START TRANSACTION`, `COMMIT`, and `ROLLBACK` with proper boundaries.
- Understand the difference between `SET SESSION autocommit` and `SET GLOBAL autocommit`.
- Recognize statements that cause an implicit commit and important exceptions.
- Understand why a transaction cannot be shared across two connections.
- Map transactions to JDBC and manage connection pools safely.
- Recognize the limits of rollback with storage engines that do not support transactions.

## 1. Transactions and autocommit

A transaction is a group of database operations treated as a single unit of work. With InnoDB tables, a transaction allows committing all changes or rolling back uncommitted changes. `autocommit` determines whether MySQL automatically ends a transaction after each statement or lets the session keep the transaction open until the client requests otherwise.

Check the current mode:

```sql
SELECT
    CONNECTION_ID() AS connection_id,
    @@session.autocommit AS session_autocommit,
    @@global.autocommit AS global_autocommit;
```

In MySQL, `autocommit` is a system variable with `GLOBAL` and `SESSION` scopes. The default value is typically `1`.

| Value | Meaning |
| --- | --- |
| `autocommit = 1` | Each statement not inside an explicit transaction is automatically committed upon success |
| `autocommit = 0` | The session operates in continuous transaction mode; transactional statements are grouped into the current transaction until `COMMIT` or `ROLLBACK` |

`autocommit` is a connection configuration, not a property of a table or an individual SQL statement. `@@session.autocommit` is the value currently used by the session; `@@global.autocommit` is the default value applied to new connections.

## 2. autocommit = 1: Every Statement Is a Transaction

With the default mode:

```sql
SET SESSION autocommit = 1;

UPDATE accounts_demo
SET balance = balance - 100.00
WHERE account_id = 1;

UPDATE accounts_demo
SET balance = balance + 100.00
WHERE account_id = 2;
```

The two `UPDATE` statements are two separate transactions. If the first succeeds and the second fails, the first statement's change has already been committed and cannot be undone by a subsequent `ROLLBACK`.

This suits independent operations such as changing a single attribute, writing a log record, or updating a value that does not depend on the next statement. It is insufficient for business operations requiring multiple actions to succeed together, such as transferring money between two accounts.

A successful DML statement on an InnoDB table is automatically committed upon completion if the session is in `autocommit = 1` and no explicit transaction wraps it. If the statement fails, MySQL/InnoDB handles the error at the statement level; no successful changes from that statement are committed as a completed operation.

## 3. Explicit Transactions with START TRANSACTION

To group multiple statements into a single unit of work, use:

```sql
START TRANSACTION;

-- Statements belonging to the same transaction
UPDATE ...;
INSERT ...;
DELETE ...;

COMMIT;
```

`BEGIN` or `BEGIN WORK` can also start a transaction. `START TRANSACTION` is usually clearer when reading SQL code.

- `START TRANSACTION` begins an explicit transaction on the current connection.
- `COMMIT` confirms transactional changes in the current transaction.
- `ROLLBACK` discards uncommitted transactional changes in the current transaction.

While an explicit transaction is open, `autocommit` may remain `1`; statements between `START TRANSACTION` and `COMMIT`/`ROLLBACK` still belong to the same transaction. After the transaction ends, the session returns to its configured autocommit behavior.

### 3.1. Atomic Money Transfer Example

Create the table and initial data before opening a transaction:

```sql
DROP TABLE IF EXISTS accounts_demo;

CREATE TABLE accounts_demo (
    account_id BIGINT UNSIGNED NOT NULL,
    owner_name VARCHAR(100) NOT NULL,
    balance DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (account_id),
    CONSTRAINT chk_accounts_demo_balance CHECK (balance >= 0)
) ENGINE = InnoDB;

INSERT INTO accounts_demo (account_id, owner_name, balance) VALUES
(1, 'An', 1000.00),
(2, 'Binh', 500.00);
```

Transfer 100.00 from account 1 to account 2:

```sql
START TRANSACTION;

UPDATE accounts_demo
SET balance = balance - 100.00
WHERE account_id = 1
  AND balance >= 100.00;

UPDATE accounts_demo
SET balance = balance + 100.00
WHERE account_id = 2;

COMMIT;
```

Both changes belong to the same transaction. If the application verifies both operations are valid and commits, the final balances are 900.00 and 600.00. If an error requires aborting before commit, run `ROLLBACK` on the same connection.

In a real application, you must not rely solely on the SQL statement not throwing an exception. Check the update count of each statement; for example, the debit statement must update exactly one row. If the account does not exist or has insufficient funds, the application must roll back instead of proceeding to credit the receiving account.

Example application-level control flow:

```text
START TRANSACTION
       |
       v
Debit source account
       |
       v
Exactly one row updated?
    /       \
   No       Yes
   |         |
ROLLBACK     v
          Credit destination account
                 |
                 v
          Exactly one row updated?
              /       \
             No       Yes
             |         |
          ROLLBACK   COMMIT
```

This is illustrative business logic. In a high-concurrency system, you must also handle deadlocks, bounded retries, and idempotency of the transfer request.

### 3.2. Verifying Rollback

```sql
START TRANSACTION;

UPDATE accounts_demo
SET balance = balance - 50.00
WHERE account_id = 1;

SELECT account_id, balance
FROM accounts_demo
ORDER BY account_id;

ROLLBACK;

SELECT account_id, balance
FROM accounts_demo
ORDER BY account_id;
```

On the same connection, `SELECT` before `ROLLBACK` sees the transaction's own uncommitted changes. After `ROLLBACK`, the balance reverts to the value committed before the transaction. Another connection does not see those uncommitted changes due to InnoDB's consistent read mechanism.

## 4. autocommit = 0: Session Maintains Transaction

You can disable autocommit for the current connection:

```sql
SET SESSION autocommit = 0;
SELECT @@session.autocommit;
```

When disabled, transactional statements do not auto-commit after each statement. A transaction starts implicitly when the session executes a transactional operation and continues until the client runs `COMMIT` or `ROLLBACK`.

```sql
SET SESSION autocommit = 0;

UPDATE accounts_demo
SET balance = balance - 25.00
WHERE account_id = 1;

UPDATE accounts_demo
SET balance = balance + 25.00
WHERE account_id = 2;

COMMIT;
```

`COMMIT` ends the current transaction but does not automatically reset `autocommit` to 1. The session stays in `autocommit = 0` mode; the next transaction will start implicitly when the session executes the next transactional statement.

To re-enable default mode:

```sql
SET SESSION autocommit = 1;
```

If you switch from `autocommit = 0` to `autocommit = 1` while a transaction is open, MySQL commits the current transaction. This is an implicit commit; do not use this command as a way to "clean up state" unless you have explicitly decided to keep the changes.

### 4.1. Do Not Arbitrarily Mix SET autocommit=0 and START TRANSACTION

`START TRANSACTION` starts a new transaction and commits any previously open transaction. Therefore, if a session is in `autocommit = 0`, has uncommitted changes, and then runs `START TRANSACTION`, those earlier changes may be committed unexpectedly.

Choose one clear model:

- Use `autocommit = 1` and open each multi-statement transaction with `START TRANSACTION`/`COMMIT`/`ROLLBACK`.
- Or use `autocommit = 0` for strictly managed sessions, always ending transactions and restoring state before returning the connection.

For web applications and connection pools, the first model is usually easier to control because transaction boundaries are explicit in each unit of work.

## 5. Transaction Boundaries Belong to Each Connection

Each connection to MySQL has its own session, including:

- Its `@@session.autocommit` value.
- Its open transaction and uncommitted changes.
- Its session transaction isolation level.
- Session variables, temporary tables, and certain other states.

Example verifying two connections:

**Connection A:**

```sql
SELECT CONNECTION_ID(), @@session.autocommit;
START TRANSACTION;
UPDATE accounts_demo
SET balance = balance - 10.00
WHERE account_id = 1;
```

**Connection B:**

```sql
SELECT CONNECTION_ID(), @@session.autocommit;
SELECT account_id, balance
FROM accounts_demo
WHERE account_id = 1;
```

Connection B has its own transaction and autocommit state. With InnoDB, B does not see A's uncommitted update in a regular consistent read; it reads the committed version according to B's isolation/snapshot. If A runs `COMMIT`, subsequent appropriate reads by B can see the new balance.

`COMMIT` in connection B cannot commit A's transaction. `ROLLBACK` in B also cannot undo A's changes. A transaction is not scoped by logged-in user, application thread, HTTP request, or database name; it is managed on a specific physical connection/session.

### 5.1. One Business Operation Must Use the Same Connection

If a business operation consists of three repository calls requiring the same transaction, all three calls must use the same connection participating in that transaction. If each repository independently obtains a connection from the pool, they may run in three separate transactions even if called inside the same Java method.

In a transaction-aware framework like Spring, the transaction manager typically binds the datasource connection to the current execution context. Repositories must use the same datasource and a connection-acquisition mechanism compatible with the transaction manager to participate in that transaction.

Do not pass a connection with an active transaction to another thread or use it concurrently from multiple threads. JDBC `Connection` is not designed for arbitrary concurrent transaction manipulation across threads.

## 6. SESSION and GLOBAL autocommit

Check both scopes:

```sql
SELECT @@session.autocommit, @@global.autocommit;
```

Set for the current connection:

```sql
SET SESSION autocommit = 0;
-- Or the short form in the current session:
SET autocommit = 1;
```

Set the default value for new connections:

```sql
SET GLOBAL autocommit = 1;
```

`SET GLOBAL` requires appropriate administrative privileges and does not alter the session value of existing connections. Newly created connections inherit the global value at connection time unless overridden by client or application configuration.

| Operation | Effect |
| --- | --- |
| `SET SESSION autocommit = 0` | Only changes the current connection |
| `SET SESSION autocommit = 1` | Only changes the current connection; switching 0 → 1 commits an open transaction |
| `SET GLOBAL autocommit = 0` | Changes the default for new connections; does not change running sessions |
| `SET GLOBAL autocommit = 1` | Changes the default for new connections; does not change running sessions |

Do not change global autocommit to fix a local application bug. Identify which connection is misconfigured and fix it properly in the connection pool or session initialization.

## 7. COMMIT, ROLLBACK, and Savepoints

### 7.1. COMMIT

`COMMIT` confirms transactional changes in the current transaction. After commit, changes become committed data and transaction locks are released according to InnoDB rules.

```sql
START TRANSACTION;
UPDATE inventory SET quantity = quantity - 1 WHERE product_id = 100;
INSERT INTO inventory_events (product_id, event_type) VALUES (100, 'SALE');
COMMIT;
```

Both changes belong to the same transaction if both tables use a transaction-capable storage engine and the statements succeed.

### 7.2. ROLLBACK

`ROLLBACK` discards uncommitted transactional changes of the current transaction:

```sql
START TRANSACTION;
UPDATE inventory SET quantity = quantity - 1 WHERE product_id = 100;
ROLLBACK;
```

Rollback does not undo previously committed data. If the session is in `autocommit = 1` and the previous statement already auto-committed, a subsequent `ROLLBACK` cannot reverse that statement.

### 7.3. SAVEPOINT and ROLLBACK TO SAVEPOINT

A savepoint marks a position inside a transaction, allowing partial rollback of changes made after that marker:

```sql
START TRANSACTION;

UPDATE accounts_demo
SET balance = balance - 20.00
WHERE account_id = 1;

SAVEPOINT after_debit;

UPDATE accounts_demo
SET balance = balance + 20.00
WHERE account_id = 2;

-- If the step after the savepoint needs to be canceled:
ROLLBACK TO SAVEPOINT after_debit;

-- Can continue other operations and then commit or roll back everything.
COMMIT;
```

`ROLLBACK TO SAVEPOINT` only discards changes after the savepoint; the transaction remains open. `RELEASE SAVEPOINT` removes the marker; `COMMIT` or a full-transaction `ROLLBACK` also removes savepoints.

A savepoint is not a nested transaction. You cannot use a savepoint to commit a part independently from the outer transaction.

## 8. Implicit Commit: Statements That Can End a Transaction Unexpectedly

Not every SQL statement stays inside a transaction in a rollbackable way. MySQL has statements that cause an implicit commit, meaning they commit the current transaction before executing that statement.

Common groups include:

- DDL such as `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`, `RENAME TABLE`, `TRUNCATE TABLE`.
- Certain administrative or account-management statements such as `CREATE USER`, `ALTER USER`, `GRANT`, `REVOKE`.
- `START TRANSACTION` when a previous transaction is still open.
- `SET autocommit = 1` when switching from 0 to 1.
- Certain table-locking and other administrative statements per MySQL rules.

Dangerous example:

```sql
START TRANSACTION;

UPDATE accounts_demo
SET balance = balance - 100.00
WHERE account_id = 1;

ALTER TABLE accounts_demo
ADD COLUMN note VARCHAR(100) NULL;

ROLLBACK;
```

`ALTER TABLE` causes an implicit commit. Therefore, the earlier balance change may already have been committed before the DDL ran; the final `ROLLBACK` cannot undo it.

### 8.1. The Temporary Table Exception

`CREATE TEMPORARY TABLE` and `DROP TEMPORARY TABLE` do not trigger an implicit commit like regular DDL. However, creating or dropping a temporary table is not rolled back: if the transaction rolls back, the temporary table remains created or dropped depending on the operation executed.

Other DDL on temporary tables, such as `ALTER TABLE`, may still trigger an implicit commit under corresponding rules. Do not assume every operation on a temporary table is safe inside a transaction.

### 8.2. Atomic DDL Does Not Mean DDL Is Transactional

MySQL 8.0 has atomic DDL for many supported DDL operations: metadata and data dictionary changes of the DDL itself are guaranteed to complete or recover as a unit on crash. That does not mean DDL participates in an application's DML transaction or can be canceled with `ROLLBACK` after the statement succeeds.

Run migrations/schema changes in a separate process outside business transactions that require full rollback.

## 9. Transactions Only Protect Transaction-Capable Storage Engines

InnoDB supports transactions, commit, rollback, and locking/consistent-read mechanisms. MyISAM does not support transactions the way InnoDB does.

If a transaction updates an InnoDB table and a MyISAM table, `ROLLBACK` can only undo the change in the InnoDB table; the change in MyISAM is not undone.

Check the engine:

```sql
SELECT
    TABLE_NAME,
    ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('accounts_demo', 'inventory');
```

For business operations requiring atomicity, all participating tables must use an appropriate transactional engine, typically InnoDB. Also note that external operations such as sending emails, calling payment APIs, or writing files are not automatically rolled back by a MySQL transaction; they need dedicated coordination patterns such as a transactional outbox or saga.

## 10. Transactions in JDBC

JDBC `Connection` defaults to auto-commit mode. To group multiple statements, call `setAutoCommit(false)`, perform the work on the same connection, and then call `commit()` or `rollback()`.

The following snippet is placed inside a method declaring `throws SQLException`:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        try (PreparedStatement debit = connection.prepareStatement(
                "UPDATE accounts_demo " +
                "SET balance = balance - ? " +
                "WHERE account_id = ? AND balance >= ?")) {
            debit.setBigDecimal(1, new BigDecimal("100.00"));
            debit.setLong(2, 1L);
            debit.setBigDecimal(3, new BigDecimal("100.00"));

            int debited = debit.executeUpdate();
            if (debited != 1) {
                throw new SQLException("Debit failed: account missing or insufficient balance");
            }
        }

        try (PreparedStatement credit = connection.prepareStatement(
                "UPDATE accounts_demo SET balance = balance + ? WHERE account_id = ?")) {
            credit.setBigDecimal(1, new BigDecimal("100.00"));
            credit.setLong(2, 2L);

            int credited = credit.executeUpdate();
            if (credited != 1) {
                throw new SQLException("Credit failed: destination account not found");
            }
        }

        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    }
}
```

The example uses `BigDecimal` for monetary amounts and checks the update count of each step. In real applications, you also need deadlock retries, logging, exception mapping, and handling cases where the commit outcome is indeterminate due to connection loss.

### 10.1. setAutoCommit(true) Can Commit the Current Transaction

According to JDBC, calling `setAutoCommit(true)` while a connection is in auto-commit false mode and has an open transaction makes the driver commit the current transaction. Therefore, do not call this method to "reset" the connection before deciding whether the transaction should be committed.

A safe cleanup order is usually:

1. If the operation fails before commit, call `rollback()`.
2. Restore connection state according to the pool/framework contract.
3. Close the logical connection to return it to the pool.

`commit()` or `rollback()` is only valid when the connection is in manual transaction mode in JDBC; calling them while auto-commit is enabled can throw `SQLException` depending on the driver.

### 10.2. Using try-with-resources Does Not Replace Rollback

`try-with-resources` guarantees closing the resource, but your code must still decide whether to commit or roll back. Do not assume `Connection.close()` always rolls back as the application expects, especially when `close()` on a pooled connection only returns the logical connection to the pool.

If uncommitted and the physical connection actually closes, MySQL rolls back the uncommitted InnoDB transaction. However, in a pool the physical connection stays alive; leftover transactions or session state can affect the next request if the pool does not reset properly. Always roll back explicitly on error and follow your transaction manager.

## 11. Connection Pools and Session State

A connection pool reuses physical connections to reduce connection-opening overhead. Because `autocommit` is session state, pool configuration and cleanup directly impact transaction boundaries.

Common risks:

- A request calls `setAutoCommit(false)` and returns the connection to the pool without committing/rolling back.
- A subsequent request receives a connection with `autocommit = 0` or an uncleaned transaction.
- A repository acquires a new connection on its own instead of using the connection managed by the transaction manager.
- Code calls `setAutoCommit(true)` while uncommitted changes remain and accidentally commits them.
- Session variables or isolation levels are modified and leak into the next checkout.

Principles:

- Let the pool manage default configuration; never arbitrarily change `GLOBAL autocommit` from business code.
- Start and end transactions within the same connection-management scope.
- Always commit on success or roll back on failure.
- Restore `autoCommit`, isolation level, read-only, and other session state if code modified them and the pool/framework does not handle it automatically.
- Use a transaction manager or transaction-aware connection acquisition API.
- Keep transactions short; do not wait for users, call external services, or perform long tasks while holding locks.

Some pools have mechanisms to reset state when a connection is returned. This is an extra safeguard, not a substitute for properly closing transactions in code.

## 12. Transaction Boundaries and Application Errors

### 12.1. A Failed Statement Does Not Always Roll Back the Entire Transaction

In an explicit transaction, a failed statement is usually rolled back at the statement level; the transaction itself may remain open. Do not assume every `SQLException` automatically rolls back the entire transaction. The application must decide to roll back the transaction when the business workflow cannot continue.

An important exception is a deadlock: InnoDB chooses one transaction as a victim and rolls back that transaction to resolve the deadlock. The application must retry the entire transaction under a bounded retry policy, not just the last statement.

A lock wait timeout usually rolls back only the statement that timed out by default, unless `innodb_rollback_on_timeout` changes that behavior. After a lock timeout error, the application should roll back the entire transaction if there is no explicit recovery logic.

### 12.2. Losing Connection During COMMIT

If the client loses connection right when sending `COMMIT`, the application may not know whether the server committed or not. You cannot conclude the transaction definitely rolled back merely because the client received a timeout or network error.

For operations that may be resent, design an idempotency key, unique transaction ID, or request tracking table to check the result before retrying. Never blindly retry a debit/credit operation, as doing so could apply it twice if the first commit succeeded.

### 12.3. Do Not Hold Transactions Too Long

Long transactions can hold row locks, increase contention, retain old read views, delay undo purge, and increase undo history size. Read/validate necessary data, open the transaction close to the write point, execute database operations quickly, and commit/roll back.

Do not open a transaction before user UI confirmation or before an HTTP call with unpredictable response times.

## 13. Commands and States to Remember

| Command | Main Effect | Notes |
| --- | --- | --- |
| `SET SESSION autocommit = 1` | Enables auto-commit for the current connection | Switching from 0 to 1 can commit an open transaction |
| `SET SESSION autocommit = 0` | Disables auto-commit for the current connection | Session must end transactions with COMMIT/ROLLBACK |
| `SET GLOBAL autocommit = 1` | Changes default for new connections | Does not change existing sessions |
| `START TRANSACTION` | Starts an explicit transaction | Commits any previously open transaction; does not support nested transactions |
| `COMMIT` | Commits the current transaction | Does not reset autocommit mode |
| `ROLLBACK` | Discards uncommitted changes | Cannot reverse committed changes or non-transactional engine operations |
| `SAVEPOINT name` | Creates a marker within a transaction | Not a nested transaction |
| `ROLLBACK TO SAVEPOINT name` | Discards changes after the marker | Transaction remains open |
| `RELEASE SAVEPOINT name` | Removes the marker | Does not commit the transaction |

Check session state:

```sql
SELECT
    CONNECTION_ID(),
    @@session.autocommit,
    @@session.transaction_isolation;
```

`@@session.transaction_isolation` shows the session's isolation level. The isolation level affects how transactions see data, but does not change the rule that transactions and autocommit belong to each individual connection.

## 14. Two-Session Verification Procedure

The following practice helps make transaction boundaries clear:

1. Open two connections A and B to the same schema.
2. On A, verify `@@session.autocommit = 1`, start a transaction, and update an account.
3. On A, read the row again to confirm the session sees its own change.
4. On B, read the same row; B only sees committed data according to B's isolation/snapshot.
5. On A, run `ROLLBACK`; verify B still sees the old value.
6. Repeat but replace `ROLLBACK` with `COMMIT`; perform an appropriate fresh read on B to see the committed value.
7. On A, set `autocommit = 0`; perform an update and read `CONNECTION_ID()` and `@@session.autocommit` on both A and B to confirm session state is not shared.
8. End the transaction on A and re-enable `autocommit = 1` before returning the connection if it is a reused connection.

Do not run test steps on production accounts or data. Use a separate InnoDB lab table and restore data after the exercise.

## 15. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking autocommit is a single server-wide setting | Misunderstanding state across connections | Check `@@session.autocommit` and `@@global.autocommit` |
| Running multiple DMLs with autocommit=1 and thinking they share a transaction | Earlier statement may commit even if a later one fails | Use `START TRANSACTION` for multi-step workflows |
| Forgetting COMMIT or ROLLBACK when autocommit=0 | Transactions/locks persist and affect reused connections | End transactions on every code path |
| Thinking COMMIT re-enables autocommit | Session stays in `autocommit=0` | Intentionally reset session state |
| Calling START TRANSACTION while an old transaction is open | Old transaction is implicitly committed | Do not assume nested transactions; use savepoints for internal markers |
| Running DDL inside a DML transaction | Implicit commit removes full rollback capability | Separate migrations from business transactions |
| Assuming ROLLBACK reverses every engine | MyISAM and external operations are not rolled back | Use InnoDB and design coordination for side effects |
| Each repository acquires its own connection | Operations are not in the same transaction | Share the connection managed by the transaction manager |
| Using setAutoCommit(true) for cleanup | Can commit undecided changes | Explicitly roll back or commit before switching modes |
| Blindly retrying when losing connection on COMMIT | May execute the business operation twice | Use idempotency and verify transaction status |

## 16. Practice Exercises

1. Check `@@session.autocommit` and `@@global.autocommit` on a new connection.
2. Run two `UPDATE` statements with `autocommit = 1`; intentionally make the second fail and verify the first committed.
3. Re-run inside `START TRANSACTION`; when the second fails, roll back and verify both changes are discarded.
4. Set `autocommit = 0`, perform an update, and `COMMIT`. Verify autocommit mode is still 0.
5. Switch from `autocommit = 0` to 1 while a transaction is open in a lab environment. Verify the implicit commit and explain the risk.
6. Open two connections. On A update without committing; on B read the same row. Then commit or roll back on A and observe again on B.
7. Create a savepoint, perform two updates, roll back to the savepoint, and commit the rest.
8. Try `ALTER TABLE` inside a DML transaction on a lab table. Observe why a subsequent rollback cannot undo the DML change before the DDL.
9. Compare rollback on an InnoDB table and a MyISAM table in a lab environment.
10. Write a JDBC transfer service using a single connection, checking update counts, committing on success, and rolling back on exception.
11. Simulate a connection pool: change autoCommit and return the connection; inspect the pool's reset mechanism and ensure the next request receives the right state.

## 17. Pre-Production Transaction Checklist

- [ ] Identified which statements must succeed/fail together.
- [ ] Verified `autocommit` on the executing connection.
- [ ] Multi-statement transactions have explicit `START TRANSACTION`/`setAutoCommit(false)`.
- [ ] Every success branch commits; every error branch rolls back.
- [ ] Participating tables use an appropriate transactional storage engine, typically InnoDB.
- [ ] No DDL or implicit-commit statements inside business transactions.
- [ ] All repositories in the same business operation share the connection managed by the transaction manager.
- [ ] Connection pool resets autocommit and session state per a verified contract.
- [ ] Transactions are kept short and exclude user/external service wait times.
- [ ] Deadlocks and lock timeouts are handled intentionally.
- [ ] Retries are bounded and operations are protected against duplication via idempotency when needed.
- [ ] Reconciliation mechanism exists when a client loses connection during commit.

## 18. Completion Criteria

You have completed this lesson when you can explain per-connection autocommit mode, distinguish a self-committing statement from a multi-statement transaction, properly use `START TRANSACTION`/`COMMIT`/`ROLLBACK`, recognize implicit commits and storage engine limits, and implement JDBC transactions on a single connection while returning pooled connections to a clean state. You must also be able to explain why transactions are not shared across two connections and how to handle commits interrupted by network errors.

## References

- [MySQL 8.4 Reference Manual — autocommit, Commit, and Rollback](https://dev.mysql.com/doc/refman/8.4/en/innodb-autocommit-commit-rollback.html)
- [MySQL 8.4 Reference Manual — Statements That Cause an Implicit Commit](https://dev.mysql.com/doc/refman/8.4/en/implicit-commit.html)
- [MySQL 8.4 Reference Manual — Transactional and Locking Statements](https://dev.mysql.com/doc/refman/8.4/en/sql-transactional-statements.html)
- [MySQL 8.4 Reference Manual — InnoDB and Transactions](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-model.html)
