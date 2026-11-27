# Single-Table UPDATE, Multi-Column UPDATE, and Subquery UPDATE in Oracle

## 1. What Is UPDATE Used For?

`UPDATE` modifies the values of one or more columns on existing rows in a table. You can update to a fixed value, compute a new value from the row's current data, or fetch data from a subquery.

For example, increasing salaries by 5% for employees in department 10:

```sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 10;
```

Example of updating salary and modification timestamp simultaneously:

```sql
UPDATE employees
SET salary = salary * 1.05,
    updated_at = SYSTIMESTAMP
WHERE department_id = 10;
```

Example of retrieving new salaries from an adjustment table:

```sql
UPDATE employees e
SET salary = (
    SELECT a.new_salary
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
)
WHERE EXISTS (
    SELECT 1
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
);
```

`UPDATE` is a DML (Data Manipulation Language) statement. It modifies data within the current transaction; changes are only made permanent when the transaction is committed with `COMMIT`, or discarded with `ROLLBACK`.

This lesson belongs to the **Data Manipulation** chapter and focuses on single-table updates, multi-column updates in one statement, and updates from subqueries. Key topics include `SET` syntax, `WHERE` conditions, scalar subqueries, multi-column assignment subqueries, correlated subqueries, handling zero or multiple source rows, verifying results, and managing transactions.

## 2. Basic UPDATE Syntax

Common syntax pattern:

```sql
UPDATE table_name
SET column_name = expression
    [, column_name = expression ...]
[WHERE condition];
```

Where:

- `table_name`: the target table to modify.
- `SET`: declares the columns and new values.
- `expression`: a literal, calculation, function, `CASE` expression, or compatible subquery.
- `WHERE`: determines which rows are updated.

Example:

```sql
UPDATE products
SET unit_price = 125000
WHERE product_id = 1001;
```

This statement replaces `UNIT_PRICE` of the product with ID 1001 with 125000. Other rows are unaffected.

### 2.1. UPDATE Without WHERE

```sql
UPDATE products
SET discontinued_flag = 'N';
```

Without `WHERE`, **every row** in the `PRODUCTS` table is updated. This can be intentional when normalizing an entire dataset, but it is also a dangerous bug if the author forgot the condition.

Before running an UPDATE on live data, run a SELECT with the same condition:

```sql
SELECT product_id, unit_price
FROM products
WHERE product_id = 1001;
```

Only after confirming the exact target row set should you run the corresponding UPDATE.

### 2.2. WHERE Can Use Standard Conditions

```sql
UPDATE employees
SET commission_pct = 0.10
WHERE department_id = 20
  AND commission_pct IS NULL;
```

Filter conditions can combine `AND`, `OR`, `IN`, `BETWEEN`, `EXISTS`, subqueries, and NULL checks. If a column is nullable, use `IS NULL`/`IS NOT NULL`; comparing with `= NULL` will not match NULL rows.

### 2.3. WHERE Specifies Target Rows, Not Source Values

Distinguish the two parts:

```sql
UPDATE employees e
SET salary = salary * 1.05             -- New value
WHERE department_id = 10;             -- Target rows
```

When using a subquery:

```sql
UPDATE employees e
SET salary = (
    SELECT a.new_salary
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
)
WHERE e.department_id = 10;
```

`WHERE e.department_id = 10` restricts which employees are updated. The condition inside the subquery determines the corresponding new value for each employee.

## 3. Updating a Single Column

### 3.1. Assigning a Fixed Value

```sql
UPDATE customers
SET status = 'ACTIVE'
WHERE customer_id = 501;
```

### 3.2. Computing from the Current Value

```sql
UPDATE inventory
SET quantity = quantity - 3
WHERE product_id = 2001;
```

Oracle computes the expression from the current value of the row being updated. Add a business condition if negative quantities are not allowed:

```sql
UPDATE inventory
SET quantity = quantity - 3
WHERE product_id = 2001
  AND quantity >= 3;
```

After the UPDATE, the application should check the affected row count. If zero rows were updated, either the product does not exist or stock is insufficient.

### 3.3. Using CASE for Conditional Updates

```sql
UPDATE employees
SET salary = CASE
                 WHEN performance_score >= 90 THEN salary * 1.10
                 WHEN performance_score >= 75 THEN salary * 1.05
                 ELSE salary
             END
WHERE review_year = 2026;
```

`CASE` computes the new value for each row. Rows not matching the first branch are checked against subsequent branches; `ELSE salary` preserves the current salary for remaining cases.

Without `ELSE`, a CASE expression returns NULL when no branch matches. This can unexpectedly set the column to NULL.

### 3.4. Setting a Column to NULL or DEFAULT

```sql
UPDATE customers
SET secondary_phone = NULL
WHERE customer_id = 501;
```

Valid only if the column allows NULL and related constraints remain satisfied.

If you want to use the column's declared default value:

```sql
UPDATE orders
SET priority_code = DEFAULT
WHERE order_id = 9001;
```

`DEFAULT` uses the default defined for the column. If the column has no default, behavior must be verified against the schema definition and Oracle version in use; do not treat DEFAULT as a way to auto-generate an arbitrary business value.

## 4. Updating Multiple Columns in One UPDATE

When a business operation modifies multiple attributes of the same row, you can list multiple assignments in a single `SET` clause.

### 4.1. Per-Column Assignment Syntax

```sql
UPDATE employees
SET salary = salary * 1.05,
    commission_pct = 0.12,
    updated_at = SYSTIMESTAMP
WHERE employee_id = 100;
```

Three columns are updated in the same statement:

- `SALARY` increases by 5%.
- `COMMISSION_PCT` is set to 0.12.
- `UPDATED_AT` receives the current system timestamp.

### 4.2. Column Expressions Are Independent

```sql
UPDATE products
SET unit_price = unit_price * 1.08,
    tax_amount = unit_price * 0.08,
    updated_at = SYSDATE
WHERE category_id = 30;
```

In an UPDATE statement, right-hand expressions are evaluated from the row's values before the update; do not rely on listing order to make a later column read the new value of an earlier column. In the example above, `TAX_AMOUNT` is computed from the old `UNIT_PRICE`.

If you want to calculate tax based on the new price, write the full expression:

```sql
UPDATE products
SET unit_price = unit_price * 1.08,
    tax_amount = unit_price * 1.08 * 0.08
WHERE category_id = 30;
```

Or compute the new price in a clearly structured expression. Do not chain multiple UPDATEs when a single statement can express all changes to the same row.

### 4.3. Updating Multiple Columns with Different Conditions

```sql
UPDATE customer_profiles
SET phone_verified = CASE
                         WHEN phone_number IS NOT NULL THEN 'Y'
                         ELSE 'N'
                     END,
    email_verified = CASE
                         WHEN email_address IS NOT NULL THEN 'Y'
                         ELSE 'N'
                     END,
    updated_at = SYSTIMESTAMP
WHERE profile_status = 'PENDING';
```

Each column has its own expression, yet all apply to the row set selected by `WHERE`.

## 5. Assigning Multiple Columns from a Subquery

Oracle allows assigning a column list from a subquery that returns corresponding expressions:

```sql
UPDATE target_table t
SET (column_a, column_b) = (
    SELECT source_a, source_b
    FROM source_table s
    WHERE s.key_id = t.key_id
)
WHERE ...;
```

Key requirements:

1. The number of expressions in the SELECT list must equal the number of columns on the left-hand side.
2. Expression order must match column order exactly.
3. The subquery for a target row must return at most one row.
4. Each expression's data type must be assignable to its target column.

### 5.1. Example: Updating Address and Postal Code

Suppose `customers` needs normalized addresses from `customer_address_updates`:

```sql
UPDATE customers c
SET (address_line, postal_code) = (
    SELECT u.address_line,
           u.postal_code
    FROM customer_address_updates u
    WHERE u.customer_id = c.customer_id
)
WHERE EXISTS (
    SELECT 1
    FROM customer_address_updates u
    WHERE u.customer_id = c.customer_id
);
```

For each customer with an update record, Oracle retrieves both values from the same source row and assigns them in order:

- `u.address_line` to `c.address_line`.
- `u.postal_code` to `c.postal_code`.

`WHERE EXISTS` ensures only customers with source data are updated. Without this condition, customers with no row in `CUSTOMER_ADDRESS_UPDATES` would still be updated and both target columns would be set to NULL.

### 5.2. Source and Target Columns Are Matched by Position

Example:

```sql
SET (first_name, last_name) = (
    SELECT s.last_name,
           s.first_name
    FROM staging_names s
    WHERE s.employee_id = e.employee_id
)
```

The column count matches, but the order is semantically wrong: source `LAST_NAME` gets assigned to `FIRST_NAME`. Oracle does not match automatically by alias name. Check each position:

| Position | Target column | Source expression |
|---:|---|---|
| 1 | `FIRST_NAME` | `S.FIRST_NAME` |
| 2 | `LAST_NAME` | `S.LAST_NAME` |

### 5.3. Updating Multiple Columns with Calculated Values

```sql
UPDATE products p
SET (unit_price, updated_at) = (
    SELECT ROUND(s.proposed_price, 2),
           SYSTIMESTAMP
    FROM price_staging s
    WHERE s.product_id = p.product_id
)
WHERE EXISTS (
    SELECT 1
    FROM price_staging s
    WHERE s.product_id = p.product_id
);
```

This example assumes `PRICE_STAGING` has at most one row per `PRODUCT_ID`. If there are multiple source rows for the same product, the subquery will raise a multi-row error.

### 5.4. One Subquery for Multiple Columns Pulls Data from the Same Source Row

If `FIRST_NAME`, `LAST_NAME`, and `EMAIL` must come from the same staging record, assign them as a tuple:

```sql
UPDATE employees e
SET (first_name, last_name, email) = (
    SELECT s.first_name,
           s.last_name,
           s.email
    FROM employee_staging s
    WHERE s.employee_id = e.employee_id
)
WHERE EXISTS (
    SELECT 1
    FROM employee_staging s
    WHERE s.employee_id = e.employee_id
);
```

This syntax guarantees values come from the same source row. If split into three separate scalar subqueries, each query must maintain consistent filtering and row-selection rules; if source data changes between steps, grouping into one UPDATE also keeps the operation consistent within a single statement.

## 6. Scalar Subqueries in the SET Clause

A scalar subquery is a subquery used as a single-value expression. In `SET`, it can fetch one value from another table:

```sql
UPDATE employees e
SET salary = (
    SELECT a.new_salary
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
)
WHERE e.employee_id = 100;
```

The subquery must return at most one row for each target row updated.

### 6.1. Subquery Returns Exactly One Row

If one adjustment row is found for employee 100, `SALARY` receives `NEW_SALARY`.

### 6.2. Subquery Returns Zero Rows

A scalar subquery returning no rows evaluates to NULL. Therefore:

```sql
UPDATE employees e
SET salary = (
    SELECT a.new_salary
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
);
```

If an employee has no adjustment row, that employee's `SALARY` will be set to NULL. If the column is NOT NULL, the statement fails due to the constraint. This is a common cause of multi-row UPDATEs accidentally wiping existing values on rows without source matches.

### 6.3. Subquery Returns More Than One Row

If there are two adjustment rows for the same employee, the scalar subquery does not know which row to pick and Oracle reports:

```text
ORA-01427: single-row subquery returns more than one row
```

Do not fix this by arbitrarily adding `ROWNUM = 1`. First determine why the source has multiple rows and what business rule selects the winning record.

### 6.4. Guarding UPDATE with EXISTS

Common pattern:

```sql
UPDATE employees e
SET salary = (
    SELECT a.new_salary
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
)
WHERE EXISTS (
    SELECT 1
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
);
```

`EXISTS` excludes target rows that have no source record. It does not solve the case of multiple source rows; source data uniqueness must still be guaranteed.

## 7. UPDATE with Correlated Subqueries

A correlated subquery references columns of the row currently being updated. Oracle evaluates the expression in the context of the target row.

### 7.1. Fetching a Value from Another Table

```sql
UPDATE employees e
SET department_id = (
    SELECT m.new_department_id
    FROM employee_department_map m
    WHERE m.employee_id = e.employee_id
)
WHERE EXISTS (
    SELECT 1
    FROM employee_department_map m
    WHERE m.employee_id = e.employee_id
);
```

`e.employee_id` is the value of the row being updated. The subquery finds the corresponding mapping for that row.

### 7.2. Updating with an Aggregated Value from a Child Table

Example of updating each customer's total spend:

```sql
UPDATE customers c
SET total_spent = (
    SELECT SUM(o.total_amount)
    FROM orders o
    WHERE o.customer_id = c.customer_id
)
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
```

A `SUM` subquery without `GROUP BY` returns one aggregate row. If there are no orders, `SUM` is NULL. The EXISTS condition avoids updating customers who have no orders yet.

If business rules define customers without orders as having total spend 0 and you want to update those customers too:

```sql
UPDATE customers c
SET total_spent = NVL((
    SELECT SUM(o.total_amount)
    FROM orders o
    WHERE o.customer_id = c.customer_id
), 0);
```

Here there is no WHERE, so every customer is updated; customers without orders receive 0. Only use this when it is an agreed business rule.

### 7.3. Updating from the Latest Value in a History Table

```sql
UPDATE customer_profiles p
SET last_order_date = (
    SELECT MAX(o.order_date)
    FROM orders o
    WHERE o.customer_id = p.customer_id
)
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = p.customer_id
);
```

`MAX` returns one row and the largest date value. This is straightforward if only one aggregate value is needed. If you need multiple columns from the same latest order, use a subquery with deterministic row selection rules or consider `MERGE`/an appropriate inline view.

### 7.4. Updating from the Same Table

The subquery can read the target table itself to compute new values:

```sql
UPDATE employees e
SET salary = (
    SELECT ROUND(AVG(e2.salary), 2)
    FROM employees e2
    WHERE e2.department_id = e.department_id
)
WHERE e.department_id = 10;
```

This example sets each department 10 employee's salary to the department average as read by the subquery. This is only a technical example; in practice, consider whether replacing every individual salary with the department average makes business sense.

## 8. When There Is No Source Row: Keep Old Value, Set NULL, or Set Default?

This is the most important decision when updating from a subquery.

Suppose the target table has:

| employee_id | current salary |
|---:|---:|
| 101 | 10000 |
| 102 | 12000 |
| 103 | 15000 |

The source table only has adjustments for employees 101 and 102.

### 8.1. Only Update Rows That Have Source Data

```sql
UPDATE employees e
SET salary = (
    SELECT a.new_salary
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
)
WHERE EXISTS (
    SELECT 1
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
);
```

Employee 103 has no source record and is left unchanged.

### 8.2. Update All Rows, Setting NULL When No Source Exists

```sql
UPDATE employees e
SET salary = (
    SELECT a.new_salary
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
);
```

Employee 103 will receive NULL from the empty scalar subquery. Use only when the requirement truly is to clear old values on rows lacking source records.

### 8.3. Update All Rows, Keeping Old Value When No Source Exists

You can use `NVL` if NULL only happens when there is no match or the source returns NULL:

```sql
UPDATE employees e
SET salary = NVL((
    SELECT a.new_salary
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
), e.salary);
```

However, this merges two distinct situations:

1. No source row exists.
2. A source row exists, but `NEW_SALARY` is NULL.

If those two situations have different meanings, use `EXISTS` or check the source column explicitly:

```sql
UPDATE employees e
SET salary = CASE
    WHEN EXISTS (
        SELECT 1
        FROM salary_adjustments a
        WHERE a.employee_id = e.employee_id
          AND a.new_salary IS NOT NULL
    )
    THEN (
        SELECT a.new_salary
        FROM salary_adjustments a
        WHERE a.employee_id = e.employee_id
          AND a.new_salary IS NOT NULL
    )
    ELSE e.salary
END;
```

This example keeps the old salary if no non-NULL new salary exists. Ensure the subquery still returns at most one row.

### 8.4. Using CASE to Express Policy Clearly

```sql
UPDATE employees e
SET salary = CASE
    WHEN EXISTS (
        SELECT 1
        FROM salary_adjustments a
        WHERE a.employee_id = e.employee_id
    )
    THEN (
        SELECT a.new_salary
        FROM salary_adjustments a
        WHERE a.employee_id = e.employee_id
    )
    ELSE e.salary
END;
```

The EXISTS condition checks whether a source row exists; the THEN branch fetches the value. If a source row exists with NULL `NEW_SALARY`, the target value is also set to NULL. Whether this policy is right or wrong depends on the business rules.

## 9. Controlling Source Data with Multiple Rows

A subquery assigning a value to a target row must produce a single value. Before running UPDATE, check the source keys:

```sql
SELECT employee_id,
       COUNT(*) AS source_count
FROM salary_adjustments
GROUP BY employee_id
HAVING COUNT(*) > 1;
```

If the query returns rows, there are multiple source records for one employee. You must decide:

- Duplicate data is an error and must be fixed at the source.
- Only select records with an approved status.
- Select the record with the latest effective timestamp.
- Aggregate source rows according to a business rule.

### 9.1. Selecting the Latest Record with ROW_NUMBER

If the source table holds multiple versions and the rule is to pick the latest record:

```sql
UPDATE employees e
SET salary = (
    SELECT new_salary
    FROM (
        SELECT a.new_salary,
               ROW_NUMBER() OVER (
                   PARTITION BY a.employee_id
                   ORDER BY a.effective_at DESC, a.adjustment_id DESC
               ) AS rn
        FROM salary_adjustments a
        WHERE a.employee_id = e.employee_id
    )
    WHERE rn = 1
)
WHERE EXISTS (
    SELECT 1
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
);
```

`adjustment_id` acts as a tie-breaker so row selection is deterministic if multiple adjustments share the same `EFFECTIVE_AT`. The subquery in SET still returns at most one row.

Where possible, enforce uniqueness with an appropriate constraint rather than relying solely on query logic. Selecting the "latest" must have a clear definition of effective time and valid status.

### 9.2. Aggregating the Source Before Updating

If the requirement is to sum order revenue:

```sql
UPDATE customers c
SET total_spent = (
    SELECT SUM(o.total_amount)
    FROM orders o
    WHERE o.customer_id = c.customer_id
)
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
```

An aggregate without GROUP BY returns one row, so `SUM` is a scalar value. If multiple metrics are needed, assign a tuple:

```sql
UPDATE customers c
SET (total_spent, order_count) = (
    SELECT SUM(o.total_amount),
           COUNT(*)
    FROM orders o
    WHERE o.customer_id = c.customer_id
)
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
```

The aggregate subquery returns one row for each processed customer. `WHERE EXISTS` in the example limits the update to customers with at least one order.

## 10. UPDATE from Subqueries with Complex Conditions

### 10.1. Only Update When Source Value Differs from Current Value

```sql
UPDATE products p
SET unit_price = (
    SELECT s.proposed_price
    FROM price_staging s
    WHERE s.product_id = p.product_id
)
WHERE EXISTS (
    SELECT 1
    FROM price_staging s
    WHERE s.product_id = p.product_id
      AND s.proposed_price <> p.unit_price
);
```

If either value can be NULL, `<>` can evaluate to UNKNOWN. If you need to detect changes including NULLs, write a NULL-safe comparison explicitly:

```sql
WHERE EXISTS (
    SELECT 1
    FROM price_staging s
    WHERE s.product_id = p.product_id
      AND (
             s.proposed_price <> p.unit_price
          OR (s.proposed_price IS NULL AND p.unit_price IS NOT NULL)
          OR (s.proposed_price IS NOT NULL AND p.unit_price IS NULL)
      )
)
```

### 10.2. Updating from a GROUP BY Query

```sql
UPDATE departments d
SET annual_sales = (
    SELECT SUM(o.total_amount)
    FROM orders o
    WHERE o.department_id = d.department_id
      AND o.order_date >= DATE '2026-01-01'
      AND o.order_date <  DATE '2027-01-01'
)
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.department_id = d.department_id
      AND o.order_date >= DATE '2026-01-01'
      AND o.order_date <  DATE '2027-01-01'
);
```

This is a per-department scalar aggregate. The half-open interval condition ensures all timestamps within 2026 are included if `ORDER_DATE` contains a time component.

### 10.3. Updating Multiple Columns from a Group of Data

```sql
UPDATE customers c
SET (total_order_count, total_spent, last_order_date) = (
    SELECT COUNT(*),
           SUM(o.total_amount),
           MAX(o.order_date)
    FROM orders o
    WHERE o.customer_id = c.customer_id
)
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
```

The metrics are computed from the same set of customer orders. `COUNT(*)` counts rows; `SUM` and `MAX` ignore NULL values in their respective expressions.

## 11. UPDATE with Subqueries in WHERE

Subqueries are not limited to SET. They can also determine target rows.

### 11.1. Using IN

```sql
UPDATE employees
SET bonus = 1000
WHERE department_id IN (
    SELECT department_id
    FROM departments
    WHERE location_id = 1700
);
```

Employees belonging to departments at location 1700 are updated.

### 11.2. Using EXISTS

```sql
UPDATE customers c
SET status = 'VIP'
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.total_amount >= 100000000
);
```

Customers are marked VIP if at least one order reaches the threshold. `EXISTS` does not multiply target rows when multiple matching orders exist.

### 11.3. Combining a SET Subquery and a WHERE Subquery

```sql
UPDATE employees e
SET salary = (
    SELECT a.new_salary
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
)
WHERE e.department_id = 20
  AND EXISTS (
      SELECT 1
      FROM salary_adjustments a
      WHERE a.employee_id = e.employee_id
  );
```

The outer condition limits the department; EXISTS guarantees source existence; the SET subquery retrieves the new value. These three parts have distinct responsibilities and should be read separately.

## 12. UPDATE from Subqueries and Version-Specific UPDATE ... FROM

In many traditional Oracle versions, the standard way to update one table from another is using a **scalar subquery or tuple subquery in SET**, usually paired with `EXISTS`:

```sql
UPDATE target_table t
SET target_value = (
    SELECT s.source_value
    FROM source_table s
    WHERE s.key_id = t.key_id
)
WHERE EXISTS (
    SELECT 1
    FROM source_table s
    WHERE s.key_id = t.key_id
);
```

Do not copy `UPDATE ... FROM` syntax from PostgreSQL or SQL Server into an older Oracle database and assume it is supported. `UPDATE ... FROM` syntax is an Oracle version-dependent capability; if your target system supports this extension, verify the exact syntax in the SQL Language Reference for your running release and check join source uniqueness. Examples in this lesson use traditional subqueries for broader compatibility across Oracle versions.

### 12.1. When Should You Consider MERGE?

If the requirement is to synchronize data from a source with both cases:

- Target row already exists: update.
- Target row does not exist: insert.

then `MERGE` usually expresses it more clearly:

```sql
MERGE INTO employees e
USING employee_updates s
   ON (e.employee_id = s.employee_id)
WHEN MATCHED THEN
    UPDATE SET
        e.salary = s.new_salary,
        e.department_id = s.new_department_id;
```

The example above only updates matched rows. If inserts are needed too, you can add `WHEN NOT MATCHED THEN INSERT (...) VALUES (...)` per data rules. `MERGE` is a separate statement, not just another way to write `UPDATE`; this lesson focuses on single-table UPDATE.

### 12.2. MERGE Also Requires Duplicate Source Control

If the source has multiple rows matching a single target row, `MERGE` can raise errors like `ORA-30926` when a target row is modified multiple times. Normalize the source to one row per key before running MERGE.

## 13. RETURNING: Receiving Values After UPDATE

Oracle supports `RETURNING ... INTO` to retrieve updated column values without running a separate SELECT in certain cases.

Example updating one employee:

```sql
UPDATE employees
SET salary = salary * 1.05
WHERE employee_id = 100
RETURNING salary INTO :new_salary;
```

`:new_salary` is a bind/host variable provided by the tool or application. In PL/SQL:

```sql
DECLARE
    v_new_salary employees.salary%TYPE;
BEGIN
    UPDATE employees
    SET salary = salary * 1.05
    WHERE employee_id = 100
    RETURNING salary INTO v_new_salary;

    DBMS_OUTPUT.PUT_LINE('New salary: ' || v_new_salary);
END;
/
```

This example assumes the condition updates at most one row. If UPDATE affects multiple rows, receiving the results requires an appropriate mechanism, such as `RETURNING BULK COLLECT INTO` in PL/SQL where suitable.

`RETURNING` does not auto-`COMMIT`; the transaction remains managed by the caller.

## 14. UPDATE, Constraints, and Triggers

### 14.1. Constraints Are Checked

UPDATE must obey table constraints:

- `NOT NULL`: a required column cannot be set to NULL.
- `CHECK`: the new value must satisfy the check condition.
- `UNIQUE`: the new value must not create a duplicate within the constraint scope.
- `PRIMARY KEY`: the primary key must remain unique and non-NULL.
- `FOREIGN KEY`: the referenced value must be valid under the relationship and referential action.

Example:

```sql
UPDATE inventory
SET quantity = -5
WHERE product_id = 100;
```

If there is a `CHECK (quantity >= 0)`, UPDATE fails with a constraint violation. Oracle raises the corresponding constraint error; the statement fails and must be handled according to transaction state.

### 14.2. Triggers Can Fire on UPDATE

If the table has `BEFORE UPDATE` or `AFTER UPDATE` triggers, those triggers may execute additional logic when UPDATE affects rows. Thus, actual effects can include changes performed by triggers.

Before running a bulk UPDATE on a business table, understand its related triggers and their side effects. Do not disable triggers just to make a statement run faster without an approved governance process.

### 14.3. Updating to the Same Value as the Old Value

An UPDATE statement still targets a row even when the new expression equals the old value. This can fire triggers and generate undo/redo. If you only want to update when the value changes, add an explicit comparison condition and handle NULL explicitly.

## 15. Transactions, Row Locks, and Safety

### 15.1. UPDATE Makes Changes Within a Transaction

Example:

```sql
UPDATE accounts
SET status = 'SUSPENDED'
WHERE account_id = 5001;

-- Check result in the same transaction:
SELECT account_id, status
FROM accounts
WHERE account_id = 5001;

-- Confirm:
COMMIT;

-- Or discard uncommitted changes:
-- ROLLBACK;
```

In interactive sessions, verify affected row counts and new values before committing when workflow permits. In applications, transaction boundaries are typically managed by a service or transaction manager.

### 15.2. SAVEPOINT for Partial Rollback

```sql
SAVEPOINT before_price_update;

UPDATE products
SET unit_price = unit_price * 1.10
WHERE category_id = 30;

-- If you need to discard only changes after the savepoint:
ROLLBACK TO before_price_update;
```

`ROLLBACK TO SAVEPOINT` undoes changes after the savepoint without discarding earlier work in the transaction. Afterward you can continue or roll back the full transaction.

### 15.3. UPDATE Locks Affected Rows

Oracle uses row locks to coordinate concurrent transactions modifying data. A large UPDATE can hold many locks until commit or rollback, causing other transactions to wait if they try to update the same rows.

Best practices:

- Limit target rows with an accurate WHERE clause.
- Chunk updates into batches for very large volumes if business rules allow.
- Keep transactions short.
- Avoid calling external APIs or waiting for user input while holding an open transaction.
- Handle controlled retries on deadlock/lock wait per application policy.

### 15.4. Do Not Auto-COMMIT After Every UPDATE

`COMMIT` confirms all changes in the current transaction, not just the most recent UPDATE. In multi-step workflows, place commits at proper business boundaries. If each statement auto-commits, you may be unable to roll back the entire operation when a later step fails.

## 16. UPDATE with JDBC

In Java, use `PreparedStatement` to pass values via bind parameters. Never concatenate user input into SQL strings.

### 16.1. Updating a Single Column

```java
String sql = """
    UPDATE employees
    SET salary = ?
    WHERE employee_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, new BigDecimal("25000.00"));
    ps.setLong(2, 100L);

    int rowsUpdated = ps.executeUpdate();
    if (rowsUpdated == 0) {
        // No matching employee.
    } else if (rowsUpdated == 1) {
        // Exactly one employee updated.
    } else {
        // Condition not unique as expected; handle per business rules.
    }
}
```

Text blocks `"""` require Java 15 or newer. On older Java versions, write the SQL as concatenated lines using `+`.

### 16.2. Updating Multiple Columns

```java
String sql =
    "UPDATE employees " +
    "SET salary = ?, commission_pct = ?, updated_at = SYSTIMESTAMP " +
    "WHERE employee_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, new BigDecimal("28000.00"));
    ps.setBigDecimal(2, new BigDecimal("0.12"));
    ps.setLong(3, 100L);

    int rowsUpdated = ps.executeUpdate();
}
```

`executeUpdate()` returns the number of affected rows. Do not use `executeQuery()` for UPDATE statements.

### 16.3. Passing Typed NULL

```java
if (newSalary == null) {
    ps.setNull(1, java.sql.Types.NUMERIC);
} else {
    ps.setBigDecimal(1, newSalary);
}
```

Binding SQL NULL requires the matching JDBC type. Before setting a column to NULL, verify whether the column allows NULL and what that means in the business domain.

### 16.4. Transaction Management

```java
connection.setAutoCommit(false);

try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE inventory SET quantity = quantity - ? WHERE product_id = ?")) {
    ps.setInt(1, 3);
    ps.setLong(2, 2001L);

    int rows = ps.executeUpdate();
    if (rows != 1) {
        throw new IllegalStateException("Unexpected update count: " + rows);
    }

    connection.commit();
} catch (Exception ex) {
    connection.rollback();
    throw ex;
}
```

This snippet illustrates application-managed transactions; in real applications, ensure rollback is also called if an error occurs before entering the appropriate `try` block, and restore auto-commit state according to your connection/pool management policy.

## 17. Safe Workflow Before Running UPDATE

A practical workflow may include:

**Step 1 — Identify target rows**

Write the WHERE condition first and run a SELECT with that same condition:

```sql
SELECT employee_id, salary
FROM employees
WHERE department_id = 20
  AND status = 'ACTIVE';
```

**Step 2 — Check the source if using a subquery**

```sql
SELECT employee_id, COUNT(*) AS source_rows
FROM salary_adjustments
GROUP BY employee_id
HAVING COUNT(*) > 1;
```

Ensure the source has at most one row per target key, or has a defined selection/aggregation rule.

**Step 3 — Define the missing-source policy**

Decide whether to keep the old value, set NULL, set default, or only update rows that have source data. Use `EXISTS`, `CASE`, or `NVL` appropriately.

**Step 4 — Check types and constraints**

Verify precision, scale, length, NOT NULL, CHECK, UNIQUE, foreign keys, and triggers.

**Step 5 — Run UPDATE and check row count**

In SQL Developer or SQLcl, observe the updated row count message. In JDBC, inspect the return value of `executeUpdate()`.

**Step 6 — Verify data after updating**

```sql
SELECT employee_id, salary
FROM employees
WHERE department_id = 20
  AND status = 'ACTIVE';
```

**Step 7 — COMMIT or ROLLBACK**

Only commit when results are verified and the transaction is in a valid state.

## 18. Common Errors When Updating from Subqueries

| Error/Symptom | Cause | How to fix |
|---|---|---|
| `ORA-01427: single-row subquery returns more than one row` | SET subquery returns multiple rows for one target row | Check uniqueness, filter status, aggregate, or select one row with deterministic ORDER BY |
| Target value unexpectedly becomes NULL | Scalar subquery returns no rows and target rows are not filtered | Add EXISTS if updating only when source exists; or define NULL policy explicitly |
| `ORA-01407: cannot update (...) to NULL` | NOT NULL column receives NULL | Check source data, NULL policy, and constraints |
| `ORA-02290` | New value violates CHECK constraint | Adjust data/logic to valid domain |
| `ORA-00001` | New value violates unique/primary key | Check duplicates and keys |
| `ORA-02291` | Foreign key value has no parent row | Check referenced data |
| Too many rows updated | Missing WHERE or overly broad condition | Run SELECT with same condition, check row count |
| Zero rows updated | No rows match WHERE, or EXISTS found no source rows | Check keys, data types, and source data |
| Multiple columns receive wrong data | Column order and SELECT list do not align | Match each position in tuple assignment |
| Calculated value differs from expectation | Confusing old vs new values within the same SET | Rewrite full expression or use an appropriate subquery/CTE |
| UPDATE is slow or blocks other sessions | Too many rows, suboptimal indexes/predicates, long transaction | Limit rows, inspect plan, batch updates, and commit at boundaries |

### 18.1. Distinguishing ORA-01427 from Duplicate Source Data

Simply adding `MAX()` does not always properly solve ORA-01427:

```sql
SET salary = (
    SELECT MAX(new_salary)
    FROM salary_adjustments
    WHERE employee_id = e.employee_id
)
```

This runs because the aggregate returns one row, but it picks the highest salary. If the business needs the latest record by `EFFECTIVE_AT`, MAX salary may be wrong. Choose the business rule first, then write the SQL.

### 18.2. Aggregate Subqueries Without GROUP BY

```sql
SELECT COUNT(*), SUM(amount)
FROM payments
WHERE customer_id = :id
```

An aggregate without `GROUP BY` returns one row even when there are no matching records. `COUNT(*)` is 0 and `SUM(amount)` is NULL. This differs from a normal subquery returning zero rows, even though an empty scalar subquery also evaluates to NULL.

## 19. Comprehensive Lab Exercise

The steps below create dedicated tables in a practice schema. Only run when you have table creation privileges and avoid table names colliding with existing data.

### Step 1. Create the Employees Table

```sql
CREATE TABLE demo_update_employees (
    employee_id NUMBER PRIMARY KEY,
    employee_name VARCHAR2(100) NOT NULL,
    department_id NUMBER,
    salary NUMBER(12, 2),
    email VARCHAR2(150),
    updated_at TIMESTAMP
);
```

### Step 2. Create the Adjustment Source Table

```sql
CREATE TABLE demo_salary_updates (
    employee_id NUMBER NOT NULL,
    new_salary NUMBER(12, 2),
    new_email VARCHAR2(150)
);
```

### Step 3. Insert Sample Data

```sql
INSERT INTO demo_update_employees
VALUES (1, 'An', 10, 10000, 'an@example.test', SYSTIMESTAMP);

INSERT INTO demo_update_employees
VALUES (2, 'Binh', 10, 12000, 'binh@example.test', SYSTIMESTAMP);

INSERT INTO demo_update_employees
VALUES (3, 'Chi', 20, 15000, 'chi@example.test', SYSTIMESTAMP);

INSERT INTO demo_salary_updates
VALUES (1, 11000, 'an.new@example.test');

INSERT INTO demo_salary_updates
VALUES (2, 13200, 'binh.new@example.test');

COMMIT;
```

Employee 3 has no adjustment source row.

### Step 4. Preview Target and Source Rows Before UPDATE

```sql
SELECT e.employee_id,
       e.salary AS old_salary,
       s.new_salary,
       e.email AS old_email,
       s.new_email
FROM demo_update_employees e
LEFT JOIN demo_salary_updates s
  ON s.employee_id = e.employee_id
ORDER BY e.employee_id;
```

Confirm employees 1 and 2 have source rows; employee 3 has no source row.

### Step 5. Update Two Columns from Subquery

```sql
UPDATE demo_update_employees e
SET (salary, email) = (
    SELECT s.new_salary,
           s.new_email
    FROM demo_salary_updates s
    WHERE s.employee_id = e.employee_id
)
WHERE EXISTS (
    SELECT 1
    FROM demo_salary_updates s
    WHERE s.employee_id = e.employee_id
);
```

Only employees 1 and 2 are updated. Employee 3 retains its original salary and email.

### Step 6. Verify Results

```sql
SELECT employee_id,
       employee_name,
       salary,
       email,
       updated_at
FROM demo_update_employees
ORDER BY employee_id;
```

### Step 7. Test Duplicate Source Scenario

Perform only in the demo table:

```sql
INSERT INTO demo_salary_updates
VALUES (1, 11500, 'an.second@example.test');

COMMIT;
```

Try re-running the UPDATE from Step 5. The subquery for employee 1 now returns two rows, so `ORA-01427` may occur. After observing, check:

```sql
SELECT employee_id, COUNT(*) AS source_count
FROM demo_salary_updates
GROUP BY employee_id
HAVING COUNT(*) > 1;
```

### Step 8. Clean Up Test Data

If you only want to delete the duplicate row just added:

```sql
DELETE FROM demo_salary_updates
WHERE employee_id = 1
  AND new_salary = 11500;

COMMIT;
```

Then, if you no longer need the demo tables and have confirmed they are objects you created:

```sql
DROP TABLE demo_salary_updates PURGE;
DROP TABLE demo_update_employees PURGE;
```

`DROP TABLE ... PURGE` drops the table and data, bypassing the recycle bin per command behavior; DDL performs an implicit commit. Never run on business tables or shared objects.

## 20. Key Rules to Remember

| Need | How to write it |
|---|---|
| Update one column | `SET col = expression` |
| Update multiple columns | `SET col1 = expr1, col2 = expr2` |
| Assign multiple columns from same source row | `SET (col1, col2) = (SELECT expr1, expr2 ...)` |
| Fetch value from another table | Correlated scalar subquery in SET |
| Update only rows with source data | Combine with `WHERE EXISTS (...)` |
| Keep old value when no source exists | Filter rows with EXISTS or CASE |
| Set NULL when no source exists | Allow empty scalar subquery, but only intentionally |
| Source has multiple rows | Normalize keys, aggregate, or select one row deterministically |
| Verify affected rows | `SELECT` with same WHERE before UPDATE; inspect row count after UPDATE |
| Retrieve values after UPDATE | `RETURNING ... INTO` where appropriate |
| Update or insert | Consider `MERGE` |
| Manage changes | `COMMIT`, `ROLLBACK`, `SAVEPOINT` |

## 21. Self-Check Questions

**Question 1.** What happens if UPDATE has no WHERE clause?

**Answer:** Every row in the table is included in the target set of the UPDATE.

**Question 2.** How do you update three columns in a single statement?

**Answer:** List three assignments in SET, separated by commas.

**Question 3.** What does `SET (a,b) = (SELECT x,y ...)` require?

**Answer:** Expression count and order must match the column list; the subquery for each target row must return at most one row.

**Question 4.** What is the value if a scalar subquery in SET returns no rows?

**Answer:** The scalar value is NULL. If you do not want to set target rows to NULL, guard rows with EXISTS or write another policy.

**Question 5.** What is the common error if a subquery in SET returns multiple rows?

**Answer:** `ORA-01427: single-row subquery returns more than one row`.

**Question 6.** Why pair EXISTS with a scalar subquery?

**Answer:** EXISTS prevents updating target rows without source records; it does not replace ensuring the source subquery returns at most one row.

**Question 7.** Does an aggregate without GROUP BY return a row when there is no matching data?

**Answer:** Yes. `COUNT(*)` returns 0, and `SUM`/`AVG` can return NULL.

**Question 8.** Should you add MAX to every scalar subquery to avoid ORA-01427?

**Answer:** No. MAX is only correct when the business genuinely needs the largest value; if you need the latest record, select by timestamp and tie-breaker.

**Question 9.** Does UPDATE auto-COMMIT?

**Answer:** No. DML runs inside a transaction; COMMIT or ROLLBACK is needed at business boundaries.

**Question 10.** How do you check the number of rows updated in JDBC?

**Answer:** Call `PreparedStatement.executeUpdate()` and inspect the returned integer.

**Question 11.** If you need to both update existing rows and insert missing rows, which command should you consider?

**Answer:** `MERGE`, provided source data and matching keys are clearly defined.

**Question 12.** Why should you not assume SET assignment order lets a later column read the new value of an earlier column?

**Answer:** UPDATE expressions are evaluated from the row's pre-update values; if you need the new value, write out the full expression or structure the subquery accordingly.

## 22. Conclusion

`UPDATE` modifies data in a single table and can update one or multiple columns in a single statement. For values taken from a subquery, Oracle allows using scalar subqueries in `SET`, or assigning a group of columns via a tuple subquery. Expressions must match in order, and the subquery for each target row must return at most one row.

The most critical aspect to control is when the source has zero rows or multiple rows. An empty scalar subquery produces NULL; without `WHERE EXISTS`, UPDATE can unexpectedly write NULL into target columns. A multi-row subquery causes `ORA-01427`, so you must guarantee uniqueness, aggregate per business rules, or select one record with deterministic ordering. When updating multiple columns, verify positional mapping between target columns and source expressions.

Before running on live data, verify the target row set with SELECT, check source data, constraints, and triggers, monitor affected row counts, then `COMMIT` or `ROLLBACK` per transaction boundaries. In Java/JDBC, use bind parameters, `executeUpdate()`, and explicit transaction boundaries. These steps keep UPDATE both data-accurate and safe in Oracle applications.
