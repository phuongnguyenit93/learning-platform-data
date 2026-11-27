# Restrictions on Modifying the Triggering Table and Recursion Risks

Triggers let MySQL automatically execute an SQL block when a row is INSERTed, UPDATEd, or DELETEd. This mechanism is useful for validating data, normalizing values of a row about to be written, and storing audits in another table. However, triggers have an important restriction: **a trigger cannot modify a table that is already being used by the statement that fired it**. If a trigger attempts directly or through a routine to write back to that same table, MySQL may reject the statement with error 1442.

This limit is commonly called the mutating-table restriction. It prevents a statement modifying a table from invoking a trigger that modifies the same table in a nested execution flow. Because triggers can also touch other tables and fire those tables' triggers, an uncontrolled design can form circular dependency chains that are hard to predict and diagnose.

In the **DATABASE_MYSQL** module, triggers should be used for local, well-scoped tasks. This lesson explains which tables may be modified, how to use NEW and OLD, why error 1442 occurs, how to identify indirect trigger chains, and safe alternative design patterns.

## 1. Which Statements Fire Triggers?

MySQL supports row-level triggers (FOR EACH ROW). A trigger is attached to one table, one timing, and one event:

- BEFORE INSERT: runs before a row is inserted.
- AFTER INSERT: runs after a row is inserted.
- BEFORE UPDATE: runs before a row is updated.
- AFTER UPDATE: runs after a row is updated.
- BEFORE DELETE: runs before a row is deleted.
- AFTER DELETE: runs after a row is deleted.

MySQL has no statement-level triggers. If an UPDATE statement affects 1,000 rows, the corresponding trigger can run 1,000 times, once per row.

Example:

```sql
UPDATE orders
SET status = 'EXPIRED'
WHERE expires_at < CURRENT_TIMESTAMP;
```

If the statement affects 300 rows, the AFTER UPDATE trigger on orders is invoked for each updated row. The trigger does not run a single time for the entire statement.

This matters for the mutating-table restriction: throughout the time the statement processes rows and fires triggers, the source table remains in use by that same statement.

## 2. The Mutating-Table Restriction and Error 1442

MySQL does not allow a trigger to modify a table already being used by the statement that fired the trigger. For example, an UPDATE on accounts fires a trigger, and the trigger executes an UPDATE on accounts itself. The outer statement is already using accounts, so the nested write operation is rejected.

Example table:

```sql
CREATE TABLE accounts (
    account_id BIGINT UNSIGNED NOT NULL,
    balance DECIMAL(14, 2) NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (account_id)
) ENGINE = InnoDB;
```

Incorrect trigger:

```sql
DELIMITER //

CREATE TRIGGER trg_accounts_after_update
AFTER UPDATE ON accounts
FOR EACH ROW
BEGIN
    UPDATE accounts
    SET updated_at = CURRENT_TIMESTAMP
    WHERE account_id = NEW.account_id;
END//

DELIMITER ;
```

When running:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 42;
```

MySQL rejects the nested write operation and returns a common error:

```text
ERROR 1442 (HY000):
Can't update table 'accounts' in stored function/trigger
because it is already used by statement which invoked
this stored function/trigger.
```

The exact message may vary slightly by version and context, but error code 1442 indicates that a stored function/trigger attempted to modify a table already used by the statement that invoked it.

### 2.1. Why Can't You UPDATE the Source Table?

The outer statement controls reading, locking, and modifying rows in the table. If the trigger emitted another write statement against the same table, MySQL would have to coordinate two nested modification streams on the same object within a single execution. This rule prevents such recursive updates.

You cannot work around this by:

- Changing the table alias.
- Moving the UPDATE into a stored procedure called from the trigger.
- Moving the UPDATE into a stored function and calling that function.
- Splitting the UPDATE into another SQL statement still executed inside the trigger.
- Using dynamic SQL to obscure the table name.

What is checked is the actual underlying table and execution path, not the alias name or whether the statement is written directly in the trigger or hidden inside a routine.

### 2.2. Scope of the Restriction

Distinguish two points:

1. A trigger can read OLD and NEW to inspect values of the row being processed.
2. A trigger cannot use a write statement to modify a table already used by the triggering statement.

The core restriction is modifying a table already in use by the outer statement. Do not misinterpret error 1442 as meaning a trigger cannot reference any column or value of the source row; OLD and NEW are the exact interface MySQL provides for that purpose.

If you need to read other rows of the source table, examine the query context and data semantics very carefully. The fact that a SELECT may run does not make writing to the same table valid, nor does it guarantee the query observes intermediate states the way the application expects.

## 3. Using NEW and OLD to Update the Current Row

For BEFORE INSERT or BEFORE UPDATE triggers, MySQL allows assigning values to columns of the row about to be written via NEW.column_name.

This is the proper way to normalize data on the current row itself. No second UPDATE on the source table is needed.

Example table:

```sql
CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;
```

Valid trigger:

```sql
DELIMITER //

CREATE TRIGGER trg_products_before_update
BEFORE UPDATE ON products
FOR EACH ROW
BEGIN
    IF NEW.price < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Price cannot be negative';
    END IF;

    SET NEW.updated_at = CURRENT_TIMESTAMP;
END//

DELIMITER ;
```

When the application runs:

```sql
UPDATE products
SET price = 125000
WHERE product_id = 10;
```

The trigger modifies NEW.updated_at on the row being updated. There is no second UPDATE statement on products, so it does not violate the mutating-table restriction.

### 3.1. NEW and OLD by Trigger Type

| Trigger | NEW | OLD | Can Assign NEW? |
|---|---|---|---|
| BEFORE INSERT | Row values about to be inserted | Not available | Yes |
| AFTER INSERT | Row values just inserted | Not available | No |
| BEFORE UPDATE | New values | Old values | Yes |
| AFTER UPDATE | New values | Old values | No |
| BEFORE DELETE | Not available | Values about to be deleted | No |
| AFTER DELETE | Not available | Deleted values | No |

OLD is read-only. NEW can be assigned in BEFORE INSERT and BEFORE UPDATE; in AFTER triggers, the row has already been written, so NEW cannot be changed.

Example checking status changes:

```sql
DELIMITER //

CREATE TRIGGER trg_orders_before_update
BEFORE UPDATE ON orders
FOR EACH ROW
BEGIN
    IF NOT (OLD.status <=> NEW.status) THEN
        SET NEW.updated_at = CURRENT_TIMESTAMP;
    END IF;
END//

DELIMITER ;
```

The <=> operator is a NULL-safe equality comparison. It returns TRUE when both sides are NULL, making old-vs-new value comparison clearer than = when NULLs are possible.

### 3.2. BEFORE and AFTER Have Distinct Purposes

Use BEFORE when you need to:

- Validate values about to be written.
- Normalize or assign values to NEW.
- Reject data with SIGNAL.

Use AFTER when you need to:

- Write audits to a separate table.
- Record an event after the source row has been written.
- Update another summary table if design and transaction semantics allow.

Do not use an AFTER trigger to emit an UPDATE back onto the table that just changed. If you need to update a column on the same row, consider a BEFORE trigger and assign NEW.column.

## 4. Proper Audit Example: Writing to Another Table

A common requirement is recording order status change history. A trigger can write OLD and NEW to a separate audit table.

Create source table:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;
```

Create audit table:

```sql
CREATE TABLE order_status_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    old_status VARCHAR(20) NOT NULL,
    new_status VARCHAR(20) NOT NULL,
    changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (audit_id),
    KEY idx_audit_order_changed (order_id, changed_at)
) ENGINE = InnoDB;
```

Valid trigger:

```sql
DELIMITER //

CREATE TRIGGER trg_orders_after_status_update
AFTER UPDATE ON orders
FOR EACH ROW
BEGIN
    IF NOT (OLD.status <=> NEW.status) THEN
        INSERT INTO order_status_audit (
            order_id,
            old_status,
            new_status
        )
        VALUES (
            NEW.order_id,
            OLD.status,
            NEW.status
        );
    END IF;
END//

DELIMITER ;
```

The trigger only INSERTs into order_status_audit and never UPDATEs orders. Thus, it does not try to modify the source table already in use by the outer statement.

Verify:

```sql
UPDATE orders
SET status = 'PAID',
    updated_at = CURRENT_TIMESTAMP
WHERE order_id = 9001;

SELECT *
FROM order_status_audit
WHERE order_id = 9001
ORDER BY audit_id;
```

With InnoDB, writing the source table and the audit table participate together in the triggering statement's transaction. If the trigger errors, the statement fails and transactional changes within the statement roll back. This is an advantage when business updates and audits must stay atomic.

The audit table must be designed so it does not trigger a path back to orders. If the audit table has other triggers, inspect the entire impact chain.

## 5. Direct and Indirect Recursion Risks

A trigger should not be treated as a workflow engine free to call itself back. Recursion risk arises when a trigger modifies another table, that operation fires a downstream trigger, and the chain loops back to the originating table or active flow.

Example dependency:

- UPDATE orders
- AFTER UPDATE trigger on orders
- INSERT order_audit
- AFTER INSERT trigger on order_audit
- UPDATE orders

The first trigger writes to order_audit. The trigger on order_audit then attempts to update orders. This is a circular design. When the execution path attempts to modify a table still used by the original statement, MySQL may reject it with error 1442. Even if a trigger chain does not immediately hit that error, circular dependencies make behavior hard to trace and prone to unexpected repeated writes.

### 5.1. Multi-Table Trigger Chains

Suppose:

- A trigger on orders writes to order_audit.
- A trigger on order_audit updates customer_summary.
- A trigger on customer_summary updates orders again.

This is an A → B → C → A chain. When designing, treat every trigger action and any routine it calls as part of a dependency graph. A cycle in the graph can lead back to modifying a table used by the outer statement or create an uncontrollable execution chain.

Do not inspect only statements in the first trigger. Trace all of:

- Triggers on tables being written to.
- Stored procedures called from triggers.
- Stored functions used in expressions.
- Triggers on audit or summary tables.
- Statements emitted from those routines.

### 5.2. Indirect Triggers via Stored Procedures/Functions

Moving an UPDATE into a procedure does not remove the restriction.

Example call path:

```sql
-- Trigger on orders calls this routine.
CALL refresh_order_row(NEW.order_id);
```

If refresh_order_row executes UPDATE orders, it is still trying to modify the source table while the statement on orders has fired the trigger. Moving the UPDATE into a routine only lengthens the call path; it does not alter MySQL's rules.

Similarly, if a stored function is called from a statement or trigger and attempts to modify a table used by that statement, the corresponding error can still occur.

## 6. Row-by-Row Triggers and Amplification Effects

Because MySQL triggers run FOR EACH ROW, a large statement can fire them many times.

Example:

```sql
UPDATE order_items
SET status = 'ARCHIVED'
WHERE created_at < '2024-01-01';
```

If the statement affects 500,000 rows, the AFTER UPDATE trigger on order_items may execute 500,000 times. If each trigger invocation writes to multiple tables, secondary operations multiply with the row count.

Risks:

- Statement duration increases sharply.
- Many index writes and extra I/O.
- Locks on secondary tables held longer within the transaction.
- Higher deadlock risk when transactions write to multiple tables in different orders.
- Audit or summary tables grow rapidly.
- Multi-layered trigger chains make latency unpredictable.

Triggers have no statement-level mechanism to batch processing once for the whole rowset. When batch aggregation is required, consider processing in a stored procedure or separate job using set-based SQL.

### 6.1. Do Not Use Triggers to Replace Batch Processing

For instance, instead of updating a summary row per row via triggers, you can execute:

```sql
UPDATE customer_summary AS s
JOIN (
    SELECT
        customer_id,
        SUM(total_amount) AS total_amount
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id
) AS x
    ON x.customer_id = s.customer_id
SET s.paid_total = x.total_amount;
```

A set-based statement can recompute many customers in one pass. Choose a refresh approach suited to data size, update frequency, and required freshness.

## 7. Other Important Limitations When Designing Triggers

Beyond the mutating-table restriction, triggers have several limitations affecting architecture:

- Triggers run only row by row; there are no statement-level triggers.
- Triggers cannot start transactions or independently COMMIT/ROLLBACK; they join the invoking statement's transaction.
- Triggers cannot return a result set directly to the client.
- Stored procedures called from triggers must obey stored-program restrictions in trigger context, such as not returning result sets to the client or using dynamic SQL disallowed in that call path.
- Triggers cannot modify a table already in use by the statement that fired them.
- A trigger cannot modify OLD itself; it can only assign NEW in BEFORE INSERT/UPDATE.
- Foreign key ON DELETE CASCADE or ON UPDATE CASCADE actions in InnoDB do not fire corresponding triggers.

The last point is critical for auditing. If a child row is deleted due to a foreign key cascade, do not assume a DELETE trigger on the child table will be invoked to write an audit. If cascades must be audited, design another mechanism or perform deletions through a controlled workflow.

## 8. Triggers and Transactions

Triggers do not own their own transactions. INSERT/UPDATE/DELETE statements executed by a trigger join the statement's transaction or the caller's open transaction.

Example:

```sql
START TRANSACTION;

UPDATE orders
SET status = 'PAID'
WHERE order_id = 9001;

-- AFTER UPDATE trigger writes order_status_audit.

COMMIT;
```

If the trigger's audit INSERT fails on InnoDB, the outer UPDATE also fails. Inside an explicit transaction, the caller must handle the error and decide on ROLLBACK according to the transaction contract.

With tables using a storage engine that does not support transactions, you cannot assume all executed changes will be undone. To guarantee atomicity between source and audit tables, use a transactional engine like InnoDB for all involved tables.

### 8.1. A Trigger Error Fails the Statement

If a trigger raises SIGNAL, violates a constraint, or hits another SQL error, the statement firing the trigger fails. With InnoDB, transactional changes made by that statement roll back.

Validation example:

```sql
DELIMITER //

CREATE TRIGGER trg_products_validate_insert
BEFORE INSERT ON products
FOR EACH ROW
BEGIN
    IF NEW.price < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Price must be non-negative';
    END IF;
END//

DELIMITER ;
```

An INSERT with a negative price fails; the row is not inserted into the InnoDB table. The application should handle the SQLSTATE and message per the designed error contract.

## 9. Safe Alternative Design Patterns

When faced with a requirement like "the trigger needs to update the source table itself", identify the real goal and pick an appropriate pattern.

### 9.1. Updating Columns of the Current Row via NEW

If you only need to normalize or compute values for the row currently being written, use a BEFORE trigger:

```sql
CREATE TRIGGER trg_orders_before_insert
BEFORE INSERT ON orders
FOR EACH ROW
SET NEW.created_at = COALESCE(
    NEW.created_at,
    CURRENT_TIMESTAMP
);
```

This is an assignment on the new row, not an UPDATE on the source table.

### 9.2. Writing Audits to a Separate Table

If change history is needed, use an AFTER trigger to INSERT into an audit table. Ensure the audit table has no trigger looping back to update the source table.

### 9.3. Using a Stored Procedure as an Orchestration Point

If business logic must update multiple tables in a clear sequence, let the application call an orchestrating procedure:

1. Check preconditions.
2. Update the source table.
3. Read affected row counts if needed.
4. Update related tables with set-based statements.
5. Write outbox or audit entries.
6. Commit according to the transaction contract.

Orchestrated statements run sequentially at the procedure level after each statement completes. Never place updates to the source table inside a trigger fired by a statement on that very table.

### 9.4. Using Generated Columns or Constraints

If a value can be expressed from columns on the same row, consider a generated column. If the requirement is a single-row constraint, use CHECK, NOT NULL, UNIQUE, or appropriate keys when supported by MySQL.

Example:

```sql
CREATE TABLE order_lines (
    line_id BIGINT UNSIGNED NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    line_total DECIMAL(14, 2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED,
    PRIMARY KEY (line_id),
    CHECK (quantity > 0),
    CHECK (unit_price >= 0)
) ENGINE = InnoDB;
```

line_total is calculated from columns in the same row; no trigger is needed to UPDATE order_lines back.

### 9.5. Using an Outbox for Post-Commit Processing

If a source change must trigger another workflow, write an event to an outbox table in the same transaction as the business data. An external worker reads the outbox and performs work after commit.

This pattern fits when you:

- Need to call external services.
- Need heavy aggregation processing.
- Need independent retries.
- Do not want trigger chains stretching business transaction duration.

An outbox needs idempotency keys, processing state, and a clear retry strategy to prevent duplicate processing.

## 10. How to Trace Error 1442

When a statement reports error 1442, trace the write path back to the source table in order:

1. Identify which table the outer statement is running on.
2. List the triggers on that table.
3. Read every trigger body using SHOW CREATE TRIGGER.
4. Look for direct INSERT/UPDATE/DELETE statements on the source table.
5. Inspect routines called by the trigger.
6. Inspect functions used in expressions or statements.
7. Trace triggers on secondary tables written to by the first trigger.
8. Check whether the dependency path loops back to the source table.
9. Replace same-row writes with SET NEW.column where applicable.
10. Move multi-step workflows to a procedure/application/outbox.

List triggers in the current schema:

```sql
SHOW TRIGGERS
FROM sales;
```

View detailed definition:

```sql
SHOW CREATE TRIGGER sales.trg_orders_after_status_update;
```

Query metadata:

```sql
SELECT
    TRIGGER_SCHEMA,
    TRIGGER_NAME,
    EVENT_MANIPULATION,
    EVENT_OBJECT_SCHEMA,
    EVENT_OBJECT_TABLE,
    ACTION_TIMING,
    ACTION_STATEMENT,
    DEFINER
FROM information_schema.TRIGGERS
WHERE TRIGGER_SCHEMA = 'sales'
ORDER BY EVENT_OBJECT_TABLE, ACTION_TIMING, EVENT_MANIPULATION;
```

Metadata helps list triggers by table and timing. Then read each ACTION_STATEMENT or use SHOW CREATE TRIGGER to inspect contents and routine call paths.

### 10.1. Building a Trigger Dependency Graph

You can document paths in a table like:

| Source Trigger | Action | Next Trigger | Risk |
|---|---|---|---|
| orders AFTER UPDATE | INSERT order_audit | order_audit AFTER INSERT | Can open a nested chain |
| order_audit AFTER INSERT | UPDATE customer_summary | customer_summary trigger | Increases depth and locks |
| customer_summary AFTER UPDATE | UPDATE orders | orders trigger | Dependency cycle returning to source table |

A strictly one-way chain is easier to understand and test. If the graph has a cycle, reconsider trigger responsibilities and move orchestration to a controlled layer.

## 11. Complete Example: Replacing Self-Updating Trigger with a BEFORE Trigger

Requirement: whenever a product is updated, updated_at must reflect the new timestamp. The wrong approach is an AFTER UPDATE trigger running UPDATE products. The right approach is BEFORE UPDATE assigning NEW.updated_at.

```sql
CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;
```

Correct trigger:

```sql
DELIMITER //

CREATE TRIGGER trg_products_set_updated_at
BEFORE UPDATE ON products
FOR EACH ROW
BEGIN
    SET NEW.updated_at = CURRENT_TIMESTAMP;
END//

DELIMITER ;
```

Test:

```sql
UPDATE products
SET price = price + 1000
WHERE product_id = 10;

SELECT product_id, price, updated_at
FROM products
WHERE product_id = 10;
```

The updated_at column is set in the same row update operation. There is no nested UPDATE statement.

## 12. Complete Example: One-Way Auditing

A safe audit model keeps writes flowing one way from business tables to audit tables.

```sql
CREATE TABLE payment (
    payment_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (payment_id)
) ENGINE = InnoDB;

CREATE TABLE payment_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    payment_id BIGINT UNSIGNED NOT NULL,
    old_status VARCHAR(20) NOT NULL,
    new_status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (audit_id),
    KEY idx_payment_audit_payment (payment_id, audit_id)
) ENGINE = InnoDB;
```

Trigger:

```sql
DELIMITER //

CREATE TRIGGER trg_payment_audit
AFTER UPDATE ON payment
FOR EACH ROW
BEGIN
    IF NOT (OLD.status <=> NEW.status) THEN
        INSERT INTO payment_audit (
            payment_id,
            old_status,
            new_status
        )
        VALUES (
            NEW.payment_id,
            OLD.status,
            NEW.status
        );
    END IF;
END//

DELIMITER ;
```

Execution path:

1. UPDATE payment.
2. AFTER UPDATE trigger runs.
3. Trigger INSERTs into payment_audit.
4. Statement finishes.

There is no trigger on payment_audit writing back to payment. If additional processing is required after the audit is recorded, use a worker/outbox or an application-invoked procedure.

## 13. Common Misconceptions

| Mistake | Consequence | How to Handle |
|---|---|---|
| AFTER UPDATE trigger runs UPDATE back on source table | Error 1442 | Use BEFORE and assign NEW if modifying only the current row |
| Moving UPDATE into a stored procedure to bypass limit | Still violates if procedure modifies table used by statement | Trace the entire call chain |
| Assuming renaming alias avoids the error | MySQL still identifies the same underlying table | Redesign the write operation |
| Using triggers as a multi-layered workflow | Hard to control ordering, locks, and retries | Use procedure/application/outbox |
| Trigger A writes B, trigger B writes back to A | Dependency cycle and potential mutating-table restriction | Keep trigger graph one-way |
| Thinking triggers run once per statement | Multi-row DML can fire triggers many times | Evaluate FOR EACH ROW cost |
| Using AFTER trigger to modify NEW | Cannot assign NEW in AFTER | Assign NEW in BEFORE |
| Auditing without considering transactions | Audit and source data may lack atomicity across engines | Use InnoDB for all related tables |
| Thinking foreign key cascades fire triggers | InnoDB cascades do not fire triggers | Design separate auditing for cascades |
| Inspecting only direct triggers | Error may lie in procedures/functions or secondary table triggers | Trace all dependencies |
| Not testing batches | Triggers can noticeably slow large statements | Test with row counts near real workloads |

## 14. Safe Trigger Design Checklist

**Before creating a trigger:**

- Identify the event: INSERT, UPDATE, or DELETE.
- Choose BEFORE or AFTER based on the goal.
- If modifying the current row itself, use NEW.column in a BEFORE trigger.
- Identify which tables the outer statement uses.
- Do not design triggers that write back to the source table.
- Inspect procedures/functions the trigger may call.
- Map the dependency graph across tables and triggers.
- Eliminate A → B → ... → A cycles.
- Evaluate per-row trigger execution and batch cost.

**When writing to another table:**

- Use a separate audit/outbox table.
- Do not create triggers on the secondary table writing back to the source table.
- Use InnoDB for tables needing shared transactions.
- Establish a consistent table access order to reduce deadlocks.
- Test constraint errors, SIGNAL, and rollback.
- Confirm whether foreign key cascades skip triggers.

**During operations:**

- Use SHOW TRIGGERS and SHOW CREATE TRIGGER to inspect.
- Query INFORMATION_SCHEMA.TRIGGERS.
- Record error code 1442 and the failing statement.
- Trace stored routines and nested triggers together.
- Test single-row and multi-row DML.
- Measure statement duration and secondary write volume.
- Put trigger changes in reviewed migrations with rollback plans.

## 15. Key Takeaways

- MySQL triggers execute FOR EACH ROW; there are no statement-level triggers.
- A trigger cannot modify a table already used by the statement that fired it; a common error is 1442.
- Moving the UPDATE into a stored procedure/function does not bypass the mutating-table restriction.
- OLD and NEW provide old/new row values; OLD is read-only.
- You can assign NEW.column in BEFORE INSERT and BEFORE UPDATE to modify values on the current row itself.
- AFTER triggers are suited for writing audits to another table, not for updating the source table back.
- Triggers can create chains across secondary tables; A → B → A cycles are hard to control and risk error 1442.
- Triggers run many times for multi-row DML, so secondary costs scale with row counts.
- Triggers join the invoking statement's transaction; they have no independent transaction to COMMIT on their own.
- With InnoDB, trigger errors fail the statement and transactional changes of the statement roll back.
- Foreign key cascades in InnoDB do not fire corresponding triggers.
- When multi-step workflows, aggregation, or asynchronous processing are needed, consider stored procedures, application services, or an outbox.
- Use SHOW CREATE TRIGGER and INFORMATION_SCHEMA.TRIGGERS to trace the entire execution path.

Good trigger design keeps actions short, local, and with clear one-way dependencies. When modifying the current row, assign NEW in a BEFORE trigger; when recording history, write to a separate audit table; when coordinating multiple tables or steps, move the logic to an orchestration layer with a clear transaction contract.

## References

- MySQL 8.0 Reference Manual — Restrictions on Stored Programs: https://dev.mysql.com/doc/refman/8.0/en/stored-program-restrictions.html
- MySQL 8.0 Reference Manual — Trigger Syntax and Examples: https://dev.mysql.com/doc/refman/8.0/en/trigger-syntax.html
- MySQL 8.0 Reference Manual — Using Triggers: https://dev.mysql.com/doc/refman/8.0/en/triggers.html
- MySQL 8.0 Reference Manual — CREATE TRIGGER Statement: https://dev.mysql.com/doc/refman/8.0/en/create-trigger.html
- MySQL 8.0 Reference Manual — The TRIGGERS Table: https://dev.mysql.com/doc/refman/8.0/en/information-schema-triggers-table.html
- MySQL 8.0 Reference Manual — InnoDB and FOREIGN KEY Constraints: https://dev.mysql.com/doc/refman/8.0/en/create-table-foreign-keys.html
