# Multiple Triggers for the Same Timing/Event and FOLLOWS/PRECEDES

## Lesson Objectives

After this lesson, you will be able to:

- Explain how MySQL classifies triggers by table, timing (BEFORE/AFTER), and event (INSERT/UPDATE/DELETE).
- Understand why a table can have multiple triggers for the same timing and event pair.
- Describe the default creation-order execution when no ordering clause is specified.
- Use FOLLOWS and PRECEDES to place a new trigger after or before an existing trigger.
- Identify the required conditions for the referenced trigger: same table, same timing, and same event.
- Distinguish ordering within the BEFORE group from the AFTER group.
- Understand how BEFORE triggers pass modifications through NEW to subsequent triggers.
- Inspect execution order using INFORMATION_SCHEMA.TRIGGERS and ACTION_ORDER.
- Manage trigger ordering changes during deployment, testing, and version upgrades.
- Avoid common mistakes when multiple triggers update data or write audits together.

A trigger is attached to one table, one timing, and one event. Timing can be BEFORE or AFTER; event can be INSERT, UPDATE, or DELETE. In modern MySQL, a table can have multiple triggers in the same group, such as multiple BEFORE UPDATE triggers.

If no order is specified, triggers in the same group execute in the order they were created. When explicit control is required, MySQL lets you declare FOLLOWS or PRECEDES right after FOR EACH ROW in CREATE TRIGGER. FOLLOWS places the new trigger after the named trigger; PRECEDES places the new trigger before the named trigger.

This ordering matters when one trigger normalizes data, the next trigger validates the normalized data, and another trigger stamps a timestamp or writes an audit. Without managing order, inter-trigger logic can depend on deployment history and become difficult to diagnose.

## 1. Grouping Triggers by Timing and Event

MySQL identifies a trigger group by three factors:

1. The table the trigger is attached to.
2. The activation timing: BEFORE or AFTER.
3. The activation event: INSERT, UPDATE, or DELETE.

Example on the orders table:

| Group | Timing | Event | Example Purpose |
|---|---|---|---|
| 1 | BEFORE | INSERT | Normalize data before inserting a row |
| 2 | AFTER | INSERT | Record order creation event |
| 3 | BEFORE | UPDATE | Normalize or validate new values |
| 4 | AFTER | UPDATE | Write audit after updating |
| 5 | BEFORE | DELETE | Check deletion conditions |
| 6 | AFTER | DELETE | Save deleted row information |

A table can have multiple triggers in each group. For instance, you can create three BEFORE UPDATE triggers and two AFTER UPDATE triggers on the same table.

Ordering is only defined among triggers in the same group. A BEFORE UPDATE trigger cannot be placed with FOLLOWS after an AFTER UPDATE trigger because they belong to different timings. Similarly, BEFORE INSERT and BEFORE UPDATE are two separate groups.

### 1.1. MySQL Triggers Are Always FOR EACH ROW

MySQL only supports row-level triggers:

~~~sql
CREATE TRIGGER bu_orders_example
BEFORE UPDATE ON orders
FOR EACH ROW
SET NEW.updated_at = CURRENT_TIMESTAMP;
~~~

If an UPDATE statement affects 100 rows, triggers are fired for each affected row. If there are three BEFORE UPDATE triggers in the group, all three run in their defined order for every row.

MySQL does not support FOR EACH STATEMENT. Do not design triggers as though they run only once for an entire UPDATE statement.

### 1.2. BEFORE and AFTER Have Different Responsibilities

- BEFORE: runs before the row operation completes. For INSERT and UPDATE, you can assign values to NEW.column.
- AFTER: runs after the row operation completes. You can read OLD and NEW, but you cannot modify NEW.

MySQL performs basic column value checks before firing triggers. Therefore, you cannot rely on a BEFORE trigger to turn a type-invalid or column-invalid value into a valid one. Ensure input data passes basic type and column-level checks before trigger business logic runs.

OLD/NEW availability depends on the event:

| Event | OLD | NEW |
|---|---|---|
| INSERT | Not available | Row about to be inserted |
| UPDATE | Row before update | Row after update |
| DELETE | Row about to be deleted | Not available |

OLD and NEW are case-insensitive keywords. They only access the row currently being processed by the trigger.

### 1.3. Multiple Triggers in the Same Group Run Sequentially

For a single UPDATE row, the general order is:

~~~text
BEFORE UPDATE trigger 1
BEFORE UPDATE trigger 2
BEFORE UPDATE trigger 3
       |
       v
Row update operation
       |
       v
AFTER UPDATE trigger 1
AFTER UPDATE trigger 2
~~~

This is the conceptual order for one row. When a statement updates multiple rows, the flow repeats for each row.

There is no single combined list mixing BEFORE and AFTER triggers. All BEFORE triggers for a row run before the row operation; afterward, the AFTER triggers run.

## 2. Support for Multiple Triggers per Timing/Event

Before MySQL 5.7.2, each table could have at most one trigger for each combination of timing and event. For example, a table could only have one BEFORE UPDATE trigger.

Since MySQL 5.7.2, this limit was removed. A table can have multiple triggers in the same group, and order can be controlled with FOLLOWS/PRECEDES.

| Version | Multiple triggers per group | FOLLOWS/PRECEDES | ACTION_ORDER |
|---|---|---|---|
| Before MySQL 5.7.2 | No | No | No multi-trigger ordering yet |
| MySQL 5.7.2 and later | Yes | Yes | Present in INFORMATION_SCHEMA.TRIGGERS |
| MySQL 8.0 | Yes | Yes | Yes |
| MySQL 8.4 | Yes | Yes | Yes |

If you must support servers older than 5.7.2, merge logic into one trigger per group or upgrade the server. Do not deploy multiple triggers per group on a source expecting an older replica to handle them the same way.

### 2.1. Trigger Names Are Schema-Scoped

Trigger names must be unique within the schema containing the trigger. Two different tables in the same schema cannot have two triggers with the same name. Two different schemas can use the same trigger name.

Therefore, name triggers to reflect table, event, and responsibility:

- bu_orders_10_normalize
- bu_orders_30_validate
- bu_orders_40_stamp
- au_orders_10_audit

The prefix bu can be read as BEFORE UPDATE, and au as AFTER UPDATE. The numeric part helps readers recognize intended order, though numbers in names do not control actual execution order. Actual order is determined by creation order or FOLLOWS/PRECEDES.

## 3. Default Order When Creating Multiple Triggers

If neither FOLLOWS nor PRECEDES is specified, the new trigger is placed after existing triggers on the same table, timing, and event.

Example:

~~~sql
CREATE TRIGGER bu_orders_first
BEFORE UPDATE ON orders
FOR EACH ROW
SET NEW.status = UPPER(NEW.status);

CREATE TRIGGER bu_orders_second
BEFORE UPDATE ON orders
FOR EACH ROW
SET NEW.updated_at = CURRENT_TIMESTAMP;
~~~

If bu_orders_first is created before bu_orders_second, the default execution order of the two triggers is:

1. bu_orders_first
2. bu_orders_second

This order follows creation time, not trigger name, alphabetical order, or migration filename order.

If a trigger is dropped and recreated, the default order can change because the newly created trigger becomes the newest trigger in the group. Therefore, when triggers have data dependencies on each other, use FOLLOWS/PRECEDES to express ordering directly in DDL.

### 3.1. CREATE TRIGGER Syntax and trigger_order Position

General syntax:

~~~sql
CREATE
    [DEFINER = user]
    TRIGGER trigger_name
    { BEFORE | AFTER } { INSERT | UPDATE | DELETE }
    ON table_name
    FOR EACH ROW
    [ FOLLOWS other_trigger_name | PRECEDES other_trigger_name ]
    trigger_body;
~~~

Where:

- trigger_name: name of the new trigger, unique within the schema.
- BEFORE or AFTER: activation timing.
- INSERT, UPDATE, DELETE: event.
- table_name: permanent table to which the trigger is attached.
- FOLLOWS or PRECEDES: optional clause specifying relative order.
- trigger_body: a single statement or a BEGIN ... END block.

FOLLOWS/PRECEDES sits immediately after FOR EACH ROW. Triggers cannot be attached to views or TEMPORARY tables.

## 4. FOLLOWS: Placing a New Trigger After an Existing Trigger

FOLLOWS causes the new trigger to fire after the specified trigger. The referenced trigger must exist and must share the same table, timing, and event.

Syntax:

~~~sql
CREATE TRIGGER new_trigger
BEFORE UPDATE ON orders
FOR EACH ROW
FOLLOWS existing_trigger
trigger_body;
~~~

Example:

~~~sql
CREATE TRIGGER bu_orders_validate
BEFORE UPDATE ON orders
FOR EACH ROW
FOLLOWS bu_orders_normalize
BEGIN
    IF NEW.total_amount < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'total_amount cannot be negative';
    END IF;
END;
~~~

If bu_orders_normalize is a BEFORE UPDATE trigger on the same orders table, the validate trigger is placed after it.

This matters if the normalize trigger alters NEW.status or NEW.total_amount. The validate trigger will inspect the values after the normalize trigger has run.

### 4.1. FOLLOWS Does Not Mean Calling Another Trigger

FOLLOWS only defines activation order within the server. It does not invoke a trigger like calling a stored procedure, pass parameters, or create a nested call.

When an UPDATE statement affects a row, MySQL automatically fires every trigger in the group in order. Each trigger remains an independent database object with its own body.

### 4.2. The Referenced Trigger Must Belong to the Same Group

The following example is invalid if au_orders_audit is an AFTER UPDATE trigger:

~~~sql
CREATE TRIGGER bu_orders_validate
BEFORE UPDATE ON orders
FOR EACH ROW
FOLLOWS au_orders_audit
BEGIN
    IF NEW.total_amount < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Invalid amount';
    END IF;
END;
~~~

Reason: the new trigger is BEFORE UPDATE, while the referenced trigger is AFTER UPDATE. The two triggers do not share the same action time, so a FOLLOWS relationship cannot be established.

Similarly, you cannot reference a BEFORE INSERT trigger when creating a BEFORE UPDATE trigger, even though both are on the same table.

## 5. PRECEDES: Placing a New Trigger Before an Existing Trigger

PRECEDES causes the new trigger to fire before the specified trigger.

Example:

~~~sql
CREATE TRIGGER bu_orders_default_status
BEFORE UPDATE ON orders
FOR EACH ROW
PRECEDES bu_orders_validate
BEGIN
    IF TRIM(NEW.status) = '' THEN
        SET NEW.status = 'NEW';
    END IF;
END;
~~~

If bu_orders_validate is a BEFORE UPDATE trigger on the same table, the default status trigger will run before validate.

PRECEDES is useful when inserting a data-preparation step ahead of a validation trigger or ahead of a trigger performing dependent actions.

### 5.1. Specify One Anchor Trigger

A new trigger can have only one trigger_order clause: either FOLLOWS or PRECEDES, never both at once.

Invalid example:

~~~sql
CREATE TRIGGER bu_orders_default
BEFORE UPDATE ON orders
FOR EACH ROW
FOLLOWS bu_orders_normalize
PRECEDES bu_orders_validate
SET NEW.status = 'NEW';
~~~

If you need to control a long chain, create triggers in a clear sequence and link each trigger to one anchor trigger. After creation, inspect ACTION_ORDER to confirm the actual result.

### 5.2. FOLLOWS/PRECEDES Does Not Change Event or Timing

FOLLOWS/PRECEDES only orders triggers within the same group. They cannot:

- Move a BEFORE trigger to run after the row write operation.
- Move an AFTER trigger to run before the row write operation.
- Insert an INSERT trigger between UPDATE triggers.
- Change the table a trigger is attached to.

If logic needs to run after UPDATE completes, create an AFTER UPDATE trigger. You cannot use FOLLOWS to turn BEFORE into AFTER.

## 6. Passing Changes to NEW Through a Chain of BEFORE Triggers

A key reason to define order is that BEFORE triggers can read and modify NEW values in sequence.

Example processing chain:

1. Default trigger sets NEW.status = 'NEW' if status is empty.
2. Normalization trigger converts status to uppercase and trims spaces.
3. Validation trigger verifies status is within the allowed set.
4. Timestamp trigger stamps NEW.updated_at.

Later triggers see NEW values already modified by earlier BEFORE triggers. Therefore, execution order can change business outcomes.

Example:

~~~sql
CREATE TRIGGER bu_orders_normalize
BEFORE UPDATE ON orders
FOR EACH ROW
SET NEW.status = UPPER(TRIM(NEW.status));

CREATE TRIGGER bu_orders_validate
BEFORE UPDATE ON orders
FOR EACH ROW
FOLLOWS bu_orders_normalize
BEGIN
    IF NEW.status NOT IN ('NEW', 'PAID', 'CANCELLED') THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Unsupported order status';
    END IF;
END;
~~~

When updating status to ' paid ', the normalize trigger converts it to PAID. The validate trigger then checks PAID, not the raw input string.

If the order were reversed, validate could reject ' paid ' before normalize had a chance to fix it.

### 6.1. AFTER Triggers Read the Final Result

AFTER triggers cannot modify NEW. They can read OLD and NEW to write audits or update other tables.

Example:

~~~sql
CREATE TRIGGER au_orders_audit
AFTER UPDATE ON orders
FOR EACH ROW
INSERT INTO order_audit (
    order_id,
    old_status,
    new_status,
    changed_at
)
VALUES (
    OLD.order_id,
    OLD.status,
    NEW.status,
    CURRENT_TIMESTAMP
);
~~~

If there are multiple AFTER UPDATE triggers, they also have their own ordering. Their ordering is never mixed with BEFORE UPDATE triggers.

## 7. Lab: Normalizing, Defaulting, Validating, and Auditing

This lab creates four BEFORE UPDATE triggers with explicit ordering and one AFTER UPDATE trigger for auditing. The BEFORE triggers demonstrate both FOLLOWS and PRECEDES.

### 7.1. Creating the Tables

~~~sql
CREATE TABLE orders_trigger_demo (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    updated_at DATETIME NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;

CREATE TABLE orders_trigger_audit_demo (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    old_status VARCHAR(20) NOT NULL,
    new_status VARCHAR(20) NOT NULL,
    old_amount DECIMAL(12, 2) NOT NULL,
    new_amount DECIMAL(12, 2) NOT NULL,
    changed_at DATETIME NOT NULL,
    PRIMARY KEY (audit_id),
    KEY idx_audit_order (order_id)
) ENGINE = InnoDB;

INSERT INTO orders_trigger_demo (
    status, total_amount
)
VALUES ('new', 100.00);
~~~

### 7.2. Creating the First Normalization Trigger

This trigger is created first in the BEFORE UPDATE group:

The DELIMITER command is a mysql command-line client directive to change the statement terminator when sending a trigger definition containing multiple semicolons. It is not an SQL statement sent to the server; if using another client tool, use that tool's equivalent delimiter mechanism.

~~~sql
DELIMITER $$

CREATE TRIGGER bu_orders_10_normalize
BEFORE UPDATE ON orders_trigger_demo
FOR EACH ROW
SET NEW.status = UPPER(TRIM(NEW.status))$$

DELIMITER ;
~~~

### 7.3. Creating the Validation Trigger Using FOLLOWS

The validate trigger must run after normalize:

~~~sql
DELIMITER $$

CREATE TRIGGER bu_orders_30_validate
BEFORE UPDATE ON orders_trigger_demo
FOR EACH ROW
FOLLOWS bu_orders_10_normalize
BEGIN
    IF NEW.total_amount < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'total_amount cannot be negative';
    END IF;

    IF NEW.status NOT IN ('NEW', 'PAID', 'CANCELLED') THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Unsupported order status';
    END IF;
END$$

DELIMITER ;
~~~

### 7.4. Creating the Timestamping Trigger

This trigger runs after validate:

~~~sql
DELIMITER $$

CREATE TRIGGER bu_orders_40_stamp
BEFORE UPDATE ON orders_trigger_demo
FOR EACH ROW
FOLLOWS bu_orders_30_validate
SET NEW.updated_at = CURRENT_TIMESTAMP$$

DELIMITER ;
~~~

### 7.5. Creating the Defaulting Trigger Using PRECEDES

This trigger is created last, yet placed before normalize:

~~~sql
DELIMITER $$

CREATE TRIGGER bu_orders_00_default
BEFORE UPDATE ON orders_trigger_demo
FOR EACH ROW
PRECEDES bu_orders_10_normalize
BEGIN
    IF TRIM(NEW.status) = '' THEN
        SET NEW.status = 'NEW';
    END IF;
END$$

DELIMITER ;
~~~

Expected order in the BEFORE UPDATE group:

| ACTION_ORDER | Trigger | Responsibility |
|---:|---|---|
| 1 | bu_orders_00_default | Assign NEW if status is empty |
| 2 | bu_orders_10_normalize | Trim whitespace and uppercase |
| 3 | bu_orders_30_validate | Validate status and amount |
| 4 | bu_orders_40_stamp | Assign updated_at |

Even though the default trigger was created last, PRECEDES places it before the normalize trigger. FOLLOWS establishes the chain normalize → validate → stamp.

### 7.6. Creating the AFTER UPDATE Audit Trigger

~~~sql
DELIMITER $$

CREATE TRIGGER au_orders_10_audit
AFTER UPDATE ON orders_trigger_demo
FOR EACH ROW
INSERT INTO orders_trigger_audit_demo (
    order_id,
    old_status,
    new_status,
    old_amount,
    new_amount,
    changed_at
)
VALUES (
    OLD.order_id,
    OLD.status,
    NEW.status,
    OLD.total_amount,
    NEW.total_amount,
    CURRENT_TIMESTAMP
)$$

DELIMITER ;
~~~

The audit trigger belongs to the AFTER UPDATE group, independent of the BEFORE UPDATE group. It reads the result after BEFORE triggers have processed NEW and the UPDATE operation has succeeded.

### 7.7. Checking Order in Metadata

~~~sql
SELECT
    TRIGGER_NAME,
    EVENT_MANIPULATION,
    ACTION_TIMING,
    ACTION_ORDER
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE TRIGGER_SCHEMA = DATABASE()
  AND EVENT_OBJECT_TABLE = 'orders_trigger_demo'
ORDER BY
    EVENT_MANIPULATION,
    ACTION_TIMING,
    ACTION_ORDER;
~~~

ACTION_ORDER is the trigger's execution position within the list of triggers for the same table, EVENT_MANIPULATION, and ACTION_TIMING. Do not compare ACTION_ORDER between BEFORE UPDATE and AFTER UPDATE as if they belonged to a single shared list.

You can view trigger definitions:

~~~sql
SHOW CREATE TRIGGER bu_orders_30_validate;
SHOW CREATE TRIGGER bu_orders_00_default;
~~~

SHOW CREATE TRIGGER helps inspect the trigger body and the FOLLOWS/PRECEDES clause.

### 7.8. Testing Updating Values That Require Normalization

~~~sql
UPDATE orders_trigger_demo
SET status = ' paid ',
    total_amount = 150.00
WHERE order_id = 1;

SELECT *
FROM orders_trigger_demo
WHERE order_id = 1;

SELECT *
FROM orders_trigger_audit_demo
WHERE order_id = 1
ORDER BY audit_id;
~~~

Expected result:

- The default trigger does not change status because the value is non-empty.
- The normalize trigger changes ' paid ' to PAID.
- The validate trigger accepts the status and amount.
- The stamp trigger assigns updated_at.
- The AFTER trigger writes an audit with OLD.status as new and NEW.status as PAID.

### 7.9. Testing PRECEDES with an Empty Status

~~~sql
UPDATE orders_trigger_demo
SET status = '   '
WHERE order_id = 1;

SELECT order_id, status, updated_at
FROM orders_trigger_demo
WHERE order_id = 1;
~~~

The default trigger runs before normalize, changing the empty string to NEW. The normalize trigger continues normalizing to NEW, validate accepts it, and stamp updates the timestamp.

### 7.10. Testing Validation Errors

~~~sql
UPDATE orders_trigger_demo
SET total_amount = -1.00
WHERE order_id = 1;
~~~

The UPDATE statement is rejected with SQLSTATE 45000. Triggers following the validate trigger in the BEFORE UPDATE group do not run for that update; the row operation does not complete and the AFTER UPDATE audit trigger does not fire.

With InnoDB, changes from the failed statement roll back according to the engine's transaction rules. Do not assume similar rollback behavior for tables using a storage engine that does not support transactions.

## 8. Inspecting and Managing Triggers

### 8.1. Listing Triggers in a Schema

~~~sql
SHOW TRIGGERS;
~~~

SHOW TRIGGERS is useful for viewing the trigger list, event, timing, table, definition, and definer. The LIKE clause of SHOW TRIGGERS filters by trigger name, not by the attached table name. To filter by table and inspect order, use the INFORMATION_SCHEMA.TRIGGERS query in the next section.

### 8.2. Viewing Order and Definitions with INFORMATION_SCHEMA

~~~sql
SELECT
    TRIGGER_NAME,
    EVENT_OBJECT_TABLE,
    EVENT_MANIPULATION,
    ACTION_TIMING,
    ACTION_ORDER,
    ACTION_STATEMENT
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE TRIGGER_SCHEMA = DATABASE()
ORDER BY
    EVENT_OBJECT_TABLE,
    EVENT_MANIPULATION,
    ACTION_TIMING,
    ACTION_ORDER;
~~~

Key columns:

- TRIGGER_NAME: trigger name.
- EVENT_OBJECT_TABLE: attached table.
- EVENT_MANIPULATION: INSERT, UPDATE, or DELETE.
- ACTION_TIMING: BEFORE or AFTER.
- ACTION_ORDER: position within the group of triggers with the same event and timing.
- ACTION_STATEMENT: trigger body contents.

Appropriate privileges are required to view schema metadata. Never use ACTION_ORDER alone while ignoring table, event, and timing.

### 8.3. Dropping a Trigger

~~~sql
DROP TRIGGER IF EXISTS bu_orders_30_validate;
~~~

If the trigger is not in the default database, specify the schema explicitly:

~~~sql
DROP TRIGGER IF EXISTS app_db.bu_orders_30_validate;
~~~

DROP TRIGGER only removes the specified trigger. It does not drop the table the trigger is attached to.

If a table is dropped, the triggers attached to that table are dropped as well.

### 8.4. Changing the Order of Existing Triggers

FOLLOWS/PRECEDES is specified at CREATE TRIGGER time. You cannot use ALTER TRIGGER to change activation order.

If you need to change the ordering relationship of an existing trigger, plan a DROP and CREATE of the trigger with the appropriate trigger_order clause. Because this operation can create a window where the trigger does not exist, deploy it in a controlled migration and verify ACTION_ORDER afterward.

When a trigger is dropped, the remaining triggers in the group remain independent triggers. Do not rely on the old order after changing the trigger set; always check metadata and re-establish any needed FOLLOWS/PRECEDES relationships.

## 9. Common Mistakes When Using Multiple Triggers

| Error or Misconception | Reality | How to Handle |
|---|---|---|
| A table can only have one BEFORE UPDATE trigger | Since MySQL 5.7.2, multiple triggers per group are allowed | Check server version |
| A new trigger always runs first | By default, a new trigger runs after existing triggers in the group | Use PRECEDES if it must run earlier |
| Trigger name controls order | Names do not control execution order | Use FOLLOWS/PRECEDES and check ACTION_ORDER |
| FOLLOWS can reference any trigger | Referenced trigger must have same table, event, and timing | Verify group before creating |
| PRECEDES changes timing | It only changes order within the same group | Create with the right BEFORE/AFTER from the start |
| BEFORE and AFTER share a single list | The two timings are two independent groups | Check ACTION_TIMING |
| AFTER trigger can modify NEW | NEW is read-only in AFTER | Move value-modifying logic to BEFORE |
| Later trigger does not see prior NEW changes | Later BEFORE triggers see NEW modified by earlier triggers | Define order explicitly |
| Order by numbers in names | Names like _10_ or _20_ are only conventions | Do not use as a substitute for FOLLOWS/PRECEDES |
| ACTION_ORDER is schema-wide order | ACTION_ORDER is meaningful within same table, event, and timing | ORDER BY all grouping columns |
| Can use FOLLOWS and PRECEDES together | A trigger has only one trigger_order clause | Design one anchor relationship per trigger |
| DROP then CREATE does not affect order | The recreated trigger may become a newer element in the group | Redeclare order and verify |
| Trigger fails yet statement continues | Trigger error fails the statement | Use SIGNAL intentionally and test transactions |
| Foreign key cascade fires triggers | Cascaded foreign key actions do not fire triggers | Place necessary logic elsewhere |
| Triggers on TEMPORARY tables | MySQL does not support triggers on TEMPORARY tables or views | Attach triggers to permanent tables |
| Replication always runs triggers like source | Statement-based and row-based replication handle triggers differently | Check binlog format and topology |

## 10. Event and Replication Notes

### 10.1. INSERT ... ON DUPLICATE KEY UPDATE

The INSERT ... ON DUPLICATE KEY UPDATE statement can trigger different trigger chains depending on whether a new row has a key conflict.

For a row, BEFORE INSERT fires first. If a duplicate key occurs, the UPDATE branch continues by firing BEFORE UPDATE and AFTER UPDATE; if there is no duplicate, the INSERT branch finishes with AFTER INSERT.

Therefore, when a table has both INSERT and UPDATE triggers, test both branches of this statement separately. Do not assume an INSERT statement only fires INSERT triggers in every case.

### 10.2. Foreign Key Cascades

Foreign key cascade actions do not fire triggers. For example, if ON DELETE CASCADE deletes child rows because a parent row was deleted, DELETE triggers on the child table are not fired by that cascade operation.

If cascaded changes must also be audited, design auditing at the business layer or in an appropriate data model; do not assume child table triggers receive every delete operation.

### 10.3. Statement-Based and Row-Based Replication

How triggers behave on a replica depends on the binlog format:

- Statement-based replication: the statement executes on the replica and the replica's triggers are fired by that statement.
- Row-based replication: triggers do not re-run on the replica for replicated row changes; changes produced by triggers on the source are logged as row events and applied on the replica.

When deploying multiple triggers in a replication topology, every server must have compatible schema and trigger definitions. Do not upgrade the source ahead of a replica if the replica still runs a version that does not support multiple triggers per group.

## 11. Workflow for Designing and Deploying Trigger Ordering

When a table has multiple triggers with the same timing and event:

1. List responsibilities: normalization, defaults, validation, timestamping, auditing.
2. Classify each responsibility into BEFORE or AFTER and INSERT/UPDATE/DELETE.
3. Put operations that must modify NEW into BEFORE.
4. Identify data dependencies between BEFORE triggers.
5. Choose an anchor trigger and declare FOLLOWS/PRECEDES for dependent triggers.
6. Use AFTER for audits or operations that need to read the written row.
7. Verify order in INFORMATION_SCHEMA.TRIGGERS using ACTION_ORDER.
8. Test multiple rows, empty values, valid values, and values that raise SIGNAL.
9. Verify whether an error in one trigger prevents subsequent triggers from running.
10. Verify storage engine transaction behavior.
11. Verify trigger definitions and ordering after migration.
12. Verify binlog format and replica compatibility.
13. Document each trigger's responsibility so operators understand why the order exists.

Deployment diagram:

~~~mermaid
flowchart TD
    A[Business analysis] --> B[Group by BEFORE/AFTER and INSERT/UPDATE/DELETE]
    B --> C[List triggers in the same group]
    C --> D[Identify dependencies between triggers]
    D --> E[Choose FOLLOWS/PRECEDES]
    E --> F[Create triggers]
    F --> G[Read INFORMATION_SCHEMA.TRIGGERS]
    G --> H{ACTION_ORDER correct?}
    H -->|No| I[Adjust migration]
    I --> F
    H -->|Yes| J[Test DML and error paths]
    J --> K[Verify audit, transaction, and replication]
    K --> L[Deploy with control]
~~~

## 12. Practice Exercises

### Exercise 1: Multiple BEFORE UPDATE Triggers

Create two BEFORE UPDATE triggers on one table. The first trigger normalizes status, and the second trigger validates status. Prove that the second trigger sees the normalized NEW.status.

### Exercise 2: Default Order

Create three triggers in the same group in different orders. Query ACTION_ORDER and confirm the default order.

### Exercise 3: FOLLOWS

Create a new trigger using FOLLOWS referencing an existing trigger. Check ACTION_ORDER before and after creation.

### Exercise 4: PRECEDES

Create a status-defaulting trigger with PRECEDES referencing a normalize trigger. Try updating status to an empty string and observe the result.

### Exercise 5: Referencing the Wrong Group

Try using FOLLOWS to reference an AFTER UPDATE trigger when creating a BEFORE UPDATE trigger. Record the error and explain the same-group requirement.

### Exercise 6: BEFORE vs. AFTER

Create a BEFORE UPDATE trigger that modifies NEW and an AFTER UPDATE trigger that writes an audit. Compare the NEW value recorded in the audit with the initial value from the UPDATE statement.

### Exercise 7: ACTION_ORDER

Write a query against INFORMATION_SCHEMA.TRIGGERS listing triggers by schema, table, event, timing, and action order. Explain why all grouping columns must be included.

### Exercise 8: Failing Trigger

Create a BEFORE UPDATE trigger using SIGNAL when total_amount is negative. Verify that subsequent triggers do not run and the AFTER UPDATE audit does not write a row for the failed statement.

### Exercise 9: Order Change After DROP/CREATE

DROP one trigger in the group and recreate it. Observe ACTION_ORDER and re-establish the necessary FOLLOWS/PRECEDES relationships.

### Exercise 10: Replication Verification

Use a test environment with a source and replica. Compare trigger behavior with statement-based and row-based binlog formats. Verify that audit data is not written twice on the replica.

## Conclusion

MySQL allows multiple triggers for the same table, timing, and event starting in version 5.7.2. When no order is specified, triggers in the same group run in creation order. FOLLOWS places the new trigger after a trigger in the same group; PRECEDES places the new trigger before a trigger in the same group.

Explicit ordering is especially important when BEFORE triggers jointly modify NEW or when one trigger validates data normalized by a preceding trigger. AFTER triggers belong to a separate group and are typically suited for writing audits after the row operation. Use INFORMATION_SCHEMA.TRIGGERS and ACTION_ORDER to verify actual order, then test both valid data and error paths before deployment.

## References

- MySQL 8.4 Reference Manual — Trigger Syntax and Examples: https://dev.mysql.com/doc/refman/8.4/en/trigger-syntax.html
- MySQL 8.4 Reference Manual — CREATE TRIGGER Statement: https://dev.mysql.com/doc/refman/8.4/en/create-trigger.html
- MySQL 8.4 Reference Manual — INFORMATION_SCHEMA TRIGGERS Table: https://dev.mysql.com/doc/refman/8.4/en/information-schema-triggers-table.html
- MySQL 8.4 Reference Manual — DROP TRIGGER Statement: https://dev.mysql.com/doc/refman/8.4/en/drop-trigger.html
- MySQL 8.4 Reference Manual — Replication and Triggers: https://dev.mysql.com/doc/refman/8.4/en/replication-features-triggers.html
- MySQL 5.7.2 Release Notes — Multiple Triggers for the Same Event and Action Time: https://dev.mysql.com/doc/relnotes/mysql/5.7/en/news-5-7-2.html
