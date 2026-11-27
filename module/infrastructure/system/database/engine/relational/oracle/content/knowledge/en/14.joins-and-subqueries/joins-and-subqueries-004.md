# Placement of Conditions in ON vs WHERE and Its Effect on OUTER JOIN in Oracle

When writing a query to retrieve departments along with their employees, we often want to display **every department**, including those without employees. The appropriate statement is `LEFT OUTER JOIN`. However, if an employee status filter is then added to `WHERE`, departments without employees may vanish from the result. The query still executes normally without any error, yet its meaning has changed.

This is one of the most common JOIN logic bugs: **putting a condition in `ON` vs `WHERE` can change an OUTER JOIN's result**. The two clauses are not freely interchangeable. `ON` determines whether two sides match to form a joined row; `WHERE` filters rows of the JOIN result after Oracle has generated NULL-extended rows for the unmatched side.

This lesson belongs to the **Joins and Subqueries** module for Oracle Database. We will use a departments/employees example to distinguish `INNER JOIN`, `LEFT OUTER JOIN`, `RIGHT OUTER JOIN`, and `FULL OUTER JOIN`; examine conditions on the preserved side and the matched side; handle NULLs; write anti-joins; and review common mistakes.

After this lesson, you can:

- Explain the roles of join conditions in `ON` and result filters in `WHERE`.
- Predict what happens when a right-table condition is placed in `ON` versus `WHERE` of a `LEFT JOIN`.
- Recognize when a `WHERE` condition makes an OUTER JOIN behave like an INNER JOIN.
- Understand why `WHERE right_table.column IS NULL` can find unmatched rows, and why you must test a non-NULL key column.
- Write multi-column conditions, date/time conditions, `OR`, `IS NULL`, and multi-table conditions without accidentally dropping preserved rows.
- Distinguish SQL semantics from how the Oracle optimizer transforms execution plans.

> **Example scope:** Syntax uses ANSI JOIN in Oracle Database 19c. The `DEPARTMENTS` and `EMPLOYEES` tables in the practice section are standalone lab tables. Do not run DDL or sample data scripts on a live application schema.

## 1. Two Condition Locations Have Different Roles

A SELECT statement with a JOIN typically has the structure:

~~~sql
SELECT ...
FROM table_a a
LEFT JOIN table_b b
    ON a.key_col = b.key_col
WHERE ...;
~~~

Distinguish the two clauses:

| Clause | Question it answers | Logical timing |
| --- | --- | --- |
| `ON` | Should two rows from the two sources be considered a matching pair? | When determining JOIN pairs |
| `WHERE` | After the JOIN produces its result set, which rows are kept? | After JOIN and the NULL-extension step of OUTER JOIN |

Example:

~~~sql
SELECT d.department_id, d.department_name, e.employee_id
FROM departments d
LEFT JOIN employees e
    ON e.department_id = d.department_id
   AND e.status = 'ACTIVE'
WHERE d.department_id < 50;
~~~

- `e.department_id = d.department_id` defines the department/employee relationship.
- `e.status = 'ACTIVE'` specifies which employees are eligible to match a department.
- `d.department_id < 50` filters the departments in the final result.

With `LEFT JOIN`, if a department has no matching ACTIVE employee, Oracle still keeps the department row and sets the `EMPLOYEES` columns to NULL. This is the crucial difference compared to moving the status condition down to `WHERE`.

### 1.1. Conceptual processing flow of LEFT OUTER JOIN

~~~text
Left table (DEPARTMENTS)          Right table (EMPLOYEES)
              |                              |
              +--------------+---------------+
                             |
                             v
                       ON CONDITION
                 Determine matching row pairs
                             |
               +-------------+-------------+
               |                           |
             Match                      No match
               |                           |
               v                           v
         Pair two rows              Keep left row
                                    right cols = NULL
               |                           |
               +-------------+-------------+
                             |
                             v
                        JOIN RESULT
                             |
                             v
                      WHERE CONDITION
                             |
                             v
                      REMAINING ROWS
~~~

This is a semantic mental model, not a mandatory physical step order in the execution plan. The Oracle optimizer can push predicates, reorder joins, or choose hash/nested loops/merge join algorithms as long as the result preserves SQL semantics.

## 2. INNER JOIN: ON and WHERE Conditions Are Often Equivalent

With `INNER JOIN`, only row pairs satisfying the join condition are kept. Example:

~~~sql
-- Employee filter placed directly inside ON:
SELECT d.department_id, e.employee_id, e.status
FROM departments d
JOIN employees e
    ON e.department_id = d.department_id
   AND e.status = 'ACTIVE';

-- Employee filter placed in WHERE:
SELECT d.department_id, e.employee_id, e.status
FROM departments d
JOIN employees e
    ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE';
~~~

In this example, both queries have the same result semantics: only department/employee pairs sharing the same department with an ACTIVE employee are returned. With INNER JOIN, conditions referencing only sources in the join can usually be placed in either `ON` or `WHERE` without changing the result set.

However, keep **table relationship conditions** in `ON` and **business filter conditions** in `WHERE` to make SQL easier to read:

~~~sql
SELECT d.department_id, e.employee_id
FROM departments d
JOIN employees e
    ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE'
  AND d.location_id = 1700;
~~~

For INNER JOIN, the optimizer can transform predicates between ON and WHERE. Do not generalize this to OUTER JOIN: in an OUTER JOIN, preserving unmatched rows is part of the semantics.

## 3. LEFT OUTER JOIN: The Left Side Is Preserved

### 3.1. Basic LEFT JOIN

~~~sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM departments d
LEFT OUTER JOIN employees e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id;
~~~

Oracle returns:

- Every department/employee pair with a matching department_id.
- One row for each department without matching employees, with employee-side columns as NULL.
- If a department has multiple employees, the department appears in multiple rows, one per matching employee.

`LEFT JOIN` is shorthand for `LEFT OUTER JOIN`.

### 3.2. Right-table condition placed in ON

Requirement: show **every department**, along with ACTIVE employees if any.

~~~sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name,
    e.status
FROM departments d
LEFT JOIN employees e
    ON e.department_id = d.department_id
   AND e.status = 'ACTIVE'
ORDER BY d.department_id, e.employee_id;
~~~

The status condition is part of the employee matching rule. INACTIVE employees are not matched. If a department has only INACTIVE employees, the department still appears with NULL employee columns.

### 3.3. Placing the same condition in WHERE changes the result

~~~sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name,
    e.status
FROM departments d
LEFT JOIN employees e
    ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE'
ORDER BY d.department_id, e.employee_id;
~~~

This query keeps only post-JOIN rows where `e.status = 'ACTIVE'` is TRUE. For departments with no employees, `e.status` is NULL due to NULL extension; `NULL = 'ACTIVE'` is not TRUE, so WHERE removes those rows. INACTIVE employees are also removed.

The result usually matches an INNER JOIN with the ACTIVE condition:

~~~sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name,
    e.status
FROM departments d
JOIN employees e
    ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE';
~~~

This is commonly called a **null-rejecting predicate** on the right side: a WHERE condition that rejects rows whose right-side columns were NULL-extended. Such a condition can undo the row-preserving behavior of LEFT JOIN.

### 3.4. Side-by-side result comparison

Suppose the data is:

| Department | Department ID | Employee | Status |
| --- | ---: | --- | --- |
| Sales | 10 | An | ACTIVE |
| Sales | 10 | Binh | INACTIVE |
| IT | 20 | Chi | INACTIVE |
| HR | 30 | *(none)* | *(NULL)* |
| Legal | 40 | *(none)* | *(NULL)* |

Result when filtering status in `ON`:

~~~sql
LEFT JOIN employees e
  ON e.department_id = d.department_id
 AND e.status = 'ACTIVE'
~~~

| Department | Employee | Status |
| --- | --- | --- |
| Sales | An | ACTIVE |
| IT | NULL | NULL |
| HR | NULL | NULL |
| Legal | NULL | NULL |

Result when filtering status in `WHERE`:

~~~sql
LEFT JOIN employees e
  ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE'
~~~

| Department | Employee | Status |
| --- | --- | --- |
| Sales | An | ACTIVE |

IT, HR, and Legal disappeared. This is not a syntax error; the second query is asking for a different result.

## 4. Left-Table Condition in ON vs WHERE?

Another misconception is thinking every filter should go into `ON` for "early filtering." With LEFT JOIN, a condition on the **preserved left side** has a different meaning:

~~~sql
-- A: filter departments in WHERE
SELECT d.department_id, d.department_name, e.employee_id
FROM departments d
LEFT JOIN employees e
    ON e.department_id = d.department_id
WHERE d.status = 'OPEN';

-- B: department condition placed in ON
SELECT d.department_id, d.department_name, e.employee_id
FROM departments d
LEFT JOIN employees e
    ON e.department_id = d.department_id
   AND d.status = 'OPEN';
~~~

**Query A:** CLOSED departments are excluded from the result. This is usually the intent when a report only wants OPEN departments.

**Query B:** every department is still preserved because DEPARTMENTS is the left side. For CLOSED departments, the ON condition fails so no employees match; Oracle still returns that department with NULL employee columns.

Therefore:

- Conditions on the **preserved** side usually go in `WHERE` if you want to exclude rows from that side.
- Conditions on the **matched** side usually go in `ON` if you want to restrict matches without dropping rows from the preserved side.

This is a principle for reading query intent, not a rule saying one type of condition must always sit in one place. If the business goal differs, placement should change accordingly.

## 5. NULL Extension and Three-Valued Logic

### 5.1. Why does WHERE drop unmatched rows?

In SQL, a condition can evaluate to:

- TRUE
- FALSE
- UNKNOWN (typically from comparing against NULL)

`WHERE` keeps rows only when the condition evaluates to **TRUE**. Both FALSE and UNKNOWN are rejected.

Examples:

| Expression | Result |
| --- | --- |
| `'ACTIVE' = 'ACTIVE'` | TRUE |
| `'INACTIVE' = 'ACTIVE'` | FALSE |
| `NULL = 'ACTIVE'` | UNKNOWN |
| `NULL IS NULL` | TRUE |
| `NULL IS NOT NULL` | FALSE |

In a LEFT JOIN with no partner, right-side columns are filled with NULL. Thus `WHERE e.status = 'ACTIVE'` does not retain unmatched rows.

### 5.2. Not every WHERE condition on the right side drops NULL-extended rows

The condition:

~~~sql
WHERE e.employee_id IS NULL
~~~

is TRUE for rows with no matching employee. This condition is used in anti-joins later in this lesson.

The condition:

~~~sql
WHERE e.status IS NULL
~~~

also retains unmatched rows, but it additionally retains **matched** employees whose `STATUS` happens to be NULL. If the goal is to find departments with no employees, test a mandatory NOT NULL employee key column like `EMPLOYEE_ID`, rather than relying on a nullable attribute column.

### 5.3. OR does not automatically recover all lost rows

A commonly misleading pattern:

~~~sql
SELECT d.department_id, e.employee_id, e.status
FROM departments d
LEFT JOIN employees e
    ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE'
   OR e.employee_id IS NULL;
~~~

The author may expect `OR e.employee_id IS NULL` to keep every department that has no ACTIVE employees. Look at the IT department in our example, which has only an INACTIVE employee:

1. ON pairs IT with Chi's row because department_id matches.
2. Because a matching row exists, Oracle does not create an extra NULL-extended row for IT.
3. WHERE evaluates `e.status = 'ACTIVE'` as FALSE and `e.employee_id IS NULL` as FALSE too.
4. IT is excluded.

If the requirement is **every department and only ACTIVE employees**, put the status check in ON:

~~~sql
SELECT d.department_id, e.employee_id, e.status
FROM departments d
LEFT JOIN employees e
    ON e.department_id = d.department_id
   AND e.status = 'ACTIVE';
~~~

This is a fundamental difference between "having no employees at all" and "having no employees matching ACTIVE." The two requirements are not the same.

## 6. Multi-Column and Date/Time Conditions in ON

### 6.1. Matching by key and taking only valid rows

Example retrieving every customer along with paid orders:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM customers c
LEFT JOIN orders o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
ORDER BY c.customer_id, o.order_id;
~~~

Customers without PAID orders still appear. Moving `o.status = 'PAID'` to WHERE would exclude customers without matching orders.

### 6.2. Date/time conditions on the right side

Requirement: show all customers along with orders created in November 2026:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.created_at
FROM customers c
LEFT JOIN orders o
    ON o.customer_id = c.customer_id
   AND o.created_at >= TIMESTAMP '2026-11-01 00:00:00'
   AND o.created_at <  TIMESTAMP '2026-12-01 00:00:00'
ORDER BY c.customer_id, o.created_at;
~~~

Customers who only have orders older than November still appear with NULL order columns, because no order satisfies the **entire ON condition**. Moving the two date predicates to WHERE would drop customers who have no orders in November.

The half-open interval `>= start of month` and `< start of next month` covers all fractional seconds without guessing an end-of-day literal. The literal type must match the column type; the example above assumes `CREATED_AT` is a TIMESTAMP without time zone.

### 6.3. Multi-key join conditions

A relationship may require multiple components:

~~~sql
SELECT
    a.account_id,
    t.transaction_id
FROM accounts a
LEFT JOIN transactions t
    ON t.account_id = a.account_id
   AND t.tenant_id = a.tenant_id
   AND t.currency_code = a.currency_code
   AND t.status = 'POSTED';
~~~

Each ON condition helps determine whether a transaction is a valid partner for the account. Accidentally omitting the tenant/currency condition can join wrong data; moving the status condition to WHERE would drop accounts with no POSTED transactions.

### 6.4. Conditions with OR inside ON

~~~sql
SELECT c.customer_id, o.order_id
FROM customers c
LEFT JOIN orders o
    ON o.customer_id = c.customer_id
   AND (o.status = 'PAID' OR o.status = 'SHIPPED');
~~~

This restricts matches to two statuses. Use parentheses to make logic clear when mixing AND/OR. If the expression becomes complex, consider filtering orders in a CTE first and LEFT JOINing to that filtered set:

~~~sql
WITH eligible_orders AS (
    SELECT order_id, customer_id, status
    FROM orders
    WHERE status IN ('PAID', 'SHIPPED')
)
SELECT c.customer_id, o.order_id, o.status
FROM customers c
LEFT JOIN eligible_orders o
    ON o.customer_id = c.customer_id;
~~~

The CTE clearly names the "eligible orders set" before joining. This is equivalent in goal if the filter applies strictly to the orders source and the query has no other semantics-altering logic. The optimizer may inline the CTE; do not assume it always materializes a temporary table.

## 7. RIGHT OUTER JOIN: The Right Side Is Preserved

`RIGHT JOIN` is the mirror image of `LEFT JOIN`. It preserves every row of the right table, even when no matching row exists on the left.

~~~sql
SELECT
    d.department_id,
    e.employee_id,
    e.employee_name
FROM departments d
RIGHT OUTER JOIN employees e
    ON e.department_id = d.department_id
   AND d.status = 'OPEN';
~~~

Every employee still appears. If the department does not exist or is not OPEN, the `DEPARTMENTS` columns are NULL-extended.

Swapping the table order and using LEFT JOIN is usually easier to read:

~~~sql
SELECT
    d.department_id,
    e.employee_id,
    e.employee_name
FROM employees e
LEFT JOIN departments d
    ON d.department_id = e.department_id
   AND d.status = 'OPEN';
~~~

Both express the same intent of preserving the employees table. When reading a query, identify **which table must keep all its rows**; do not look at LEFT/RIGHT alone while ignoring source order.

A condition on the preserved table (here employees) placed in ON restricts matching partners while still keeping right-table rows. To exclude certain employees, place the corresponding condition in WHERE.

## 8. FULL OUTER JOIN: Preserving Both Sides

`FULL OUTER JOIN` keeps:

- Row pairs matching on the ON condition.
- Rows present only on the left, with NULL right columns.
- Rows present only on the right, with NULL left columns.

Example:

~~~sql
SELECT
    a.account_id,
    a.account_name,
    b.account_id AS imported_account_id,
    b.account_name AS imported_name
FROM accounts a
FULL OUTER JOIN imported_accounts b
    ON b.account_id = a.account_id;
~~~

This query can reconcile two account sources, including records present in only one source.

### 8.1. Adding conditions in ON

~~~sql
SELECT
    a.account_id,
    b.account_id AS imported_account_id
FROM accounts a
FULL OUTER JOIN imported_accounts b
    ON b.account_id = a.account_id
   AND b.is_valid = 'Y';
~~~

The condition `b.is_valid = 'Y'` restricts pairing. Rows failing that condition can still appear as single-sided rows in the FULL OUTER JOIN:

- An A row finding no valid B is preserved on the A side.
- An invalid B row does not pair with A and can still be preserved on the B side.

This is not a "keep only valid B" query; ON controls pairing only, while FULL OUTER preserves both sides.

### 8.2. Placing a right-side condition in WHERE

~~~sql
SELECT
    a.account_id,
    b.account_id AS imported_account_id
FROM accounts a
FULL OUTER JOIN imported_accounts b
    ON b.account_id = a.account_id
WHERE b.is_valid = 'Y';
~~~

WHERE drops A-only rows because `b.is_valid` is NULL on those rows. It also drops B-only rows where `IS_VALID` is not Y or is NULL. The query no longer fully preserves both sides as originally intended.

With FULL OUTER JOIN, a WHERE condition on one side can drop one class of unmatched rows; conditions on both sides can alter both. Always analyze all three row categories:

1. Matched rows.
2. Left-only rows.
3. Right-only rows.

Then evaluate the WHERE expression on each category.

## 9. Finding Unmatched Rows: Anti-Join

A common requirement: find customers **who have no orders at all**. Written with LEFT JOIN:

~~~sql
SELECT
    c.customer_id,
    c.customer_name
FROM customers c
LEFT JOIN orders o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
~~~

`ORDER_ID` is assumed to be a NOT NULL primary key. With no matching order, Oracle generates a padded row with `O.ORDER_ID = NULL`, which WHERE keeps. If at least one order exists, `O.ORDER_ID` is non-NULL in the matched rows so the customer does not appear.

### 9.1. Why should you check the primary key?

Avoid writing:

~~~sql
WHERE o.note IS NULL
~~~

if `NOTE` is nullable. A customer with a real order whose `NOTE` was left blank also satisfies this condition and gets misidentified as having no orders.

Always test a right-side column guaranteed to be **NOT NULL for any real row**, usually the primary key.

### 9.2. NOT EXISTS expresses anti-join clearly

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

`NOT EXISTS` directly states "no related order exists." The Oracle optimizer can often transform appropriate anti-join forms into corresponding plans. Semantically, this is clear and avoids having to pick a right-side column for a NULL check.

### 9.3. Finding customers without a PAID order

This requirement differs from "no orders at all":

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

A customer with a PENDING order and no PAID order is still returned. The status condition is part of the **definition of the target partner**, so it goes inside the NOT EXISTS subquery.

Equivalent LEFT JOIN formulation:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
LEFT JOIN orders o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
WHERE o.order_id IS NULL;
~~~

The status condition stays in ON to define "a qualifying PAID order"; WHERE checks that no qualifying order was found. Moving `o.status = 'PAID'` to WHERE would instead search for PAID orders rather than customers lacking PAID orders.

### 9.4. NOT IN and NULL

Another formulation:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders o
);
~~~

If the subquery returns even one `NULL`, `NOT IN` evaluates to UNKNOWN for non-matching values and returns no rows as expected. `NOT EXISTS` is generally safer and clearer for anti-joins when the source column may contain NULL. If using NOT IN, filter out NULLs in the subquery, for example:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders o
    WHERE o.customer_id IS NOT NULL
);
~~~

## 10. Conditions on a Third Table in a Chained OUTER JOIN

Suppose we want all departments, ACTIVE employees, and work location details:

~~~sql
SELECT
    d.department_id,
    e.employee_id,
    l.location_id,
    l.city
FROM departments d
LEFT JOIN employees e
    ON e.department_id = d.department_id
   AND e.status = 'ACTIVE'
LEFT JOIN locations l
    ON l.location_id = e.location_id
   AND l.country_id = 'VN'
ORDER BY d.department_id, e.employee_id;
~~~

Meaning:

- All departments are preserved.
- Only ACTIVE employees are joined.
- Location info is joined only if it is in Vietnam.
- If an employee has no Vietnam location, the department and employee can still appear while location columns are NULL.

Adding `WHERE l.country_id = 'VN'` would drop rows lacking a matching location; the LEFT JOIN chain would lose the preservation the author intended.

With multiple chained OUTER JOINs, verify each layer:

1. Which table is preserved at each join step?
2. Which matching partners do the ON conditions restrict?
3. Which layers' NULL-extended rows would a final WHERE eliminate?

Do not inspect a long query and blindly move all predicates to the bottom to make it look "tidy."

## 11. Putting Filters in an Inline View/CTE Before OUTER JOIN

Another clean way to structure queries is filtering the right-side source in a subquery:

~~~sql
WITH active_employees AS (
    SELECT employee_id, department_id, employee_name, status
    FROM employees
    WHERE status = 'ACTIVE'
)
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM departments d
LEFT JOIN active_employees e
    ON e.department_id = d.department_id;
~~~

The CTE `ACTIVE_EMPLOYEES` contains only ACTIVE employees. The subsequent LEFT JOIN preserves departments and joins only against the filtered employee set.

In this simple case, the result is equivalent to placing `e.status = 'ACTIVE'` in ON. Using a CTE can improve readability when the right-side filter is lengthy, reused, or worth separating as business logic.

### 11.1. Do not filter after JOIN if you want to preserve the left side

If changed to:

~~~sql
WITH active_employees AS (
    SELECT employee_id, department_id, employee_name, status
    FROM employees
)
SELECT
    d.department_id,
    e.employee_id
FROM departments d
LEFT JOIN active_employees e
    ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE';
~~~

the filter sits in WHERE and departments without ACTIVE employees are dropped. Using a CTE alone does not change semantics; **predicate placement within the query block containing the OUTER JOIN** still determines the result.

### 11.2. CTEs can contain aggregations

For example, keeping every customer and attaching their count of PAID orders:

~~~sql
WITH paid_order_counts AS (
    SELECT customer_id, COUNT(*) AS paid_count
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    c.customer_name,
    NVL(p.paid_count, 0) AS paid_count
FROM customers c
LEFT JOIN paid_order_counts p
    ON p.customer_id = c.customer_id;
~~~

Customers with no PAID orders have no row in the CTE, yet are kept by LEFT JOIN; `NVL` displays 0. Moving the condition out of the CTE into a post-join WHERE would require re-evaluating NULL semantics and customer exclusion.

## 12. Conditions in ON Can Affect Row Counts in Various Ways

### 12.1. ON is not always key equality

LEFT JOIN can use range conditions:

~~~sql
SELECT
    p.product_id,
    p.product_name,
    r.price
FROM products p
LEFT JOIN price_rules r
    ON r.product_id = p.product_id
   AND p.effective_at >= r.valid_from
   AND p.effective_at <  r.valid_to;
~~~

A product is matched with the price rule active at a given timestamp. If no rule qualifies, the product still appears with NULL rule columns. The date conditions belong in ON because they define **which rule is a valid match**, not a criterion to exclude products.

### 12.2. Multiple matching rows still produce multiple result rows

LEFT JOIN does not guarantee each left row appears only once. If a department has 10 ACTIVE employees, the result has 10 rows for that department. To get one row per department, aggregate the right side first:

~~~sql
WITH employee_summary AS (
    SELECT department_id, COUNT(*) AS active_count
    FROM employees
    WHERE status = 'ACTIVE'
    GROUP BY department_id
)
SELECT
    d.department_id,
    d.department_name,
    NVL(s.active_count, 0) AS active_count
FROM departments d
LEFT JOIN employee_summary s
    ON s.department_id = d.department_id;
~~~

Once the CTE has at most one row per department_id, the join yields one row per department (assuming department_id is unique in DEPARTMENTS).

### 12.3. WHERE can filter using expressions from both sides

~~~sql
SELECT d.department_id, e.employee_id
FROM departments d
LEFT JOIN employees e
    ON e.department_id = d.department_id
WHERE d.status = 'OPEN'
  AND (e.salary >= 5000 OR e.employee_id IS NULL);
~~~

This keeps OPEN departments that have an employee earning at least 5,000 as well as departments with zero matching employees; however, if a department has only employees earning under 5,000, it already matched in ON, and all of those rows are dropped by WHERE. No additional NULL-extended row is generated after WHERE.

If the goal is "every OPEN department, matching only employees earning 5,000 or more," move the salary condition into ON:

~~~sql
SELECT d.department_id, e.employee_id
FROM departments d
LEFT JOIN employees e
    ON e.department_id = d.department_id
   AND e.salary >= 5000
WHERE d.status = 'OPEN';
~~~

## 13. Legacy Oracle Syntax with the (+) Operator

Oracle historically supported a legacy outer join syntax using the `(+)` operator in `WHERE`:

~~~sql
SELECT d.department_id, e.employee_id
FROM departments d, employees e
WHERE d.department_id = e.department_id(+);
~~~

The `(+)` marker goes on the NULL-extended side—in this example, `EMPLOYEES`. To add a status condition while still keeping departments, legacy syntax requires marking that side appropriately:

~~~sql
SELECT d.department_id, e.employee_id
FROM departments d, employees e
WHERE d.department_id = e.department_id(+)
  AND e.status(+) = 'ACTIVE';
~~~

Omitting `(+)` from `e.status = 'ACTIVE'` can eliminate NULL-extended rows and make the result behave like an inner join in this situation.

However, `(+)` syntax has many limitations compared to ANSI JOIN, especially when combining multiple tables, OR conditions, subqueries, and complex expressions. Do not mix `(+)` syntax with `JOIN ... ON` in the same query block. For new code, prefer ANSI:

~~~sql
SELECT d.department_id, e.employee_id
FROM departments d
LEFT JOIN employees e
    ON e.department_id = d.department_id
   AND e.status = 'ACTIVE';
~~~

ANSI JOIN makes it clear which table is preserved and which predicates belong to the join relationship, making queries easier to read and less error-prone.

## 14. How to Read an OUTER JOIN Query Before Running It

When reviewing SQL, ask this sequence of questions:

1. **Which table must keep all its rows?** For LEFT JOIN, that is the left table of that specific join.
2. **Which conditions define a valid partner?** Place key predicates and partner criteria in ON.
3. **Which conditions exclude business records from the final output?** Place them in WHERE when you genuinely intend to drop even preserved rows that fail them.
4. **Which columns become NULL when there is no partner?** Check whether WHERE predicates on those columns evaluate to UNKNOWN/FALSE or TRUE.
5. **Can multiple rows match?** Check cardinality to understand the result row count.
6. **Is an anti-join needed?** Use NOT EXISTS or check IS NULL on a right-side primary key.
7. **Are multiple OUTER JOINs chained?** Analyze preservation and NULL extension layer by layer.

### 14.1. Quick decision table for LEFT JOIN

| Intent | Appropriate Condition Placement |
| --- | --- |
| Keep all departments, match only ACTIVE employees | `e.status = 'ACTIVE'` in ON |
| Show only OPEN departments | `d.status = 'OPEN'` in WHERE |
| Keep all OPEN departments, match only high-salary employees | `e.salary >= ...` in ON and `d.status = 'OPEN'` in WHERE |
| Keep only departments that have ACTIVE employees | INNER JOIN with ACTIVE filter, or LEFT JOIN + intentional null-rejecting WHERE |
| Find departments with no employees at all | LEFT JOIN on key + WHERE employee key IS NULL, or NOT EXISTS |
| Find departments with no ACTIVE employees | LEFT JOIN with status in ON + WHERE employee key IS NULL, or NOT EXISTS with status |
| Keep only departments with employees who have an email | WHERE e.email IS NOT NULL or INNER JOIN depending on intent |

Crucially, the business specification must clearly state whether it means "no employees at all" or "no employees meeting a condition." Those are two distinct data questions.

## 15. Practice Lab: Observing ON vs WHERE on the Same Data

The following steps create two small tables. Execute them in a dedicated lab schema. If the table names already exist, pick different names and replace them consistently throughout the exercise.

### Step 1 — Create the departments table

~~~sql
CREATE TABLE join_department_lab (
    department_id NUMBER PRIMARY KEY,
    department_name VARCHAR2(40 CHAR) NOT NULL,
    status VARCHAR2(10 CHAR) NOT NULL
);

INSERT INTO join_department_lab VALUES (10, 'Sales', 'OPEN');
INSERT INTO join_department_lab VALUES (20, 'IT', 'OPEN');
INSERT INTO join_department_lab VALUES (30, 'HR', 'OPEN');
INSERT INTO join_department_lab VALUES (40, 'Legal', 'CLOSED');

COMMIT;
~~~

### Step 2 — Create the employees table

~~~sql
CREATE TABLE join_employee_lab (
    employee_id NUMBER PRIMARY KEY,
    department_id NUMBER,
    employee_name VARCHAR2(40 CHAR) NOT NULL,
    status VARCHAR2(10 CHAR),
    salary NUMBER(10,2),
    CONSTRAINT fk_join_emp_dept_lab
        FOREIGN KEY (department_id)
        REFERENCES join_department_lab(department_id)
);

INSERT INTO join_employee_lab
VALUES (101, 10, 'An', 'ACTIVE', 7000);

INSERT INTO join_employee_lab
VALUES (102, 10, 'Binh', 'INACTIVE', 5000);

INSERT INTO join_employee_lab
VALUES (201, 20, 'Chi', 'INACTIVE', 6000);

COMMIT;
~~~

The dataset is designed intentionally:

- Sales has one ACTIVE employee and one INACTIVE employee.
- IT has only an INACTIVE employee.
- HR has no employees.
- Legal has no employees and is CLOSED.

### Step 3 — LEFT JOIN without status filtering

~~~sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name,
    e.status
FROM join_department_lab d
LEFT JOIN join_employee_lab e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id;
~~~

The result has four departments and five total rows:

| Department | Employee | Status |
| --- | --- | --- |
| Sales | An | ACTIVE |
| Sales | Binh | INACTIVE |
| IT | Chi | INACTIVE |
| HR | NULL | NULL |
| Legal | NULL | NULL |

### Step 4 — Place ACTIVE in ON

~~~sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name,
    e.status
FROM join_department_lab d
LEFT JOIN join_employee_lab e
    ON e.department_id = d.department_id
   AND e.status = 'ACTIVE'
ORDER BY d.department_id, e.employee_id;
~~~

The result has four rows:

| Department | Employee | Status |
| --- | --- | --- |
| Sales | An | ACTIVE |
| IT | NULL | NULL |
| HR | NULL | NULL |
| Legal | NULL | NULL |

IT remains even though it has an INACTIVE employee, because IT has no employee **satisfying the ON condition**. HR and Legal also have no qualifying employees.

### Step 5 — Move ACTIVE to WHERE

~~~sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name,
    e.status
FROM join_department_lab d
LEFT JOIN join_employee_lab e
    ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE'
ORDER BY d.department_id, e.employee_id;
~~~

Only Sales/An remains. IT is eliminated because it already paired with Chi before WHERE ran; HR and Legal are eliminated because status is NULL.

### Step 6 — Try OR IS NULL and explain why IT is missing

~~~sql
SELECT d.department_id, e.employee_id, e.status
FROM join_department_lab d
LEFT JOIN join_employee_lab e
    ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE'
   OR e.employee_id IS NULL
ORDER BY d.department_id;
~~~

The result contains Sales, HR, and Legal; IT still does not appear. Explain using the four steps: ON → match → NULL extension (only if no match) → WHERE.

### Step 7 — Find departments without ACTIVE employees

~~~sql
SELECT d.department_id, d.department_name
FROM join_department_lab d
LEFT JOIN join_employee_lab e
    ON e.department_id = d.department_id
   AND e.status = 'ACTIVE'
WHERE e.employee_id IS NULL
ORDER BY d.department_id;
~~~

The result includes IT, HR, and Legal. This asks for "no ACTIVE employees," so IT is returned despite having an INACTIVE employee.

### Step 8 — Rewrite using NOT EXISTS

~~~sql
SELECT d.department_id, d.department_name
FROM join_department_lab d
WHERE NOT EXISTS (
    SELECT 1
    FROM join_employee_lab e
    WHERE e.department_id = d.department_id
      AND e.status = 'ACTIVE'
)
ORDER BY d.department_id;
~~~

The result must match Step 7. Compare both formulations and identify the key column tested in the LEFT JOIN version.

### Step 9 — Department condition in ON vs WHERE

~~~sql
-- Every department is preserved; only OPEN departments can pair with employees.
SELECT d.department_id, d.status, e.employee_id
FROM join_department_lab d
LEFT JOIN join_employee_lab e
    ON e.department_id = d.department_id
   AND d.status = 'OPEN'
ORDER BY d.department_id;

-- Only OPEN departments are preserved.
SELECT d.department_id, d.status, e.employee_id
FROM join_department_lab d
LEFT JOIN join_employee_lab e
    ON e.department_id = d.department_id
WHERE d.status = 'OPEN'
ORDER BY d.department_id;
~~~

Compare Legal: the first query still preserves Legal with NULL employee columns; the second query excludes Legal.

### Step 10 — Counting employees properly after LEFT JOIN

~~~sql
SELECT
    d.department_id,
    COUNT(*) AS joined_rows,
    COUNT(e.employee_id) AS employee_count
FROM join_department_lab d
LEFT JOIN join_employee_lab e
    ON e.department_id = d.department_id
GROUP BY d.department_id
ORDER BY d.department_id;
~~~

For HR and Legal, `COUNT(*)` is 1 because each department produces one NULL-extended row; `COUNT(e.employee_id)` is 0 because the employee key is NULL. To count employees, use `COUNT(e.employee_id)` or a guaranteed NOT NULL right-side column.

### Step 11 — Clean up lab tables when no longer needed

~~~sql
-- Run only if you are sure these are the two lab tables you created.
DROP TABLE join_employee_lab PURGE;
DROP TABLE join_department_lab PURGE;
~~~

The employee table has a foreign key to department, so drop the child table first. `PURGE` bypasses the recycle bin; do not use it if you want to keep the practice data.

## 16. Common Errors and Misconceptions

| Symptom | Cause | Fix According to Intent |
| --- | --- | --- |
| LEFT JOIN yet departments without employees disappear | WHERE filters right-side column, rejecting NULL extensions | Move partner condition to ON to keep departments |
| Department with only INACTIVE employees still disappears after `OR e.id IS NULL` | ON already matched the INACTIVE employee, so no NULL-extended row was created | Put ACTIVE in ON or use NOT EXISTS |
| Using `WHERE e.note IS NULL` to find no employees | NOTE can be NULL on real employees | Check right-side PK or use NOT EXISTS |
| LEFT JOIN returns more rows than departments | One department has multiple matching employees | Aggregate the right side first if you want one row per department |
| Moving a left-table condition from WHERE to ON adds rows back | Left table is the preserved side | Keep left-table filter predicates in WHERE if you want to exclude those rows |
| FULL OUTER JOIN stops preserving left-only rows | WHERE on right-side column rejects NULL extensions | Evaluate predicate across row types; move partner conditions to ON |
| Anti-join with NOT IN unexpectedly returns empty | Subquery contains NULL | Use NOT EXISTS or filter NULLs in the subquery |
| Correct JOIN keys yet totals are doubled | 1:N relationship or joining multiple detail tables multiplies rows | Determine grain/cardinality and aggregate at the proper level |
| Legacy SQL with (+) is hard to read | Legacy outer join syntax has limitations | Migrate to ANSI JOIN as part of a migration plan |

### 16.1. ORA-01417 and legacy syntax issues

When using `(+)`, certain multi-table joins and multi-condition combinations have restrictions depending on the Oracle version; errors such as `ORA-01417` can occur in invalid legacy patterns. Never sprinkle `(+)` onto columns randomly. Rewrite using ANSI JOIN, clearly specify each relationship, and test the result.

### 16.2. A condition in WHERE is not automatically wrong

If the requirement is "only return departments that have ACTIVE employees," the condition:

~~~sql
WHERE e.status = 'ACTIVE'
~~~

is valid, because you intentionally want to exclude departments lacking ACTIVE employees. You can write an INNER JOIN directly to express that intent:

~~~sql
SELECT d.department_id, e.employee_id
FROM departments d
JOIN employees e
    ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE';
~~~

What to avoid is writing LEFT JOIN expecting to preserve the entire left side, and then accidentally adding a WHERE predicate that eliminates the very rows you meant to preserve. Correct placement depends on **business semantics**, not a mechanical rule applied to every SQL query.

## 17. Self-Check Questions

1. How do `ON` and `WHERE` differ when a query contains a LEFT OUTER JOIN?
2. In a LEFT JOIN, which table is preserved when no matching row exists?
3. If `e.status = 'ACTIVE'` is in ON, will a department with only INACTIVE employees appear?
4. If the same condition is in WHERE, why is a department with no employees excluded?
5. Does `WHERE e.status = 'ACTIVE' OR e.employee_id IS NULL` keep a department that only has INACTIVE employees? Why?
6. Why should you check `IS NULL` on the right-side primary key in an anti-join?
7. Distinguish "having no employees at all" from "having no ACTIVE employees."
8. Rewrite the anti-join finding customers without PAID orders using NOT EXISTS.
9. When a left-table condition is placed in ON of a LEFT JOIN, what happens to left rows failing the condition?
10. In a FULL OUTER JOIN, which row types can be lost if a right-table condition is placed in WHERE?
11. How do `COUNT(*)` and `COUNT(e.employee_id)` differ for a department with no employees?
12. Should an order date condition go in ON or WHERE if you still want to keep all customers?
13. Why can a department appear multiple times in a LEFT JOIN result?
14. How can a CTE filtering ACTIVE employees before LEFT JOIN make SQL easier to understand?
15. Why shouldn't you assume the result is identical regardless of where the optimizer pushes predicates?

**Answer hints:**

1. ON determines matching pairs; WHERE filters the result set after JOIN/NULL extension.
2. The left table.
3. Yes; the department is preserved with NULL employee columns.
4. Right-side columns of unmatched rows are NULL; the comparison returns UNKNOWN and WHERE rejects them.
5. No. The INACTIVE employee matched in ON so no NULL-extended row is generated; WHERE drops that row.
6. The primary key is never NULL on real rows, so NULL indicates no partner exists.
7. The second condition removes only non-ACTIVE employees from eligible partners; a department with INACTIVE employees still has zero ACTIVE employees.
8. Use NOT EXISTS with `customer_id` and `status='PAID'` inside the subquery.
9. The left row is still kept, but right-side columns are NULL because no pair matched.
10. Left-only rows are dropped if the right-side predicate rejects NULL; depending on the condition, right-only rows may also be filtered out.
11. COUNT(*) counts the NULL-extended row (1); COUNT(e.employee_id) counts 0.
12. Put the order condition in ON if every customer must be preserved.
13. Because multiple employees can share the same department_id, and each pair produces one row.
14. The CTE gives a name to the filtered partner set, separating business filters from the join step.
15. The optimizer may only transform queries in ways that preserve semantics; authors must understand predicate and NULL semantics.

## Oracle Reference Documentation

- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): join syntax, outer joins, ON and WHERE conditions.
- [Oracle Database SQL Language Reference — Joins](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Joins.html): inner, outer, full outer join rules and ANSI/legacy syntax.
- [Oracle Database SQL Language Reference — Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Conditions.html): SQL conditions, NULLs, and three-valued logic.
- [Oracle Database SQL Language Reference — EXISTS Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/EXISTS-Condition.html): `EXISTS` and `NOT EXISTS` in subqueries.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): how the optimizer transforms queries, predicates, and execution plans.
