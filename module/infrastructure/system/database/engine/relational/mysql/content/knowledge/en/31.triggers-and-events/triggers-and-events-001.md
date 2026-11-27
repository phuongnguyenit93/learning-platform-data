# BEFORE/AFTER Triggers for INSERT, UPDATE, and DELETE

A trigger in MySQL is a stored program automatically invoked by the database when a table event occurs. For InnoDB tables, triggers can validate data before writing, normalize input values, or write audit records after a row is inserted, updated, or deleted. Triggers run per row (`FOR EACH ROW`), so a statement affecting 1,000 rows can invoke a trigger 1,000 times.

MySQL supports two timings, `BEFORE` and `AFTER`, combined with three events, `INSERT`, `UPDATE`, and `DELETE`. Inside a trigger, `NEW` represents the new row values and `OLD` represents the row values before the operation. In `BEFORE INSERT` and `BEFORE UPDATE`, you can assign values to `NEW.column`; `AFTER` triggers can only read the relevant values. `DELETE` only has `OLD` because there is no new row after the operation.

Triggers are suitable for data rules that must be enforced consistently regardless of which client writes to the table, such as normalizing fields, validating state transitions, or recording audits in the same transaction. Triggers are not suitable for making HTTP calls, sending emails, orchestrating services, or containing long business workflows that are hard to observe.

## 1. What Is a Trigger?

A trigger is a schema object attached to a table and automatically fired by MySQL when the table receives an operation of the declared type. Applications do not invoke triggers with `CALL`; the application executes `INSERT`, `UPDATE`, or `DELETE`, and the trigger runs according to its definition.

Key characteristics:

- A trigger is attached to a single base table.
- Triggers execute row by row; MySQL does not have statement-level triggers.
- Each trigger has one event (`INSERT`, `UPDATE`, `DELETE`) and one timing (`BEFORE`, `AFTER`).
- Triggers use `OLD`/`NEW` to access row values.
- Triggers run within the context of the triggering statement and in the same transaction if the tables use a transactional engine such as InnoDB.
- Triggers do not create an independent transaction and cannot issue `COMMIT`/`ROLLBACK` themselves.

Since MySQL 5.7.2, a table can have multiple triggers with the same timing/event. If no order is specified, they execute in creation order; `FOLLOWS` or `PRECEDES` can be used to define relative ordering.

## 2. Six Combinations of BEFORE/AFTER and INSERT/UPDATE/DELETE

| Trigger | Timing | Readable | Assignable |
| --- | --- | --- | --- |
| `BEFORE INSERT` | Before inserting each row | `NEW` | `NEW.column` |
| `AFTER INSERT` | After inserting each row | `NEW` | Cannot modify `NEW` |
| `BEFORE UPDATE` | Before updating each row | `OLD`, `NEW` | `NEW.column` |
| `AFTER UPDATE` | After updating each row | `OLD`, `NEW` | Cannot modify `NEW` |
| `BEFORE DELETE` | Before deleting each row | `OLD` | No `NEW` |
| `AFTER DELETE` | After deleting each row | `OLD` | No `NEW` |

`OLD` is always the row image before the operation; `NEW` is the new row image for INSERT/UPDATE. Do not use `OLD` in an INSERT trigger or `NEW` in a DELETE trigger.

## 3. CREATE TRIGGER Syntax

General syntax:

```sql
CREATE
    [DEFINER = user]
    TRIGGER trigger_name
    trigger_time trigger_event
    ON tbl_name
    FOR EACH ROW
    [FOLLOWS other_trigger | PRECEDES other_trigger]
    trigger_body;
```

`trigger_time` is `BEFORE` or `AFTER`; `trigger_event` is `INSERT`, `UPDATE`, or `DELETE`; `trigger_body` is a single statement or a `BEGIN ... END` compound statement.

Minimal example:

```sql
CREATE TRIGGER bi_customers_set_created_at
BEFORE INSERT ON customers
FOR EACH ROW
SET NEW.created_at = COALESCE(NEW.created_at, CURRENT_TIMESTAMP);
```

When creating a trigger using the MySQL command-line client, you usually need to change `DELIMITER` because the body may contain semicolons. `DELIMITER` is a client command, not an SQL statement sent to the server; migration frameworks/JDBC typically need to send the full `CREATE TRIGGER` statement according to the tool's own mechanism.

## 4. Preparing the Sample Tables

The example uses a customers table and an audit table. The audit table has no foreign key to `customers`, so the history remains after a customer is deleted:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    display_name VARCHAR(150) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4;

CREATE TABLE customer_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    operation VARCHAR(10) NOT NULL,
    old_status VARCHAR(20) NULL,
    new_status VARCHAR(20) NULL,
    changed_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (audit_id),
    KEY idx_customer_audit_customer_time (customer_id, changed_at)
) ENGINE=InnoDB;
```

In real systems, auditing may require actor, request ID, source service, or snapshots of changed fields. Only store identity from a session variable if the application sets it over a trusted connection and prevents callers from spoofing it arbitrarily.

## 5. BEFORE INSERT: Normalizing and Validating New Values

`BEFORE INSERT` runs before the new row is written. This is the right place to normalize input values and reject invalid data:

```sql
DELIMITER //

CREATE TRIGGER bi_customers_normalize
BEFORE INSERT ON customers
FOR EACH ROW
BEGIN
    SET NEW.email = LOWER(TRIM(NEW.email));
    SET NEW.display_name = TRIM(NEW.display_name);

    IF NEW.email = '' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Email must not be empty';
    END IF;

    IF NEW.status NOT IN ('pending', 'active', 'suspended') THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Invalid customer status';
    END IF;
END//

DELIMITER ;
```

`NEW` is the row about to be inserted, so the trigger can assign `NEW.email` and `NEW.display_name`. If a condition is invalid, `SIGNAL` raises an error and the INSERT statement fails.

Do not check for duplicate email with a `SELECT` before inserting: a race condition can occur between checking and writing. Use a `UNIQUE KEY` so the database enforces uniqueness; triggers should only handle rules that constraints cannot express.

## 6. AFTER INSERT: Writing an Audit Record After Row Insertion

`AFTER INSERT` runs after the new row has been added to the base table. You can write an audit record using `NEW` values:

```sql
DELIMITER //

CREATE TRIGGER ai_customers_audit
AFTER INSERT ON customers
FOR EACH ROW
BEGIN
    INSERT INTO customer_audit (
        customer_id, operation, old_status, new_status
    )
    VALUES (
        NEW.customer_id, 'INSERT', NULL, NEW.status
    );
END//

DELIMITER ;
```

The trigger can read `NEW.customer_id` after MySQL has assigned the `AUTO_INCREMENT` value. The audit row is written in the same InnoDB transaction as the original INSERT. If the audit insert fails, the original INSERT statement also fails; the two changes are never committed separately.

## 7. BEFORE UPDATE: Validating Changes and Normalizing NEW

`BEFORE UPDATE` has both the old image `OLD` and the proposed new image `NEW`. You can compare states, reject invalid state transitions, or set timestamps:

```sql
DELIMITER //

CREATE TRIGGER bu_customers_validate
BEFORE UPDATE ON customers
FOR EACH ROW
BEGIN
    SET NEW.email = LOWER(TRIM(NEW.email));
    SET NEW.display_name = TRIM(NEW.display_name);

    IF NEW.status NOT IN ('pending', 'active', 'suspended') THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Invalid customer status';
    END IF;

    IF NOT (OLD.status <=> NEW.status)
       AND OLD.status = 'suspended'
       AND NEW.status = 'active' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Suspended customer cannot be reactivated here';
    END IF;

    SET NEW.updated_at = CURRENT_TIMESTAMP;
END//

DELIMITER ;
```

`<=>` is MySQL's NULL-safe comparison operator. `NOT (OLD.status <=> NEW.status)` detects differences even when one value is NULL. A trigger can modify `NEW` in BEFORE UPDATE; do not assign to `OLD` because it is the pre-operation row image and is read-only.

## 8. AFTER UPDATE: Recording Old and New Values

`AFTER UPDATE` can read both `OLD` and `NEW`. For example, write an audit record only when the status changes:

```sql
DELIMITER //

CREATE TRIGGER au_customers_audit
AFTER UPDATE ON customers
FOR EACH ROW
BEGIN
    IF NOT (OLD.status <=> NEW.status) THEN
        INSERT INTO customer_audit (
            customer_id, operation, old_status, new_status
        )
        VALUES (
            NEW.customer_id, 'UPDATE', OLD.status, NEW.status
        );
    END IF;
END//

DELIMITER ;
```

You cannot modify `NEW.status` in an AFTER trigger. If you need to change a value before writing, do it in a BEFORE trigger. AFTER triggers are suited for in-database side effects such as writing audit or outbox rows.

Do not use an AFTER trigger to update the same `customers` table already being used by the UPDATE statement; MySQL prevents triggers from modifying a table already used by the triggering statement and may raise error 1442.

## 9. BEFORE DELETE: Rejecting Deletions Based on Data Rules

`BEFORE DELETE` only has `OLD`. You can inspect the existing row before allowing deletion:

```sql
DELIMITER //

CREATE TRIGGER bd_customers_protect_active
BEFORE DELETE ON customers
FOR EACH ROW
BEGIN
    IF OLD.status = 'active' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Active customer cannot be deleted';
    END IF;
END//

DELIMITER ;
```

If the trigger raises `SIGNAL`, the DELETE operation for that row is rejected. There is no `NEW` in a DELETE trigger because the deleted row has no post-operation image.

For relational rules such as "do not delete a customer who still has orders", a `RESTRICT` foreign key is usually more appropriate and clearer than a trigger counting rows manually. Use triggers when the condition cannot be expressed with a constraint or when additional behavior is needed.

## 10. AFTER DELETE: Saving an Audit Record Before Losing the Row

`AFTER DELETE` runs after the row is removed from the base table, yet can still read the old values via `OLD`:

```sql
DELIMITER //

CREATE TRIGGER ad_customers_audit
AFTER DELETE ON customers
FOR EACH ROW
BEGIN
    INSERT INTO customer_audit (
        customer_id, operation, old_status, new_status
    )
    VALUES (
        OLD.customer_id, 'DELETE', OLD.status, NULL
    );
END//

DELIMITER ;
```

Because the audit table has no foreign key to `customers`, the history record remains after the customer is deleted. The trigger runs in the same transaction as the original DELETE; if the audit insert fails on InnoDB, the DELETE will not commit on its own either.

## 11. NEW and OLD: Usage Rules

| Trigger | `OLD.column` | `NEW.column` | Write to `NEW`? |
| --- | --- | --- | --- |
| BEFORE INSERT | Invalid | Value about to be inserted | Yes |
| AFTER INSERT | Invalid | Inserted value | No |
| BEFORE UPDATE | Value before update | Proposed new value | Yes |
| AFTER UPDATE | Value before update | Value after update | No |
| BEFORE DELETE | Value about to be deleted | Invalid | No |
| AFTER DELETE | Deleted value | Invalid | No |

`OLD`/`NEW` only reference columns of the current row. To read other rows, use a SELECT within the trigger scope provided it does not hit MySQL's restrictions.

## 12. Triggers Execute Row by Row

If a statement affects 500 rows, the corresponding trigger can run 500 times:

```sql
UPDATE customers
SET status = 'suspended'
WHERE status = 'pending';
```

With 500 matching rows, BEFORE UPDATE and AFTER UPDATE fire once for each row. A trigger with a heavy subquery or large audit insert multiplies that cost by the number of rows.

MySQL does not support statement-level triggers that execute once for the entire UPDATE statement. If you need to process an entire dataset, prefer set-based SQL in the application/procedure or explicit batch design. Do not assume MySQL provides virtual `inserted`/`deleted` tables containing the entire rowset.

## 13. Multiple Triggers for the Same Timing and Event

On MySQL 5.7.2 and later, you can create multiple triggers for the same table, timing, and event. If no order is specified, they run in creation order. You can specify order explicitly:

```sql
CREATE TRIGGER bu_customers_second_check
BEFORE UPDATE ON customers
FOR EACH ROW
FOLLOWS bu_customers_validate
BEGIN
    SET NEW.display_name = TRIM(NEW.display_name);
END;
```

`FOLLOWS`/`PRECEDES` defines relative order against another trigger with the same timing/event on the same table. The referenced trigger must exist. When multiple triggers exist, inspect `ACTION_ORDER` in metadata and manage ordering through migrations.

## 14. Using SIGNAL to Reject Data

Inside a trigger, use `SIGNAL` to intentionally raise an SQL error:

```sql
SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'Business rule violated';
```

`45000` is the SQLSTATE reserved for user-defined application exceptions. The caller receives the error and can map it to an appropriate business error. Keep messages short and stable, and do not include sensitive data in the message. Do not silently ignore invalid data or mutate data in ways the caller cannot predict.

## 15. Trigger Transactions and Rollback

With InnoDB tables, the triggering statement and the InnoDB operations executed by the trigger belong to the same transaction:

- If the original INSERT/UPDATE/DELETE fails, changes made inside the trigger are also rolled back.
- If the audit operation inside the trigger fails, the original statement fails.
- If the caller's transaction rolls back after the statement succeeds, both base table changes and audit changes are rolled back.
- Triggers must not open their own transaction, `COMMIT`, or `ROLLBACK`.

This fits audit rows or outbox rows that must be atomic with the data change. Prefer InnoDB for both the base table and secondary tables written by triggers. If using a nontransactional engine, do not assume all side effects roll back together.

Triggers should not send emails or make HTTP calls. Write an outbox event in the same transaction; a Java worker reads the outbox and performs side effects after commit.

## 16. Important Limitations of MySQL Triggers

- Triggers only run `FOR EACH ROW`; there are no statement-level triggers.
- You cannot use `START TRANSACTION`, `COMMIT`, or `ROLLBACK` inside a trigger.
- Triggers cannot return a result set directly to the client.
- You cannot use `RETURN` to exit a trigger as in a function.
- A trigger cannot modify a table already being used by the statement that fired it; doing so can raise error 1442.
- You cannot create triggers on views; triggers attach to base tables.
- `TRUNCATE TABLE` is DDL and does not fire DELETE triggers.
- Cascade operations performed by foreign keys do not fire the corresponding triggers.
- There is no `UPDATE OF column` syntax; you must compare `OLD`/`NEW` to know which column changed.
- Triggers increase the latency and lock duration of the original statement.

All stored-program limitations apply to the trigger body. Do not design triggers as places for network orchestration or transaction control.

## 17. Checking Which Columns Actually Changed

MySQL does not have trigger syntax like `AFTER UPDATE OF status`. UPDATE triggers are declared per table; if you only want to audit specific columns, compare `OLD` and `NEW`:

```sql
IF NOT (OLD.email <=> NEW.email)
   OR NOT (OLD.display_name <=> NEW.display_name) THEN
    -- Write audit for contact information changes.
END IF;
```

The `<=>` operator performs a NULL-safe comparison, unlike `=` when NULLs are involved. Do not use `OLD.col <> NEW.col` if you need to accurately detect transitions between NULL and a non-NULL value.

## 18. Special INSERT Forms and Data Write Paths

Beyond standard INSERTs, MySQL has special write forms:

- `INSERT ... ON DUPLICATE KEY UPDATE` may go through INSERT and UPDATE trigger logic depending on whether each row is newly inserted or hits the duplicate branch.
- `REPLACE` may delete conflicting rows and then insert new rows; the corresponding DELETE and INSERT triggers may fire.
- `LOAD DATA` can also fire INSERT triggers for the loaded rows.

These forms have specific firing orders and counts depending on the actual execution path. If a table has audit or normalization triggers, test every DML form the application uses; do not assume every write command only fires an INSERT trigger.

## 19. Triggers, Foreign Keys, and Cascades

Foreign keys and triggers are two separate mechanisms. InnoDB can automatically execute `ON DELETE CASCADE` or `ON UPDATE CASCADE`, but cascade operations performed by foreign keys do not fire triggers on the cascaded tables.

If deleting a customer causes child rows to be deleted via `ON DELETE CASCADE`, the child table's DELETE trigger does not run for those cascaded deletions. If you need to audit cascaded changes, you must design another mechanism or perform explicit deletes through the application/procedure.

Do not replace foreign keys with triggers that manually check relationships when a constraint can express the requirement accurately. Constraints are managed by the database and protect better against race conditions.

## 20. Triggers and DEFINER Security

Triggers have a `DEFINER` attribute; when a trigger runs, MySQL checks privileges on underlying objects against the definer's privileges. Triggers do not have an `SQL SECURITY INVOKER` clause like procedures/functions.

This allows an application user to run DML on a table while the trigger writes audits using the definer's privileges. You should:

- Use a dedicated definer account with least privilege.
- Ensure the definer exists across all target deployment environments.
- Avoid using a DBA account or personal account with overly broad privileges.
- Grant the `TRIGGER` privilege to the deployment account creating triggers and required privileges on related tables.
- Verify the definer's privileges on audit/outbox tables after migrations.
- Manage `DEFINER` in source control/migrations and review privilege changes.

`CURRENT_USER()` inside a trigger reflects the active security context/definer, not inherently the application's end-user identity. If you need to audit the actor, pass the identity through a trusted application mechanism protected against spoofing.

## 21. Inspecting Triggers and Metadata

List triggers:

```sql
SHOW TRIGGERS FROM app_db;
```

View definition:

```sql
SHOW CREATE TRIGGER app_db.ai_customers_audit\G
```

Query metadata:

```sql
SELECT
    TRIGGER_NAME,
    EVENT_MANIPULATION,
    EVENT_OBJECT_TABLE,
    ACTION_TIMING,
    ACTION_ORDER,
    DEFINER,
    SQL_MODE,
    ACTION_STATEMENT
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE TRIGGER_SCHEMA = 'app_db'
ORDER BY EVENT_OBJECT_TABLE, EVENT_MANIPULATION,
         ACTION_TIMING, ACTION_ORDER;
```

Metadata helps verify triggers, event/timing, ordering, and definer. Appropriate privileges are required to view full definitions. Do not rely solely on trigger names; inspect `ACTION_STATEMENT` and test actual behavior.

Drop a trigger:

```sql
DROP TRIGGER IF EXISTS app_db.ai_customers_audit;
```

Modifying a trigger typically requires `DROP` followed by `CREATE` via a migration. Perform this in a controlled manner because the gap between drop and create can allow DML to run without the trigger; plan the migration and verify afterward.

## 22. Performance and Operational Cost

Triggers execute synchronously within the original statement. Trigger processing time adds directly to INSERT/UPDATE/DELETE latency and can extend lock hold times.

- Keep triggers short, with minimal subqueries and proper indexes.
- Avoid cursors/row-by-row loops when set-based SQL can be used.
- Avoid auditing many large columns unnecessarily; manage storage size and retention.
- Check for deadlocks when triggers write to multiple tables or transactions update tables in different orders.
- Benchmark DML before and after adding triggers under representative load.
- Monitor audit/outbox table size, indexes, and purge/archive throughput.
- Test all write paths: application code, batch jobs, ETL, `LOAD DATA`, upserts, and admin tools.

Triggers can create side effects that are hard to spot from application SQL alone. Document clearly in schema docs and migrations that a table has triggers; developers/DBAs should check triggers when investigating slow DML or unexpected errors.

## 23. Trigger Testing Workflow

1. Create an equivalent test schema and representative dataset.
2. Test each event (INSERT, UPDATE, DELETE) at the required timing.
3. Verify `OLD`/`NEW`, NULLs, defaults, and `AUTO_INCREMENT`.
4. Test multi-row DML to confirm per-row trigger execution.
5. Verify `SIGNAL` fails the statement and InnoDB rolls back properly.
6. Verify audits when the transaction commits and when the caller rolls back.
7. Test upserts, REPLACE, and LOAD DATA if the workload uses them.
8. Check whether foreign key cascades bypass child table triggers.
9. Verify definer privileges and runtime user privileges.
10. Verify execution order when multiple triggers share the same event/timing.
11. Measure latency, lock waits, deadlocks, and generated storage growth.
12. Prepare a migration rollback and verify triggers after deployment.

## 24. Common Errors and Misconceptions

| Misconception / Error | Reality | How to Handle |
| --- | --- | --- |
| AFTER trigger can modify NEW | NEW in AFTER is read-only | Assign values in a BEFORE trigger |
| DELETE trigger has NEW | DELETE only has OLD | Read data via OLD |
| Trigger runs once per statement | MySQL runs FOR EACH ROW | Estimate cost per row |
| Can COMMIT inside a trigger | Trigger joins the statement/caller transaction | Let the caller own the transaction |
| TRUNCATE fires DELETE triggers | TRUNCATE is DDL and skips DELETE triggers | Use DELETE if row-level triggers are needed |
| FK CASCADE fires child triggers | Cascades executed by InnoDB skip triggers | Design separate cascade auditing |
| Can UPDATE the triggering table | MySQL blocks modifying a table used by the statement (1442) | Assign NEW in BEFORE or write to another table |
| Triggers only run from Java | Any DML client on the table can fire them | Test ETL, batch jobs, and admin tools too |
| Triggers have no latency impact | Triggers run synchronously with DML | Benchmark cost under realistic load |
| DEFINER is the request's end user | Trigger runs under definer privileges | Design a separate, trusted actor audit mechanism |

## 25. Practice Exercises

1. Create `customers` and `customer_audit` following the example.
2. Create a BEFORE INSERT trigger to trim/lowercase email and reject empty emails with `SIGNAL`.
3. Create an AFTER INSERT trigger to write audits; inspect `AUTO_INCREMENT` in `NEW`.
4. Create a BEFORE UPDATE trigger to validate status and set `NEW.updated_at`.
5. Create an AFTER UPDATE trigger that writes an audit only when `OLD.status` differs from `NEW.status` using NULL-safe comparison.
6. Create a BEFORE DELETE trigger rejecting deletion of active customers; inspect the error received by the caller.
7. Create an AFTER DELETE trigger recording `OLD.customer_id` and `OLD.status` in the audit table.
8. UPDATE multiple rows; count audit records and explain per-row trigger execution.
9. Create two BEFORE UPDATE triggers on the same table; use `FOLLOWS` and inspect `ACTION_ORDER`.
10. Try `TRUNCATE TABLE` and FK `ON DELETE CASCADE`; observe that triggers do not fire as in normal DELETEs.
11. Try `INSERT ... ON DUPLICATE KEY UPDATE`, `REPLACE`, and `LOAD DATA` if the lab environment supports them.
12. Grant `TRIGGER` privilege to the deployment user and least privilege to the definer.
13. Measure DML execution time before/after adding triggers and with proper indexes on the audit table.
14. Design a trigger that only writes an outbox event to InnoDB; use an external worker to process side effects.

## 26. Key Takeaways

A MySQL trigger attaches to one table, one timing (`BEFORE`/`AFTER`), and one event (`INSERT`/`UPDATE`/`DELETE`), executing `FOR EACH ROW`. `BEFORE INSERT`/`BEFORE UPDATE` can read and assign `NEW`; `AFTER` is read-only; DELETE only has `OLD`. Use BEFORE to normalize/validate and `SIGNAL SQLSTATE '45000'` to reject data; use AFTER to write audit or outbox rows in the same transaction.

Triggers are not statement-level triggers, cannot COMMIT/ROLLBACK on their own, cannot return result sets, and cannot modify a table already used by the triggering statement; `TRUNCATE` does not fire DELETE triggers, and FK cascades do not fire child table triggers. Side effects run synchronously, increasing latency and lock duration; keep triggers short, use constraints when appropriate, manage DEFINER/`TRIGGER` privileges, and check `OLD`/`NEW`, multi-trigger ordering, and metadata. Test all real DML paths; use an outbox/worker for side effects outside the database.
