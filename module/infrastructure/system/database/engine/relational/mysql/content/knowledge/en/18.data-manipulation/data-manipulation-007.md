# Single-Table DELETE, Multi-Table DELETE, and Deleting Parent-Child Data

In MySQL, `DELETE` removes rows stored in a table. A statement can target a single table, use `JOIN` to identify rows to delete, or delete rows from multiple tables in one statement. When tables are linked by foreign keys, the outcome also depends on the `ON DELETE` rules declared in the parent-child relationship.

This lesson belongs to the **Data Manipulation** section of MySQL. After completing it, you will be able to choose the right `DELETE` syntax, predict side effects on related tables, inspect data before deleting, and use transactions to control high-risk operations.

## 1. Single-Table DELETE Syntax

Basic syntax:

```sql
DELETE FROM table_name
WHERE condition;
```

`WHERE` identifies which rows to delete. If `WHERE` is omitted, MySQL deletes every row in the table while keeping the table structure, columns, indexes, and constraints intact.

For example, deleting one employee by primary key:

```sql
DELETE FROM employees
WHERE employee_id = 105;
```

Deleting multiple employees by condition:

```sql
DELETE FROM employees
WHERE status = 'INACTIVE'
  AND hired_at < '2022-01-01';
```

Conditions in `WHERE` follow standard SQL expression rules. You can combine `AND`, `OR`, `IN`, `BETWEEN`, `LIKE`, date/time predicates, or subqueries. Use parentheses when combining `AND` and `OR` to make logical precedence explicit.

```sql
DELETE FROM employees
WHERE status = 'INACTIVE'
  AND (department_id = 10 OR department_id = 20);
```

### Previewing Rows That Will Be Deleted

Before running `DELETE`, execute a `SELECT` with the exact same condition. The result confirms the data scope and catches errors such as a missing condition, wrong key, or incorrect date threshold.

```sql
SELECT employee_id, full_name, status, hired_at
FROM employees
WHERE status = 'INACTIVE'
  AND hired_at < '2022-01-01'
ORDER BY hired_at, employee_id;
```

If you only need the expected row count, run `COUNT(*)` with the same condition:

```sql
SELECT COUNT(*) AS rows_to_delete
FROM employees
WHERE status = 'INACTIVE'
  AND hired_at < '2022-01-01';
```

Only after confirming the result should you run the corresponding `DELETE` statement. Never rely on the fact that an application screen shows only a few rows or has UI filters to assume the server-side deletion scope.

### ORDER BY and LIMIT for Batched Deletion

With single-table delete syntax, MySQL allows `ORDER BY` and `LIMIT`. This is useful when purging old data in batches to reduce lock hold times and undo log generation in a single run.

```sql
DELETE FROM api_requests
WHERE created_at < '2025-01-01'
ORDER BY created_at, request_id
LIMIT 1000;
```

This statement deletes at most 1,000 of the oldest matching rows. The secondary key `request_id` makes ordering deterministic when multiple rows share the same `created_at`. You can repeat it in batches until no matching rows remain; in operational scripts, inspect the row count per batch and commit in appropriate batch sizes.

`LIMIT` is no substitute for `WHERE`: if the condition is missing or wrong, the statement can still delete the wrong set of rows. When deleting large volumes, define explicit filter conditions and ensure suitable indexes exist on filter or sort columns.

## 2. DELETE with JOIN to Select Rows to Delete

Sometimes the deletion condition resides in another table. The `DELETE ... FROM ... JOIN` syntax lets you join tables to locate target rows. For instance, deleting only employees belonging to archived departments:

```sql
DELETE e
FROM employees AS e
JOIN departments AS d
  ON d.department_id = e.department_id
WHERE d.is_archived = 1;
```

`e` is the alias for `employees`; the `DELETE e` clause designates the table whose rows are deleted. The `departments` table participates in the join for filtering, but none of its rows are deleted. This uses multi-table syntax for target specification even though the target list contains only one table.

Preview that exact join with `SELECT`:

```sql
SELECT e.employee_id, e.full_name, d.department_name
FROM employees AS e
JOIN departments AS d
  ON d.department_id = e.department_id
WHERE d.is_archived = 1;
```

Another use case is deleting discontinued products that no longer appear in any order line items. Use `LEFT JOIN` to find products with no matching row in `order_items`:

```sql
DELETE p
FROM products AS p
LEFT JOIN order_items AS oi
  ON oi.product_id = p.product_id
WHERE oi.item_id IS NULL
  AND p.is_discontinued = 1;
```

The condition `oi.item_id IS NULL` selects products that have no related records. The statement deletes only from `products`; `order_items` is used solely to identify eligible products.

When using `JOIN`, double-check the join condition. A missing join condition or joining on the wrong key can expand the target set unexpectedly. If one table has multiple rows matching a single row in the other table, inspect the `SELECT` output before deleting to understand the full impact.

## 3. Deleting Data Across Multiple Tables in One Statement

MySQL supports multi-table `DELETE`, where the alias list right after `DELETE` specifies which tables will have rows deleted. The example below deletes closed accounts along with their old login sessions:

```sql
DELETE u, s
FROM users AS u
JOIN sessions AS s
  ON s.user_id = u.user_id
WHERE u.account_status = 'CLOSED'
  AND s.last_seen_at < '2025-01-01';
```

In this example, matching rows in both `users` and `sessions` are targeted for deletion. If you wrote only `DELETE s`, MySQL would delete only from `sessions`, leaving `users` intact. Multi-table syntax also has a `DELETE FROM ... USING ...` form, though `DELETE alias_list FROM ... JOIN ...` is usually easier to read when explicitly naming target tables.

Key points to remember:

- Multi-table `DELETE` does not support `ORDER BY` or `LIMIT`. If you need to chunk the data, determine batches of keys to delete first and perform appropriate operations per batch.
- The list after `DELETE` must contain the exact aliases of the tables you intend to delete from. Tables appearing only in `FROM` or `JOIN` are not deleted automatically.
- The example above assumes the relationship between the two tables allows simultaneous deletion. If foreign keys constrain deletion order, design the operation around foreign key rules; in InnoDB, the order chosen by the optimizer for a multi-table `DELETE` can conflict with parent-child order, causing the statement to fail and roll back.

When foreign keys exist, it is usually better to rely on `ON DELETE CASCADE` where business rules allow, or delete child tables before parent tables inside a single transaction. The next section explains how to choose between these approaches.

## 4. Deleting Parent-Child Data with Foreign Keys

Suppose an e-commerce system has three tables: `customers` as the parent table, `orders` as a child of `customers`, and `order_items` as a child of `orders`. The relationships are declared with foreign keys in InnoDB:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    KEY ix_orders_customer_id (customer_id),
    CONSTRAINT fk_orders_customer
      FOREIGN KEY (customer_id)
      REFERENCES customers (customer_id)
      ON DELETE CASCADE
) ENGINE = InnoDB;

CREATE TABLE order_items (
    item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    product_name VARCHAR(120) NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    PRIMARY KEY (item_id),
    KEY ix_order_items_order_id (order_id),
    CONSTRAINT fk_items_order
      FOREIGN KEY (order_id)
      REFERENCES orders (order_id)
      ON DELETE CASCADE
) ENGINE = InnoDB;
```

With both foreign keys using `ON DELETE CASCADE`, deleting a customer cascades to that customer's orders, and deleting each order cascades to that order's line items:

```sql
DELETE FROM customers
WHERE customer_id = 42;
```

MySQL executes the cascading actions along the declared relationship chain. You do not need to write separate `DELETE` statements for `orders` and `order_items`. This mechanism fits when child data has no independent meaning once the parent is removed, such as line items of an order purged under a retention policy.

### ON DELETE Options

The `ON DELETE` rule dictates what happens to child rows when a parent row is deleted:

| Rule | Behavior |
| --- | --- |
| `RESTRICT` | Rejects deleting the parent row if referencing child rows still exist. This is the default behavior when no delete rule is specified in InnoDB. |
| `NO ACTION` | In InnoDB, behaves identically to `RESTRICT`. |
| `CASCADE` | Automatically deletes referencing child rows; the action can propagate through multi-level child relationships. |
| `SET NULL` | Sets the foreign key column in child rows to `NULL`; that column must allow `NULL`. |

Choose `CASCADE` based on business requirements, not merely to shorten SQL statements. A single delete on a parent table can erase huge numbers of rows across many tables. For data that must be retained for auditing, reconciliation, or retention periods, keep the records, transition their status, or archive them instead of cascading deletes.

### When Foreign Keys Use RESTRICT

If foreign keys disallow cascading, MySQL rejects deleting the parent row while referencing child rows remain. In that case, delete in order from the deepest child table up to the parent table. For example, with `order_items` → `orders` → `customers` using `RESTRICT`:

```sql
START TRANSACTION;

DELETE oi
FROM order_items AS oi
JOIN orders AS o
  ON o.order_id = oi.order_id
WHERE o.customer_id = 42;

DELETE FROM orders
WHERE customer_id = 42;

DELETE FROM customers
WHERE customer_id = 42;

COMMIT;
```

The first statement deletes the order line items, the second deletes orders that no longer have child rows, and the final statement deletes the customer. If any step errors or verification fails, run `ROLLBACK` instead of `COMMIT` to undo changes in the transaction. This sequence also makes it explicit to readers exactly what data is deleted at each level.

Do not disable `FOREIGN_KEY_CHECKS` just to force deleting parent data. Disabling foreign key checks does not trigger cascades; doing so can leave orphaned child rows behind. When re-enabling checks, MySQL does not automatically scan and revalidate all existing rows to fix violated relationships.

## 5. Using Transactions to Control Deletion

For InnoDB tables, `DELETE` can be rolled back when executed inside a transaction. This allows verifying scope and results before confirming:

```sql
START TRANSACTION;

DELETE FROM employees
WHERE status = 'INACTIVE'
  AND hired_at < '2022-01-01';

SELECT COUNT(*) AS remaining_rows
FROM employees
WHERE status = 'INACTIVE'
  AND hired_at < '2022-01-01';

-- If the result is correct:
COMMIT;

-- If an accidental deletion is detected, use ROLLBACK instead of COMMIT.
```

In real workflows, run the preview `SELECT` right after `START TRANSACTION` and before `DELETE`; the `SELECT` after `DELETE` verifies remaining matching rows. Only `COMMIT` when results match expectations. If autocommit is enabled and no explicit transaction is started, each statement normally commits immediately, making `ROLLBACK` impossible once `DELETE` has finished.

Transactions do not replace backups or approval workflows for critical data deletions. They also guarantee rollback only on storage engines that support transactions, such as InnoDB. Verify the engine of target tables before relying on rollback capability.

## 6. Performance and Operations When Deleting Large Datasets

A large `DELETE` can hold locks for a long time, generate heavy undo logs, increase I/O load, and impact concurrent transactions. When purging historical data, consider these points:

1. **Filter with intentional predicates.** Use primary keys, date ranges, or verified statuses; avoid unintended full-table scans and deletes.
2. **Index filter and join columns.** Indexes on filter and join columns help MySQL locate target rows efficiently. InnoDB requires suitable indexes for foreign keys and automatically creates one on the child side if none exists.
3. **Batch large deletions.** With single-table `DELETE`, combine `ORDER BY` and `LIMIT`, verifying and committing each batch. Size batches according to live workload and lock duration.
4. **Track dependent relationships.** Check foreign keys, cascades, and tables with triggers before deleting. A single delete on a parent table can trigger many indirect modifications.
5. **Verify environment and recovery options.** Confirm server, schema, filter conditions, and backups before running operations affecting critical data.

Do not use `LIMIT` arbitrarily as a substitute for a batched deletion plan. Without `ORDER BY`, the subset of rows deleted in each run may not follow the intended business order. For multi-table `DELETE`, because `ORDER BY` and `LIMIT` are unavailable, design a separate target-key selection step if batch control is needed.

## 7. Comparing DELETE, TRUNCATE, and DROP

All three commands can appear in data-cleanup workflows, but their effects differ:

| Command | Effect | Key Notes |
| --- | --- | --- |
| `DELETE FROM t WHERE ...` | Deletes rows matching the condition; without `WHERE`, deletes all rows. | DML; in InnoDB can be rolled back in a transaction; fires `DELETE` triggers; does not reset the `AUTO_INCREMENT` counter. |
| `TRUNCATE TABLE t` | Deletes all data in the table. | Has no `WHERE`; DDL causing an implicit commit; resets `AUTO_INCREMENT`; does not fire `DELETE` triggers; cannot truncate a table referenced by another table's foreign key. |
| `DROP TABLE t` | Deletes both the table and its structure. | Columns, indexes, and table definition are removed; not an option for deleting data only. |

When you need conditional deletion, transaction control, or row-by-row parent-child handling, use `DELETE`. Consider `TRUNCATE` only when the explicit goal is emptying an entire table and related constraints have been verified.

## 8. Safe Operational Workflow

Before running a deletion in a shared or production environment, apply the following sequence:

1. Confirm the exact server, database, and target table.
2. Write the complete `WHERE` condition or `JOIN`; do not execute the delete statement first.
3. Convert that exact condition into a `SELECT` to inspect keys and affected row counts.
4. Check foreign keys, `ON DELETE` actions, triggers, and related tables.
5. Start a transaction if the engine supports it; execute the delete, verify the outcome, and only then `COMMIT`.
6. For large datasets, delete in batches while monitoring system load; ensure an appropriate recovery plan is ready.

Common mistakes include omitting `WHERE`, joining on the wrong key, assuming multi-table `DELETE` automatically deletes from every table in the join, deleting parent rows before handling children under `RESTRICT`, or disabling foreign key checks to bypass errors. When encountering a constraint error, read the constraint name in the error message and inspect referencing child rows before deciding to change deletion policies.

`DELETE` is a powerful tool for managing data lifecycle. A sound statement accurately targets the intended rows, respects foreign key relationships, and pairs with verification or recovery measures proportional to the criticality of the data.
