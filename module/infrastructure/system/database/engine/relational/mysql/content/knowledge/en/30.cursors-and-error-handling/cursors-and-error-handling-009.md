# Per-Statement Error Handling vs. Full-Business-Operation Rollback

When an SQL statement fails in MySQL, there are two rollback scopes to distinguish:

- **Statement rollback**: InnoDB rolls back only the changes made by the failing statement itself. Earlier successful statements in the same transaction remain uncommitted and active.
- **Transaction rollback**: MySQL/InnoDB rolls back all transactional changes since the start of the transaction, or since a SAVEPOINT if using `ROLLBACK TO SAVEPOINT`.

These two scopes determine how stored procedures, handlers, and batch data workflows are written. A `CONTINUE` handler may skip a per-statement error and continue processing; an `EXIT` handler may stop a block. However, a handler does not itself decide whether a transaction commits or rolls back. To undo an entire business operation, the code must establish clear transaction boundaries and execute ROLLBACK in the right place.

This lesson falls under the `DATABASE_MYSQL` scope: designing error handling in stored programs, distinguishing per-statement errors from full-transaction failures, using `DECLARE HANDLER`, `RESIGNAL`, `GET DIAGNOSTICS`, and `SAVEPOINT`, while keeping multi-table operations consistent.

## 1. Two Levels of Atomicity

Atomicity can be viewed at two scopes.

### 1.1. Atomicity of a Single Statement

For InnoDB tables, a single DML statement is an atomic execution unit. If a statement fails due to a constraint violation or SQL error, InnoDB typically rolls back the changes produced by that statement alone.

Example:

~~~sql
CREATE TABLE account_statement_demo (
    account_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO account_statement_demo (account_id, balance)
VALUES (1, 1000.00), (2, 500.00);
~~~

Start a transaction and run two statements:

~~~sql
START TRANSACTION;

UPDATE account_statement_demo
SET balance = balance - 100
WHERE account_id = 1;

-- Since account_id=2 already exists, this INSERT fails.
INSERT INTO account_statement_demo (account_id, balance)
VALUES (2, 999.00);
~~~

The INSERT statement fails with a duplicate primary key error. With InnoDB, the changes of the failed INSERT are rolled back. The preceding UPDATE remains inside the active transaction and is not rolled back merely because the INSERT failed.

You can inspect this in the same session:

~~~sql
SELECT *
FROM account_statement_demo
ORDER BY account_id;

SELECT @@session.in_transaction;
~~~

If you subsequently call COMMIT, the first UPDATE is still committed. Only if you call ROLLBACK is the first UPDATE undone.

### 1.2. Atomicity of the Entire Transaction

A transaction groups multiple statements into a single business unit:

~~~sql
START TRANSACTION;

UPDATE account_statement_demo
SET balance = balance - 100
WHERE account_id = 1;

UPDATE account_statement_demo
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

If the second step fails and the application decides the entire business operation cannot complete, it must ROLLBACK the transaction:

~~~sql
ROLLBACK;
~~~

With InnoDB, ROLLBACK undoes all uncommitted transactional changes across the entire transaction. This is the scope typically required for money transfers, order placement, inventory deduction with ledger recording, or updating multiple business-related tables.

### 1.3. Quick Comparison

| Scope | What Is Rolled Back? | Is the Transaction Still Active? |
|---|---|---|
| Statement rollback | Changes of the failing statement | Usually yes, if the error did not cause InnoDB to roll back the whole transaction |
| ROLLBACK TO SAVEPOINT | Changes after the savepoint inside the transaction | Yes |
| ROLLBACK | All uncommitted transactional changes in the transaction | No; transaction ends |
| Deadlock victim rollback | Entire transaction chosen as victim by InnoDB | No; must retry the transaction if appropriate |

Never assume "an SQL error occurred" always means the entire transaction was rolled back. The error type and InnoDB configuration determine the rollback scope.

## 2. How Autocommit Affects the Observed Scope

### 2.1. autocommit = 1

By default, MySQL enables autocommit. A standalone successful statement normally commits on completion:

~~~sql
UPDATE account_statement_demo
SET balance = balance + 10
WHERE account_id = 1;
~~~

If the statement fails, it does not commit its changes. Because there are no preceding statements inside a standalone transaction, there are usually no earlier business changes left uncommitted.

### 2.2. Explicit Transactions

Even when autocommit is enabled, multiple statements can be grouped:

~~~sql
START TRANSACTION;

UPDATE account_statement_demo
SET balance = balance - 10
WHERE account_id = 1;

UPDATE account_statement_demo
SET balance = balance + 10
WHERE account_id = 2;

COMMIT;
~~~

If the second statement errors, the transaction can still remain open after a standard statement rollback. The caller must decide whether to continue, fix the error, use a savepoint, or ROLLBACK the entire transaction.

### 2.3. autocommit = 0

When autocommit is disabled, subsequent transactional statements belong to a transaction until COMMIT or ROLLBACK:

~~~sql
SET autocommit = 0;

UPDATE account_statement_demo
SET balance = balance + 10
WHERE account_id = 1;

COMMIT;
~~~

Disabling autocommit does not automatically establish a full-business rollback policy. The application must still handle errors and close transactions promptly. Forgotten open transactions hold locks and read views for too long.

## 3. Condition Groups in MySQL

Stored programs can handle conditions using handlers. MySQL supports common condition classes:

| Condition | Meaning |
|---|---|
| `SQLWARNING` | SQLSTATE class 01: warnings |
| `NOT FOUND` | SQLSTATE class 02: row not found or cursor data exhausted |
| `SQLEXCEPTION` | SQLSTATE classes other than 00, 01, and 02 |
| Specific SQLSTATE | E.g., `'45000'` for application-raised errors |
| MySQL error code | E.g., specific numeric code such as duplicate key |

A handler can catch a specific condition or an entire class of conditions.

### 3.1. Duplicate Key

For example, a duplicate primary key error typically has MySQL error 1062 and SQLSTATE `23000`. Without a matching handler, the error is returned to the caller.

Handlers can be declared by error code or SQLSTATE:

~~~sql
DECLARE CONTINUE HANDLER FOR 1062
    SET v_duplicate_found = TRUE;
~~~

Or:

~~~sql
DECLARE CONTINUE HANDLER FOR SQLSTATE '23000'
    SET v_constraint_error = TRUE;
~~~

SQLSTATE class 23 encompasses many integrity constraint errors, not solely duplicate keys. If you only want to handle duplicates, catching error code 1062 specifically is clearer.

### 3.2. NOT FOUND

`NOT FOUND` typically occurs when:
- Cursor `FETCH` moves past the last row.
- `SELECT ... INTO` finds no rows.

Example:

~~~sql
DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_done = TRUE;
~~~

Inside a cursor loop, this handler usually sets a flag so the loop terminates. Watch block scope carefully, because the same handler can also catch a `SELECT ... INTO` returning no rows if it executes in the same scope.

### 3.3. SQLEXCEPTION

`SQLEXCEPTION` catches SQL errors outside the SQLWARNING and NOT FOUND classes. This is the condition commonly used for full-transaction rollback handlers:

~~~sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    ROLLBACK;
    RESIGNAL;
END;
~~~

The handler above rolls back the current transaction and then re-raises the error to the caller. Use this pattern only when the procedure genuinely owns the transaction; if the transaction belongs to the caller, ROLLBACK can wipe out the caller's earlier work.

### 3.4. SIGNAL Creating a Business Error

You can actively raise a condition:

~~~sql
SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'Insufficient balance';
~~~

SQLSTATE class 45 represents application-defined exceptions. It allows reporting business errors such as invalid quantities, nonexistent accounts, or disallowed order state transitions.

If the error is raised inside a statement within an InnoDB transaction, that statement fails; broader rollback scope depends on handlers and the transaction contract.

## 4. DECLARE HANDLER: CONTINUE and EXIT

Syntax:

~~~sql
DECLARE { CONTINUE | EXIT } HANDLER
FOR condition_value
statement;
~~~

MySQL provides two practical handler types:

- `CONTINUE`: handles the condition and then resumes execution at the statement immediately following the one that raised the condition.
- `EXIT`: handles the condition and then exits the compound block (`BEGIN ... END`) where the handler is declared.

MySQL does not support `UNDO` handlers.

### 4.1. CONTINUE

Example marking a duplicate and continuing:

~~~sql
DELIMITER //

CREATE PROCEDURE insert_customer_if_new(
    IN p_customer_id BIGINT UNSIGNED,
    IN p_email VARCHAR(254),
    OUT p_inserted BOOLEAN
)
BEGIN
    DECLARE v_duplicate BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR 1062
        SET v_duplicate = TRUE;

    SET p_inserted = FALSE;

    INSERT INTO customer (customer_id, email)
    VALUES (p_customer_id, p_email);

    IF v_duplicate = FALSE THEN
        SET p_inserted = TRUE;
    END IF;
END//

DELIMITER ;
~~~

When INSERT encounters a duplicate key:
1. InnoDB rolls back the failed INSERT statement.
2. The CONTINUE handler sets the flag.
3. Execution continues after INSERT.
4. The procedure returns `p_inserted = FALSE`.

The handler does not roll back the current transaction. If earlier successful statements ran in the transaction, those changes remain.

This example illustrates control flow only. If the table has multiple unique keys, you must distinguish which duplicate occurred and may need more specific error handling or an intentional upsert.

### 4.2. EXIT

Example:

~~~sql
DELIMITER //

CREATE PROCEDURE validate_order(
    IN p_quantity INT
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        SET @routine_failed = TRUE;
        RESIGNAL;
    END;

    IF p_quantity <= 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Quantity must be positive';
    END IF;

    INSERT INTO order_validation_log(quantity)
    VALUES (p_quantity);
END//

DELIMITER ;
~~~

When SIGNAL raises an error:
- The EXIT handler is invoked.
- The handler executes RESIGNAL.
- The block containing the handler ends due to the re-raised condition.
- The caller receives the error.

An EXIT handler does not automatically roll back the transaction. If the routine executed transactional statements before the error, the caller must still decide whether the transaction will commit or roll back, unless the handler explicitly does so.

### 4.3. Block Scope Determines Where EXIT Stops

A handler declared inside a nested block only EXITs that block:

~~~sql
BEGIN
    -- outer block
    BEGIN
        DECLARE EXIT HANDLER FOR SQLEXCEPTION
            SET v_failed = TRUE;

        INSERT INTO target_table(id) VALUES (1);
    END;

    -- If the handler handled the error internally, the outer block can continue.
    SET v_after_inner_block = TRUE;
END;
~~~

Use nested blocks to isolate errors per row or per step. Never assume EXIT always exits the entire procedure; it exits the block containing the handler.

## 5. Handlers Do Not Decide Rollback Automatically

This is the most important principle of this lesson.

~~~sql
DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
    SET v_error_seen = TRUE;
~~~

The handler above only modifies a variable. It does not call ROLLBACK.

Similarly:

~~~sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    SET v_error_seen = TRUE;
END;
~~~

The EXIT handler stops the block, yet the transaction may still remain active. If the procedure finishes without COMMIT or ROLLBACK, the connection can hold the transaction open.

A handler only controls execution flow and executes the statements written inside its body. To roll back, you must explicitly write `ROLLBACK` or `ROLLBACK TO SAVEPOINT`.

### 5.1. Three Different Error Policies

| Policy | Handler/Transaction | Outcome |
|---|---|---|
| Record per-statement error and continue | CONTINUE; no full transaction rollback | Failing statement is rolled back; other steps continue |
| Stop routine and let caller decide | EXIT or RESIGNAL; no automatic rollback | Routine stops; caller-owned transaction remains managed by caller |
| Roll back entire business operation | EXIT handler calls ROLLBACK then RESIGNAL | All uncommitted InnoDB changes in the transaction are undone |

Choose a policy based on business requirements. For instance, row-by-row data import may accept skipping a bad row; a funds transfer must usually roll back completely if any step fails.

## 6. Statement Rollback During Row-by-Row Processing

Suppose we have a staging table and target tables:

~~~sql
CREATE TABLE import_stage (
    source_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    email VARCHAR(254) NOT NULL,
    display_name VARCHAR(150) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE imported_customer (
    source_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    email VARCHAR(254) NOT NULL UNIQUE,
    display_name VARCHAR(150) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE import_error_log (
    source_id BIGINT UNSIGNED NOT NULL,
    mysql_errno INT NOT NULL,
    returned_sqlstate CHAR(5) NOT NULL,
    message_text VARCHAR(1024) NOT NULL,
    logged_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE = InnoDB;
~~~

If a row has an email that already exists, that row's INSERT fails due to the unique key. In a row-by-row workflow:
- Valid rows are written to `imported_customer`.
- Failing rows have their details written to `import_error_log`.
- Subsequent rows continue to be processed.
- At the end of the batch, successful rows can be COMMITted together.

This is a "skip errors at the row/statement level" policy rather than a full-batch rollback.

### 6.1. Cursor with Local Handler for Each INSERT

~~~sql
DELIMITER //

CREATE PROCEDURE import_customers_continue_on_row_error()
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_source_id BIGINT UNSIGNED;
    DECLARE v_email VARCHAR(254);
    DECLARE v_display_name VARCHAR(150);
    DECLARE v_sqlstate CHAR(5);
    DECLARE v_errno INT;
    DECLARE v_message VARCHAR(1024);

    DECLARE cur_import CURSOR FOR
        SELECT source_id, email, display_name
        FROM import_stage
        ORDER BY source_id;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    OPEN cur_import;

    read_loop: LOOP
        FETCH cur_import
        INTO v_source_id, v_email, v_display_name;

        IF v_done THEN
            LEAVE read_loop;
        END IF;

        BEGIN
            DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
            BEGIN
                GET DIAGNOSTICS CONDITION 1
                    v_sqlstate = RETURNED_SQLSTATE,
                    v_errno = MYSQL_ERRNO,
                    v_message = MESSAGE_TEXT;

                INSERT INTO import_error_log (
                    source_id,
                    mysql_errno,
                    returned_sqlstate,
                    message_text
                )
                VALUES (
                    v_source_id,
                    v_errno,
                    v_sqlstate,
                    v_message
                );
            END;

            INSERT INTO imported_customer (
                source_id,
                email,
                display_name
            )
            VALUES (
                v_source_id,
                v_email,
                v_display_name
            );
        END;
    END LOOP;

    CLOSE cur_import;
    COMMIT;
END//

DELIMITER ;
~~~

How it works:

1. The procedure opens a transaction so the batch has a single final commit point.
2. The cursor reads each staging row.
3. Each INSERT is placed inside a child block with its own CONTINUE handler.
4. If the INSERT succeeds, the loop moves to the next row.
5. If the INSERT fails, InnoDB rolls back that INSERT statement.
6. The handler reads diagnostics and writes the error to `import_error_log`.
7. The CONTINUE handler finishes, and the loop continues with the next row.
8. If an error occurs that is not handled by the local handler, the outer EXIT handler rolls back the entire transaction and calls RESIGNAL.
9. If everything aside from per-row errors completes, the procedure COMMITs the successful rows and error logs.

**Preconditions for this example:** all three tables must use InnoDB; the procedure owns the transaction and must only be called when the caller has no open transaction. `START TRANSACTION` in MySQL commits any previously active transaction, so if the caller has uncommitted work, this procedure could inadvertently commit it. In real applications, clearly choose the transaction contract as shown in Section 10.

If the INSERT into `import_error_log` also fails, the error raised inside the local handler is not caught by that same handler. It propagates to the outer EXIT handler, causing the whole batch to roll back. This is safer than silently losing both data and error traces.

### 6.2. Why Use a Nested Block?

A handler declared inside a child block applies only to statements in that block. Consequently:
- A single row's INSERT error can be handled locally.
- Cursor FETCH end-of-data is still handled by the outer NOT FOUND handler.
- Errors outside the per-row scope trigger the batch-level EXIT handler.

Placing a procedure-wide CONTINUE handler for SQLEXCEPTION could accidentally swallow severe errors such as cursor open failures, logging failures, or batch status update failures. Narrow scope keeps the policy clear.

## 7. Rolling Back the Entire Business Operation with an EXIT Handler

For a funds transfer, you cannot ignore a failed step and commit an earlier step. If debiting the source succeeds yet crediting the destination fails, the entire transaction must roll back.

Example procedure owning the transaction:

~~~sql
DELIMITER //

CREATE PROCEDURE transfer_funds(
    IN p_from_account BIGINT UNSIGNED,
    IN p_to_account BIGINT UNSIGNED,
    IN p_amount DECIMAL(12, 2)
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    IF p_from_account = p_to_account THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Source and destination must differ';
    END IF;

    IF p_amount <= 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Transfer amount must be positive';
    END IF;

    START TRANSACTION;

    UPDATE account
    SET balance = balance - p_amount
    WHERE account_id = p_from_account
      AND balance >= p_amount;

    IF ROW_COUNT() <> 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Source account missing or insufficient balance';
    END IF;

    UPDATE account
    SET balance = balance + p_amount
    WHERE account_id = p_to_account;

    IF ROW_COUNT() <> 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Destination account not found';
    END IF;

    INSERT INTO transfer_audit (
        from_account,
        to_account,
        amount,
        created_at
    )
    VALUES (
        p_from_account,
        p_to_account,
        p_amount,
        NOW(6)
    );

    COMMIT;
END//

DELIMITER ;
~~~

Explanation:
- The procedure starts a transaction before write operations.
- The source UPDATE deducts funds guarded by sufficient balance.
- If not exactly one row was updated, SIGNAL raises a business error.
- The destination UPDATE adds funds.
- If the destination account does not exist, SIGNAL fires.
- If the audit INSERT fails, the error also enters the EXIT handler.
- The EXIT handler ROLLBACKs the entire transaction and then RESIGNALs so the caller knows the operation failed.

Assuming all tables are InnoDB and there are no external non-transactional side effects, all changes succeed or roll back together: source balance, destination balance, and audit record remain consistent.

### 7.1. Procedure-Owned Transaction Contract

The example above uses `START TRANSACTION`, `COMMIT`, and `ROLLBACK`. It assumes the procedure owns the transaction. Do not call this procedure while the caller has an open uncommitted transaction that must be preserved, because starting a new transaction can implicitly commit the active one.

Application documentation should clearly state:
- The caller must invoke on a connection with no open transaction.
- The procedure opens and closes the transaction itself.
- Errors are RESIGNALed so the caller detects failure.
- The caller does not issue COMMIT/ROLLBACK to alter results already committed by the procedure.

## 8. Caller-Owned Transactions: Procedure Reports Errors Only

Another design leaves transaction ownership with the application. The procedure only executes statements and raises errors; it does not call START TRANSACTION, COMMIT, or ROLLBACK itself.

Example:

~~~sql
DELIMITER //

CREATE PROCEDURE apply_order_changes(
    IN p_order_id BIGINT UNSIGNED
)
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM orders
        WHERE order_id = p_order_id
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Order does not exist';
    END IF;

    UPDATE orders
    SET status = 'PROCESSING'
    WHERE order_id = p_order_id;

    INSERT INTO order_audit(order_id, event_name, created_at)
    VALUES (p_order_id, 'PROCESSING', NOW(6));
END//

DELIMITER ;
~~~

Application:

~~~sql
START TRANSACTION;

CALL apply_order_changes(1001);

-- COMMIT only after all caller-side business steps succeed.
COMMIT;
~~~

If CALL reports an error, the caller catches the exception and decides to ROLLBACK:

~~~sql
ROLLBACK;
~~~

If the procedure has a CONTINUE handler that swallows errors, the caller may not realize the operation failed. Therefore, with caller-owned transactions, the procedure should let errors propagate or use an EXIT handler with RESIGNAL without rolling back the caller's transaction itself.

### 8.1. EXIT Handler and RESIGNAL Do Not Require Rollback

You can record or enrich information and then re-raise the error:

~~~sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    SET v_failed = TRUE;
    RESIGNAL;
END;
~~~

There is no ROLLBACK inside the handler. The caller receives the error and owns the transaction decision.

This is the appropriate pattern when a service layer coordinates multiple procedures inside a single transaction.

## 9. SAVEPOINT: Partial Rollback While Keeping the Transaction

SAVEPOINT creates a marker within a transaction:

~~~sql
START TRANSACTION;

UPDATE account
SET balance = balance - 20
WHERE account_id = 1;

SAVEPOINT after_debit;

UPDATE account
SET balance = balance + 20
WHERE account_id = 2;

ROLLBACK TO SAVEPOINT after_debit;

-- The transaction remains active.
COMMIT;
~~~

After `ROLLBACK TO SAVEPOINT after_debit`:
- Changes made after the savepoint are undone.
- Changes made before the savepoint remain in the transaction.
- The transaction does not end.
- Subsequent statements and COMMIT/ROLLBACK can proceed.

### 9.1. Using Savepoints for Individual Units of Work

Savepoints can be used in batches when you want to roll back one group of work while keeping earlier groups:

~~~sql
START TRANSACTION;

SAVEPOINT batch_item_1;
-- Process item 1.

SAVEPOINT batch_item_2;
-- Process item 2.

-- If item 2 fails:
ROLLBACK TO SAVEPOINT batch_item_2;

-- Continue with item 3.
COMMIT;
~~~

Inside stored programs, you can set a SAVEPOINT before a processing block and use a handler to roll back to that savepoint. However, you must manage savepoint names, scope, and errors during savepoint creation/rollback. Savepoints are meaningful only while a transaction is active.

### 9.2. SAVEPOINT Is Not a Child Transaction

MySQL does not support nested transactions where a child transaction can COMMIT independently. A savepoint merely marks a position inside the current transaction.

- COMMIT ends the entire transaction and removes savepoints.
- Full-transaction ROLLBACK erases all changes and savepoints.
- ROLLBACK TO SAVEPOINT does not end the transaction.
- RELEASE SAVEPOINT removes the marker without rolling back data.

Do not use SAVEPOINT expecting a piece of work to commit independently from its parent transaction.

### 9.3. DDL and Implicit Commits

Many DDL statements such as ALTER TABLE, CREATE TABLE, DROP TABLE, and TRUNCATE TABLE cause an implicit commit. DDL can invalidate active transactions and prior savepoints. Do not use SAVEPOINT expecting to roll back DDL.

## 10. Errors in Procedures: Who Owns the Transaction?

A stored procedure can be designed under two contracts.

| Contract | Procedure | Caller |
|---|---|---|
| Procedure-owned | START TRANSACTION, COMMIT, and ROLLBACK | Calls on a connection with no open transaction to preserve; receives error on failure |
| Caller-owned | Never calls START/COMMIT/ROLLBACK | Opens transaction, calls one or more procedures, decides COMMIT/ROLLBACK |

### 10.1. Do Not Mix the Two Contracts

A common bug occurs when a procedure executes START TRANSACTION and COMMIT while the application thinks it controls a broader transaction.

Example:
1. Application runs START TRANSACTION.
2. Updates table A.
3. Calls procedure.
4. Procedure executes START TRANSACTION and COMMIT.
5. The application's prior transaction may have already been implicitly committed.

When the procedure commits, the application can no longer roll back changes made before the procedure call as intended.

### 10.2. Functions and Triggers Do Not Manage Transactions

Stored functions and triggers have stricter limits than procedures:
- Cannot execute START TRANSACTION, COMMIT, or ROLLBACK.
- Execute within the caller's statement/transaction context.
- Errors in functions/triggers can cause the invoking statement to fail.
- Transactional changes made by a function/trigger (when permitted) participate in the caller's transaction.

Therefore, never place transaction ownership in functions or triggers. Use procedures or the application layer to coordinate multi-step transactions.

## 11. Deadlock vs. Lock Wait Timeout: Two Different Rollback Scopes

Not all concurrency errors have the same rollback scope.

### 11.1. Deadlock

When InnoDB detects a deadlock, it selects one transaction as the victim and rolls back that entire transaction to break the wait cycle.

The application typically receives a deadlock error (MySQL error 1213, SQLSTATE 40001). How to handle:
1. Catch the error.
2. Treat the transaction as completely rolled back.
3. Retry the entire transaction from the beginning if the operation is safe to retry.
4. Use backoff and cap the retry count.
5. Access rows in a consistent order to reduce deadlocks.

Never re-run only the final statement of a transaction that was rolled back due to deadlock.

### 11.2. Lock Wait Timeout

When a statement waits too long for a lock, InnoDB by default rolls back only the waiting statement, not the entire transaction.

The `innodb_rollback_on_timeout` variable can change this behavior. Check:

~~~sql
SELECT
    @@GLOBAL.innodb_lock_wait_timeout,
    @@GLOBAL.innodb_rollback_on_timeout;
~~~

If `innodb_rollback_on_timeout = 0`, the timed-out statement is usually rolled back while the transaction remains active. If enabled, a timeout can roll back the entire transaction.

After a lock wait timeout, the application must know the actual server setting and decide:
- Retry the statement inside the still-valid transaction.
- ROLLBACK the entire transaction and retry.
- Return an error to the caller.

For multi-step business operations, rolling back the whole transaction and retrying from the beginning usually guarantees consistency more easily, though idempotency and side effects must be considered.

### 11.3. Error Comparison Table

| Situation | Typical InnoDB Behavior | Application Action |
|---|---|---|
| Duplicate key on INSERT | Rolls back failing statement | Fix data, handle duplicate, or roll back transaction per business rules |
| CHECK/FOREIGN KEY violation | Rolls back failing statement | Handle error; transaction usually remains open |
| SIGNAL in stored program | Statement containing error fails | Handler/caller decides transaction scope |
| Lock wait timeout, default | Rolls back waiting statement | Decide whether to continue or roll back transaction |
| Deadlock victim | Rolls back entire transaction | Retry whole transaction if safe |
| Connection error before knowing if COMMIT finished | Outcome may be unknown to client | Check state/idempotency before retrying |

Behavior can depend on storage engine, statement type, and server configuration. Do not apply InnoDB rollback rules to every engine.

## 12. Non-Transactional Tables and External Side Effects

Statement rollback and transaction rollback protect only transactional storage engine changes.

### 12.1. MyISAM Does Not Roll Back Like InnoDB

Example table:

~~~sql
CREATE TABLE legacy_counter (
    counter_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    value_count BIGINT NOT NULL
) ENGINE = MyISAM;
~~~

Changes on MyISAM are not undone by ROLLBACK like InnoDB. If a transaction updates both InnoDB and MyISAM tables, ROLLBACK can undo only the InnoDB transactional portion; MyISAM changes may persist.

For business operations requiring atomicity, all participating tables should use InnoDB.

### 12.2. Side Effects Outside the Database

An SQL transaction cannot automatically undo:
- Emails already sent.
- HTTP requests already invoked.
- Files already written.
- Messages published to external systems.
- Actions on services not participating in the same transaction.

If the application triggers an external side effect before COMMIT and the transaction later rolls back, the external system will still have received the effect.

Use a transactional outbox:
1. Write business changes and an outbox event within the same InnoDB transaction.
2. COMMIT.
3. A worker reads the outbox and dispatches messages/emails/APIs.
4. Mark events processed using an idempotent mechanism.
5. Retry when external services experience transient errors.

This decouples database transactions from external side effects while preserving recoverability.

## 13. GET DIAGNOSTICS: Reading Error Causes

Handlers can use GET DIAGNOSTICS to retrieve information about the condition that just occurred.

Example:

~~~sql
DECLARE v_sqlstate CHAR(5);
DECLARE v_errno INT;
DECLARE v_message TEXT;

DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
BEGIN
    GET DIAGNOSTICS CONDITION 1
        v_sqlstate = RETURNED_SQLSTATE,
        v_errno = MYSQL_ERRNO,
        v_message = MESSAGE_TEXT;
END;
~~~

Useful items:

| Item | Meaning |
|---|---|
| RETURNED_SQLSTATE | SQLSTATE of the condition |
| MYSQL_ERRNO | MySQL error code |
| MESSAGE_TEXT | Error text |
| ROW_COUNT | Affected rows of the relevant statement in diagnostics context |

GET DIAGNOSTICS should be called early in the handler, before running extra statements that can alter the diagnostics area. If persisting errors, copy details into local variables before inserting into logs.

### 13.1. RESIGNAL Preserves the Original Error

If a handler merely logs an error and ends via CONTINUE, the error can be swallowed and the caller may assume the operation succeeded.

Use RESIGNAL to re-raise the current condition:

~~~sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    GET DIAGNOSTICS CONDITION 1
        v_sqlstate = RETURNED_SQLSTATE,
        v_errno = MYSQL_ERRNO,
        v_message = MESSAGE_TEXT;

    INSERT INTO routine_error_audit (
        sqlstate_value,
        mysql_errno,
        message_text,
        logged_at
    )
    VALUES (
        v_sqlstate,
        v_errno,
        v_message,
        NOW(6)
    );

    RESIGNAL;
END;
~~~

If the audit INSERT sits inside the same transaction and the caller later rolls back, the audit row is also rolled back. If durable error trails must survive rollback, log at the application layer or design a dedicated logging channel/transaction; do not assume an InnoDB log row inside a failed transaction will survive.

### 13.2. RESIGNAL Can Modify the Condition

RESIGNAL can re-raise a condition or alter attributes such as SQLSTATE/message using MySQL-supported syntax. When preserving the original error verbatim, use `RESIGNAL;` with no replacement details.

Do not emit a new error that obscures the root cause if the caller needs to classify deadlocks, duplicate keys, or constraint violations.

## 14. Cursor Handlers and NOT FOUND

In a cursor loop, `NOT FOUND` normally signals that FETCH has run out of rows. It is not a business error and must not be confused with SQLEXCEPTION.

Skeleton example:

~~~sql
DECLARE v_done BOOLEAN DEFAULT FALSE;
DECLARE v_id BIGINT UNSIGNED;

DECLARE cur CURSOR FOR
    SELECT source_id
    FROM import_stage
    ORDER BY source_id;

DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_done = TRUE;

OPEN cur;

read_loop: LOOP
    FETCH cur INTO v_id;

    IF v_done THEN
        LEAVE read_loop;
    END IF;

    -- Process current row.
END LOOP;

CLOSE cur;
~~~

### 14.1. Scope of the NOT FOUND Handler

If the same block both FETCHes a cursor and executes `SELECT ... INTO`, a `SELECT ... INTO` finding no rows can also trigger the NOT FOUND handler and set `v_done = TRUE`. The loop can then end early by mistake.

How to avoid:
- Use a nested block with its own NOT FOUND handler for `SELECT ... INTO`.
- Use separate flags for each purpose.
- Design SELECTs with unique keys and explicit no-row handling.
- Never place an overly broad handler covering unrelated operations.

### 14.2. Per-Row Errors Inside a Cursor Loop

You can use a child block with `CONTINUE HANDLER FOR SQLEXCEPTION` for statements processing a single row, as in the import example in Section 6. This lets:
- One row's INSERT error be recorded.
- The loop continue.
- Severe errors outside the child block reach the batch-level handler.

Do not declare a global CONTINUE handler for all SQLEXCEPTIONs without distinguishing skippable data errors from infrastructure errors that must halt the batch.

## 15. Error Handling in Java JDBC

When the application owns the transaction, JDBC must roll back if any business step fails.

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        debitAccount(connection, fromAccountId, amount);
        creditAccount(connection, toAccountId, amount);
        insertTransferAudit(connection, fromAccountId, toAccountId, amount);

        connection.commit();
    } catch (SQLException ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    }
}
~~~

### 15.1. Do Not Rely Only on Statement Rollback When Atomicity Is Needed

If one statement in a transaction fails, MySQL/InnoDB may only roll back that statement. JDBC does not automatically guarantee the whole transaction was rolled back. If business rules require all steps to succeed together, catch the exception and call `connection.rollback()`.

### 15.2. Savepoints in JDBC

~~~java
Savepoint savepoint = connection.setSavepoint("beforeOptionalStep");

try {
    runOptionalStep(connection);
} catch (SQLException ex) {
    connection.rollback(savepoint);
    // Decide whether to continue or throw depending on business contract.
}
~~~

Savepoints let you discard an optional step and continue the transaction. Do not use them if the actual error caused InnoDB to roll back the entire transaction, such as a deadlock victim. Once the transaction has rolled back, savepoints no longer exist.

### 15.3. Retrying Deadlocks

If you receive a deadlock error:
- Roll back the transaction (even if the server rolled back the full transaction, rolling back is safe).
- Start a new transaction.
- Re-run the entire operation from the start.
- Cap retries and add backoff.
- Ensure requests carry an idempotency key if clients may retry after timeouts.

Never retry only the final SQL statement when preceding statements were rolled back with the transaction.

## 16. Patterns to Use and Avoid

| Scenario | Recommended Pattern | Avoid |
|---|---|---|
| One data row fails while batch keeps processing others | Child block + CONTINUE handler + log error | Procedure-wide handler swallowing all errors |
| Multi-step funds transfer | Transaction + EXIT handler ROLLBACK + RESIGNAL | Ignoring error in credit step |
| Procedure inside a service's larger transaction | Caller-owned; procedure RESIGNALs without COMMIT/ROLLBACK | Procedure running START/COMMIT and ending parent transaction |
| Rolling back only an optional step | SAVEPOINT and ROLLBACK TO SAVEPOINT | Treating savepoint as a child transaction |
| Deadlock | Retry entire transaction | Retrying only the last statement |
| Sending email after writing data | Outbox after COMMIT | Sending email in a function and expecting ROLLBACK to undo it |
| Cursor end of rows | Scoped NOT FOUND handler | Treating NOT FOUND as a general SQL error |
| Logging errors after full rollback | Application log or dedicated separate log transaction | InnoDB log insert followed by rollback expecting log to survive |

## 17. Common Mistakes

| Mistake or Misconception | Cause | How to Fix |
|---|---|---|
| Statement error wiped out the whole transaction | Confusing statement rollback with transaction rollback | Check transaction state and error type |
| CONTINUE handler automatically rolls back | Handlers only direct control flow | Write ROLLBACK explicitly when needed |
| EXIT handler always exits the procedure | EXIT leaves the declaring block | Place handler in the proper scope |
| Handler swallows error making caller think it succeeded | CONTINUE finishes without reporting status | Return OUT status or RESIGNAL |
| Duplicate key rolled back the prior UPDATE | Earlier UPDATE remains in transaction | Caller decides COMMIT or ROLLBACK |
| Deadlock only rolls back the last statement | InnoDB rolls back the entire victim transaction | Retry the whole transaction |
| Lock timeout always rolls back full transaction | Default usually rolls back statement; config can change behavior | Inspect `innodb_rollback_on_timeout` |
| ROLLBACK does not undo MyISAM changes | MyISAM is non-transactional | Use InnoDB for data requiring atomicity |
| Audit log vanishes after error | Log was inside the same rolled-back transaction | Log outside transaction or use separate design |
| NOT FOUND stops cursor early | `SELECT ... INTO` in same scope triggered handler | Separate blocks and handlers |
| SAVEPOINT disappears after DDL | DDL triggers implicit commit | Keep DDL out of rollbackable transactions |
| Procedure rolls back caller's work | Procedure claims transaction ownership while caller has open transaction | Choose caller-owned or procedure-owned contract |
| Deadlock retry causes duplicate side effects | Non-idempotent external side effects | Outbox and idempotency keys |
| Using INSERT IGNORE to "skip all errors" | IGNORE turns errors into warnings/partial acceptance in some cases | Catch errors intentionally and inspect warnings |

## 18. Procedure for Designing Rollback Policies

Before writing handlers, answer these questions:

1. Is the business unit a single statement, a row, a batch, or an entire transaction?
2. If one row fails, may remaining rows still be processed?
3. If the second step fails, may the first step be kept?
4. Is the transaction owned by the procedure or the caller?
5. Do all participating tables use InnoDB?
6. Are there any DDL or implicit-commit operations in the workflow?
7. Which handlers process SQLEXCEPTION, SQLWARNING, and NOT FOUND?
8. Is CONTINUE genuinely appropriate, or is EXIT required?
9. Is RESIGNAL needed so the caller receives the error?
10. Is SAVEPOINT needed for an optional sub-step?
11. How are deadlocks and lock timeouts retried?
12. Does error logging need to survive rollback?
13. Are there side effects outside the database?
14. Could retries create duplicate data or duplicate side effects?
15. Have you tested with two sessions and real constraint errors?

## 19. Practice Exercises

### Exercise 1: Statement Rollback

Open a transaction, UPDATE a row, then INSERT an existing primary key. Inspect the row after the error. Confirm the prior UPDATE remains in the transaction.

### Exercise 2: Transaction Rollback

Repeat Exercise 1, then call ROLLBACK after the error. Confirm the earlier UPDATE was undone.

### Exercise 3: CONTINUE Handler

Write a procedure catching duplicate key with a CONTINUE handler, setting a flag, and returning an OUT parameter to the caller. Confirm the procedure continues after the failing statement.

### Exercise 4: EXIT Handler

Write a procedure using an EXIT handler for SQLEXCEPTION. Raise SIGNAL inside a nested block and identify which block terminates.

### Exercise 5: Full Business Operation Rollback

Create a funds transfer procedure with an InnoDB transaction. Intentionally make the credit step fail and confirm the source balance is not deducted after ROLLBACK.

### Exercise 6: Caller-Owned Transaction

Write a procedure without START/COMMIT/ROLLBACK. Call it inside a JDBC or SQL client transaction; trigger an error and let the caller roll back everything.

### Exercise 7: SAVEPOINT

Perform three write steps, place a savepoint before the second step, roll back to the savepoint, and commit. Determine exactly which steps are retained.

### Exercise 8: Cursors and NOT FOUND

Write a cursor loop with a CONTINUE HANDLER FOR NOT FOUND. Add a `SELECT ... INTO` returning no rows in the same scope and observe the done flag. Then move the SELECT into a child block with its own handler.

### Exercise 9: Batch Continuing When One Row Fails

Use `import_stage` and `imported_customer`. Include a duplicate email, use a local handler per INSERT, and log the error. Confirm valid rows commit and failing rows are not inserted.

### Exercise 10: Deadlock and Lock Timeout

Use two sessions locking two rows in opposite orders to create a deadlock in the lab. Record the error and confirm the victim transaction is rolled back entirely. Then test lock wait timeout and inspect `innodb_rollback_on_timeout`.

### Exercise 11: InnoDB vs. MyISAM

Create two tables with different engines, update both in a single transaction, and execute ROLLBACK. Compare which data is rolled back.

### Exercise 12: Error Logging and RESIGNAL

Write an EXIT handler using GET DIAGNOSTICS to log an error and then RESIGNAL. Trigger an error, roll back the transaction, and verify why transactional logs can disappear with the transaction.

## 20. Pre-Deployment Checklist

- [ ] Distinguished statement rollback, savepoint rollback, and transaction rollback.
- [ ] Identified whether transactions are owned by the procedure or the caller.
- [ ] Used InnoDB for all tables requiring atomicity.
- [ ] Understood autocommit and explicit transactions.
- [ ] Selected CONTINUE or EXIT according to business policy.
- [ ] Declared handlers in the proper scope.
- [ ] Handled NOT FOUND separately for cursors and `SELECT ... INTO`.
- [ ] Ensured handlers do not swallow errors without returning status.
- [ ] Used RESIGNAL when the caller must receive the original error.
- [ ] Used GET DIAGNOSTICS to gather SQLSTATE, error code, and message when needed.
- [ ] Called ROLLBACK explicitly when full business operation rollback is required.
- [ ] Used SAVEPOINT only inside an active transaction.
- [ ] Understood that DDL triggers implicit commits and invalidates savepoints.
- [ ] Distinguished full-transaction deadlock rollback from default statement-level lock timeout rollback.
- [ ] Checked `innodb_rollback_on_timeout`.
- [ ] Handled full-transaction retries and idempotency.
- [ ] Determined whether error logs are rolled back with the transaction.
- [ ] Avoided external side effects before COMMIT or used an outbox.
- [ ] Tested failures at every step and verified data state after rollback.

## 21. Conclusion

With InnoDB, a failing DML statement normally rolls back only that statement's changes; prior successful statements in the transaction remain until the caller COMMITs or ROLLBACKs. That is statement rollback. To ensure an entire multi-step business operation succeeds or fails together, you must roll back the entire transaction when a mandatory step fails.

Handlers only dictate how a stored program reacts to a condition: CONTINUE resumes after the statement, EXIT leaves the block, RESIGNAL forwards the error to the caller. A handler does not roll back automatically unless its body calls ROLLBACK. SAVEPOINT supports partial rollback within a transaction. Deadlocks are a special case where InnoDB rolls back the entire victim transaction; lock wait timeouts by default roll back only the waiting statement unless configuration changes that behavior. Finally, transactions protect only participating transactional engines; MyISAM tables and external side effects are not automatically rolled back. Establish transaction ownership, storage engine, handler scope, and retry policy before deploying.

## Official References

- [MySQL 8.4 Reference Manual – Condition Handling](https://dev.mysql.com/doc/refman/8.4/en/condition-handling.html)
- [MySQL 8.4 Reference Manual – DECLARE ... HANDLER](https://dev.mysql.com/doc/refman/8.4/en/declare-handler.html)
- [MySQL 8.4 Reference Manual – GET DIAGNOSTICS](https://dev.mysql.com/doc/refman/8.4/en/get-diagnostics.html)
- [MySQL 8.4 Reference Manual – RESIGNAL Statement](https://dev.mysql.com/doc/refman/8.4/en/resignal.html)
- [MySQL 8.4 Reference Manual – SIGNAL Statement](https://dev.mysql.com/doc/refman/8.4/en/signal.html)
- [MySQL 8.4 Reference Manual – Cursor Restrictions](https://dev.mysql.com/doc/refman/8.4/en/cursor-restrictions.html)
- [MySQL 8.4 Reference Manual – InnoDB Error Handling](https://dev.mysql.com/doc/refman/8.4/en/innodb-error-handling.html)
- [MySQL 8.4 Reference Manual – InnoDB Deadlocks](https://dev.mysql.com/doc/refman/8.4/en/innodb-deadlocks.html)
- [MySQL 8.4 Reference Manual – InnoDB Parameters: innodb_rollback_on_timeout](https://dev.mysql.com/doc/refman/8.4/en/innodb-parameters.html)
- [MySQL 8.4 Reference Manual – SAVEPOINT, ROLLBACK TO SAVEPOINT](https://dev.mysql.com/doc/refman/8.4/en/savepoint.html)
- [MySQL 8.4 Reference Manual – Statements That Cause an Implicit Commit](https://dev.mysql.com/doc/refman/8.4/en/implicit-commit.html)
- [MySQL 8.4 Reference Manual – InnoDB and Transaction Management](https://dev.mysql.com/doc/refman/8.4/en/innodb-autocommit-commit-rollback.html)
- [MySQL 8.4 Reference Manual – MyISAM Storage Engine](https://dev.mysql.com/doc/refman/8.4/en/myisam-storage-engine.html)
