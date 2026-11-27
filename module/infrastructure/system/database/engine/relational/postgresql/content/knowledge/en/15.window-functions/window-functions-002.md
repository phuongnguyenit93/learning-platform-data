# Distinguishing Group Aggregation from Window Functions in PostgreSQL

## 1. Same sum calculation, but two different data questions

Suppose you have an employees table where each employee belongs to a department and has a salary. You want to know:

- **How many employees does each department have, and what is its total salary?**
- **What is each employee's salary, and what is the total salary of that employee's department?**

The first question requires **group aggregation** with `GROUP BY`: multiple employee rows are collapsed into **one row per department**.

The second question requires a **window function** with `OVER (...)`: it still preserves **each employee row**, while adding metrics calculated over the related group of employees.

Both calculations can use the same `SUM` function, yet the results have different **row granularity (grain)**:

```text
SOURCE DATA                GROUP BY dept_id
1. An   - dept 10          dept 10 | 3 people | 51 million
2. Bình - dept 10          dept 20 | 2 people | 50 million
3. Chi  - dept 10          dept 30 | 3 people | 40 million
4. Dũng - dept 20
5. Hà   - dept 20          8 rows -> 3 rows
6. Lan  - dept 30
7. Minh - dept 30
8. Phúc - dept 30

                           WINDOW OVER (PARTITION BY dept_id)
                           An   | dept 10 | 51 million
                           Bình | dept 10 | 51 million
                           Chi  | dept 10 | 51 million
                           Dũng | dept 20 | 50 million
                           Hà   | dept 20 | 50 million
                           Lan  | dept 30 | 40 million
                           Minh | dept 30 | 40 million
                           Phúc | dept 30 | 40 million

                           8 rows -> still 8 rows
```

**Core rule:** `GROUP BY` changes the result granularity to one row per group; a window function calculates over a set of related rows **without collapsing those rows into a single row**.

This is a semantic difference, not merely a syntactic one.

### What will you learn?

After this lesson, you will be able to:

1. Distinguish standard aggregates from aggregates invoked as window functions.
2. Understand `GROUP BY`, `HAVING`, `OVER`, `PARTITION BY`, `ORDER BY`, and window frames.
3. Explain why `SUM(salary)` and `SUM(salary) OVER (PARTITION BY ...)` produce different output row counts.
4. Use window functions to compute group totals, shares, group averages, rankings, cumulative totals, and differences from preceding rows.
5. Combine `GROUP BY` and window functions in the same query when you need reports like "group by day, then accumulate across days".
6. Avoid the `ROWS` vs. `RANGE` pitfall when `ORDER BY` values contain ties.
7. Filter rows based on window results using CTEs/subqueries in the proper evaluation order.
8. Recognize `COUNT(*)`, `NULL`, `DISTINCT`, one-to-many joins, and aggregation pitfalls.
9. Read PostgreSQL plans with `EXPLAIN` for large datasets.
10. Choose the query pattern based on **required output row count**, rather than picking functions out of habit.

## 2. Setting up the PostgreSQL practice dataset

This lesson uses two independent datasets: **employees–departments** and **daily sales**. The SQL assumes you are practicing on a lab database with a role permitted to create schemas/tables. Do not run sample table creation/insertion statements directly on production.

### 2.1. Departments table

```sql
CREATE SCHEMA IF NOT EXISTS window188;

CREATE TABLE window188.departments (
    department_id integer PRIMARY KEY,
    department_name text NOT NULL UNIQUE
);

INSERT INTO window188.departments(department_id, department_name)
VALUES
    (10, 'Sales'),
    (20, 'Engineering'),
    (30, 'Customer Support'),
    (40, 'Legal');
```

Department 40 has no employees yet. This will help distinguish a group report based solely on the employees table from one that aims to retain **empty departments as well**.

### 2.2. Employees table

To keep calculations easy to verify, salaries are stored in **millions of VND** in the integer column `salary_million`. This is for learning purposes, not a recommendation to use integer millions for accounting in real payroll systems.

```sql
CREATE TABLE window188.employees (
    employee_id integer PRIMARY KEY,
    employee_name text NOT NULL,
    department_id integer NOT NULL
        REFERENCES window188.departments(department_id),
    salary_million integer NOT NULL
        CHECK (salary_million > 0),
    hired_on date NOT NULL
);

INSERT INTO window188.employees(
    employee_id,
    employee_name,
    department_id,
    salary_million,
    hired_on
)
VALUES
    (101, 'An',   10, 15, DATE '2026-01-10'),
    (102, 'Bình', 10, 18, DATE '2026-02-15'),
    (103, 'Chi',  10, 18, DATE '2026-03-20'),
    (104, 'Dũng', 20, 24, DATE '2026-01-05'),
    (105, 'Hà',   20, 26, DATE '2026-03-01'),
    (106, 'Lan',  30, 12, DATE '2026-02-01'),
    (107, 'Minh', 30, 12, DATE '2026-03-01'),
    (108, 'Phúc', 30, 16, DATE '2026-04-01');
```

Inspect the source table:

```sql
SELECT employee_id, employee_name,
       department_id, salary_million, hired_on
FROM window188.employees
ORDER BY department_id, employee_id;
```

| employee_id | employee_name | department_id | salary_million |
|---:|---|---:|---:|
| 101 | An | 10 | 15 |
| 102 | Bình | 10 | 18 |
| 103 | Chi | 10 | 18 |
| 104 | Dũng | 20 | 24 |
| 105 | Hà | 20 | 26 |
| 106 | Lan | 30 | 12 |
| 107 | Minh | 30 | 12 |
| 108 | Phúc | 30 | 16 |

Total salary in millions: `15 + 18 + 18 + 24 + 26 + 12 + 12 + 16 = 141`.

### 2.3. Daily sales data

We create another table to learn **cumulative totals and window frames**:

```sql
CREATE TABLE window188.sales (
    sale_id integer PRIMARY KEY,
    sold_on date NOT NULL,
    amount integer NOT NULL CHECK (amount >= 0)
);

INSERT INTO window188.sales(sale_id, sold_on, amount)
VALUES
    (1001, DATE '2026-01-05', 100),
    (1002, DATE '2026-01-05',  40),
    (1003, DATE '2026-01-06',  20),
    (1004, DATE '2026-01-08',  60),
    (1005, DATE '2026-02-01',  90),
    (1006, DATE '2026-02-05',  10);
```

Count: 6 sales, total amount 320 units. **Jan 05 has two sales**, intentionally creating rows sharing the same `sold_on` value so you can observe the difference between the default window frame and an explicit `ROWS` frame.

**Note:** If you re-run these `INSERT` statements on a lab table that already contains records with the same primary keys, PostgreSQL will raise a duplicate key error. Use a fresh lab schema or reset the fixture through an authorized procedure; do not arbitrarily delete data whose ownership is unclear.

## 3. Group aggregation: GROUP BY changes granularity

### 3.1. One result row per department

```sql
SELECT
    department_id,
    COUNT(*) AS employee_count,
    SUM(salary_million) AS total_salary_million,
    ROUND(AVG(salary_million), 2) AS avg_salary_million
FROM window188.employees
GROUP BY department_id
ORDER BY department_id;
```

Result:

| department_id | employee_count | total_salary_million | avg_salary_million |
|---:|---:|---:|---:|
| 10 | 3 | 51 | 17.00 |
| 20 | 2 | 50 | 25.00 |
| 30 | 3 | 40 | 13.33 |

From **8 employee rows**, the result shrinks to **3 department rows that have employees**.

When grouping by `department_id`:

- All employees in department 10 are collapsed into one group.
- All employees in department 20 form the second group.
- All employees in department 30 form the third group.
- Department 40 does not appear because no row in `employees` has `department_id = 40`.

### 3.2. GROUP BY does not preserve individual employees

Consider this query:

```sql
-- Invalid GROUP BY semantics in PostgreSQL:
SELECT
    department_id,
    employee_name,
    SUM(salary_million)
FROM window188.employees
GROUP BY department_id;
```

Because department 10's group has multiple employee names, PostgreSQL cannot arbitrarily pick an `employee_name` to represent the group. With this schema, the query fails because the column is neither grouped nor aggregated.

Basic rule: in a query with `GROUP BY`, columns in `SELECT` generally need to be:

- Expressions used for grouping.
- Aggregate results such as `SUM`, `COUNT`, `AVG`, `MIN`, `MAX`.
- Or expressions accepted by PostgreSQL under appropriate **functional dependency** rules.

Do not rely on "the first employee name in the group" when SQL does not define how to pick one.

### 3.3. GROUP BY on multiple columns creates smaller groups

```sql
SELECT
    department_id,
    salary_million,
    COUNT(*) AS employees_with_salary
FROM window188.employees
GROUP BY department_id, salary_million
ORDER BY department_id, salary_million;
```

Result:

| department_id | salary_million | employees_with_salary |
|---:|---:|---:|
| 10 | 15 | 1 |
| 10 | 18 | 2 |
| 20 | 24 | 1 |
| 20 | 26 | 1 |
| 30 | 12 | 2 |
| 30 | 16 | 1 |

It is still `GROUP BY`, but the **grain** is now "one row per department–salary pair", rather than one row per department.

**Every column added to GROUP BY can increase the number of groups**, because the grouping key definition changes.

## 4. Aggregates without GROUP BY: the whole table becomes one group

If you only want the total salary of the **entire table**:

```sql
SELECT
    COUNT(*) AS employees,
    SUM(salary_million) AS company_salary_million,
    ROUND(AVG(salary_million), 2) AS avg_salary_million
FROM window188.employees;
```

Result:

| employees | company_salary_million | avg_salary_million |
|---:|---:|---:|
| 8 | 141 | 17.63 |

There is no `GROUP BY` yet aggregates are present, so the entire row set after `FROM/WHERE` is treated as **a single aggregation group** and the query returns one row.

If the table is empty:

- `COUNT(*)` returns 0.
- `SUM` and `AVG` typically return NULL rather than 0.

This same distinction also appears with window aggregates when a partition contains no matching non-null values.

## 5. Window functions: OVER(PARTITION BY ...) preserves row-level detail

Now compute the sum and count per department, but **without collapsing individual employees**:

```sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary_million,
    COUNT(*) OVER (
        PARTITION BY department_id
    ) AS department_employee_count,
    SUM(salary_million) OVER (
        PARTITION BY department_id
    ) AS department_salary_million
FROM window188.employees
ORDER BY department_id, employee_id;
```

Result:

| employee_id | employee_name | department_id | salary_million | department_employee_count | department_salary_million |
|---:|---|---:|---:|---:|---:|
| 101 | An | 10 | 15 | 3 | 51 |
| 102 | Bình | 10 | 18 | 3 | 51 |
| 103 | Chi | 10 | 18 | 3 | 51 |
| 104 | Dũng | 20 | 24 | 2 | 50 |
| 105 | Hà | 20 | 26 | 2 | 50 |
| 106 | Lan | 30 | 12 | 3 | 40 |
| 107 | Minh | 30 | 12 | 3 | 40 |
| 108 | Phúc | 30 | 16 | 3 | 40 |

The result still has **8 rows**, one row for each employee.

### 5.1. Meaning of PARTITION BY

`PARTITION BY department_id` splits the window's input row set into **partitions**:

```text
Partition 10:
  An    (15)
  Bình  (18)
  Chi   (18)
  SUM = 51, COUNT = 3

Partition 20:
  Dũng  (24)
  Hà    (26)
  SUM = 50, COUNT = 2

Partition 30:
  Lan   (12)
  Minh  (12)
  Phúc  (16)
  SUM = 40, COUNT = 3
```

Each employee receives the result of the **partition containing that employee**. Unlike `GROUP BY`, PostgreSQL does not discard the rows for An, Bình, and Chi to leave only one row for department 10.

### 5.2. PARTITION BY is not GROUP BY

The two terms "group" and "partition" easily confuse learners:

- `GROUP BY department_id` collapses **multiple rows** into **one row per group**.
- `OVER(PARTITION BY department_id)` lets **each row** see related rows within the same partition.

Same `department_id` key, different purposes.

### 5.3. What happens if PARTITION BY is omitted?

```sql
SELECT
    employee_id,
    employee_name,
    salary_million,
    SUM(salary_million) OVER () AS company_total
FROM window188.employees
ORDER BY employee_id;
```

Every employee gets `company_total = 141`.

`OVER ()` creates a window over the **entire input row set** after the query's relevant filtering/grouping steps, rather than splitting by department automatically.

## 6. Direct comparison: regular SUM vs. SUM OVER

Consider four SQL statements:

**A — One total for the whole table:**

```sql
SELECT SUM(salary_million) AS total
FROM window188.employees;
```

Returns **1 row**, value 141.

**B — One total per department:**

```sql
SELECT department_id,
       SUM(salary_million) AS department_total
FROM window188.employees
GROUP BY department_id
ORDER BY department_id;
```

Returns **3 rows**, totals 51, 50, 40.

**C — Department total attached to each employee:**

```sql
SELECT employee_id, department_id,
       SUM(salary_million) OVER (
           PARTITION BY department_id
       ) AS department_total
FROM window188.employees
ORDER BY employee_id;
```

Returns **8 rows**, each employee carrying their department's total.

**D — Company total attached to each employee:**

```sql
SELECT employee_id,
       SUM(salary_million) OVER () AS company_total
FROM window188.employees
ORDER BY employee_id;
```

Returns **8 rows**, every row carrying the total 141.

Summary table:

| Expression/construct | Evaluation scope | Example row count | Granularity |
|---|---|---:|---|
| `SUM(salary)` without GROUP BY | Whole table after filtering | 1 | Company total |
| `SUM(salary)` + GROUP BY dept | Each department | 3 | One row/department |
| `SUM(salary) OVER(PARTITION BY dept)` | Each department | 8 | One row/employee |
| `SUM(salary) OVER()` | Entire window row set | 8 | One row/employee |

**Decision point:** do you need to preserve employee rows for further calculation, or do you only need a summary table? Answer this before choosing the syntax.

## 7. GROUP BY and OVER can coexist

There is no rule saying "once you use GROUP BY, you cannot use a window". In practice, the two techniques are often **combined in two layers**:

1. `GROUP BY` creates one row per department.
2. A window function computes **over the aggregated department rows**.

Example calculating each department's share of total company payroll:

```sql
WITH department_totals AS (
    SELECT
        department_id,
        SUM(salary_million) AS department_salary
    FROM window188.employees
    GROUP BY department_id
)
SELECT
    department_id,
    department_salary,
    SUM(department_salary) OVER () AS company_salary,
    ROUND(
        100.0 * department_salary
        / SUM(department_salary) OVER (),
        2
    ) AS percentage_of_company
FROM department_totals
ORDER BY department_id;
```

Result:

| department_id | department_salary | company_salary | percentage_of_company |
|---:|---:|---:|---:|
| 10 | 51 | 141 | 36.17 |
| 20 | 50 | 141 | 35.46 |
| 30 | 40 | 141 | 28.37 |

`SUM(department_salary) OVER ()` runs over the **three rows** of the `department_totals` CTE. It no longer runs over the eight employee rows.

### 7.1. Writing concisely in a single SELECT

PostgreSQL allows using an aggregate result as input to a window function:

```sql
SELECT
    department_id,
    SUM(salary_million) AS department_salary,
    SUM(SUM(salary_million)) OVER () AS company_salary,
    ROUND(
        100.0 * SUM(salary_million)
        / SUM(SUM(salary_million)) OVER (),
        2
    ) AS percentage_of_company
FROM window188.employees
GROUP BY department_id
ORDER BY department_id;
```

How to read the expression:

```sql
SUM( SUM(salary_million) ) OVER ()
     ^^^^^^^^^^^^^^^^^^^
     Per-department salary total, formed by GROUP BY

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Window SUM computed over the aggregated department rows
```

This **does not mean** PostgreSQL runs the exact same aggregate twice over the same row set. These are two evaluation levels: the inner aggregate produces group values, and the outer window aggregate processes the grouped rows.

For complex queries, a two-level CTE is often easier to maintain than direct nesting.

### 7.2. What to avoid: re-aggregating repeated values across rows

If you take `department_salary` repeated across **each employee** via a window and then sum all of those values:

```text
Dept 10: 51 appears 3 times -> summed to 153
Dept 20: 50 appears 2 times -> summed to 100
Dept 30: 40 appears 3 times -> summed to 120
Sum of department_salary cells across 8 rows = 373
```

The number **373** is not the total salary of 141; it is the sum of group totals multiplied by employee counts.

**Rule:** do not re-`SUM` window metrics repeated across multiple rows if you want the true total; aggregate at the **correct grain** before computing shares or higher-level totals.

## 8. HAVING filters groups, WHERE filters rows, filtering windows needs another query level

Three situations often get mixed up:

- `WHERE` filters input rows **before GROUP BY/window**.
- `HAVING` filters **aggregated groups**.
- Filtering by a **window function** value normally requires a subquery or CTE and filtering in the outer query.

### 8.1. WHERE: considering only employees earning at least 18 million

```sql
SELECT
    department_id,
    COUNT(*) AS employees_at_least_18,
    SUM(salary_million) AS salary_total
FROM window188.employees
WHERE salary_million >= 18
GROUP BY department_id
ORDER BY department_id;
```

Result:

| department_id | employees_at_least_18 | salary_total |
|---:|---:|---:|
| 10 | 2 | 36 |
| 20 | 2 | 50 |

Department 30 does not appear because no employee there earns 18 or more.

### 8.2. HAVING: keeping only departments with total salary above 45 million

```sql
SELECT
    department_id,
    SUM(salary_million) AS department_salary
FROM window188.employees
GROUP BY department_id
HAVING SUM(salary_million) > 45
ORDER BY department_id;
```

Result:

| department_id | department_salary |
|---:|---:|
| 10 | 51 |
| 20 | 50 |

`HAVING` does not "filter individual employees earning over 45"; it filters **groups** whose total salary exceeds 45.

### 8.3. Filtering against each employee's department average

Requirement:

> "Retrieve employees whose salary is **higher than their own department's average**."

Compute the window first:

```sql
WITH employee_with_avg AS (
    SELECT
        employee_id,
        employee_name,
        department_id,
        salary_million,
        AVG(salary_million) OVER (
            PARTITION BY department_id
        ) AS department_average
    FROM window188.employees
)
SELECT
    employee_id,
    employee_name,
    department_id,
    salary_million,
    ROUND(department_average, 2) AS department_average
FROM employee_with_avg
WHERE salary_million > department_average
ORDER BY department_id, employee_id;
```

Result:

| employee_id | employee_name | department_id | salary_million | department_average |
|---:|---|---:|---:|---:|
| 102 | Bình | 10 | 18 | 17.00 |
| 103 | Chi | 10 | 18 | 17.00 |
| 105 | Hà | 20 | 26 | 25.00 |
| 108 | Phúc | 30 | 16 | 13.33 |

**Why is a CTE needed?** In PostgreSQL, window functions cannot be used directly in `WHERE`, `GROUP BY`, or `HAVING` clauses at the **same SELECT level**. They are evaluated at a logical stage after these clauses.

### 8.4. Common invalid query

```sql
-- Invalid in PostgreSQL:
SELECT employee_id, salary_million
FROM window188.employees
WHERE salary_million > AVG(salary_million)
    OVER (PARTITION BY department_id);
```

A query like this cannot be fixed by "changing OVER to GROUP BY" if you still need to keep individual employees. Move the window calculation into a subquery/CTE as in the previous example.

## 9. Windows run on the already-filtered row set

This point is critical when comparing metrics.

### 9.1. Filter first, then compute the average

```sql
SELECT
    employee_id,
    department_id,
    salary_million,
    AVG(salary_million) OVER (
        PARTITION BY department_id
    ) AS avg_salary_of_filtered_rows
FROM window188.employees
WHERE salary_million >= 18
ORDER BY department_id, employee_id;
```

Because `WHERE` runs before the window at the same query level:

- Department 10 has only two employees earning 18 → average 18, **not 17**.
- Department 20 has two employees earning 24 and 26 → average 25.
- Department 30 has no remaining rows, so there is no department 30 partition in the result.

### 9.2. Compute the full average first, then filter employees

If you want:

> "Show only employees earning 18 or more, but compute the department average across **all employees**."

use a CTE:

```sql
WITH enriched AS (
    SELECT
        employee_id,
        department_id,
        salary_million,
        AVG(salary_million) OVER (
            PARTITION BY department_id
        ) AS full_department_avg
    FROM window188.employees
)
SELECT *
FROM enriched
WHERE salary_million >= 18
ORDER BY department_id, employee_id;
```

Bình and Chi still get `full_department_avg = 17` instead of 18.

**Takeaway:** the exact same `AVG(...) OVER(PARTITION BY ...)` expression can yield different values if the input row set is filtered differently. Always determine **when and where filtering occurs**.

## 10. PARTITION BY is not ORDER BY

The two clauses inside `OVER` serve distinct roles:

- `PARTITION BY` determines **which rows belong to the same partition**.
- `ORDER BY` determines **the logical order of rows within each partition**; it also affects the default window frame of many aggregate functions.

Example:

```sql
SELECT
    employee_id,
    department_id,
    salary_million,
    SUM(salary_million) OVER (
        PARTITION BY department_id
    ) AS whole_department_total,
    SUM(salary_million) OVER (
        PARTITION BY department_id
        ORDER BY employee_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS running_department_total
FROM window188.employees
ORDER BY department_id, employee_id;
```

Result:

| employee_id | dept | salary | whole_department_total | running_department_total |
|---:|---:|---:|---:|---:|
| 101 | 10 | 15 | 51 | 15 |
| 102 | 10 | 18 | 51 | 33 |
| 103 | 10 | 18 | 51 | 51 |
| 104 | 20 | 24 | 50 | 24 |
| 105 | 20 | 26 | 50 | 50 |
| 106 | 30 | 12 | 40 | 12 |
| 107 | 30 | 12 | 40 | 24 |
| 108 | 30 | 16 | 40 | 40 |

If you only want the **entire partition total repeated on every row**, do not add `ORDER BY` to `OVER`. If you add `ORDER BY`, think carefully about the **frame**, because many queries will switch to cumulative calculation.

### 10.1. ORDER BY inside OVER does not sort the final output

```sql
SUM(salary_million) OVER (
    PARTITION BY department_id
    ORDER BY employee_id
)
```

uses ordering for **window calculation**. It does not guarantee the order of rows returned to the client.

For stable output ordering, add `ORDER BY` at the SELECT level:

```sql
ORDER BY department_id, employee_id
```

These two `ORDER BY` clauses serve different functions.

## 11. Window frame: the entire partition or only preceding rows?

A window can be viewed across three layers:

```text
Remaining rows after FROM/WHERE/GROUP BY/HAVING
             |
             +-- PARTITION BY: split into partitions
                      |
                      +-- ORDER BY: define order within each partition
                               |
                               +-- FRAME: which part of the partition
                                          is used for the current calculation
```

For aggregate functions like `SUM`, `AVG`, `COUNT`, `MIN`, `MAX` used as window functions, the **frame** determines which rows are included for the current row in ordered queries.

### 11.1. Without ORDER BY inside OVER

```sql
SUM(amount) OVER ()
```

evaluates over the entire window row set.

```sql
SUM(amount) OVER (PARTITION BY customer_id)
```

evaluates over each customer's entire partition.

### 11.2. With ORDER BY and no explicit frame

```sql
SUM(amount) OVER (ORDER BY sold_on)
```

typically uses the **default frame**:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING
          AND CURRENT ROW
```

Key point: with the default `RANGE`, rows sharing the **same sort value** (*peers*) are also included in the frame up to the current row. Therefore, a "running total" can **jump by date group**, rather than increasing transaction by transaction.

### 11.3. ROWS to sum row by row in a defined order

```sql
SUM(amount) OVER (
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND CURRENT ROW
)
```

`ROWS` defines the frame by **row position**. `sale_id` acts as a secondary key so the ordering of same-day sales is deterministic.

This is the standard pattern for a **per-transaction running total**.

## 12. Practicing the default frame and tied dates

The `sales` table has two sales on Jan 05:

```text
sale_id | sold_on     | amount
--------+-------------+-------
1001    | 2026-01-05  | 100
1002    | 2026-01-05  |  40
1003    | 2026-01-06  |  20
1004    | 2026-01-08  |  60
1005    | 2026-02-01  |  90
1006    | 2026-02-05  |  10
```

### 12.1. Using the default RANGE frame by date

```sql
SELECT
    sale_id,
    sold_on,
    amount,
    SUM(amount) OVER (
        ORDER BY sold_on
    ) AS running_default
FROM window188.sales
ORDER BY sold_on, sale_id;
```

Result:

| sale_id | sold_on | amount | running_default |
|---:|---|---:|---:|
| 1001 | 2026-01-05 | 100 | 140 |
| 1002 | 2026-01-05 | 40 | 140 |
| 1003 | 2026-01-06 | 20 | 160 |
| 1004 | 2026-01-08 | 60 | 220 |
| 1005 | 2026-02-01 | 90 | 310 |
| 1006 | 2026-02-05 | 10 | 320 |

The two Jan 05 rows are peers under `ORDER BY sold_on`. The default frame includes **both** when evaluating each row in the peer group, so both receive 140.

### 12.2. Using ROWS with a unique ordering key

```sql
SELECT
    sale_id,
    sold_on,
    amount,
    SUM(amount) OVER (
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS running_per_transaction
FROM window188.sales
ORDER BY sold_on, sale_id;
```

Result:

| sale_id | sold_on | amount | running_per_transaction |
|---:|---|---:|---:|
| 1001 | 2026-01-05 | 100 | 100 |
| 1002 | 2026-01-05 | 40 | 140 |
| 1003 | 2026-01-06 | 20 | 160 |
| 1004 | 2026-01-08 | 60 | 220 |
| 1005 | 2026-02-01 | 90 | 310 |
| 1006 | 2026-02-05 | 10 | 320 |

Now the total increases **after each transaction**, following the order defined by `sold_on, sale_id`.

### 12.3. ROWS when ORDER BY lacks a secondary key

If you write:

```sql
SUM(amount) OVER (
    ORDER BY sold_on
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND CURRENT ROW
)
```

then when two sales share the same `sold_on`, the relative order between them is **not fully determined**. The two rows can receive cumulative totals in an unexpected processing order.

To make results deterministic and testable, add a stable ordering key such as `sale_id`.

### 12.4. Getting the entire partition total despite ORDER BY

```sql
SELECT
    sale_id,
    amount,
    SUM(amount) OVER (
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS all_sales_total
FROM window188.sales
ORDER BY sold_on, sale_id;
```

Every row receives `all_sales_total = 320`.

If you only need the repeated table total, writing `SUM(amount) OVER()` is simpler.

## 13. ROWS and RANGE are not just two equivalent ways of writing

| Characteristic | ROWS | RANGE |
|---|---|---|
| How frame is determined | By row position in window order | By sort values / peer relationships and range rules |
| When multiple rows share ORDER BY | Can step one row at a time | Peers can be included together in the frame |
| Per-transaction running total | Usually used with a tiebreaker key | Can sum an entire same-day group at once |
| Predictability with duplicate ORDER BY | Requires a tiebreaker key | Requires understanding peers |
| Example | `ROWS UNBOUNDED PRECEDING` | `RANGE UNBOUNDED PRECEDING` |

PostgreSQL also supports the `GROUPS` mode and frame `EXCLUDE` options in supported versions, but for mastering the basics, the most important thing is understanding the difference between **row units** and **groups of equal sort values**.

### 13.1. Frame over the last three transactions

```sql
SELECT
    sale_id,
    sold_on,
    amount,
    SUM(amount) OVER (
        ORDER BY sold_on, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS recent_three_transactions
FROM window188.sales
ORDER BY sold_on, sale_id;
```

Expected result:

| sale_id | amount | recent_three_transactions |
|---:|---:|---:|
| 1001 | 100 | 100 |
| 1002 | 40 | 140 |
| 1003 | 20 | 160 |
| 1004 | 60 | 120 |
| 1005 | 90 | 170 |
| 1006 | 10 | 160 |

For example, at row 1004: it sums 40 + 20 + 60 = 120, excluding transaction 1001 which has fallen outside the three-most-recent-rows frame.

### 13.2. Three transactions vs. last three calendar days

`ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` means **three rows**, not three days. If a single day has many transactions or some days have none, three rows can span a long or short time period.

To get "the last three calendar days", design by **day** or use an appropriate time-based frame. You can aggregate by day first and then apply a window over the daily rows; if days with no data must be included, generate a complete calendar and `LEFT JOIN` the metrics.

## 14. Window functions that are not regular aggregates

Not all window functions are standard aggregates with `OVER` appended.

Representative functions:

| Function | Purpose |
|---|---|
| `ROW_NUMBER()` | Numbers each row within a partition |
| `RANK()` | Ranks rows; tied rows create gaps |
| `DENSE_RANK()` | Ranks rows; does not skip the next rank number |
| `LAG(expression)` | Retrieves a value from a preceding row in window order |
| `LEAD(expression)` | Retrieves a value from a following row |
| `FIRST_VALUE(expression)` | Retrieves the first value in the frame |
| `LAST_VALUE(expression)` | Retrieves the last value in the frame |
| `NTH_VALUE(expression,n)` | Retrieves the nth value in the frame if present |
| `NTILE(n)` | Distributes rows into roughly equal buckets by order |

These functions return a result **on every row**, according to the appropriate partition, order, and frame. They are not a way to produce **one row per group** like `GROUP BY`.

## 15. Ranking employees within departments

Department 10 has salaries: 18, 18, 15. Department 30 has salaries: 16, 12, 12. This is good data for comparing how ties are handled.

```sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary_million,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY salary_million DESC, employee_id
    ) AS row_num,
    RANK() OVER (
        PARTITION BY department_id
        ORDER BY salary_million DESC
    ) AS salary_rank,
    DENSE_RANK() OVER (
        PARTITION BY department_id
        ORDER BY salary_million DESC
    ) AS dense_salary_rank
FROM window188.employees
ORDER BY department_id, salary_million DESC, employee_id;
```

Result:

| employee_id | dept | salary | row_num | salary_rank | dense_salary_rank |
|---:|---:|---:|---:|---:|---:|
| 102 | 10 | 18 | 1 | 1 | 1 |
| 103 | 10 | 18 | 2 | 1 | 1 |
| 101 | 10 | 15 | 3 | 3 | 2 |
| 105 | 20 | 26 | 1 | 1 | 1 |
| 104 | 20 | 24 | 2 | 2 | 2 |
| 108 | 30 | 16 | 1 | 1 | 1 |
| 106 | 30 | 12 | 2 | 2 | 2 |
| 107 | 30 | 12 | 3 | 2 | 2 |

### 15.1. Why does ROW_NUMBER differ from RANK?

- `ROW_NUMBER` gives **each row a distinct sequence number**. Adding `employee_id` to `ORDER BY` breaks ties deterministically.
- `RANK` gives both people earning 18 **a tied rank of 1**, and the next person receives rank 3.
- `DENSE_RANK` also gives both people earning 18 rank 1, but the next person receives rank 2.

**Be careful:** if you write `RANK() OVER(ORDER BY salary_million DESC, employee_id)`, two people with the same salary but different IDs will **no longer tie**, because the `(salary, employee_id)` tuples differ.

### 15.2. Can GROUP BY replace these functions?

Not directly. `GROUP BY department_id` returns only one row per department and does not retain individual employee rows to attach ranks to.

To rank **employees**, keep employee granularity and use window functions; to rank **departments by total salary**, use `GROUP BY` to form department rows first and then `RANK` over the grouped set.

## 16. Top 1 or top N per group

### 16.1. Picking one highest-paid employee per department

```sql
WITH ranked AS (
    SELECT
        employee_id,
        employee_name,
        department_id,
        salary_million,
        ROW_NUMBER() OVER (
            PARTITION BY department_id
            ORDER BY salary_million DESC, employee_id
        ) AS rn
    FROM window188.employees
)
SELECT
    employee_id,
    employee_name,
    department_id,
    salary_million
FROM ranked
WHERE rn = 1
ORDER BY department_id;
```

Result:

| employee_id | employee_name | dept | salary |
|---:|---|---:|---:|
| 102 | Bình | 10 | 18 |
| 105 | Hà | 20 | 26 |
| 108 | Phúc | 30 | 16 |

In department 10, Bình and Chi both earn 18. `ROW_NUMBER` with the ID tiebreaker picks **one deterministic person**, rather than returning both.

### 16.2. If you want to keep everyone tied for highest

Use `RANK()`:

```sql
WITH ranked AS (
    SELECT
        employee_id,
        employee_name,
        department_id,
        salary_million,
        RANK() OVER (
            PARTITION BY department_id
            ORDER BY salary_million DESC
        ) AS salary_rank
    FROM window188.employees
)
SELECT *
FROM ranked
WHERE salary_rank = 1
ORDER BY department_id, employee_id;
```

The result includes **Bình and Chi** in department 10, **Hà** in department 20, and **Phúc** in department 30.

### 16.3. Can GROUP BY MAX replace this?

```sql
SELECT department_id,
       MAX(salary_million) AS max_salary
FROM window188.employees
GROUP BY department_id;
```

This query is correct if you only need **the highest salary per department**; it **does not return the corresponding employee's name/ID**.

To retrieve employee rows, use window ranking, join the MAX result back to the source table, use `DISTINCT ON` (PostgreSQL), or use `LATERAL` depending on tie-handling requirements. The choice depends on whether you need one person or everyone sharing the maximum salary.

## 17. LAG and LEAD: looking at previous/next rows without a self-JOIN

Consider sales ordered by date and then by `sale_id`.

```sql
SELECT
    sale_id,
    sold_on,
    amount,
    LAG(amount) OVER (
        ORDER BY sold_on, sale_id
    ) AS previous_amount,
    LEAD(amount) OVER (
        ORDER BY sold_on, sale_id
    ) AS next_amount
FROM window188.sales
ORDER BY sold_on, sale_id;
```

Result:

| sale_id | amount | previous_amount | next_amount |
|---:|---:|---:|---:|
| 1001 | 100 | NULL | 40 |
| 1002 | 40 | 100 | 20 |
| 1003 | 20 | 40 | 60 |
| 1004 | 60 | 20 | 90 |
| 1005 | 90 | 60 | 10 |
| 1006 | 10 | 90 | NULL |

`LAG` and `LEAD` keep each sale as **one row**, rather than collapsing like `GROUP BY`. They can be used to compute differences:

```sql
SELECT
    sale_id,
    sold_on,
    amount,
    amount - LAG(amount) OVER (
        ORDER BY sold_on, sale_id
    ) AS diff_from_previous_sale
FROM window188.sales
ORDER BY sold_on, sale_id;
```

At the first sale, `LAG` has no preceding row so it returns NULL; the corresponding subtraction is also NULL. To choose a fallback value, you can use `COALESCE` per business contract, but do not automatically treat "no preceding transaction" as 0 in every report.

### 17.1. Previous row does not mean previous day

Because Jan 05 has two sales, `LAG` on the second sale points to a sale on the **same day**. If the requirement is to compare **today's revenue with the previous day's**, aggregate the data to **one row per day** first, then apply `LAG` over the daily set; if comparing against yesterday even when no sales occurred, a full calendar is required.

## 18. Aggregating by day and then computing a cumulative total

A very common requirement:

> "Display each day's **daily sales total** and **period-to-date cumulative sales**."

If you only use `GROUP BY`, you get daily totals without a cumulative column. If you only use a window over sales, the result has **one row per sale**, which is the wrong grain (one row/day).

Solution: **GROUP BY first, window second**.

### 18.1. Using a two-stage CTE

```sql
WITH daily_sales AS (
    SELECT
        sold_on,
        SUM(amount) AS daily_amount
    FROM window188.sales
    GROUP BY sold_on
)
SELECT
    sold_on,
    daily_amount,
    SUM(daily_amount) OVER (
        ORDER BY sold_on
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS cumulative_amount
FROM daily_sales
ORDER BY sold_on;
```

Result:

| sold_on | daily_amount | cumulative_amount |
|---|---:|---:|
| 2026-01-05 | 140 | 140 |
| 2026-01-06 | 20 | 160 |
| 2026-01-08 | 60 | 220 |
| 2026-02-01 | 90 | 310 |
| 2026-02-05 | 10 | 320 |

The input dataset has **6 sales**, while `GROUP BY` produces **5 days with sales**. The window then computes the cumulative total across those **five daily rows**.

### 18.2. Nesting two SUM calls in one SELECT

```sql
SELECT
    sold_on,
    SUM(amount) AS daily_amount,
    SUM(SUM(amount)) OVER (
        ORDER BY sold_on
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS cumulative_amount
FROM window188.sales
GROUP BY sold_on
ORDER BY sold_on;
```

The result matches the CTE above.

Meaning:

- The inner `SUM(amount)` sums **each day's group**.
- The outer `SUM(... ) OVER (...)` runs over the **daily rows produced by GROUP BY**.

This is the standard pattern for **"aggregate by time period, then accumulate"** reports.

### 18.3. Days without sales are still missing

The result table above omits Jan 07 because the `sales` table **contains no transactions** on that date. Window functions **do not generate missing dates**, nor does `GROUP BY` fabricate empty groups.

If a chart must display every consecutive day, generate a calendar with `generate_series`, `LEFT JOIN` actual figures, and apply `COALESCE` before computing the running total.

## 19. Combining generate_series, GROUP BY, and windows to fill empty days

Example from Jan 05 to Jan 08, 2026:

```sql
WITH calendar AS (
    SELECT DATE '2026-01-05' + n AS day
    FROM generate_series(0, 3) AS g(n)
),
daily_sales AS (
    SELECT
        c.day,
        COALESCE(SUM(s.amount), 0) AS daily_amount
    FROM calendar AS c
    LEFT JOIN window188.sales AS s
        ON s.sold_on = c.day
    GROUP BY c.day
)
SELECT
    day,
    daily_amount,
    SUM(daily_amount) OVER (
        ORDER BY day
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS cumulative_amount
FROM daily_sales
ORDER BY day;
```

Result:

| day | daily_amount | cumulative_amount |
|---|---:|---:|
| 2026-01-05 | 140 | 140 |
| 2026-01-06 | 20 | 160 |
| 2026-01-07 | 0 | 160 |
| 2026-01-08 | 60 | 220 |

There are three clear layers:

1. **Calendar** generates every day.
2. **GROUP BY** aggregates each day's sales and preserves empty days thanks to `LEFT JOIN`.
3. **Window SUM** accumulates the daily rows in order.

### 19.1. Be careful where conditions on the sales table are placed

If you want to count only sales with `amount >= 50` while still keeping every day, put the condition inside `ON`:

```sql
LEFT JOIN window188.sales AS s
    ON s.sold_on = c.day
   AND s.amount >= 50
```

If you put `s.amount >= 50` in `WHERE` after the `LEFT JOIN`, days without qualifying sales will be **removed from the day set** before `GROUP BY`/window runs. That breaks charts requiring all dates to be shown.

## 20. Computing each employee's share of department and company totals

Window aggregates allow attaching different denominators onto the **same employee row**:

```sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary_million,
    SUM(salary_million) OVER (
        PARTITION BY department_id
    ) AS department_salary,
    SUM(salary_million) OVER () AS company_salary,
    ROUND(
        100.0 * salary_million
        / SUM(salary_million) OVER (
            PARTITION BY department_id
        ),
        2
    ) AS pct_of_department,
    ROUND(
        100.0 * salary_million
        / SUM(salary_million) OVER (),
        2
    ) AS pct_of_company
FROM window188.employees
ORDER BY department_id, employee_id;
```

Examples:

- An earns 15 out of department total 51 → `15 / 51 × 100 ≈ 29.41%`.
- An earns 15 out of company total 141 → `15 / 141 × 100 ≈ 10.64%`.
- Hà earns 26 out of department total 50 → `52.00%`.

### 20.1. Why cannot GROUP BY directly replace this?

If you only `GROUP BY department_id`, you no longer have individual employee rows to calculate shares specifically for An, Bình, or Chi. You could `GROUP BY` to compute department totals and then **JOIN** those totals back to the employees table, though windows are usually more concise.

### 20.2. Departments with a zero total

The lab data guarantees `salary_million > 0`, so partition denominators are always positive. In real data, if a group total can be 0, avoid division by zero:

```sql
salary_amount
/ NULLIF(
    SUM(salary_amount) OVER (PARTITION BY department_id),
    0
)
```

`NULLIF(total,0)` returns NULL when the total is 0; division by NULL returns NULL instead of raising an exception. How NULL is displayed or interpreted should follow business rules.

## 21. COUNT(*) and COUNT(column) in groups and windows

### 21.1. Without NULLs in the employee key

On the lab `employees` table:

```sql
SELECT
    department_id,
    COUNT(*) AS all_rows,
    COUNT(employee_id) AS known_employee_ids
FROM window188.employees
GROUP BY department_id
ORDER BY department_id;
```

Both counts are equal because `employee_id` is a NOT NULL primary key.

### 21.2. LEFT JOIN to retain departments with no employees

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(*) AS rows_after_left_join,
    COUNT(e.employee_id) AS actual_employees,
    COALESCE(SUM(e.salary_million), 0) AS salary_total
FROM window188.departments AS d
LEFT JOIN window188.employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

Result:

| department_id | rows_after_left_join | actual_employees | salary_total |
|---:|---:|---:|---:|
| 10 | 3 | 3 | 51 |
| 20 | 2 | 2 | 50 |
| 30 | 3 | 3 | 40 |
| 40 | 1 | 0 | 0 |

Department 40 still produces **one null-extended row** after the `LEFT JOIN`, so `COUNT(*) = 1`, whereas `COUNT(e.employee_id) = 0`.

This is a frequent counting bug, regardless of whether `GROUP BY` or a window is used afterward.

### 21.3. Window over the post-LEFT JOIN set

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    COUNT(*) OVER (
        PARTITION BY d.department_id
    ) AS rows_in_join_partition,
    COUNT(e.employee_id) OVER (
        PARTITION BY d.department_id
    ) AS employees_in_partition
FROM window188.departments AS d
LEFT JOIN window188.employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id NULLS LAST;
```

For department 40, one result row still appears:

```text
department_id          = 40
employee_id            = NULL
rows_in_join_partition = 1
employees_in_partition = 0
```

**Windows do not automatically fix COUNT(*) semantics on null-extended rows.** They strictly evaluate over the row set formed by the query.

## 22. FILTER with regular aggregates and window aggregates

PostgreSQL supports `FILTER (WHERE ...)` syntax to choose which rows contribute to **a specific aggregate**.

### 22.1. GROUP BY and FILTER

Count employees earning at least 18 million per department:

```sql
SELECT
    department_id,
    COUNT(*) AS total_employees,
    COUNT(*) FILTER (
        WHERE salary_million >= 18
    ) AS employees_from_18
FROM window188.employees
GROUP BY department_id
ORDER BY department_id;
```

Result:

| department_id | total_employees | employees_from_18 |
|---:|---:|---:|
| 10 | 3 | 2 |
| 20 | 2 | 2 |
| 30 | 3 | 0 |

Still **one row per department**.

### 22.2. Window aggregate and FILTER

```sql
SELECT
    employee_id,
    department_id,
    salary_million,
    COUNT(*) FILTER (
        WHERE salary_million >= 18
    ) OVER (
        PARTITION BY department_id
    ) AS colleagues_from_18
FROM window188.employees
ORDER BY department_id, employee_id;
```

The result still has **8 rows**; each employee gets the count of people earning 18 or more in their department:

- Department 10: 2.
- Department 20: 2.
- Department 30: 0.

### 22.3. FILTER does not apply uniformly to all window functions

`FILTER` is syntax for **aggregate functions** (including when called as window aggregates), not an arbitrary filter for `ROW_NUMBER()`, `LAG()`, `RANK()`, and non-aggregate window functions.

This example is **invalid**:

```sql
-- Invalid:
SELECT ROW_NUMBER()
       FILTER (WHERE salary_million >= 18)
       OVER (PARTITION BY department_id)
FROM window188.employees;
```

To number **only employees earning >= 18**, filter the input source **before computing ROW_NUMBER**, or compute the ordering over the full source and filter outside as required.

## 23. FIRST_VALUE and LAST_VALUE: understand frames before using them

Applications often need "the highest/lowest salary in the department" or "the first/last value in a given order".

For department 10's salaries sorted ascending: 15, 18, 18.

### 23.1. FIRST_VALUE picks the first element in the frame

```sql
SELECT
    employee_id,
    department_id,
    salary_million,
    FIRST_VALUE(salary_million) OVER (
        PARTITION BY department_id
        ORDER BY salary_million, employee_id
    ) AS minimum_salary_in_order
FROM window188.employees
ORDER BY department_id, salary_million, employee_id;
```

For department 10, every employee gets the first value **15**. Because the first row remains inside the default cumulative frame of subsequent rows, this phrasing usually yields the expected result in this example.

### 23.2. LAST_VALUE is easily misunderstood

An expression like:

```sql
LAST_VALUE(salary_million) OVER (
    PARTITION BY department_id
    ORDER BY salary_million, employee_id
)
```

**does not implicitly retrieve the last row of the entire partition**. With the ordered default frame, the frame end is usually the **current row and its peers**, so the result can simply be the current row's salary.

To get the last element of the entire partition, specify the frame explicitly:

```sql
SELECT
    employee_id,
    department_id,
    salary_million,
    LAST_VALUE(salary_million) OVER (
        PARTITION BY department_id
        ORDER BY salary_million, employee_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS highest_salary_in_partition
FROM window188.employees
ORDER BY department_id, salary_million, employee_id;
```

When ordered by ascending salary, the last element of the partition is the highest salary.

### 23.3. If you only need the maximum salary, MAX is simpler

```sql
MAX(salary_million) OVER (
    PARTITION BY department_id
)
```

Computes the highest salary across the whole partition without worrying about `LAST_VALUE` frames.

If you need **the name of the highest-paid person**, handle ties using ranking, `DISTINCT ON`, or an appropriate row-selection method.

## 24. DISTINCT does not replace GROUP BY, and COUNT(DISTINCT) OVER has limitations

### 24.1. DISTINCT removes duplicate result rows

```sql
SELECT DISTINCT department_id
FROM window188.employees
ORDER BY department_id;
```

Returns three department IDs: 10, 20, 30.

This is not an aggregation computing total salary or employee counts. It merely eliminates duplicates of the selected values.

### 24.2. GROUP BY is flexible for per-key aggregates

```sql
SELECT department_id,
       COUNT(*) AS employee_count
FROM window188.employees
GROUP BY department_id;
```

Returns one row per group along with the count.

### 24.3. PostgreSQL does not support DISTINCT directly inside standard window aggregates

The following example is not a valid way to count distinct departments on each row in PostgreSQL:

```sql
-- Invalid in PostgreSQL:
SELECT
    employee_id,
    COUNT(DISTINCT department_id) OVER ()
FROM window188.employees;
```

PostgreSQL reports a limitation regarding `DISTINCT` inside an aggregate function used as a window function.

The workaround is to **separate the step that identifies distinct values** and then compute the window at the appropriate grain:

```sql
WITH distinct_departments AS (
    SELECT DISTINCT department_id
    FROM window188.employees
)
SELECT
    department_id,
    COUNT(*) OVER () AS distinct_department_count
FROM distinct_departments
ORDER BY department_id;
```

The result has three rows, with `distinct_department_count = 3` on each row.

If the requirement is simply a single table-wide count, simpler is:

```sql
SELECT COUNT(DISTINCT department_id) AS distinct_departments
FROM window188.employees;
```

**Rule:** do not force a window function when a standard aggregate solves it cleanly and concisely.

## 25. NULL: aggregates and windows share common rules

When using `COUNT`, `SUM`, `AVG`, `MIN`, and `MAX` aggregates, remember:

- `COUNT(*)` counts **rows**.
- `COUNT(column)` counts only **non-NULL values** in the column.
- `SUM(column)` and `AVG(column)` ignore NULL values.
- On a set with no non-NULL input values, `SUM`/`AVG` can return NULL.
- `COALESCE` can replace NULL with a suitable display value, though NULL and 0 do not always share the same semantics.

An immediate example without creating tables:

```sql
WITH data(department_id, amount) AS (
    VALUES
        (1, 10),
        (1, NULL::integer),
        (1, 20),
        (2, NULL::integer)
)
SELECT
    department_id,
    COUNT(*) AS row_count,
    COUNT(amount) AS known_amount_count,
    SUM(amount) AS amount_sum
FROM data
GROUP BY department_id
ORDER BY department_id;
```

Result:

| department_id | row_count | known_amount_count | amount_sum |
|---:|---:|---:|---:|
| 1 | 3 | 2 | 30 |
| 2 | 1 | 0 | NULL |

When using `OVER(PARTITION BY department_id)` on the same dataset, the equivalent aggregate results **repeat across each corresponding row**, instead of collapsing into two rows.

### 25.1. PARTITION BY with NULL keys

In windows, rows with `department_id NULL` belong together in one partition for that partition key. This is how data is divided for evaluation, not because standard comparison `NULL = NULL` evaluates to TRUE.

If a partition key is nullable, decide whether the "unassigned" group should be calculated together or handled separately.

### 25.2. Handling NULL elements in ORDER BY

PostgreSQL supports `NULLS FIRST`/`NULLS LAST` in window ordering clauses when explicit rules are needed:

```sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY hired_on NULLS LAST, employee_id
)
```

In the lab schema `hired_on` is NOT NULL, but in real-world data allowing NULLs, define NULL placement so ordering and ranks do not surprise you.

## 26. JOIN grain: do not multiply metrics before GROUP BY or windows

Suppose an employee has multiple skills and we join:

```text
departments -> employees -> employee_skills
```

If each employee has three skills, the post-join result can contain **three rows for one employee**. In that case:

```sql
SUM(e.salary_million)
```

after the join can add the same employee's salary **three times**, whether you use `GROUP BY` or a window.

Some resulting bugs:

- `GROUP BY department_id` after the join produces an **inflated** department salary total.
- `SUM(e.salary_million) OVER(PARTITION BY department_id)` is also inflated, while repeating the result across multiple skill rows.
- `COUNT(*)` counts post-join rows, not distinct employees.

### 26.1. How to avoid this

If the target metric is salary per **employee**, keep one row per employee before aggregating or windowing.

You can:

- Aggregate skills down to one row per employee **before joining**.
- Use `EXISTS` if you only need to check whether an employee possesses a certain skill.
- Use `COUNT(DISTINCT employee_id)` in group aggregates where appropriate, though do not treat `DISTINCT` as a universal band-aid for join errors.
- Split the report into multiple CTEs with clear grains—such as `employee_totals` and `skill_counts`—and join them on unique keys.

### 26.2. Windows do not automatically deduplicate

Even though windows do not "collapse rows", that **does not guarantee the input already has one row per entity**. They preserve the grain of whatever rows exist at the window evaluation stage, including rows multiplied by a `JOIN`.

## 27. Naming a WINDOW to reuse configurations

When multiple functions share the same partition/order, PostgreSQL supports the `WINDOW` clause:

```sql
SELECT
    employee_id,
    department_id,
    salary_million,
    SUM(salary_million) OVER dept_window AS department_total,
    AVG(salary_million) OVER dept_window AS department_average,
    COUNT(*) OVER dept_window AS department_count
FROM window188.employees
WINDOW dept_window AS (
    PARTITION BY department_id
)
ORDER BY department_id, employee_id;
```

This avoids repeating `PARTITION BY department_id` multiple times.

### 27.1. A window with its own ordering

```sql
SELECT
    employee_id,
    department_id,
    salary_million,
    ROW_NUMBER() OVER ordered_dept AS employee_sequence,
    SUM(salary_million) OVER (
        PARTITION BY department_id
    ) AS department_total
FROM window188.employees
WINDOW ordered_dept AS (
    PARTITION BY department_id
    ORDER BY employee_id
)
ORDER BY department_id, employee_id;
```

Here:

- `ordered_dept` defines the ordering for numbering each employee.
- The department total uses a window **without ORDER BY** so it always covers the full partition.

**Do not overuse one ordered named window** for every aggregate if one function needs the full-group total and another needs a cumulative total. The same `PARTITION BY` with **different frames** yields different meanings.

## 28. Logical query processing order in PostgreSQL

To understand `GROUP BY` and windows, keep a logical diagram of SQL stages in mind:

```text
FROM / JOIN
    |
WHERE
    |
GROUP BY
    |
Group aggregates
    |
HAVING
    |
Evaluate window expressions on remaining rows
    |
SELECT / output expressions
    |
DISTINCT (if present)
    |
Output ORDER BY
    |
LIMIT / OFFSET
```

This is a **semantic model**, not a rigid physical execution plan. The PostgreSQL optimizer can push down predicates, reorder operations, or eliminate unnecessary steps while preserving results.

Some consequences:

1. `WHERE` cannot directly reference window results at the **same SELECT level**.
2. `HAVING` filters groups and can change the number of rows the window sees.
3. If `GROUP BY` is present, the window processes **aggregated rows**, no longer all detailed rows.
4. The outermost `ORDER BY` determines display order; `ORDER BY` inside `OVER` determines window calculation.
5. `LIMIT` normally caps final output rows; it does not alter `SUM(...) OVER()` computed over the full window set beforehand, unless you put `LIMIT` inside a subquery **before** the window.

### 28.1. Example: LIMIT does not turn company total into a three-person total

```sql
SELECT
    employee_id,
    salary_million,
    SUM(salary_million) OVER () AS company_salary
FROM window188.employees
ORDER BY employee_id
LIMIT 3;
```

Only returns the first **3 rows**, yet every row still carries `company_salary = 141`, not 51.

If you want the total of **three pre-selected people**, select those three people in a subquery and compute the window outside:

```sql
WITH first_three AS (
    SELECT employee_id, salary_million
    FROM window188.employees
    ORDER BY employee_id
    LIMIT 3
)
SELECT
    employee_id,
    salary_million,
    SUM(salary_million) OVER () AS selected_three_total
FROM first_three
ORDER BY employee_id;
```

Now every row has `selected_three_total = 51`.

## 29. Comparing GROUP BY + JOIN of aggregated results vs. windows

There are two equivalent patterns in terms of goal when you want **employees + department total salary**.

### 29.1. GROUP BY then JOIN back

```sql
WITH department_sums AS (
    SELECT
        department_id,
        SUM(salary_million) AS department_total
    FROM window188.employees
    GROUP BY department_id
)
SELECT
    e.employee_id,
    e.employee_name,
    e.department_id,
    e.salary_million,
    ds.department_total
FROM window188.employees AS e
JOIN department_sums AS ds
    ON ds.department_id = e.department_id
ORDER BY e.department_id, e.employee_id;
```

### 29.2. Using a window

```sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary_million,
    SUM(salary_million) OVER (
        PARTITION BY department_id
    ) AS department_total
FROM window188.employees
ORDER BY department_id, employee_id;
```

Both return **8 rows**, with department totals 51, 50, 40 attached to each employee.

### 29.3. Which approach to choose?

| Criterion | GROUP BY + re-JOIN | Window |
|---|---|---|
| Attaching a per-department sum to each employee | Works | Usually shorter |
| Need a department summary table reused in multiple places | Convenient | Does not automatically create a summary table |
| Need multiple metrics in the same partition | May require multiple aggregate expressions | Multiple `OVER` clauses share the partition |
| Only need one row per department | `GROUP BY` directly | Window leaves extra rows unless reduced afterward |
| Need ranking/preceding-row logic | Can be complex | Windows are more natural |
| Performance | Depends on optimizer execution | Depends on partition, sort, frame, and plan |

There is no rule that "windows are always faster than GROUP BY + JOIN". Measure on real data and queries. Output requirements and readability come first.

## 30. EXPLAIN: Aggregate and WindowAgg in PostgreSQL

PostgreSQL can use different plan nodes:

- `HashAggregate`: groups and aggregates using a hash table when appropriate.
- `GroupAggregate`: groups and aggregates over rows already sorted suitably.
- `WindowAgg`: evaluates window functions over rows in the required partition/order.
- `Sort`: sorts data for grouping, window ordering, or final result `ORDER BY`.
- `Incremental Sort`: can leverage partial existing ordering in certain plans.

**These names are examples that may appear, not a guarantee** that every PostgreSQL version or dataset will use those exact nodes.

### 30.1. Plan for GROUP BY

```sql
EXPLAIN
SELECT department_id, SUM(salary_million)
FROM window188.employees
GROUP BY department_id;
```

The planner may choose hash aggregation or group aggregation depending on size and statistics.

### 30.2. Plan for a window

```sql
EXPLAIN
SELECT
    employee_id,
    department_id,
    SUM(salary_million) OVER (
        PARTITION BY department_id
    ) AS department_total
FROM window188.employees;
```

You may see `WindowAgg` and a sort step by the partition key when needed.

### 30.3. GROUP BY followed by a window

```sql
EXPLAIN
SELECT
    department_id,
    SUM(salary_million) AS department_total,
    SUM(SUM(salary_million)) OVER () AS company_total
FROM window188.employees
GROUP BY department_id;
```

The query has two semantic layers, so the plan can include both **aggregation** and **window** nodes.

### 30.4. Measuring actual runtime

In the lab database:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    employee_id,
    department_id,
    SUM(salary_million) OVER (
        PARTITION BY department_id
    ) AS department_total
FROM window188.employees;
```

`EXPLAIN ANALYZE` executes the query to measure timing and row counts; for these lab `SELECT` examples it is safe. Never casually run `EXPLAIN ANALYZE` on DML statements with side effects in production.

### 30.5. What does performance depend on?

- **Input row count:** windows may process and return more rows than `GROUP BY`.
- **Partition and ORDER BY keys:** determine sorting, ability to exploit existing order, and partition count.
- **Frame:** ordered windows with complex frames can consume more memory/work than full-partition aggregates.
- **Indexes:** indexes on filter/partition/order keys sometimes assist the plan, but never replace measurement.
- **Rows produced by JOINs:** if a join multiplies rows, windows/aggregates must process more data.
- **work_mem and sort spills:** large queries may spill temporary data to disk when sorting/windowing exceeds appropriate memory limits.
- **Selectivity:** filtering before vs. after a window changes both the **result** and the cost.

**Do not alter WHERE/OVER just to make a plan look faster** if doing so alters the set of rows participating in the calculation.

## 31. When to choose GROUP BY vs. when to choose windows?

| Requirement | Prefer | Reason |
|---|---|---|
| Employee count per department | `GROUP BY` | Needs one row/department |
| Total company salary | Aggregate without GROUP BY | Needs one number |
| Employee list with department total on each row | `OVER(PARTITION BY ...)` | Preserves each employee |
| Transaction list with running total | Window with `ORDER BY/ROWS` | Calculates across preceding rows |
| Ranking employees by salary in department | `RANK/ROW_NUMBER OVER` | Preserves each employee |
| Employees above department average | Window in CTE, filter outside | Needs to compare each row with its group |
| Daily total revenue report | `GROUP BY sold_on` | One row/day |
| Daily revenue and cumulative total over days | `GROUP BY` then window | Two calculation stages |
| Only departments with total salary > 45 | `HAVING` | Filters groups |
| Top 1 employee per department | `ROW_NUMBER OVER` then `WHERE rn=1` | Picks one row by rule |
| Department share of company total | `GROUP BY` then window | Computes metric across groups |
| Report including empty departments | `departments LEFT JOIN employees` then GROUP BY | Must preserve department source |
| Counting statuses per group | `GROUP BY + FILTER` | One row/group, multiple metrics |

### Quick selection rules

- **Want fewer rows, one row per group?** Think `GROUP BY`.
- **Want to keep each row and attach group/sequence metrics?** Think `OVER`.
- **Want to both group by day and accumulate over time?** Combine `GROUP BY` and `OVER` in two stages.
- **Want to keep only rows meeting a window criterion?** Compute the window in a CTE first, then filter in the outer query.

## 32. Common mistakes to avoid

### Mistake 1. Thinking PARTITION BY is like GROUP BY

`PARTITION BY` defines window partitions without collapsing rows into one.

**Consequence:** a report expecting one row/department returns one row/employee.

### Mistake 2. Using GROUP BY when individual employee names are still needed

When grouping by department, selecting an unaggregated `employee_name` is generally invalid.

**Fix:** keep individual employee rows and use `SUM(...) OVER(PARTITION BY ...)`.

### Mistake 3. Adding ORDER BY inside OVER and assuming it is still the full department total

`SUM(salary) OVER(PARTITION BY dept ORDER BY employee_id)` can become a cumulative sum via the default frame rather than the repeated full-partition total.

**Fix:** omit `ORDER BY` if you want the full department total, or set frame `UNBOUNDED PRECEDING ... UNBOUNDED FOLLOWING`.

### Mistake 4. Forgetting peers in the default RANGE frame

Two sales on the same day can receive the same cumulative total instead of stepping transaction by transaction.

**Fix:** to sum row by row, use `ROWS ... CURRENT ROW` with a unique tiebreaker key.

### Mistake 5. Using ROW_NUMBER when ORDER BY does not break ties

If two employees have equal salaries, which one gets chosen as "first" can be unstable when ordering only by salary.

**Fix:** add `employee_id` or a stable tiebreaker key to `ROW_NUMBER`. If tied people should stay tied, use `RANK`/`DENSE_RANK` with the right criteria.

### Mistake 6. Adding employee_id to RANK and losing ties

`RANK() OVER(ORDER BY salary DESC, employee_id)` compares distinct tuples, so equal salaries no longer tie.

**Fix:** keep `ORDER BY salary DESC` inside `RANK` when "equal salary means equal rank".

### Mistake 7. Putting a window inside same-level WHERE or HAVING

PostgreSQL does not allow window functions directly in these clauses.

**Fix:** use a CTE/subquery to compute first, and an outer query to filter.

### Mistake 8. Filtering with WHERE first and expecting the window to still see all rows

`WHERE salary >= 18` removes lower-paid employees before the partition average is computed.

**Fix:** compute the average over the full dataset in a CTE, then filter the result outside.

### Mistake 9. Summing department totals repeated on every employee

Total 51 is repeated three times, total 50 twice, total 40 three times. Summing all cells yields 373 instead of 141.

**Fix:** aggregate at department grain or compute `SUM(SUM(salary)) OVER()` after `GROUP BY`.

### Mistake 10. Using COUNT(*) for an empty department after LEFT JOIN

An empty department still produces one NULL-extended row, so `COUNT(*)` returns 1.

**Fix:** use `COUNT(e.employee_id)`.

### Mistake 11. Assuming windows fabricate days with no sales

Without a Jan 07 row in `sales`, the window will not generate that date.

**Fix:** use `generate_series` to build a calendar, `LEFT JOIN` sales, then `GROUP BY` and window.

### Mistake 12. Using SUM on a one-to-many joined table without accounting for fan-out

An employee with multiple skill rows causes their salary to be summed repeatedly.

**Fix:** check the grain, aggregate the child source before joining, or use `EXISTS`.

### Mistake 13. Using DISTINCT in a window aggregate when PostgreSQL does not support it

`COUNT(DISTINCT x) OVER(...)` is invalid in standard PostgreSQL versions.

**Fix:** use a regular aggregate or isolate the `DISTINCT` step in a CTE/subquery.

### Mistake 14. Using LAST_VALUE without checking the frame

`LAST_VALUE` with the default frame can return the current row's value instead of the partition's last row.

**Fix:** use a frame ending at `UNBOUNDED FOLLOWING`, or use `MAX/MIN OVER(PARTITION BY ...)` if you only need extremes.

### Mistake 15. Believing OVER ORDER BY determines final output order

It governs window evaluation order, not final result order.

**Fix:** add `ORDER BY` at the `SELECT` level.

### Mistake 16. Using LIMIT after a window and thinking the window only ran on displayed rows

`LIMIT 3` after a window can still leave the total 141 on each displayed row.

**Fix:** to compute only over three rows, select three rows in a subquery before applying the window.

## 33. Practice exercises with solutions

The following exercises use the `window188` schema created at the beginning of the lesson.

### Exercise 1. Count employees per department

**Requirement:** return one row per department that has employees.

```sql
SELECT
    department_id,
    COUNT(*) AS employee_count
FROM window188.employees
GROUP BY department_id
ORDER BY department_id;
```

**Answer:** department 10 has 3, department 20 has 2, department 30 has 3.

### Exercise 2. Keep employee names and the number of colleagues in their department

```sql
SELECT
    employee_name,
    department_id,
    COUNT(*) OVER (
        PARTITION BY department_id
    ) AS department_employee_count
FROM window188.employees
ORDER BY department_id, employee_id;
```

**Answer:** 8 rows. Every employee in department 10 gets 3, department 20 gets 2, department 30 gets 3.

### Exercise 3. Company total salary as a single row

```sql
SELECT SUM(salary_million) AS company_salary
FROM window188.employees;
```

**Answer:** 141.

### Exercise 4. Company total salary attached to each employee

```sql
SELECT
    employee_id,
    salary_million,
    SUM(salary_million) OVER () AS company_salary
FROM window188.employees
ORDER BY employee_id;
```

**Answer:** 8 rows, every row has `company_salary = 141`.

### Exercise 5. Why does GROUP BY return 3 rows while the window returns 8?

**Solution:** `GROUP BY` collapses each department into one row. The window computes metrics over department partitions while keeping each employee row.

### Exercise 6. Find departments with total salary at least 50 million

```sql
SELECT
    department_id,
    SUM(salary_million) AS total_salary
FROM window188.employees
GROUP BY department_id
HAVING SUM(salary_million) >= 50
ORDER BY department_id;
```

**Answer:** department 10 (51), department 20 (50).

### Exercise 7. Find employees earning more than their department's average

```sql
WITH enriched AS (
    SELECT
        employee_id,
        employee_name,
        department_id,
        salary_million,
        AVG(salary_million) OVER (
            PARTITION BY department_id
        ) AS dept_avg
    FROM window188.employees
)
SELECT employee_id, employee_name, department_id
FROM enriched
WHERE salary_million > dept_avg
ORDER BY department_id, employee_id;
```

**Answer:** Bình, Chi, Hà, Phúc.

### Exercise 8. Why is COUNT(*) wrong when a department is empty?

Department 40 has no employees, yet `LEFT JOIN` produces one row with NULL employee columns.

**Solution:** `COUNT(*)` counts 1 result row; `COUNT(e.employee_id)` counts 0 real employees.

### Exercise 9. Rank salaries in department 10

```sql
SELECT
    employee_id,
    salary_million,
    RANK() OVER (
        PARTITION BY department_id
        ORDER BY salary_million DESC
    ) AS rnk,
    DENSE_RANK() OVER (
        PARTITION BY department_id
        ORDER BY salary_million DESC
    ) AS dense_rnk
FROM window188.employees
WHERE department_id = 10
ORDER BY salary_million DESC, employee_id;
```

**Answer:** Bình and Chi get rank 1, dense rank 1; An gets rank 3, dense rank 2.

### Exercise 10. Pick one highest-paid person per department

```sql
WITH ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY salary_million DESC, employee_id
           ) AS rn
    FROM window188.employees
)
SELECT employee_name, department_id, salary_million
FROM ranked
WHERE rn = 1
ORDER BY department_id;
```

**Answer:** Bình, Hà, Phúc.

### Exercise 11. Keep everyone tied for first place

Replace `ROW_NUMBER` with:

```sql
RANK() OVER (
    PARTITION BY department_id
    ORDER BY salary_million DESC
)
```

and filter `rank = 1` in the outer query.

**Answer:** Bình, Chi, Hà, Phúc.

### Exercise 12. Compute row-by-row cumulative sales total

```sql
SELECT
    sale_id,
    sold_on,
    amount,
    SUM(amount) OVER (
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS running_total
FROM window188.sales
ORDER BY sold_on, sale_id;
```

**Answer:** 100, 140, 160, 220, 310, 320.

### Exercise 13. Why can both Jan 05 sales get running total 140?

With:

```sql
SUM(amount) OVER (ORDER BY sold_on)
```

the default frame is based on `RANGE` and includes peer rows sharing the same Jan 05 date.

**Solution:** both get 140. To sum transaction by transaction, use `ROWS` and order by `sold_on, sale_id`.

### Exercise 14. Daily totals and daily cumulative totals

```sql
WITH daily AS (
    SELECT sold_on, SUM(amount) AS daily_total
    FROM window188.sales
    GROUP BY sold_on
)
SELECT
    sold_on,
    daily_total,
    SUM(daily_total) OVER (
        ORDER BY sold_on
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS running_total
FROM daily
ORDER BY sold_on;
```

**Answer:** Jan 05: 140/140; Jan 06: 20/160; Jan 08: 60/220; Feb 01: 90/310; Feb 05: 10/320.

### Exercise 15. Display Jan 07 as well even though it has no sales

```sql
WITH calendar AS (
    SELECT DATE '2026-01-05' + n AS day
    FROM generate_series(0,3) AS g(n)
),
daily AS (
    SELECT
        c.day,
        COALESCE(SUM(s.amount),0) AS revenue
    FROM calendar AS c
    LEFT JOIN window188.sales AS s
        ON s.sold_on=c.day
    GROUP BY c.day
)
SELECT
    day,
    revenue,
    SUM(revenue) OVER (
        ORDER BY day
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running
FROM daily
ORDER BY day;
```

**Answer:** Jan 07 has revenue 0, running 160.

### Exercise 16. Take only the first three employees while keeping total 141

```sql
SELECT
    employee_id,
    SUM(salary_million) OVER() AS company_total
FROM window188.employees
ORDER BY employee_id
LIMIT 3;
```

**Solution:** the window runs over all eight employees before `LIMIT` truncates the result to three rows. To get the total of those three people, use a CTE to pick three people first and then apply the window.

### Exercise 17. Calculate each department's share of payroll

```sql
WITH dept AS (
    SELECT department_id,
           SUM(salary_million) AS total
    FROM window188.employees
    GROUP BY department_id
)
SELECT
    department_id,
    total,
    ROUND(
        100.0 * total / SUM(total) OVER(), 2
    ) AS share_pct
FROM dept
ORDER BY department_id;
```

**Answer:** approximately 36.17%, 35.46%, 28.37%.

### Exercise 18. Is filtering by sequence number in the same-level WHERE valid?

```sql
-- Wrong:
SELECT
    employee_id,
    ROW_NUMBER() OVER(
        PARTITION BY department_id
        ORDER BY employee_id
    ) AS rn
FROM window188.employees
WHERE rn = 1;
```

**Solution:** no. An alias in `SELECT`/window cannot be referenced directly like this in same-level `WHERE`. Compute `rn` in a CTE/subquery and filter in the outer query.

### Exercise 19. Why can summing department totals repeated on employees add up to 373?

**Solution:** department 10's total of 51 is repeated three times, department 20's total of 50 twice, and department 30's total of 40 three times. Summing those repeated values gives `153 + 100 + 120 = 373`, not the company salary total. You must bring data to **one row per department** grain before summing department totals.

### Exercise 20. Do window functions automatically reduce row counts?

**No.** A window function by itself attaches calculations to rows at the current granularity. However, **a query may simultaneously contain GROUP BY, DISTINCT, or LIMIT** that changes row counts at other stages; therefore, you must inspect the entire SQL structure.

## 34. Quick reference table

| Goal | Syntax | Effect on row count |
|---|---|---|
| Table-wide total | `SELECT SUM(x) FROM t` | Usually one aggregate row |
| Total per group | `SELECT k, SUM(x) FROM t GROUP BY k` | One row per non-empty group |
| Group total on each row | `SUM(x) OVER (PARTITION BY k)` | Keeps current rows |
| Table-wide total on each row | `SUM(x) OVER ()` | Keeps current rows |
| Count records in same group | `COUNT(*) OVER(PARTITION BY k)` | Value repeated per partition |
| Row-by-row running total | `SUM(x) OVER(ORDER BY t,id ROWS UNBOUNDED PRECEDING)` | Keeps each row, cumulative values |
| Full partition total with ORDER | `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` | Every row gets same partition total |
| Filter input rows | `WHERE ...` | Before same-level GROUP BY/window |
| Filter groups | `HAVING SUM(x)>...` | After GROUP BY, before same-level window |
| Filter by window result | Window in CTE, outer `WHERE` | After window is computed |
| Count multiple statuses per group | `COUNT(*) FILTER(WHERE ...)` + GROUP BY | One row/group |
| Conditional count on each row | `COUNT(*) FILTER(WHERE ...) OVER(PARTITION BY k)` | Each row gets group metric |
| Ranking | `RANK() OVER(PARTITION BY k ORDER BY x DESC)` | Keeps each row |
| Pick top 1 | `ROW_NUMBER() OVER(...)` then filter `rn = 1` outside | One row/group if non-empty |
| Keep first-place ties | `RANK() OVER(...)` then filter `rank = 1` | May return multiple rows/group |
| Get previous row value | `LAG(x) OVER(ORDER BY t,id)` | Keeps each row |
| Group by day then accumulate | GROUP BY day in CTE, SUM OVER outside | One row/day |
| Group then compute group share | `SUM(SUM(x)) OVER()` or grouped CTE | One row/group |
| Inspect aggregation plan | `EXPLAIN` with GROUP BY | May use HashAggregate/GroupAggregate |
| Inspect window plan | `EXPLAIN` with OVER | May use WindowAgg and Sort |

## 35. Summary: decide granularity before choosing syntax

To distinguish group aggregation from window functions in PostgreSQL, always start with this question:

> **Does the result need one row per group, or does it still need one row per original record?**

If you want one row per department:

```sql
SELECT
    department_id,
    SUM(salary_million) AS department_salary
FROM window188.employees
GROUP BY department_id;
```

The result has **3 rows** on the sample data.

If you want to keep every employee and add the department salary total:

```sql
SELECT
    employee_id,
    department_id,
    salary_million,
    SUM(salary_million) OVER (
        PARTITION BY department_id
    ) AS department_salary
FROM window188.employees;
```

The result has **8 rows**.

If you want daily totals and daily cumulative totals:

```sql
WITH daily AS (
    SELECT sold_on, SUM(amount) AS daily_amount
    FROM window188.sales
    GROUP BY sold_on
)
SELECT
    sold_on,
    daily_amount,
    SUM(daily_amount) OVER (
        ORDER BY sold_on
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_amount
FROM daily
ORDER BY sold_on;
```

These are **two processing stages**, not mutually exclusive methods.

Key points to remember:

1. `GROUP BY` changes the query's grain; window functions do not collapse rows—they attach computed values to the current row.
2. `PARTITION BY` defines the group of rows visible to the window; `ORDER BY` inside `OVER` defines ordering and can affect the frame.
3. When `ORDER BY` is present in a window, the default frame can include **tied peer rows**; use `ROWS` and an explicit secondary key for per-record running totals.
4. `WHERE` and `HAVING` apply before windows at the same `SELECT` level; to filter window results, use a **CTE/subquery** and filter outside.
5. `GROUP BY` and windows **can be combined** to compute daily totals, group shares, or rankings over aggregated groups.
6. `LEFT JOIN`, `COUNT(*)`, and `NULL` values can cause miscounts; verify the grain and key columns.
7. Never re-sum group totals repeated on individual employees, never use `DISTINCT` to mask join errors, and never assume windows fabricate missing dates.
8. Optimize performance only after confirming semantics; `EXPLAIN` shows how PostgreSQL executes aggregation/window steps on real data.

**One sentence to remember:** `GROUP BY` answers "how much is each group?", whereas a window function answers "for this row, what is the metric of its group or related rows?".
