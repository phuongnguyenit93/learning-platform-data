# START TRANSACTION, BEGIN, COMMIT, and ROLLBACK

## Objectives

After this lesson, you will be able to:

- Explain transactions and why multiple SQL statements must be grouped into a single unit of work.
- Start a transaction using `START TRANSACTION` or `BEGIN`.
- Use `COMMIT` to confirm changes and `ROLLBACK` to discard uncommitted changes.
- Distinguish explicit transactions from MySQL's default `autocommit` mode.
- Identify which operations can actually be rolled back based on the storage engine.
- Recognize statements that trigger an implicit commit and avoid breaking transaction boundaries.
- Use savepoints when partial rollback of work is needed.
- Properly manage transactions in Java JDBC and connection pools.
- Design data write workflows with error checking, locking, and recovery capability.

## 1. What Is a Transaction?

A transaction is a unit of work consisting of one or more SQL statements processed as a group. With tables using a transaction-capable storage engine such as InnoDB, the application can confirm all changes with `COMMIT` or discard uncommitted changes with `ROLLBACK`.

For example, transferring 500,000 VND from account A to account B requires at least two operations:

1. Deduct 500,000 VND from account A.
2. Add 500,000 VND to account B.

If deducting succeeds but adding fails, the data becomes incorrect. A transaction ensures the two changes are committed together or rolled back together, provided they are performed on transaction-capable tables within the same transaction.

### 1.1. Relation to ACID

Transactions in InnoDB support the ACID properties:

| Property | Meaning |
|---|---|
| Atomicity | Changes in a transaction are confirmed together or discarded upon rollback |
| Consistency | A transaction must move data from one valid state to another valid state according to applied constraints and business rules |
| Isolation | Concurrent transactions are controlled according to the isolation level and locking/consistent-read mechanisms |
| Durability | After a successful commit, changes are protected according to the server and storage durability configuration |

Transactions do not automatically guarantee every business rule. The application must still verify balances, ownership, order statuses, and other conditions. Database constraints should be used to protect rules that can be expressed in the schema.

## 2. Starting a Transaction with START TRANSACTION

`START TRANSACTION` begins an explicit transaction on the current connection.

Basic syntax:

```sql
START TRANSACTION;

-- One or more SQL statements
UPDATE accounts
SET balance = balance - 100000
WHERE account_id = 101;

UPDATE accounts
SET balance = balance + 100000
WHERE account_id = 202;

COMMIT;
```

Changes are executed within the transaction until a statement ends the transaction with `COMMIT` or `ROLLBACK`, or an implicit commit event occurs.

You can write:

```sql
START TRANSACTION;
```

This is a clear and common way to start a group of write operations.

### 2.1. BEGIN Is an Equivalent Syntax

In MySQL, `BEGIN` or `BEGIN WORK` can be used to start a transaction and is equivalent to `START TRANSACTION` in regular SQL contexts:

```sql
BEGIN;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 10;

COMMIT;
```

`START TRANSACTION` is usually easier to recognize when reading SQL code because it explicitly states the intent to start a transaction.

Note: inside stored programs, `BEGIN ... END` is also used to open/close a compound statement block. When writing a procedure, function, or trigger, distinguish block syntax from transaction control statements; do not mechanically replace every `BEGIN` with `START TRANSACTION`.

### 2.2. No Conventional Nested Transactions

MySQL does not support independent nested transactions. Calling `START TRANSACTION` while another transaction is open ends the current transaction with an implicit commit and then starts a new transaction. This can cause earlier changes to be committed unexpectedly.

Do not use `START TRANSACTION` inside a transaction thinking it creates a child transaction. If you need to undo part of the work, use `SAVEPOINT` and `ROLLBACK TO SAVEPOINT`.

## 3. COMMIT Confirms Changes

`COMMIT` ends the current transaction and confirms the transaction's changes.

```sql
START TRANSACTION;

UPDATE products
SET stock_quantity = stock_quantity - 2
WHERE product_id = 501;

INSERT INTO inventory_movements (
    product_id,
    quantity_change,
    movement_type,
    created_at
)
VALUES (
    501,
    -2,
    'SALE',
    CURRENT_TIMESTAMP
);

COMMIT;
```

If the statements succeed and `COMMIT` succeeds, the changes are confirmed. With InnoDB, the transaction ends and locks held by the transaction are released according to engine rules.

### 3.1. COMMIT Does Not Mean All Prior Operations Are Business-Valid

MySQL commits the valid changes executed within the transaction. It does not automatically know that a negative inventory quantity is wrong, that source and destination accounts must differ, or that an order must not be paid twice.

The application must verify the result of each operation before committing. If a business condition is not met, roll back.

### 3.2. Commit Is a Boundary That Cannot Be Undone by Regular ROLLBACK

After `COMMIT` succeeds, a subsequent `ROLLBACK` cannot cancel the committed transaction:

```sql
START TRANSACTION;
UPDATE accounts SET balance = balance - 100 WHERE account_id = 101;
COMMIT;

-- Cannot undo the changes committed above
ROLLBACK;
```

To reverse a committed business operation, the application must execute a compensating transaction, such as recording a new refund transaction. This is a new business change, not a rollback of the old transaction.

## 4. ROLLBACK Discards Uncommitted Changes

`ROLLBACK` ends the current transaction and discards uncommitted transactional changes.

```sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 500000
WHERE account_id = 101;

UPDATE accounts
SET balance = balance + 500000
WHERE account_id = 202;

-- Detected invalid destination account or failed business condition
ROLLBACK;
```

After rolling back, the InnoDB changes in this transaction are undone. Locks held by the transaction are also released.

### 4.1. ROLLBACK Does Not Erase Every Trace of Statements

Rollback does not mean everything in the system returns to its original state in every aspect:

- Changes on transactional tables such as InnoDB are undone.
- Changes on non-transactional tables such as MyISAM are not undone.
- Some counters or auto-generated values may not revert to old numbers; do not rely on IDs being contiguous.
- Effects outside MySQL such as sending emails, calling APIs, writing files, or publishing messages to other systems are not rolled back by a database transaction.
- Statements causing an implicit commit may have ended the transaction earlier.

Therefore, verify the storage engine of all participating tables and avoid placing external tasks in the middle of a group of changes that the application expects to roll back completely.

### 4.2. ROLLBACK on Error

Applications should follow this exception-handling principle: if a commit has not succeeded, roll back the transaction before returning the connection to the pool or ending processing.

Do not ignore rollback errors. If rollback fails because the connection was lost or the server is unreachable, the application must remove the connection from the pool and treat the outcome state as potentially indeterminate.

## 5. Autocommit in MySQL

### 5.1. Default autocommit = 1

MySQL usually starts with `autocommit` enabled:

```sql
SELECT @@SESSION.autocommit;
```

When `autocommit = 1`, each standalone SQL statement executes as its own transaction if the storage engine supports transactions. If the statement succeeds, changes are committed when the statement finishes; if the statement fails, transactional changes of that statement are discarded.

Example:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;
```

If no explicit transaction is open and autocommit is enabled, the UPDATE above auto-commits upon success. A subsequent UPDATE is a different transaction.

### 5.2. START TRANSACTION Creates an Explicit Transaction Even When Autocommit Is On

You do not need to disable autocommit to use transactions:

```sql
SELECT @@SESSION.autocommit; -- usually 1

START TRANSACTION;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 202;

COMMIT;
```

Both UPDATE statements belong to the same explicit transaction and are only confirmed upon commit. After the transaction ends, the session returns to its original autocommit mode.

This is usually the recommended approach for a business unit consisting of multiple SQL statements.

### 5.3. Disabling Autocommit at the Session Level

You can disable autocommit:

```sql
SET SESSION autocommit = 0;
```

When disabled, changes do not auto-commit after each statement. The application must explicitly call `COMMIT` or `ROLLBACK`. After a transaction ends, subsequent statements belong to a new transaction under the disabled autocommit mode.

Check and re-enable:

```sql
SELECT @@SESSION.autocommit;
SET SESSION autocommit = 1;
```

Switching `autocommit` from 0 to 1 commits any open transaction. Therefore, do not re-enable it arbitrarily while unconfirmed changes remain. Explicitly commit or roll back first.

### 5.4. Should You Use START TRANSACTION or autocommit = 0?

In applications, explicit transactions are usually easier to control:

- Start/end boundaries are clearly visible in code.
- A request can use a transaction for a single specific business operation.
- Reduces the risk of returning a connection to the pool with an open transaction still active.
- Avoids unintentionally keeping transactions open because session autocommit was disabled.

`autocommit = 0` may suit certain tools or interactive workflows, but requires strict session lifecycle management.

## 6. Storage Engine Determines Rollback Capability

A transaction is a capability of the storage engine, not merely an SQL keyword.

### 6.1. InnoDB Supports Transactions

InnoDB is MySQL's common default storage engine and supports:

- `START TRANSACTION`, `COMMIT`, `ROLLBACK`.
- Row-level locking and concurrency control mechanisms.
- Consistent reads and multiple isolation levels.
- Foreign keys and crash recovery.

Example checking the engine:

```sql
SHOW TABLE STATUS
WHERE Name IN ('accounts', 'inventory_movements');

SELECT
    TABLE_NAME,
    ENGINE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('accounts', 'inventory_movements');
```

All tables participating in a business operation must use a transaction-capable engine if you want to roll back all changes.

### 6.2. MyISAM Does Not Support Rollback

MyISAM does not support transactions the way InnoDB does. If a transaction updates an InnoDB table and then updates a MyISAM table, and subsequently rolls back:

- The InnoDB change is undone.
- The MyISAM change may remain.

This is why you must not mix transactional and non-transactional tables in a business operation that requires atomicity.

### 6.3. Check Engines Before Designing Transactions

```sql
SELECT
    TABLE_NAME,
    ENGINE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME;
```

Do not check only the main table. Check detail tables, history tables, balance tables, inventory tables, and every table written within the same transaction.

## 7. Full Example: Transferring Money Between Two Accounts

### 7.1. Illustrative Schema

```sql
CREATE TABLE accounts (
    account_id BIGINT UNSIGNED NOT NULL,
    owner_name VARCHAR(150) NOT NULL,
    balance DECIMAL(19,2) NOT NULL,
    PRIMARY KEY (account_id),
    CONSTRAINT chk_accounts_balance_nonnegative CHECK (balance >= 0)
) ENGINE = InnoDB;

CREATE TABLE account_transfers (
    transfer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    from_account_id BIGINT UNSIGNED NOT NULL,
    to_account_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(19,2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (transfer_id),
    CONSTRAINT chk_transfer_amount_positive CHECK (amount > 0),
    CONSTRAINT chk_transfer_accounts_different
        CHECK (from_account_id <> to_account_id)
) ENGINE = InnoDB;
```

`CHECK` constraints are enforced in MySQL 8.0.16 and later. If using an older version, verify behavior and add checks in the application or an appropriate compatibility mechanism.

### 7.2. Starting a Transaction and Conditional Updates

Example transferring 500,000 VND from account 101 to 202:

```sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 500000
WHERE account_id = 101
  AND balance >= 500000;

-- Application must check ROW_COUNT() = 1.
-- If not 1: ROLLBACK and report source account missing or insufficient balance.

UPDATE accounts
SET balance = balance + 500000
WHERE account_id = 202;

-- Application must check ROW_COUNT() = 1.
-- If not 1: ROLLBACK because destination account does not exist.

INSERT INTO account_transfers (
    from_account_id,
    to_account_id,
    amount
)
VALUES (101, 202, 500000);

COMMIT;
```

The SQL snippet above describes the sequence of operations; checking affected rows is mandatory and must be controlled by the client/procedure before proceeding. If any step fails to meet conditions, the transaction must be rolled back instead of continuing to `COMMIT`.

`UPDATE ... WHERE balance >= ...` checks the balance and deducts funds in a single locked operation, avoiding the "read balance outside transaction then update later" pattern that is prone to race conditions. You must check affected rows immediately after the corresponding UPDATE; `ROW_COUNT()` can be used in the same session to inspect the result of the statement just executed.

### 7.3. Locking Both Accounts in a Consistent Order

If business logic needs to read information from both accounts before updating, you can lock the rows with `SELECT ... FOR UPDATE` inside the transaction:

```sql
START TRANSACTION;

SELECT account_id, balance
FROM accounts
WHERE account_id IN (101, 202)
ORDER BY account_id
FOR UPDATE;

-- Application verifies both accounts exist, balance, and business rules.
-- Then executes UPDATE/INSERT and COMMIT; if invalid, executes ROLLBACK.
```

Sorting locks in the same order across transfer workflows helps reduce deadlock risk when two transfers happen in opposite directions. This is not a guarantee against deadlocks; the application must still handle deadlock errors and retry the transaction appropriately.

### 7.4. Why Not Issue COMMIT Regardless of Result?

If the source account has insufficient funds, the first UPDATE may affect 0 rows. If the application still adds funds to the destination account and commits, the system creates money out of nowhere. Therefore, commit must only be called after all steps succeed and all business conditions are confirmed.

## 8. Savepoints: Partial Transaction Rollback

A savepoint marks a position inside a transaction. You can roll back to a savepoint to discard changes after that marker while keeping changes before it.

```sql
START TRANSACTION;

UPDATE inventory
SET quantity = quantity - 5
WHERE product_id = 100;

SAVEPOINT after_inventory_update;

INSERT INTO shipment_items (shipment_id, product_id, quantity)
VALUES (9001, 100, 5);

-- If writing shipment item fails business validation:
ROLLBACK TO SAVEPOINT after_inventory_update;

-- Can continue processing in the transaction, or roll back everything.
COMMIT;
```

In the example, `ROLLBACK TO SAVEPOINT` discards changes after the savepoint while keeping the inventory update before it. This is only appropriate if business logic genuinely wants to keep the inventory update; in a typical fulfillment flow, both changes must go together, so an error in the second step might require a full `ROLLBACK`.

Related commands:

```sql
SAVEPOINT savepoint_name;
ROLLBACK TO SAVEPOINT savepoint_name;
RELEASE SAVEPOINT savepoint_name;
```

`COMMIT` or a full-transaction `ROLLBACK` deletes all savepoints. Savepoints do not create nested transactions and cannot roll back changes that have already been committed.

## 9. Statements That Cause Implicit Commit

Certain statements in MySQL automatically commit the current transaction before executing or according to implicit commit rules. This is especially important when mixing DDL and DML.

Dangerous example:

```sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;

ALTER TABLE accounts ADD COLUMN note VARCHAR(100) NULL;

ROLLBACK;
```

`ALTER TABLE` is a DDL statement that causes an implicit commit in MySQL. The earlier UPDATE change may already have been committed before the ALTER executes; the subsequent ROLLBACK cannot undo an already committed UPDATE.

### 9.1. Statement Groups to Watch Out For

Statements that commonly trigger an implicit commit include:

- DDL such as `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`, `RENAME TABLE`, `TRUNCATE TABLE`.
- Schema/database/index operations such as `CREATE DATABASE`, `DROP DATABASE`, `CREATE INDEX`, `DROP INDEX`.
- Certain administrative and table-locking commands such as `LOCK TABLES`.
- `SET autocommit = 1` when the value changes from 0 to 1.
- `START TRANSACTION` when a transaction is already open ends the current transaction before starting the new one.

The exact list has exceptions and differences by statement/version; check the MySQL documentation for your deployment version before designing migrations.

### 9.2. Temporary Tables Are an Exception to Understand Correctly

`CREATE TEMPORARY TABLE` and `DROP TEMPORARY TABLE` do not trigger an implicit commit the way regular DDL does. However, creating/dropping temporary tables cannot be rolled back like regular InnoDB data changes. Therefore, "no implicit commit" does not mean "fully rollbackable."

### 9.3. Separate Migrations from Business Transactions

Do not place DDL schema migrations in the middle of transactions processing orders, money transfers, or inventory. Run migrations through a separate deployment process with compatibility checks, backups, and metadata lock assessments.

## 10. Transactions and Connections

A transaction is bound to a MySQL connection/session. Every statement belonging to a transaction must run on the same physical connection.

Conceptually wrong example:

1. Connection A runs `START TRANSACTION`.
2. Connection B runs `UPDATE`.
3. Connection A runs `COMMIT`.

The UPDATE on connection B does not belong to connection A's transaction. `COMMIT` only ends the transaction on connection A.

This is especially important when using a connection pool. Never check out one connection to start a transaction, return it to the pool, and then check out another connection to continue statements.

### 10.1. Connection Closed While Transaction Is Uncommitted

If a connection terminates while an InnoDB transaction is still open, the server rolls back the uncommitted transaction during session cleanup. Applications should not rely on closing a connection as normal transaction control; always commit or roll back explicitly.

### 10.2. Connection Lost During COMMIT

If the client loses connection right while sending `COMMIT`, the application may not know whether the server committed or not. Do not assume "no response received" means the transaction rolled back.

For retryable operations such as order creation or money transfers, design an idempotency key or unique transaction code to query status after reconnecting, avoiding executing the business operation twice.

## 11. Transactions in Java JDBC

JDBC provides `Connection.setAutoCommit(false)`, `commit()`, and `rollback()` to manage transactions.

Example:

```java
try (Connection connection = dataSource.getConnection()) {
    boolean originalAutoCommit = connection.getAutoCommit();
    boolean transactionClean = false;
    Throwable failure = null;

    try {
        connection.setAutoCommit(false);

        try {
            try (PreparedStatement debit = connection.prepareStatement(
                    "UPDATE accounts "
                  + "SET balance = balance - ? "
                  + "WHERE account_id = ? AND balance >= ?")) {
                debit.setBigDecimal(1, amount);
                debit.setLong(2, fromAccountId);
                debit.setBigDecimal(3, amount);

                if (debit.executeUpdate() != 1) {
                    throw new IllegalStateException(
                        "Source account does not exist or has insufficient balance");
                }
            }

            try (PreparedStatement credit = connection.prepareStatement(
                    "UPDATE accounts SET balance = balance + ? "
                  + "WHERE account_id = ?")) {
                credit.setBigDecimal(1, amount);
                credit.setLong(2, toAccountId);

                if (credit.executeUpdate() != 1) {
                    throw new IllegalStateException(
                        "Destination account does not exist");
                }
            }

            try (PreparedStatement insert = connection.prepareStatement(
                    "INSERT INTO account_transfers "
                  + "(from_account_id, to_account_id, amount) "
                  + "VALUES (?, ?, ?)")) {
                insert.setLong(1, fromAccountId);
                insert.setLong(2, toAccountId);
                insert.setBigDecimal(3, amount);
                insert.executeUpdate();
            }

            connection.commit();
            transactionClean = true;
        } catch (SQLException | RuntimeException ex) {
            try {
                connection.rollback();
                transactionClean = true;
            } catch (SQLException rollbackError) {
                ex.addSuppressed(rollbackError);
            }
            throw ex;
        }
    } catch (SQLException | RuntimeException ex) {
        failure = ex;
        throw ex;
    } finally {
        if (transactionClean) {
            try {
                connection.setAutoCommit(originalAutoCommit);
            } catch (SQLException resetError) {
                // Do not reuse connection if resetting state fails.
                if (failure != null) {
                    failure.addSuppressed(resetError);
                } else {
                    // Invalidate connection using the pool's API before closing.
                    throw resetError;
                }
            }
        } else {
            // Indeterminate transaction state: evict connection using the pool's API.
        }
    }
}
```

The example illustrates how to manage a transaction on the same connection:

- Disable autocommit before executing the group of statements.
- Use prepared statements for input values.
- Check the updated row count for both source and destination accounts.
- Commit only after all operations succeed.
- Roll back when encountering an SQL error or business error.
- Restore autocommit state before the connection is returned to the pool.

In production code, if rollback or resetting autocommit fails, the connection is in an indeterminate state and must be removed from the pool using the active pool's invalidate/evict API. Standard JDBC does not provide a universal evict API across all connection pools; never return a broken connection to the pool for reuse. If resetting autocommit fails, preserve that error alongside the original exception using a suppressed exception or appropriate logging mechanism.

### 11.1. Do Not Call Commit on a Different Connection

All prepared statements in a transaction must be created and executed on the same `Connection`. Opening a new connection inside a service to run an auxiliary query puts that query outside the current transaction.

### 11.2. Do Not Keep a Transaction Open While Waiting for a User

Do not open a transaction and then wait for user confirmation in the UI, wait for OTP input, or wait for another HTTP request. Long transactions hold locks and snapshots, increasing lock wait risk, deadlocks, and large undo history. Separate confirmation steps into an appropriate workflow, using intermediate states or a reservation mechanism when needed.

## 12. Isolation, Locking, and Short Transactions

`COMMIT` and `ROLLBACK` define transaction boundaries; the isolation level determines how concurrent transactions view data and interact with one another.

Check the isolation level:

```sql
SELECT
    @@SESSION.transaction_isolation AS session_isolation,
    @@GLOBAL.transaction_isolation AS global_isolation;
```

Variable names and supported values depend on the MySQL version. Common InnoDB isolation levels include `READ UNCOMMITTED`, `READ COMMITTED`, `REPEATABLE READ`, and `SERIALIZABLE`.

Example of locking a row for update:

```sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 101
FOR UPDATE;

-- Check conditions and perform updates within the same transaction.

COMMIT;
```

`FOR UPDATE` is a locking read in InnoDB. Locks are held until the transaction ends. Proper indexes are needed to avoid unintended wide range locks.

A transaction should:

- Include only operations that need atomicity together.
- Be kept as short as possible.
- Access rows in a consistent order across competing threads.
- Have indexes for filter and lock conditions.
- Handle deadlocks by rolling back and retrying the entire business unit when appropriate.

Do not issue `COMMIT` early merely to release locks if doing so breaks business atomicity. Redesign transaction boundaries if a transaction is too long.

## 13. Deadlocks and Errors in Transactions

Two transactions can hold locks needed by the other, forming a wait cycle (deadlock). InnoDB detects deadlocks and chooses one transaction as a victim to roll back.

When encountering a deadlock:

1. Catch the error from MySQL/JDBC.
2. Treat the transaction chosen as victim as failed.
3. Roll back / ensure the connection is in a clean state.
4. If the operation is retryable, start a new transaction and retry all operations with a retry limit and appropriate backoff.
5. Log locks, statements, and business identifiers for investigation.

Do not merely re-run the last SQL statement in the failed transaction. You must repeat the entire unit of work because read states and prior changes are no longer valid.

Lock wait timeout differs from deadlock. Depending on `innodb_rollback_on_timeout`, a timeout may roll back only the current statement or the entire transaction. Applications need to handle this explicitly by rolling back the entire transaction before reusing the connection, rather than assuming all errors have the same rollback scope.

## 14. Common Misconceptions

| Misconception | Reality | Correct Practice |
|---|---|---|
| Every UPDATE always needs START TRANSACTION | With autocommit enabled, a single InnoDB statement is already its own transaction | Only open explicit transactions when multiple operations must commit/roll back together |
| BEGIN creates a nested transaction | MySQL does not support conventional nested transactions | Use savepoints for partial rollbacks |
| ROLLBACK undoes everything | Only undoes uncommitted transactional changes; does not undo external side effects or MyISAM tables | Check engines and isolate external tasks |
| COMMIT can be rolled back later | Commit has ended the transaction; a subsequent ROLLBACK does not reverse it | Use a compensating transaction if business reversal is needed |
| DDL can run inside a transaction and be rolled back | Many DDL statements cause an implicit commit | Separate schema migrations from business transactions |
| Disabling autocommit is the only way to use transactions | START TRANSACTION works while autocommit is enabled | Use explicit transactions per unit of work |
| A transaction can continue on another connection | Transactions are bound to a session/connection | Use the same physical connection until COMMIT/ROLLBACK |
| Losing the COMMIT response means rollback | Commit status may be indeterminate to the client | Design idempotency and verify transaction status |
| Deadlock only requires re-running the last statement | The victim transaction has already been rolled back | Retry the entire transaction according to policy |

## 15. Quick Verification Query Set

```sql
-- Check autocommit and isolation level
SELECT
    @@SESSION.autocommit AS session_autocommit,
    @@SESSION.transaction_isolation AS session_isolation;

-- Start transaction and update test data
START TRANSACTION;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 100;

-- Verify change within the same transaction
SELECT product_id, quantity
FROM inventory
WHERE product_id = 100;

-- Choose one of the two ending commands:
-- COMMIT;
-- ROLLBACK;

-- Check storage engines
SELECT TABLE_NAME, ENGINE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE();
```

The queries use `inventory` and `product_id` as examples. Only run the update part on test data and explicitly choose `COMMIT` or `ROLLBACK` before ending the session.

## 16. Pre-Production Transaction Checklist

- [ ] Accurately identified operations that must commit or roll back together.
- [ ] All participating tables use a transaction-capable storage engine, typically InnoDB.
- [ ] Checked `@@SESSION.autocommit` and avoided assuming session configuration.
- [ ] Transactions are started and ended explicitly.
- [ ] All statements within a transaction use the same connection.
- [ ] Verified affected row counts and business conditions before COMMIT.
- [ ] No implicit-commit DDL statements placed inside transactions.
- [ ] Savepoints used only when partial rollback is genuinely business-valid.
- [ ] Transactions are short, with indexes on filter/lock conditions and consistent row access ordering.
- [ ] Handled deadlocks, lock wait timeouts, and rollback errors.
- [ ] Implemented idempotency or status verification when connection drops during COMMIT.
- [ ] Connections are reset or evicted from the pool if transaction state is indeterminate.
- [ ] External side effects are orchestrated separately without assuming ROLLBACK can undo them.

## 17. Conclusion

`START TRANSACTION` or `BEGIN` opens an explicit transaction; `COMMIT` confirms changes; `ROLLBACK` discards uncommitted transactional changes. With `autocommit = 1`, each standalone statement usually auto-commits, yet multiple statements can still be grouped into the same transaction without disabling autocommit.

Rollback capability depends on the storage engine. InnoDB supports transactions; MyISAM does not provide equivalent rollback. Certain DDL statements trigger an implicit commit, transactions are bound to a single connection, and effects outside the database cannot be rolled back. Define clear business boundaries, validate every step before committing, handle errors/deadlocks, and keep transactions short so data remains both consistent and operationally stable.
