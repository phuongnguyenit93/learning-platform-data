# Start Time, End Time, and Boundaries of a Transaction in Oracle

In Oracle Database, a single DML statement can modify multiple rows, yet those changes do not become confirmed data immediately after each statement. They belong to a **transaction**: a unit of work that can be confirmed together with `COMMIT` or discarded with `ROLLBACK`. Understanding exactly when a transaction starts, where it ends, and which operations create transaction boundaries on their own is essential to avoid data loss, unintended commits, and holding locks too long.

For example, when transferring money between two accounts, the system must debit the source account and credit the destination account as a single unit. If it only debits the money and the application encounters an error before crediting, the transaction must be rolled back so data is not left in a half-finished state. If both operations succeed, the application commits to confirm all changes.

This lesson belongs to the **Transactions** topic of *Database Engine Relational Oracle*. It focuses on:

- Implicit transaction start in a session and the role of `SET TRANSACTION`.
- Ending boundaries via `COMMIT`, `ROLLBACK`, and savepoints.
- DDL statements that trigger implicit commits.
- Transaction scope across a session, PL/SQL, and connection pools.
- Data visibility, row locks, and read consistency.
- Differences between `READ COMMITTED`, `SERIALIZABLE`, and `READ ONLY`.
- Hands-on scenarios and common errors when managing transactions.

## 1. What Is a Transaction?

A transaction is a sequence of database operations treated as a single unit of work. Oracle uses transactions to ensure that the unit's changes are confirmed or discarded according to consistency rules.

The four properties are commonly described as ACID:

| Property | Meaning |
| --- | --- |
| **Atomicity** | Transaction changes are confirmed together; if rolled back, uncommitted changes are discarded. |
| **Consistency** | A transaction must move data from one valid state to another valid state according to constraints and business rules. |
| **Isolation** | Concurrent transactions are coordinated so they do not read each other's uncommitted data and follow the chosen isolation level. |
| **Durability** | After a successful COMMIT, Oracle guarantees that committed changes can be recovered after a crash via redo/recovery mechanisms. |

ACID does not mean all business errors are automatically detected. The application must still validate balances, permissions, status, and business conditions before committing.

### Example: Money Transfer

Suppose you transfer 100 from account A to account B:

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 'A';

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 'B';

COMMIT;
~~~

Both UPDATEs belong to the same transaction if there is no intervening commit/rollback boundary. If the second UPDATE fails and the application decides to cancel the transaction:

~~~sql
ROLLBACK;
~~~

Oracle discards the uncommitted debit change from the first UPDATE as well. In a real application, you must validate prerequisites (account exists, sufficient balance, exactly one row updated, valid destination account) before committing. The SQL snippet above only illustrates the transaction boundary, not a complete money-transfer workflow.

## 2. When Does a Transaction Start?

Oracle manages transactions per session. After the previous transaction ends, the first data-modifying operation typically opens a new transaction. DML operations such as `INSERT`, `UPDATE`, `DELETE`, and `MERGE` join the current transaction; they do not auto-commit merely because the statement succeeded.

Example:

~~~sql
INSERT INTO departments (department_id, department_name)
VALUES (90, 'Research');

UPDATE departments
SET department_name = 'Research and Development'
WHERE department_id = 90;

-- Not committed yet: both changes still belong to the current transaction.
COMMIT;
~~~

The transaction contains both the INSERT and the UPDATE. Upon COMMIT, both changes are confirmed.

### No Need to Write BEGIN TRANSACTION as in Some Other DBMSs

In standard Oracle SQL, you do not open a transaction with `BEGIN TRANSACTION` syntax like in some other database systems. DML transactions are managed implicitly by the session; the first DML statement after the previous boundary starts a new unit of change.

Example:

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 10;

-- The transaction now has uncommitted changes.
COMMIT;
~~~

### Standard SELECT and Transactions

A standard SELECT creates no uncommitted DML changes and holds no row locks merely for reading a table. Oracle provides read consistency for SELECT statements, meaning a query reads a consistent image of data as of the appropriate point in time without seeing another session's uncommitted changes.

However, do not think SELECT and transactions are completely unrelated. `SET TRANSACTION READ ONLY`/`SERIALIZABLE` configures the transaction mode and must be executed before any other statement in the transaction. `SELECT ... FOR UPDATE` locks the selected rows in preparation for updating, and those locks are held until the transaction ends.

### SET TRANSACTION: Configuring a Transaction Right at the Start

Oracle lets you set the transaction mode with `SET TRANSACTION`. This command must be the first statement of the transaction:

~~~sql
COMMIT;
SET TRANSACTION READ ONLY;

SELECT department_id, COUNT(*)
FROM employees
GROUP BY department_id;

COMMIT;
~~~

Another example:

~~~sql
COMMIT;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT ...
FROM ...

UPDATE ...
SET ...
WHERE ...;

COMMIT;
~~~

Key options include `READ WRITE` (default), `READ ONLY`, and `ISOLATION LEVEL SERIALIZABLE`. Do not place `SET TRANSACTION` after already running DML or another statement in the transaction; Oracle will raise an error because the transaction has already begun.

### BEGIN and END in PL/SQL Are Not Transaction Boundaries

A PL/SQL block:

~~~sql
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 'A';

    UPDATE accounts
    SET balance = balance + 100
    WHERE account_id = 'B';
END;
/
~~~

`BEGIN`/`END` merely mark the scope of a PL/SQL block. They do not auto-commit at the end of the block. If the block finishes successfully without a COMMIT/ROLLBACK or a DDL statement causing an implicit commit, the changes remain in the session's transaction and the caller can commit or roll back afterward.

This is a critical point when calling stored procedures: a procedure should not commit arbitrarily if the caller needs to combine multiple procedures into a single business transaction.

## 3. COMMIT: Ending and Confirming a Transaction

`COMMIT` ends the current transaction and confirms all uncommitted changes of the session:

~~~sql
UPDATE employees
SET salary = salary + 500
WHERE employee_id = 100;

COMMIT;
~~~

After a successful COMMIT:

- The transaction's changes become confirmed changes.
- Other sessions can see the new data according to their read consistency.
- Row locks held by the transaction are released.
- Savepoints in the transaction are cleared.
- The current transaction ends; subsequent DML will belong to a new transaction.

Oracle generates the corresponding commit record and SCN. The redo mechanism guarantees commit durability; do not assume every data block has already been written to datafiles by DBWR before COMMIT returns. Redo/log recovery protects committed changes, while data block writes can happen later.

### COMMIT Does Not Only Confirm the Last Statement

~~~sql
INSERT INTO audit_events(event_id, event_type)
VALUES (1001, 'STARTED');

UPDATE jobs
SET status = 'DONE'
WHERE job_id = 55;

COMMIT;
~~~

COMMIT confirms **all uncommitted changes in the current transaction**, including both the INSERT and the UPDATE. It is not limited to the immediately preceding statement.

### COMMIT WORK

~~~sql
COMMIT WORK;
~~~

This is a valid full syntax form. In everyday usage, `COMMIT` and `COMMIT WORK` share the same goal of ending the current transaction. Advanced options such as `WRITE WAIT/NOWAIT` or `IMMEDIATE/BATCH` affect the redo write policy and must be used according to durability requirements; do not change them merely to try speeding things up without understanding the risks.

## 4. ROLLBACK: Discarding Uncommitted Changes

`ROLLBACK` without a savepoint discards all uncommitted changes in the current transaction:

~~~sql
UPDATE products
SET unit_price = unit_price * 1.10
WHERE category_id = 7;

-- Realized the update scope was wrong.
ROLLBACK;
~~~

After ROLLBACK:

- Uncommitted DML changes in the transaction are undone.
- Row locks held by the transaction are released.
- Savepoints in the transaction are cleared.
- The current transaction ends.
- Previously committed changes are unaffected.

ROLLBACK cannot reverse a COMMITted transaction. If you committed by mistake, you need a compensating transaction, recovery from an appropriate backup/flashback, or a controlled data-correction procedure.

### ROLLBACK WORK

~~~sql
ROLLBACK WORK;
~~~

This is the full syntax form corresponding to a standard ROLLBACK.

### A Failed DML Statement Does Not Mean the Whole Transaction Auto-Rolls Back

If a DML statement fails, Oracle normally rolls back the failed statement to the state before that statement began; earlier statements in the same transaction remain in effect as uncommitted work. The application must decide whether to fix and commit or roll back the entire transaction.

Example:

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 'A';

-- The following statement may fail due to a constraint violation.
INSERT INTO departments (department_id, department_name)
VALUES (10, 'Duplicate department');

-- The first UPDATE is still in the transaction if not rolled back yet.
ROLLBACK;
~~~

Never assume an arbitrary SQL error automatically discards all previous changes. Handle exceptions and transaction boundaries explicitly.

## 5. SAVEPOINT and ROLLBACK TO SAVEPOINT

`SAVEPOINT` sets a marker inside a transaction so you can roll back part of the work without discarding the entire transaction.

~~~sql
UPDATE orders
SET status = 'PROCESSING'
WHERE order_id = 500;

SAVEPOINT after_order_status;

INSERT INTO order_audit(order_id, action_name)
VALUES (500, 'PROCESSING');

UPDATE inventory
SET reserved_qty = reserved_qty + 1
WHERE product_id = 900;

-- If the inventory step is invalid, roll back to the savepoint.
ROLLBACK TO SAVEPOINT after_order_status;

-- The transaction is still active; another step can be executed.
INSERT INTO order_audit(order_id, action_name)
VALUES (500, 'PROCESSING_RETRY');

COMMIT;
~~~

After `ROLLBACK TO SAVEPOINT after_order_status`, changes after the savepoint are undone, while the order status change before the savepoint remains in the transaction and will be COMMITted at the end. This command **does not end the transaction**.

### Creating and Using Multiple Savepoints

~~~sql
SAVEPOINT step_a;
UPDATE accounts SET status = 'REVIEW' WHERE account_id = 'A';

SAVEPOINT step_b;
UPDATE accounts SET status = 'HOLD' WHERE account_id = 'B';

ROLLBACK TO SAVEPOINT step_a;
~~~

Rolling back to `step_a` discards changes made after that marker, including the change at `step_b`. Savepoints created after the target marker are erased; the target savepoint itself can still be reused within the transaction. Savepoint names are scoped to the current transaction; reusing the same name replaces the earlier marker.

### Savepoints Are Not Nested Transactions

Oracle does not provide traditional nested transactions where a child transaction can commit independently inside a parent transaction. Savepoints only create rollback markers within the same transaction. Upon COMMIT, all remaining changes in the transaction are confirmed; upon a full ROLLBACK, all uncommitted changes are discarded.

## 6. DDL and Implicit Commit: Boundaries That Easily Cause Lost Changes

One of Oracle's most important rules is that **DDL causes an implicit commit**. For syntactically valid DDL, Oracle performs an implicit commit before running the DDL; if the DDL succeeds, Oracle performs an implicit commit after the DDL completes.

Common commands:

- `CREATE TABLE`, `CREATE INDEX`, `CREATE VIEW`.
- `ALTER TABLE`, `ALTER INDEX`.
- `DROP TABLE`, `DROP INDEX`.
- `TRUNCATE TABLE`.
- `GRANT`, `REVOKE`, and other DDL operations.

This means DDL can end a session's open DML transaction. Example:

~~~sql
UPDATE employees
SET salary = salary + 100
WHERE employee_id = 100;

CREATE TABLE lab_notes (
    note_id NUMBER PRIMARY KEY,
    note_text VARCHAR2(100)
);

ROLLBACK;
~~~

The UPDATE before `CREATE TABLE` was already implicitly committed before the DDL ran. Therefore, the final ROLLBACK **cannot undo** that salary change. If `CREATE TABLE` succeeds, the DDL is also committed upon completion.

### Failed DDL Can Still Have Committed Earlier DML

The pre-DDL commit rule must be kept in mind even when DDL fails to complete. If a DDL statement is syntactically valid but fails during execution, the preceding transaction may still have been committed at the pre-DDL step. Never rely on ROLLBACK after a DDL failure expecting to recover DML that was already implicitly committed.

### DELETE Differs from TRUNCATE

~~~sql
DELETE FROM staging_orders
WHERE load_date < DATE '2025-01-01';

ROLLBACK;
~~~

DELETE is DML; if not yet committed, it can be rolled back.

~~~sql
TRUNCATE TABLE staging_orders;
~~~

TRUNCATE is DDL; it triggers an implicit commit and cannot be rolled back like DELETE. Distinguish them clearly before running table cleanup operations.

| Operation | Classification | Can Be Rolled Back Before COMMIT? |
| --- | --- | --- |
| `INSERT` | DML | Yes |
| `UPDATE` | DML | Yes |
| `DELETE` | DML | Yes |
| `MERGE` | DML | Yes |
| `CREATE TABLE` | DDL | No, not under standard DML transaction semantics |
| `ALTER TABLE` | DDL | No, not under standard DML transaction semantics |
| `DROP TABLE` | DDL | No, not under standard DML transaction semantics |
| `TRUNCATE TABLE` | DDL | No, not under standard DML transaction semantics |
| `GRANT` / `REVOKE` | DDL in Oracle | No, not under standard DML transaction semantics |

Some administrative operations have specialized mechanisms, but never assume you can bundle ordinary DDL into a DML transaction and roll everything back. Complete or discard DML before running DDL.

### DDL in Deployment Scripts

~~~sql
UPDATE application_config
SET config_value = 'new'
WHERE config_key = 'mode';

ALTER TABLE orders ADD source_code VARCHAR2(20);

UPDATE orders
SET source_code = 'LEGACY'
WHERE source_code IS NULL;

COMMIT;
~~~

The config UPDATE may already have been implicitly committed before `ALTER TABLE`. If the second UPDATE fails, the final ROLLBACK cannot restore the config to its old value. Split migrations into steps with clear boundaries, recovery plans, and verification after each DDL.

## 7. Transaction Boundaries and Sessions

A transaction belongs to a **database session**, not to an individual SQL statement or an application variable. Each session has its current transaction, uncommitted changes, and locks held by that transaction.

### Two Sessions See Different Data

Suppose Session A runs:

~~~sql
UPDATE accounts
SET balance = 900
WHERE account_id = 'A';
~~~

Session A sees its own new value within that session. Session B running a standard SELECT before A commits still sees the previously committed version; B cannot read A's uncommitted value of 900.

When A runs:

~~~sql
COMMIT;
~~~

New queries in B under READ COMMITTED can see the committed value. A query in B that started before A's commit continues reading the consistent data image as of when that query began.

### Row Locks Are Held Until the Transaction Boundary

When updating a row, Oracle locks that row to prevent another session from performing conflicting overwrites. Locks are normally held until COMMIT or ROLLBACK:

~~~sql
UPDATE accounts
SET balance = balance - 50
WHERE account_id = 'A';

-- Row A remains locked in the transaction.
-- Not committed or rolled back yet.
~~~

Another session wanting to UPDATE the same row may have to wait. Transactions left open too long increase blocking, timeouts, and deadlock risk. Keep transactions short, and never wait for user input or call network services while holding locks.

### SELECT FOR UPDATE

If you need to read a row and then update it without letting another session modify it in between, you can use `SELECT ... FOR UPDATE`:

~~~sql
SELECT account_id, balance
FROM accounts
WHERE account_id = 'A'
FOR UPDATE;
~~~

Oracle locks the selected rows. The locks continue to be held until COMMIT/ROLLBACK. Options such as `NOWAIT`, `WAIT n`, or `SKIP LOCKED` alter how rows currently locked by another session are handled; choose based on business requirements, and do not use SKIP LOCKED if skipping rows would lose work that must be processed.

### Session Termination and Uncommitted Transactions

If a session is terminated abnormally, Oracle rolls back that session's uncommitted changes during cleanup/recovery. However, behavior when a client exits normally can depend on the client/driver: some applications auto-commit, some roll back, or require explicit handling. Do not rely on closing a window, closing a connection, or returning a connection to a pool to decide whether data gets committed.

Safe rule: the application must explicitly call COMMIT or ROLLBACK before returning a connection to the pool or ending a unit of work. Connection pools commonly reuse sessions; an unfinished transaction can cause subsequent requests to inherit unwanted state and locks.

## 8. Autocommit Is a Client Configuration

Oracle Database does not have a general rule that every DML statement auto-commits right after running. Auto-committing after each statement can happen because the client or driver enables **autocommit**.

For example, in JDBC, the auto-commit property typically defaults to true per the JDBC API; an application can turn it off to group multiple statements into a single transaction:

~~~java
connection.setAutoCommit(false);

try {
    updateDebit(connection);
    updateCredit(connection);
    connection.commit();
} catch (SQLException e) {
    connection.rollback();
    throw e;
}
~~~

If autocommit is enabled, each successful statement may be committed individually per driver mechanics. Two transfer UPDATEs would then no longer belong to one shared transaction. Check the actual configuration of your JDBC pool, ORM, or SQL tool.

In SQL Developer, SQL*Plus, Java applications, and ETL tools, autocommit state and connection-closing behavior can differ. Do not infer client behavior solely from Oracle SQL syntax.

## 9. Stored Procedures and the Caller's Transaction

A stored procedure runs in the caller's session. If the procedure does not execute COMMIT/ROLLBACK itself, DML inside the procedure joins the session's current transaction:

~~~sql
CREATE OR REPLACE PROCEDURE update_employee_name (
    p_employee_id IN NUMBER,
    p_new_name    IN VARCHAR2
) AS
BEGIN
    UPDATE employees
    SET employee_name = p_new_name
    WHERE employee_id = p_employee_id;
END;
/
~~~

The caller can orchestrate multiple steps:

~~~sql
BEGIN
    update_employee_name(100, 'New Name');
    update_employee_department(100, 20);
END;
/

-- The caller decides the transaction boundary.
COMMIT;
~~~

If a procedure executes COMMIT on its own, it ends the session's current transaction, including earlier changes made by the caller in the same transaction. That is why many business APIs keep the transaction boundary at the highest calling layer.

### An Exception Does Not Automatically Replace ROLLBACK

When an exception escapes a PL/SQL block, Oracle does not by default roll back the entire session transaction. The failed statement is handled via statement-level rollback; earlier changes may still be uncommitted. The caller needs to decide whether to roll back or continue.

Handling pattern:

~~~sql
BEGIN
    perform_step_one;
    perform_step_two;
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

This pattern fits if the block owns the entire transaction. If the block is part of a transaction managed by a caller, a full ROLLBACK can wipe out work done before calling the block. In that case, consider savepoints and clear caller/callee conventions; do not swallow exceptions without reporting the error.

## 10. Isolation Levels and Read Consistency

Transaction boundaries determine which changes are confirmed; the isolation level determines how a transaction sees concurrent changes from other sessions. Oracle supports these main modes:

| Mode | Data Image Read | Allows DML? |
| --- | --- | --- |
| READ COMMITTED (default) | Each SELECT reads committed data as of the time the statement begins, plus the transaction's own changes | Yes |
| SERIALIZABLE | Statements in the transaction read from a consistent image as of the time the transaction began, plus the transaction's own changes | Yes, but may encounter write-conflict errors |
| READ ONLY | Consistent image as of the time the transaction began | Disallows DML in the transaction |

Oracle never lets a session read another session's uncommitted data (dirty read). The default READ COMMITTED level provides **statement-level read consistency**; SERIALIZABLE and READ ONLY provide a transaction-level consistent image.

### READ COMMITTED: Oracle's Default

~~~sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM accounts
WHERE account_id = 'A';

-- Another session may commit changes here.

SELECT balance
FROM accounts
WHERE account_id = 'A';
~~~

Two separate SELECT statements can see two different committed versions if another session commits in between. This is not a dirty read: each query still reads a consistent image as of when that statement started.

This characteristic suits most OLTP applications because transactions are short and each statement sees freshly committed data. If a business process needs multiple SELECTs to read one stable snapshot, consider READ ONLY or SERIALIZABLE.

### SERIALIZABLE: Consistent Image for the Whole Transaction

~~~sql
COMMIT;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM accounts
WHERE account_id = 'A';

-- Subsequent queries still read the snapshot as of transaction start.
SELECT COUNT(*)
FROM accounts
WHERE status = 'ACTIVE';

COMMIT;
~~~

SERIALIZABLE fits when a unit of work requires consistent read results across multiple statements. If the transaction attempts to update a row modified by another transaction since the SERIALIZABLE transaction started, Oracle can raise `ORA-08177: can't serialize access for this transaction`. The application must handle this by rolling back and retrying the entire unit of work when business rules permit.

SERIALIZABLE does not mean all transactions execute physically sequentially. Oracle uses read consistency and conflict detection to ensure results equivalent to a valid serial order; the application must still handle conflict and constraint errors.

### READ ONLY: Read-Only on a Single Snapshot

~~~sql
COMMIT;
SET TRANSACTION READ ONLY;

SELECT department_id, SUM(salary)
FROM employees
GROUP BY department_id;

SELECT COUNT(*)
FROM orders
WHERE order_date >= DATE '2026-01-01';

COMMIT;
~~~

SELECTs in the transaction read the same consistent snapshot. You cannot run INSERT/UPDATE/DELETE in a READ ONLY transaction. This mode is useful for reports needing multiple queries without letting later queries see data committed midway through.

### Setting the Isolation Level at the Right Time

SET TRANSACTION statements must be the first statement of the transaction. If the session has an earlier transaction, finish it first:

~~~sql
COMMIT;
SET TRANSACTION READ ONLY;
~~~

Do not run a SELECT, DML, or another statement and then try to set the isolation level for that transaction. When the transaction ends, the transaction-level mode ends as well; the next transaction reverts to the default mode or whatever mode the application sets.

## 11. Locks and Deadlocks Related to Transaction Boundaries

Oracle uses row-level locking for DML. Two sessions can read the same row concurrently, but when both want to modify a row already locked by another session, one session must wait or receive an error depending on the statement and timeout.

### Blocking Example

Session A:

~~~sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 100;

-- Not committed yet.
~~~

Session B:

~~~sql
UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 100;
~~~

Session B can block waiting for Session A to end its transaction. When A COMMITs, B continues against the new data state; when A ROLLBACKs, B can proceed against the pre-change state. If A leaves the transaction open for a long time, B and other sessions can be blocked.

### Deadlock

A deadlock happens when two or more sessions hold locks that the other needs, forming a wait cycle. Example:

1. Session A locks account row A.
2. Session B locks account row B.
3. Session A wants to lock row B and must wait for B.
4. Session B wants to lock row A and must wait for A.

Oracle detects the deadlock and raises `ORA-00060: deadlock detected while waiting for resource`; the involved statement in one session is rolled back to break the cycle. The application must handle the error and decide whether to roll back the transaction/try again per business rules. Never assume all previous changes in the transaction were automatically rolled back as a whole.

### How to Reduce Blocking and Deadlocks

- Update rows in the same lock order across all business flows.
- Keep transactions short and commit/roll back promptly upon completion.
- Do not hold transactions open while waiting for input or calling external services.
- Use sufficiently selective WHERE conditions and appropriate indexes to avoid locking/reading unintended rows.
- Handle timeouts, deadlocks, and conflict errors with bounded retry logic.
- Do not automatically retry a non-idempotent operation without verifying whether the prior attempt could already have completed.

## 12. Behaviors Easily Confused with Transactions

### Sequence NEXTVAL Does Not Roll Back

Allocated sequence values are not DML changes that can be rolled back:

~~~sql
SELECT order_seq.NEXTVAL
FROM dual;

ROLLBACK;
~~~

Values already fetched from a sequence are not returned upon rollback. Therefore sequences can have gaps; do not use sequences to generate strictly contiguous document numbers if business rules prohibit gaps.

### DDL Can End a Caller's Transaction

A stored procedure or script invoking DDL can cause an implicit commit, even if the caller never wrote COMMIT. Therefore, never place DDL in the middle of a DML sequence while expecting the caller to roll everything back.

### COMMIT Inside a Procedure Affects the Session's Transaction

A procedure does not own its own ordinary transaction. COMMIT inside a procedure ends the session's current transaction, which may include changes the caller made before invoking the procedure. Transaction boundary conventions should be explicitly designed between the application layer and stored procedures.

### Autonomous Transactions Are a Deliberate Exception

PL/SQL supports autonomous transactions via the `AUTONOMOUS_TRANSACTION` pragma. This transaction is independent of the main transaction; it must COMMIT or ROLLBACK on its own:

~~~sql
CREATE OR REPLACE PROCEDURE write_error_log (
    p_message IN VARCHAR2
) AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO application_error_log(message, logged_at)
    VALUES (p_message, SYSTIMESTAMP);

    COMMIT;
END;
/
~~~

If the main transaction later ROLLBACKs, the autonomous transaction's log record remains because it committed independently. This is useful for error logs that must persist even when the business operation fails, but must be used deliberately: an autonomous transaction cannot see the main transaction's uncommitted changes and can cause contention/deadlocks if it tries to access resources locked by the main transaction.

An autonomous transaction is not a general-purpose way to "partially commit" a parent transaction. Savepoints suit partial rollback within the same transaction; an autonomous transaction is an independent transaction with its own lifecycle.

## 13. Transaction Management Patterns in Applications

A unit of work should have clear start and end points in the layer that owns the business operation.

### Pattern: Commit DML on Success or Roll Back on Error

~~~sql
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 'A'
      AND balance >= 100;

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Insufficient funds or account missing');
    END IF;

    UPDATE accounts
    SET balance = balance + 100
    WHERE account_id = 'B';

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(-20002, 'Destination account missing');
    END IF;

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

The example checks the updated row count on both sides. If either condition is not met, the exception sends execution into the handler and rolls back the entire transaction. In a real system, you must also validate distinct source/destination accounts, currency, transaction limits, auditing, idempotency, and retry handling.

### Pattern: Using a Savepoint for an Optional Step

~~~sql
UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = 500;

SAVEPOINT before_optional_note;

BEGIN
    INSERT INTO order_notes(order_id, note_text)
    VALUES (500, 'Optional note');
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO before_optional_note;
        -- Log the error or handle the optional branch.
END;

COMMIT;
~~~

This pattern preserves the order confirmation change while allowing the optional note step to be undone separately. If business rules require the note to be mandatory, do not swallow the error and still commit the order.

### Transaction Boundaries in JDBC

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        debitAccount(connection, sourceId, amount);
        creditAccount(connection, targetId, amount);
        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        connection.rollback();
        throw ex;
    }
}
~~~

In applications with a connection pool, return the connection to the pool in a clean state and restore connection settings if the application altered isolation/autocommit. Never assume closing a connection acts as a safe COMMIT.

## 14. Common Errors and How to Handle Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| ROLLBACK did not undo a prior UPDATE | A DDL statement implicitly committed the transaction before it | Identify DDL in the script; separate DML/DDL into clear deployment steps. |
| Two UPDATEs only partially committed | Client has autocommit enabled or a COMMIT occurred between statements | Check driver/client settings and set autocommit to false when a multi-statement transaction is needed. |
| Another session does not see newly UPDATEd data | Transaction has not COMMITted yet | Commit after the business unit of work finishes. |
| Another session blocks on UPDATE | Prior session holds a row lock with an unfinished transaction | End the transaction promptly; inspect sessions/blocking. |
| SET TRANSACTION raises an error | Another statement already ran in the transaction | Place SET TRANSACTION at the very start of the transaction, after finishing the prior transaction. |
| Procedure committed unwanted changes | COMMIT inside procedure ended the caller's transaction | Let the caller manage commit or define clear ownership. |
| DML error occurred but earlier changes remain | A failed statement does not auto-roll back the whole transaction | Handle the exception and roll back everything or roll back to a savepoint as required. |
| Cannot roll back TRUNCATE | TRUNCATE is DDL and performs an implicit commit | Use DELETE if rollback capability is needed; verify scope before running. |
| Sequence skipped numbers after rollback | NEXTVAL is non-transactional | Accept gaps; do not use sequences for strictly contiguous numbering. |
| ORA-08177 | Write conflict in SERIALIZABLE | Roll back and retry the entire transaction if safe. |
| ORA-00060 | Deadlock due to lock wait cycle | Standardize update order, keep transactions short, implement bounded retries. |
| Connection pool retains old transaction state | Connection returned while a transaction was still open | Always COMMIT/ROLLBACK and reset connection state before returning to the pool. |

## 15. Comprehensive Hands-On Lab

Run this in a study schema with `CREATE TABLE` privilege and sufficient quota. DDL triggers an implicit commit in Oracle; do not run table creation/deletion commands on a live business schema.

### Step 1: Create the Accounts Table

~~~sql
CREATE TABLE lab_accounts (
    account_id VARCHAR2(10) PRIMARY KEY,
    balance    NUMBER(12,2) NOT NULL
);

INSERT INTO lab_accounts VALUES ('A', 1000);
INSERT INTO lab_accounts VALUES ('B', 500);
COMMIT;
~~~

### Step 2: Execute DML and Then ROLLBACK

~~~sql
UPDATE lab_accounts
SET balance = balance - 100
WHERE account_id = 'A';

SELECT account_id, balance
FROM lab_accounts
ORDER BY account_id;

ROLLBACK;

SELECT account_id, balance
FROM lab_accounts
ORDER BY account_id;
~~~

Observe the values in the same session before and after rollback. After ROLLBACK, the balance returns to the previously committed state.

### Step 3: Execute Two Changes and Then COMMIT

~~~sql
UPDATE lab_accounts
SET balance = balance - 100
WHERE account_id = 'A';

UPDATE lab_accounts
SET balance = balance + 100
WHERE account_id = 'B';

COMMIT;
~~~

Check the total balance of both accounts before and after. Total balance must be preserved in this example.

### Step 4: Use SAVEPOINT

~~~sql
UPDATE lab_accounts
SET balance = balance - 50
WHERE account_id = 'A';

SAVEPOINT after_debit;

UPDATE lab_accounts
SET balance = balance + 50
WHERE account_id = 'B';

ROLLBACK TO SAVEPOINT after_debit;

SELECT account_id, balance
FROM lab_accounts
ORDER BY account_id;

ROLLBACK;
~~~

Observe: the change before the savepoint remains in the transaction after ROLLBACK TO SAVEPOINT; the final ROLLBACK cancels the entire transaction.

### Step 5: Demonstrate That DDL Triggers Implicit Commit

~~~sql
UPDATE lab_accounts
SET balance = balance + 10
WHERE account_id = 'A';

CREATE TABLE lab_ddl_marker (
    marker_id NUMBER PRIMARY KEY
);

ROLLBACK;

SELECT account_id, balance
FROM lab_accounts
WHERE account_id = 'A';
~~~

The UPDATE before `CREATE TABLE` was implicitly committed. Thus the final ROLLBACK does not revert balance to the old value. Do not run this example on real data.

### Step 6: Test Read Consistency with Two Sessions

Open two separate sessions in your SQL client.

Session A:

~~~sql
UPDATE lab_accounts
SET balance = 700
WHERE account_id = 'A';

-- Not committed yet.
~~~

Session B:

~~~sql
SELECT balance
FROM lab_accounts
WHERE account_id = 'A';
~~~

Session B reads the previously committed value, not A's uncommitted 700. After A COMMITs, run a new SELECT in B to observe the committed value.

### Step 7: Observe Blocking

Session A:

~~~sql
UPDATE lab_accounts
SET balance = balance + 1
WHERE account_id = 'A';

-- Keep transaction open.
~~~

Session B:

~~~sql
UPDATE lab_accounts
SET balance = balance + 1
WHERE account_id = 'A';
~~~

Observe B waiting on the lock. Switch back to A and run COMMIT or ROLLBACK; B will proceed according to the outcome of A's transaction.

### Step 8: Clean Up Lab Tables

~~~sql
DROP TABLE lab_ddl_marker PURGE;
DROP TABLE lab_accounts PURGE;
~~~

Only run this once you finish the lesson and no longer need the data. DROP TABLE is DDL with an implicit commit; PURGE bypasses the Recycle Bin.

## 16. Self-Check Questions

1. **When does a transaction in Oracle usually start?** When the session executes its first data-modifying operation after the previous transaction boundary; special transaction modes must be set before the first statement.
2. **Do you need to write BEGIN TRANSACTION in Oracle SQL?** No; DML transactions are managed implicitly per session.
3. **Do PL/SQL BEGIN/END auto-commit?** No; they are block boundaries, not transaction boundaries.
4. **Which changes does COMMIT confirm?** All uncommitted changes in the session's current transaction.
5. **What does ROLLBACK without a savepoint do?** Discards all uncommitted changes of the current transaction and ends the transaction.
6. **Does ROLLBACK TO SAVEPOINT end the transaction?** No; it discards changes after the savepoint and the transaction continues.
7. **Why is DDL dangerous when uncommitted DML exists?** DDL triggers an implicit commit before running and commits after succeeding.
8. **How do DELETE and TRUNCATE differ regarding transactions?** DELETE is DML and can be rolled back before commit; TRUNCATE is DDL and causes an implicit commit.
9. **Does a standard SELECT lock rows?** No; standard SELECT reads via read consistency, whereas SELECT FOR UPDATE locks the selected rows.
10. **How long are row locks held?** Normally until COMMIT or ROLLBACK of the transaction holding the locks.
11. **Does autocommit belong to the Oracle server or the client?** It is a client/driver setting; check the actual tool or connection pool configuration.
12. **At what level does READ COMMITTED read a snapshot?** Each statement reads a consistent image as of the time that statement starts.
13. **How does SERIALIZABLE differ from READ COMMITTED?** Statements in a SERIALIZABLE transaction use a consistent image as of transaction start; write conflicts can raise ORA-08177.
14. **Does READ ONLY allow DML?** No; it provides a consistent snapshot for reading within the transaction.
15. **Does sequence NEXTVAL roll back?** No; already issued values are not returned upon rollback.
16. **How does a procedure containing COMMIT affect its caller?** It ends the session's current transaction, including changes made by the caller before calling the procedure.
17. **How does an autonomous transaction differ from a savepoint?** An autonomous transaction is independent with its own commit/rollback; a savepoint is just a rollback marker within the parent transaction.
18. **Is closing a connection a safe way to commit?** No; behavior depends on the client/driver. Applications must explicitly commit/roll back before returning a connection.

Transaction boundaries in Oracle are determined primarily by COMMIT, ROLLBACK, and operations like DDL that trigger implicit commits. DML transactions usually begin implicitly within a session, while SET TRANSACTION must be placed right at the start of a transaction when special isolation is required. Manage transactions in the layer that owns the business unit, keep transactions short, handle errors explicitly, and verify client autocommit settings. Above all, never let a DDL statement, a self-committing procedure, or a connection pool accidentally terminate or carry over a transaction your application did not intend.
