# REPLACE and Its Delete/Insert Impact on Foreign Keys, Triggers, and Identifiers

This lesson belongs to the **Data Manipulation** chapter of the `DATABASE_MYSQL` module. The module aims to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, privilege management, backups, and operational troubleshooting for relational databases. The `REPLACE` statement is often described as an "overwrite if already exists" operation, yet how MySQL executes it can produce far greater side effects than an UPDATE statement.

After this lesson, you will be able to explain accurately how REPLACE handles primary key and UNIQUE key conflicts, understand why an old row is deleted before a new row is inserted, predict the impact on default values, AUTO_INCREMENT, foreign keys, and triggers, and choose between REPLACE and safer update alternatives.

## 1. What Is REPLACE?

`REPLACE` is a MySQL extension for inserting a new row. If the new row conflicts with a PRIMARY KEY or a unique index, MySQL deletes the conflicting old row and then inserts the new row.

Conceptually, you can picture it as:

~~~sql
-- Conceptual illustration, not a direct replacement syntax
DELETE FROM target_table
WHERE primary_or_unique_key_conflicts;

INSERT INTO target_table (...)
VALUES (...);
~~~

Key point: **REPLACE does not update the old row in place. It performs a delete followed by an insert.**

If there is no unique key conflict, REPLACE behaves like a standard INSERT.

Only PRIMARY KEY and unique indexes trigger conflict handling in REPLACE; a non-unique regular index does not cause old rows to be replaced. Even if the new values are identical to the existing row, the conflict branch still has delete-then-insert semantics rather than turning into a no-op UPDATE.

Example:

~~~sql
CREATE TABLE products (
    product_id INT NOT NULL PRIMARY KEY,
    sku VARCHAR(30) NOT NULL UNIQUE,
    product_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

INSERT INTO products (product_id, sku, product_name)
VALUES (1, 'KB-001', 'Keyboard');

REPLACE INTO products (product_id, sku, product_name)
VALUES (1, 'KB-001', 'Keyboard Pro');
~~~

After the REPLACE statement, the row with `product_id = 1` contains the new name. Under the hood, however, the old row was deleted and a new row was inserted.

This difference affects:

- Foreign keys referencing the old row.
- DELETE and INSERT triggers.
- AUTO_INCREMENT columns.
- Columns omitted from the INSERT list.
- Default values and DEFAULT expressions.
- Affected row counts and application logic.

## 2. REPLACE Syntax

MySQL supports several main forms.

### VALUES Form

~~~sql
REPLACE INTO table_name (column1, column2, column3)
VALUES (value1, value2, value3);
~~~

You can insert multiple rows in a single statement:

~~~sql
REPLACE INTO products (product_id, sku, product_name)
VALUES
    (1, 'KB-001', 'Keyboard Pro'),
    (2, 'MS-002', 'Wireless Mouse');
~~~

Each row is processed under REPLACE rules. One row may be newly inserted while another replaces an existing row due to a key conflict.

### SET Form

~~~sql
REPLACE INTO products
SET
    product_id = 1,
    sku = 'KB-001',
    product_name = 'Keyboard Pro';
~~~

The SET form is convenient when assigning each column by name.

### SELECT Form

You can insert data from another query:

~~~sql
REPLACE INTO product_snapshot
    (product_id, sku, product_name)
SELECT
    product_id,
    sku,
    product_name
FROM products_staging;
~~~

Each row from SELECT is processed as an input row to REPLACE. If source data conflicts with a unique key in the target table, the conflicting target row may be deleted before the new row is inserted.

REPLACE has no WHERE clause to select which target row to update. Conflict detection is based strictly on the PRIMARY KEY and unique indexes.

## 3. How Does MySQL Determine Which Rows Get Deleted?

An input row to REPLACE can conflict with:

- The PRIMARY KEY.
- A single unique index.
- Multiple unique indexes simultaneously.

If there is no conflict, MySQL inserts the new row.

If one old row conflicts, MySQL deletes that row and inserts the new row.

If the new row conflicts with multiple different old rows across different unique indexes, MySQL can delete **all conflicting old rows** and then insert one new row.

This is a very dangerous situation when a table has multiple independent UNIQUE keys.

### Primary Key Conflict

~~~sql
CREATE TABLE demo_replace (
    id INT NOT NULL PRIMARY KEY,
    value_text VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

INSERT INTO demo_replace (id, value_text)
VALUES (1, 'old value');

REPLACE INTO demo_replace (id, value_text)
VALUES (1, 'new value');

SELECT * FROM demo_replace;
~~~

The primary key `id = 1` already exists. The old row is replaced with the new row.

### Unique Index Conflict

~~~sql
CREATE TABLE account_demo (
    account_id INT NOT NULL PRIMARY KEY,
    email VARCHAR(200) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

INSERT INTO account_demo
    (account_id, email, display_name)
VALUES
    (10, 'an@example.test', 'An');

REPLACE INTO account_demo
    (account_id, email, display_name)
VALUES
    (20, 'an@example.test', 'An Nguyen');
~~~

There is no PRIMARY KEY conflict because 20 does not exist yet. However, the email is already used by the row with account_id 10. MySQL deletes that row and inserts the new row with account_id 20.

As a result, REPLACE can change the primary identifier of an entity merely because a secondary unique key matched.

### A New Row Conflicting with Two Old Rows

Pay special attention to this example:

~~~sql
CREATE TABLE account_keys (
    account_id INT NOT NULL PRIMARY KEY,
    email VARCHAR(200) NOT NULL UNIQUE,
    login_name VARCHAR(80) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

INSERT INTO account_keys
    (account_id, email, login_name, display_name)
VALUES
    (1, 'an@example.test', 'an_login', 'An'),
    (2, 'binh@example.test', 'binh_login', 'Binh');

REPLACE INTO account_keys
    (account_id, email, login_name, display_name)
VALUES
    (3, 'an@example.test', 'binh_login', 'New account');
~~~

The new row has:

- An email matching row 1.
- A login name matching row 2.
- Account ID 3, which does not exist yet.

MySQL can delete both row 1 and row 2, then insert row 3. Only one new row remains in the table.

Do not treat unique indexes as "lookup conditions to find a row to update." They are uniqueness constraints; REPLACE resolves conflicts by deleting the old rows.

## 4. Unspecified Columns Receive Default Values

Because REPLACE inserts a new row, columns omitted from the column list receive DEFAULT, NULL if permitted, or an implicit default according to SQL mode and column definition.

MySQL does not preserve the old values of omitted columns.

Example:

~~~sql
CREATE TABLE inventory (
    product_id INT NOT NULL PRIMARY KEY,
    sku VARCHAR(30) NOT NULL UNIQUE,
    product_name VARCHAR(100) NOT NULL,
    stock_quantity INT NOT NULL DEFAULT 0,
    note VARCHAR(200) NULL DEFAULT NULL
) ENGINE=InnoDB;

INSERT INTO inventory
    (product_id, sku, product_name, stock_quantity, note)
VALUES
    (1, 'KB-001', 'Keyboard', 25, 'Imported in January');

REPLACE INTO inventory
    (product_id, sku, product_name)
VALUES
    (1, 'KB-001', 'Keyboard Pro');

SELECT * FROM inventory;
~~~

After REPLACE, the row contains:

| Column | Value After REPLACE |
|---|---|
| product_id | 1 |
| sku | KB-001 |
| product_name | Keyboard Pro |
| stock_quantity | 0 |
| note | NULL |

The stock quantity of 25 and the old note are lost. They were replaced with DEFAULT because they were not supplied in the new row.

This is a common reason REPLACE causes data loss even when an application only intended to rename an item or sync a couple of columns.

If you need to keep existing column values, use UPDATE or `INSERT ... ON DUPLICATE KEY UPDATE` with an explicit list of updated columns.

## 5. Impact on AUTO_INCREMENT and Identifiers

REPLACE can generate a new AUTO_INCREMENT value if the inserted row does not provide a value for that column.

Example:

~~~sql
CREATE TABLE customer_identity (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(200) NOT NULL UNIQUE,
    full_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

INSERT INTO customer_identity (email, full_name)
VALUES ('an@example.test', 'An');

SELECT * FROM customer_identity;
~~~

Suppose the row is assigned `customer_id = 1`.

Next:

~~~sql
REPLACE INTO customer_identity (email, full_name)
VALUES ('an@example.test', 'An Nguyen');

SELECT * FROM customer_identity;
~~~

The email conflicts with the old row. The old row is deleted and a new row is inserted. Because REPLACE did not provide customer_id, MySQL assigns a new AUTO_INCREMENT value, typically 2.

The identifier has changed even though the email remained the same.

If REPLACE explicitly supplies the existing primary key value, for example:

~~~sql
REPLACE INTO customer_identity
    (customer_id, email, full_name)
VALUES
    (1, 'an@example.test', 'An Updated');
~~~

then the new row uses the specified customer_id. Even so, the operation is still a delete/insert and still carries all DELETE side effects.

### Consequences for Systems Referencing IDs

If other tables store `customer_id`, an ID change can:

- Break links if foreign keys are not designed accordingly.
- Trigger ON DELETE CASCADE and delete child rows.
- Be rejected by ON DELETE RESTRICT.
- Change the ID returned to the application or synchronization pipelines.
- Corrupt audit history or external system references not protected by foreign keys.

For entities with stable identifiers, never use REPLACE just to update attributes.

## 6. Foreign Keys: REPLACE Can Delete Data in Child Tables

Because REPLACE deletes the conflicting parent row before inserting the new row, foreign key ON DELETE actions apply just as they do for a DELETE operation.

Three critical behaviors:

| ON DELETE | When REPLACE Deletes the Parent Row |
|---|---|
| CASCADE | Referencing child rows can be deleted along with it |
| SET NULL | The foreign key column in child rows is set to NULL if configuration allows |
| RESTRICT / NO ACTION | Deleting the parent row is rejected if referencing child rows exist |

### ON DELETE CASCADE Example

~~~sql
CREATE TABLE customers (
    customer_id INT NOT NULL PRIMARY KEY,
    email VARCHAR(200) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE orders (
    order_id INT NOT NULL PRIMARY KEY,
    customer_id INT NOT NULL,
    order_total DECIMAL(12,2) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

INSERT INTO customers
    (customer_id, email, display_name)
VALUES
    (1, 'an@example.test', 'An');

INSERT INTO orders (order_id, customer_id, order_total)
VALUES
    (1001, 1, 500.00),
    (1002, 1, 250.00);
~~~

Execute REPLACE:

~~~sql
REPLACE INTO customers
    (customer_id, email, display_name)
VALUES
    (1, 'an@example.test', 'An Nguyen');
~~~

MySQL deletes the old customer row. Because the foreign key uses ON DELETE CASCADE, the orders referencing customer_id 1 are deleted as well. Then the new customer row is inserted.

Verify:

~~~sql
SELECT * FROM customers;
SELECT * FROM orders;
~~~

The customers table has the new row, but orders 1001 and 1002 have been deleted.

This is a severe risk: looking at the parent table might make it seem as though only the customer's name was updated, while all child data has been wiped out.

### ON DELETE RESTRICT Example

If the foreign key uses RESTRICT:

~~~sql
CREATE TABLE departments (
    department_id INT NOT NULL PRIMARY KEY,
    department_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE employees (
    employee_id INT NOT NULL PRIMARY KEY,
    department_id INT NOT NULL,
    CONSTRAINT fk_employee_department
        FOREIGN KEY (department_id)
        REFERENCES departments (department_id)
        ON DELETE RESTRICT
) ENGINE=InnoDB;
~~~

If a department is currently referenced by employees, replacing the department with the same key can fail because the delete step for the old row is rejected by the foreign key.

You cannot assume that re-inserting the same primary key makes the foreign key "ignore" the deletion. Constraints are checked during execution, and DELETE occurs before INSERT.

### SET NULL

With `ON DELETE SET NULL`, child rows may be preserved while their foreign key column is set to NULL. That column must allow NULL; otherwise, the delete step can fail.

### Multi-Level Foreign Keys

If a parent row has multiple levels of child data and foreign keys use CASCADE, a single REPLACE on the parent table can trigger a chain of deletions across many tables. Inspect the entire foreign key graph before running it on real data.

## 7. Both DELETE and INSERT Triggers Can Fire

REPLACE is processed as deleting the old row and inserting the new row. Consequently, DELETE and INSERT triggers can fire.

- DELETE triggers process the deleted old row.
- INSERT triggers process the newly inserted row.
- UPDATE triggers do not fire merely because REPLACE replaces a row.

This affects:

- Audit tables.
- Change history logs.
- Summary tables maintained by triggers.
- Event publishing mechanisms.
- Secondary validation or data-generation routines.

Audit table example:

The `DELIMITER` block below is a command for the `mysql` command-line client, used to change the statement terminator when defining triggers with multiple SQL statements. If using another administration tool, use that tool's trigger creation mechanism.

~~~sql
CREATE TABLE customer_events (
    event_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    event_type VARCHAR(20) NOT NULL,
    customer_id INT NOT NULL,
    email VARCHAR(200) NOT NULL,
    event_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

DELIMITER //

CREATE TRIGGER customers_after_delete
AFTER DELETE ON customers
FOR EACH ROW
BEGIN
    INSERT INTO customer_events
        (event_type, customer_id, email)
    VALUES
        ('DELETE', OLD.customer_id, OLD.email);
END//

CREATE TRIGGER customers_after_insert
AFTER INSERT ON customers
FOR EACH ROW
BEGIN
    INSERT INTO customer_events
        (event_type, customer_id, email)
    VALUES
        ('INSERT', NEW.customer_id, NEW.email);
END//

DELIMITER ;
~~~

When replacing an existing customer, both DELETE and INSERT triggers can record their corresponding events.

If you rely on UPDATE triggers to record history, those triggers will not cover the DELETE/INSERT paths of REPLACE. Design auditing to match the actual operation semantics.

**Note on cascades:** InnoDB executes foreign key actions through its own internal mechanism; cascading operations do not fire triggers on child tables. Do not rely on child-table triggers to capture every row deleted via ON DELETE CASCADE. When complete auditing is required, implement logging at the application layer or through an appropriate data pipeline.

## 8. Affected Row Counts Differ from UPDATE

REPLACE can report different affected row counts depending on what happened:

- If no old row conflicted and one new row is inserted, the affected row count is normally 1.
- If one old row is deleted and one new row is inserted, the affected row count is normally 2.
- If multiple old rows are deleted due to conflicts across multiple unique keys, the affected row count can be higher.

Do not interpret affected rows as the number of business entities "updated." REPLACE can delete several old rows and insert only one new row.

If the application needs to know exactly which entities were impacted, verify by unique keys and explicit auditing instead of relying solely on affected rows.

### LAST_INSERT_ID and AUTO_INCREMENT

If REPLACE inserts a row with a newly allocated AUTO_INCREMENT value, the connector can retrieve the generated value using MySQL's standard mechanism. Read the driver-returned value or `LAST_INSERT_ID()` immediately on the same connection when needed.

Do not assume the old ID is retained when REPLACE only passes a secondary unique key such as email or SKU.

## 9. REPLACE in Transactions and Storage Engines

For InnoDB tables, the delete and insert steps belong to the same REPLACE statement. If the statement fails due to a constraint or other error, InnoDB can roll back the statement's changes per statement atomicity.

Example:

~~~sql
START TRANSACTION;

REPLACE INTO customers
    (customer_id, email, display_name)
VALUES
    (1, 'an@example.test', 'An Updated');

-- Inspect related tables within the same transaction.

ROLLBACK;
~~~

ROLLBACK undoes changes in an uncommitted InnoDB transaction, including changes made by REPLACE.

However, do not rely on this for tables using non-transactional storage engines. With non-transactional engines, an error in a multi-row statement can leave partial changes depending on the error type and timing.

### Auto-Increment Does Not Necessarily Revert

Even when a transaction rolls back, allocated AUTO_INCREMENT values may not be reused. Gaps in the ID sequence are normal behavior; never use IDs as a gapless sequential counter.

### Required Privileges

REPLACE requires both INSERT and DELETE privileges on the target table. If either privilege is missing, the statement will be rejected.

Because the operation can delete data, the DELETE privilege is an important check when designing application accounts. An account granted only INSERT will not have enough privileges to run REPLACE.

## 10. Comparing REPLACE with UPDATE and INSERT ... ON DUPLICATE KEY UPDATE

These three options have distinct semantics.

| Criterion | REPLACE | UPDATE | INSERT ... ON DUPLICATE KEY UPDATE |
|---|---|---|---|
| No matching row | Inserts a new row | Updates no rows | Inserts a new row |
| Matching row exists | Deletes conflicting row(s), then inserts new row | Modifies rows selected by WHERE | Updates the conflicting row |
| Keeps unspecified columns | No; uses DEFAULT/NULL per definition | Yes, except columns in SET | Yes, except updated columns |
| Preserves existing identifier | Not guaranteed, especially on secondary unique conflicts with AUTO_INCREMENT | Yes, if key is not modified | Usually keeps the updated row's key |
| FK ON DELETE impact | Can trigger | No row deletion occurs | No row deletion occurs |
| Triggers | DELETE and INSERT | UPDATE | INSERT/UPDATE per execution branch |
| Best fit | Intentionally replacing an entire row with delete/insert semantics | Modifying a known row | Inserting new rows or updating specific columns on conflict |

### Using UPDATE When the Row Already Exists

If the primary key is known:

~~~sql
UPDATE inventory
SET
    product_name = 'Keyboard Pro'
WHERE product_id = 1;
~~~

The stock_quantity and note columns remain intact.

### Using INSERT ... ON DUPLICATE KEY UPDATE

If you want to insert when absent and update specific columns on conflict:

~~~sql
INSERT INTO inventory
    (product_id, sku, product_name, stock_quantity, note)
VALUES
    (1, 'KB-001', 'Keyboard Pro', 25, 'Imported in February')
ON DUPLICATE KEY UPDATE
    product_name = 'Keyboard Pro',
    stock_quantity = 25,
    note = 'Imported in February';
~~~

The duplicate branch performs an UPDATE. The old row is not deleted, so foreign key ON DELETE actions are not triggered by this statement.

List only the columns that actually need updating. If `stock_quantity` is omitted from the UPDATE clause, the existing inventory quantity is preserved.

If the table has multiple unique indexes, check whether an input row could conflict with multiple different rows. ON DUPLICATE KEY UPDATE can also fail with a unique key error if updating the conflicting row introduces another violation. Key design must ensure conflicts map to the same business entity.

### When Is REPLACE Actually Appropriate?

REPLACE can be appropriate when:

- The target row is a standalone record with no child data that must be preserved.
- Every column of the new row is supplied or has a well-defined DEFAULT.
- Deleting and re-inserting is the explicit business intent.
- DELETE/INSERT triggers and auditing are designed accordingly.
- No unintended foreign key side effects exist.
- Changing AUTO_INCREMENT or identifiers is acceptable.

For instance, a standalone staging or cache table with no dependent references is a far better candidate than a core customers table referenced by many other tables.

## 11. Safety Procedure Before Running REPLACE

Before running REPLACE in production:

1. **Check keys:** list the PRIMARY KEY and all unique indexes that could conflict.
2. **Locate existing rows:** use SELECT to see which rows currently own the keys being inserted.
3. **Check multi-key conflicts:** determine whether different unique keys could point to different existing rows.
4. **Check omitted columns:** inspect what DEFAULT, NULL, or implicit values they will receive.
5. **Check AUTO_INCREMENT:** verify whether old IDs will be kept or new IDs may be generated.
6. **Check foreign keys:** review CASCADE, SET NULL, RESTRICT, and multi-level relationships.
7. **Check triggers:** inspect what DELETE/INSERT triggers do and whether audits reflect reality.
8. **Check privileges:** the executing account needs both INSERT and DELETE.
9. **Test in a transaction or staging environment:** verify data before committing.
10. **Reconcile afterward:** inspect the target table, child tables, audits, and external references.

A pre-replacement key-check pattern:

~~~sql
SELECT *
FROM inventory
WHERE product_id = 1
   OR sku = 'KB-001';
~~~

If the two conditions return different rows, stop and determine which record is the valid owner. Do not run REPLACE just because the statement can "resolve" the conflict on its own.

## 12. Hands-On Lab: Observing REPLACE Side Effects

Perform this in an isolated lab database.

### Step 1: Create the Database and Products Table

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_replace_lab;
USE mysql_replace_lab;

CREATE TABLE inventory (
    product_id INT NOT NULL PRIMARY KEY,
    sku VARCHAR(30) NOT NULL UNIQUE,
    product_name VARCHAR(100) NOT NULL,
    stock_quantity INT NOT NULL DEFAULT 0,
    note VARCHAR(200) NULL DEFAULT NULL
) ENGINE=InnoDB;

INSERT INTO inventory
    (product_id, sku, product_name, stock_quantity, note)
VALUES
    (1, 'KB-001', 'Keyboard', 25, 'Imported in January');
~~~

### Step 2: Observe Columns Reset to DEFAULT

~~~sql
REPLACE INTO inventory
    (product_id, sku, product_name)
VALUES
    (1, 'KB-001', 'Keyboard Pro');

SELECT * FROM inventory;
~~~

Record stock_quantity and note. Explain why they are no longer 25 and the old note.

### Step 3: Observe a Secondary Unique Key Conflict Changing the ID

~~~sql
CREATE TABLE customer_identity (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(200) NOT NULL UNIQUE,
    full_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

INSERT INTO customer_identity (email, full_name)
VALUES ('an@example.test', 'An');

SELECT * FROM customer_identity;

REPLACE INTO customer_identity (email, full_name)
VALUES ('an@example.test', 'An Nguyen');

SELECT * FROM customer_identity;
~~~

Compare customer_id before and after REPLACE. Explain why the email stayed the same while the identifier changed.

### Step 4: Observe Multiple Rows Deleted Across Multiple Unique Keys

~~~sql
CREATE TABLE account_keys (
    account_id INT NOT NULL PRIMARY KEY,
    email VARCHAR(200) NOT NULL UNIQUE,
    login_name VARCHAR(80) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

INSERT INTO account_keys
    (account_id, email, login_name, display_name)
VALUES
    (1, 'an@example.test', 'an_login', 'An'),
    (2, 'binh@example.test', 'binh_login', 'Binh');

SELECT * FROM account_keys ORDER BY account_id;

REPLACE INTO account_keys
    (account_id, email, login_name, display_name)
VALUES
    (3, 'an@example.test', 'binh_login', 'New account');

SELECT * FROM account_keys ORDER BY account_id;
~~~

Observe why two old rows disappeared even though REPLACE inserted only one row.

### Step 5: Observe Foreign Key CASCADE

~~~sql
CREATE TABLE customers (
    customer_id INT NOT NULL PRIMARY KEY,
    email VARCHAR(200) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE orders (
    order_id INT NOT NULL PRIMARY KEY,
    customer_id INT NOT NULL,
    order_total DECIMAL(12,2) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

INSERT INTO customers
    (customer_id, email, display_name)
VALUES
    (1, 'an@example.test', 'An');

INSERT INTO orders (order_id, customer_id, order_total)
VALUES
    (1001, 1, 500.00),
    (1002, 1, 250.00);

REPLACE INTO customers
    (customer_id, email, display_name)
VALUES
    (1, 'an@example.test', 'An Updated');

SELECT * FROM customers;
SELECT * FROM orders;
~~~

Confirm that the new customer row exists while the old orders were deleted by CASCADE.

### Step 6: Test Safer Update Alternatives

In Step 5, the orders were deleted by CASCADE. Re-insert the child rows so you can clearly compare UPDATE and ON DUPLICATE KEY UPDATE:

~~~sql
INSERT INTO orders (order_id, customer_id, order_total)
VALUES
    (1001, 1, 500.00),
    (1002, 1, 250.00);

UPDATE customers
SET display_name = 'An Updated Safely'
WHERE customer_id = 1;

SELECT * FROM orders;
~~~

And:

~~~sql
INSERT INTO customers
    (customer_id, email, display_name)
VALUES
    (1, 'an@example.test', 'An Updated Safely')
ON DUPLICATE KEY UPDATE
    display_name = 'An Updated Safely';

SELECT * FROM orders;
~~~

Inspect the orders table. Neither update approach deletes the parent row, so neither triggers ON DELETE CASCADE like REPLACE does.

### Step 7: Cleanup

~~~sql
DROP DATABASE mysql_replace_lab;
~~~

Run this only on the lab database you just created. It drops all tables, triggers, and practice data inside that database.

## 13. Common Errors and Fixes

| Symptom | Cause | Fix |
|---|---|---|
| Lost values in omitted columns | REPLACE inserts a new row and applies DEFAULT/NULL | Supply all columns or use UPDATE / ON DUPLICATE KEY UPDATE |
| AUTO_INCREMENT ID changed | Secondary unique conflict and statement omitted old ID | Use UPDATE or ODKU if preserving identity is required |
| Child rows vanished | REPLACE deleted the parent row and ON DELETE CASCADE ran | Check FKs first; use UPDATE when only modifying attributes |
| REPLACE failed due to foreign key | Child rows reference it and FK uses RESTRICT/NO ACTION | Use UPDATE or handle child relationships per business rules |
| Audit logged DELETE and INSERT instead of UPDATE | REPLACE fires triggers for delete/insert semantics | Design triggers and auditing around actual semantics |
| Multiple accounts disappeared after one REPLACE | Different unique indexes conflicted with different rows | Check all unique keys before executing |
| Affected rows greater than 1 | Old row(s) deleted and new row inserted | Do not treat affected rows as the count of updated records |
| Insufficient privileges on REPLACE | Account lacks DELETE or INSERT privilege | Grant least privilege needed or choose the appropriate statement |
| Child audit missed cascaded deletes | InnoDB cascades do not fire triggers on child tables | Design auditing at the application layer or an appropriate pipeline |
| Multi-row REPLACE yields unpredictable results | Each input row can conflict with multiple existing rows | Inspect source data, unique keys, and test beforehand |

## 14. Pre-Use Checklist for REPLACE

- [ ] Confirmed the business genuinely wants delete-and-reinsert semantics.
- [ ] Listed the PRIMARY KEY and all unique indexes.
- [ ] Checked whether an input row could conflict with multiple existing rows.
- [ ] Checked what DEFAULT or NULL omitted columns will receive.
- [ ] Verified whether AUTO_INCREMENT could generate a new ID.
- [ ] Reviewed foreign keys and CASCADE, SET NULL, and RESTRICT actions.
- [ ] Reviewed DELETE and INSERT triggers.
- [ ] Understood that child-table triggers do not fire on InnoDB cascades.
- [ ] Verified the account has INSERT and DELETE privileges.
- [ ] Tested in staging or a rollback-capable transaction.
- [ ] Verified target table, child tables, audits, and external references afterward.
- [ ] Considered UPDATE or INSERT ... ON DUPLICATE KEY UPDATE if the goal is modifying existing rows.

## 15. Principles to Remember

1. REPLACE deletes conflicting rows and inserts a new row; it is not an UPDATE.
2. Conflicts can come from the PRIMARY KEY or any unique index.
3. One new row can cause multiple old rows to be deleted if different unique keys conflict with different rows.
4. Unspecified columns receive DEFAULT/NULL per column definition instead of preserving old values.
5. AUTO_INCREMENT can generate a new identifier when a conflict occurs on a secondary unique key.
6. Deleting the parent row can trigger ON DELETE CASCADE, SET NULL, or be rejected by RESTRICT.
7. DELETE and INSERT triggers fire; UPDATE triggers do not substitute for those two paths.
8. InnoDB cascades do not fire triggers on child tables.
9. REPLACE requires INSERT and DELETE privileges.
10. Use UPDATE or INSERT ... ON DUPLICATE KEY UPDATE when you want to modify existing rows and preserve relationships.
11. Always inspect unique keys, foreign keys, triggers, and default columns before using REPLACE in production.

## Official References

The behaviors in this lesson were verified against the **MySQL 9.7 Reference Manual** as of **19-11-2026**:

1. [REPLACE Statement](https://dev.mysql.com/doc/refman/9.7/en/replace.html): syntax, key conflict rules, multi-row deletion, privileges, and affected rows.
2. [INSERT ... ON DUPLICATE KEY UPDATE Statement](https://dev.mysql.com/doc/refman/9.7/en/insert-on-duplicate.html): comparison with updating on key conflict.
3. [InnoDB and FOREIGN KEY Constraints](https://dev.mysql.com/doc/refman/9.7/en/innodb-foreign-key-constraints.html): RESTRICT, CASCADE, SET NULL, and foreign key behavior.
4. [Using Triggers](https://dev.mysql.com/doc/refman/9.7/en/triggers.html): trigger types and firing operations.
5. [Foreign Key Constraints](https://dev.mysql.com/doc/refman/9.7/en/create-table-foreign-keys.html): foreign key definitions and referential actions.
6. [InnoDB AUTO_INCREMENT Handling](https://dev.mysql.com/doc/refman/9.7/en/innodb-auto-increment-handling.html): allocating and managing AUTO_INCREMENT values.
7. [Privileges Provided by MySQL](https://dev.mysql.com/doc/refman/9.7/en/privileges-provided.html): INSERT and DELETE privileges required for data operations.
