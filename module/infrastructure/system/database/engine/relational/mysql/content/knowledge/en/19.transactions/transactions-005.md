# Statement Atomicity and Transaction Atomicity

In the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query optimization, privilege management, backups, and relational database operations. When updating data, it is necessary to understand two distinct rollback scopes: **statement atomicity** and **transaction atomicity**.

With InnoDB, a failed DML statement is usually rolled back as a unit, while earlier successful statements in the same transaction still remain active inside the transaction. Only `ROLLBACK` undoes all uncommitted changes of the transaction; `COMMIT` confirms all of those changes. Distinguishing these two scopes helps handle errors properly, avoid committing partial data, and design safe retry flows.

Practice examples use InnoDB and MySQL 8.0 syntax. Check the server version with SELECT VERSION(); some status variables and DDL behaviors may differ between versions.

## 1. Two Atomicity Scopes

**Statement atomicity** means a single statement is treated as a unit for transactional tables: if the statement fails, changes made by that statement itself are undone. For example, if a multi-row INSERT encounters a duplicate key error partway through, InnoDB undoes the rows that INSERT had already inserted.

**Transaction atomicity** means the entire group of statements in a transaction is treated as a unit: either all changes are committed, or all uncommitted changes are rolled back. If a transaction has three successful statements and the fourth statement fails, the three previous statements do not automatically disappear merely because the fourth failed.

| Scope | Protected Unit | How It Ends |
|---|---|---|
| Statement atomicity | A single SQL statement | The statement succeeds or the statement's changes are undone |
| Transaction atomicity | Multiple statements belonging to the same transaction | COMMIT confirms all or ROLLBACK undoes all |

The two scopes are related but do not replace each other. Statement atomicity protects each individual operation; transaction atomicity protects a multi-operation business workflow.

## 2. Statement Atomicity in InnoDB

InnoDB is a transaction-capable storage engine. When a statement modifies multiple rows and an error occurs during execution, InnoDB can undo the changes made by that statement itself.

For example, the ledger_entries table has primary key entry_id. A statement inserts two rows, but the second row violates the primary key:

~~~sql
INSERT INTO ledger_entries (entry_id, account_id, amount)
VALUES
    (9002, 1, -100.00),
    (9001, 2,  100.00);
~~~

Suppose entry_id = 9001 already exists. The statement hits a duplicate key error. With InnoDB, the entire statement is rolled back: row 9002 is no longer inserted even though it appeared before the failing row in the VALUES list.

Statement atomicity also applies to multi-row DML statements such as UPDATE or DELETE. If an error causes the statement to fail, the statement's changes on InnoDB tables are undone as a unit.

### 2.1. Statement Failure Does Not Mean the Transaction Ended

Inside an explicit transaction, an error such as duplicate key usually rolls back only the failing statement. The transaction remains open and earlier successful statements remain uncommitted changes.

Example:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 1;

-- Suppose entry_id = 9001 already exists.
INSERT INTO ledger_entries (entry_id, account_id, amount)
VALUES
    (9002, 1, -100.00),
    (9001, 2,  100.00);

-- After the duplicate key error, check state in the same session.
SELECT account_id, balance
FROM accounts
WHERE account_id = 1;

SELECT entry_id
FROM ledger_entries
WHERE entry_id = 9002;

ROLLBACK;
~~~

After the INSERT error:

- The INSERT statement's changes are undone; entry_id 9002 does not exist.
- The earlier UPDATE still remains in the transaction; the current session still sees the balance reduced by 100.
- If COMMIT is called, the earlier UPDATE can be committed even though the INSERT failed.
- If ROLLBACK is called, the earlier UPDATE is also undone.

This is the most important point when handling mid-transaction errors: never assume that a single statement error has rolled back the entire transaction.

### 2.2. Conceptual Rollback Mechanism

InnoDB uses undo information to be able to restore data state before a change. When a statement needs to roll back, the engine uses undo information to remove the changes created by that statement. When a transaction rolls back, InnoDB undoes all uncommitted changes belonging to the transaction.

The internal details are more complex than a user-created SQL savepoint. You can picture InnoDB marking the scope of a statement's changes so it can undo the exact necessary part; you do not need to manually create a SAVEPOINT before every DML statement to get statement atomicity.

## 3. Transaction Atomicity: Multiple Statements as One Unit

A business workflow often consists of multiple operations that must succeed together. For example, transferring money between two accounts:

1. Deduct money from the sending account.
2. Add money to the receiving account.
3. Record the transaction.

If only one step succeeds, data can become inconsistent. A transaction groups the steps into a single unit:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 100.00
WHERE account_id = 2;

INSERT INTO ledger_entries (entry_id, account_id, amount)
VALUES
    (9101, 1, -100.00),
    (9102, 2,  100.00);

COMMIT;
~~~

If all statements succeed and COMMIT succeeds, the changes are confirmed. If a business error is detected before commit, the application can call ROLLBACK to undo both UPDATEs and the INSERT.

Checking only SQL errors is not enough. The application must also check the affected row count. For example, an UPDATE by account_id may run without SQL error yet update 0 rows because the account does not exist; in that case there is no SQL error, yet the money transfer workflow is still invalid.

## 4. Autocommit and Transaction Boundaries

MySQL usually runs with autocommit = 1. In that mode, each statement executed outside an explicit transaction is treated as its own transaction and automatically committed if it succeeds.

Check session configuration:

~~~sql
SELECT @@SESSION.autocommit;
~~~

With autocommit enabled:

~~~sql
UPDATE accounts
SET balance = balance - 10.00
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 10.00
WHERE account_id = 2;
~~~

The two UPDATEs are two separate transactions. If the second fails, the first may already be committed; you cannot roll it back by calling ROLLBACK afterward.

To make both statements belong to the same transaction:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 10.00
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 10.00
WHERE account_id = 2;

COMMIT;
~~~

START TRANSACTION opens an explicit transaction even when autocommit is enabled. When the transaction ends with COMMIT or ROLLBACK, the session returns to its configured autocommit behavior.

MySQL does not support nested transactions. Calling START TRANSACTION while another transaction is open ends the current transaction via implicit commit before starting the new transaction. If you need a sub-scope for undoing work, use SAVEPOINT instead of calling START TRANSACTION again.

### 4.1. Autocommit Disabled

You can set autocommit for the session:

~~~sql
SET SESSION autocommit = 0;
~~~

When autocommit is off, changes are held in the transaction until COMMIT or ROLLBACK. After a transaction ends, the session continues operating in autocommit-off mode and the next transaction is opened according to that mode's rules.

In applications, manage transaction boundaries explicitly and restore session settings when returning a connection to a connection pool. A connection left in autocommit = 0 can cause subsequent operations to accidentally stay in an unfinished transaction.

## 5. Comparing Statement Rollback and Full-Transaction Rollback

Suppose a transaction executes three statements:

~~~sql
START TRANSACTION;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 10;

INSERT INTO order_items (item_id, product_id, quantity)
VALUES (1001, 10, 1);

UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = 500;
~~~

If the INSERT statement hits a duplicate key:

- The INSERT statement is rolled back.
- The earlier UPDATE inventory still remains in the transaction.
- The UPDATE orders after the error can still execute if the application intentionally proceeds and the transaction remains valid.
- COMMIT can confirm the successful statements before and after the error.
- ROLLBACK undoes all uncommitted changes of all three statements.

Applications should generally stop the business workflow and roll back when a mandatory step fails. Continuing a transaction after an error is only appropriate when logic clearly determines that the error is safe to skip.

## 6. SAVEPOINT: Partial Transaction Rollback

SAVEPOINT allows marking a position in a transaction so part of the changes can be rolled back:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 50.00
WHERE account_id = 1;

SAVEPOINT after_debit;

INSERT INTO transaction_notes (transaction_id, note)
VALUES (9100, 'Transfer note');

-- If only the note part is invalid:
ROLLBACK TO SAVEPOINT after_debit;

-- Changes before the savepoint remain.
COMMIT;
~~~

ROLLBACK TO SAVEPOINT undoes changes after the savepoint and keeps the transaction open. It does not commit the part before the savepoint.

### 6.1. SAVEPOINT Does Not Replace a Transaction

If a transfer debited the sending account before the savepoint and then rolled back to the savepoint, the debit still remains. If business logic requires undoing the debit as well, you must roll back the entire transaction or roll back to a savepoint placed before the debit.

You can remove a savepoint when it is no longer needed:

~~~sql
RELEASE SAVEPOINT after_debit;
~~~

COMMIT or a full-transaction ROLLBACK ends the scope of all savepoints belonging to that transaction.

### 6.2. Using Savepoints to Handle Optional Steps

Savepoints are useful when a transaction has a mandatory part and an optional part. For example, creating an order and deducting inventory are mandatory; writing an auxiliary note may be allowed to fail while keeping the order. Apply this only when business rules allow the optional part to be absent and the application handles the error intentionally.

Do not use savepoints to mask data integrity errors in core steps. If deducting inventory or writing order details fails, the entire transaction must roll back.

## 7. Errors That Can Affect Rollback Scope Differently

Not every error has the same behavior. You need to recognize the error type and InnoDB configuration.

### 7.1. Common Constraint Errors

For example, duplicate key or foreign key violations in an InnoDB DML statement usually cause that statement to be rolled back. The explicit transaction stays open so the application can decide whether to continue, roll back, or handle the error.

~~~sql
START TRANSACTION;

INSERT INTO lab_parent (parent_id) VALUES (1);

-- If the foreign key does not exist, this INSERT statement fails.
INSERT INTO lab_child (child_id, parent_id)
VALUES (10, 999);

-- The failing INSERT was rolled back; the prior statement remains an uncommitted change.
ROLLBACK;
~~~

### 7.2. Deadlock

When InnoDB detects a deadlock, the engine chooses one transaction as a victim and rolls back that entire transaction to release locks. The application receives a deadlock error (typically error 1213 / SQLSTATE 40001) and must re-execute the entire transaction if the business operation is still needed.

Do not merely re-run the SQL statement that just failed. Earlier statements in the victim transaction were rolled back; you must start a new transaction and execute the full workflow again.

### 7.3. Lock Wait Timeout

When waiting for a lock exceeds the allowed timeout, InnoDB by default rolls back the waiting statement, not necessarily the entire transaction. The variable innodb_rollback_on_timeout can change this behavior to roll back the entire transaction when a lock wait timeout occurs.

Check:

~~~sql
SELECT @@SESSION.innodb_lock_wait_timeout;
SELECT @@GLOBAL.innodb_rollback_on_timeout;
~~~

If the application continues after a lock wait timeout, it must know with certainty whether the transaction is still open or was rolled back completely. Never infer rollback scope solely from receiving a timeout error.

### 7.4. Connection Errors and Lost Responses

If the connection closes while a transaction is uncommitted, MySQL rolls back the open transaction during session termination. However, if the client loses connection right while sending COMMIT, the client may not know whether the server committed or not.

In a situation where the response is lost after COMMIT, do not blindly resend the business operation. Design an idempotency key, unique transaction ID, or status verification query step to avoid recording it twice.

## 8. Statements That May Not Roll Back Completely as Expected

Statement atomicity and transaction atomicity depend on the storage engine and statement type.

### 8.1. Non-Transactional Storage Engines

InnoDB supports COMMIT and ROLLBACK. MyISAM does not support transactions; changes on MyISAM tables are not undone by ROLLBACK.

Example of the risk:

~~~sql
START TRANSACTION;

UPDATE innodb_accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE myisam_audit
SET event_count = event_count + 1
WHERE event_id = 10;

ROLLBACK;
~~~

Changes on innodb_accounts are undone; changes on myisam_audit are not rolled back. Therefore, an atomic transaction cannot be guaranteed across tables using non-transactional engines.

For workflows requiring atomicity, participating tables should use a transactional engine like InnoDB. Check engines:

~~~sql
SHOW TABLE STATUS
WHERE Name IN ('innodb_accounts', 'myisam_audit');
~~~

### 8.2. INSERT IGNORE and Statements That Convert Errors into Warnings

INSERT IGNORE can skip certain rows that violate constraints or have data errors and continue inserting valid rows. When errors are downgraded to warnings, the statement no longer fails in the usual way, so the entire statement is not rolled back.

~~~sql
INSERT IGNORE INTO ledger_entries (entry_id, account_id, amount)
VALUES
    (9002, 1, -100.00),
    (9001, 2,  100.00);

SHOW WARNINGS;
~~~

If 9001 already exists, the conflicting row may be skipped while row 9002 is still inserted. This is the intended behavior of IGNORE, not a violation of statement atomicity. Inspect warnings and affected row counts if using IGNORE.

Similarly, variants like UPDATE IGNORE can skip failing rows. Never add IGNORE just to make a statement "go through"; you must determine whether skipped data is acceptable.

### 8.3. DDL and Implicit Commit

Many DDL statements such as CREATE TABLE, ALTER TABLE, and DROP TABLE cause an implicit commit. They may commit the current transaction before executing and can create their own commit boundary per MySQL rules.

Example:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 10
WHERE account_id = 1;

CREATE TABLE lab_marker (
    marker_id INT PRIMARY KEY
);

ROLLBACK;
~~~

Do not assume the final ROLLBACK will undo the UPDATE before the DDL. The DDL may have already committed the prior transaction. MySQL 8.0 has atomic DDL for many supported DDL operations, meaning the DDL operation is crash-safe as a unit; this does not turn DDL into something that can be rolled back within a user's DML transaction.

Some exceptions like CREATE TEMPORARY TABLE do not trigger an implicit commit, yet temporary table creation is still not rolled back in the usual way. When designing business transactions, avoid mixing DDL into the middle of DML steps.

### 8.4. Transactional Tables and External Side Effects

ROLLBACK only undoes transactional changes managed by MySQL within the transaction. It does not automatically recall sent emails, HTTP requests made to other services, files written, or operations in an external system. If an application performs side effects before COMMIT and the transaction then rolls back, the two systems can become out of sync.

For integration workflows, consider a transactional outbox: write the event to be sent into an InnoDB table in the same transaction as the business data, commit both, and then have a separate process send the event and mark it processed. This ties event generation to the data transaction; delivery still needs retry and idempotency mechanisms.

## 9. Atomicity Does Not Equal All ACID Properties

Atomicity is one component of ACID:

| Property | Meaning |
|---|---|
| Atomicity | A transaction's changes are committed together or rolled back together |
| Consistency | A transaction must bring data from a valid state to a valid state according to constraints and business rules |
| Isolation | Concurrent transactions do not observe or interfere with one another beyond the chosen isolation level |
| Durability | After commit is confirmed per guaranteed configuration, data persists across crashes per system commitments |

Statement atomicity protects one statement. Transaction atomicity protects a sequence of statements. Yet atomicity alone does not ensure business rules are correct, does not automatically prevent race conditions, and does not replace durability.

For example, a transaction can atomically debit two accounts yet still be business-invalid if it fails to check balance before deducting. Similarly, a transaction may commit successfully, but an unsuitable durability configuration can provide different guarantees than operational expectations. You must thoroughly design constraints, isolation, locking, and persistence settings.

## 10. Designing Transactions to Avoid Committing Partial Data

A safe transaction flow typically follows this structure:

1. Start the transaction.
2. Read and lock data needing protection if required by business logic.
3. Check conditions before writing.
4. Execute mandatory changes.
5. Verify affected row counts and business outcomes.
6. Commit when all steps are valid.
7. Roll back when any mandatory step fails.

Example transfer with balance check:

~~~sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;

-- Application confirms the account exists and balance >= 100.00.
UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 1
  AND balance >= 100.00;

-- Application must confirm the UPDATE just affected exactly 1 row.
UPDATE accounts
SET balance = balance + 100.00
WHERE account_id = 2;

-- Only commit after verifying all steps and recording the ledger successfully.
COMMIT;
~~~

This is an illustrative skeleton; the application must handle non-existent accounts, insufficient balance, non-existent receiving accounts, and errors while writing to the ledger by calling ROLLBACK. SELECT ... FOR UPDATE holds the necessary lock until the transaction ends in InnoDB, helping prevent certain race conditions when multiple transactions update the account concurrently.

Do not keep a transaction open while waiting for user input or calling network services. Prolonged transactions keep locks alive longer, increasing deadlock risk and reducing concurrency.

## 11. Retrying After Errors and Idempotency

Some errors such as deadlocks are transient errors that can be retried. The right way to retry:

- Identify retryable errors, such as deadlock.
- Ensure the old transaction has been rolled back or terminated.
- Start a new transaction.
- Re-run the entire business operation from the beginning.
- Limit retry attempts and apply appropriate backoff.
- Ensure the operation has idempotency or a business key to prevent duplicate effects.

Do not retry only the last statement in a deadlocked transaction because the entire transaction was rolled back. For duplicate key errors, before retrying you must determine whether it is a data conflict, an operation already executed earlier, or an existing idempotency key.

### 11.1. Unique Transaction ID

You can use an idempotency key to prevent the same business request from being processed twice:

~~~sql
CREATE TABLE transfer_requests (
    request_id VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (request_id)
) ENGINE=InnoDB;
~~~

The application writes the unique request_id in the same transaction as the balance and ledger changes. If the client resends the same request_id, the primary key identifies that the request already exists. The application should read the existing transaction status to return the appropriate result rather than automatically executing the transfer again.

### 11.2. Losing Connection During COMMIT

If the server finishes committing but the response is lost over the network, the client may receive a connection error even though the transaction committed. Resending a new debit command without checking request_id can create a second transaction. An idempotency key and a ledger with a unique code help distinguish "not yet processed" from "processed but client missed the response."

## 12. Inspecting Transaction State and Data

During development, you can use the following queries to observe state:

~~~sql
SELECT @@SESSION.autocommit;
SELECT @@SESSION.in_transaction;
SELECT @@SESSION.transaction_isolation;
~~~

@@SESSION.in_transaction indicates whether the session is currently inside a transaction on versions supporting this variable. If the variable is unavailable on the running version, rely on client/driver state and the application's transaction management.

Check a table's engine:

~~~sql
SHOW CREATE TABLE accounts;
~~~

Inspect constraints, primary keys, foreign keys, and engines before relying on rollback. Do not assume every table in an SQL query is InnoDB just because the main database uses InnoDB.

## 13. Comprehensive Example: Distinguishing Statement Rollback from Transaction Rollback

Create lab data:

~~~sql
CREATE TABLE lab_accounts (
    account_id INT NOT NULL,
    owner_name VARCHAR(80) NOT NULL,
    balance DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (account_id)
) ENGINE=InnoDB;

CREATE TABLE lab_ledger (
    entry_id INT NOT NULL,
    account_id INT NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (entry_id),
    CONSTRAINT fk_lab_ledger_account
      FOREIGN KEY (account_id)
      REFERENCES lab_accounts (account_id)
) ENGINE=InnoDB;

INSERT INTO lab_accounts (account_id, owner_name, balance)
VALUES (1, 'An', 1000.00), (2, 'Binh', 500.00);

INSERT INTO lab_ledger (entry_id, account_id, amount)
VALUES (9001, 2, 25.00);
~~~

### 13.1. Step 1 — Create a Change Before the Failing Statement

~~~sql
START TRANSACTION;

UPDATE lab_accounts
SET balance = balance - 100.00
WHERE account_id = 1;
~~~

Read the balance in the same session:

~~~sql
SELECT account_id, balance
FROM lab_accounts
ORDER BY account_id;
~~~

The current session sees account 1 has 900.00 remaining. This change is not yet committed.

### 13.2. Step 2 — Trigger an Error in a Multi-Row Statement

Run the following statement separately. It attempts to insert a new entry 9002 and an existing entry 9001:

~~~sql
INSERT INTO lab_ledger (entry_id, account_id, amount)
VALUES
    (9002, 1, -100.00),
    (9001, 2,  100.00);
~~~

MySQL reports a duplicate key error. With InnoDB, the entire statement is rolled back. Verify:

~~~sql
SELECT *
FROM lab_ledger
WHERE entry_id IN (9001, 9002);
~~~

Only the initial entry 9001 exists; entry 9002 was not kept.

### 13.3. Step 3 — Observe That the Transaction Still Holds the Earlier Change

~~~sql
SELECT account_id, balance
FROM lab_accounts
WHERE account_id = 1;

SELECT @@SESSION.in_transaction;
~~~

In the same session, balance is still 900.00 and the transaction remains open. The INSERT error did not automatically roll back the prior UPDATE.

### 13.4. Step 4 — Roll Back the Entire Transaction

~~~sql
ROLLBACK;

SELECT account_id, balance
FROM lab_accounts
ORDER BY account_id;
~~~

Account 1's balance returns to 1000.00. The prior UPDATE was undone because it belonged to the rolled-back transaction.

### 13.5. Step 5 — Attempt to Commit After a Statement Error

Repeat in a new transaction:

~~~sql
START TRANSACTION;

UPDATE lab_accounts
SET balance = balance - 100.00
WHERE account_id = 1;
~~~

Re-run the INSERT with the duplicate key and receive the error. If the application still calls:

~~~sql
COMMIT;
~~~

The UPDATE deducting 100 can be committed even though the INSERT statement failed. This is why applications must proactively roll back the entire transaction when a mandatory step fails.

### 13.6. Step 6 — Clean Up Lab Tables

~~~sql
DROP TABLE lab_ledger;
DROP TABLE lab_accounts;
~~~

If only completing the main lab exercise, drop the two newly created lab tables in child-table-before-parent-table order. If you want to continue to the extension in section 14, keep both tables and clean up only after finishing that section. If a transaction is still open, end the transaction before cleaning up.

**Expected outcome:** be able to explain why the failing INSERT kept none of its own rows while the prior UPDATE still persisted in the transaction; demonstrate that ROLLBACK undoes the UPDATE; and understand why calling COMMIT after an error can persist a partial business workflow if the application handles errors improperly.

## 14. Extended Practice: SAVEPOINT and IGNORE

### 14.1. Testing Rollback to Savepoint

~~~sql
START TRANSACTION;

UPDATE lab_accounts
SET balance = balance - 20.00
WHERE account_id = 1;

SAVEPOINT before_optional_note;

INSERT INTO lab_ledger (entry_id, account_id, amount)
VALUES (9201, 1, -20.00);

ROLLBACK TO SAVEPOINT before_optional_note;

SELECT account_id, balance
FROM lab_accounts
WHERE account_id = 1;

SELECT *
FROM lab_ledger
WHERE entry_id = 9201;

ROLLBACK;
~~~

After rolling back to the savepoint, ledger entry 9201 is gone, while the deduction of 20 still remains in the transaction. The final ROLLBACK undoes the deduction as well.

### 14.2. Testing INSERT IGNORE

~~~sql
INSERT IGNORE INTO lab_ledger (entry_id, account_id, amount)
VALUES
    (9301, 1, -10.00),
    (9001, 2,  10.00);

SHOW WARNINGS;

SELECT *
FROM lab_ledger
WHERE entry_id IN (9001, 9301);
~~~

If 9001 already exists, row 9301 may be inserted while the duplicate row is skipped with a warning. Observe row counts and warnings to distinguish a failed statement that is rolled back from an IGNORE statement that partially completes according to its rules.

This extension uses the two tables lab_accounts and lab_ledger created in section 13. If you deleted them in step 13.6, recreate the tables and sample data per section 13 before continuing. After finishing, clean up the tables:

~~~sql
DROP TABLE lab_ledger;
DROP TABLE lab_accounts;
~~~

Only drop the lab tables you just created.

## 15. Application Transaction Error-Handling Workflow

When a statement inside a transaction reports an error, the application should follow a clear procedure:

1. Log the error code, SQLSTATE, and the currently executing business step.
2. Classify the error: constraint, deadlock, lock timeout, connection loss, or non-continuable error.
3. Determine the engine of participating tables and the rollback behavior of that error type.
4. If a mandatory step failed, roll back the entire transaction while the session is still active.
5. If the transaction was already rolled back by InnoDB due to deadlock, start a new transaction before retrying.
6. If a timeout only rolled back the statement, decide explicitly whether to continue the transaction or roll back everything.
7. Only retry recoverable errors; use an idempotency key to avoid duplicate effects.
8. Do not call external services or send irreversible notifications before the data transaction is confirmed; consider a transactional outbox.
9. End the transaction before returning the connection to the pool.

In application code, wrap the transaction in a try/catch/finally block or equivalent framework mechanism. The success branch calls commit; the error branch calls rollback; finally ensures the connection is returned to the pool in a clean state. Avoid swallowing an exception and still committing.

## 16. Principles to Remember

- Statement atomicity protects the changes of a single statement on a transactional engine; transaction atomicity protects all statements within a transaction.
- With InnoDB, common DML errors like duplicate key usually roll back the failing statement, without automatically rolling back all earlier statements.
- After a statement error, the transaction may remain open; the application must decide to continue, COMMIT, or ROLLBACK.
- Calling COMMIT after a statement error can save earlier successful statements; if the failing step is mandatory, you must roll back the entire transaction.
- When autocommit is enabled, each standalone statement outside an explicit transaction commits individually; multiple statements require START TRANSACTION to be atomic together.
- SAVEPOINT and ROLLBACK TO SAVEPOINT only undo part of a transaction; they do not commit the rest.
- A deadlock causes InnoDB to roll back the entire victim transaction; retries must re-run the entire transaction.
- Lock wait timeout rolls back the waiting statement by default; innodb_rollback_on_timeout can alter rollback scope.
- MyISAM does not support transactions; ROLLBACK does not undo changes to MyISAM tables.
- INSERT IGNORE and UPDATE IGNORE can skip failing rows and continue, so they do not share the same behavior as a regular failing statement.
- Many DDL statements cause an implicit commit; atomic DDL does not mean DDL can be rolled back inside a DML transaction.
- ROLLBACK does not revoke side effects outside MySQL; use idempotency and transactional outbox when integrating services.
- Atomicity does not replace consistency, isolation, or durability; verify business conditions, locks, engines, and configuration.

Once you distinguish statement boundaries from transaction boundaries, you will handle errors at the right scope, know when a full rollback is needed, and avoid accidentally committing a partial business workflow. Always determine storage engine, autocommit, error type, and commit boundaries before building retry logic.
