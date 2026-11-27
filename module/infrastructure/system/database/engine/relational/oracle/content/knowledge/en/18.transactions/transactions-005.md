# Statement-Level Atomicity and Transaction-Level Atomicity

Oracle Database processes data changes across two critical boundaries: **statement-level atomicity** and **transaction-level atomicity**. The two concepts are related, yet not identical. A single DML statement can fail and be rolled back on its own, while preceding successful DML statements remain inside the transaction awaiting a COMMIT or ROLLBACK decision.

Understanding both boundaries helps prevent severe bugs such as debiting a source account without crediting the destination account, writing partial data when an application encounters an error, or accidentally COMMITting earlier work when running DDL. This lesson explains how Oracle protects a single statement, how multiple statements are grouped into a transaction, how SAVEPOINT works, and how JDBC/PLSQL applications control transaction boundaries.

## 1. Atomicity in ACID

ACID is the four properties commonly used to describe a database transaction:

| Property | Meaning |
|---|---|
| Atomicity | A transaction is executed completely or rolled back according to transaction boundaries |
| Consistency | A transaction moves data from one valid state to another valid state according to constraints and rules |
| Isolation | Concurrent transactions do not see intermediate states in ways that violate the isolation level |
| Durability | After a successful COMMIT, changes are durably stored via Oracle's recovery mechanism |

Atomicity answers the question: **if part of the work fails, which part is kept and which part must be undone?**

In Oracle, we must distinguish:

- **Statement-level atomicity:** a DML statement succeeds in full, or the changes of that statement itself are undone.
- **Transaction-level atomicity:** a group of statements belonging to the same transaction are COMMITted together or ROLLBACKed together.

For example, a money transfer transaction might include:

1. Debit 500,000 VND from account A.
2. Credit 500,000 VND to account B.
3. Insert one transaction log row.

If step 2 fails, transaction-level atomicity requires that step 1 must also be undone before the transaction ends. Relying solely on statement-level atomicity means Oracle only undoes the failed statement in step 2; the debit statement in step 1 remains as a pending change in the transaction.

## 2. Statement-Level Atomicity: One DML Statement Is One Unit

Oracle guarantees atomicity for each individual DML statement. Before executing DML, Oracle places an **implicit statement savepoint** (an internal savepoint for the statement). If the statement fails, Oracle undoes the changes created by that statement back to this point.

Example:

~~~sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 10;
~~~

If the statement succeeds, the quantity change on matching rows becomes part of the current transaction. If the statement fails due to a constraint error, trigger error, or another execution error, Oracle undoes the changes of that statement.

Key point: the internal rollback of a failed DML statement **is not equivalent to rolling back the entire transaction**.

### 2.1 A Multi-Row UPDATE Is Still One Statement

Suppose a table has a constraint:

~~~sql
CREATE TABLE lab_salary (
    employee_id NUMBER PRIMARY KEY,
    salary      NUMBER(12,2),
    CONSTRAINT ck_lab_salary CHECK (salary <= 200000)
);

INSERT INTO lab_salary VALUES (1, 100000);
INSERT INTO lab_salary VALUES (2, 150000);
INSERT INTO lab_salary VALUES (3, 190000);
COMMIT;
~~~

Attempt to give all employees a 10% raise:

~~~sql
UPDATE lab_salary
SET salary = salary * 1.10;
~~~

The third row will exceed the CHECK limit. When the UPDATE fails due to the constraint, Oracle undoes **all changes of that UPDATE statement**. The first two rows do not retain the new salary merely because they were processed before the third row.

Verify:

~~~sql
SELECT employee_id, salary
FROM lab_salary
ORDER BY employee_id;
~~~

The values remain 100,000, 150,000, and 190,000 as before the UPDATE. If the transaction had earlier successful DML statements, those earlier changes remain pending and can be COMMITted or ROLLBACKed separately.

### 2.2 Statement Savepoints Are Internal

Oracle creates statement savepoints automatically for DML so it can undo a failed statement. Users do not name, query, or directly use this implicit savepoint in SQL.

It differs from an application-created savepoint:

~~~sql
SAVEPOINT before_update;
~~~

`SAVEPOINT` has a user-managed name and allows returning to a position inside a transaction. An implicit statement savepoint is Oracle's internal mechanism for protecting a single statement.

### 2.3 Changes Made by Triggers Also Belong to the Triggering Statement

If a normal trigger performs INSERT/UPDATE/DELETE on another table within the same transaction, those changes belong to the work of the statement firing the trigger. If the original statement fails and Oracle rolls it back, transactional changes made by the trigger are rolled back as well.

Example:

~~~sql
CREATE TABLE lab_salary_audit (
    employee_id NUMBER,
    old_salary  NUMBER(12,2),
    new_salary  NUMBER(12,2),
    changed_at  TIMESTAMP DEFAULT SYSTIMESTAMP
);

CREATE OR REPLACE TRIGGER trg_lab_salary_audit
AFTER UPDATE OF salary ON lab_salary
FOR EACH ROW
BEGIN
    INSERT INTO lab_salary_audit (
        employee_id, old_salary, new_salary
    )
    VALUES (
        :NEW.employee_id, :OLD.salary, :NEW.salary
    );
END;
/
~~~

If an UPDATE fires the trigger for multiple rows and then the statement fails, audit rows inserted by the normal trigger are also rolled back together with the UPDATE. This prevents the business table and audit table within the same transaction from drifting out of sync just because a DML statement failed.

The key requirement is that the trigger does not use an independent transaction mechanism or external side effects outside the transaction. Autonomous transactions and external systems are explained later.

## 3. What Happens When a Statement Fails?

Suppose a transaction has three statements:

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 20;

INSERT INTO transfer_log (
    transfer_id, from_account, to_account, amount
)
VALUES (9001, 10, 20, 100);
~~~

If the final INSERT fails due to a duplicate primary key:

- The changes of that INSERT statement are undone.
- The two preceding UPDATEs remain uncommitted changes in the transaction.
- The application can fix the cause and continue, or ROLLBACK the entire transaction.

Oracle does not automatically infer that an error in the INSERT means the whole money transfer business operation must be cancelled. Transaction boundaries are controlled by the application or caller via COMMIT/ROLLBACK.

### 3.1 Comparison Table

| Event | What Oracle Automatically Undoes | Transaction State |
|---|---|---|
| An INSERT fails | Changes of that INSERT statement | Remains open if not yet COMMITted/ROLLBACKed |
| A multi-row UPDATE fails | All changes of that UPDATE statement | Earlier successful DML statements remain pending |
| A DELETE fails | Changes of that DELETE statement | Remains open if not yet ended |
| Application calls ROLLBACK | All uncommitted changes in the transaction | Ends the transaction |
| Application calls COMMIT | Confirms all changes in the transaction | Ends the transaction |
| ROLLBACK TO SAVEPOINT | Changes after the specified savepoint | Transaction remains open |

### 3.2 Do Not Infer the Whole Transaction State From One Statement Error

After catching an exception, the application needs to know:

- Which statement failed?
- Which DML statements did the transaction execute earlier?
- Were any business savepoints placed?
- Do business rules require cancelling the entire transaction or only skipping part of it?
- Did any DDL or client autocommit create a commit boundary?

If the application merely logs the error and continues running subsequent statements, the changes made before the error can still get COMMITted later. This is a common cause of half-finished data states when exceptions are mishandled.

## 4. Transaction-Level Atomicity: Grouping Statements into a Business Unit

A transaction can consist of multiple SQL statements:

~~~sql
UPDATE accounts
SET balance = balance - 500
WHERE account_id = 101;

UPDATE accounts
SET balance = balance + 500
WHERE account_id = 202;

INSERT INTO transfer_log (
    transfer_id, from_account, to_account, amount
)
VALUES (5001, 101, 202, 500);

COMMIT;
~~~

When COMMIT succeeds, the transaction's changes are confirmed together. If an error occurs before COMMIT and business rules require cancelling everything, the application calls ROLLBACK:

~~~sql
ROLLBACK;
~~~

ROLLBACK undoes all changes of the current transaction since the transaction started or the most recent COMMIT/ROLLBACK. It does not undo data already COMMITted in a previous transaction.

### 4.1 COMMIT

`COMMIT`:

- Confirms pending DML changes of the transaction.
- Makes the changes committed data.
- Ends the current transaction.
- Releases transaction locks per Oracle rules.
- Clears the transaction's savepoints.

Example:

~~~sql
UPDATE products
SET price = price * 1.05
WHERE category_id = 10;

COMMIT;
~~~

After COMMIT, a subsequent ROLLBACK cannot reverse the committed UPDATE. To revert it, you need a new transaction writing a compensating value or an appropriate recovery mechanism.

### 4.2 ROLLBACK

`ROLLBACK` without a savepoint:

~~~sql
UPDATE products
SET price = price * 1.05
WHERE category_id = 10;

DELETE FROM promotions
WHERE end_date < DATE '2026-01-01';

ROLLBACK;
~~~

Both the uncommitted UPDATE and DELETE are undone. The transaction ends; its savepoints are also lost.

### 4.3 COMMIT Is Not Just "Save the Last Statement"

COMMIT applies to **the entire current transaction**, not just the most recent DML statement. If an application ran five UPDATE statements and then executed COMMIT, all five uncommitted successful statements are confirmed.

Therefore, a misplaced COMMIT inside a stored procedure, deployment script, or application flow can commit the caller's earlier work as well if they share the same transaction/session.

## 5. SAVEPOINT and ROLLBACK TO SAVEPOINT

You do not always want to discard the entire transaction. SAVEPOINT marks a position so you can roll back partially:

~~~sql
UPDATE orders
SET status = 'READY'
WHERE order_id = 1001;

SAVEPOINT before_shipping;

INSERT INTO shipments (
    shipment_id, order_id, status
)
VALUES (7001, 1001, 'CREATED');

UPDATE inventory
SET reserved_qty = reserved_qty + 1
WHERE product_id = 55;

ROLLBACK TO SAVEPOINT before_shipping;
~~~

After `ROLLBACK TO SAVEPOINT before_shipping`:

- The shipment INSERT is undone.
- The inventory UPDATE is undone.
- The orders UPDATE before the savepoint remains pending in the transaction.
- The transaction has not ended; the application can continue or COMMIT/ROLLBACK afterward.

### 5.1 SAVEPOINT Does Not End the Transaction

`ROLLBACK TO SAVEPOINT` differs from `ROLLBACK`:

| Command | Scope | Transaction Still Open? |
|---|---|---|
| `ROLLBACK` | All uncommitted changes | No |
| `ROLLBACK TO SAVEPOINT s` | Changes after savepoint `s` | Yes |
| `COMMIT` | Confirms all uncommitted changes | No |
| `SAVEPOINT s` | Sets a rollback point | Yes |

A savepoint is not a nested transaction. Oracle does not create an independent transaction whenever it encounters SAVEPOINT.

### 5.2 Savepoints with the Same Name

If you create a new savepoint with the same name as an old savepoint, the old savepoint of that name is replaced. When rolling back to a savepoint, savepoints created after that point are erased; the target savepoint itself can still be reused until the transaction ends or it is replaced.

### 5.3 Full COMMIT and ROLLBACK Clear Savepoints

After a full COMMIT or ROLLBACK, the transaction ends and old savepoints are no longer valid. You cannot use a savepoint from a previous transaction to roll back a new transaction.

## 6. Business Example: Transferring Money Between Two Accounts

The money transfer problem must guarantee:

1. The source account exists and has sufficient balance.
2. The destination account exists.
3. Money is debited only if it can be credited to the destination account.
4. The transfer log is recorded in the same transaction.
5. If any mandatory step fails, all changes of the transfer must be undone.

### 6.1 Sample Tables

~~~sql
CREATE TABLE lab_accounts (
    account_id NUMBER(10) PRIMARY KEY,
    balance    NUMBER(14,2) NOT NULL,
    CONSTRAINT ck_lab_account_balance CHECK (balance >= 0)
);

CREATE TABLE lab_transfer_log (
    transfer_id   NUMBER(12) PRIMARY KEY,
    from_account  NUMBER(10) NOT NULL,
    to_account    NUMBER(10) NOT NULL,
    amount        NUMBER(14,2) NOT NULL,
    created_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT ck_lab_transfer_positive CHECK (amount > 0)
);

INSERT INTO lab_accounts VALUES (101, 2000);
INSERT INTO lab_accounts VALUES (202, 1000);
COMMIT;
~~~

### 6.2 Writing Multiple Statements and Checking Row Counts

PL/SQL example:

~~~sql
DECLARE
    l_amount NUMBER(14,2) := 500;
BEGIN
    SAVEPOINT transfer_start;

    UPDATE lab_accounts
    SET balance = balance - l_amount
    WHERE account_id = 101
      AND balance >= l_amount;

    IF SQL%ROWCOUNT <> 1 THEN
        ROLLBACK TO transfer_start;
        RAISE_APPLICATION_ERROR(
            -20001,
            'Source account does not exist or has insufficient balance'
        );
    END IF;

    UPDATE lab_accounts
    SET balance = balance + l_amount
    WHERE account_id = 202;

    IF SQL%ROWCOUNT <> 1 THEN
        ROLLBACK TO transfer_start;
        RAISE_APPLICATION_ERROR(
            -20002,
            'Destination account does not exist'
        );
    END IF;

    INSERT INTO lab_transfer_log (
        transfer_id, from_account, to_account, amount
    )
    VALUES (5001, 101, 202, l_amount);

    -- The caller decides COMMIT after the business operation completes.
END;
/
~~~

This example shows:

- Each UPDATE/INSERT has its own statement-level atomicity.
- SAVEPOINT creates a boundary to undo only the changes of this transfer.
- When a step does not satisfy a condition, ROLLBACK TO SAVEPOINT undoes the transfer work done so far.
- When all steps succeed, the caller still needs to COMMIT to confirm the transaction.

If the PL/SQL block is called inside a transaction that already has prior work, the savepoint enables rolling back the transfer while keeping work before the savepoint. If the requirement is to cancel the entire transaction, the caller can issue a full ROLLBACK.

### 6.3 Why Check SQL%ROWCOUNT?

An UPDATE statement can succeed without error yet still update 0 rows:

~~~sql
UPDATE lab_accounts
SET balance = balance + 500
WHERE account_id = 999;
~~~

Without account 999, the statement succeeds at the SQL level, but `SQL%ROWCOUNT` equals 0. Oracle does not raise an error merely because no rows matched. The application must decide whether 0 rows is valid or not.

### 6.4 Exception Handling and Rollback

You can add an exception handler:

~~~sql
DECLARE
    l_amount NUMBER(14,2) := 500;
BEGIN
    SAVEPOINT transfer_start;

    UPDATE lab_accounts
    SET balance = balance - l_amount
    WHERE account_id = 101
      AND balance >= l_amount;

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Insufficient source balance');
    END IF;

    UPDATE lab_accounts
    SET balance = balance + l_amount
    WHERE account_id = 202;

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(-20002, 'Destination account not found');
    END IF;

    INSERT INTO lab_transfer_log (
        transfer_id, from_account, to_account, amount
    )
    VALUES (5002, 101, 202, l_amount);

EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO transfer_start;
        RAISE;
END;
/
~~~

The handler rolls back to the savepoint and re-raises the error so the caller knows the transfer failed. Never swallow the exception and return a fake success status. The caller needs to decide whether to continue the transaction or perform a full rollback.

In production code, you must determine how transfer IDs are generated, handle retries, lock accounts, and check balances under concurrency requirements. The example above illustrates atomic boundaries, not a replacement for duplicate-transaction protection or reconciliation workflows.

## 7. Statement Atomicity Does Not Replace Concurrency Control

Atomicity ensures a single statement does not leave partial changes behind when that statement fails. It does not automatically solve all race conditions between multiple sessions.

For example, two sessions both read a balance of 500 and both decide to transfer 400. If the application reads the balance in a separate SELECT and then issues an unconditional UPDATE, both sessions may make decisions based on stale data.

One way to reduce risk is to put the business condition directly in the UPDATE itself:

~~~sql
UPDATE lab_accounts
SET balance = balance - :amount
WHERE account_id = :account_id
  AND balance >= :amount;
~~~

Then check `SQL%ROWCOUNT`. Oracle locks the updated row; concurrent transactions must obey Oracle's locking and read-consistency mechanisms. For complex business operations that must read multiple rows before deciding, `SELECT ... FOR UPDATE` can lock the relevant rows within the transaction.

Atomicity, isolation, and locking are related, yet answer different questions:

- Atomicity: within what scope are changes undone?
- Isolation: how do concurrent transactions see data?
- Locking: which session can modify a row currently locked by another session?

## 8. Transaction Boundaries in SQL*Plus and SQL Tools

Oracle Database manages transactions on the server. Client tools can influence that boundary via autocommit settings.

### 8.1 Autocommit Disabled

In a standard SQL*Plus session, DML is normally kept pending until the user issues COMMIT or ROLLBACK, unless configuration/autocommit changes:

~~~sql
UPDATE lab_accounts
SET balance = balance - 100
WHERE account_id = 101;

UPDATE lab_accounts
SET balance = balance + 100
WHERE account_id = 202;

-- Not committed yet: changes still belong to the current transaction.
ROLLBACK;
~~~

Both UPDATEs are undone.

### 8.2 Autocommit Enabled

Some clients provide an autocommit option or corresponding configuration command. When enabled, the client may COMMIT after every successful DML statement. In that case:

1. The first UPDATE finishes and is committed.
2. The second UPDATE becomes a separate transaction.
3. If the second UPDATE fails, the first UPDATE remains committed.

This breaks the intent of grouping multiple statements into one business transaction. When a multi-step transaction is needed, explicitly verify the tool's autocommit setting.

Menu names and autocommit defaults vary across SQL Developer, SQLcl, SQL*Plus, and third-party tools. Do not infer behavior merely by clicking Run; check the session/client settings.

### 8.3 DDL Has Implicit COMMIT

DDL commands such as CREATE, ALTER, DROP, and TRUNCATE have implicit commit rules in Oracle. DDL typically commits the current transaction before executing; successful DDL also commits after executing.

Example:

~~~sql
UPDATE lab_accounts
SET balance = balance + 100
WHERE account_id = 101;

CREATE TABLE lab_temp_note (
    note_id NUMBER
);

ROLLBACK;
~~~

The UPDATE before DDL may already have been committed by the implicit commit before `CREATE TABLE` ran. The final ROLLBACK cannot undo that UPDATE. This is why you should not mix DDL into the middle of a business transaction requiring atomicity.

If the DDL fails, the implicit commit before execution may still have ended the preceding transaction. Never use DDL as a "trial" operation inside a transaction when you expect to roll everything back on error.

## 9. Transactions in PL/SQL

A PL/SQL block, procedure, or function runs inside the calling session's transaction unless the code explicitly controls transactions. A procedure finishing normally does not automatically mean the transaction has COMMITted.

Example of a procedure performing only DML:

~~~sql
CREATE OR REPLACE PROCEDURE update_product_price (
    p_product_id IN NUMBER,
    p_new_price  IN NUMBER
) AS
BEGIN
    UPDATE products
    SET price = p_new_price
    WHERE product_id = p_product_id;
END;
/
~~~

The caller can do:

~~~sql
BEGIN
    update_product_price(10, 250);
    -- Execute additional business steps.
    COMMIT;
END;
/
~~~

If the procedure calls COMMIT on its own, it will commit all pending changes in the same transaction/session, including changes made by the caller before calling the procedure. Therefore, transaction ownership must be explicitly designed.

### 9.1 An Exception Does Not Automatically Mean Full Rollback

When DML inside PL/SQL fails, Oracle applies statement-level atomicity to that DML. Preceding successful DML in the same transaction may still remain pending. An exception handler can:

- `ROLLBACK TO SAVEPOINT` to undo partially.
- `ROLLBACK` to undo the entire transaction.
- Handle the error and continue if business rules permit.
- Re-raise the exception for the caller to decide.

Avoid writing:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        NULL;
~~~

if doing so leaves the caller unaware that the operation failed. Swallowing errors can allow the application to continue and COMMIT pre-error changes in an incomplete business state.

### 9.2 COMMIT Inside Stored Procedures

A procedure reused across multiple business flows should normally let the caller manage the transaction, unless the procedure's contract explicitly defines it as a self-committing unit. Placing COMMIT arbitrarily inside a procedure makes it hard for callers to combine the procedure atomically with other steps.

If a procedure requires an independent log entry that persists even when the main transaction rolls back, that is a distinct requirement and must be deliberately designed using an autonomous transaction or an appropriate logging system; never use stray COMMITs to achieve that effect.

## 10. Transactions in JDBC

JDBC provides an API to control autocommit, commit, and rollback.

### 10.1 Default Autocommit

Per JDBC, a new connection typically starts in autocommit mode. When autocommit is enabled, each SQL statement is committed upon completion. To place multiple statements in the same transaction, the application must disable autocommit.

~~~java
Connection connection = dataSource.getConnection();

try {
    connection.setAutoCommit(false);

    try (PreparedStatement debit = connection.prepareStatement(
            "UPDATE accounts " +
            "SET balance = balance - ? " +
            "WHERE account_id = ? AND balance >= ?")) {
        debit.setBigDecimal(1, amount);
        debit.setLong(2, sourceAccountId);
        debit.setBigDecimal(3, amount);

        int updated = debit.executeUpdate();
        if (updated != 1) {
            throw new SQLException("Source account missing or insufficient");
        }
    }

    try (PreparedStatement credit = connection.prepareStatement(
            "UPDATE accounts SET balance = balance + ? WHERE account_id = ?")) {
        credit.setBigDecimal(1, amount);
        credit.setLong(2, destinationAccountId);

        int updated = credit.executeUpdate();
        if (updated != 1) {
            throw new SQLException("Destination account not found");
        }
    }

    try (PreparedStatement log = connection.prepareStatement(
            "INSERT INTO transfer_log " +
            "(transfer_id, from_account, to_account, amount) " +
            "VALUES (?, ?, ?, ?)")) {
        log.setLong(1, transferId);
        log.setLong(2, sourceAccountId);
        log.setLong(3, destinationAccountId);
        log.setBigDecimal(4, amount);
        log.executeUpdate();
    }

    connection.commit();
} catch (SQLException | RuntimeException ex) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        ex.addSuppressed(rollbackError);
    }
    throw ex;
} finally {
    connection.close();
}
~~~

This example shows a transaction comprising a debit, a credit, and a log insert. If any step fails, the catch block calls rollback to discard all uncommitted changes in the transaction. `setAutoCommit(false)` is the crucial step ensuring the statements truly share the same transaction.

In production code using a connection pool, follow the pool/framework's conventions for returning connections, resetting state, and handling rollback errors. Never alter autocommit arbitrarily or return a connection to the pool with an unhandled transaction.

Do not unconditionally call §setAutoCommit(true)§ in §finally§ after a rollback that might have failed: JDBC may commit the current transaction when toggling autocommit from false to true. Handle the commit/rollback outcome first, then let the connection pool reset state per its configuration or perform the reset only once the transaction is confirmed closed.

### 10.2 Forgetting setAutoCommit(false)

When autocommit remains enabled:

~~~java
connection.setAutoCommit(true);
debitStatement.executeUpdate();   // may already be committed
creditStatement.executeUpdate();  // separate transaction
~~~

If credit fails, a subsequent rollback cannot reverse the already committed debit. Each statement has statement atomicity, but the transfer operation lacks the intended transaction atomicity.

### 10.3 Do Not Commit on Every Small Successful Branch

In a multi-step business flow, commit only at the boundary where the entire business unit is considered complete. If a helper method commits on its own after updating one table, the caller cannot roll back that helper when a later step fails.

## 11. SAVEPOINT in JDBC

JDBC provides an API to create and roll back to savepoints:

~~~java
Savepoint beforeShipping = connection.setSavepoint("before_shipping");

try {
    createShipment(connection, orderId);
    reserveInventory(connection, productId);
} catch (SQLException ex) {
    connection.rollback(beforeShipping);
    throw ex;
}

// Transaction stays open; the caller still decides commit or rollback.
~~~

`connection.rollback(savepoint)` only rolls back changes made after the savepoint. It does not commit the work before the savepoint and does not end the transaction. Afterward, the caller can continue or roll back everything.

Not every driver, database, or connection mode supports all savepoint features identically. With Oracle JDBC, use the same connection owning the transaction and handle `SQLException` appropriately.

## 12. DML Error Logging: Deliberately Allowing Partial Row Success

Statement-level atomicity is the default behavior when a DML statement fails. However, Oracle provides **DML error logging** allowing certain row-level errors to be recorded in an error table while the DML statement continues processing other rows.

This is a deliberate mechanism for loading imperfect data. Distinguish:

- Without error logging: a DML error fails the statement and the statement's changes are rolled back.
- With error logging: rows failing with supported errors can be written to an error table; valid rows are still processed, and the statement can complete successfully.

### 12.1 Create an Error Logging Table

~~~sql
BEGIN
    DBMS_ERRLOG.CREATE_ERROR_LOG(
        dml_table_name      => 'ORDERS',
        err_log_table_name  => 'ERR$_ORDERS'
    );
END;
/
~~~

The procedure creates a table storing error details for the target table. Create the error table in an appropriate schema and verify access privileges.

### 12.2 INSERT with LOG ERRORS

~~~sql
INSERT INTO orders (
    order_id, customer_id, order_amount
)
SELECT order_id, customer_id, order_amount
FROM staging_orders
LOG ERRORS INTO err$_orders ('BATCH_20261114')
REJECT LIMIT UNLIMITED;
~~~

Valid rows can be inserted; rows encountering errors are written to the error table within the scope of errors supported by DML error logging. Afterward, the application can inspect:

~~~sql
SELECT ora_err_number$,
       ora_err_mesg$,
       ora_err_tag$,
       order_id,
       customer_id
FROM err$_orders
WHERE ora_err_tag$ = 'BATCH_20261114';
~~~

Both successful changes and error log records remain in the current transaction. If the transaction ROLLBACKs, both are rolled back; if it COMMITs, both the loaded data and error logs are confirmed.

### 12.3 Error Logging Does Not Apply to Every Error

DML error logging has restrictions regarding error types, operations, columns, and table structures. Certain errors such as syntax errors, space/initialization errors, specific constraints, or errors occurring in certain execution paths may not be handled as row-level errors. Consult the SQL Language Reference for your target version before designing a data-loading pipeline.

Do not use `LOG ERRORS` if business rules require all rows to succeed or all to be cancelled. In that case, let the statement/transaction fail and roll back the proper scope.

## 13. FORALL SAVE EXCEPTIONS in PL/SQL

For bulk DML in PL/SQL, `FORALL ... SAVE EXCEPTIONS` lets remaining DML executions continue when some iterations fail and collects errors in `SQL%BULK_EXCEPTIONS`.

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF NUMBER;
    l_ids id_list_t := id_list_t(10, 20, 30);

    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
        UPDATE products
        SET price = price * 1.05
        WHERE product_id = l_ids(i);

EXCEPTION
    WHEN e_bulk_errors THEN
        FOR j IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Index=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_INDEX ||
                ', Error=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_CODE
            );
        END LOOP;
        -- The COMMIT/ROLLBACK decision belongs to the application's transaction logic.
END;
/
~~~

`SAVE EXCEPTIONS` is an error-handling mechanism for bulk iterations; it does not automatically decide whether business logic should keep successful iterations or cancel the entire transaction. The application must read the error list, verify valid data, and decide COMMIT/ROLLBACK. Do not confuse it with a transaction `SAVEPOINT`.

## 14. Constraints Can Be Checked at COMMIT Time

Oracle allows certain constraints to be declared `DEFERRABLE`. When a constraint is set to `DEFERRED` mode, validation can be postponed until COMMIT time instead of being enforced immediately after each statement.

Example of a deferrable foreign key:

~~~sql
ALTER TABLE child_orders
ADD CONSTRAINT fk_child_parent
FOREIGN KEY (parent_id)
REFERENCES parent_orders(parent_id)
DEFERRABLE INITIALLY IMMEDIATE;
~~~

Inside a transaction:

~~~sql
SET CONSTRAINTS fk_child_parent DEFERRED;

-- Perform temporary changes that may violate the relationship
-- during transition, as long as everything is valid at COMMIT.

COMMIT;
~~~

If a deferred constraint is still violated at COMMIT time, COMMIT does not complete successfully. The application must fix the state or ROLLBACK according to business rules. This shows that errors can surface at the transaction-ending boundary even when every individual DML statement succeeded.

Not all constraints can be deferred; syntax and applicability depend on constraint type. Check the constraint definition and current state before using it.

## 15. DDL and Implicit COMMIT: An Important Exception When Discussing Transactions

In Oracle, DDL normally creates an implicit commit boundary. Commands such as CREATE, ALTER, DROP, TRUNCATE, and CREATE INDEX can commit an open transaction before the DDL executes; successful DDL also commits after execution.

Example:

~~~sql
UPDATE accounts
SET balance = balance + 100
WHERE account_id = 101;

TRUNCATE TABLE staging_data;

ROLLBACK;
~~~

The final ROLLBACK cannot undo the UPDATE that was implicitly committed before TRUNCATE ran. TRUNCATE itself also cannot be rolled back like a regular DELETE.

### 15.1 Separate Schema Deployment From Business Transactions

Do not place CREATE/ALTER/TRUNCATE between steps of a money transfer, order placement, or payment transaction. Structure scripts into:

1. Schema/migration deployment step with its own DDL boundary.
2. Data loading/transformation step.
3. Business confirmation step via DML transactions.

If DDL operations are required in a deployment pipeline, clearly understand the commit boundaries and prepare a separate recovery plan.

## 16. Autonomous Transactions and Side Effects Outside the Parent Transaction

PL/SQL supports autonomous transactions via `PRAGMA AUTONOMOUS_TRANSACTION`. This is an independent transaction separate from the calling transaction. It can COMMIT or ROLLBACK independently; committed results are not rolled back when the parent transaction rolls back.

Illustrative example:

~~~sql
CREATE OR REPLACE PROCEDURE write_independent_log (
    p_message IN VARCHAR2
) AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO independent_audit(message, created_at)
    VALUES (p_message, SYSTIMESTAMP);

    COMMIT;
END;
/
~~~

If a parent transaction calls this procedure and then ROLLBACKs, the audit row COMMITted by the autonomous transaction still persists. This may be the goal when recording errors that must survive independently, yet it can also break data atomicity if misused.

### 16.1 Do Not Use Autonomous Transactions for Data That Must Commit Together

If a trigger writes a ledger row via an autonomous transaction while the account UPDATE belongs to the parent transaction, the following can happen:

- The ledger row commits.
- The parent transaction fails and rolls back the balance.
- The log still exists as if the business event occurred.

Therefore, audit/ledger entries that must remain consistent with business data should generally stay in the same transaction. Only use autonomous transactions when the independence requirement is clearly established.

### 16.2 Sequences Do Not Roll Back

Values fetched from an Oracle sequence via `NEXTVAL` are not returned when a transaction rolls back. Example:

~~~sql
INSERT INTO orders(order_id, customer_id)
VALUES (order_seq.NEXTVAL, 100);

ROLLBACK;
~~~

The inserted row is rolled back, yet the allocated sequence number remains consumed. Subsequent NEXTVAL calls may produce gaps. Sequences are designed to issue unique numbers safely across multiple sessions, not to act as gapless sequential counters.

Do not use missing sequence numbers to conclude that rows were committed or that a transaction lost data.

### 16.3 Side Effects Outside the Database

Sending emails, calling HTTP APIs, writing files, or sending messages to external systems do not automatically roll back with an Oracle transaction. If an application:

1. Updates an order.
2. Sends a confirmation email.
3. Rolls back the transaction because a later step failed.

the sent email may still exist even though the order was not committed. Reliable integration design is required, such as a transactional outbox: write the event to an outbox table in the same business transaction, and after COMMIT another process dispatches the message and updates its status.

## 17. Distributed Transactions

When a transaction updates multiple databases participating in a distributed transaction, Oracle can use two-phase commit (2PC) to coordinate participants:

1. **Prepare:** participants prepare and confirm they can commit.
2. **Commit:** the coordinator instructs participants to commit after all have prepared successfully.

The goal is preserving atomicity across participating databases. During network or coordinator failures, a distributed transaction can enter an in-doubt state requiring recovery/DBA intervention.

2PC does not make arbitrary external side effects transactional. An email server or REST API does not automatically enlist in an Oracle transaction simply by being called from an application.

## 18. Atomicity, Isolation, and Read Consistency

Do not use the word "atomicity" to explain every concurrency behavior.

Oracle provides read consistency so SELECT statements see a consistent data version via MVCC. At the default READ COMMITTED level, each read statement has a consistent snapshot as of the time the statement starts. Isolation/locking governs how concurrent transactions interact.

For example:

- Statement-level atomicity ensures a failed UPDATE does not leave half of its rows updated.
- Transaction-level atomicity ensures debit and credit commit together or roll back together if grouped in one transaction.
- Isolation and locking help handle two sessions transferring money or editing the same row concurrently.

All three concerns must be designed together, yet none replaces the others.

## 19. Verifying with Two Sessions

You can observe transaction atomicity using two separate SQL sessions.

### 19.1 Session A: Modify Without Committing

~~~sql
UPDATE lab_accounts
SET balance = balance - 100
WHERE account_id = 101;

-- Not committed yet.
~~~

### 19.2 Session B: Read Data

~~~sql
SELECT account_id, balance
FROM lab_accounts
WHERE account_id = 101;
~~~

Under READ COMMITTED, Session B does not see Session A's uncommitted change; it reads the committed version matching the SELECT's snapshot.

### 19.3 Session A Ends the Transaction

Try:

~~~sql
COMMIT;
~~~

Re-run the SELECT in Session B. After commit, the new SELECT can see the new balance. If COMMIT is replaced with ROLLBACK, the value reverts to the pre-transaction state.

This experiment tests visibility and transaction boundaries; it is not a performance benchmark or comprehensive proof of every isolation level.

## 20. Verifying Statement Atomicity with a Constraint Violation

Run in a test schema:

~~~sql
CREATE TABLE lab_atomicity_test (
    id NUMBER PRIMARY KEY,
    value_num NUMBER,
    CONSTRAINT ck_lab_atomicity_value CHECK (value_num <= 100)
);

INSERT INTO lab_atomicity_test VALUES (1, 10);
INSERT INTO lab_atomicity_test VALUES (2, 20);
COMMIT;
~~~

Run a statement where one row violates the constraint:

~~~sql
UPDATE lab_atomicity_test
SET value_num = CASE
    WHEN id = 1 THEN 50
    WHEN id = 2 THEN 150
END;
~~~

Because row `id = 2` violates CHECK, the UPDATE fails and the changes of that UPDATE statement are undone. Verify:

~~~sql
SELECT id, value_num
FROM lab_atomicity_test
ORDER BY id;
~~~

Both rows remain 10 and 20. Next, run one valid UPDATE followed by another failing UPDATE; after the failure, the earlier valid statement stays pending until the whole transaction is COMMITted or ROLLBACKed.

## 21. Decision Matrix: Where to Roll Back?

| Scenario | Typically Appropriate Handling |
|---|---|
| A DML statement violates a constraint with no partial-error mechanism | Let the statement fail; Oracle rolls back that statement's changes |
| A DML statement fails and earlier business steps must be cancelled | ROLLBACK the entire transaction or to a business savepoint |
| An optional step fails, work before savepoint remains valid | ROLLBACK TO SAVEPOINT and continue per business rules |
| Batch load wanting to keep valid rows and isolate failing rows | DML error logging or appropriate bulk error handling |
| Deferred constraint checked only at COMMIT | Check commit errors and handle the incomplete transaction |
| DDL runs between DML statements | Separate boundaries; account for implicit commit |
| Error log needed even after business rollback | Consider a deliberate autonomous transaction |
| External API/email called before transaction rollback | Use outbox/compensation; never assume side effects auto-roll back |
| Multiple DML statements via JDBC | Disable autocommit, commit/roll back at the business boundary |

## 22. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| An UPDATE fails but prior statements remain | Confusing statement rollback with transaction rollback | Call ROLLBACK or ROLLBACK TO SAVEPOINT per business logic |
| Transfer debits source without crediting destination | Each DML runs/commits separately or exception fails to roll back transaction | Group debit, credit, and log into one transaction |
| JDBC rollback fails to revert changes | Autocommit committed earlier statement | Call `setAutoCommit(false)` before DML |
| ROLLBACK does not undo UPDATE before DDL | DDL triggered an implicit commit | Separate DDL from business transactions |
| Procedure fails yet pre-error changes remain pending | Exceptions do not auto-roll back the entire transaction | Manage savepoints/rollbacks explicitly |
| Helper procedure commits too early | COMMIT inside procedure ends the whole session transaction | Let the caller manage the transaction or define a clear contract |
| Sequence numbers jump | NEXTVAL does not roll back | Accept gaps; never use sequences for contiguous numbering |
| Audit remains despite business rollback | Trigger/procedure uses an autonomous transaction | Only use autonomous transactions deliberately for independent logs |
| Email sent though order rolled back | External side effects do not join database transactions | Use transactional outbox or compensating mechanisms |
| Batch saves only part of the data | Deliberate use of LOG ERRORS/SAVE EXCEPTIONS or mid-flight commit | Read error logs and decide commit policy |
| COMMIT raises error from deferred constraint | Constraint is validated at commit time | Fix data or roll back; inspect DEFERRABLE settings |
| No rows updated yet app assumes success | SQL does not treat rowcount 0 as an error | Check `SQL%ROWCOUNT` or `executeUpdate()` |

## 23. Self-Check Exercises

### Exercise 1 — Statement-Level Atomicity

Create a table with a CHECK constraint and run a multi-row UPDATE where one row violates it. Check whether the other rows in the same UPDATE keep their changes. Explain the role of the implicit statement savepoint.

### Exercise 2 — Transaction-Level Atomicity

Run two successful UPDATEs in the same session, then ROLLBACK. Confirm both uncommitted changes are undone.

### Exercise 3 — A Failing Statement After a Successful Statement

Run a valid UPDATE, followed by an INSERT with a duplicate primary key. Inspect the data before calling COMMIT/ROLLBACK. Why does the first UPDATE remain pending?

### Exercise 4 — SAVEPOINT

Run UPDATE A, create a SAVEPOINT, run UPDATE B, then ROLLBACK TO SAVEPOINT. Confirm A remains pending and B is undone. Afterward, call a full ROLLBACK.

### Exercise 5 — Money Transfer

Write a PL/SQL block consisting of a debit, a credit, and a log insert. Check `SQL%ROWCOUNT` after each DML. If the destination account does not exist, roll back to the savepoint and raise an error.

### Exercise 6 — JDBC Autocommit

Write two JDBC versions: one with autocommit true and one with `setAutoCommit(false)`. Intentionally make the second statement fail and compare the state of the first statement.

### Exercise 7 — DDL Implicit Commit

Run an uncommitted DML statement, then execute `CREATE TABLE` in a test schema. Call ROLLBACK and observe why the DML before DDL was not undone.

### Exercise 8 — Error Logging

Create an error table via `DBMS_ERRLOG`, load a dataset containing both valid rows and constraint-violating rows using `LOG ERRORS`. Compare destination row counts and error row counts. Try ROLLBACK to see how both groups behave.

### Exercise 9 — Autonomous Transaction

Invoke a procedure with `PRAGMA AUTONOMOUS_TRANSACTION` to write an audit record, then roll back the parent transaction. Observe the audit record. Explain why this technique must not be used for a ledger that must stay synchronized with the business operation.

### Exercise 10 — Distinguishing ACID

Using the money transfer example, describe which parts belong to atomicity, isolation, consistency, and durability. Name a race condition that atomicity alone does not solve.

## 24. Checklist for Designing Transaction Boundaries

Before implementing a multi-step business workflow, determine:

- Which DML statements must succeed together?
- Which statements can fail and what scope must that failure undo?
- Is there an appropriate point to place a SAVEPOINT?
- Who owns the transaction: procedure, service layer, or caller?
- Is JDBC autocommit currently enabled?
- Does any DDL accidentally commit the transaction?
- Do triggers contain autonomous transactions or external side effects?
- Are sequence gaps acceptable?
- Are there deferred constraints validated only at COMMIT?
- Does batch processing intentionally use DML error logging or SAVE EXCEPTIONS?
- Does every DML check updated row counts when business rules require exactly one row?
- Is there retry or duplicate-transaction handling if the client disconnects after the server commits?

## 25. Key Takeaways

| Concept | Practical Rule |
|---|---|
| Statement atomicity | If one DML statement fails, Oracle rolls back that DML statement's changes |
| Transaction atomicity | COMMIT or ROLLBACK applies to the entire current transaction |
| Implicit statement savepoint | Oracle's internal mechanism used to roll back a failed DML statement |
| COMMIT | Confirms pending changes and ends the transaction |
| ROLLBACK | Discards all uncommitted changes in the transaction |
| SAVEPOINT | Marks a partial rollback position |
| ROLLBACK TO | Discards changes after the savepoint; transaction stays open |
| PL/SQL exception | Does not automatically replace business rollback policy |
| JDBC autocommit | Enabling autocommit can turn every DML statement into its own transaction |
| DDL | Has implicit commit; do not place arbitrarily inside a DML transaction |
| LOG ERRORS | Deliberate mechanism allowing row errors to be handled while keeping valid rows |
| SAVE EXCEPTIONS | Collects errors in bulk DML; application decides transaction outcome |
| Autonomous transaction | Commits independently; not rolled back with the parent transaction |
| Sequence | NEXTVAL is not returned upon rollback |
| External side effect | Email/API/file does not auto-roll back with an Oracle transaction |

Statement-level atomicity protects a single DML statement from leaving partial changes behind when that statement itself fails. Transaction-level atomicity protects an entire business unit of work spanning multiple statements. When designing systems, group mandatory steps into the same transaction, use savepoints for branches requiring partial rollback, and let the right application layer own the COMMIT decision. At the same time, verify autocommit, DDL, autonomous transactions, and external side effects because they can introduce boundaries SQL authors did not anticipate.
