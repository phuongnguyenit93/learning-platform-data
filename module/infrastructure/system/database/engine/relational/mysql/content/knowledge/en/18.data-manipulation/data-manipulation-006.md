# Single-Table UPDATE and Multi-Table Updates

`UPDATE` modifies the column values of existing rows. In MySQL, you can update a single table based on its own conditions, use data from related tables to update one target table, or update multiple tables in a single statement. Choosing the right form of `UPDATE` keeps statements controllable, prevents unintended row modifications, and clarifies syntax limitations.

## Objectives

After this lesson, you will be able to:

- Write single-table `UPDATE` statements with expressions, conditions, and default values.
- Use `ORDER BY` and `LIMIT` to control order or chunk single-table updates.
- Use `UPDATE ... JOIN` to pull data from related tables and update one or multiple tables.
- Recognize the limitations of multi-table update syntax, especially regarding `ORDER BY`, `LIMIT`, foreign key relationships, and joins producing duplicate key matches.
- Preview the affected scope and verify results before finalizing changes.

Examples use modern MySQL syntax and assume the tables already exist with the columns shown.

## 1. Updating a Single Table

### Syntax

```sql
UPDATE [LOW_PRIORITY] [IGNORE] table_name
SET column_1 = expression_1,
    column_2 = expression_2,
    ...
[WHERE condition]
[ORDER BY expression [ASC | DESC], ...]
[LIMIT row_count];
```

`SET` specifies which columns to change and their new values. Each assignment can use literals, arithmetic expressions, functions, conditional expressions, or the `DEFAULT` keyword. `WHERE` filters the rows to update. If `WHERE` is omitted, every row in the table is within the update scope.

Example raising salaries by 8% for active employees in department 12:

```sql
UPDATE employees
SET salary = ROUND(salary * 1.08, 2),
    updated_at = CURRENT_TIMESTAMP
WHERE department_id = 12
  AND status = 'ACTIVE';
```

Expressions in `SET` are evaluated using the column values of the row being updated. Thus, `salary = salary * 1.08` does not require querying the salary first and splicing it into the statement.

### Updating with Precise Conditions

When updating a record by primary key, the condition is typically very clear:

```sql
UPDATE customers
SET email = 'lan.nguyen@example.com',
    updated_at = CURRENT_TIMESTAMP
WHERE customer_id = 105;
```

Conditions can combine multiple columns, ranges, and statuses:

```sql
UPDATE subscriptions
SET status = 'EXPIRED'
WHERE status = 'ACTIVE'
  AND expires_at < CURRENT_DATE;
```

For nullable columns, use `IS NULL` or `IS NOT NULL`; comparing with `= NULL` does not produce the intended match:

```sql
UPDATE customers
SET phone_verified = 0
WHERE phone_number IS NULL;
```

### Assigning Default Values and Conditional Updates

`DEFAULT` instructs MySQL to assign the column's declared default value:

```sql
UPDATE products
SET status = DEFAULT
WHERE product_id = 230;
```

You can use `CASE` to choose a new value per row:

```sql
UPDATE inventory
SET stock_status = CASE
        WHEN quantity = 0 THEN 'OUT_OF_STOCK'
        WHEN quantity <= reorder_level THEN 'LOW_STOCK'
        ELSE 'AVAILABLE'
    END,
    checked_at = CURRENT_TIMESTAMP
WHERE warehouse_id = 7;
```

Multiple columns in the same statement can be updated together. However, in single-table update syntax, MySQL generally evaluates `SET` assignments from left to right. If a later assignment needs a column's old value, assign the dependent column first:

```sql
UPDATE counters
SET previous_value = current_value,
    current_value = current_value + 1
WHERE counter_id = 1;
```

In this example, `previous_value` receives `current_value` before it is incremented. If you reverse the order of the two assignments, the second assignment could read the already-updated value. Do not rely on this assignment-order rule when switching to multi-table update syntax; assignment evaluation order is not guaranteed in that case.

### `ORDER BY` and `LIMIT`

In single-table update syntax, `ORDER BY` determines the processing order of rows and `LIMIT` caps the number of matching rows considered:

```sql
UPDATE task_queue
SET state = 'PROCESSING',
    claimed_at = CURRENT_TIMESTAMP
WHERE state = 'READY'
ORDER BY priority DESC, task_id ASC
LIMIT 20;
```

Include a unique tie-breaker column, such as the primary key, at the end of `ORDER BY` so ordering stays deterministic when multiple rows share the same priority. `LIMIT` caps the number of rows matched by `WHERE`; the number of rows actually changed may be lower if some rows already hold the assigned values.

A common pattern is splitting a large update task into multiple batches:

```sql
UPDATE event_log
SET archived = 1
WHERE archived = 0
  AND created_at < '2025-01-01'
ORDER BY event_id
LIMIT 500;
```

The application or operational job can repeat the statement in batches, inspect the changed row count, and stop when no matching rows remain. The condition must ensure processed rows leave the target set; otherwise, subsequent runs may keep hitting the same rows.

`ORDER BY` and `LIMIT` do not apply to the multi-table update syntax covered in the next section.

### `LOW_PRIORITY` and `IGNORE`

- `LOW_PRIORITY` delays the statement until no other sessions are reading from the table on storage engines that use table-level locks. This option provides no similar benefit for InnoDB, which uses row-level locks for most update operations.
- `IGNORE` instructs MySQL to continue through certain data errors or key conflicts, potentially skipping conflicting rows and emitting warnings. The result may be that only a subset of rows is updated. After using this option, inspect the row count and run `SHOW WARNINGS`; do not use it merely to hide data errors.

## 2. Using Related Tables to Update One Table

`UPDATE` can combine tables using `JOIN`. Lookup tables can supply values or filtering conditions while only one target table is modified.

Example syncing the default discount rate from customers to their pending orders:

```sql
UPDATE orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
SET o.discount_rate = c.default_discount,
    o.updated_at = CURRENT_TIMESTAMP
WHERE o.status = 'PENDING'
  AND c.active = 1;
```

In this statement, `customers` participates only in the join and supplies `default_discount`; all assigned columns belong to `orders`. The statement uses multi-table `UPDATE` syntax because `table_references` contains a join. Consequently, single-table `ORDER BY` or `LIMIT` clauses cannot be added to this example.

The join condition must reflect the true relationship between the two tables. If each order belongs to only one customer, `customers.customer_id` should be a primary key or have a `UNIQUE` constraint. If the join produces multiple source rows for the same order, do not rely on an arbitrary source row to supply the update value. Ensure the join key is unique or normalize source data to one row per target key before updating.

## 3. Updating Multiple Tables in a Single Statement

### Syntax

```sql
UPDATE [LOW_PRIORITY] [IGNORE] table_references
SET table_1.col_a = expr_a,
    table_2.col_b = expr_b,
    ...
[WHERE condition];
```

In `table_references`, list the tables and join relationships. In `SET`, explicitly qualify the columns belonging to each table to update. A single statement can update columns in one or more tables in the list; tables used solely for lookup are not modified automatically.

Example updating product prices and the restock flag for warehouse 7:

```sql
UPDATE products AS p
JOIN inventory AS i
  ON i.product_id = p.product_id
 AND i.warehouse_id = 7
SET p.price = ROUND(p.price * 1.05, 2),
    i.restock_required = CASE
        WHEN i.quantity < i.reorder_level THEN 1
        ELSE 0
    END
WHERE p.active = 1;
```

Both `products` and `inventory` have columns updated. The condition `warehouse_id = 7` is placed in the join condition to match only inventory records for the target warehouse. Schema design should guarantee each `(product_id, warehouse_id)` pair identifies at most one inventory row, typically via a `UNIQUE` constraint. When the join relationship is unique, each product pairs with a single inventory row for that warehouse and results are predictable.

### Limitations to Keep in Mind

**No `ORDER BY` or `LIMIT`.** Multi-table update syntax does not support these two clauses. If you need to chunk the workload, determine the set of keys to process first, then update key batches in a business-appropriate manner; do not add `LIMIT` directly to an `UPDATE ... JOIN` statement.

**Each target row is updated at most once.** If a join produces multiple matches pointing to the same row of a target table, MySQL still updates that row only once. Therefore, when multiple source rows match the same target row, do not assume a particular source row will be picked to supply the value. Make the join relationship unique or aggregate/select source data explicitly before updating.

**No guarantee on assignment evaluation order.** In multi-table updates, do not rely on the order of assignments in `SET` to pass new values between columns. Write each expression so its result does not depend on evaluation order, or split into explicitly ordered statements inside the same transaction.

**Watch InnoDB foreign keys.** When foreign keys exist between tables, the internal processing order chosen by the optimizer may differ from the parent-child hierarchy order. A multi-table update statement can fail and roll back if that order violates a constraint. When changing referenced keys, configure `ON UPDATE` appropriately if the business requires cascading changes; otherwise, updating tables one by one in a controlled order inside a transaction is usually easier to reason about.

**Consider triggers and side effects.** `UPDATE` triggers on every modified table can fire. If triggers log history, adjust balances, or modify related data, account for those effects when predicting the outcome of a multi-table update statement.

## 4. Checking Before and After Updating

A syntactically valid statement can still select the wrong set of rows. Before running an important change, use the exact same conditions to preview the scope:

```sql
SELECT employee_id, department_id, salary, status
FROM employees
WHERE department_id = 12
  AND status = 'ACTIVE'
ORDER BY employee_id;
```

If the `UPDATE` statement uses `JOIN`, run a `SELECT` with the exact same join and conditions to inspect the target keys alongside expected source values. In particular, verify that each target key matches the exact number of source rows required by the design.

With InnoDB tables, you can wrap changes in a transaction to verify before confirming:

```sql
START TRANSACTION;

UPDATE employees
SET salary = ROUND(salary * 1.08, 2)
WHERE department_id = 12
  AND status = 'ACTIVE';

SELECT employee_id, salary
FROM employees
WHERE department_id = 12
  AND status = 'ACTIVE'
ORDER BY employee_id;

-- If the result is correct:
COMMIT;

-- If the result is incorrect, use ROLLBACK instead of COMMIT.
```

In an actual session, run only one of the two transaction-ending commands: `COMMIT` to persist changes or `ROLLBACK` to discard uncommitted changes. Transactions can only roll back changes on storage engines that support transactions, such as InnoDB.

After the statement, check the matched and changed row counts and warning count reported by the client. `ROW_COUNT()` returns affected rows per the current connection's rules; the `CLIENT_FOUND_ROWS` client option can change how row counts are reported. If `IGNORE` was used, run `SHOW WARNINGS` immediately after the statement to inspect issues downgraded to warnings.

## 5. Performance and Common Mistakes

`WHERE` and join conditions determine the scan range as well as which rows InnoDB must lock. Choose proper join keys, maintain appropriate indexes for frequently filtered columns, and avoid unintentionally broad update ranges. On large tables, batched updates reduce lock hold times and make progress observable; choose a batch size suited to system load.

| Issue | Common Cause | Resolution |
|---|---|---|
| Every row was modified | Omitted `WHERE` or overly broad condition | Run `SELECT` with the exact same condition before updating |
| Zero rows modified | Condition matched nothing, values already matched new values, or join found no rows | Verify conditions and joins using `SELECT` |
| Wrong values updated from related table | One target key matched multiple source rows | Ensure uniqueness or aggregate source data beforehand |
| Foreign key error | Update order conflicted with parent-child relationship | Review `ON UPDATE`, update order, and transactions |
| Multi-table statement syntax error with `LIMIT` | `LIMIT` is not supported in multi-table update syntax | Select key batches first and update accordingly |
| Warnings occurred yet statement ran | Used `IGNORE` or data conversion emitted warnings | Read `SHOW WARNINGS` and verify each case |

Never treat a successful `UPDATE` as sole proof that the business outcome is correct. Verify row counts, post-update values, and related side effects such as triggers or foreign key constraints.

## 6. Practice Exercises

Assume you have tables `employees(employee_id, department_id, salary, status, updated_at)`, `departments(department_id, bonus_rate)`, and `payroll_summary(department_id, total_salary, updated_at)`.

1. Increase salary by 5% for active employees in department 4. Also update `updated_at`.
2. Use `JOIN` to increase `employees.salary` by `departments.bonus_rate` via `department_id`. Update only active employees.
3. Use a single multi-table update statement to modify `departments.bonus_rate` and `payroll_summary.updated_at`, joining both tables on `department_id`. Assume `payroll_summary.department_id` is unique; target only departments that have at least one active employee.
4. Explain why `ORDER BY` and `LIMIT` cannot be added to the statement in exercise 3. Propose how to verify and chunk the work if the row count is very large.
5. Write `SELECT` queries to preview rows that will be modified and verify the results after updating.

## Key Takeaways

- Single-table `UPDATE` supports `WHERE`, `ORDER BY`, and `LIMIT`; omitting `WHERE` updates every row.
- `UPDATE ... JOIN` can update a single target table or multiple tables depending on which columns appear in `SET`.
- Multi-table update syntax does not support `ORDER BY` and `LIMIT`; each target row is updated once even if the join produces duplicate matches.
- Keep joins unique and do not rely on assignment evaluation order in multi-table updates.
- Preview scope with `SELECT`, verify results, and use InnoDB transactions when you need commit or rollback control.
