# COMMIT/ROLLBACK Boundaries in Procedures vs. Functions/Triggers

This lesson belongs to the **Stored program** chapter of the **DATABASE_MYSQL** module. The module aims to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, privilege management, backups, and handling relational database operational issues. Stored procedures, stored functions, and triggers can all execute SQL statements, yet they carry different transaction control permissions. Confusing these boundaries can cause a procedure to accidentally `COMMIT` application work, a function to fail creation, or a trigger to break statement atomicity.

After this lesson, you will be able to distinguish transaction privileges across procedures, functions, and triggers; understand that transactions belong to the session/caller rather than automatically to a procedure; recognize the effects of `START TRANSACTION`, `COMMIT`, `ROLLBACK`, and implicit commits; design procedures under caller-owned or procedure-owned transaction models; handle errors using `EXIT HANDLER`, `ROLLBACK`, and `RESIGNAL`; use `SAVEPOINT` within the proper scope; and verify results across multiple sessions.

## 1. Transactions belong to the session, not to a procedure alone

In MySQL, a transaction is the unit of work of a connection/session. A stored procedure invoked via `CALL` runs inside the session that called it. A procedure does not automatically get an inner nested transaction just because it is defined as a separate object.

Example:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

CALL sp_write_transfer_audit(1, 2, 100);

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

If `sp_write_transfer_audit` only `INSERT`s audit data and issues no `COMMIT`, `ROLLBACK`, or `START TRANSACTION`, changes inside the procedure belong to the caller's open transaction. The final `COMMIT` confirms all transaction-safe changes in the session.

This can be visualized as:

~~~text
Connection / Session
└── Transaction T1
    ├── UPDATE accounts (caller)
    ├── CALL procedure
    │   └── INSERT audit_log (procedure)
    └── UPDATE accounts (caller)
        └── COMMIT T1
~~~

`CALL` does not create an independent transaction. Transaction boundaries are determined by transaction control statements, `autocommit`, and statements causing an implicit commit.

### Procedures can participate in the caller's transaction

If the caller has already opened a transaction, a procedure without transaction control can perform DML inside that transaction:

~~~sql
CREATE PROCEDURE sp_add_audit(
    IN p_action VARCHAR(50),
    IN p_reference_id BIGINT
)
BEGIN
    INSERT INTO audit_log (action_name, reference_id, created_at)
    VALUES (p_action, p_reference_id, CURRENT_TIMESTAMP(6));
END;
~~~

Caller:

~~~sql
START TRANSACTION;

UPDATE orders
SET status = 'PAID'
WHERE order_id = 1001;

CALL sp_add_audit('ORDER_PAID', 1001);

ROLLBACK;
~~~

If both `orders` and `audit_log` use InnoDB, both the `UPDATE` and `INSERT` are rolled back. The procedure cannot independently decide that the audit row should commit separately when the caller chooses `ROLLBACK`.

### Procedures can also control transactions themselves

MySQL permits stored procedures to run `START TRANSACTION`, `COMMIT`, and `ROLLBACK`. This is useful when a procedure is designed as a complete business operation, such as placing an order or transferring funds.

However, this capability affects the session's transaction. If a procedure is called when the caller already has an open transaction, `START TRANSACTION` can commit the pending transaction before starting a new one. `COMMIT` inside a procedure also commits the session's current transaction.

Therefore, before writing a procedure, clearly define who owns the transaction:

- Caller-owned: the application or outer procedure opens and closes the transaction; the child procedure only performs DML.
- Procedure-owned: the procedure itself opens, commits, or rolls back the transaction; the caller must understand the procedure will end any current transaction.

Never mix these two contracts in the same call flow.

## 2. Transaction permissions of procedures, functions, and triggers

MySQL applies different rules to the three stored program types.

| Capability | Stored procedure | Stored function | Trigger |
|---|---|---|---|
| Execute DML on eligible tables | Yes | Yes, within function restrictions | Yes |
| `START TRANSACTION` | Yes | No | No |
| `COMMIT` transaction | Yes | No | No |
| `ROLLBACK` entire transaction | Yes | No | No |
| Cause implicit commit/rollback | Possibly, if the statement is allowed in the call context | Prohibited | Prohibited |
| `ROLLBACK TO SAVEPOINT` | Yes | Prohibited under stored function rollback restrictions | Allowed because it does not end the transaction |
| Participates in caller's transaction | Yes | Yes | Yes, via the triggering statement |
| Can end caller's transaction | Yes | No | No |

Key restrictions:

1. Stored procedures are permitted to contain transaction-control statements, but a procedure called from a stored function or trigger must obey the function/trigger's restrictions.
2. Stored functions cannot contain statements that perform explicit or implicit commits/rollbacks.
3. Triggers cannot use statements that start or end a transaction.
4. Triggers are permitted to use `ROLLBACK TO SAVEPOINT` because it only rolls back to a savepoint without ending the transaction.
5. Procedures do not create nested transactions. A session can have only one active regular transaction at a time.

### Procedures called from functions or triggers

A normal procedure can contain `COMMIT`. However, if a function or trigger invokes that procedure, statements prohibited inside functions/triggers remain prohibited throughout the call chain.

Example not allowed:

~~~sql
CREATE PROCEDURE sp_commit_work()
BEGIN
    UPDATE counters
    SET counter_value = counter_value + 1
    WHERE counter_id = 1;

    COMMIT;
END;
~~~

If a trigger calls the procedure above, the trigger cannot use the procedure as an indirect way to `COMMIT`. MySQL enforces restrictions based on the calling context.

Design rule: procedures used inside triggers/functions must be routines without transaction control. When a business commit is needed, invoke that procedure directly from the application or an outer orchestrating procedure.

## 3. START TRANSACTION differs from BEGIN ... END in stored programs

In regular SQL, `BEGIN WORK` can be used as an alias for `START TRANSACTION`. Inside stored programs, however, the parser interprets `BEGIN [WORK]` as opening a `BEGIN ... END` compound statement.

Therefore, to begin a transaction inside a stored procedure or event, use:

~~~sql
START TRANSACTION;
~~~

Do not write:

~~~sql
BEGIN WORK;
~~~

expecting to start a transaction inside a procedure. In stored programs, `BEGIN` opens a code block.

Example:

~~~sql
CREATE PROCEDURE sp_example()
BEGIN
    START TRANSACTION;

    UPDATE counters
    SET counter_value = counter_value + 1
    WHERE counter_id = 1;

    COMMIT;
END;
~~~

Here:

- `BEGIN` opens the procedure body.
- `END` closes the procedure body.
- `START TRANSACTION` opens the transaction.
- `COMMIT` ends the transaction.

`START TRANSACTION` is prohibited inside stored functions or triggers.

## 4. START TRANSACTION can commit an already-open transaction

This is the most critical point when a procedure manages its own transaction.

In MySQL, starting a new transaction causes any pending transaction in the session to be committed first. Transactions cannot be nested.

Caller example:

~~~sql
START TRANSACTION;

UPDATE wallet
SET balance = balance - 50
WHERE wallet_id = 1;

CALL sp_process_payment(1001);

ROLLBACK;
~~~

Suppose `sp_process_payment` has the body:

~~~sql
CREATE PROCEDURE sp_process_payment(IN p_order_id BIGINT)
BEGIN
    START TRANSACTION;

    UPDATE orders
    SET status = 'PAID'
    WHERE order_id = p_order_id;

    COMMIT;
END;
~~~

Actual execution sequence:

1. Caller starts transaction `T1`.
2. Caller deducts 50 from `wallet` in `T1`.
3. `CALL` invokes procedure.
4. `START TRANSACTION` inside the procedure ends `T1` via an implicit commit.
5. Procedure starts transaction `T2`.
6. Procedure updates `orders` and runs `COMMIT T2`.
7. Procedure returns to caller.
8. Caller runs `ROLLBACK`, but both `T1` and `T2` have already ended; the `wallet` update was committed at step 4, and the `orders` update was committed at step 6.

The final `ROLLBACK` cannot undo the `wallet` change.

Diagram:

~~~text
Caller                         Procedure
  |                                |
  | START TRANSACTION (T1)         |
  | UPDATE wallet                  |
  |                                |
  | CALL ------------------------> |
  |                         START TRANSACTION
  |                         implicit COMMIT T1
  |                         START T2
  |                         UPDATE orders
  |                         COMMIT T2
  | <-------------------------- RETURN
  | ROLLBACK
  | (no T1/T2 left to roll back)
~~~

Never call a procedure that runs `START TRANSACTION` from inside a caller-managed transaction if the caller expects to roll back the entire unit of work.

### COMMIT inside a procedure also commits the caller's transaction

Even when a procedure does not run `START TRANSACTION`, `COMMIT` still terminates the session's current transaction.

~~~sql
CREATE PROCEDURE sp_update_and_commit()
BEGIN
    UPDATE settings
    SET setting_value = 'enabled'
    WHERE setting_name = 'feature_x';

    COMMIT;
END;
~~~

If the caller ran `START TRANSACTION` before `CALL`, the `COMMIT` above ends the caller's transaction, including changes made prior to calling the procedure.

A procedure containing `COMMIT` must therefore clearly advertise its transaction contract to callers.

## 5. Autocommit and multiple DML statements in a procedure

By default, MySQL enables `autocommit`. Every statement touching a transactional engine executes as its own transaction if the session has not explicitly opened one.

Check:

~~~sql
SELECT @@SESSION.autocommit;
~~~

When `autocommit = 1`:

~~~sql
UPDATE inventory
SET available_qty = available_qty - 1
WHERE product_id = 10;
~~~

Without an explicit transaction, a successful statement is committed automatically.

A procedure containing multiple DML statements without `START TRANSACTION`/`COMMIT` does not automatically turn the entire procedure body into a single transaction. When there is no caller transaction and `autocommit` is enabled, each DML statement obeys the session's autocommit rules.

Example:

~~~sql
CREATE PROCEDURE sp_two_updates()
BEGIN
    UPDATE account_summary
    SET amount = amount - 100
    WHERE account_id = 1;

    UPDATE account_summary
    SET amount = amount + 100
    WHERE account_id = 2;
END;
~~~

Without an enclosing transaction, do not assume both `UPDATE`s roll back together if the second statement fails. For both changes to belong to one atomic unit, either the caller must open a transaction or the procedure must be designed to own the transaction.

If `autocommit = 0`, the transaction remains open until `COMMIT` or `ROLLBACK`. Take special care with connection pools because session state can persist when connections are reused.

Do not change `autocommit` inside a shared procedure without an explicit contract. Running `SET autocommit = 1` when its current value is `0` causes an implicit commit.

## 6. Stored functions cannot control transactions

Stored functions are invoked inside SQL expressions, such as `SELECT`, `WHERE`, `ORDER BY`, or DML expressions. Because a function can run in the context of a statement, MySQL forbids functions from terminating the caller's enclosing transaction.

Example function reading stock quantity:

~~~sql
CREATE FUNCTION fn_available_stock(
    p_product_id BIGINT UNSIGNED
)
RETURNS INT
READS SQL DATA
BEGIN
    DECLARE v_available INT DEFAULT NULL;

    SELECT available_qty
    INTO v_available
    FROM inventory
    WHERE product_id = p_product_id;

    RETURN v_available;
END;
~~~

Can be called:

~~~sql
SELECT fn_available_stock(10);
~~~

The function above only reads data and does not start, commit, or roll back transactions.

The following are invalid inside a stored function:

~~~sql
START TRANSACTION;
COMMIT;
ROLLBACK;
~~~

Functions are also prohibited from running statements that cause an implicit commit/rollback. For instance, DDL statements like `ALTER TABLE`, `CREATE TABLE`, or `TRUNCATE TABLE` cannot be used to indirectly control transactions from a function.

### Functions still execute inside the caller's transaction

Example:

~~~sql
START TRANSACTION;

UPDATE inventory
SET available_qty = available_qty - 1
WHERE product_id = 10;

SELECT fn_available_stock(10);

ROLLBACK;
~~~

The function reads data state according to the session's transaction/read view. The function does not commit the `inventory` change. The caller's `ROLLBACK` still decides the transaction outcome.

Stored functions can execute DML within MySQL's restrictions, but that DML does not make the function the transaction owner. It remains bound to the statement/caller's transaction. In addition, a function cannot modify a table already being used for reading or writing by the statement invoking the function.

### Procedures called from functions

If a function calls a procedure, that procedure is likewise barred from running statements prohibited inside functions.

For example, a procedure containing `COMMIT` can run standalone via `CALL`, yet cannot be called from a function to bypass transaction restrictions.

## 7. Triggers cannot start or end transactions

Triggers fire during `INSERT`, `UPDATE`, or `DELETE` on the associated table. A trigger is part of the triggering statement.

Example:

~~~sql
CREATE TABLE order_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    order_id BIGINT UNSIGNED NOT NULL,
    action_name VARCHAR(30) NOT NULL,
    created_at DATETIME(6) NOT NULL
) ENGINE=InnoDB;

CREATE TRIGGER trg_orders_after_insert
AFTER INSERT ON orders
FOR EACH ROW
BEGIN
    INSERT INTO order_audit (
        order_id,
        action_name,
        created_at
    )
    VALUES (
        NEW.order_id,
        'ORDER_CREATED',
        CURRENT_TIMESTAMP(6)
    );
END;
~~~

When the application `INSERT`s an order, the trigger inserts an audit record within the exact same statement transaction context.

~~~sql
START TRANSACTION;

INSERT INTO orders (order_id, customer_id, status)
VALUES (1001, 42, 'NEW');

ROLLBACK;
~~~

If both `orders` and `order_audit` use InnoDB, both the order row and the audit row are rolled back.

### No COMMIT or ROLLBACK inside triggers

Triggers cannot use statements that start or end a transaction:

~~~sql
START TRANSACTION;
COMMIT;
ROLLBACK;
~~~

A trigger cannot end the application's transaction because it is part of the executing statement.

If a trigger calls a stored procedure, that procedure also cannot contain statements causing an explicit or implicit commit or rollback.

### ROLLBACK TO SAVEPOINT is an exception

Triggers are allowed to use `ROLLBACK TO SAVEPOINT` because that statement does not end the transaction.

~~~sql
SAVEPOINT sp_trigger_work;

INSERT INTO audit_detail (...);

ROLLBACK TO SAVEPOINT sp_trigger_work;
~~~

This only illustrates savepoint semantics, not a trigger pattern to use routinely. Savepoints created inside a trigger scope have their own level; when the trigger exits, savepoints at that level are released and previous-level savepoints are restored.

Do not confuse `ROLLBACK TO SAVEPOINT` with `ROLLBACK`:

| Statement | Outcome |
|---|---|
| `ROLLBACK` | Ends the transaction and undoes all uncommitted transactional changes |
| `ROLLBACK TO SAVEPOINT x` | Undoes changes after savepoint `x`; the transaction continues |
| `RELEASE SAVEPOINT x` | Removes the savepoint without committing or rolling back the transaction |

### Errors inside triggers and statement rollback

If a trigger raises an error, the statement that fired the trigger fails.

With transactional tables like InnoDB, changes made by that statement are rolled back along with transactional changes made by the trigger. The caller's broader transaction may remain open; the caller decides whether to continue or roll back the whole transaction.

With non-transactional tables, MySQL cannot undo writes made before the error occurred. Therefore, operations requiring atomicity should use a transactional storage engine.

## 8. Implicit commits: a procedure can commit without writing COMMIT

`COMMIT` is not the only statement that ends a transaction. Certain statements automatically commit an open transaction before executing; many also commit afterward.

Common examples:

| Category | Examples |
|---|---|
| DDL | `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE` |
| Indexes | `CREATE INDEX`, `DROP INDEX` |
| Views/routines/triggers | `CREATE VIEW`, `ALTER VIEW`, `CREATE PROCEDURE`, `CREATE FUNCTION`, `CREATE TRIGGER` |
| Database administration | `CREATE DATABASE`, `DROP DATABASE` |
| DDL-style data deletion | `TRUNCATE TABLE` |
| User privileges | `GRANT`, `REVOKE`, `CREATE USER`, `ALTER USER` |
| Transaction/lock control | `START TRANSACTION`, `BEGIN`, `LOCK TABLES`, certain cases of `SET autocommit = 1` |

A procedure may contain certain DDL statements, but that does not make DDL transactional or rollbackable.

Example:

~~~sql
START TRANSACTION;

UPDATE account_summary
SET amount = amount - 100
WHERE account_id = 1;

ALTER TABLE audit_log
ADD COLUMN source_name VARCHAR(50);

ROLLBACK;
~~~

`ALTER TABLE` triggers an implicit commit before executing. The earlier `UPDATE` has already been committed; `ROLLBACK` after `ALTER` cannot restore the `UPDATE`.

### Temporary tables have an exception but lack atomic rollback

`CREATE TEMPORARY TABLE` and `DROP TEMPORARY TABLE` do not trigger an implicit commit the way regular `CREATE/DROP TABLE` does. However, these operations are still not rolled back like DML.

Example:

~~~sql
START TRANSACTION;

CREATE TEMPORARY TABLE tmp_work (
    id INT PRIMARY KEY
);

ROLLBACK;
~~~

After `ROLLBACK`, the temporary table still exists. This means transactions cannot restore the entire session state as if `CREATE TEMPORARY TABLE` had never occurred.

Certain other operations on temporary tables, such as `ALTER TABLE` or `CREATE INDEX`, can still cause an implicit commit.

### Never use DDL as an intermediate step in a business transaction

If a procedure executes:

1. `UPDATE` balance.
2. `CREATE TABLE` or `TRUNCATE` a table.
3. `INSERT` business data.
4. `ROLLBACK` on error.

then the DDL step may have already committed the earlier `UPDATE`. The proper design is separating DDL from business transactions or using pre-created staging tables.

## 9. Choosing the caller-owned or procedure-owned model

This is the most critical design decision.

### Caller-owned transaction model

The procedure contains only DML and does not issue `START TRANSACTION`, `COMMIT`, or full-transaction `ROLLBACK`.

~~~sql
CREATE PROCEDURE sp_change_order_status(
    IN p_order_id BIGINT,
    IN p_new_status VARCHAR(20)
)
BEGIN
    UPDATE orders
    SET status = p_new_status
    WHERE order_id = p_order_id;
END;
~~~

Caller:

~~~sql
START TRANSACTION;

CALL sp_change_order_status(1001, 'PAID');

INSERT INTO order_audit (
    order_id,
    action_name,
    created_at
)
VALUES (
    1001,
    'STATUS_CHANGED',
    CURRENT_TIMESTAMP(6)
);

COMMIT;
~~~

Advantages:

- The application decides transaction boundaries.
- Multiple procedures and DML statements can be combined into one transaction.
- Procedures are easy to reuse across many workflows.
- The caller can roll back everything if a later step fails.

Disadvantages:

- The caller must understand that the procedure does not self-commit.
- If called outside a transaction with `autocommit` enabled, each DML statement autocommits individually.
- The transaction contract must be clearly documented in the API spec.

Use this model when the application coordinates multiple operations and decides when to commit.

### Procedure-owned transaction model

The procedure opens and closes the transaction itself.

~~~sql
CREATE PROCEDURE sp_record_payment(
    IN p_order_id BIGINT,
    IN p_payment_ref VARCHAR(100)
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    UPDATE orders
    SET status = 'PAID'
    WHERE order_id = p_order_id;

    INSERT INTO payments (
        order_id,
        payment_ref,
        created_at
    )
    VALUES (
        p_order_id,
        p_payment_ref,
        CURRENT_TIMESTAMP(6)
    );

    COMMIT;
END;
~~~

Advantages:

- The entire business action is encapsulated in one routine.
- The procedure rolls itself back if an error occurs before commit.
- The caller simply invokes a single business operation.

Disadvantages:

- The procedure can commit an open caller transaction when running `START TRANSACTION`.
- Cannot be safely composed into a larger caller-managed transaction.
- Harder to coordinate with external multi-step workflows.
- Implicit commits must be audited across every inner statement.

Use this model when the procedure is a standalone business unit and callers accept that the procedure owns the session's transaction.

### Never mix the two models

Do not write a procedure that sometimes self-commits and sometimes waits for the caller to commit based on a boolean flag or unclear session state. That makes it hard for callers to predict whether a transaction has ended.

A clear convention:

- Procedures suffixed/grouped as `*_in_tx`: no transaction control; caller owns the transaction.
- Standalone business procedures: manage transactions themselves and document clearly not to call inside an active transaction.
- Triggers/functions: no transaction control; execute logic only inside the caller's transaction.

Routine names are only a convention; document contracts explicitly and review actual code.

## 10. Error handling in procedure-owned transactions

When a procedure owns the transaction, ensure errors do not leave an active transaction open.

Common pattern:

~~~sql
CREATE PROCEDURE sp_atomic_operation()
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    -- Business DML statements
    UPDATE ...;
    INSERT ...;

    COMMIT;
END;
~~~

Meaning:

- `EXIT HANDLER` runs when an `SQLEXCEPTION` occurs.
- `ROLLBACK` undoes the current transaction.
- `RESIGNAL` rethrows the error so the caller knows the operation failed.
- If no error occurs, `COMMIT` confirms all changes.

### Why is RESIGNAL needed?

If a handler only runs `ROLLBACK` and exits without `RESIGNAL`, the caller may not receive the original error as expected. `RESIGNAL` propagates the active error outward so the application or outer procedure can decide the next step.

Never catch an error and silently ignore it when the caller needs to know the transaction failed.

### EXIT HANDLER vs. CONTINUE HANDLER

| Handler | Behavior |
|---|---|
| `EXIT` | Exits the `BEGIN...END` block where the handler is declared after running the handler |
| `CONTINUE` | Runs the handler and continues right after the failing statement |
| `UNDO` | Not supported by MySQL |

Transaction handlers typically use `EXIT` to prevent subsequent business steps from running after a statement fails.

### Declaring handlers in the right position

Inside a stored program block, declare variables and conditions before handlers; all `DECLARE`s must precede executable statements.

Example:

~~~sql
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;
    UPDATE inventory
    SET available_qty = available_qty - 1
    WHERE product_id = 10;
    COMMIT;
END
~~~

### NOT FOUND is not SQLEXCEPTION

SQLSTATE class `02` is `NOT FOUND`, which is not part of `SQLEXCEPTION`. A `SELECT ... INTO` that finds no rows can trigger `NOT FOUND` and keep running without firing an `SQLEXCEPTION` handler.

Example:

~~~sql
DECLARE v_available INT DEFAULT NULL;

SELECT available_qty
INTO v_available
FROM inventory
WHERE product_id = p_product_id
FOR UPDATE;

IF v_available IS NULL THEN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Product does not exist';
END IF;
~~~

Because the variable starts as `NULL` and the `available_qty` column is declared `NOT NULL`, missing rows can be detected via `NULL`. `SIGNAL` raises a class `45` exception for `EXIT HANDLER FOR SQLEXCEPTION` to catch.

## 11. SAVEPOINT: partial rollback without ending the transaction

`SAVEPOINT` creates a marker within a transaction. `ROLLBACK TO SAVEPOINT` undoes changes made after that marker while keeping the transaction active.

Example:

~~~sql
START TRANSACTION;

UPDATE orders
SET status = 'PROCESSING'
WHERE order_id = 1001;

SAVEPOINT before_optional_audit;

INSERT INTO audit_log (
    order_id,
    action_name,
    created_at
)
VALUES (
    1001,
    'PROCESSING',
    CURRENT_TIMESTAMP(6)
);

ROLLBACK TO SAVEPOINT before_optional_audit;

UPDATE orders
SET status = 'PAID'
WHERE order_id = 1001;

COMMIT;
~~~

Outcome:

- The first `UPDATE` is preserved.
- The audit `INSERT` after the savepoint is undone.
- The final `UPDATE` executes.
- `COMMIT` ends the transaction.

### SAVEPOINT inside a procedure

A procedure can use savepoints of the current transaction if one is active. It does not create a new transaction.

~~~sql
CREATE PROCEDURE sp_optional_step()
BEGIN
    SAVEPOINT sp_optional_step;

    INSERT INTO audit_log (
        order_id,
        action_name,
        created_at
    )
    VALUES (
        1001,
        'OPTIONAL_STEP',
        CURRENT_TIMESTAMP(6)
    );

    -- When needing to undo only the optional step:
    ROLLBACK TO SAVEPOINT sp_optional_step;

    RELEASE SAVEPOINT sp_optional_step;
END;
~~~

This procedure must be called inside an intentional transaction if the savepoint needs to coexist with other steps. Without an enclosing transaction, `autocommit` may commit each statement immediately; never treat savepoints as independent transactions.

Savepoint names are managed within the transaction. Creating a savepoint with an existing name replaces the older savepoint of that name.

### SAVEPOINT does not release all row locks

`ROLLBACK TO SAVEPOINT` does not necessarily release all row locks acquired after the savepoint. InnoDB retains certain locks stored in memory until the transaction ends.

Thus, partial rollback does not mean all lock resources have been freed.

### SAVEPOINT inside functions and triggers

MySQL creates a separate savepoint level when a stored function is invoked or a trigger fires. Savepoints at earlier levels are temporarily inaccessible from the new level; savepoints created within that level are released when the function/trigger exits and earlier-level savepoints are restored. This scoping rule does not grant `COMMIT` or full-transaction `ROLLBACK` to functions/triggers. Specifically, triggers are documented to permit `ROLLBACK TO SAVEPOINT`; stored functions remain subject to rollback statement restrictions.

For triggers, MySQL allows `ROLLBACK TO SAVEPOINT` because it does not end the transaction. This differs completely from full-transaction `ROLLBACK`, which is prohibited inside triggers.

## 12. DDL and implicit commits inside stored procedures

Procedures are permitted to contain certain DDL statements, yet DDL does not become transactional merely by appearing inside `BEGIN ... END`.

Example:

~~~sql
CREATE PROCEDURE sp_bad_migration()
BEGIN
    START TRANSACTION;

    UPDATE settings
    SET setting_value = 'new'
    WHERE setting_name = 'mode';

    TRUNCATE TABLE staging_data;

    ROLLBACK;
END;
~~~

`TRUNCATE TABLE` causes an implicit commit. The prior `UPDATE settings` may already be committed before `TRUNCATE`. The `ROLLBACK` at the end of the procedure cannot restore it.

Statements that commonly cause an implicit commit include:

- `CREATE/ALTER/DROP TABLE`.
- `CREATE/DROP INDEX`.
- `CREATE/ALTER/DROP VIEW`.
- `CREATE/ALTER/DROP PROCEDURE` or `FUNCTION`.
- `CREATE/DROP TRIGGER`.
- `TRUNCATE TABLE`.
- `CREATE/DROP DATABASE`.
- `GRANT/REVOKE` and certain user management statements.

A few narrow exceptions such as `CREATE TEMPORARY TABLE` and `DROP TEMPORARY TABLE` do not implicitly commit, though creating/dropping temporary tables still cannot be rolled back like DML. `ALTER` or `CREATE INDEX` operations on temporary tables can still cause implicit commits.

Before adding DDL to a procedure, check the implicit-commit documentation for your exact MySQL version. In business workflows, prepare schemas/staging tables before opening DML transactions.

## 13. Storage engines determine how far rollback reaches

`COMMIT`/`ROLLBACK` only carries full transactional guarantees for tables using a transactional storage engine.

With InnoDB:

- `INSERT`/`UPDATE`/`DELETE` inside a transaction can commit or roll back.
- Triggers modifying InnoDB tables run inside the same statement/transaction.
- When a statement fails, transactional changes of that statement are rolled back.
- When a transaction rolls back completely, row locks held by the transaction are released.

With non-transactional tables:

- Changes may be persisted immediately.
- `ROLLBACK` does not undo those writes.
- If a statement or trigger fails, writes performed before the error may remain.

Dangerous example:

~~~sql
CREATE TABLE business_data (
    id INT PRIMARY KEY,
    value_num INT NOT NULL
) ENGINE=InnoDB;

CREATE TABLE legacy_log (
    id INT PRIMARY KEY,
    message_text VARCHAR(100)
) ENGINE=MyISAM;
~~~

A procedure updates `business_data` and then writes to `legacy_log`. If the transaction rolls back, `business_data` is undone while `legacy_log` retains its changes.

To ensure business atomicity, prefer using the same transactional engine across all involved tables, typically InnoDB.

## 14. A trigger error does not mean full-transaction rollback

Distinguish statement rollback from transaction rollback.

Suppose the caller runs:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

INSERT INTO orders (...); -- Trigger raises an error

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

If the trigger causes `INSERT` to fail on an InnoDB table, the `INSERT` statement rolls back. The caller's transaction may still remain open. The first `UPDATE` is not automatically rolled back just because the second statement failed.

The application must decide:

- Continue the transaction if the statement error is recoverable and business logic permits.
- `ROLLBACK` the entire transaction if the business unit must be atomic.
- Or use a handler in an orchestrating procedure to roll back and `RESIGNAL`.

Never assume every SQL error automatically rolls back the entire transaction. Behavior depends on error type, storage engine, and InnoDB configuration.

Specifically:

- Deadlocks normally cause InnoDB to roll back the entire victim transaction.
- Lock wait timeouts by default typically roll back only the timed-out statement, not necessarily the whole transaction.
- Handlers can explicitly `ROLLBACK` the transaction when the procedure owns it.

## 15. Reference design: procedure-owned order placement

Problem: deduct inventory and create an order in one transaction. If stock is insufficient or `INSERT` fails, roll back everything.

### Step 1: create InnoDB tables

~~~sql
CREATE TABLE inventory (
    product_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    available_qty INT NOT NULL
) ENGINE=InnoDB;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME(6) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE order_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    order_id BIGINT UNSIGNED NOT NULL,
    action_name VARCHAR(30) NOT NULL,
    created_at DATETIME(6) NOT NULL
) ENGINE=InnoDB;
~~~

### Step 2: create the audit trigger

~~~sql
DELIMITER //

CREATE TRIGGER trg_orders_after_insert
AFTER INSERT ON orders
FOR EACH ROW
BEGIN
    INSERT INTO order_audit (
        order_id,
        action_name,
        created_at
    )
    VALUES (
        NEW.order_id,
        'ORDER_CREATED',
        CURRENT_TIMESTAMP(6)
    );
END//

DELIMITER ;
~~~

The trigger does not `COMMIT`. The audit `INSERT` participates in the same `orders` `INSERT` statement and current transaction.

### Step 3: create the self-managing transaction procedure

~~~sql
DELIMITER //

CREATE PROCEDURE sp_place_order(
    IN p_product_id BIGINT UNSIGNED,
    IN p_quantity INT
)
BEGIN
    DECLARE v_available INT DEFAULT NULL;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Quantity must be positive';
    END IF;

    SELECT available_qty
    INTO v_available
    FROM inventory
    WHERE product_id = p_product_id
    FOR UPDATE;

    IF v_available IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Product does not exist';
    END IF;

    IF v_available < p_quantity THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Insufficient inventory';
    END IF;

    UPDATE inventory
    SET available_qty = available_qty - p_quantity
    WHERE product_id = p_product_id;

    INSERT INTO orders (
        product_id,
        quantity,
        status,
        created_at
    )
    VALUES (
        p_product_id,
        p_quantity,
        'NEW',
        CURRENT_TIMESTAMP(6)
    );

    COMMIT;
END//

DELIMITER ;
~~~

Key points:

- The procedure owns the transaction.
- Callers must not open a transaction prior to `CALL` if they expect to preserve other uncommitted changes.
- `SELECT ... FOR UPDATE` locks the inventory row inside the transaction.
- `SIGNAL` on invalid data raises an exception.
- `EXIT HANDLER` rolls back and runs `RESIGNAL`.
- `INSERT` into `orders` fires the trigger; the audit row participates in the transaction.
- The final `COMMIT` confirms inventory, order, and audit atomically.

### Step 4: call the procedure

~~~sql
INSERT INTO inventory (product_id, available_qty)
VALUES (10, 20);

CALL sp_place_order(10, 3);
~~~

Verify:

~~~sql
SELECT *
FROM inventory
WHERE product_id = 10;

SELECT *
FROM orders
ORDER BY order_id DESC;

SELECT *
FROM order_audit
ORDER BY audit_id DESC;
~~~

Expected result:

- `available_qty` drops from `20` to `17`.
- One new order is created.
- One `ORDER_CREATED` audit record is created.

### Step 5: trigger an error to observe rollback

~~~sql
CALL sp_place_order(10, 1000);
~~~

The procedure raises `Insufficient inventory`. `EXIT HANDLER` executes `ROLLBACK` followed by `RESIGNAL`.

Verify again:

~~~sql
SELECT available_qty
FROM inventory
WHERE product_id = 10;

SELECT COUNT(*) AS order_count
FROM orders;

SELECT COUNT(*) AS audit_count
FROM order_audit;
~~~

No new order or audit row exists; inventory remains unchanged.

### Step 6: test the procedure when the caller already has a transaction

In a test session:

~~~sql
START TRANSACTION;

INSERT INTO inventory (product_id, available_qty)
VALUES (20, 50);

CALL sp_place_order(10, 1);

ROLLBACK;
~~~

`START TRANSACTION` inside `sp_place_order` terminates the caller's open transaction. Therefore, `INSERT inventory product_id=20` may already be committed before the procedure opens its own transaction. The caller's final `ROLLBACK` cannot undo that `INSERT`.

Only run this experiment in a lab database. It demonstrates the procedure-owned transaction contract.

## 16. Reference design: procedure letting the caller own the transaction

When the application needs to combine multiple business steps, the procedure should execute DML only.

~~~sql
DELIMITER //

CREATE PROCEDURE sp_change_stock(
    IN p_product_id BIGINT UNSIGNED,
    IN p_delta INT
)
BEGIN
    UPDATE inventory
    SET available_qty = available_qty + p_delta
    WHERE product_id = p_product_id;
END//

DELIMITER ;
~~~

Caller:

~~~sql
START TRANSACTION;

CALL sp_change_stock(10, -2);

INSERT INTO order_audit (
    order_id,
    action_name,
    created_at
)
VALUES (
    0,
    'MANUAL_STOCK_CHANGE',
    CURRENT_TIMESTAMP(6)
);

ROLLBACK;
~~~

Because the procedure issues no `COMMIT`/`ROLLBACK`, both `UPDATE inventory` and `INSERT audit` participate in the caller's transaction. `ROLLBACK` undoes both if both tables use InnoDB.

This model fits applications performing transaction orchestration in the service layer.

## 17. Testing transaction boundaries across two sessions

Use two independent connections to observe caller and procedure transactions.

### Test A: non-committing procedure

Session A:

~~~sql
START TRANSACTION;

CALL sp_change_stock(10, -1);

SELECT available_qty
FROM inventory
WHERE product_id = 10;
~~~

Session B, before Session A commits:

~~~sql
SELECT available_qty
FROM inventory
WHERE product_id = 10;
~~~

With InnoDB and the default `REPEATABLE READ` isolation level, Session B does not see Session A's uncommitted change. After Session B runs, return to Session A:

~~~sql
ROLLBACK;
~~~

Session B continues seeing the old value after Session A rolls back.

### Test B: self-committing procedure

Create a test table and procedure purely for demonstration:

~~~sql
CREATE TABLE transaction_probe (
    probe_id INT NOT NULL PRIMARY KEY,
    value_num INT NOT NULL
) ENGINE=InnoDB;

INSERT INTO transaction_probe (probe_id, value_num)
VALUES (1, 0);
~~~

~~~sql
DELIMITER //

CREATE PROCEDURE sp_commit_marker()
BEGIN
    UPDATE transaction_probe
    SET value_num = value_num + 1
    WHERE probe_id = 1;

    COMMIT;
END//

DELIMITER ;
~~~

Session A:

~~~sql
START TRANSACTION;

UPDATE transaction_probe
SET value_num = value_num + 10
WHERE probe_id = 1;

CALL sp_commit_marker();

ROLLBACK;
~~~

Session B reads `transaction_probe` again. Both the caller's `+10` change and the procedure's `+1` change were committed by the `COMMIT` inside the procedure. The final `ROLLBACK` in Session A has no effect on an already-ended transaction.

### Test C: trigger participating in a statement

Create an audit trigger on an InnoDB table, then:

~~~sql
START TRANSACTION;

INSERT INTO orders (
    product_id,
    quantity,
    status,
    created_at
)
VALUES (
    10,
    1,
    'NEW',
    CURRENT_TIMESTAMP(6)
);

ROLLBACK;
~~~

Inspect both `orders` and `order_audit`. Both changes must be rolled back if the statement succeeds and the transaction later rolls back.

## 18. Monitoring open transactions and identifying who committed

When a procedure or trigger is called from an application, you may need to investigate which session holds a transaction.

Inspect InnoDB transactions:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_mysql_thread_id,
    trx_rows_modified,
    trx_rows_locked,
    trx_query
FROM INFORMATION_SCHEMA.INNODB_TRX
ORDER BY trx_started;
~~~

Inspect sessions:

~~~sql
SELECT
    ID,
    USER,
    HOST,
    DB,
    COMMAND,
    TIME,
    STATE,
    INFO
FROM INFORMATION_SCHEMA.PROCESSLIST
ORDER BY TIME DESC;
~~~

Match `trx_mysql_thread_id` against `PROCESSLIST.ID`.

Performance Schema provides transaction event tables to view transactions linked to statements and stored program events. You can query:

~~~sql
SELECT
    THREAD_ID,
    EVENT_ID,
    STATE,
    AUTOCOMMIT,
    ISOLATION_LEVEL,
    ACCESS_MODE,
    TIMER_START,
    TIMER_END
FROM performance_schema.events_transactions_history_long
ORDER BY THREAD_ID, EVENT_ID;
~~~

History tables have bounded capacity and depend on enabled consumers/instruments. Do not assume every transaction remains in history.

When investigating a procedure causing unexpected commits:

1. Inspect the procedure source and any nested procedures it calls.
2. Search for `START TRANSACTION`, `COMMIT`, `ROLLBACK`, and `SET autocommit`.
3. Search for DDL and statements causing implicit commits.
4. Check whether the caller opened a transaction before `CALL`.
5. Check session `autocommit`.
6. Correlate transaction events and commit timestamps.
7. Check triggers/functions invoked indirectly by statements.

## 19. Common errors and fixes

| Symptom | Cause | How to handle |
|---|---|---|
| Function fails creation due to `COMMIT` | Stored functions cannot control transactions | Remove transaction-control statements from the function |
| Trigger errors on `COMMIT` | Triggers cannot terminate transactions | Let the caller/procedure coordinate transactions |
| Procedure commits caller data | `COMMIT` acts on the session's current transaction | Clearly choose caller-owned or procedure-owned |
| `START TRANSACTION` in procedure loses pre-`CALL` rollback capability | `START TRANSACTION` implicitly commits pending transaction | Do not call procedure-owned routines inside a caller's transaction |
| Thinking `BEGIN` in a procedure starts a transaction | Parser treats `BEGIN` as a `BEGIN...END` block | Use `START TRANSACTION` |
| Multi-DML procedure fails midway but keeps earlier steps | No enclosing transaction and `autocommit` is on | Open a transaction in the caller or procedure |
| `ROLLBACK` does not undo `TRUNCATE` | `TRUNCATE` triggers implicit commit and does not roll back like DML | Use `DELETE` inside a transaction or staging |
| Handler rolls back but caller sees no error | Handler swallowed the error | Use `RESIGNAL` after `ROLLBACK` |
| `SQLEXCEPTION` handler misses `NOT FOUND` | SQLSTATE class `02` is outside `SQLEXCEPTION` | Declare a `NOT FOUND` handler or check `SELECT INTO` variables |
| Trigger fails but transaction remains open | Statement rolled back; outer transaction may remain active | Caller decides to `ROLLBACK` the entire transaction |
| `ROLLBACK` fails to restore MyISAM table | Non-transactional engine does not support rollback | Use InnoDB for data requiring atomicity |
| `ROLLBACK TO SAVEPOINT` still holds locks | InnoDB does not release all row locks on savepoint rollback | End the transaction when all locks must be released |
| Procedure called from trigger cannot run `COMMIT` | Nested procedure must obey trigger restrictions | Move transaction control outside the call chain |
| Procedure in a connection pool leaves open transactions | Missing `COMMIT`/`ROLLBACK` or unhandled errors | Use handlers, check `autocommit`, and clean up connections |
| DDL inside procedure commits early | DDL triggers implicit commit | Separate DDL migrations from DML transactions |

## 20. Transaction design checklist for stored programs

- [ ] Determined whether the transaction belongs to the caller or the procedure.
- [ ] Explicitly documented the transaction contract for every procedure.
- [ ] Caller-owned procedures contain no `START TRANSACTION`, `COMMIT`, or full-transaction `ROLLBACK`.
- [ ] Procedure-owned procedures are invoked only when the caller has no transaction to preserve.
- [ ] Understood that `START TRANSACTION` can commit a pending transaction.
- [ ] Never assumed MySQL supports nested transactions.
- [ ] Distinguished `BEGIN ... END` from `START TRANSACTION`.
- [ ] Functions contain no explicit or implicit commits or rollbacks.
- [ ] Triggers contain no statements that start or end transactions.
- [ ] Procedures called from functions/triggers obey call-context restrictions.
- [ ] Understood that `ROLLBACK TO SAVEPOINT` does not end the transaction.
- [ ] Declared `EXIT HANDLER` for `SQLEXCEPTION` when a procedure owns the transaction.
- [ ] Handler rolls back and runs `RESIGNAL` when callers need error notification.
- [ ] Handled `NOT FOUND` separately when using `SELECT ... INTO`.
- [ ] Audited DDL and implicit-commit statements.
- [ ] Tables requiring atomicity use a transactional engine like InnoDB.
- [ ] Tested trigger errors and statement rollbacks.
- [ ] Tested transactions across two sessions.
- [ ] Checked `autocommit` and session state when using connection pools.
- [ ] Did not run Content QA/refactors or production migrations during this authoring step.

## 21. Principles to remember

1. Transactions are session-scoped, not automatically scoped to a procedure.
2. Stored procedures can execute `START TRANSACTION`, `COMMIT`, and `ROLLBACK`.
3. `COMMIT`/`ROLLBACK` inside a procedure affects the session's active transaction, including changes made by the caller.
4. `START TRANSACTION` terminates any pending transaction before starting a new one; MySQL does not support conventional nested transactions.
5. Inside stored programs, `BEGIN` opens a `BEGIN...END` block; use `START TRANSACTION` to start a transaction inside procedures/events.
6. Stored functions cannot perform explicit or implicit commits/rollbacks.
7. Triggers cannot start or end transactions; `ROLLBACK TO SAVEPOINT` is an exception because it does not end the transaction.
8. Procedures called from functions/triggers must obey the calling context's restrictions.
9. Functions and triggers participate in the statement/caller's transaction and never decide commits themselves.
10. A trigger error fails the statement; with InnoDB, transactional changes of that statement roll back, while an enclosing transaction may remain open.
11. `EXIT HANDLER FOR SQLEXCEPTION` combined with `ROLLBACK` and `RESIGNAL` is the standard error-handling pattern for procedure-owned transactions.
12. `NOT FOUND` is not part of `SQLEXCEPTION`; handle SQLSTATE class `02` explicitly when needed.
13. `SAVEPOINT` only creates a marker inside the current transaction, not a new transaction.
14. DDL such as `TRUNCATE`, `ALTER TABLE`, and `CREATE INDEX` can implicitly commit; never place them mid-transaction when rollback is needed.
15. `ROLLBACK` is fully guaranteed only with transactional storage engines; InnoDB is the standard choice.
16. Test transaction boundaries across caller, procedure, function, trigger, and multiple sessions.

## Official references

Behaviors in this article are cross-checked against the **MySQL 9.7 Reference Manual**:

1. [Restrictions on Stored Programs](https://dev.mysql.com/doc/refman/9.7/en/stored-program-restrictions.html): transaction-control restrictions in functions/triggers and limits on procedures called from functions/triggers.
2. [START TRANSACTION, COMMIT, and ROLLBACK Statements](https://dev.mysql.com/doc/refman/9.7/en/commit.html): session transactions, autocommit, `START TRANSACTION`, `COMMIT`, `ROLLBACK`, and starting a transaction committing a pending one.
3. [Statements That Cause an Implicit Commit](https://dev.mysql.com/doc/refman/9.7/en/implicit-commit.html): DDL, `TRUNCATE`, user privileges, and implicit-commit statements.
4. [Trigger Syntax and Examples](https://dev.mysql.com/doc/refman/9.7/en/trigger-syntax.html): transaction restrictions in triggers, `ROLLBACK TO SAVEPOINT`, and trigger error handling.
5. [SAVEPOINT, ROLLBACK TO SAVEPOINT, and RELEASE SAVEPOINT](https://dev.mysql.com/doc/refman/9.7/en/savepoint.html): partial rollback, row locks, and savepoint levels in functions/triggers.
6. [DECLARE ... HANDLER Statement](https://dev.mysql.com/doc/refman/9.7/en/declare-handler.html): `EXIT`, `CONTINUE`, `SQLSTATE`, `SQLEXCEPTION`, `NOT FOUND`, and `UNDO` not being supported.
7. [Performance Schema Transaction Tables](https://dev.mysql.com/doc/refman/9.7/en/performance-schema-transaction-tables.html): relationship between transaction events and stored procedure/function/trigger events.
8. [InnoDB autocommit, Commit, and Rollback](https://dev.mysql.com/doc/refman/9.7/en/innodb-autocommit-commit-rollback.html): autocommit and multi-statement transactions in InnoDB.
9. [CREATE PROCEDURE and CREATE FUNCTION Statements](https://dev.mysql.com/doc/refman/9.7/en/create-procedure.html): differences in transaction statements between procedures and functions.
