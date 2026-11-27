# Top-N Per Group and Handling Ties

A report may need the three highest-paid employees in each department, the five best-selling products in each category, or the latest transactions for each account. This is the **Top-N per group** problem: limiting the number of rows within each group rather than limiting the entire result set.

With standard `ORDER BY ... LIMIT 3`, MySQL returns only three rows for the entire query. To retrieve Top-N separately within each group, MySQL 8.0 provides window functions such as `ROW_NUMBER()`, `RANK()`, and `DENSE_RANK()`. These three functions handle tied values differently, so you must choose according to the exact business rule.

In the **DATABASE_MYSQL** module, this lesson helps you build explainable Top-N reports: how groups are defined, whether "Top 3" includes ties, when exactly N rows are needed, and how to guarantee deterministic result ordering.

## 1. Why doesn't LIMIT solve Top-N per group?

Suppose the `employees` table has columns `employee_id`, `department_id`, `employee_name`, and `salary`. The query:

```sql
SELECT employee_id, department_id, employee_name, salary
FROM employees
ORDER BY salary DESC
LIMIT 3;
```

only retrieves the three highest-paid employees across the entire company. It does not retrieve three employees per department.

To solve Top-N per group, split the data into groups with `PARTITION BY`, sort rows within each group using the window function's `ORDER BY`, and then filter on the computed sequence number or rank.

## 2. Sample dataset

Create a test table:

```sql
CREATE TABLE employees (
    employee_id BIGINT UNSIGNED NOT NULL,
    department_id BIGINT UNSIGNED NOT NULL,
    employee_name VARCHAR(120) NOT NULL,
    salary DECIMAL(12,2) NOT NULL,
    employment_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    PRIMARY KEY (employee_id)
) ENGINE=InnoDB;

INSERT INTO employees
    (employee_id, department_id, employee_name, salary)
VALUES
    (101, 10, 'An',   9000.00),
    (102, 10, 'Binh', 8500.00),
    (103, 10, 'Chi',  8500.00),
    (104, 10, 'Dung', 7000.00),
    (105, 10, 'Ha',   6500.00),
    (201, 20, 'Khanh', 9500.00),
    (202, 20, 'Lan',   9200.00),
    (203, 20, 'Minh',  8800.00),
    (204, 20, 'Nga',   8800.00),
    (205, 20, 'Phuc',  7600.00);
```

Department 10 has two employees tied at `8500.00`; department 20 has two employees tied at `8800.00`. These tie cases help distinguish the three ranking functions.

## 3. PARTITION BY splits groups, ORDER BY ranks within groups

A window function can compute sequence numbers within each department:

```sql
SELECT
    employee_id,
    department_id,
    employee_name,
    salary,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id ASC
    ) AS row_num
FROM employees;
```

- `PARTITION BY department_id` divides rows by department. The counter restarts from 1 for each department.
- `ORDER BY salary DESC` places higher salaries first within each department.
- `employee_id ASC` is a unique tie-breaker that determines ordering among employees with identical salaries.
- `ROW_NUMBER()` assigns a distinct sequence number to each row within a partition.

`PARTITION BY` does not collapse rows like `GROUP BY` does. Every employee remains in the result; the window function simply appends a value computed across related rows.

## 4. Filtering Top-N with ROW_NUMBER()

To retrieve at most three employees per department, use `ROW_NUMBER()` and filter in an outer query block:

```sql
WITH ranked_employees AS (
    SELECT
        employee_id,
        department_id,
        employee_name,
        salary,
        ROW_NUMBER() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC, employee_id ASC
        ) AS row_num
    FROM employees
)
SELECT
    employee_id,
    department_id,
    employee_name,
    salary,
    row_num
FROM ranked_employees
WHERE row_num <= 3
ORDER BY department_id, row_num;
```

The result has at most three rows per department. If two employees share the same salary, the `employee_id` tie-breaker decides who comes first. The query always selects exactly three rows whenever a department has at least three employees.

This is the right choice when the requirement strictly means "no more than N rows per group"—for example, a UI displaying three product cards per category that must not exceed the card limit.

### Why is an outer query or CTE required?

You cannot use the `row_num` alias directly inside `WHERE` in the same query block:

```sql
-- Invalid: WHERE cannot see window function aliases at the same level
SELECT
    employee_id,
    department_id,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC
    ) AS row_num
FROM employees
WHERE row_num <= 3;
```

`WHERE` filters input rows before window function values are produced. Placing the calculation in a CTE or derived table and filtering in the outer query is the proper approach.

## 5. How do ROW_NUMBER, RANK, and DENSE_RANK differ?

All three functions are used for ranking but handle ties differently:

| Function | Numbering | When values tie | Use when |
|---|---|---|---|
| `ROW_NUMBER()` | 1, 2, 3, 4, ... | Each row gets a distinct number | Strictly up to N rows are needed |
| `RANK()` | 1, 2, 2, 4, ... | Tied rank; subsequent ranks skip | Top-N positions keeping all boundary ties |
| `DENSE_RANK()` | 1, 2, 2, 3, ... | Tied rank; next rank is not skipped | Top-N distinct value tiers, e.g., top three salary levels |

Example with descending salaries `100, 90, 90, 80`:

| Salary | `ROW_NUMBER()`* | `RANK()` | `DENSE_RANK()` |
|---:|---:|---:|---:|
| 100 | 1 | 1 | 1 |
| 90 | 2 | 2 | 2 |
| 90 | 3 | 2 | 2 |
| 80 | 4 | 4 | 3 |

*Note:* `ROW_NUMBER()` in this illustration requires a stable secondary sort; whether 2 and 3 go to one 90 row or the other depends on the declared tie-breaker.

`RANK()` reflects a row's position in an ordering with ties. After two rows tied at rank 2, the next rank is 4. `DENSE_RANK()` numbers distinct value tiers consecutively with no gaps.

## 6. Does Top-N keep tied rows at the boundary?

This is the business question you must answer before choosing a function.

### Requirement A: strictly at most N rows per group

Use `ROW_NUMBER()`:

```sql
WITH ranked AS (
    SELECT
        employee_id,
        department_id,
        employee_name,
        salary,
        ROW_NUMBER() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC, employee_id
        ) AS rn
    FROM employees
)
SELECT *
FROM ranked
WHERE rn <= 3;
```

If multiple people tie for third place, only the ones selected by the tie-breaker appear. The output never exceeds three rows per department.

### Requirement B: top three positions, keeping everyone tied at third place

Use `RANK()` and order solely by the tie-defining criterion, here `salary`:

```sql
WITH ranked AS (
    SELECT
        employee_id,
        department_id,
        employee_name,
        salary,
        RANK() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC
        ) AS salary_rank
    FROM employees
)
SELECT *
FROM ranked
WHERE salary_rank <= 3
ORDER BY department_id, salary DESC, employee_id;
```

If multiple people share the third-place salary, all of them are kept. Consequently, the number of rows returned per group may exceed three.

**Do not add `employee_id` to `ORDER BY` inside `RANK()` if people with the same salary should tie.** Ordering by `(salary DESC, employee_id ASC)` means two rows with different IDs are no longer peers and will receive different ranks. You can still use `employee_id` in the outermost `ORDER BY` to sort display output without breaking tie rules.

### Requirement C: top three distinct salary levels

Use `DENSE_RANK()`:

```sql
WITH ranked AS (
    SELECT
        employee_id,
        department_id,
        employee_name,
        salary,
        DENSE_RANK() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC
        ) AS salary_level
    FROM employees
)
SELECT *
FROM ranked
WHERE salary_level <= 3
ORDER BY department_id, salary DESC, employee_id;
```

This query returns all employees earning one of the top three distinct salary levels in each department. If 10 employees share the highest salary, all 10 are kept while occupying only one rank level.

## 7. Distinguishing RANK and DENSE_RANK at the Top-N boundary

Given salaries `100, 90, 90, 80`:

- `RANK() <= 3` returns `100` and `90`. `80` has rank 4 and is excluded.
- `DENSE_RANK() <= 3` returns `100`, `90`, and `80`, as those are the first three distinct salary levels.

Given `100, 100, 90, 80`:

- `RANK() <= 3` returns `100, 100, 90`; `80` has rank 4.
- `DENSE_RANK() <= 3` returns all four rows, because the three distinct salary levels are `100`, `90`, and `80`.

Therefore, "Top 3 with ties" is still ambiguous. Clarify whether it means "top three positions" or "top three distinct value tiers."

## 8. Filtering data before ranking vs. after ranking

`WHERE` inside the CTE executes before the window function computes ranks. `WHERE` in the outer query filters already-ranked results.

Example ranking only active employees:

```sql
UPDATE employees
SET employment_status = 'INACTIVE'
WHERE employee_id = 105;

WITH ranked_active AS (
    SELECT
        employee_id,
        department_id,
        employee_name,
        salary,
        ROW_NUMBER() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC, employee_id
        ) AS rn
    FROM employees
    WHERE employment_status = 'ACTIVE'
)
SELECT *
FROM ranked_active
WHERE rn <= 3;
```

Inactive employees do not participate in ranking. If the status filter were placed in the outer query after computing `ROW_NUMBER()`, inactive employees would still consume rank slots during ranking and then get dropped—leaving a department with fewer than three rows even when eligible active employees exist further down.

Place filters at the right stage according to business rules: filter the candidate pool before ranking, or filter ranked rows afterward.

## 9. Top-N when data contains NULL

If the ranking column allows `NULL`, define where missing values belong. In MySQL, ascending order places `NULL` before non-NULL values; descending order places `NULL` after non-NULL values.

To put high salaries first and explicitly place `NULL` salaries last:

```sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY salary IS NULL ASC,
             salary DESC,
             employee_id ASC
)
```

The expression `salary IS NULL` evaluates to 0 for non-NULL salaries and 1 for `NULL`; sorting ascending places rows with salaries first. If the salary column is `NOT NULL`, this handling is unnecessary.

With `RANK()` or `DENSE_RANK()`, rows with `NULL` in the ranking expression can tie with one another. If `NULL` is not a valid business tier, filter those rows out before ranking:

```sql
FROM employees
WHERE salary IS NOT NULL
```

Do not automatically treat `NULL` as 0 using `COALESCE(salary, 0)` unless business rules truly equate a missing salary with 0; substituting 0 can alter rankings.

## 10. Multi-criteria Top-N

You can rank by multiple columns. For instance, picking the top three products by revenue per category, breaking revenue ties by higher units sold:

```sql
WITH ranked_products AS (
    SELECT
        category_id,
        product_id,
        revenue,
        units_sold,
        ROW_NUMBER() OVER (
            PARTITION BY category_id
            ORDER BY revenue DESC,
                     units_sold DESC,
                     product_id ASC
        ) AS rn
    FROM product_sales
)
SELECT category_id, product_id, revenue, units_sold
FROM ranked_products
WHERE rn <= 3
ORDER BY category_id, revenue DESC, units_sold DESC, product_id;
```

If tie rules depend solely on revenue, `RANK()` must use only `ORDER BY revenue DESC`; `units_sold` and `product_id` can be used in the outermost display order. Clearly defining which columns constitute a tie is essential.

## 11. Top-N per group including empty groups?

Window functions only rank rows present in the input set. If all departments must appear—even departments with zero employees—use the departments table on the left and `LEFT JOIN` against the Top-N result:

```sql
WITH ranked_employees AS (
    SELECT
        employee_id,
        department_id,
        employee_name,
        salary,
        ROW_NUMBER() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC, employee_id
        ) AS rn
    FROM employees
)
SELECT
    d.department_id,
    d.department_name,
    r.employee_id,
    r.employee_name,
    r.salary
FROM departments AS d
LEFT JOIN ranked_employees AS r
    ON r.department_id = d.department_id
   AND r.rn <= 3
ORDER BY d.department_id, r.rn;
```

The condition `r.rn <= 3` is placed in `ON` so departments with no matching employees are preserved. Placing it in `WHERE` would discard rows with `r.rn IS NULL`, effectively turning the `LEFT JOIN` into an inner filter.

## 12. Performance and indexing for Top-N per group

Window functions need to partition and sort rows by the columns in `PARTITION BY` and `ORDER BY`. A suitably ordered index can help reduce read or sort costs, though it does not guarantee MySQL will always avoid sorting or materialization.

For ranking employees by department and salary:

```sql
CREATE INDEX idx_employees_department_salary
    ON employees (department_id, salary DESC, employee_id);
```

Run this index creation once if the table does not already have an index with that name; the DDL at the start of this lesson intentionally created only a primary key so we can observe the index's impact separately in the lab.

The index order starts with `department_id`, followed by `salary` in ranking direction and `employee_id` as the tie-breaker. If queries also filter on `employment_status`, another index such as `(employment_status, department_id, salary, employee_id)` may be worth evaluating based on selectivity and real query patterns.

Inspect the execution plan:

```sql
EXPLAIN
WITH ranked_employees AS (
    SELECT
        employee_id,
        department_id,
        salary,
        ROW_NUMBER() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC, employee_id
        ) AS rn
    FROM employees
)
SELECT employee_id, department_id, salary
FROM ranked_employees
WHERE rn <= 3;
```

Check estimated row counts, chosen index, sort operations, and CTE materialization. In MySQL 8.0.18+, `EXPLAIN ANALYZE` executes the query to measure actual timing and row counts; run it only in an appropriate environment because the statement actually executes.

Do not assume a window function will stop after reading N rows per partition. Under many plans, the server still reads and ranks most or all of the candidate set before filtering `rn <= N`. On very large datasets, benchmark with realistic data and consider alternative query patterns if needed.

## 13. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using `LIMIT N` for the entire query | Returns only N rows across all groups combined | Use a window function with `PARTITION BY` |
| Using `ROW_NUMBER()` when business rules require keeping ties | Some tied rows are dropped | Use `RANK()` or `DENSE_RANK()` per Top-N definition |
| Using `DENSE_RANK()` when N positions are required | May return more rows than expected | Use `RANK()` to keep boundary ties, or `ROW_NUMBER()` to cap rows |
| Adding a unique key to `ORDER BY` inside `RANK()` | Rows no longer tie | Rank only by tie-defining criteria; put tie-breaker in `ROW_NUMBER()` or outer `ORDER BY` |
| Filtering window alias in same-level `WHERE` | Alias scope error | Use a CTE or derived table |
| Filtering rows after ranking when they should be excluded beforehand | Ineligible rows consume rank positions | Put candidate filters in the CTE before the window function |
| Missing tie-breaker for `ROW_NUMBER()` | Nondeterministic order among tied values | Add a unique key to window `ORDER BY` |
| Ignoring `NULL`s in the ranking column | Rows with missing data may land in unintended positions | Define explicit NULL rules or filter NULLs before ranking |

## 14. Checklist for choosing a ranking function

Before writing a Top-N query, answer:

1. Which column(s) define the group in `PARTITION BY`?
2. What is the primary ranking criterion and sort direction (ascending/descending)?
3. Does "Top N" mean strictly at most N rows, N positions keeping ties, or N distinct value tiers?
4. If using `ROW_NUMBER()`, which tie-breaker guarantees unique ordering?
5. If using `RANK()`/`DENSE_RANK()`, which columns actually define a tie?
6. Which filter predicates must apply before ranking?
7. Can the ranking column be `NULL`, and how should NULLs be handled?
8. Should groups with zero rows still appear via `LEFT JOIN`?
9. Do indexes support the partition, order, and filter columns?
10. Have you checked `EXPLAIN` or `EXPLAIN ANALYZE` on representative data?

## 15. Practice exercises

Using the `employees` table from the beginning of the lesson:

1. Write a query returning strictly at most two highest-paid employees per department using `ROW_NUMBER()`.
2. Use `RANK()` to retrieve the top three salary positions while keeping all employees tied at the boundary.
3. Use `DENSE_RANK()` to retrieve employees earning the top three distinct salary levels in each department.
4. Add `employee_id` to `RANK()`'s `ORDER BY`; observe how equal-salary rows lose their tied status and explain why.
5. On the test table, allow `salary` to be `NULL` via `ALTER TABLE employees MODIFY salary DECIMAL(12,2) NULL`, insert an employee with a `NULL` salary, and test ranking with and without an explicit NULL rule.
6. Rank only `ACTIVE` employees; compare results when filtering status inside the CTE vs. in the outer query.
7. Use `LEFT JOIN` to display departments with zero employees in the Top-N list.
8. Use `EXPLAIN` to inspect the impact of index `(department_id, salary, employee_id)`.

You have completed this lesson when you can choose accurately between `ROW_NUMBER()`, `RANK()`, and `DENSE_RANK()` based on tie policy, build Top-N queries per partition, and explain when a ranking order requires a tie-breaker or must omit one. Always define the business meaning of "Top-N" before selecting a function, because different choices change both the row count and which individuals are returned.
