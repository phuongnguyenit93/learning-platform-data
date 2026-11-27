# Cannot Add/Update/Delete Child Row and Foreign Key Errors

Foreign key errors commonly occur when an application inserts or updates a child record whose referenced parent record does not exist, or when an application deletes or updates a parent record while dependent child records still exist. In MySQL InnoDB, the two most common errors are `ERROR 1452` (cannot add or update a child row) and `ERROR 1451` (cannot delete or update a parent row).

Foreign keys protect referential integrity in the database. When an error occurs, pinpoint the child table, parent table, constraint, participating columns, and data state at the moment the statement failed. Never disable foreign key checks just to push a statement through: doing so can create orphan data, and MySQL does not re-validate previously written rows when checks are turned back on.

This lesson uses MySQL 8.4 and InnoDB. Examples illustrate customer, order, and order item relationships; substitute your actual table and column names when investigating.

## Objectives

After this lesson, you will be able to:

- Distinguish error 1452 on child tables from error 1451 on parent tables.
- Read constraint names and identify the referenced columns.
- Inspect parent/child data, data types, indexes, and foreign key definitions.
- Understand `RESTRICT`, `NO ACTION`, `CASCADE`, and `SET NULL` behavior.
- Handle write ordering, imports, migrations, and transactions involving foreign keys.
- Detect orphan data if foreign key checks were previously disabled.
- Choose fixes that preserve business integrity rather than arbitrarily deleting or bypassing data.

## 1. The Two Common Foreign Key Errors

Suppose the schema has three tables:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (id)
) ENGINE = InnoDB;

CREATE TABLE purchase_orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY idx_orders_customer_id (customer_id),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT
) ENGINE = InnoDB;

CREATE TABLE order_items (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    quantity INT NOT NULL,
    PRIMARY KEY (id),
    KEY idx_items_order_id (order_id),
    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_orders (id)
        ON UPDATE RESTRICT
        ON DELETE CASCADE
) ENGINE = InnoDB;
```

`purchase_orders.customer_id` is a child column referencing `customers.id`. `order_items.order_id` is a child column referencing `purchase_orders.id`.

### 1.1. ERROR 1452: Cannot add or update a child row

Error 1452 occurs when an `INSERT` or `UPDATE` produces a foreign key value in a child table without a matching parent row.

For example, customer `9001` does not exist:

```sql
INSERT INTO purchase_orders (customer_id, created_at)
VALUES (9001, NOW());
```

MySQL returns an error like:

```text
ERROR 1452 (23000): Cannot add or update a child row:
a foreign key constraint fails
```

The message usually includes the database, child table, and constraint name, such as `fk_orders_customer`. The direct cause is that `purchase_orders.customer_id = 9001` does not reference a valid `customers.id`.

The same error occurs when updating a child row:

```sql
UPDATE purchase_orders
SET customer_id = 9001
WHERE id = 100;
```

If customer 9001 does not exist, the `UPDATE` is rejected. If the foreign key column allows `NULL`, setting it to `NULL` can be valid because no parent row reference is required; this must be a deliberate business decision.

### 1.2. ERROR 1451: Cannot delete or update a parent row

Error 1451 occurs when a `DELETE` or `UPDATE` alters a referenced key in a parent table while child rows still exist and the constraint action prohibits that change.

For example, customer 10 still has orders:

```sql
DELETE FROM customers
WHERE id = 10;
```

If `purchase_orders` still contains rows with `customer_id = 10` and the constraint uses `RESTRICT`/`NO ACTION`, MySQL rejects the operation:

```text
ERROR 1451 (23000): Cannot delete or update a parent row:
a foreign key constraint fails
```

This error can also occur when updating `customers.id` to a different value. Check both deletes and primary key updates; `DELETE` is not the only statement that triggers 1451.

### 1.3. Quick Distinction

| Error Code | Target Table | Triggering Condition | First Investigation Path |
|---|---|---|---|
| 1452 | Child table | New foreign key value has no matching parent row | Look up the parent row using the full referenced key |
| 1451 | Parent table | Referencing child rows still exist and FK action disallows the change | Find all referencing child rows |

`SQLSTATE 23000` represents integrity constraint violations. Do not rely on `SQLState` alone to conclude the cause; read the error code, constraint name, and specific statement.

## 2. Procedure for Investigating Error 1452

### 2.1. Read the Constraint Name from the Error Message

Example error excerpt:

```text
CONSTRAINT `fk_orders_customer`
FOREIGN KEY (`customer_id`)
REFERENCES `customers` (`id`)
```

This tells you:

- Child table: `purchase_orders`.
- Child column: `customer_id`.
- Parent table: `customers`.
- Referenced column: `id`.
- Constraint: `fk_orders_customer`.

If the application message was truncated, run:

```sql
SHOW CREATE TABLE purchase_orders\G
```

Do not guess the constraint from column names alone. A table can have multiple foreign keys or a single composite foreign key spanning multiple columns.

### 2.2. Check Whether the Parent Row Exists

For the failing value:

```sql
SELECT id, full_name
FROM customers
WHERE id = 9001;
```

If no row returns, check whether the application passed the wrong ID, used an ID from another environment, or failed to create the parent row first. Confirm the database/schema the connection is using:

```sql
SELECT DATABASE() AS current_database,
       @@hostname AS server_host,
       @@port AS server_port,
       @@autocommit AS autocommit_mode;
```

A common mistake is creating the customer in database A while creating the order in database B, or reading an ID from staging and writing to production. Always verify the actual active connection rather than relying on assumed configuration.

### 2.3. Check the Entire Key for Composite Foreign Keys

Example two-column constraint:

```sql
FOREIGN KEY (tenant_id, account_id)
REFERENCES accounts (tenant_id, id)
```

The parent row must match both `tenant_id` and `account_id` simultaneously. Checking only `account_id` is insufficient:

```sql
SELECT tenant_id, id
FROM accounts
WHERE tenant_id = 7
  AND id = 9001;
```

Column order in the foreign key and supporting index must also match. Do not reorder columns when reading constraints or writing diagnostic queries.

### 2.4. Check NULLs and Data Rules

If the child column allows `NULL`, a `NULL` value requires no matching parent row. If the column is `NOT NULL`, `NULL` can trigger a `NOT NULL` constraint error before or alongside data validation depending on the statement.

Check the definition:

```sql
SHOW CREATE TABLE purchase_orders\G

SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'purchase_orders'
  AND COLUMN_NAME = 'customer_id';
```

Do not use `NULL` to bypass the error if every order must belong to a customer. When the relationship is mandatory, create or identify the right parent row before writing the child row.

## 3. Procedure for Investigating Error 1451

### 3.1. Find Referencing Child Rows

If attempting to delete customer 10:

```sql
SELECT id, customer_id, created_at
FROM purchase_orders
WHERE customer_id = 10;
```

If rows return, they reference the customer. Depending on business rules, you can:

- Reject deleting the customer and preserve order history.
- Reassign the relationship to another valid customer if permitted by business logic.
- Archive or delete child rows via an approved workflow.
- Use `ON DELETE CASCADE` if deleting the parent must delete all child data.

Never delete child rows solely to make a `DELETE` succeed. Orders, invoices, and transaction histories often must be retained for audit or business requirements.

### 3.2. Inspect Multi-Level Relationship Chains

In the example, customers have orders, and orders have items. Deleting a customer may be blocked by `purchase_orders`; deleting an order may trigger a cascade to `order_items` per the declared constraint.

Query all related data before making changes:

```sql
SELECT
    c.id AS customer_id,
    p.id AS order_id,
    i.id AS item_id,
    i.product_name
FROM customers AS c
LEFT JOIN purchase_orders AS p
    ON p.customer_id = c.id
LEFT JOIN order_items AS i
    ON i.order_id = p.id
WHERE c.id = 10
ORDER BY p.id, i.id;
```

This query clarifies the scope of affected data. In multi-tier schemas, continue tracing foreign keys downward from parent tables to child tables and inspect every cascade action.

### 3.3. Updating Parent Keys

If altering a primary key or referenced key, check the `ON UPDATE` rule:

```sql
SELECT
    CONSTRAINT_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE CONSTRAINT_SCHEMA = DATABASE()
  AND REFERENCED_TABLE_NAME = 'customers'
  AND REFERENCED_COLUMN_NAME = 'id';
```

In standard design, surrogate identifying primary keys like `id` rarely need to change. If a business code must change, consider keeping a stable surrogate primary key and updating the separate business-code column. That avoids cascading updates across foreign keys.

## 4. Verifying Foreign Key Definitions and Data Types

### 4.1. Read SHOW CREATE TABLE on Both Sides

Run for both child and parent tables:

```sql
SHOW CREATE TABLE customers\G
SHOW CREATE TABLE purchase_orders\G
```

Compare:

- Storage engine of both tables; InnoDB supports foreign keys.
- Data types of the referencing and referenced columns.
- Length and signedness for integer types.
- Charset/collation for string columns.
- Column order in composite keys.
- Indexes on the referenced column and child column.
- `ON DELETE` and `ON UPDATE` rules.

Common design mismatch example:

```sql
-- Signedness mismatch:
-- customers.id is BIGINT UNSIGNED
-- purchase_orders.customer_id is signed BIGINT
```

For integer types, size and signedness must match. For string types, charset/collation on both columns must be compatible per InnoDB requirements. When creating a foreign key, define the child column with the exact same type as the parent column instead of expecting MySQL to coerce values.

### 4.2. Query Constraint Metadata

Look up constraints and participating columns:

```sql
SELECT
    k.CONSTRAINT_NAME,
    k.TABLE_NAME AS child_table,
    k.COLUMN_NAME AS child_column,
    k.ORDINAL_POSITION,
    k.REFERENCED_TABLE_NAME AS parent_table,
    k.REFERENCED_COLUMN_NAME AS parent_column
FROM information_schema.KEY_COLUMN_USAGE AS k
WHERE k.CONSTRAINT_SCHEMA = DATABASE()
  AND k.REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY k.TABLE_NAME, k.CONSTRAINT_NAME, k.ORDINAL_POSITION;
```

Look up delete/update rules:

```sql
SELECT
    CONSTRAINT_NAME,
    TABLE_NAME,
    REFERENCED_TABLE_NAME,
    UPDATE_RULE,
    DELETE_RULE
FROM information_schema.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE();
```

These queries determine exact constraint names and behaviors in the current database. If working across multiple schemas, filter explicitly by `CONSTRAINT_SCHEMA` rather than relying on `DATABASE()`.

### 4.3. Indexes and Composite Keys

InnoDB requires an appropriate index on the referenced column in the parent table; by design you should reference a primary key or unique key. The child column also needs an index so referential checks and cascading operations run efficiently; InnoDB can automatically create the required index when adding a foreign key if none exists.

For a composite key `(tenant_id, account_id)`, the index must start with the columns in the exact required order. Inspect indexes:

```sql
SHOW INDEX FROM accounts;
SHOW INDEX FROM purchase_orders;
```

Do not mechanically create duplicate indexes. Check whether an existing index already shares the required leading column prefix and order.

## 5. ON DELETE and ON UPDATE Behaviors

Referential actions determine how MySQL handles deleting a parent row or updating a referenced key.

| Rule | Behavior | When to Consider |
|---|---|---|
| `RESTRICT` | Rejects parent modification if referencing child rows exist | When you want to protect child data and force explicit handling in the app |
| `NO ACTION` | In InnoDB, equivalent to `RESTRICT`; checked immediately, not deferred until end of transaction | When clearly stating parent changes are disallowed while children exist |
| `CASCADE` | Automatically deletes/updates matching child rows when the parent changes | When child data lifecycle depends entirely on the parent |
| `SET NULL` | Sets the foreign key column in child rows to `NULL` | When the relationship is optional and the child column allows `NULL` |

If no rule is specified, the default restricts parent changes (`NO ACTION`/`RESTRICT` per InnoDB semantics).

### 5.1. RESTRICT and NO ACTION

Both rules prohibit deleting/updating the parent while child rows still exist. In InnoDB, checks run immediately when the statement executes; MySQL does not support deferred constraint checking until `COMMIT`.

### 5.2. CASCADE

Example where deleting an order automatically deletes its items:

```sql
CONSTRAINT fk_items_order
    FOREIGN KEY (order_id)
    REFERENCES purchase_orders (id)
    ON DELETE CASCADE
```

Deleting a `purchase_orders` row automatically deletes its corresponding `order_items` rows. This is a powerful action: accidentally deleting one parent row can wipe out many child rows. Only use cascade when data lifecycles and retention policies permit it.

### 5.3. SET NULL

Example where a manager relationship is optional:

```sql
CREATE TABLE employees (
    id BIGINT UNSIGNED PRIMARY KEY,
    manager_id BIGINT UNSIGNED NULL,
    CONSTRAINT fk_employee_manager
        FOREIGN KEY (manager_id)
        REFERENCES employees (id)
        ON DELETE SET NULL
) ENGINE = InnoDB;
```

When a manager is deleted, `manager_id` on direct reports is set to `NULL`. The `manager_id` column must allow `NULL`; if it is `NOT NULL`, this design is invalid.

### 5.4. Do Not Change Rules Just to Avoid Errors

Changing `RESTRICT` to `CASCADE` to silence error 1451 can delete unintended data. Changing it to `SET NULL` can break required relationships. Before changing a rule, confirm:

1. Whether the relationship is mandatory.
2. Whether child data must exist independently after parent deletion.
3. Whether audit, retention, or soft-delete requirements apply.
4. How many rows will be cascaded or set to null.
5. Whether the application and reports accept the new behavior.

## 6. Write Ordering and Transactions

### 6.1. Create Parent First, Child Second

When creating a customer and an order in the same transaction, insert the parent row first:

```sql
START TRANSACTION;

INSERT INTO customers (full_name)
VALUES ('Nguyen An');

SET @customer_id = LAST_INSERT_ID();

INSERT INTO purchase_orders (customer_id, created_at)
VALUES (@customer_id, NOW());

COMMIT;
```

In application code, retrieve the generated key via JDBC/JPA or use an explicitly generated ID. If parent creation fails, roll back the transaction and do not proceed to insert child rows with an assumed ID.

### 6.2. Delete Child First, Parent Second

With `RESTRICT`, if business rules require deleting the whole tree, delete child rows first:

```sql
START TRANSACTION;

DELETE FROM order_items
WHERE order_id IN (
    SELECT id
    FROM purchase_orders
    WHERE customer_id = 10
);

DELETE FROM purchase_orders
WHERE customer_id = 10;

DELETE FROM customers
WHERE id = 10;

COMMIT;
```

This is strictly a technical example; do not run this flow if orders or items must be retained. For large datasets, batch the deletes, control locking, and assess transaction duration. InnoDB DML operations can roll back before commit; do not assume the same for DDL.

### 6.3. Pre-Checking Before Writing Does Not Replace Foreign Keys

A common mistake pattern is:

1. `SELECT` to check if the parent exists.
2. If found, run `INSERT` into the child table.

Between the two steps, another transaction may delete or modify the parent. Relying only on a pre-check query creates a race condition. The foreign key is the final safeguard, and InnoDB coordinates locks to preserve integrity across concurrent transactions.

Applications may still pre-check to provide friendly error messages, but they must handle 1452/1451 errors at the actual write operation. Never treat an earlier `SELECT` result as a guarantee that the parent still exists.

## 7. Imports, Migrations, and Orphan Data

### 7.1. Import in Dependency Order

When loading data from CSV or dumps:

1. Create the schema and tables in dependency order.
2. Load parent table data first.
3. Load child table data afterward.
4. Reconcile row counts, keys, and referential integrity.
5. Switch applications to use the data only after verification passes.

When using dump/restore tools, check how the tool orders tables, triggers, and constraints. A standalone child table data file may fail to import independently if its parent table has not been populated yet.

### 7.2. foreign_key_checks

MySQL allows disabling foreign key checks in a session:

```sql
SELECT @@SESSION.foreign_key_checks;
SET SESSION foreign_key_checks = 0;
-- Controlled import operation.
SET SESSION foreign_key_checks = 1;
```

This is a special mechanism for controlled import/restore workflows, not a fix for 1452 or 1451 errors in applications. While `foreign_key_checks` is disabled, MySQL can accept child rows without matching parents. Re-enabling the variable does not scan or re-validate data loaded while checks were off.

If checks were ever turned off, proactively query for orphan rows before trusting the dataset. Also ensure the variable is re-enabled in the exact same session; a session variable does not affect other connections.

### 7.3. Finding Orphan Data

For `purchase_orders.customer_id -> customers.id`:

```sql
SELECT p.id, p.customer_id
FROM purchase_orders AS p
LEFT JOIN customers AS c
    ON c.id = p.customer_id
WHERE p.customer_id IS NOT NULL
  AND c.id IS NULL
LIMIT 100;
```

Count total orphans:

```sql
SELECT COUNT(*) AS orphan_count
FROM purchase_orders AS p
LEFT JOIN customers AS c
    ON c.id = p.customer_id
WHERE p.customer_id IS NOT NULL
  AND c.id IS NULL;
```

For composite foreign keys, join on all columns in matching pairs. If a component is allowed to be `NULL`, evaluate according to composite key semantics and business rules rather than joining on a single column and assuming orphan status.

### 7.4. Fixing Orphan Rows

Never auto-delete orphans. Possible remediation options include:

- Restoring missing parent rows from an authoritative data source.
- Remapping child keys to the proper parent row when backed by business evidence.
- Moving invalid records to a quarantine area for data-owner review.
- Deleting child records only when retention policy allows and with approval.
- Keeping records in a staging table without promoting them into production tables until relationships are valid.

Record affected counts, keys, and remediation actions for auditability. Afterward, re-run the orphan query and verify all related relationships.

## 8. Deep Diagnostics with InnoDB and Performance Schema

### 8.1. SHOW ENGINE INNODB STATUS

After a foreign key error, run:

```sql
SHOW ENGINE INNODB STATUS\G
```

Locate the `LATEST FOREIGN KEY ERROR` section. It typically logs the timestamp, transaction, statement, and constraint involved in the most recent foreign key error recorded by InnoDB. This is valuable when application logs omit full details.

Note: this records only the latest error on the instance and can be overwritten by a subsequent error. Collect it promptly after reproducing the error; do not treat it as a complete history across all transactions.

### 8.2. Inspecting Transactions and Locks

When errors only happen under concurrent load, inspect active transactions and locks:

```sql
SELECT *
FROM information_schema.INNODB_TRX
ORDER BY trx_started;

SELECT *
FROM performance_schema.data_locks;

SELECT *
FROM performance_schema.data_lock_waits;
```

These tables help locate long-running transactions, pending locks, and relationships between lock holders and blocked transactions. Access to Performance Schema / Information Schema may depend on account privileges; grant appropriate read-only observability permissions to operators.

### 8.3. Comparing Constraints Against Live Data

For a 1452 error, record the failing statement's foreign key value and query the exact parent table. For 1451, query the child table using the parent key. If data changes continuously, investigate within an appropriate transaction/snapshot or reproduce in a test environment; queries executed after the failure may see a different state than existed at failure time.

## 9. Real-World Troubleshooting Walkthrough

An order creation service intermittently receives error 1452:

```text
Cannot add or update a child row:
a foreign key constraint fails
(`shop`.`purchase_orders`, CONSTRAINT `fk_orders_customer`
FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`))
```

Troubleshooting steps:

1. Record the `customer_id` sent in the request and confirm the connection's database/schema.
2. Run `SHOW CREATE TABLE purchase_orders` and verify `fk_orders_customer` references `customers.id`.
3. Query `customers` for that ID. If missing, trace where the ID originated: request payload, cache, customer creation service, or an earlier transaction.
4. If the customer was created in another transaction, verify that transaction committed before the order write ran.
5. If customer and order are created in the same flow, insert the parent before the child in the same transaction and use the real generated ID.
6. If errors occur only under concurrent requests, check for race conditions, transaction rollbacks, and parent-creation logs.
7. After deploying the fix, monitor error rates and reconcile orphan rows.

Another example: deleting a customer fails with 1451. Query all orders for that customer, check retention policies, and choose among rejecting the delete, soft-deleting, reassigning relationships, or executing an approved cascade delete. Never change `RESTRICT` to `CASCADE` just to silence the error message.

## 10. Common Causes and Fixes

| Symptom | Possible Cause | Remediation Path |
|---|---|---|
| Child insert reports 1452 | Parent does not exist or wrong ID passed | Verify ID and create parent before child |
| Child update reports 1452 | Updated FK to a nonexistent parent | Verify target parent and mapping |
| Parent delete reports 1451 | Referencing child rows still exist | Find child rows and apply business policy |
| Parent key update reports 1451 | Parent key referenced by children; rule forbids cascade | Keep surrogate key stable or design proper update rule |
| Fails in only one environment | Wrong database, missing seed data, or environment drift | Verify `DATABASE()`, host, and parent data |
| Error during import | Child loaded before parent or dump missing parent table | Order import sequence and reconcile keys |
| FK creation fails | Incompatible type, signedness, charset/collation, or missing index | Compare `SHOW CREATE TABLE` on both tables |
| Orphans exist after re-enabling `foreign_key_checks` | MySQL does not re-validate existing data automatically | Run orphan query and repair data |
| Error appears only under load | Race condition between parent/child ops or transaction rollback | Inspect transactions, locks, and handle errors on write |
| Deleting parent wipes too much data | `ON DELETE CASCADE` mismatches data lifecycle | Review retention, soft delete, and FK rules |

## 11. Foreign Key Troubleshooting Checklist

- [ ] Recorded full error code (1451/1452), `SQLState`, and failing statement.
- [ ] Confirmed the connection's actual database/schema.
- [ ] Read constraint name, child table, parent table, and all participating columns.
- [ ] Checked parent existence (1452) or referencing child rows (1451).
- [ ] For composite FKs, verified all column pairs in exact order.
- [ ] Compared data types, signedness, charset/collation, and indexes on both tables.
- [ ] Checked `ON DELETE`, `ON UPDATE`, nullability, and transaction order.
- [ ] Inspected `LATEST FOREIGN KEY ERROR` if deeper InnoDB diagnostics were needed.
- [ ] Checked imports, migrations, concurrent transactions, and potential rollbacks.
- [ ] If `foreign_key_checks` was ever disabled, queried for and resolved orphan rows.
- [ ] Chose a business-aligned fix, retained evidence, and monitored after deployment.

## 12. Self-Check Exercises

1. Does `ERROR 1452` occur on the parent table or child table? What condition triggers it?
2. Can `ERROR 1451` occur when updating a parent table's primary key?
3. For a composite foreign key `(tenant_id, account_id)`, why is checking only `account_id` insufficient?
4. How does `RESTRICT` differ from `CASCADE` when deleting a parent?
5. Why does `SET NULL` require the foreign key column to allow `NULL`?
6. Does disabling and re-enabling `foreign_key_checks` cause MySQL to validate already-loaded rows?
7. When importing data with parent/child relationships, which table should be loaded first?
8. Why does checking parent existence via `SELECT` before `INSERT` not replace a foreign key?
9. Which command displays InnoDB's `LATEST FOREIGN KEY ERROR` section?
10. Before considering cascade when deleting a customer with orders, what must you determine?

**Answer hints:** (1) Child table; the new FK value has no matching parent row. (2) Yes, if child rows exist and `ON UPDATE` does not permit the change. (3) Because all components of the key must match the same parent row in exact order. (4) `RESTRICT` blocks deleting the parent while children exist; `CASCADE` automatically deletes dependent child rows. (5) Because MySQL must set the child row's FK to `NULL` when the parent is deleted. (6) No; you must manually query for orphan rows. (7) Parent table first, child table second. (8) The parent could be deleted between the two steps; the FK enforces integrity at write time. (9) `SHOW ENGINE INNODB STATUS`. (10) Retention policy, audit requirements, data lifecycle, and the number of affected child rows.

## References

- [MySQL 8.4 Reference Manual: InnoDB and FOREIGN KEY Constraints](https://dev.mysql.com/doc/refman/8.4/en/innodb-foreign-key-constraints.html)
- [MySQL 8.4 Reference Manual: FOREIGN KEY Constraint Differences](https://dev.mysql.com/doc/refman/8.4/en/ansi-diff-foreign-keys.html)
- [MySQL 8.4 Reference Manual: INFORMATION_SCHEMA KEY_COLUMN_USAGE](https://dev.mysql.com/doc/refman/8.4/en/information-schema-key-column-usage-table.html)
- [MySQL 8.4 Reference Manual: INFORMATION_SCHEMA REFERENTIAL_CONSTRAINTS](https://dev.mysql.com/doc/refman/8.4/en/information-schema-referential-constraints-table.html)
- [MySQL 8.4 Reference Manual: InnoDB Standard Monitor and Lock Monitor](https://dev.mysql.com/doc/refman/8.4/en/innodb-standard-monitor.html)
