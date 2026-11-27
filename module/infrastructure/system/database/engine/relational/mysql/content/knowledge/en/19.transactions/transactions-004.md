# SAVEPOINT, ROLLBACK TO SAVEPOINT, and RELEASE SAVEPOINT

A transaction can consist of multiple business steps. Sometimes the core steps are valid, but an optional step or part of the processing needs to be canceled. `SAVEPOINT` marks a position inside a transaction; `ROLLBACK TO SAVEPOINT` undoes changes made after that position while keeping the transaction open; `RELEASE SAVEPOINT` removes the marker when it is no longer needed.

In MySQL with InnoDB, savepoints help build workflows capable of partial recovery, such as creating an order and reserving inventory while skipping a failed promotion-application step. Savepoints do not create child transactions, do not commit independently, and do not replace transaction management in the application.

In the `DATABASE_MYSQL` module, this technique relates directly to transactions, rollback, error handling, locking, and data consistency. This lesson focuses on MySQL 8.x and InnoDB tables.

## Objectives

After this lesson, you will be able to:

- Explain the role of a savepoint inside an open transaction.
- Create markers using `SAVEPOINT`.
- Partially undo work using `ROLLBACK TO SAVEPOINT` without canceling the entire transaction.
- Remove markers using `RELEASE SAVEPOINT`.
- Manage multiple savepoints, duplicate names, and rollback ordering.
- Distinguish partial rollback from full-transaction `ROLLBACK` and `COMMIT`.
- Recognize cases where savepoints become invalid, such as commit or implicit commit.
- Understand savepoint limitations regarding non-transactional engines, auto-increment, locks, and deadlocks.
- Design safe error-handling flows in applications.

## 1. Transactions and Savepoints

A transaction groups multiple statements into a single unit of work. With InnoDB, a transaction can end with `COMMIT` to confirm changes or `ROLLBACK` to undo uncommitted changes.

A savepoint creates a marker inside a transaction. After creating it, the application can continue executing SQL. If part of the work needs to be canceled, `ROLLBACK TO SAVEPOINT` restores transactional data to the state at that marker; operations before the marker remain in the transaction.

```text
START TRANSACTION
       |
       v
    SQL step 1
       |
       v
    SAVEPOINT s1
       |
       v
    SQL steps 2, 3
       |
       +---- error / invalid optional part ------+
       |                                         |
       v                                         v
    SQL step 4                             ROLLBACK TO s1
       |                                         |
       +--------------------+--------------------+
                            |
                            v
                     COMMIT or ROLLBACK
```

Key point: `ROLLBACK TO SAVEPOINT` does not end the transaction. After a partial rollback, the application must still decide to continue processing and `COMMIT`, or cancel everything with `ROLLBACK`.

## 2. Prerequisites for Using Savepoints

A savepoint must reside inside an active transaction. Under the default configuration `autocommit = 1`, each standalone statement is typically committed automatically; open a transaction explicitly before creating a savepoint:

```sql
START TRANSACTION;

UPDATE account
SET balance = balance - 100.00
WHERE account_id = 10;

SAVEPOINT after_debit;

-- Subsequent statements belong to the same transaction.

ROLLBACK TO SAVEPOINT after_debit;
ROLLBACK;
```

The example above only illustrates syntax and transaction scope. `ROLLBACK TO` undoes the part after the savepoint; the final `ROLLBACK` cancels the entire transaction, including the update before the savepoint.

Check autocommit mode:

```sql
SELECT @@SESSION.autocommit;
```

You can use `SET autocommit = 0` so each session starts a transaction implicitly when performing a transactional operation, though for workflows needing clear boundaries, `START TRANSACTION` and `COMMIT`/`ROLLBACK` are usually easier to read. Do not confuse setting `autocommit = 0` with a transaction already being committed.

## 3. SAVEPOINT: Creating a Marker

Syntax:

```sql
SAVEPOINT savepoint_name;
```

Example:

```sql
START TRANSACTION;

UPDATE inventory
SET reserved_qty = reserved_qty + 2
WHERE sku = 'KB-01';

SAVEPOINT after_reservation;

INSERT INTO order_note (order_id, note_text)
VALUES (5001, 'Customer requested morning delivery');

-- Continue other steps...

COMMIT;
```

The savepoint `after_reservation` marks the state after updating the reserved stock quantity. If subsequent operations need to be canceled, the application can revert to this marker while keeping the prior inventory update.

Savepoint names are chosen by the application. Name them to reflect business boundaries, such as `before_optional_discount`, `after_stock_reservation`, or `before_import_row_20`. Avoid overly generic names like `s1` or `temp` in multi-step flows.

## 4. ROLLBACK TO SAVEPOINT: Partial Undo

Syntax:

```sql
ROLLBACK TO SAVEPOINT savepoint_name;
```

This command undoes transactional changes made after the specified savepoint. Changes before the savepoint remain inside the transaction and can be committed or rolled back later.

Simple example:

```sql
START TRANSACTION;

UPDATE account
SET balance = balance - 100.00
WHERE account_id = 10;

SAVEPOINT after_first_update;

UPDATE account
SET balance = balance + 100.00
WHERE account_id = 20;

ROLLBACK TO SAVEPOINT after_first_update;

-- Update to account 20 has been undone.
-- Update to account 10 still remains in the transaction.

COMMIT;
```

After `COMMIT`, only the update to account 10 is saved. This example intentionally creates an unbalanced state to illustrate rollback scope; do not use this pattern for real money transfers. For money transfers, if one leg fails, you usually must roll back the entire transaction to avoid debiting without crediting.

### 4.1. A Savepoint Is Retained After ROLLBACK TO

`ROLLBACK TO SAVEPOINT` does not delete the specified savepoint. You can continue operations and roll back to the same marker again:

```sql
START TRANSACTION;

SAVEPOINT checkpoint_a;

INSERT INTO import_log (message) VALUES ('attempt 1');
ROLLBACK TO SAVEPOINT checkpoint_a;

INSERT INTO import_log (message) VALUES ('attempt 2');
ROLLBACK TO SAVEPOINT checkpoint_a;

-- Both INSERTs after checkpoint_a have been undone.
COMMIT;
```

The transaction remains open after each rollback to the marker. If you want to discard that marker, call `RELEASE SAVEPOINT`.

### 4.2. Newer Savepoints Are Discarded

If multiple markers exist in sequence:

```sql
START TRANSACTION;
SAVEPOINT s1;
SAVEPOINT s2;
SAVEPOINT s3;

ROLLBACK TO SAVEPOINT s1;
```

When rolling back to `s1`, changes after `s1` are undone and savepoints created after `s1` (`s2`, `s3`) are removed. `s1` remains valid. You cannot subsequently roll back to `s2` or `s3` after this operation.

## 5. RELEASE SAVEPOINT: Removing a Marker

Syntax:

```sql
RELEASE SAVEPOINT savepoint_name;
```

`RELEASE SAVEPOINT` removes a marker from the transaction. It does not undo statements executed after the marker, does not commit, and does not roll back data.

```sql
START TRANSACTION;

UPDATE inventory
SET reserved_qty = reserved_qty + 1
WHERE sku = 'KB-01';

SAVEPOINT before_optional_note;

INSERT INTO order_note (order_id, note_text)
VALUES (5001, 'Deliver outside business hours');

RELEASE SAVEPOINT before_optional_note;

COMMIT;
```

Here, the note is still saved because `RELEASE` only removes the marker. Only calling `ROLLBACK TO SAVEPOINT` before releasing would undo the note insert.

Any remaining savepoints are automatically released when the transaction ends with `COMMIT` or `ROLLBACK`. Therefore, `RELEASE` is usually useful when the processing flow continues for a long time and no longer needs the marker; it is not mandatory to release every savepoint before committing.

## 6. Multiple Savepoints and Reused Names

Multiple savepoints can be created within the same transaction:

```sql
START TRANSACTION;

UPDATE inventory
SET reserved_qty = reserved_qty + 1
WHERE sku = 'KB-01';
SAVEPOINT stock_reserved;

INSERT INTO orders (order_id, sku, quantity, order_status)
VALUES (5001, 'KB-01', 1, 'PENDING');
SAVEPOINT order_created;

INSERT INTO order_note (order_id, note_text)
VALUES (5001, 'Optional note');
SAVEPOINT note_added;

ROLLBACK TO SAVEPOINT order_created;

-- note_added has been removed; order_created still remains.
-- The note is undone; the inventory update and order creation remain.

COMMIT;
```

If you create a new savepoint with the same name as an existing savepoint, the old savepoint is replaced by the new marker:

```sql
START TRANSACTION;

SAVEPOINT step_marker;
UPDATE account SET balance = balance - 10 WHERE account_id = 10;

SAVEPOINT step_marker;
-- The old step_marker is replaced by the new marker at the current position.

ROLLBACK TO SAVEPOINT step_marker;
-- Only undoes changes after the second SAVEPOINT.

ROLLBACK;
```

Reusing names can cause confusion when reading logs or maintaining code. In complex flows, use distinct names for each stage.

## 7. Business Example: Orders, Inventory, and Optional Promotion Step

Suppose an ordering workflow has two core parts: creating the order and reserving stock. Applying reward points/promotions is an additional step; if this step is invalid, the system can still proceed with the order according to business policy.

Illustrative schema:

```sql
CREATE TABLE inventory (
    sku VARCHAR(30) NOT NULL,
    available_qty INT NOT NULL,
    reserved_qty INT NOT NULL DEFAULT 0,
    PRIMARY KEY (sku),
    CONSTRAINT chk_inventory_qty
        CHECK (available_qty >= 0 AND reserved_qty >= 0)
) ENGINE=InnoDB;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sku VARCHAR(30) NOT NULL,
    quantity INT NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_sku (sku),
    CONSTRAINT chk_order_quantity CHECK (quantity > 0)
) ENGINE=InnoDB;

CREATE TABLE order_promotion (
    order_id BIGINT UNSIGNED NOT NULL,
    promotion_code VARCHAR(30) NOT NULL,
    discount_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, promotion_code),
    CONSTRAINT chk_promotion_discount CHECK (discount_amount >= 0)
) ENGINE=InnoDB;
```

The schema focuses solely on illustrating savepoints; a real system needs foreign keys, stock validation, pricing rules, and appropriate write permissions. The tables use InnoDB so changes can be rolled back. `CHECK` constraints are enforced by MySQL from version 8.0.16 onward.

### 7.1. Scenario Where the Optional Step Succeeds

```sql
START TRANSACTION;

INSERT INTO orders (sku, quantity, order_status)
VALUES ('KB-01', 2, 'PENDING');

SET @new_order_id = LAST_INSERT_ID();

UPDATE inventory
SET available_qty = available_qty - 2,
    reserved_qty = reserved_qty + 2
WHERE sku = 'KB-01'
  AND available_qty >= 2;

-- Application must check ROW_COUNT() = 1.
-- If not exactly one row updated, ROLLBACK the entire transaction.

SAVEPOINT before_optional_promotion;

INSERT INTO order_promotion
    (order_id, promotion_code, discount_amount)
VALUES
    (@new_order_id, 'WELCOME10', 10.00);

RELEASE SAVEPOINT before_optional_promotion;

COMMIT;
```

When all steps succeed, the order, stock reservation update, and promotion are committed together. If the promotion does not need to be rolled back, the savepoint can be released or left to disappear automatically at commit.

### 7.2. Scenario Where the Optional Step Fails

Keep the order creation and stock reservation steps, while canceling the promotion-application step when needed:

```sql
ROLLBACK TO SAVEPOINT before_optional_promotion;

-- Order and inventory updates before the savepoint remain.
-- No promotion changes after the savepoint remain.

COMMIT;
```

This snippet assumes the application already created the savepoint and executed the promotion operations within the same transaction. If the promotion step raises an SQL error, the application layer must catch the error, verify the transaction is still active, and roll back to the savepoint when appropriate. Do not run the rollback snippet as an independent statement after the transaction has already ended.

### 7.3. If a Core Step Fails

If stock cannot be reserved or the order cannot be created, do not commit a partial core state:

```sql
ROLLBACK;
```

A full-transaction `ROLLBACK` discards both order creation and inventory changes. The rule for choosing partial versus full rollback must be based on business boundaries, not merely on which statement threw an error.

## 8. Savepoints in Multi-Step Processing or Batch Imports

Savepoints can help process individual records in a batch while preserving earlier valid records within the same transaction. Illustrative example:

```sql
START TRANSACTION;

SAVEPOINT before_row_1;
INSERT INTO staging_result (source_id, normalized_value)
VALUES (1, 'A');

SAVEPOINT before_row_2;
INSERT INTO staging_result (source_id, normalized_value)
VALUES (2, 'B');

-- If the 3rd record is invalid:
SAVEPOINT before_row_3;
INSERT INTO staging_result (source_id, normalized_value)
VALUES (3, 'INVALID');

-- After the application detects a business error:
ROLLBACK TO SAVEPOINT before_row_3;

-- Can continue processing another record.
SAVEPOINT before_row_4;
INSERT INTO staging_result (source_id, normalized_value)
VALUES (4, 'D');

COMMIT;
```

Rows 1, 2, and 4 are committed; row 3 is excluded if rolled back to the right savepoint. This is a sequential flow example; a real application must manage savepoint names, SQL errors, connection state, and decide which batches require a full rollback.

### 8.1. Choosing Transaction and Savepoint Boundaries

You do not need to create a savepoint for every SQL statement. Place markers at meaningful boundaries:

- After core data has been validated.
- Before an optional step that may be skipped.
- Before a group of operations that can be retried independently.
- Before a record in a batch when policy allows keeping other records.

Too many savepoints make code hard to understand and increase management overhead. For very large batches, splitting into smaller transactions may be better than one long transaction holding thousands of savepoints; the decision depends on atomicity and recovery requirements.

## 9. Savepoints Are Not Nested Transactions

MySQL does not create nested transactions by calling `START TRANSACTION` inside an active transaction. Calling `START TRANSACTION` while a transaction is already open ends the current transaction with an implicit commit before starting the new transaction.

A savepoint is only a rollback marker inside the same transaction:

| Action | Savepoint | True Nested Transaction |
|---|---|---|
| Can partially roll back | Yes | Yes, depending on the DBMS |
| Can commit child part independently | No | Possible in systems supporting nested transactions |
| Part before marker still waits on outer transaction | Yes | Depends on the model |
| Full `COMMIT` | Commits all remaining changes of the transaction | Depends on the DBMS |

Example:

```sql
START TRANSACTION;
INSERT INTO audit_event (event_name) VALUES ('outer start');

SAVEPOINT inner_work;
INSERT INTO audit_event (event_name) VALUES ('optional step');
ROLLBACK TO SAVEPOINT inner_work;

-- No independent COMMIT for inner_work.
COMMIT;
```

Only `outer start` is saved. Data after the savepoint is undone; a savepoint cannot independently commit its own changes.

## 10. Savepoints and Transaction State

| Command | Data Effect | Transaction After Command | Savepoint |
|---|---|---|---|
| `SAVEPOINT s` | No data change | Remains open | Creates or replaces `s` |
| `ROLLBACK TO SAVEPOINT s` | Undoes changes after `s` | Remains open | `s` remains; newer markers are deleted |
| `RELEASE SAVEPOINT s` | Does not undo changes | Remains open | Deletes `s` |
| `COMMIT` | Confirms all remaining changes | Ends | All markers are deleted |
| `ROLLBACK` | Undoes entire transaction | Ends | All markers are deleted |

If you reference a savepoint that no longer exists or has an incorrect name, MySQL reports an error. Common causes include having already committed/rolled back the transaction, rolling back to an older marker that removed newer ones, or having already released that marker.

## 11. Impact of Implicit Commit and DDL Statements

Savepoints only exist within the current transaction. When the transaction ends, savepoints become invalid. Certain statements in MySQL trigger an implicit commit; many DDL statements such as `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`, and other administrative operations belong to this group.

Example where you should not expect rollback to a savepoint after DDL:

```sql
START TRANSACTION;
UPDATE account SET balance = balance - 10 WHERE account_id = 10;
SAVEPOINT before_ddl;

CREATE TABLE temp_work (id INT PRIMARY KEY);

-- DDL may have implicitly committed the prior transaction.
-- Cannot rely on before_ddl to roll back the old update.
```

Some exceptions related to temporary tables have their own implicit commit rules; do not generalize that every DDL statement behaves identically. Check the documentation for your MySQL version before mixing DDL with business transactions.

Operations such as `START TRANSACTION` while an old transaction is open, or changing `autocommit` from 0 to 1, can also end the current transaction. Avoid executing DDL and implicit-commit operations in the middle of flows relying on savepoints for rollback.

## 12. Storage Engines and Non-Rollbackable Changes

Savepoints are only meaningful for changes in a storage engine that supports transactions/savepoints. InnoDB is the appropriate default choice for flows requiring atomicity.

If a transaction updates both an InnoDB table and a table using a non-transactional engine, `ROLLBACK TO SAVEPOINT` or `ROLLBACK` cannot guarantee undoing changes in the non-transactional table. When designing business flows needing partial rollback, all participating tables should use a compatible transactional engine.

### 12.1. AUTO_INCREMENT May Have Gaps After Rollback

An allocated `AUTO_INCREMENT` value is not necessarily reused after rollback:

```sql
START TRANSACTION;

INSERT INTO orders (sku, quantity, order_status)
VALUES ('KB-01', 1, 'PENDING');

ROLLBACK;
```

The insert allocated an ID, then the transaction rolled back. That ID may not appear in the table, and a subsequent insert may receive a higher ID. Do not treat strictly sequential IDs as proof of record count or as a savepoint bug.

## 13. Locking, Isolation, and Concurrency Errors

Savepoints do not create a new transaction and do not release all locks as if the transaction had ended. With InnoDB, rolling back to a savepoint can undo data, but row locks acquired in memory after the savepoint are not necessarily released. Therefore, do not use savepoints expecting to automatically yield all locks to other transactions.

The transaction retains its isolation scope and snapshot according to the rules of the current isolation level. `ROLLBACK TO SAVEPOINT` does not start a new transaction and does not automatically create a new snapshot.

### 13.1. Lock Wait Timeout and Deadlock

When a lock wait timeout occurs, InnoDB by default usually rolls back the timed-out statement; if `innodb_rollback_on_timeout` is enabled, it can roll back the entire transaction. The application needs to know the configuration and transaction state before deciding whether to roll back to a savepoint or roll back everything.

When InnoDB detects a deadlock, it selects a victim transaction and rolls back that entire transaction. A savepoint does not preserve work before the marker when the transaction is rolled back due to a deadlock. The application usually must retry the entire unit of work in a new transaction.

Check the timeout rollback configuration:

```sql
SELECT @@GLOBAL.innodb_rollback_on_timeout;
```

Do not arbitrarily retry a statement inside a transaction without verifying that the transaction is still valid and what state prior operations are in.

## 14. Error-Handling Pattern in Applications

Illustrative SQL scripts are often written sequentially, whereas an application must branch on success/failure based on each statement's result. A general handling pattern:

```text
begin transaction
execute required steps
if a required step fails:
    rollback entire transaction
else:
    create savepoint before_optional_step
    execute optional steps
    if optional step fails and policy allows skipping it:
        rollback to savepoint before_optional_step
        continue with valid core work
    else:
        release savepoint when no longer needed
    commit transaction
```

Implementation principles:

- Use the same connection for the entire transaction and all savepoints.
- Do not return the connection to the pool while the transaction has not been committed/rolled back.
- If an error causes the server to roll back the entire transaction, do not continue using an old savepoint.
- If rolling back to a savepoint succeeds, you must still commit or roll back the outer transaction.
- Ensure every table requiring recovery uses a transactional engine.
- Keep transactions short to reduce lock hold duration.
- Do not perform external side effects (sending emails, calling payment APIs) assuming SQL rollback will undo them.

With JDBC, `Connection.setSavepoint()`, `Connection.rollback(savepoint)`, and `Connection.releaseSavepoint(savepoint)` are the corresponding APIs. Disable auto-commit or start a transaction according to appropriate configuration before calling them; use the same connection until the transaction ends.

Condensed Java example:

```java
connection.setAutoCommit(false);

try {
    createOrder(connection);
    reserveInventory(connection);

    Savepoint optionalStep = connection.setSavepoint("before_optional_promotion");
    try {
        applyPromotion(connection);
        connection.releaseSavepoint(optionalStep);
    } catch (SQLException optionalFailure) {
        connection.rollback(optionalStep);
        // Only continue if policy allows skipping the promotion.
    }

    connection.commit();
} catch (SQLException failure) {
    try {
        connection.rollback();
    } catch (SQLException rollbackFailure) {
        failure.addSuppressed(rollbackFailure);
        // Mark connection unsafe for reuse and evict from pool.
    }
    throw failure;
}
```

This is an illustrative skeleton and does not cover all connection-management policies. After committing or rolling back successfully, restore `autoCommit` according to the connection pool's contract. If rollback fails, do not return that connection to the pool as a clean connection; close or evict it using the pool's mechanism. Do not place `setAutoCommit(true)` unconditionally in `finally`, because enabling auto-commit while a transaction is still active can commit the transaction. If `commit()` encounters a connection error, the commit outcome may be indeterminate to the client; an idempotency mechanism or reconciliation by business ID is needed before retrying.

## 15. Common Errors

| Symptom | Cause | How to Handle |
|---|---|---|
| `ROLLBACK TO SAVEPOINT` reports non-existent | Not created, already released, transaction ended, or newer marker deleted | Check flow and savepoint ordering |
| Rolled back to marker but transaction has not ended | This is the expected behavior | Continue and then `COMMIT` or full `ROLLBACK` |
| Data after savepoint still remains | Used `RELEASE` instead of `ROLLBACK TO`, or operation used non-transactional engine | Verify engine and proper rollback command |
| Data before savepoint is lost | Application called full-transaction `ROLLBACK` or encountered a deadlock | Distinguish partial rollback from full rollback |
| Older savepoint disappears after rollback | Rolling back to an earlier marker removes markers created after it | Recreate needed markers after rollback |
| Savepoint disappears after DDL | Statement triggered an implicit commit | Separate DDL from business transactions |
| Assuming RELEASE undoes data | Confusing marker removal with rollback | `RELEASE` only deletes the savepoint; use `ROLLBACK TO` to undo |
| Locks remain after partial rollback | InnoDB transaction stays open and locks may remain held | End transactions early when possible |
| AUTO_INCREMENT IDs have gaps | Allocated values are not reused after rollback | Do not rely on contiguous IDs |
| Retrying savepoint after deadlock fails | InnoDB rolled back the entire transaction | Start a new transaction and retry the full unit of work |

## 16. Process for Choosing Partial vs. Full Rollback

Before placing a savepoint, define business boundaries:

1. Which steps are mandatory for the transaction to be considered valid?
2. Which steps are optional and can be skipped without corrupting core state?
3. If an optional step fails, is the data before the savepoint still consistent?
4. Do all participating tables use InnoDB or a compatible transactional engine?
5. Are there any DDL or implicit-commit statements between the savepoint and the rollback?
6. Is the error a statement error, a lock timeout, or a deadlock that rolled back the entire transaction?
7. Are there external side effects requiring compensation or handling via an outbox?
8. After partial rollback, can the transaction commit safely?

If you cannot prove the remaining state is valid, roll back the entire transaction. Savepoints are only useful when partial recovery boundaries are clearly defined.

## 17. Practice Exercises

Perform in a separate lab schema with InnoDB tables:

1. Open a transaction, update a row, create a savepoint, update another row, and roll back to the savepoint; verify only the first update remains in the transaction.
2. After `ROLLBACK TO`, perform another update and roll back to the same savepoint again; confirm the savepoint is still valid.
3. Create `s1`, `s2`, `s3`, roll back to `s1`; attempt to roll back to `s2` and note the error because newer markers were removed.
4. Create two savepoints with the same name at two points in time; verify the old name is replaced and rollback only reverts to the new position.
5. Use `RELEASE SAVEPOINT`, then attempt to roll back to the released name; confirm the marker no longer exists.
6. Compare `ROLLBACK TO SAVEPOINT` with full-transaction `ROLLBACK` and `COMMIT`.
7. Create a transaction with a savepoint and then run DDL; observe the implicit commit and verify the savepoint can no longer be used.
8. Insert a row with `AUTO_INCREMENT` and roll back; insert again and observe that IDs can have gaps.
9. Create one transactional table and one non-transactional table in the lab if engines are supported; compare rollback behavior and note limitations.
10. Use `SHOW ENGINE INNODB STATUS` to observe a deadlock in a test environment; verify a deadlock can roll back the entire transaction rather than rolling back to a savepoint.
11. Write a flow for order creation/stock reservation/optional promotion step; clearly define partial rollback cases and full rollback cases.
12. Write a JDBC program using `Savepoint`; verify using the same connection, handling exceptions, and ending the transaction.

You have completed the lesson when you can accurately predict which changes remain after each command, know when savepoints become invalid, and design recovery branches without leaving incomplete business states.

## 18. Principles to Remember

- `SAVEPOINT name` creates a marker inside an open transaction.
- `ROLLBACK TO SAVEPOINT name` undoes changes after the marker without ending the transaction.
- The savepoint rolled back to remains valid; savepoints created after it are discarded.
- `RELEASE SAVEPOINT name` only deletes the marker; it neither commits nor undoes data.
- `COMMIT` and full-transaction `ROLLBACK` delete all savepoints.
- Reusing a savepoint name replaces the old marker with the new one.
- Savepoints are not nested transactions and cannot independently commit a sub-part.
- Starting a new transaction or executing an implicit-commit statement can invalidate savepoints.
- Only transactional data can be recovered via transactions/savepoints; prefer InnoDB for all participating tables.
- Rollback does not guarantee reusing allocated `AUTO_INCREMENT` values.
- Rolling back to a savepoint does not equate to releasing all row locks; the transaction stays open.
- InnoDB deadlocks can roll back the entire transaction; applications must retry the unit of work in a new transaction.
- Only perform partial rollback when remaining steps still form a valid business state; otherwise, roll back everything.
