# Scalar, Table, and Correlated Subqueries in PostgreSQL

In SQL, a `SELECT` statement does not have to stand only at the top of a query. It can also appear **inside another SQL statement** to compute a value, produce an intermediate dataset, or check for the existence of related rows.

For example, an HR application might want to find employees whose salary is higher than **their own department's average**. A sales system might need to display **the most recent order for each customer**, including customers who have not made a purchase yet. Another report needs to find **customers with no paid orders**.

All of these problems can use a *subquery*, but how you write it and what results you get depend on the subquery's position and the number of rows and columns it returns.

Three core concepts of this lesson:

- **Scalar subquery**: returns at most **one row, one column**, used as a single-valued expression. If there are no rows, the value is `NULL`; if it returns more than one row, an error is raised.
- **Table subquery / derived table**: produces a temporary relation that can contain **multiple rows and multiple columns**, commonly appearing in `FROM` or `JOIN`, given an alias, and able to participate in combining data like a table.
- **Correlated subquery**: a subquery that **references columns from the outer query**. It can be a scalar subquery, `EXISTS`, `NOT EXISTS`, or a table subquery using `LATERAL`.

One point to keep in mind: **"scalar", "table", and "correlated" are not three mutually exclusive categories**. "Scalar/table" describes **the result shape and usage context**; "correlated" describes **the data reference scope**. A scalar subquery can be correlated or uncorrelated.

This lesson uses modern PostgreSQL, providing a practice schema, result analysis, common pitfalls, equivalent approaches using `JOIN`/window functions, and how to inspect execution plans.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Identify the outer query and the subquery; distinguish between scalar results and table results.
2. Use scalar subqueries in `SELECT`, `WHERE`, and other calculated expressions.
3. Understand how PostgreSQL handles a scalar subquery returning **0, 1, or multiple rows**.
4. Use a derived table in `FROM`/`JOIN` to aggregate and then combine data.
5. Write correlated subqueries properly using inner and outer table aliases.
6. Use `EXISTS`, `NOT EXISTS`, `IN`, and comparisons against subquery results.
7. Use `JOIN LATERAL` and `LEFT JOIN LATERAL` for latest-row/top-N-per-record problems.
8. Distinguish between `NULL`, "no rows", aggregates, and the `NOT IN` pitfall.
9. Compare subqueries with `JOIN`, CTEs, and window functions in terms of semantics and complexity.
10. Know when to inspect `EXPLAIN (ANALYZE, BUFFERS)` and consider indexes.
11. Design safe queries without letting subqueries mask data constraint errors or concurrency issues.

All commands for creating/dropping tables and modifying data in this lesson **must only be run on a dedicated practice database**.

---

## 2. Map of Subquery Types

A subquery is classified by **how its result is consumed**:

| Position / Form | How the result is used | Typical example |
| --- | --- | --- |
| `SELECT (SELECT ...) AS value` | A single value | Company-wide average salary |
| `WHERE salary > (SELECT ...)` | A value for comparison | Salary higher than average |
| `FROM (SELECT ...) AS stats` | An intermediate table | Total order count per customer |
| `JOIN (SELECT ...) AS stats ON ...` | A table to join | Matching customers with statistics |
| `WHERE id IN (SELECT ...)` | Single-column set of values | Customers with PAID orders |
| `WHERE EXISTS (SELECT ...)` | Check for at least one row | Customers with orders |
| `WHERE NOT EXISTS (SELECT ...)` | Check for zero rows | Customers who haven't purchased |
| `JOIN LATERAL (SELECT ... outer_column ...)` | Sub-table allowed to reference preceding tables | Most recent order for each customer |

**Correlation** is another classification dimension:

```text
                         SUBQUERY
                              |
                  +-----------+-----------+
                  |                       |
            By result shape          By reference
                  |                       |
           +------+-------+          +----+------+
           |              |          |           |
        Scalar       Table-valued  Independent  Correlated
        0..1 x 1       0..N x M    of outer    uses outer cols
           |              |          |           |
           +--------------+----------+-----------+
                Properties can be combined
```

Example of a correlated scalar subquery:

```sql
SELECT e.employee_name,
       (
           SELECT AVG(e2.salary)
           FROM employees AS e2
           WHERE e2.department_id = e.department_id
       ) AS department_avg
FROM employees AS e;
```

It returns one average value per employee while also using `e.department_id` from the outer query. This is both **scalar** and **correlated**.

---

## 3. Preparing the Practice PostgreSQL Dataset

We use two groups of tables:

1. `departments` and `employees` for salaries, department-level statistics, and correlated queries.
2. `customers` and `orders` for latest orders, table aggregations, `EXISTS`, `NOT EXISTS`, and `LATERAL`.

The data is designed to include **departments with no employees**, **employees not yet assigned to a department**, **customers with no orders**, and **multiple orders with the same timestamp**, helping observe edge cases.

> **Warning:** The `DROP TABLE IF EXISTS` block below will delete practice tables with the same names in the `subquery_lab` schema. Do not run it on a production database or a schema containing data you need to keep.

### 3.1. Creating the schema and tables

```sql
CREATE SCHEMA IF NOT EXISTS subquery_lab;

DROP TABLE IF EXISTS subquery_lab.orders;
DROP TABLE IF EXISTS subquery_lab.customers;
DROP TABLE IF EXISTS subquery_lab.employees;
DROP TABLE IF EXISTS subquery_lab.departments;

CREATE TABLE subquery_lab.departments (
    department_id INTEGER PRIMARY KEY,
    department_name TEXT NOT NULL UNIQUE
);

CREATE TABLE subquery_lab.employees (
    employee_id INTEGER PRIMARY KEY,
    employee_name TEXT NOT NULL,
    department_id INTEGER
        REFERENCES subquery_lab.departments(department_id),
    salary NUMERIC(12,2) NOT NULL CHECK (salary >= 0),
    joined_at DATE NOT NULL
);

CREATE TABLE subquery_lab.customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL
);

CREATE TABLE subquery_lab.orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES subquery_lab.customers(customer_id),
    status TEXT NOT NULL
        CHECK (status IN ('DRAFT', 'PAID', 'CANCELED')),
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    ordered_at TIMESTAMPTZ NOT NULL
);
```

Here, `employees.department_id` **allows NULL** to represent employees not yet assigned to a department. In contrast, `orders.customer_id` is `NOT NULL` and has a `FOREIGN KEY`, so every order must belong to a valid customer.

### 3.2. Loading departments and employees

```sql
INSERT INTO subquery_lab.departments (
    department_id, department_name
)
VALUES
    (10, 'Engineering'),
    (20, 'Sales'),
    (30, 'Operations'),
    (40, 'Legal');

INSERT INTO subquery_lab.employees (
    employee_id, employee_name, department_id, salary, joined_at
)
VALUES
    (1, 'An',   10,   3000.00, DATE '2026-01-10'),
    (2, 'Bình', 10,   4200.00, DATE '2026-01-11'),
    (3, 'Chi',  10,   4200.00, DATE '2026-02-02'),
    (4, 'Dũng', 20,   2500.00, DATE '2026-02-10'),
    (5, 'Hà',   20,   3500.00, DATE '2026-03-01'),
    (6, 'Lan',  30,   2800.00, DATE '2026-03-05'),
    (7, 'Mai',  NULL, 2600.00, DATE '2026-03-06'),
    (8, 'Nam',  30,   3200.00, DATE '2026-03-08');
```

The dataset has the following structure:

| Department | Employee | Salary | Department Avg |
| --- | --- | ---: | ---: |
| 10 — Engineering | An | 3000 | 3800 |
| 10 — Engineering | Bình | 4200 | 3800 |
| 10 — Engineering | Chi | 4200 | 3800 |
| 20 — Sales | Dũng | 2500 | 3000 |
| 20 — Sales | Hà | 3500 | 3000 |
| 30 — Operations | Lan | 2800 | 3000 |
| 30 — Operations | Nam | 3200 | 3000 |
| Unassigned | Mai | 2600 | Undefined |
| 40 — Legal | No employees | — | NULL |

The average across all 8 employees is **3250**.

### 3.3. Loading customers and orders

```sql
INSERT INTO subquery_lab.customers (
    customer_id, customer_name
)
VALUES
    (101, 'An Nhiên'),
    (102, 'Bảo Châu'),
    (103, 'Gia Hân'),
    (104, 'Minh Khoa'),
    (105, 'Quốc Nam');

INSERT INTO subquery_lab.orders (
    order_id, customer_id, status, amount, ordered_at
)
VALUES
    (1001, 101, 'PAID',      100.00, '2026-01-01 09:00:00+00'),
    (1002, 101, 'DRAFT',     150.00, '2026-02-15 08:00:00+00'),
    (1003, 102, 'PAID',      200.00, '2026-02-15 08:00:00+00'),
    (1004, 103, 'CANCELED',   50.00, '2026-03-01 10:00:00+00'),
    (1005, 103, 'PAID',       75.00, '2026-03-01 10:00:00+00'),
    (1006, 101, 'PAID',      175.00, '2026-04-03 12:00:00+00');
```

Characteristics:

- Customer **101** has three orders, two PAID; total PAID = 275.
- Customer **102** has one PAID order; total PAID = 200.
- Customer **103** has two orders with the same `ordered_at` timestamp but different `order_id`s, only one PAID; total PAID = 75.
- Customers **104** and **105** have no orders yet.

Having two orders for customer 103 with the same timestamp helps illustrate **why `ORDER BY ordered_at DESC LIMIT 1` is not enough to pick a deterministic row when there is a tie**.

### 3.4. Initial verification

```sql
SELECT COUNT(*) AS departments_count
FROM subquery_lab.departments;

SELECT COUNT(*) AS employees_count
FROM subquery_lab.employees;

SELECT COUNT(*) AS customers_count
FROM subquery_lab.customers;

SELECT COUNT(*) AS orders_count
FROM subquery_lab.orders;
```

Corresponding results: **4, 8, 5, 6**.

You can inspect the data:

```sql
SELECT *
FROM subquery_lab.employees
ORDER BY employee_id;

SELECT *
FROM subquery_lab.orders
ORDER BY customer_id, ordered_at, order_id;
```

---

## 4. What Is a Scalar Subquery?

A **scalar subquery** is a subquery used where SQL expects **a single value**.

Common syntax:

```sql
SELECT (
    SELECT expression
    FROM some_table
    WHERE ...
) AS one_value;
```

Key rules:

1. The subquery must produce **one column** compatible with a scalar expression context.
2. If it returns **exactly one row** → the value in that row is used.
3. If it returns **no rows** → the result of the scalar subquery is **NULL**.
4. If it returns **more than one row** → PostgreSQL raises the error `more than one row returned by a subquery used as an expression`.
5. The single column's value in that single row may itself be NULL; distinguish this from the zero-row case.

### 4.1. Uncorrelated scalar subquery

Find the company's highest salary:

```sql
SELECT (
    SELECT MAX(salary)
    FROM subquery_lab.employees
) AS company_max_salary;
```

Result: **4200**.

The subquery here does not use any column from the outer query; it is called an **uncorrelated subquery**.

You can also write:

```sql
SELECT employee_id, employee_name, salary
FROM subquery_lab.employees
WHERE salary > (
    SELECT AVG(salary)
    FROM subquery_lab.employees
)
ORDER BY salary DESC, employee_id;
```

The company-wide average is 3250; employees earning more than this:

| ID | Employee | Salary |
| ---: | --- | ---: |
| 2 | Bình | 4200 |
| 3 | Chi | 4200 |
| 5 | Hà | 3500 |

If the table changes, the result may differ. This example is based on the initial lab dataset.

### 4.2. Placing a scalar subquery in the SELECT list

```sql
SELECT
    e.employee_id,
    e.employee_name,
    e.salary,
    (
        SELECT AVG(e2.salary)
        FROM subquery_lab.employees AS e2
    ) AS company_avg_salary
FROM subquery_lab.employees AS e
ORDER BY e.employee_id;
```

Here, all eight employees have `company_avg_salary = 3250` in the result. The subquery is uncorrelated, so **semantically** it supplies the same value for all outer rows.

Do not assume PostgreSQL will necessarily execute it eight times. The planner can recognize an independent subquery and execute it using an optimization mechanism like `InitPlan`.

### 4.3. Zero rows: a scalar subquery returns NULL

```sql
SELECT (
    SELECT o.amount
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = 104
) AS customer_104_order_amount;
```

Customer 104 has no orders, so the subquery returns **0 rows** and the scalar result is **NULL**.

This is not the number 0. NULL here means **no value could be obtained from the subquery**.

If business logic displays "total is 0 when there are no orders", you can use:

```sql
SELECT COALESCE(
    (
        SELECT SUM(o.amount)
        FROM subquery_lab.orders AS o
        WHERE o.customer_id = 104
    ),
    0::NUMERIC
) AS customer_104_total;
```

The result is 0 because of **`COALESCE`**, not because PostgreSQL automatically treats no orders as a sum of 0.

### 4.4. Multiple rows: a scalar subquery causes an error

This is an **intentionally invalid** example:

```sql
-- EXPECTED ERROR: customer 101 has three orders.
SELECT (
    SELECT o.amount
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = 101
) AS one_amount;
```

The subquery returns three rows, whereas the context allows only one value. PostgreSQL rejects it rather than arbitrarily picking the first row.

The error message typically looks like:

```text
ERROR: more than one row returned by a subquery used as an expression
```

Do not fix this error by adding `LIMIT 1` without understanding the business requirement. You must answer: do you want the total amount, the largest amount, the latest order, a specific order by unique key, or a list of all orders?

### 4.5. Selecting a single row using ORDER BY ... LIMIT 1

If you want the amount of customer 101's **latest order**:

```sql
SELECT (
    SELECT o.amount
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = 101
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 1
) AS latest_order_amount;
```

Result: **175.00** (order 1006).

Both columns in ORDER BY have a purpose:

- `ordered_at DESC`: newer timestamps come first.
- `order_id DESC`: when two orders share the same timestamp, pick the higher ID according to the illustrative rule.

If you use `LIMIT 1` without ORDER BY, PostgreSQL **makes no guarantee about which row will be chosen**. If you only ORDER BY timestamp when multiple orders share the same timestamp, the result can still be non-deterministic with respect to your intent.

### 4.6. The number of columns must also match

Example **intentionally invalid in a scalar context**:

```sql
-- EXPECTED ERROR: scalar subquery does not accept two separate columns.
SELECT (
    SELECT o.order_id, o.amount
    FROM subquery_lab.orders AS o
    WHERE o.order_id = 1001
);
```

Even though the subquery returns only one row, it returns **two columns**. If you want two attributes of the same order, use a derived table/`JOIN LATERAL`, a deliberately declared composite type, or an appropriate JSON representation—do not try to place a two-column table where a single value is expected.

### 4.7. Aggregates guarantee a single value

Instead of selecting multiple orders directly:

```sql
SELECT (
    SELECT SUM(o.amount)
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = 101
) AS total_order_amount;
```

The result is **425.00** (100 + 150 + 175), including the DRAFT order because there is no status filter yet.

If counting only PAID orders:

```sql
SELECT (
    SELECT SUM(o.amount)
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = 101
      AND o.status = 'PAID'
) AS paid_total;
```

Result: **275.00**.

Common aggregates like `SUM`, `AVG`, `MAX`, `MIN`, and `COUNT` **without GROUP BY** normally return one summary row, even when the input set is empty. However, the result of many aggregates on an empty set is NULL, while `COUNT(*)` is 0.

---

## 5. Scalar Subqueries with COUNT, SUM, and NULL

This is an important point when building reports.

```sql
SELECT
    (
        SELECT COUNT(*)
        FROM subquery_lab.orders
        WHERE customer_id = 104
    ) AS order_count,

    (
        SELECT SUM(amount)
        FROM subquery_lab.orders
        WHERE customer_id = 104
    ) AS order_amount_sum,

    (
        SELECT AVG(amount)
        FROM subquery_lab.orders
        WHERE customer_id = 104
    ) AS order_amount_avg;
```

For customer 104 with no orders:

| Expression | Result |
| --- | --- |
| `COUNT(*)` | 0 |
| `SUM(amount)` | NULL |
| `AVG(amount)` | NULL |

Reason:

- `COUNT(*)` counts rows, so an empty set has 0 rows.
- `SUM` and `AVG` have no input values to determine an average/sum amount under SQL aggregate rules, so they return NULL.

In some cases you can use:

```sql
COALESCE(SUM(amount), 0::NUMERIC)
```

to represent "total revenue is 0 when there are no orders". However, you should not blindly convert every `AVG` NULL into 0: the average of a set with zero observations should not necessarily be interpreted as 0.

### 5.1. A scalar subquery with zero rows differs from one row containing NULL

Compare:

```sql
-- Subquery with no rows:
SELECT (
    SELECT amount
    FROM subquery_lab.orders
    WHERE order_id = -1
) AS a;

-- Aggregate returning one row whose value is NULL:
SELECT (
    SELECT AVG(amount)
    FROM subquery_lab.orders
    WHERE order_id = -1
) AS b;
```

Both `a` and `b` may display NULL, but for different reasons:

- `a`: the subquery has no rows → scalar context returns NULL.
- `b`: the aggregate produces one row with an AVG value of NULL.

If business logic needs to distinguish these two states, you must also query the row count or existence status instead of inspecting only a single NULL cell.

---

## 6. What Is a Correlated Subquery?

A **correlated subquery** references at least one column from an outer query block.

Consider:

```sql
SELECT
    e.employee_id,
    e.employee_name,
    e.department_id,
    e.salary,
    (
        SELECT AVG(e2.salary)
        FROM subquery_lab.employees AS e2
        WHERE e2.department_id = e.department_id
    ) AS department_avg
FROM subquery_lab.employees AS e
ORDER BY e.employee_id;
```

Aliases:

- `e`: the employee currently being examined by the outer query.
- `e2`: employees queried inside to compute the average.
- `e2.department_id = e.department_id`: the **correlating** condition between the two scopes.

Concept:

```text
Outer query: employee e
        |
        +--> An   (department_id=10)
        |      |
        |      +--> Subquery finds dept 10 salaries -> AVG=3800
        |
        +--> Hà   (department_id=20)
        |      |
        |      +--> Subquery finds dept 20 salaries -> AVG=3000
        |
        +--> Mai  (department_id=NULL)
               |
               +--> e2.department_id = NULL has no TRUE rows
                    -> AVG on empty set is NULL
```

Illustrative result:

| ID | Employee | Dept | Salary | department_avg |
| ---: | --- | ---: | ---: | ---: |
| 1 | An | 10 | 3000 | 3800 |
| 2 | Bình | 10 | 4200 | 3800 |
| 3 | Chi | 10 | 4200 | 3800 |
| 4 | Dũng | 20 | 2500 | 3000 |
| 5 | Hà | 20 | 3500 | 3000 |
| 6 | Lan | 30 | 2800 | 3000 |
| 7 | Mai | NULL | 2600 | NULL |
| 8 | Nam | 30 | 3200 | 3000 |

### 6.1. Why does employee Mai get a NULL department_avg?

The condition:

```sql
WHERE e2.department_id = e.department_id
```

when `e.department_id` is NULL becomes:

```sql
e2.department_id = NULL
```

In SQL, `= NULL` evaluates to **UNKNOWN**, even when `e2.department_id` is also NULL. Therefore, no row in the subquery satisfies the WHERE condition; AVG is NULL.

If business logic wants to treat unassigned employees as a **shared NULL group**, you can use null-safe equality:

```sql
SELECT
    e.employee_id,
    e.employee_name,
    (
        SELECT AVG(e2.salary)
        FROM subquery_lab.employees AS e2
        WHERE e2.department_id
              IS NOT DISTINCT FROM e.department_id
    ) AS department_or_unassigned_avg
FROM subquery_lab.employees AS e
ORDER BY e.employee_id;
```

Mai is then compared against employees with `department_id IS NULL`, receiving an average of **2600** in the lab.

**Both approaches can be right**, depending on the definition of "same-department employees": should unassigned employees be treated as a common group or not?

### 6.2. Using a correlated scalar subquery in WHERE

Requirement:

> Find employees whose salary is **higher than the average of their own department**.

```sql
SELECT
    e.employee_id,
    e.employee_name,
    e.department_id,
    e.salary
FROM subquery_lab.employees AS e
WHERE e.department_id IS NOT NULL
  AND e.salary > (
      SELECT AVG(e2.salary)
      FROM subquery_lab.employees AS e2
      WHERE e2.department_id = e.department_id
  )
ORDER BY e.department_id, e.salary DESC, e.employee_id;
```

Result:

| ID | Employee | Dept | Salary | Dept Avg |
| ---: | --- | ---: | ---: | ---: |
| 2 | Bình | 10 | 4200 | 3800 |
| 3 | Chi | 10 | 4200 | 3800 |
| 5 | Hà | 20 | 3500 | 3000 |
| 8 | Nam | 30 | 3200 | 3000 |

Difference from the query in section 4.1: there, each employee was compared to **a single company-wide average** of 3250. Here, each person is compared to **their own department's average**.

### 6.3. Do not forget the correlation condition

The following query is **uncorrelated**:

```sql
SELECT e.employee_name, e.salary
FROM subquery_lab.employees AS e
WHERE e.salary > (
    SELECT AVG(e2.salary)
    FROM subquery_lab.employees AS e2
);
```

It returns employees earning more than the **company-wide average**, not their department average. If the goal is department-level comparison, missing `e2.department_id = e.department_id` produces the wrong business result even though the SQL is completely valid.

---

## 7. Aliases and Column Scope: Avoiding a Dangerous Mistake

In correlated subqueries, the same column names often exist in multiple query blocks. Always **explicitly qualify column names with table aliases**.

Correct example:

```sql
SELECT e.employee_id, e.department_id
FROM subquery_lab.employees AS e
WHERE EXISTS (
    SELECT 1
    FROM subquery_lab.departments AS d
    WHERE d.department_id = e.department_id
);
```

**Semantically wrong** example:

```sql
-- DO NOT use this to check relationships:
SELECT e.employee_id
FROM subquery_lab.employees AS e
WHERE EXISTS (
    SELECT 1
    FROM subquery_lab.departments AS d
    WHERE department_id = department_id
);
```

Both sides of `department_id` inside the subquery may be resolved by PostgreSQL to **the inner table `d`'s column**, not one side from `d` and one side from `e`. The condition becomes a self-comparison and can be TRUE for almost all department rows, making EXISTS always TRUE whenever `departments` is non-empty.

Never rely on name resolution rules hoping the engine will "automatically infer one column is outer".

### 7.1. When a column name does not exist in the inner query block

PostgreSQL searches outer query scopes for a column name when it is not found in the inner scope. That is sometimes convenient, but it can also make a SQL statement **accidentally become a correlated subquery** if the schema changes or names are ambiguous.

Working rules:

- Define aliases `e`, `e2`, `d`, `c`, `o` and use them in join conditions.
- Distinguish `outer_alias.column` and `inner_alias.column`.
- Do not write `WHERE id = id` and rely on guesswork.
- When refactoring subqueries, re-check aliases and column resolution.
- If a query runs across multiple tenants, specify the full tenant key in the condition.

---

## 8. Table Subqueries: Derived Tables in FROM

Unlike a scalar subquery, a **derived table** is the result of a SELECT placed in `FROM`, typically having multiple rows and multiple columns:

```sql
SELECT result_alias.column_name
FROM (
    SELECT ...
) AS result_alias;
```

The name `result_alias` allows the outer query to reference columns of the intermediate result.

In modern PostgreSQL, some versions allow omitting the alias for a subquery in FROM, but **writing an explicit alias** is a good habit for readability, portability, and avoiding ambiguity.

### 8.1. Aggregating employee counts by department and joining

```sql
SELECT
    d.department_id,
    d.department_name,
    COALESCE(stats.employee_count, 0) AS employee_count,
    stats.avg_salary
FROM subquery_lab.departments AS d
LEFT JOIN (
    SELECT
        e.department_id,
        COUNT(*) AS employee_count,
        AVG(e.salary) AS avg_salary
    FROM subquery_lab.employees AS e
    WHERE e.department_id IS NOT NULL
    GROUP BY e.department_id
) AS stats
    ON stats.department_id = d.department_id
ORDER BY d.department_id;
```

The derived table `stats` has the following rows:

```text
department_id | employee_count | avg_salary
--------------+----------------+-----------
10            | 3              | 3800
20            | 2              | 3000
30            | 2              | 3000
```

It **has no row for department 40**, because department 40 has no employees to GROUP BY. The outer `LEFT JOIN` preserves department 40 and fills the `stats` columns with NULL.

Use `COALESCE(employee_count,0)` to display **0 employees**. You do not have to turn NULL `avg_salary` into 0, because "the average salary of an empty department" has no observed value.

Final result:

| Dept | Name | employee_count | avg_salary |
| ---: | --- | ---: | ---: |
| 10 | Engineering | 3 | 3800 |
| 20 | Sales | 2 | 3000 |
| 30 | Operations | 2 | 3000 |
| 40 | Legal | 0 | NULL |

### 8.2. A derived table does not persist independently after the query

The `stats` result is a **statement-scoped temporary relation**. It does not create a physical table that can be read in subsequent statements.

If you need:

- **Single use within one SQL statement**: a derived table or CTE may suffice.
- **Reuse multiple times in the same statement**: consider a CTE.
- **Storage and reading across multiple statements**: you may need a temporary table, materialized view, or regular table depending on requirements.

Do not call a derived table a "created and stored table" when no actual DDL occurred.

### 8.3. Filtering, sorting, and joining derived tables

For example, keeping only departments with an average salary above 3100:

```sql
SELECT
    stats.department_id,
    stats.employee_count,
    stats.avg_salary
FROM (
    SELECT
        department_id,
        COUNT(*) AS employee_count,
        AVG(salary) AS avg_salary
    FROM subquery_lab.employees
    WHERE department_id IS NOT NULL
    GROUP BY department_id
) AS stats
WHERE stats.avg_salary > 3100
ORDER BY stats.avg_salary DESC;
```

Result: only department **10** (AVG=3800).

The condition `WHERE stats.avg_salary > 3100` is applied in the outer query block, because at that point `avg_salary` is already a column of the derived table.

If you only need to filter groups once, you can write it directly with `HAVING`:

```sql
SELECT department_id, AVG(salary) AS avg_salary
FROM subquery_lab.employees
WHERE department_id IS NOT NULL
GROUP BY department_id
HAVING AVG(salary) > 3100;
```

Not every aggregation needs to be wrapped in a subquery. Choose the structure that makes the logic clearest.

### 8.4. Do not confuse ordering inside a derived table with final result order

Example:

```sql
SELECT *
FROM (
    SELECT employee_id, salary
    FROM subquery_lab.employees
    ORDER BY salary DESC
) AS x;
```

If the outer query needs a guaranteed sort order, **there must still be an ORDER BY on the outermost query block**. Never assume that ordering inside a derived table is preserved across joins, filters, or optimizations.

Practical exception: an `ORDER BY` inside a subquery combined with `LIMIT`/`FETCH FIRST` can determine **which rows are selected** before the outer query processes them, but the **final display order** still requires an ORDER BY on the outer SELECT.

---

## 9. Derived Tables for Order Reporting

A report needs to show each customer along with their total order count and total revenue **only from PAID orders**.

Using a derived table:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(s.order_count, 0) AS order_count,
    COALESCE(s.total_paid, 0::NUMERIC) AS total_paid
FROM subquery_lab.customers AS c
LEFT JOIN (
    SELECT
        o.customer_id,
        COUNT(*) AS order_count,
        SUM(o.amount) FILTER (WHERE o.status = 'PAID')
            AS total_paid
    FROM subquery_lab.orders AS o
    GROUP BY o.customer_id
) AS s
  ON s.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Inside the subquery:

- `COUNT(*)` counts **all** orders for the customer.
- `SUM(amount) FILTER (WHERE status='PAID')` sums only PAID orders.
- `GROUP BY customer_id` produces one summary row per customer who has at least one order.

Result:

| customer_id | Customer | order_count | total_paid |
| ---: | --- | ---: | ---: |
| 101 | An Nhiên | 3 | 275 |
| 102 | Bảo Châu | 1 | 200 |
| 103 | Gia Hân | 2 | 75 |
| 104 | Minh Khoa | 0 | 0 |
| 105 | Quốc Nam | 0 | 0 |

### 9.1. Why not count carelessly after a raw join?

If a report joins `customers` with `orders` and then joins an `order_items` table that has multiple items per order, each order can appear **multiple times** in the joined result, causing `COUNT(order_id)` and `SUM(order_amount)` to be multiplied.

A derived table aggregating at the **right data grain** before joining usually keeps that problem under control.

Example:

```text
customers        orders              order_items
    1  ------->  3 orders ----------> multiple items / order

JOIN everything then SUM(order.amount):
    each order's amount may be duplicated per item

GROUP orders by customer first:
    each customer has 1 summary row
    -> LEFT JOIN customers does not multiply totals
```

However, pre-aggregating does not automatically make every report correct: if item-level statistics are needed, you must pick the appropriate grain and formula from the start.

### 9.2. LEFT JOIN or INNER JOIN?

If you change it to:

```sql
FROM subquery_lab.customers AS c
JOIN (...) AS s
  ON s.customer_id = c.customer_id
```

customers 104 and 105 will **disappear** because they have no matching statistics rows.

Use `LEFT JOIN` when the requirement must still show customers **without orders**, and use `INNER JOIN` when you only want customers who have statistics.

---

## 10. CTE: Naming a Table Subquery

A **Common Table Expression** uses `WITH` to create a named result scoped to the SQL statement:

```sql
WITH order_stats AS (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(amount) FILTER (WHERE status = 'PAID') AS total_paid
    FROM subquery_lab.orders
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(s.order_count, 0) AS order_count,
    COALESCE(s.total_paid, 0::NUMERIC) AS total_paid
FROM subquery_lab.customers AS c
LEFT JOIN order_stats AS s
  ON s.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Conceptually, this is an alternative way to write the derived table from section 9, except the definition is placed at the top of the SQL statement and given the name `order_stats`.

Benefits:

- Makes it easier to break large queries into logical steps.
- Can reference the CTE multiple times in the same statement when appropriate.
- Can be used in recursive queries with `WITH RECURSIVE` — a separate topic.

Do not assume a CTE is **always stored as a physical intermediate table**. Modern PostgreSQL can **inline/fold** side-effect-free SELECT CTEs under optimization conditions, or materialize them depending on context and reference count. The `MATERIALIZED` / `NOT MATERIALIZED` options in supported versions can influence the plan.

**Use CTEs to express logic clearly**, then inspect `EXPLAIN` when performance matters. Do not treat a CTE as a default guarantee that a query block is evaluated only once.

---

## 11. Correlated Subqueries with EXISTS

`EXISTS (subquery)` checks whether **at least one row** is returned.

Example finding customers who have at least one PAID order:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM subquery_lab.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

Result: **101, 102, 103**.

This is a correlated subquery because `o.customer_id = c.customer_id` references `c` from the outer query.

### 11.1. EXISTS only cares whether a row exists

```sql
SELECT
    EXISTS (SELECT NULL::INTEGER) AS has_null_valued_row,
    EXISTS (SELECT 1 WHERE FALSE) AS has_no_row;
```

Result:

- `EXISTS(SELECT NULL)` is TRUE because the SELECT returns **one row**; the NULL value inside the row does not matter.
- `EXISTS(SELECT 1 WHERE FALSE)` is FALSE because the subquery **returns zero rows**.

Therefore:

```sql
EXISTS (SELECT 1 FROM ...)
```

and:

```sql
EXISTS (SELECT * FROM ...)
```

usually have the same meaning. `SELECT 1` is a convention indicating that only existence matters, not a promise that it is always faster than `SELECT *`.

### 11.2. EXISTS avoids row duplication from joins

If a customer has multiple PAID orders, an `INNER JOIN` can produce multiple rows for the same customer:

```sql
SELECT c.customer_id, c.customer_name
FROM subquery_lab.customers AS c
JOIN subquery_lab.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

Customer 101 can appear **twice** because they have two PAID orders. If the requirement is simply "which customers have at least one PAID order", `EXISTS` returns **one row per customer row** without needing DISTINCT to remove duplicates introduced by the join.

Alternatively, one might write:

```sql
SELECT DISTINCT c.customer_id, c.customer_name
FROM subquery_lab.customers AS c
JOIN subquery_lab.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

But `EXISTS` expresses the existence-check intent more directly in this case.

---

## 12. NOT EXISTS: Finding Missing Matches with a Correlated Query

Requirement:

> Find customers who have **never placed an order**.

```sql
SELECT c.customer_id, c.customer_name
FROM subquery_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Result: **104, 105**.

Another requirement:

> Find customers who **do not have a PAID order**, even if they may have DRAFT or CANCELED orders.

```sql
SELECT c.customer_id, c.customer_name
FROM subquery_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

On the lab dataset, the result is also **104, 105** because every customer who has placed an order has at least one PAID order. However, if a customer with only a DRAFT order is added later, they will **not belong** to "never placed an order" but will **belong** to "no PAID order".

This shows how **two queries can coincidentally return the same result on current data while having different business meanings**.

### 12.1. Finding "has orders, but no PAID order"

General pattern:

```sql
SELECT c.customer_id, c.customer_name
FROM subquery_lab.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
)
AND NOT EXISTS (
    SELECT 1
    FROM subquery_lab.orders AS p
    WHERE p.customer_id = c.customer_id
      AND p.status = 'PAID'
)
ORDER BY c.customer_id;
```

On the original dataset, the query returns **0 rows** because everyone with an order has a PAID order. This is a valid result, not an error.

To see the difference, you can insert data **temporarily inside a lab transaction**:

```sql
BEGIN;

INSERT INTO subquery_lab.orders (
    order_id, customer_id, status, amount, ordered_at
)
VALUES (
    1007, 104, 'DRAFT', 10.00, '2026-04-05 09:00:00+00'
);

SELECT c.customer_id, c.customer_name
FROM subquery_lab.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
)
AND NOT EXISTS (
    SELECT 1
    FROM subquery_lab.orders AS p
    WHERE p.customer_id = c.customer_id
      AND p.status = 'PAID'
)
ORDER BY c.customer_id;

ROLLBACK;
```

Inside the transaction, the temporary result includes **104**; after `ROLLBACK`, the data returns to its initial state.

### 12.2. Do not confuse "has no PAID order" with "has a non-PAID order"

The statement:

```sql
SELECT DISTINCT c.customer_id
FROM subquery_lab.customers AS c
JOIN subquery_lab.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status <> 'PAID';
```

is **not equivalent** to NOT EXISTS for customers with no PAID orders. It finds customers who have at least one non-PAID order; customer 101 appears because of DRAFT order 1002, **even though they also have two PAID orders**.

Rule to remember:

```text
Has at least one NON-PAID order
    EXISTS(order WHERE status <> 'PAID')

Has NO PAID order
    NOT EXISTS(order WHERE status = 'PAID')
```

The two predicates differ whenever a customer can have multiple orders.

---

## 13. IN, NOT IN, and the NULL Pitfall in Subqueries

When a subquery returns one column, you can use it as a **set of values** in `IN`:

```sql
SELECT c.customer_id, c.customer_name
FROM subquery_lab.customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM subquery_lab.orders AS o
    WHERE o.status = 'PAID'
)
ORDER BY c.customer_id;
```

Result: 101, 102, 103.

However, `NOT IN` has special rules with `NULL`.

### 13.1. NULL on the right side can make NOT IN return UNKNOWN

```sql
SELECT
    1 NOT IN (2, 3, NULL) AS not_in_with_null,
    2 NOT IN (2, 3, NULL) AS matched_value,
    1 NOT IN (2, 3) AS not_in_no_null;
```

| Expression | Result |
| --- | --- |
| `1 NOT IN (2,3,NULL)` | NULL (UNKNOWN) |
| `2 NOT IN (2,3,NULL)` | FALSE |
| `1 NOT IN (2,3)` | TRUE |

Because `1 <> NULL` is UNKNOWN, PostgreSQL cannot conclude that 1 differs from **every element** in the list. In `WHERE`, UNKNOWN is filtered out just like FALSE.

Therefore, if a subquery pulls keys from a table that may contain NULL:

```sql
WHERE id NOT IN (SELECT nullable_id FROM some_table)
```

it can produce an **unexpectedly empty result**. For "no related row exists" problems, `NOT EXISTS` is usually easier to read and semantically safer.

### 13.2. Clarifying NULL on both sides

If the outer row's key can be NULL, `NOT EXISTS` using `=` treats it as **having no matching row**, because `NULL = NULL` returns UNKNOWN.

If business logic wants two NULLs to be considered equal when matching, PostgreSQL supports:

```sql
a IS NOT DISTINCT FROM b
```

Example:

```sql
SELECT
    NULL::INTEGER IS NOT DISTINCT FROM NULL::INTEGER AS both_null,
    NULL::INTEGER IS DISTINCT FROM 10 AS null_vs_ten;
```

Both columns return TRUE.

Still, consider carefully: **do two unknown customer IDs really represent the same customer?** Most reference-key problems should handle NULL/missing data separately rather than merging two NULLs into one entity.

### 13.3. Empty right-hand set

One easily forgotten detail: if the right-hand list/subquery is completely **empty**, `NOT IN` returns TRUE for every left-hand value, including NULL:

```sql
SELECT
    NULL::INTEGER NOT IN (
        SELECT x
        FROM (VALUES (1), (2)) AS t(x)
        WHERE FALSE
    ) AS null_not_in_empty;
```

The result is TRUE. Do not oversimplify by claiming "NULL on the left always makes NOT IN return UNKNOWN" without accounting for the empty-set case.

---

## 14. Comparing with ANY and ALL

Besides `IN`, PostgreSQL lets you compare a value against subquery results using `ANY`/`SOME` and `ALL`.

Syntax:

```sql
expression operator ANY (subquery)
expression operator ALL (subquery)
```

### 14.1. ANY: at least one row satisfies the comparison

Example:

```sql
SELECT e.employee_id, e.employee_name, e.salary
FROM subquery_lab.employees AS e
WHERE e.salary > ANY (
    SELECT e2.salary
    FROM subquery_lab.employees AS e2
    WHERE e2.department_id = 10
)
ORDER BY e.salary DESC, e.employee_id;
```

The predicate "salary greater than **at least one salary** in department 10" differs from "salary greater than the highest salary in department 10".

Department 10 has salaries 3000, 4200, 4200. An employee earning 3200 is already greater than **3000**, so they satisfy `> ANY` even though they do not exceed the maximum of 4200.

You can use `= ANY(array)` as an alternative syntax for IN over an array; however, `ANY (SELECT ...)` takes a subquery result set, whereas `ANY(array)` takes an array expression. Be careful to distinguish the argument type and bind parameters.

### 14.2. ALL: satisfied for every row

Find employees whose salary is **no lower than any colleague in the same department**:

```sql
SELECT
    e.employee_id,
    e.employee_name,
    e.department_id,
    e.salary
FROM subquery_lab.employees AS e
WHERE e.department_id IS NOT NULL
  AND e.salary >= ALL (
      SELECT e2.salary
      FROM subquery_lab.employees AS e2
      WHERE e2.department_id = e.department_id
  )
ORDER BY e.department_id, e.employee_id;
```

Result: **Bình (2), Chi (3), Hà (5), Nam (8)**.

Department 10 has two people tied at the highest salary of 4200, so both are kept. `>= ALL` means "greater than or equal to all", and does not pick only a single person.

### 14.3. Empty sets in ANY and ALL

Under quantifier logic:

- `condition ANY (empty set)` is FALSE.
- `condition ALL (empty set)` is TRUE.

This is why the example above includes:

```sql
WHERE e.department_id IS NOT NULL
```

Employee Mai has `department_id = NULL`; with `e2.department_id = NULL` inside the subquery, the set of matching colleagues is empty, so `salary >= ALL (empty set)` would evaluate to TRUE if Mai were not filtered out. That could produce results contrary to the intent of "highest in an assigned department".

When the subset can contain `NULL`, `ANY`/`ALL` are also subject to three-valued logic. Do not blindly replace an ALL comparison with MIN/MAX without checking empty sets, NULLs, and the comparison operator.

---

## 15. LATERAL: Table Subqueries Referencing Preceding Rows

A regular derived table in `FROM` **cannot freely reference columns of other tables at the same FROM level** without an appropriate mechanism. PostgreSQL provides **`LATERAL`** for this.

Concept:

> For each row already present on the left of FROM/JOIN, allow the subquery on the right to use that row's columns to produce **its own result table**.

The most common example: **fetching the latest order for each customer**.

### 15.1. LEFT JOIN LATERAL to find the latest order

```sql
SELECT
    c.customer_id,
    c.customer_name,
    recent.order_id,
    recent.status,
    recent.amount,
    recent.ordered_at
FROM subquery_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT
        o.order_id,
        o.status,
        o.amount,
        o.ordered_at
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 1
) AS recent ON TRUE
ORDER BY c.customer_id;
```

Explanation:

1. The outer query examines a `customers` row `c`.
2. The LATERAL subquery references `c.customer_id`.
3. Only orders for that customer are selected.
4. Sorted by newest timestamp first; on timestamp ties, higher `order_id` comes first.
5. `LIMIT 1` returns at most one order.
6. `LEFT JOIN ... ON TRUE` retains the customer even when the subquery returns no orders.

Result:

| customer_id | Customer | latest order_id | status | amount |
| ---: | --- | ---: | --- | ---: |
| 101 | An Nhiên | 1006 | PAID | 175 |
| 102 | Bảo Châu | 1003 | PAID | 200 |
| 103 | Gia Hân | 1005 | PAID | 75 |
| 104 | Minh Khoa | NULL | NULL | NULL |
| 105 | Quốc Nam | NULL | NULL | NULL |

**Important point:** customer 103 has two orders with the same `ordered_at`; `ORDER BY o.order_id DESC` picks order 1005 per the illustrative rule. Without a tie-breaking criterion, "newest" may not be enough to select a single deterministic record.

### 15.2. LEFT JOIN LATERAL vs. CROSS JOIN LATERAL

If changed to:

```sql
SELECT c.customer_id, recent.order_id
FROM subquery_lab.customers AS c
CROSS JOIN LATERAL (
    SELECT o.order_id
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 1
) AS recent
ORDER BY c.customer_id;
```

only customers **101, 102, 103** remain, because the subquery returns **0 rows** for 104 and 105, so no row pairs are formed in the CROSS JOIN.

Summary:

| Join form | If the LATERAL subquery returns 0 rows |
| --- | --- |
| `CROSS JOIN LATERAL` | Left-hand row is excluded from the result |
| `JOIN LATERAL ... ON TRUE` | Same as inner join; left-hand row is dropped |
| `LEFT JOIN LATERAL ... ON TRUE` | Left-hand row is preserved; right-hand columns are NULL |

Use `LEFT JOIN LATERAL` when the requirement must also include customers without orders.

### 15.3. Top-N per customer

LATERAL is not limited to picking a single row. Fetching the **two most recent orders per customer**:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    recent.order_id,
    recent.ordered_at
FROM subquery_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.ordered_at
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 2
) AS recent ON TRUE
ORDER BY
    c.customer_id,
    recent.ordered_at DESC NULLS LAST,
    recent.order_id DESC NULLS LAST;
```

Customer 101 gets up to two orders returned; 102 gets one; 103 gets two; 104 and 105 still get one row each with NULL order columns due to LEFT JOIN.

### 15.4. Why not use a regular derived table?

Conceptual example **invalid without LATERAL**:

```sql
-- A subquery in FROM needs LATERAL to reference c.customer_id.
SELECT c.customer_id, x.order_id
FROM subquery_lab.customers AS c
JOIN (
    SELECT o.order_id
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
) AS x ON TRUE;
```

Here the subquery in FROM references `c.customer_id` from another table at the same FROM level. Add `LATERAL`:

```sql
SELECT c.customer_id, x.order_id
FROM subquery_lab.customers AS c
JOIN LATERAL (
    SELECT o.order_id
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
) AS x ON TRUE;
```

In PostgreSQL, certain set-returning functions in FROM exhibit LATERAL reference behavior by specific rules and the LATERAL keyword can be optional; for **SELECT subqueries in FROM like this example**, always write `LATERAL` explicitly.

---

## 16. Scalar Correlated Subquery vs. LEFT JOIN LATERAL

Suppose you only want the **amount** of the latest order; a scalar subquery can solve that too:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT o.amount
        FROM subquery_lab.orders AS o
        WHERE o.customer_id = c.customer_id
        ORDER BY o.ordered_at DESC, o.order_id DESC
        LIMIT 1
    ) AS latest_amount
FROM subquery_lab.customers AS c
ORDER BY c.customer_id;
```

However, if you simultaneously want `order_id`, `status`, `amount`, and `ordered_at` from **the same order**, writing multiple scalar subqueries repeating the same conditions is hard to maintain and risks inconsistency if each subquery uses slightly different selection criteria.

Using `LEFT JOIN LATERAL` has advantages:

- One query block clearly defines "the latest order".
- Returns multiple columns of the same selected row.
- Easily extends to top-N instead of just one value.
- Easy to verify `ORDER BY ... LIMIT ...` and filter conditions.

Example:

```sql
SELECT
    c.customer_id,
    r.order_id,
    r.amount,
    r.status
FROM subquery_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT order_id, amount, status
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 1
) AS r ON TRUE
ORDER BY c.customer_id;
```

**There is no universal rule that LATERAL is always faster than multiple scalar subqueries**. Performance also depends on indexes, column count, execution plan, statistics, and data. For expressing "one related row with multiple attributes", LATERAL is usually clearer.

---

## 17. Top-N and Maximum-Value Rows: Choosing the Right Approach

A common question:

> Find the highest-paid employee in each department.

There are two semantics to distinguish:

1. **All people sharing the highest salary** (keep ties).
2. **Pick exactly one representative per department** (requires a tie-breaker).

### 17.1. Correlated scalar subquery using MAX: keeps ties

```sql
SELECT
    e.department_id,
    e.employee_id,
    e.employee_name,
    e.salary
FROM subquery_lab.employees AS e
WHERE e.department_id IS NOT NULL
  AND e.salary = (
      SELECT MAX(e2.salary)
      FROM subquery_lab.employees AS e2
      WHERE e2.department_id = e.department_id
  )
ORDER BY e.department_id, e.employee_id;
```

Result:

| Dept | ID | Employee | Salary |
| ---: | ---: | --- | ---: |
| 10 | 2 | Bình | 4200 |
| 10 | 3 | Chi | 4200 |
| 20 | 5 | Hà | 3500 |
| 30 | 8 | Nam | 3200 |

Bình and Chi both reach the MAX of 4200, so both are kept. Unassigned employee Mai is excluded in this requirement.

### 17.2. Window function with RANK: also keeps ties

```sql
WITH ranked AS (
    SELECT
        e.department_id,
        e.employee_id,
        e.employee_name,
        e.salary,
        RANK() OVER (
            PARTITION BY e.department_id
            ORDER BY e.salary DESC
        ) AS salary_rank
    FROM subquery_lab.employees AS e
    WHERE e.department_id IS NOT NULL
)
SELECT
    department_id,
    employee_id,
    employee_name,
    salary
FROM ranked
WHERE salary_rank = 1
ORDER BY department_id, employee_id;
```

`RANK() = 1` keeps every employee tied for the highest salary. This is one way to replace a correlated MAX with a **window function**.

### 17.3. ROW_NUMBER: picks exactly one person by rule

```sql
WITH numbered AS (
    SELECT
        e.department_id,
        e.employee_id,
        e.employee_name,
        e.salary,
        ROW_NUMBER() OVER (
            PARTITION BY e.department_id
            ORDER BY e.salary DESC, e.employee_id ASC
        ) AS rn
    FROM subquery_lab.employees AS e
    WHERE e.department_id IS NOT NULL
)
SELECT
    department_id,
    employee_id,
    employee_name,
    salary
FROM numbered
WHERE rn = 1
ORDER BY department_id;
```

Result has **exactly one person per department**:

- Dept 10: Bình (ID 2), because of the tie at 4200 and ID 2 < ID 3.
- Dept 20: Hà (ID 5).
- Dept 30: Nam (ID 8).

This is a different business requirement from "everyone holding the highest salary". When ties must be kept, do not replace `RANK` with `ROW_NUMBER` without evaluating the requirement.

### 17.4. DISTINCT ON: a PostgreSQL-specific option

PostgreSQL supports `DISTINCT ON` to take the first row per group based on sort order:

```sql
SELECT DISTINCT ON (e.department_id)
    e.department_id,
    e.employee_id,
    e.employee_name,
    e.salary
FROM subquery_lab.employees AS e
WHERE e.department_id IS NOT NULL
ORDER BY
    e.department_id,
    e.salary DESC,
    e.employee_id ASC;
```

Rules:

- `DISTINCT ON (department_id)` keeps one row per department.
- The DISTINCT ON expressions must match the appropriate leading expressions of `ORDER BY`.
- `salary DESC, employee_id ASC` determines which row is picked in each department.

Some requirements need top-N (N > 1), in which case `ROW_NUMBER` or `LATERAL ... LIMIT N` can be more convenient.

### 17.5. Do not infer top-N from MAX when the full row is needed

`SELECT MAX(salary) GROUP BY department_id` only returns the salary amount; it **does not automatically return the identity of the employee** earning that salary. To get the employee too, you must join back, use a correlated query, window function, or LATERAL depending on tie-keeping and row-count needs.

---

## 18. Using Subqueries in WHERE for Group-Level Comparisons

Besides "higher than department average", many other filters can be written.

### 18.1. Employees earning the company's highest salary

```sql
SELECT employee_id, employee_name, salary
FROM subquery_lab.employees
WHERE salary = (
    SELECT MAX(salary)
    FROM subquery_lab.employees
)
ORDER BY employee_id;
```

Result: Bình and Chi (both 4200).

### 18.2. Departments with at least two employees

A correlated scalar subquery:

```sql
SELECT d.department_id, d.department_name
FROM subquery_lab.departments AS d
WHERE (
    SELECT COUNT(*)
    FROM subquery_lab.employees AS e
    WHERE e.department_id = d.department_id
) >= 2
ORDER BY d.department_id;
```

Result: departments **10, 20, 30**.

An alternative using aggregate and HAVING:

```sql
SELECT d.department_id, d.department_name
FROM subquery_lab.departments AS d
JOIN subquery_lab.employees AS e
  ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
HAVING COUNT(*) >= 2
ORDER BY d.department_id;
```

Both have the same meaning on the lab data. The second option can fit well if you already need to aggregate multiple metrics; the first directly expresses "how many employees each department has".

### 18.3. Departments with no employees

```sql
SELECT d.department_id, d.department_name
FROM subquery_lab.departments AS d
WHERE NOT EXISTS (
    SELECT 1
    FROM subquery_lab.employees AS e
    WHERE e.department_id = d.department_id
)
ORDER BY d.department_id;
```

Result: only department **40 — Legal**.

A scalar COUNT version can also be written:

```sql
WHERE (
    SELECT COUNT(*)
    FROM subquery_lab.employees AS e
    WHERE e.department_id = d.department_id
) = 0
```

However, `NOT EXISTS` usually conveys "no matching rows exist" more directly. PostgreSQL can also optimize it into an **anti-join**.

---

## 19. Subqueries in SELECT and Column Naming Requirements

When selecting an expression/subquery, give it an alias so the result has a convenient column name in the application:

```sql
SELECT
    d.department_id,
    d.department_name,
    (
        SELECT COUNT(*)
        FROM subquery_lab.employees AS e
        WHERE e.department_id = d.department_id
    ) AS employee_count
FROM subquery_lab.departments AS d;
```

Without `AS employee_count`, drivers or SQL tools may return a column name that is awkward to use in code.

However, an alias defined in the SELECT list **is not automatically available in every clause of the same query block**. For example, do not assume you can write:

```sql
SELECT
    (
        SELECT COUNT(*)
        FROM subquery_lab.employees
    ) AS employee_count
WHERE employee_count > 0;
```

Syntax and alias visibility across clauses have their own rules; `WHERE` cannot use a SELECT alias this way.

If you need to filter on the computed result, place the subquery inside a derived table or CTE:

```sql
SELECT q.department_id, q.employee_count
FROM (
    SELECT
        d.department_id,
        (
            SELECT COUNT(*)
            FROM subquery_lab.employees AS e
            WHERE e.department_id = d.department_id
        ) AS employee_count
    FROM subquery_lab.departments AS d
) AS q
WHERE q.employee_count > 0
ORDER BY q.department_id;
```

Result: departments 10, 20, 30.

### 19.1. Do not carelessly use SELECT * in large derived tables

`SELECT *` is convenient while learning, but in complex data-combining queries it can:

- Fetch unnecessary columns.
- Create duplicate column names across tables.
- Cause unexpected API output changes when schemas evolve.
- Increase data transfer volume.
- Make it harder to tell the grain of intermediate datasets.

For reports using multiple derived tables, explicitly list the columns actually needed and give them clear aliases.

---

## 20. Subqueries with Composite Keys and Multi-Tenancy

A correlation condition often needs **more than one column**.

Suppose an application has multiple tenants, and each tenant uses an `external_id` starting at 1. If you look up an order by `external_id` without also matching `tenant_id`, the subquery can pull **another tenant's data**.

Conceptually correct pattern:

```sql
SELECT a.tenant_id, a.external_id
FROM tenant_source AS a
WHERE NOT EXISTS (
    SELECT 1
    FROM tenant_target AS b
    WHERE b.tenant_id = a.tenant_id
      AND b.external_id = a.external_id
);
```

These two tables are **illustrative schema examples**, not part of the lab tables created earlier. In real systems, combine tenant predicates with access permissions and Row-Level Security where applicable—do not treat writing the right SQL condition as the sole security measure.

### 20.1. Watch out for NULL in composite keys

With the condition:

```sql
b.external_id = a.external_id
```

if either column is NULL, the comparison is not TRUE.

If business logic genuinely wants two NULLs to be treated as equivalent, use:

```sql
b.external_id IS NOT DISTINCT FROM a.external_id
```

However, **two unknown IDs are not necessarily the same entity**. In many problems, you should forbid NULL in business key components and handle input rows with missing codes separately.

### 20.2. Subqueries do not replace unique or foreign keys

A `NOT EXISTS` query checking that "no matching row exists yet" is **a snapshot read**; it does not prevent another transaction from inserting a matching row immediately afterward.

If a `(tenant_id, external_id)` pair must be unique, add an appropriate `UNIQUE`/`PRIMARY KEY` constraint to enforce it under concurrency. If a value must reference an existing entity, use a `FOREIGN KEY` according to your data model.

---

## 21. Subqueries in UPDATE/DELETE Operations: Exercise Caution

Subqueries do not appear only in SELECT. They can also determine the target rows of an UPDATE or DELETE.

Example: give a **5%** raise to employees whose salary is below their department average, provided they belong to an assigned department.

> **Run only on the lab database.** To avoid mutating data for later examples, wrap the entire operation in a transaction and `ROLLBACK`.

```sql
BEGIN;

UPDATE subquery_lab.employees AS e
SET salary = ROUND(e.salary * 1.05, 2)
WHERE e.department_id IS NOT NULL
  AND e.salary < (
      SELECT AVG(e2.salary)
      FROM subquery_lab.employees AS e2
      WHERE e2.department_id = e.department_id
  )
RETURNING
    e.employee_id,
    e.employee_name,
    e.department_id,
    e.salary;

ROLLBACK;
```

In the initial dataset, the employees earning below their department average are An, Dũng, and Lan; they can be updated inside the lab transaction and then rolled back.

**Note on snapshots and data modifications:** in complex DML, reads within the same statement and write effects follow specific MVCC rules. Do not mechanically assume PostgreSQL updates one employee at a time and uses that new salary when computing the average for the next person. For a real payroll process, design data sources, snapshots, transactions, and reconciliation explicitly.

### 21.1. DELETE using NOT EXISTS

A general example:

```sql
-- ILLUSTRATIVE ONLY: clearly verify target row scope before running DELETE.
DELETE FROM some_staging_table AS s
WHERE NOT EXISTS (
    SELECT 1
    FROM master_table AS m
    WHERE m.business_key = s.business_key
);
```

In production, DELETE is a destructive operation and can be affected by concurrency, foreign keys, and other processes. Run a SELECT first to inspect the affected rows, have a backup/recovery plan, and execute only with authorized permissions.

Using a subquery in DML is no reason to skip data constraints or change-scope review.

---

## 22. Performance: Does a Correlated Subquery Always Run N Times?

A common description is:

> For each outer row, PostgreSQL runs the subquery once.

That is a **useful mental model**, especially when the correlation condition depends on the outer row. However, PostgreSQL has a query optimizer; **the actual execution plan is not necessarily a literal loop as described**.

Depending on the structure, the planner may:

- Run an independent subquery as an `InitPlan` and reuse the result.
- Create a parameterized `SubPlan` and execute it repeatedly for outer rows.
- Rewrite `EXISTS` into a **Semi Join**.
- Rewrite `NOT EXISTS` into an **Anti Join**.
- Use a **Hash Join**, **Merge Join**, or **Nested Loop**.
- Use indexes to locate matching rows faster.
- Push certain conditions down to child tables, merge query blocks, or materialize as appropriate.

Therefore, you cannot conclude "a correlated subquery is always slower than a JOIN" from syntax alone.

### 22.1. Inspecting the plan with EXPLAIN

```sql
EXPLAIN
SELECT e.employee_id, e.employee_name, e.salary
FROM subquery_lab.employees AS e
WHERE e.salary > (
    SELECT AVG(e2.salary)
    FROM subquery_lab.employees AS e2
    WHERE e2.department_id = e.department_id
);
```

To get execution metrics on a **SELECT**:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT e.employee_id, e.employee_name, e.salary
FROM subquery_lab.employees AS e
WHERE e.salary > (
    SELECT AVG(e2.salary)
    FROM subquery_lab.employees AS e2
    WHERE e2.department_id = e.department_id
);
```

`EXPLAIN ANALYZE` **actually executes the statement**. For INSERT/UPDATE/DELETE, do not run it directly on production just to inspect a plan, as it will modify data. In the lab, the example uses a read-only SELECT.

### 22.2. Details to read in a plan

| Component | Meaning when observed |
| --- | --- |
| `SubPlan` | A subquery executed via the subplan mechanism |
| `InitPlan` | An independent subquery executed once to produce an initial parameter |
| `Nested Loop` | A loop-based join between outer and inner sources |
| `Hash Join / Hash Anti Join` | Joining or anti-matching using a hash table |
| `Semi Join` | Only checks whether a match exists without duplicating outer rows |
| `Aggregate / HashAggregate` | Computes aggregation, either in a subquery or after a join |
| `WindowAgg` | Executes window functions |
| `Limit` | Selects at most the requested number of rows, often with Sort/Index |
| `loops` | Number of times the node was executed as instrumented by EXPLAIN ANALYZE |
| `actual rows` | Actual rows processed/returned by the node per instrumentation stats |
| `Buffers` | Buffer activity involved, useful for diagnosing I/O causes |

A plan must also be understood alongside statistics, index structure, selectivity, and data size. Do not draw conclusions from a single node or a benchmark on a few-row table.

### 22.3. Indexes for correlation conditions

For example, common predicates:

```sql
WHERE o.customer_id = c.customer_id
```

and:

```sql
WHERE e2.department_id = e.department_id
```

can be supported by indexes:

```sql
CREATE INDEX idx_orders_customer_id
ON subquery_lab.orders (customer_id);

CREATE INDEX idx_employees_department_id
ON subquery_lab.employees (department_id);
```

For LATERAL finding the latest order:

```sql
CREATE INDEX idx_orders_customer_latest
ON subquery_lab.orders (
    customer_id,
    ordered_at DESC,
    order_id DESC
);
```

This index can help PostgreSQL locate a customer's orders in the desired order and stop after `LIMIT 1` without sorting all rows each time, depending on the plan.

For the "no PAID orders" query:

```sql
CREATE INDEX idx_orders_paid_customer
ON subquery_lab.orders (customer_id)
WHERE status = 'PAID';
```

This is a **partial index**, which can be effective if queries frequently examine only PAID status and the data distribution fits.

You do not need to create all of these indexes in a real system: indexes add storage, INSERT/UPDATE/DELETE overhead, and maintenance cost. Choose based on workload and inspect `EXPLAIN`.

### 22.4. Why aren't indexes used in the lab?

The dataset has only 8 employees and 6 orders. A sequential scan can be cheaper than an index scan. If `EXPLAIN` chooses a full table scan, that **does not prove indexes have no effect** on larger datasets.

### 22.5. Do not use LIMIT 1 to "fix" a logically wrong subquery

A scalar subquery returning multiple rows is a signal:

- You have not identified a unique key.
- Unexpected duplicate data exists.
- You actually need an aggregate.
- You actually need a list of rows, not a single value.

Adding `LIMIT 1` stops the SQL statement from raising an error, but it can **hide corrupted data** or pick an arbitrary record. Only use LIMIT when business rules clearly define a selection rule and there is a complete ORDER BY.

---

## 23. Comparing Subqueries, JOINs, Window Functions, and CTEs

Consider the requirement: **each employee along with their department's average salary**.

### 23.1. Correlated scalar subquery

```sql
SELECT
    e.employee_id,
    e.employee_name,
    e.department_id,
    e.salary,
    (
        SELECT AVG(e2.salary)
        FROM subquery_lab.employees AS e2
        WHERE e2.department_id = e.department_id
    ) AS department_avg
FROM subquery_lab.employees AS e
ORDER BY e.employee_id;
```

Advantage: closely matches the phrasing "for each employee, compute the average of that department". Drawback: it may perform similar work repeatedly if the planner does not optimize it into a shared plan.

### 23.2. JOIN with an aggregated derived table

```sql
SELECT
    e.employee_id,
    e.employee_name,
    e.department_id,
    e.salary,
    s.department_avg
FROM subquery_lab.employees AS e
LEFT JOIN (
    SELECT
        department_id,
        AVG(salary) AS department_avg
    FROM subquery_lab.employees
    WHERE department_id IS NOT NULL
    GROUP BY department_id
) AS s
  ON s.department_id = e.department_id
ORDER BY e.employee_id;
```

Advantage: computes statistics **by group** and joins once using relational logic. This is often easier to reason about on large tables when multiple department-level statistics are needed.

### 23.3. Window function

```sql
SELECT
    e.employee_id,
    e.employee_name,
    e.department_id,
    e.salary,
    CASE
        WHEN e.department_id IS NOT NULL
            THEN AVG(e.salary) OVER (
                PARTITION BY e.department_id
            )
        ELSE NULL
    END AS department_avg
FROM subquery_lab.employees AS e
ORDER BY e.employee_id;
```

Here the window function computes the group average **while keeping every employee row**.

Note: `PARTITION BY department_id` treats rows with NULL `department_id` as a single partition. To preserve the **exact semantics** of the subquery using `=` from earlier (where Mai gets a NULL `department_avg`), the example uses `CASE WHEN e.department_id IS NOT NULL THEN ... ELSE NULL END`.

If business logic treats all unassigned employees as one group, you can drop that CASE, though the **semantics then differ**.

### 23.4. Choosing by meaning and workload

| Goal | Approach usually worth considering |
| --- | --- |
| One shared statistic across all rows | Uncorrelated scalar subquery or CTE |
| One specific statistic per outer row | Correlated scalar subquery |
| Multiple group aggregates then joined | Derived table / CTE + JOIN |
| Keep every row and compute partition metrics | Window function |
| Only check if related rows exist | EXISTS |
| Only check if no related rows exist | NOT EXISTS |
| One or top-N related rows per outer row | LATERAL with ORDER BY/LIMIT |
| One representative row per group in PostgreSQL | DISTINCT ON or ROW_NUMBER |
| Need to keep all tied rows | Correlated MAX / RANK / DENSE_RANK |
| Large dataset and slow query | Compare EXPLAIN, indexes, statistics, selectivity |

**No single syntax is always superior**. Choose the version that expresses the intent accurately and readably first; optimize based on execution evidence.

---

## 24. Common Semantic Mistakes

### 24.1. Forgetting GROUP BY and getting the wrong aggregate

```sql
SELECT AVG(salary)
FROM subquery_lab.employees;
```

returns the company-wide average.

If the requirement is per department, you must include `GROUP BY department_id` or a correlation condition to the right department. Do not confuse the two problems.

### 24.2. Comparing against a multi-row subquery

```sql
-- Wrong when the subquery returns multiple salaries:
WHERE salary = (
    SELECT salary
    FROM subquery_lab.employees
    WHERE department_id = 10
)
```

If you want "equal to **any** salary in department 10", use:

```sql
WHERE salary IN (
    SELECT salary
    FROM subquery_lab.employees
    WHERE department_id = 10
)
```

If you want "equal to the **highest** salary in department 10", use:

```sql
WHERE salary = (
    SELECT MAX(salary)
    FROM subquery_lab.employees
    WHERE department_id = 10
)
```

Those two answers correspond to **two different requirements**.

### 24.3. Forgetting inner and outer aliases

```sql
WHERE department_id = department_id
```

may simply compare the same column within the same query block. Write explicitly:

```sql
WHERE inner_e.department_id = outer_e.department_id
```

### 24.4. Failing to verify uniqueness before using scalar context

A subquery having only one column does not mean it has only one row. If a subquery returns multiple orders, a scalar context will error. Choose an aggregate, unique key condition, or table-valued structure.

### 24.5. Applying COALESCE too early

If `AVG(salary)` for a department with no employees returns NULL, turning it into 0 can mislead reports into thinking the department has an **average salary of 0**. Use `COALESCE` only when business logic defines 0 as the appropriate display value.

### 24.6. ORDER BY missing a tie-breaker

`ORDER BY ordered_at DESC LIMIT 1` is not enough to identify a unique order if multiple orders share the same timestamp. Add a tie-breaker, such as `order_id DESC`, if that is a valid policy.

### 24.7. Turning LEFT JOIN into INNER JOIN via WHERE

If you want to keep customers without orders:

```sql
SELECT c.customer_id, o.order_id
FROM subquery_lab.customers AS c
LEFT JOIN subquery_lab.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

the condition `WHERE o.status = 'PAID'` eliminates unmatched right-hand rows (where status is NULL), thus dropping customers who have no orders.

If you want to **keep every customer and only match PAID orders**, put the condition in `ON`:

```sql
SELECT c.customer_id, o.order_id
FROM subquery_lab.customers AS c
LEFT JOIN subquery_lab.orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID';
```

When you need **one** latest PAID order per customer, use LEFT JOIN LATERAL with the PAID filter inside and LIMIT 1.

### 24.8. Using subqueries to validate data instead of constraints

`NOT EXISTS` does not replace a unique constraint under concurrency; `IN` does not replace a foreign key; a scalar lookup does not guarantee the referenced record will continue to exist.

### 24.9. Prematurely optimizing by changing SQL structure

A rewritten JOIN query can multiply rows on a 1-N relationship. A window function can group NULLs differently than correlated equality. A `DISTINCT ON` can drop tied rows that a correlated MAX preserves.

**Before comparing speed, prove that the two queries share the same meaning and return the exact same result set on edge-case data.**

---

## 25. Input Parameters and SQL Safety

A subquery in an application often receives user-supplied conditions: customer ID, order status, price range, start/end dates.

Never concatenate request values directly into SQL:

```text
"WHERE o.customer_id = " + userInput
```

Instead, use the driver's **prepared statements / bind parameters**.

PostgreSQL prepared statement example:

```sql
PREPARE latest_paid_order_for_customer(INTEGER) AS
SELECT
    c.customer_id,
    c.customer_name,
    r.order_id,
    r.amount
FROM subquery_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.amount
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 1
) AS r ON TRUE
WHERE c.customer_id = $1;

EXECUTE latest_paid_order_for_customer(101);

DEALLOCATE latest_paid_order_for_customer;
```

For customer 101, this is one way to fetch the latest PAID order according to the defined rules. Customers with no PAID orders are still returned with NULL `r` columns thanks to LEFT JOIN LATERAL, provided a matching `customers` row exists.

When handling multi-tenant data:

- Authenticate and authorize the caller.
- Enforce the tenant policy in **every** relevant subquery and join.
- Consider Row-Level Security where appropriate.
- Bind input parameters; never let clients supply arbitrary SQL fragments.
- Cap row counts/top-N when an endpoint allows clients to specify LIMIT.

A subquery is not a security boundary; it is just a SQL construct.

---

## 26. Data and Concurrency: Subqueries Do Not Lock the Future

Suppose you find customers who have no PAID orders using NOT EXISTS and decide to grant them a promotion. Meanwhile, another transaction might insert a new PAID order.

A SELECT that is true at the moment it runs does not mean its result will **remain unchanged in the future**.

```text
Transaction A:
  SELECT ... WHERE NOT EXISTS(order PAID) -> sees customer 104

Transaction B:
  INSERT PAID order for customer 104
  COMMIT

Transaction A:
  Grants promotion based on stale result
```

If business logic requires guaranteeing "each customer receives at most one promotion", place an appropriate `UNIQUE(customer_id, campaign_id)` constraint on the promotions table and handle `ON CONFLICT` according to policy. If the requirement also depends strictly on order state at commit time, you may need transactions, locking, `SERIALIZABLE` isolation with retries where appropriate, or workflow coordination keyed by business key.

Do not treat `NOT EXISTS` or a scalar subquery as an automatic locking mechanism that prevents other transactions from creating data.

---

## 27. Practice Exercises

### Exercise 1 — One shared value for all rows

Write SQL returning each employee along with:

- Their `salary`.
- The company-wide average using an uncorrelated scalar subquery.
- A boolean column indicating whether their salary is greater than the average.

The lab dataset has a company-wide average of **3250**. How many employees earn above this level?

### Exercise 2 — Scalar subqueries with 0 and multiple rows

Run each statement:

```sql
SELECT (
    SELECT amount
    FROM subquery_lab.orders
    WHERE customer_id = 104
) AS no_order_amount;

SELECT (
    SELECT amount
    FROM subquery_lab.orders
    WHERE customer_id = 101
) AS multiple_order_amount;
```

Explain why the first query returns NULL while the second raises an error. Rewrite the second query to return **SUM(amount)** instead of multiple rows.

### Exercise 3 — Higher than department average

Find employees whose salary is higher than **their own department's** average using a correlated scalar subquery. Expected result: **Bình, Chi, Hà, Nam**.

Explain why a query missing `e2.department_id = e.department_id` can yield a different result.

### Exercise 4 — Departments with no employees

Write:

1. Correlated scalar subquery `COUNT(*) = 0`.
2. `NOT EXISTS`.
3. `LEFT JOIN ... WHERE e.employee_id IS NULL`.

All three must find department **40 — Legal**. Why is `AVG(salary) = 0` not the right way to find empty departments?

### Exercise 5 — Aggregated derived table

Write a derived table returning `department_id`, `employee_count`, and `avg_salary`. `LEFT JOIN` it with `departments` so department 40 is still preserved.

Why does department 40 have a NULL count in the derived table before applying `COALESCE`, whereas a standalone scalar subquery `COUNT(*)` for department 40 returns 0?

### Exercise 6 — All customers including those without orders

Write a derived table aggregating order counts by `customer_id` and `LEFT JOIN` it onto the `customers` table. The result must include **5 customers**, including 104 and 105. Separate `COUNT(*)` of all orders from `SUM(amount) FILTER (WHERE status='PAID')`.

Predict the PAID totals for customers 101 and 103.

### Exercise 7 — EXISTS and JOIN

Find customers with at least one PAID order using `EXISTS`. Expected result: 101, 102, 103.

Write an `INNER JOIN` version and explain why customer 101 can appear twice. When does `DISTINCT` need to be used? Why does `EXISTS` express "at least one" more clearly?

### Exercise 8 — NOT EXISTS and NOT IN

Query the list of customers with no orders using `NOT EXISTS`, expecting 104 and 105.

Then test:

```sql
SELECT 1 NOT IN (2, 3, NULL);
```

Why must you not blindly replace NOT EXISTS with NOT IN over a nullable column of a staging table?

### Exercise 9 — Latest order with LATERAL

Write `LEFT JOIN LATERAL` to get each customer's latest order using:

```sql
ORDER BY ordered_at DESC, order_id DESC
LIMIT 1
```

Verify that customer 103 receives order **1005** on the timestamp tie, and that 104 and 105 still appear with a NULL `order_id`.

Try `CROSS JOIN LATERAL` and describe the difference.

### Exercise 10 — Top two orders per customer

Change `LIMIT 1` to `LIMIT 2` in LATERAL. Explain the row count per customer and why `LEFT JOIN LATERAL` produces a NULL-extended row for customers with no orders.

### Exercise 11 — Highest per department, keeping ties or not

Find the highest-paid employee(s) in each department using:

1. Correlated `MAX(salary)` (keeps tied employees).
2. `RANK() OVER (PARTITION BY department_id ORDER BY salary DESC)`.
3. `ROW_NUMBER()` with tie-breaker `employee_id ASC`.
4. `DISTINCT ON (department_id)`.

Explain why methods 1 and 2 return both **Bình and Chi** for department 10, while methods 3 and 4 return only one person.

### Exercise 12 — ANY/ALL and empty sets

Use `>= ALL (SELECT salary ... WHERE department_id = e.department_id)` to find the highest salary in each department.

Why must you review Mai's `department_id IS NULL` case? What is the result of `>= ALL(empty set)`?

### Exercise 13 — Null-safe equality

Compare:

```sql
SELECT
    NULL::INTEGER = NULL::INTEGER AS equals_null,
    NULL::INTEGER IS NOT DISTINCT FROM NULL::INTEGER
        AS null_safe_equals;
```

Rewrite the department-average scalar subquery to **group unassigned employees** together using `IS NOT DISTINCT FROM`. Explain the impact on Mai's result.

### Exercise 14 — Analyzing the execution plan

Run:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.customer_id
FROM subquery_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM subquery_lab.orders AS o
    WHERE o.customer_id = c.customer_id
);
```

Observe which plan type PostgreSQL chooses on the small tables. Why should you not assume the plan on 6 orders will match the plan when `orders` has millions of rows?

### Exercise 15 — Choosing a design for a real-world report

Requirement: for each customer, display the count of PAID orders, total PAID amount, latest PAID `order_id`, and the timestamp of that order. Include customers with no orders.

Propose a query combining:

- A derived table or CTE aggregated by `customer_id`.
- `LEFT JOIN LATERAL` to fetch the latest PAID order.
- `COALESCE` for order count/total amount per reporting rules.

Explain the distinct role of each part and why you should not use multiple separate scalar subqueries without a consistent ORDER BY.

---

## 28. Common Errors and How to Fix Them

| Symptom | Cause | Fix |
| --- | --- | --- |
| Scalar subquery reports "more than one row" | Subquery returns multiple rows | Re-examine the problem: aggregate, unique filter, LIMIT with ORDER BY, or derived table |
| Scalar subquery returns NULL | Zero rows, or value/aggregate is NULL | Check COUNT/EXISTS; apply COALESCE only when appropriate |
| Wrong department average | Forgot correlation on `department_id` | Use explicit aliases for inner and outer tables |
| "Same department" query drops NULL employees | `= NULL` evaluates to UNKNOWN | Decide whether to exclude them or use null-safe equality |
| Derived table cannot access outer column | Missing LATERAL for subquery in FROM | Use `JOIN LATERAL` if referencing preceding tables |
| LEFT JOIN LATERAL drops customers with no orders | Used CROSS/INNER JOIN LATERAL | Use `LEFT JOIN LATERAL ... ON TRUE` |
| LIMIT 1 picks an unstable order | Missing ORDER BY or missing tie-breaker | Sort by timestamp then a stable tie-breaking key |
| EXISTS produces multiple rows? | Confused with JOIN | EXISTS is an existence check and does not duplicate outer rows |
| NOT IN unexpectedly returns empty | Subquery contains NULL | Analyze NULLs; prefer NOT EXISTS when finding missing rows |
| JOIN multiplies SUM/COUNT | 1-N data or joining extra detail tables | Aggregate at the right grain before joining |
| Empty department AVG becomes 0 unintentionally | Unconditionally applying COALESCE to all aggregates | Distinguish missing data from a 0 value |
| CTE is not faster | A CTE is not automatically an index or cache | Check the plan and adjust structure based on evidence |
| Window function differs from scalar subquery | Different NULL grouping or filter logic | Verify against edge-case data |
| DISTINCT ON drops tied rows | It picks one row per group | Use RANK/MAX if ties must be preserved |
| Correlated query runs slowly | Repeated SubPlan, missing index, large row count | Run EXPLAIN, index join keys, consider GROUP+JOIN/window |
| Duplicate writes after NOT EXISTS | Two transactions both saw a missing row | Use UNIQUE constraints, transactions, and retry/idempotency |
| Other tenant's data included in subquery | Missing part of a composite key | Add `tenant_id` predicates and access controls |
| Production query breaks after schema change | Unqualified column names resolved differently | Fully qualify with aliases and add regression tests |

---

## 29. Checklist When Writing Subqueries in PostgreSQL

| Question | How to verify |
| --- | --- |
| Does the goal need one value or a table? | Scalar subquery or derived table |
| Is the scalar subquery guaranteed at most one row? | Unique key, aggregate, or intentional ORDER BY/LIMIT |
| If there are no rows, what should the result be? | NULL, 0, drop row, or another value per business logic |
| Does it reference outer query columns? | Use explicit aliases and confirm correlation |
| Does a derived table need columns from a preceding table in FROM? | Use LATERAL |
| Should outer rows be kept when there is no match? | LEFT JOIN / LEFT JOIN LATERAL |
| Do you need one or multiple related rows? | LIMIT 1, LIMIT N, aggregate, or window |
| If there is a tie, how should it be picked or kept? | Tie-breaker, RANK, ROW_NUMBER, or DISTINCT ON |
| Is the condition "row exists" or "value equals"? | EXISTS or IN/= depending on meaning |
| Is the condition "no row exists"? | Usually NOT EXISTS |
| Are there NULLs in keys or value sets? | Check three-valued logic, NOT IN, IS NOT DISTINCT FROM |
| Are there composite/tenant keys? | Match all referencing columns |
| Are there groupings/aggregates? | Identify grain; avoid double-counting/summing after joins |
| Is COALESCE used? | Distinguish 0 from missing data |
| Is a CTE needed for readability? | Use WITH, but do not assume materialization |
| Does the result need ordering? | Final ORDER BY and tie-breaker for top-N |
| Is the dataset large? | EXPLAIN (ANALYZE, BUFFERS), indexes, and statistics |
| Is the result used for data writes? | Constraints, transactions, locking, concurrency, and retries |
| Are there user-input parameters? | Prepared statements, authorization, and tenant scope |
| Are alternative query versions truly equivalent? | Test on NULLs, duplicates, empty sets, ties, and unmatched rows |

## Conclusion

In PostgreSQL, **subqueries** allow nesting one SELECT inside another query to compute a value, build an intermediate relation, or check related records.

- **Scalar subqueries** return one value: one row/one column is valid, zero rows yield NULL, and more than one row raises an error. Use aggregates or ORDER BY/LIMIT when the problem genuinely requires a well-defined single value.
- **Table subqueries** produce multi-row/multi-column results, commonly in FROM/JOIN. They are useful for aggregating by group before joining, separating logical steps, or avoiding data duplication caused by one-to-many relationships.
- **Correlated subqueries** reference columns from the outer query. They can be scalar, EXISTS, NOT EXISTS, or LATERAL tables; hence "correlated" is a referencing property rather than a separate result shape.
- **`LATERAL`** lets a subquery in FROM use columns from preceding tables, making it especially suitable for latest-row or top-N-per-group problems.
- **`EXISTS` and `NOT EXISTS`** directly express the presence or absence of related rows, often clearer than JOINs that can create duplicates or `NOT IN` queries that hit NULL pitfalls.
- **JOINs, CTEs, window functions, and DISTINCT ON** can express similar queries, but they are not always equivalent in how they handle NULLs, ties, duplicates, and row counts.

Writing good subqueries starts with defining the **result shape**, **linking keys**, **NULL semantics**, **expected row count**, and **business intent**. Once the SQL is correct, use EXPLAIN and realistic data to decide on optimizations. That approach keeps analytical, reporting, and advanced filtering queries clear, reliable, and maintainable.
